"""
api/routes_runs.py — Run status polling and result retrieval with quote resolution.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
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

_QUOTE_MAX_CHARS = 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_quotes(
    evidence_span_ids: list[str],
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
) -> list[QuoteObject]:
    quotes: list[QuoteObject] = []
    for es_id in evidence_span_ids:
        span = spans_by_id.get(es_id)
        if not span:
            continue
        excerpt = (span.get("excerpt") or "")[:_QUOTE_MAX_CHARS]
        quotes.append(
            QuoteObject(
                speaker_label=span.get("speaker_role"),
                quote_text=excerpt,
                meeting_id=span.get("meeting_id") or meeting_id,
                transcript_id=transcript_id,
                span_id=es_id,
            )
        )
    return quotes


def _build_run_response(run_record: dict) -> RunStatusResponse:
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

    resp = RunStatusResponse(
        run_id=run_id,
        status=status,
        gate1_pass=gate1_pass,
        analysis_type=analysis_type,
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

    # Coaching output with resolved quotes
    coaching = parsed_json.get("coaching_output", {})

    strengths: list[CoachingItemWithQuotes] = []
    for s in coaching.get("strengths", []):
        quotes = _resolve_quotes(s.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id)
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
        quotes = _resolve_quotes(f.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id)
        focus = CoachingItemWithQuotes(
            pattern_id=f.get("pattern_id", ""),
            message=f.get("message", ""),
            quotes=quotes,
        )

    micro_exp: Optional[MicroExperimentWithQuotes] = None
    micro_list = coaching.get("micro_experiment", [])
    if micro_list:
        m = micro_list[0]
        quotes = _resolve_quotes(m.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id)
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
    resp.experiment_tracking = parsed_json.get("experiment_tracking")

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

    # Ownership check (coachees can only see their own runs)
    fields = run_record.get("fields", {})
    coachee_id = fields.get("Coachee ID")
    if user.role == "coachee":
        if coachee_id and coachee_id != user.airtable_user_record_id:
            return error_response("FORBIDDEN", "You do not have access to this run.", 403)

    return _build_run_response(run_record)


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
