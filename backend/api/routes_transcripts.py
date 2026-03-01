"""
api/routes_transcripts.py — Transcript file upload and listing.
"""
from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime
from typing import Optional

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

    # Write to Airtable
    at_client = AirtableClient()

    fields: dict = {
        "Raw Transcript Text": raw_text[:100_000],
        "Transcript (extracted)": raw_text[:100_000],
        "Speaker Labels": ", ".join(parsed.speaker_labels or []),
        "Uploaded By": [user.airtable_user_record_id] if user.airtable_user_record_id else [],
    }
    if meeting_type:
        fields["Meeting Type"] = meeting_type
    if meeting_date:
        fields["Meeting Date"] = meeting_date
    if file.filename:
        fields["Title"] = file.filename

    transcript_record = at_client.create_record("transcripts", fields)
    transcript_record_id = transcript_record["id"]

    return TranscriptUploadResponse(
        transcript_id=transcript_record_id,
        speaker_labels=parsed.speaker_labels or [],
        word_count=parsed.metadata.word_count,
        meeting_type=meeting_type,
        meeting_date=meeting_date,
    )


@router.get("/api/transcripts", response_model=list[TranscriptListItem])
async def list_transcripts(
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    if user.airtable_user_record_id:
        formula = f"FIND('{user.airtable_user_record_id}', ARRAYJOIN({{Uploaded By}}))"
        records = at_client.search_records("transcripts", formula, max_records=50)
    else:
        records = []

    items = []
    for rec in records:
        f = rec.get("fields", {})
        items.append(
            TranscriptListItem(
                transcript_id=rec["id"],
                title=f.get("Title"),
                meeting_type=f.get("Meeting Type"),
                meeting_date=f.get("Meeting Date"),
                created_at=rec.get("createdTime"),
            )
        )
    return items
