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
    ExperimentDetectionWithQuotes,
    ExperimentResponse,
    RunRequestStatusResponse,
    RunStatusResponse,
)
from .errors import error_response
from .quote_helpers import (
    build_spans_lookup,
    build_turn_map,
    resolve_coaching_output,
    resolve_pattern_snapshot,
    resolve_quotes,
)

router = APIRouter()


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
    spans_by_id = build_spans_lookup(parsed_json)

    transcript_links = fields.get("Transcript ID", [])
    transcript_id = transcript_links[0] if isinstance(transcript_links, list) and transcript_links else None
    meeting_id = parsed_json.get("context", {}).get("meeting_id")

    # Build turn map for timestamp display and multi-speaker expansion
    turn_map = build_turn_map(at_client, transcript_id) if at_client else {}

    # Coaching output with resolved quotes
    strengths, focus, micro_exp = resolve_coaching_output(
        parsed_json, spans_by_id, transcript_id, meeting_id, turn_map
    )
    resp.strengths = strengths
    resp.focus = focus
    resp.micro_experiment = micro_exp

    # ── Pattern snapshot with per-pattern quotes and coaching ──────────────
    snapshot_items = resolve_pattern_snapshot(
        parsed_json, spans_by_id, transcript_id, meeting_id, turn_map
    )
    resp.pattern_snapshot = snapshot_items if snapshot_items else None

    resp.evaluation_summary = parsed_json.get("evaluation_summary")

    # ── Experiment tracking ────────────────────────────────────────────────
    exp_tracking = parsed_json.get("experiment_tracking")
    if exp_tracking:
        active_exp = exp_tracking.get("active_experiment") or {}
        exp_id_str = active_exp.get("experiment_id")
        if exp_id_str and exp_id_str != "EXP-000000":
            _links = fields.get("Active Experiment", [])
            if _links:
                active_exp["experiment_record_id"] = _links[0]

        # Build typed experiment detection with quotes and coaching
        detection = exp_tracking.get("detection_in_this_meeting")
        if isinstance(detection, dict):
            det_quotes = resolve_quotes(
                detection.get("evidence_span_ids", []),
                spans_by_id,
                transcript_id,
                meeting_id,
                turn_map,
            )
            resp.experiment_detection = ExperimentDetectionWithQuotes(
                experiment_id=detection.get("experiment_id", ""),
                attempt=detection.get("attempt", "no"),
                count_attempts=detection.get("count_attempts", 0),
                quotes=det_quotes,
                coaching_note=detection.get("coaching_note"),
                suggested_rewrite=detection.get("suggested_rewrite"),
                rewrite_for_span_id=detection.get("rewrite_for_span_id"),
            )
            # Keep raw quotes on the dict for backwards compat
            detection["quotes"] = [q.model_dump() for q in det_quotes]

    resp.experiment_tracking = exp_tracking

    # ── Fetch full experiment detail + events for inline rendering ─────────
    if at_client and exp_tracking:
        active_exp = exp_tracking.get("active_experiment") or {}
        exp_record_id = active_exp.get("experiment_record_id")
        if exp_record_id and active_exp.get("status") == "active":
            try:
                exp_rec = at_client.get_experiment(exp_record_id)
                ef = exp_rec.get("fields", {})
                attempt_count, meeting_count = at_client.count_experiment_attempts_and_meetings(exp_rec["id"])
                resp.active_experiment_detail = ExperimentResponse(
                    experiment_record_id=exp_rec["id"],
                    experiment_id=ef.get("Experiment ID", ""),
                    title=ef.get("Title", ""),
                    instruction=ef.get("Instructions") or ef.get("Instruction", ""),
                    success_marker=ef.get("Success Marker") or ef.get("Success Criteria", ""),
                    pattern_id=ef.get("Pattern ID", ""),
                    status=ef.get("Status", ""),
                    created_at=exp_rec.get("createdTime"),
                    attempt_count=attempt_count,
                    meeting_count=meeting_count,
                    started_at=ef.get("Started At"),
                    ended_at=ef.get("Ended At"),
                )
                exp_primary_id = ef.get("Experiment ID", "")
                if exp_primary_id:
                    events_formula = f"FIND('{exp_primary_id}', ARRAYJOIN({{Experiment}}))"
                    event_records = at_client.search_records(
                        "experiment_events", events_formula, max_records=10,
                    )
                    resp.active_experiment_events = [
                        {
                            "event_id": er["id"],
                            "attempt": er.get("fields", {}).get("Attempt Enum"),
                            "meeting_date": er.get("fields", {}).get("Meeting Date"),
                            "human_confirmed": er.get("fields", {}).get("User Confirmation"),
                            "notes": er.get("fields", {}).get("Notes"),
                        }
                        for er in event_records
                    ]
            except Exception:
                pass  # Non-fatal — frontend falls back to separate API call

        # Look up whether the user already submitted a human confirmation for
        # this run, so the frontend can restore the override state on refresh.
        exp_id_for_idem = (exp_tracking.get("active_experiment") or {}).get("experiment_id")
        if at_client and exp_id_for_idem:
            idem_key = f"human:{run_id}:{exp_id_for_idem}"
            try:
                existing = at_client.find_experiment_event_by_idempotency_key(idem_key)
                if existing:
                    resp.human_confirmation = existing.get("fields", {}).get("User Confirmation")
            except Exception:
                pass

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
