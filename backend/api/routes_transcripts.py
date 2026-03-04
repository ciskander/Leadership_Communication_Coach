"""
api/routes_transcripts.py — Transcript file upload and listing.
"""
from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from ..core.transcript_parser import parse_transcript
from .dependencies import get_current_user
from .dto import TranscriptListItem, TranscriptUploadResponse
from .errors import invalid_input, transcript_parse_fail

router = APIRouter()

_ALLOWED_EXTENSIONS = {".txt", ".vtt", ".srt", ".docx", ".pdf"}
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Date patterns to try detecting from raw transcript text
_DATE_PATTERNS = [
    # ISO: 2026-03-03
    (r'\b(\d{4}-\d{2}-\d{2})\b', '%Y-%m-%d'),
    # US long: March 3, 2026 / March 03, 2026
    (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b', None),
    # US short: 03/03/2026 or 3/3/2026
    (r'\b(\d{1,2}/\d{1,2}/\d{4})\b', '%m/%d/%Y'),
]


def _detect_date_from_text(text: str) -> Optional[str]:
    """Try to extract a meeting date from the first 2000 chars of transcript text.
    Returns an ISO date string (YYYY-MM-DD) or None."""
    sample = text[:2000]
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, sample, re.IGNORECASE)
        if match:
            raw = match.group(1)
            if fmt:
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            else:
                # Try parsing month-name formats
                for month_fmt in ('%B %d, %Y', '%B %d %Y', '%B %dst, %Y', '%B %dnd, %Y', '%B %drd, %Y', '%B %dth, %Y'):
                    try:
                        clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', raw, flags=re.IGNORECASE)
                        dt = datetime.strptime(clean.strip().rstrip(','), '%B %d %Y')
                        return dt.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
    return None

def _extract_speaker_previews(turns: list, max_per_speaker: int = 2) -> dict:
    """Return up to max_per_speaker utterances per speaker, truncated to 120 chars."""
    previews: dict = {}
    for turn in turns:
        label = turn.speaker_label
        if label not in previews:
            previews[label] = []
        if len(previews[label]) < max_per_speaker:
            snippet = turn.text.strip()[:120]
            if len(turn.text.strip()) > 120:
                snippet += "…"
            previews[label].append(snippet)
    return previews

def _extract_text(data: bytes, filename: str) -> str:
    """Extract plain text from various file formats."""
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".txt", ".vtt", ".srt"):
        return data.decode("utf-8", errors="replace")

    if ext == ".docx":
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    if ext == ".pdf":
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)

    raise ValueError(f"Unsupported file type: {ext}")


@router.post("/api/transcripts", response_model=TranscriptUploadResponse)
async def upload_transcript(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    meeting_type: Optional[str] = Form(default=None),
    meeting_date: Optional[str] = Form(default=None),
    user: UserAuth = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return invalid_input(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
        )

    data = await file.read()
    if len(data) > _MAX_FILE_SIZE:
        return invalid_input("File exceeds 5 MB limit.")

    # Extract text
    try:
        raw_text = _extract_text(data, file.filename or "transcript.txt")
    except Exception as exc:
        return transcript_parse_fail(f"Could not extract text: {exc}")

    # Parse transcript (speaker labels, word count, etc.)
    try:
        parsed = parse_transcript(
            data=raw_text.encode("utf-8"),
            filename=file.filename or "transcript.txt",
            source_id="",
        )
    except Exception as exc:
        return transcript_parse_fail(f"Transcript parse error: {exc}")

    # Auto-detect date from raw text if not provided
    detected_date: Optional[str] = None
    if not meeting_date:
        detected_date = _detect_date_from_text(raw_text)

    effective_date = meeting_date or detected_date

    # Build speaker previews from parsed turns
    speaker_previews = _extract_speaker_previews(parsed.turns)

    # Write to Airtable
    at_client = AirtableClient()

    fields: dict = {
        "Raw Transcript Text": raw_text[:100_000],
        "Transcript (extracted)": raw_text[:100_000],
        "Speaker Labels": ", ".join(parsed.speaker_labels or []),
        "Uploaded By": [user.airtable_user_record_id] if user.airtable_user_record_id else [],
        "Title": title or file.filename or "Untitled",
    }
    if meeting_type:
        fields["Meeting Type"] = meeting_type
    if effective_date:
        fields["Meeting Date"] = effective_date

    transcript_record = at_client.create_record("transcripts", fields)
    transcript_record_id = transcript_record["id"]

    return TranscriptUploadResponse(
        transcript_id=transcript_record_id,
        speaker_labels=parsed.speaker_labels or [],
        word_count=parsed.metadata.word_count,
        meeting_type=meeting_type,
        meeting_date=effective_date,
        detected_date=detected_date,
        speaker_previews=speaker_previews,
    )

@router.get("/api/transcripts", response_model=list[TranscriptListItem])
async def list_transcripts(
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()

    # Coaches and admins can see all transcripts; coachees only see their own.
    if user.role in ("coach", "admin"):
        formula = ""
    elif user.airtable_user_record_id:
        # "Uploaded By" is a linked record field. ARRAYJOIN returns the primary field
        # values of linked users (e.g. "U-0001"), not Airtable record IDs. We must
        # fetch the user's Airtable record to get their User ID primary field value.
        try:
            at_user = at_client.get_user(user.airtable_user_record_id)
            user_primary_id = at_user.get("fields", {}).get("User ID", "")
        except Exception as e:
            logger.warning("Could not fetch Airtable user record for transcript filter: %s", e)
            return []
        if not user_primary_id:
            return []
        formula = f"FIND('{user_primary_id}', ARRAYJOIN({{Uploaded By}}))"
    else:
        # No Airtable record linked — return empty list rather than leaking all transcripts
        return []

    records = at_client.search_records("transcripts", formula, max_records=50)

    items = []
    for rec in records:
        f = rec.get("fields", {})
        raw_labels = f.get("Speaker Labels") or ""
        speaker_labels = [s.strip() for s in raw_labels.split(",") if s.strip()]
        items.append(
            TranscriptListItem(
                transcript_id=rec["id"],
                title=f.get("Title"),
                meeting_type=f.get("Meeting Type"),
                meeting_date=f.get("Meeting Date"),
                created_at=rec.get("createdTime"),
                speaker_labels=speaker_labels,
            )
        )
    return items
