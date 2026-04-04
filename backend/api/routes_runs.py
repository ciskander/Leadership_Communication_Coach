"""
api/routes_runs.py — Run status polling and result retrieval with quote resolution.

Performance: Airtable calls are parallelized via asyncio.to_thread + gather.
Quote cleanup runs in a background thread so it doesn't block the response when
the persistent cache misses.
"""
from __future__ import annotations

import asyncio
import json
import logging
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
    resolve_experiment_coaching,
    resolve_pattern_coaching,
    resolve_pattern_snapshot,
    resolve_quotes,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _fetch_experiment_detail(
    at_client: AirtableClient, exp_record_id: str
) -> tuple[Optional[dict], list[dict]]:
    """Fetch experiment record, attempt counts, and events in minimal calls.

    Returns (experiment_record_or_None, event_list).
    """
    try:
        exp_rec = at_client.get_experiment(exp_record_id)
        ef = exp_rec.get("fields", {})
        attempt_count, meeting_count = at_client.count_experiment_attempts_and_meetings(exp_rec["id"])
        exp_rec["_attempt_count"] = attempt_count
        exp_rec["_meeting_count"] = meeting_count

        exp_primary_id = ef.get("Experiment ID", "")
        events: list[dict] = []
        if exp_primary_id:
            events_formula = f"FIND('{exp_primary_id}', ARRAYJOIN({{Experiment}}))"
            events = at_client.search_records(
                "experiment_events", events_formula, max_records=10,
            )
        return exp_rec, events
    except Exception:
        return None, []


def _fetch_human_confirmation(
    at_client: AirtableClient, run_id: str, exp_id: str
) -> Optional[str]:
    """Look up existing human confirmation for this run+experiment."""
    idem_key = f"human:{run_id}:{exp_id}"
    try:
        existing = at_client.find_experiment_event_by_idempotency_key(idem_key)
        if existing:
            return existing.get("fields", {}).get("User Confirmation")
    except Exception:
        pass
    return None


