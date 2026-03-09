"""
api/routes_runs.py — Run status polling and result retrieval with quote resolution.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from ..core.transcript_parser import parse_transcript
from .dependencies import get_current_user
from .dto import (
    CoachingItemWithQuotes,
    MicroExperimentWithQuotes,
    QuoteObject,
    RunRequestStatusResponse,
    RunStatusResponse,
)
from .errors import error_response

router = APIRouter()

_QUOTE_MAX_CHARS = 2000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS for display."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_turn_timestamps(
    at_client: AirtableClient,
    transcript_record_id: Optional[str],
) -> dict[int, Optional[float]]:
    """Parse the transcript and return a {turn_id: start_time_sec} lookup."""
    if not transcript_record_id:
        return {}
    try:
        tr_record = at_client.get_transcript(transcript_record_id)
        tr_fields = tr_record.get("fields", {})
        transcript_text = (
            tr_fields.get("Transcript (extracted)")
            or tr_fields.get("Raw Transcript Text")
            or ""
        )
        if not transcript_text:
            return {}
        parsed = parse_transcript(
            data=transcript_text.encode("utf-8"),
            filename="transcript.txt",
            source_id=tr_fields.get("Transcript ID") or transcript_record_id,
        )
        return {t.turn_id: t.start_time_sec for t in parsed.turns}
    except Exception:
        return {}


def _resolve_quotes(
    evidence_span_ids: list[str],
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
    turn_timestamps: Optional[dict[int, Optional[float]]] = None,
) -> list[QuoteObject]:
    quotes: list[QuoteObject] = []
    for es_id in evidence_span_ids:
        span = spans_by_id.get(es_id)
        if not span:
            continue
        excerpt = (span.get("excerpt") or "")[:_QUOTE_MAX_CHARS]
        # Look up timestamp from parsed transcript turns
        start_ts: Optional[str] = None
        if turn_timestamps:
            turn_id = span.get("turn_start_id")
            if isinstance(turn_id, int):
                sec = turn_timestamps.get(turn_id)
                if sec is not None:
                    start_ts = _format_timestamp(sec)
        quotes.append(
            QuoteObject(
                speaker_label=span.get("speaker_role"),
                quote_text=excerpt,
                meeting_id=span.get("meeting_id") or meeting_id,
                transcript_id=transcript_id,
                span_id=es_id,
                start_timestamp=start_ts,
            )
        )
    return quotes


def _build_run_response(run_record: dict, at_client: Optional[AirtableClient] = None) -> RunStatusResponse:
    fields = run_record.get("fields", {})
    run_id = run_record["id"]

    gate1_pass: Optional[bool] = fields.get("Gate1 Pass")
    analysis_type: Optional[str] = fields.get("Analysis Type")

    # Determine status from gate1 pass and whether parsed JSON exists
    parsed_json_str = fields.get("Parsed JSON")
    if parsed_json_str:
        status = "complete"
    elif fields.get("Parse OK") is False:
        status = "error"
    else:
        status = "running"

    if not gate1_pass and status == "complete":
        status = "complete"  # complete but with gate1 fail

    bp_links = fields.get("baseline_pack", [])
    baseline_pack_id = bp_links[0] if isinstance(bp_links, list) and bp_links else None

    resp = RunStatusResponse(
        run_id=run_id,
        status=status,
        gate1_pass=gate1_pass,
        analysis_type=analysis_type,
        baseline_pack_id=baseline_pack_id,
    )

    if not parsed_json_str:
        return resp

    try:
        parsed_json = json.loads(parsed_json_str)
    except json.JSONDecodeError:
        resp.error = {"code": "PARSE_ERROR", "message": "Run output could not be decoded."}
        return resp

    # Build spans lookup
    evidence_spans: list[dict] = parsed_json.get("evidence_spans", [])
    spans_by_id: dict[str, dict] = {
        s.get("evidence_span_id", ""): s for s in evidence_spans
    }

    transcript_links = fields.get("Transcript ID", [])
    transcript_id = transcript_links[0] if isinstance(transcript_links, list) and transcript_links else None
    meeting_id = parsed_json.get("context", {}).get("meeting_id")

    # Build turn timestamp lookup for evidence quote display
    turn_timestamps = _build_turn_timestamps(at_client, transcript_id) if at_client else {}

    # Coaching output with resolved quotes
    coaching = parsed_json.get("coaching_output", {})

    strengths: list[CoachingItemWithQuotes] = []
    for s in coaching.get("strengths", []):
        quotes = _resolve_quotes(s.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id, turn_timestamps)
        strengths.append(
            CoachingItemWithQuotes(
                pattern_id=s.get("pattern_id", ""),
                message=s.get("message", ""),
                quotes=quotes,
            )
        )

    focus: Optional[CoachingItemWithQuotes] = None
    focus_list = coaching.get("focus", [])
    if focus_list:
        f = focus_list[0]
        rewrite_span_id = f.get("rewrite_for_span_id")
        all_es_ids = f.get("evidence_span_ids", [])

        # Split: primary quote (the one the rewrite applies to) vs additional
        if rewrite_span_id and rewrite_span_id in all_es_ids:
            primary_ids = [rewrite_span_id]
            additional_ids = [eid for eid in all_es_ids if eid != rewrite_span_id]
        else:
            # Fallback: first span is primary, rest are additional
            primary_ids = all_es_ids[:1]
            additional_ids = all_es_ids[1:]

        primary_quotes = _resolve_quotes(primary_ids, spans_by_id, transcript_id, meeting_id, turn_timestamps)
        additional_quotes = _resolve_quotes(additional_ids, spans_by_id, transcript_id, meeting_id, turn_timestamps)

        focus = CoachingItemWithQuotes(
            pattern_id=f.get("pattern_id", ""),
            message=f.get("message", ""),
            quotes=primary_quotes,
            suggested_rewrite=f.get("suggested_rewrite"),
            rewrite_for_span_id=rewrite_span_id,
            additional_quotes=additional_quotes,
        )

    micro_exp: Optional[MicroExperimentWithQuotes] = None
    micro_list = coaching.get("micro_experiment", [])
    if micro_list:
        m = micro_list[0]
        quotes = _resolve_quotes(m.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id, turn_timestamps)
        micro_exp = MicroExperimentWithQuotes(
            experiment_id=m.get("experiment_id", ""),
            title=m.get("title", ""),
            instruction=m.get("instruction", ""),
            success_marker=m.get("success_marker", ""),
            pattern_id=m.get("pattern_id", ""),
            quotes=quotes,
        )

    resp.strengths = strengths
    resp.focus = focus
    resp.micro_experiment = micro_exp
    resp.pattern_snapshot = parsed_json.get("pattern_snapshot")
    resp.evaluation_summary = parsed_json.get("evaluation_summary")
    # Inject experiment_record_id into active_experiment so the frontend
    # can call lifecycle endpoints without a separate lookup
    exp_tracking = parsed_json.get("experiment_tracking")
    if exp_tracking:
        active_exp = exp_tracking.get("active_experiment") or {}
        exp_id_str = active_exp.get("experiment_id")
        if exp_id_str and exp_id_str != "EXP-000000":
            # Use the Active Experiment link stored directly on the run record
            _links = fields.get("Active Experiment", [])
            if _links:
                active_exp["experiment_record_id"] = _links[0]

        # Resolve detection evidence spans into quotes for the frontend
        detection = exp_tracking.get("detection_in_this_meeting")
        if isinstance(detection, dict):
            det_quotes = _resolve_quotes(
                detection.get("evidence_span_ids", []),
                spans_by_id,
                transcript_id,
                meeting_id,
                turn_timestamps,
            )
            detection["quotes"] = [q.model_dump() for q in det_quotes]

    resp.experiment_tracking = exp_tracking

    return resp


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/runs/{run_id}")
async def get_run(
    run_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        run_record = at_client.get_run(run_id)
    except Exception:
        return error_response("NOT_FOUND", f"Run {run_id} not found.", 404)

    # Ownership check: coachees can only see their own runs.
    # Deny access if Coachee ID is blank — don't silently allow it.
    fields = run_record.get("fields", {})
    coachee_id = fields.get("Coachee ID")
    if user.role == "coachee":
        if coachee_id != user.airtable_user_record_id:
            return error_response("FORBIDDEN", "You do not have access to this run.", 403)

    return _build_run_response(run_record, at_client)


@router.get("/api/run_requests/{rr_id}", response_model=RunRequestStatusResponse)
async def get_run_request_status(
    rr_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        rr_record = at_client.get_run_request(rr_id)
    except Exception:
        return error_response("NOT_FOUND", f"RunRequest {rr_id} not found.", 404)

    fields = rr_record.get("fields", {})

    # Ownership check: coachees can only poll their own run requests.
    if user.role == "coachee":
        user_links = fields.get("User", [])
        if not isinstance(user_links, list) or user.airtable_user_record_id not in user_links:
            return error_response("FORBIDDEN", "You do not have access to this run request.", 403)

    status = fields.get("Status", "queued")
    run_links = fields.get("Run", [])
    run_id = run_links[0] if isinstance(run_links, list) and run_links else None
    error_msg = fields.get("Error")

    error_detail = None
    if error_msg:
        error_detail = {"code": "JOB_FAILED", "message": error_msg}

    return RunRequestStatusResponse(
        run_request_id=rr_id,
        status=status,
        run_id=run_id,
        error=error_detail,
    )