async def _build_run_response(run_record: dict, at_client: Optional[AirtableClient] = None) -> RunStatusResponse:
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

    target_speaker_label: Optional[str] = fields.get("Target Speaker Label")

    resp = RunStatusResponse(
        run_id=run_id,
        status=status,
        gate1_pass=gate1_pass,
        analysis_type=analysis_type,
        baseline_pack_id=baseline_pack_id,
        target_speaker_label=target_speaker_label,
    )

    if not parsed_json_str:
        return resp

    try:
        parsed_json = json.loads(parsed_json_str)
    except json.JSONDecodeError:
        resp.error = {"code": "PARSE_ERROR", "message": "Run output could not be decoded."}
        return resp

    # Prefer the target_speaker_label from the LLM output context — it is
    # guaranteed to match the speaker labels used in the transcript turns.
    # Fall back to the Airtable field if the context is missing.
    context_label = parsed_json.get("context", {}).get("target_speaker_label")
    if context_label:
        resp.target_speaker_label = context_label

    # Use context label for quote-level is_target_speaker marking
    effective_target = context_label or target_speaker_label

    logger.info(
        "run %s: airtable_label=%r  context_label=%r  effective_target=%r",
        run_id, target_speaker_label, context_label, effective_target,
    )

    # Build spans lookup (pure computation, fast)
    spans_by_id = build_spans_lookup(parsed_json)

    transcript_links = fields.get("Transcript ID", [])
    transcript_id = transcript_links[0] if isinstance(transcript_links, list) and transcript_links else None
    meeting_id = parsed_json.get("context", {}).get("meeting_id")

    # ── Determine what parallel fetches we need ───────────────────────────
    exp_tracking = parsed_json.get("experiment_tracking")
    active_exp = (exp_tracking.get("active_experiment") or {}) if exp_tracking else {}
    exp_id_str = active_exp.get("experiment_id")
    if exp_id_str and exp_id_str != "EXP-000000":
        _links = fields.get("Active Experiment", [])
        if _links:
            active_exp["experiment_record_id"] = _links[0]

    exp_record_id = active_exp.get("experiment_record_id") if active_exp.get("status") == "active" else None
    exp_id_for_idem = active_exp.get("experiment_id") if exp_tracking else None

    # ── Launch parallel Airtable fetches ──────────────────────────────────
    # 1. Transcript (for turn map) — always needed for completed runs
    # 2. Experiment detail + events — needed when active experiment exists
    # 3. Human confirmation lookup — needed when experiment tracking active
    futures = []
    future_keys = []

    if at_client and transcript_id:
        futures.append(asyncio.to_thread(build_turn_map, at_client, transcript_id))
        future_keys.append("turn_map")

    if at_client and exp_record_id:
        futures.append(asyncio.to_thread(_fetch_experiment_detail, at_client, exp_record_id))
        future_keys.append("exp_detail")

    if at_client and exp_id_for_idem:
        futures.append(asyncio.to_thread(_fetch_human_confirmation, at_client, run_id, exp_id_for_idem))
        future_keys.append("human_confirm")

    # Run all Airtable fetches concurrently
    results_map: dict = {}
    if futures:
        results = await asyncio.gather(*futures, return_exceptions=True)
        for key, result in zip(future_keys, results):
            if isinstance(result, Exception):
                logger.warning("Parallel fetch %s failed: %s", key, result)
                results_map[key] = None
            else:
                results_map[key] = result

    turn_map = results_map.get("turn_map") or {}

    # ── Resolve quotes (pure computation using fetched data) ──────────────
    # Executive summary
    coaching_section = parsed_json.get("coaching", {})
    resp.executive_summary = coaching_section.get("executive_summary")

    # Coaching themes (cross-pattern synthesis)
    raw_themes = coaching_section.get("coaching_themes", [])
    if raw_themes and isinstance(raw_themes, list):
        from backend.api.dto import CoachingTheme
        for t in raw_themes:
            if not isinstance(t, dict) or not t.get("theme"):
                continue
            # Resolve CT- span quotes for this theme
            theme_span_ids = [
                sid for sid in [t.get("best_success_span_id"), t.get("rewrite_for_span_id")]
                if sid
            ]
            theme_quotes = resolve_quotes(
                theme_span_ids, spans_by_id, transcript_id, meeting_id, turn_map, effective_target,
            ) if theme_span_ids else []
            resp.coaching_themes.append(CoachingTheme(
                theme=t.get("theme", ""),
                explanation=t.get("explanation", ""),
                related_patterns=t.get("related_patterns", []),
                priority=t.get("priority", "primary"),
                nature=t.get("nature", "developmental"),
                best_success_span_id=t.get("best_success_span_id"),
                coaching_note=t.get("coaching_note"),
                suggested_rewrite=t.get("suggested_rewrite"),
                rewrite_for_span_id=t.get("rewrite_for_span_id"),
                quotes=theme_quotes,
            ))

    # Coaching output with resolved quotes
    focus, micro_exp = resolve_coaching_output(
        parsed_json, spans_by_id, transcript_id, meeting_id, turn_map, effective_target
    )
    resp.focus = focus
    resp.micro_experiment = micro_exp

    # Pattern snapshot with per-pattern quotes and coaching
    snapshot_items = resolve_pattern_snapshot(
        parsed_json, spans_by_id, transcript_id, meeting_id, turn_map, effective_target
    )
    resp.pattern_snapshot = snapshot_items if snapshot_items else None

    # Pattern coaching (separate from pattern_snapshot in v0.4.0)
    resp.pattern_coaching = resolve_pattern_coaching(parsed_json)

    # Experiment coaching (from coaching.experiment_coaching)
    resp.experiment_coaching = resolve_experiment_coaching(parsed_json)

    resp.evaluation_summary = parsed_json.get("evaluation_summary")

    # ── Experiment tracking ────────────────────────────────────────────────
    if exp_tracking:
        # Build typed experiment detection with quotes and coaching
        detection = exp_tracking.get("detection_in_this_meeting")
        if isinstance(detection, dict):
            det_quotes = resolve_quotes(
                detection.get("evidence_span_ids", []),
                spans_by_id,
                transcript_id,
                meeting_id,
                turn_map,
                effective_target,
            )
            # In v0.4.0, coaching fields come from coaching.experiment_coaching, not detection
            exp_coaching = coaching_section.get("experiment_coaching")
            resp.experiment_detection = ExperimentDetectionWithQuotes(
                experiment_id=detection.get("experiment_id", ""),
                attempt=detection.get("attempt", "no"),
                count_attempts=detection.get("count_attempts", 0),
                quotes=det_quotes,
                coaching_note=exp_coaching.get("coaching_note") if isinstance(exp_coaching, dict) else None,
                suggested_rewrite=exp_coaching.get("suggested_rewrite") if isinstance(exp_coaching, dict) else None,
                rewrite_for_span_id=exp_coaching.get("rewrite_for_span_id") if isinstance(exp_coaching, dict) else None,
            )
            # Keep raw quotes on the dict for backwards compat
            detection["quotes"] = [q.model_dump() for q in det_quotes]

    resp.experiment_tracking = exp_tracking

    # ── Apply parallel fetch results for experiment detail ─────────────────
    exp_detail_result = results_map.get("exp_detail")
    if exp_detail_result and exp_detail_result[0]:
        exp_rec, event_records = exp_detail_result
        ef = exp_rec.get("fields", {})
        # Parse related_patterns; fall back to legacy Pattern ID
        _rp_raw = ef.get("Related Patterns") or ""
        _rp: list[str] = []
        if _rp_raw:
            try:
                _rp = json.loads(_rp_raw)
            except (json.JSONDecodeError, TypeError):
                _rp = []
        if not _rp and ef.get("Pattern ID"):
            _rp = [ef["Pattern ID"]]
        resp.active_experiment_detail = ExperimentResponse(
            experiment_record_id=exp_rec["id"],
            experiment_id=ef.get("Experiment ID", ""),
            title=ef.get("Title", ""),
            instruction=ef.get("Instructions") or ef.get("Instruction", ""),
            success_marker=ef.get("Success Marker") or ef.get("Success Criteria", ""),
            pattern_id=ef.get("Pattern ID", ""),
            related_patterns=_rp,
            status=ef.get("Status", ""),
            created_at=exp_rec.get("createdTime"),
            attempt_count=exp_rec.get("_attempt_count"),
            meeting_count=exp_rec.get("_meeting_count"),
            started_at=ef.get("Started At"),
            ended_at=ef.get("Ended At"),
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

    human_confirm = results_map.get("human_confirm")
    if human_confirm:
        resp.human_confirmation = human_confirm

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
    # Coaches can only see runs belonging to their assigned coachees.
    fields = run_record.get("fields", {})
    coachee_id = fields.get("Coachee ID")
    if user.role == "coachee":
        if coachee_id != user.airtable_user_record_id:
            return error_response("FORBIDDEN", "You do not have access to this run.", 403)
    elif user.role == "coach":
        from .auth import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM users_auth WHERE airtable_user_record_id = %s AND coach_id = %s LIMIT 1",
                    (coachee_id, user.id),
                )
                if not cur.fetchone():
                    return error_response("FORBIDDEN", "You do not have access to this run.", 403)

    return await _build_run_response(run_record, at_client)


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
    progress_message = fields.get("Progress Message")

    error_detail = None
    if error_msg:
        error_detail = {"code": "JOB_FAILED", "message": error_msg}

    return RunRequestStatusResponse(
        run_request_id=rr_id,
        status=status,
        run_id=run_id,
        error=error_detail,
        progress_message=progress_message,
    )
