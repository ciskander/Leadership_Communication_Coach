"""
api/routes_coachee.py — Endpoints for coachee / client users.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from .dependencies import get_current_user
from .dto import (
    ActiveExperimentResponse,
    BaselinePackBuildResponse,
    BaselinePackCreateResponse,
    ClientSummaryResponse,
    CoacheeListItem,
    ExperimentActionResponse,
    ExperimentOptionsResponse,
    ExperimentResponse,
    RankedExperimentItem,
    ClientProgressResponse,
    HumanConfirmResponse,
    MeResponse,
    SingleMeetingEnqueueResponse,
)
from .errors import error_response, invalid_input
from .quote_helpers import (
    apply_quote_cleanup,
    build_spans_lookup,
    build_turn_map,
    resolve_coaching_output,
    resolve_pattern_snapshot,
)
from ..queue.tasks import enqueue_single_meeting, enqueue_baseline_pack_build, enqueue_next_experiment_suggestion

logger = logging.getLogger(__name__)

router = APIRouter()


def _is_airtable_not_found(exc: Exception) -> bool:
    """Return True if the exception represents an Airtable 404 (record not found)."""
    from requests.exceptions import HTTPError
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code == 404
    return False


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateBaselinePackBody(BaseModel):
    transcript_ids: list[str]
    target_speaker_name: str
    target_speaker_label: str
    target_role: str
    coachee_auth_id: Optional[str] = None  # Set by coach when creating on behalf of coachee


class SingleMeetingBody(BaseModel):
    transcript_id: str
    target_speaker_name: str
    target_speaker_label: str
    target_role: str
    analysis_type: str = "single_meeting"


class HumanConfirmBody(BaseModel):
    confirmed: bool
    run_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_experiment_response(exp_rec: dict, at_client: Optional[AirtableClient] = None) -> ExperimentResponse:
    ef = exp_rec.get("fields", {})
    attempt_count = None
    meeting_count = None
    if at_client is not None:
        try:
            attempt_count, meeting_count = at_client.count_experiment_attempts_and_meetings(exp_rec["id"])
        except Exception:
            logger.warning("Could not count attempts/meetings for experiment %s", exp_rec["id"])
    return ExperimentResponse(
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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/baseline_packs", response_model=BaselinePackCreateResponse)
async def create_baseline_pack(
    body: CreateBaselinePackBody,
    user: UserAuth = Depends(get_current_user),
):
    if len(body.transcript_ids) != 3:
        return invalid_input("Exactly 3 transcript IDs are required for a baseline pack.")

    at_client = AirtableClient()

    airtable_user_id = user.airtable_user_record_id
    if body.coachee_auth_id:
        from .auth import get_user_by_id
        coachee = get_user_by_id(body.coachee_auth_id)
        if coachee and coachee.airtable_user_record_id:
            airtable_user_id = coachee.airtable_user_record_id

    bp_record = at_client.create_record("baseline_packs", {
        "Target Role": body.target_role,
        "Target Speaker Name": body.target_speaker_name,
        "Speaker Label": body.target_speaker_label,
        "Status": "draft",
        "users": [airtable_user_id] if airtable_user_id else [],
    })
    bp_record_id = bp_record["id"]

    for t_id in body.transcript_ids:
        at_client.create_record("baseline_pack_items", {
            "Baseline Pack": [bp_record_id],
            "Transcript": [t_id],
            "Status": "pending",
        })

    return BaselinePackCreateResponse(
        baseline_pack_id=bp_record_id,
        status="draft",
    )


@router.post("/api/baseline_packs/{bp_id}/build", response_model=BaselinePackBuildResponse)
async def build_baseline_pack(
    bp_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        bp_rec = at_client.get_baseline_pack(bp_id)
    except Exception as exc:
        if _is_airtable_not_found(exc):
            return error_response("NOT_FOUND", "Baseline pack not found.", 404)
        logger.exception("build_baseline_pack: failed to fetch pack %s", bp_id)
        return error_response("INTERNAL_ERROR", "Failed to load baseline pack. Please try again.", 500)

    # Ownership check: coachees can only build their own packs.
    if user.role == "coachee":
        bp_user_links = bp_rec.get("fields", {}).get("users", [])
        if not isinstance(bp_user_links, list) or user.airtable_user_record_id not in bp_user_links:
            return error_response("FORBIDDEN", "You do not have access to this baseline pack.", 403)

    job = enqueue_baseline_pack_build.delay(bp_id)
    return BaselinePackBuildResponse(
        baseline_pack_id=bp_id,
        job_id=job.id,
        status="queued",
    )


@router.get("/api/baseline_packs/{bp_id}")
async def get_baseline_pack(
    bp_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        bp_rec = at_client.get_baseline_pack(bp_id)
    except Exception as exc:
        if _is_airtable_not_found(exc):
            return error_response("NOT_FOUND", "Baseline pack not found.", 404)
        logger.exception("get_baseline_pack: failed to fetch pack %s", bp_id)
        return error_response("INTERNAL_ERROR", "Failed to load baseline pack. Please try again.", 500)

    # Ownership check: coachees can only view their own packs.
    if user.role == "coachee":
        bp_user_links = bp_rec.get("fields", {}).get("users", [])
        if not isinstance(bp_user_links, list) or user.airtable_user_record_id not in bp_user_links:
            return error_response("FORBIDDEN", "You do not have access to this baseline pack.", 403)

    bf = bp_rec.get("fields", {})

    strengths, focus, micro_experiment, pattern_snapshot = [], None, None, []
    last_run_links = bf.get("Last Run", [])
    if last_run_links:
        try:
            run_rec = at_client.get_run(last_run_links[0])
            parsed_json_str = run_rec.get("fields", {}).get("Parsed JSON") or "{}"
            parsed = json.loads(parsed_json_str)

            # Baseline aggregate runs receive only slim meeting summaries —
            # NOT raw transcripts — so evidence_spans contain no real quotes.
            # Extract coaching text fields only; quotes come from sub-runs.
            coaching = parsed.get("coaching_output", {})
            strengths = [
                {"pattern_id": s.get("pattern_id", ""), "message": s.get("message", ""), "quotes": []}
                for s in coaching.get("strengths", [])
            ]
            focus_list = coaching.get("focus", [])
            if focus_list:
                f = focus_list[0]
                focus = {
                    "pattern_id": f.get("pattern_id", ""),
                    "message": f.get("message", ""),
                    "quotes": [],
                    "suggested_rewrite": f.get("suggested_rewrite"),
                    "rewrite_for_span_id": None,
                    "additional_quotes": [],
                }
            micro_list = coaching.get("micro_experiment", [])
            if micro_list:
                m = micro_list[0]
                micro_experiment = {
                    "experiment_id": m.get("experiment_id", ""),
                    "title": m.get("title", ""),
                    "instruction": m.get("instruction", ""),
                    "success_marker": m.get("success_marker", ""),
                    "pattern_id": m.get("pattern_id", ""),
                    "quotes": [],
                }
            # Pattern snapshot: extract text fields only, no quote resolution
            raw_snapshot = parsed.get("pattern_snapshot") or []
            pattern_snapshot = [
                {
                    "pattern_id": ps.get("pattern_id", ""),
                    "tier": ps.get("tier"),
                    "evaluable_status": ps.get("evaluable_status", "not_evaluable"),
                    "numerator": ps.get("numerator"),
                    "denominator": ps.get("denominator"),
                    "ratio": ps.get("ratio"),
                    "balance_assessment": ps.get("balance_assessment"),
                    "notes": ps.get("notes"),
                    "quotes": [],
                    "coaching_note": ps.get("coaching_note"),
                    "suggested_rewrite": ps.get("suggested_rewrite"),
                    "rewrite_for_span_id": ps.get("rewrite_for_span_id"),
                }
                for ps in raw_snapshot
            ]
        except Exception:
            pass

    # Fetch constituent meetings from baseline pack items
    meetings = []
    try:
        bpi_records = at_client.get_baseline_pack_items(bp_id)
        for bpi in bpi_records:
            bpif = bpi.get("fields", {})
            run_links = bpif.get("Run", [])
            transcript_links = bpif.get("Transcript", [])
            meeting_info: dict = {
                "run_id": run_links[0] if run_links else None,
                "title": None,
                "meeting_date": None,
                "meeting_type": None,
                "target_role": None,
                "sub_run_strengths": [],
                "sub_run_focus": None,
                "sub_run_pattern_snapshot": [],
            }
            if transcript_links:
                try:
                    tr_rec = at_client.get_transcript(transcript_links[0])
                    trf = tr_rec.get("fields", {})
                    meeting_info.update({
                        "title": trf.get("Title"),
                        "meeting_date": trf.get("Meeting Date"),
                        "meeting_type": trf.get("Meeting Type"),
                        "target_role": trf.get("Target Role"),
                    })
                except Exception as te:
                    logger.warning("get_baseline_pack: could not fetch transcript %s: %s", transcript_links[0] if transcript_links else "?", te)
            if run_links:
                try:
                    sub_run_rec = at_client.get_run(run_links[0])
                    sub_fields = sub_run_rec.get("fields", {})
                    sub_parsed_str = sub_fields.get("Parsed JSON") or "{}"
                    sub_parsed = json.loads(sub_parsed_str)

                    # Resolve sub-run evidence spans with transcript turn map
                    sub_spans = build_spans_lookup(sub_parsed)
                    sub_transcript_links = sub_fields.get("Transcript ID", [])
                    sub_transcript_id = sub_transcript_links[0] if isinstance(sub_transcript_links, list) and sub_transcript_links else None
                    sub_meeting_id = sub_parsed.get("context", {}).get("meeting_id")
                    meeting_info["meeting_id"] = sub_meeting_id
                    sub_turn_map = build_turn_map(at_client, sub_transcript_id)

                    sub_target_label = sub_parsed.get("context", {}).get("target_speaker_label")
                    sub_strengths, sub_focus, _ = resolve_coaching_output(
                        sub_parsed, sub_spans, sub_transcript_id, sub_meeting_id, sub_turn_map, sub_target_label
                    )
                    sub_pattern_snapshot = resolve_pattern_snapshot(
                        sub_parsed, sub_spans, sub_transcript_id, sub_meeting_id, sub_turn_map, sub_target_label
                    )

                    # Post-processing: clean up ASR artifacts in quote texts
                    apply_quote_cleanup(
                        sub_strengths, sub_focus, None, sub_pattern_snapshot
                    )

                    meeting_info["sub_run_strengths"] = [s.model_dump() for s in sub_strengths]
                    meeting_info["sub_run_focus"] = sub_focus.model_dump() if sub_focus else None
                    meeting_info["sub_run_pattern_snapshot"] = [p.model_dump() for p in sub_pattern_snapshot]
                except Exception as se:
                    logger.warning("get_baseline_pack: could not fetch sub-run %s: %s", run_links[0], se)
            meetings.append(meeting_info)
    except Exception as e:
        logger.warning("get_baseline_pack: could not fetch pack items for %s: %s", bp_id, e)

    # Annotate aggregate quotes with meeting labels for attribution
    mid_to_label: dict[str, str] = {}
    for m in meetings:
        mid = m.get("meeting_id")
        if mid:
            label = m.get("title") or m.get("meeting_date") or mid
            mid_to_label[mid] = label

    def _annotate_quotes(data: object) -> None:
        """Walk dicts/lists and set meeting_label on any quote with a matching meeting_id."""
        if isinstance(data, dict):
            if "quote_text" in data and data.get("meeting_id"):
                data["meeting_label"] = mid_to_label.get(data["meeting_id"])
            for v in data.values():
                _annotate_quotes(v)
        elif isinstance(data, list):
            for item in data:
                _annotate_quotes(item)

    _annotate_quotes(strengths)
    _annotate_quotes(focus)
    _annotate_quotes(pattern_snapshot)

    return {
        "baseline_pack_id": bp_rec["id"],
        "status": bf.get("Status"),
        "target_role": bf.get("Target Role"),
        "target_speaker_label": bf.get("Speaker Label"),
        "role_consistency": bf.get("Role Consistency"),
        "meeting_type_consistency": bf.get("Meeting Type Consistency"),
        "strengths": strengths,
        "focus": focus,
        "micro_experiment": micro_experiment,
        "pattern_snapshot": pattern_snapshot,
        "created_at": bp_rec.get("createdTime"),
        "meetings": meetings,
    }


@router.post("/api/analyses/single_meeting", response_model=SingleMeetingEnqueueResponse)
async def enqueue_analysis(
    body: SingleMeetingBody,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()

    rr_fields: dict = {
        "Analysis Type": body.analysis_type,
        "Transcript": [body.transcript_id],
        "Target Speaker Name": body.target_speaker_name,
        "Target Speaker Label": body.target_speaker_label,
        "Target Role": body.target_role,
        "Status": "queued",
    }
    if user.airtable_user_record_id:
        rr_fields["User"] = [user.airtable_user_record_id]

    # Attach active experiment if present
    try:
        user_rec = at_client.get_user(user.airtable_user_record_id or "")
        ae_links = user_rec.get("fields", {}).get("Active Experiment", [])
        if ae_links:
            rr_fields["Active Experiment"] = ae_links
    except Exception as e:
        logger.warning("Could not attach active experiment to run_request: %s", e)

    rr_record = at_client.create_record("run_requests", rr_fields)
    rr_id = rr_record["id"]

    job = enqueue_single_meeting.delay(rr_id)
    return SingleMeetingEnqueueResponse(
        run_request_id=rr_id,
        job_id=job.id,
        status="queued",
    )


@router.post("/api/coachees/me/analyze", response_model=SingleMeetingEnqueueResponse)
async def enqueue_analysis_alias(
    body: SingleMeetingBody,
    user: UserAuth = Depends(get_current_user),
):
    return await enqueue_analysis(body, user)


# ── Experiment lifecycle endpoints ────────────────────────────────────────────

@router.get("/api/client/experiments/proposed", response_model=list[ExperimentResponse])
async def get_proposed_experiments(
    user: UserAuth = Depends(get_current_user),
):
    """Return proposed experiments for the current user, most recent first (max 3)."""
    if not user.airtable_user_record_id:
        return []
    at_client = AirtableClient()
    try:
        records = at_client.get_proposed_experiments_for_user(user.airtable_user_record_id)
        return [_build_experiment_response(r) for r in records]
    except Exception as e:
        logger.warning("Error fetching proposed experiments: %s", e)
        return []


@router.post(
    "/api/client/experiments/{experiment_record_id}/accept",
    response_model=ExperimentActionResponse,
)
async def accept_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Accept a proposed experiment. Sets it to active if no active experiment exists."""
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    # Verify experiment exists and belongs to this user
    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    user_links = ef.get("User", [])
    if user.airtable_user_record_id not in user_links:
        return error_response("FORBIDDEN", "Experiment does not belong to this user.", 403)

    if ef.get("Status") != "proposed":
        return error_response("INVALID_STATE", f"Experiment is not in proposed state (current: {ef.get('Status')}).", 400)

    # Check for existing active experiment
    user_rec = at_client.get_user(user.airtable_user_record_id)
    existing_active = user_rec.get("fields", {}).get("Active Experiment", [])
    if existing_active:
        return error_response("CONFLICT", "You already have an active experiment. Complete or abandon it before accepting a new one.", 409)

    # Activate
    at_client.accept_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s accepted experiment %s", user.airtable_user_record_id, experiment_record_id)

    # Clean up other proposed experiments (user chose this one)
    try:
        remaining_proposed = at_client.get_proposed_experiments_for_user(user.airtable_user_record_id)
        for p in remaining_proposed:
            if p["id"] != experiment_record_id:
                at_client.delete_experiment(p["id"])
                logger.info("Cleaned up proposed experiment %s after accept", p["id"])
    except Exception as e:
        logger.warning("Could not clean up proposed experiments after accept: %s", e)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="active",
        message="Experiment is now active. Good luck!",
    )


@router.post(
    "/api/client/experiments/{experiment_record_id}/complete",
    response_model=ExperimentActionResponse,
)
async def complete_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Mark an active experiment as complete."""
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    user_links = ef.get("User", [])
    if user.airtable_user_record_id not in user_links:
        return error_response("FORBIDDEN", "Experiment does not belong to this user.", 403)

    if ef.get("Status") != "active":
        return error_response("INVALID_STATE", f"Experiment is not active (current: {ef.get('Status')}).", 400)

    at_client.complete_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s completed experiment %s", user.airtable_user_record_id, experiment_record_id)

    # Fire-and-forget: generate next experiment suggestion in the background
    if user.airtable_user_record_id:
        try:
            enqueue_next_experiment_suggestion.delay(user.airtable_user_record_id)
            logger.info("Enqueued next experiment suggestion for user %s", user.airtable_user_record_id)
        except Exception as e:
            logger.error("Failed to enqueue next experiment suggestion for user %s: %s", user.airtable_user_record_id, e)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="completed",
        message="Great work completing the experiment. Choose your next one when you\u2019re ready.",
    )


@router.post(
    "/api/client/experiments/{experiment_record_id}/park",
    response_model=ExperimentActionResponse,
)
async def park_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Park an active experiment for later. Counts toward the 3-parked cap."""
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    user_links = ef.get("User", [])
    if user.airtable_user_record_id not in user_links:
        return error_response("FORBIDDEN", "Experiment does not belong to this user.", 403)

    if ef.get("Status") not in ("active", "proposed"):
        return error_response("INVALID_STATE", f"Experiment cannot be parked from state: {ef.get('Status')}.", 400)

    # Check parked cap (max 3)
    parked = at_client.get_parked_experiments_for_user(user.airtable_user_record_id)
    if len(parked) >= 3:
        return error_response(
            "PARK_CAP_REACHED",
            "You already have 3 parked experiments. Resume or discard one before parking another.",
            400,
        )

    at_client.park_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s parked experiment %s", user.airtable_user_record_id, experiment_record_id)

    # Fire-and-forget: generate next experiment suggestions in the background
    if user.airtable_user_record_id:
        try:
            enqueue_next_experiment_suggestion.delay(user.airtable_user_record_id)
            logger.info("Enqueued next experiment suggestion for user %s", user.airtable_user_record_id)
        except Exception as e:
            logger.error("Failed to enqueue next experiment suggestion for user %s: %s", user.airtable_user_record_id, e)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="parked",
        message="Experiment parked. You can resume it anytime.",
    )


# Keep old endpoint as alias for backwards compatibility
@router.post(
    "/api/client/experiments/{experiment_record_id}/abandon",
    response_model=ExperimentActionResponse,
)
async def abandon_experiment_legacy(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Legacy alias — redirects to park."""
    return await park_experiment(experiment_record_id, user)


@router.post(
    "/api/client/experiments/{experiment_record_id}/resume",
    response_model=ExperimentActionResponse,
)
async def resume_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Resume a parked experiment."""
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    user_links = ef.get("User", [])
    if user.airtable_user_record_id not in user_links:
        return error_response("FORBIDDEN", "Experiment does not belong to this user.", 403)

    if ef.get("Status") != "parked":
        return error_response("INVALID_STATE", f"Only parked experiments can be resumed (current: {ef.get('Status')}).", 400)

    # Must not have an active experiment already
    user_rec = at_client.get_user(user.airtable_user_record_id)
    existing_active = user_rec.get("fields", {}).get("Active Experiment", [])
    if existing_active:
        return error_response("CONFLICT", "You already have an active experiment. Complete or park it first.", 409)

    at_client.resume_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s resumed experiment %s", user.airtable_user_record_id, experiment_record_id)

    # Clean up any pending proposed experiments since user chose to resume
    try:
        proposed = at_client.get_proposed_experiments_for_user(user.airtable_user_record_id)
        for p in proposed:
            at_client.delete_experiment(p["id"])
            logger.info("Cleaned up proposed experiment %s after resume", p["id"])
    except Exception as e:
        logger.warning("Could not clean up proposed experiments after resume: %s", e)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="active",
        message="Experiment resumed. Welcome back!",
    )


@router.post(
    "/api/client/experiments/{experiment_record_id}/discard",
    response_model=ExperimentActionResponse,
)
async def discard_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Permanently abandon a parked experiment, freeing a slot."""
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    user_links = ef.get("User", [])
    if user.airtable_user_record_id not in user_links:
        return error_response("FORBIDDEN", "Experiment does not belong to this user.", 403)

    if ef.get("Status") != "parked":
        return error_response("INVALID_STATE", f"Only parked experiments can be discarded (current: {ef.get('Status')}).", 400)

    at_client.abandon_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s discarded (abandoned) parked experiment %s", user.airtable_user_record_id, experiment_record_id)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="abandoned",
        message="Experiment discarded.",
    )


@router.get(
    "/api/client/experiments/options",
    response_model=ExperimentOptionsResponse,
)
async def get_experiment_options(
    user: UserAuth = Depends(get_current_user),
):
    """Return all proposed and parked experiments for the selection screen.

    Also returns a ``ranked`` list that merges proposed + parked into a
    single ordered list (up to 3 items), sorted by pattern weakness score
    (lowest average ratio first) so the frontend can show one unified set
    of options.
    """
    if not user.airtable_user_record_id:
        return ExperimentOptionsResponse()

    at_client = AirtableClient()

    proposed_records = at_client.get_proposed_experiments_for_user(
        user.airtable_user_record_id, max_records=3
    )
    proposed = [_build_experiment_response(r) for r in proposed_records]

    parked_records = at_client.get_parked_experiments_for_user(user.airtable_user_record_id)
    parked = [_build_experiment_response(r, at_client) for r in parked_records]

    # ── Build ranked merge ────────────────────────────────────────────────
    # Compute average pattern scores from recent runs to rank experiments.
    pattern_avg: dict[str, float] = {}
    try:
        runs_formula = (
            f"AND("
            f"{{Coachee ID}} = '{user.airtable_user_record_id}', "
            f"{{Gate1 Pass}} = TRUE()"
            f")"
        )
        run_records = at_client.search_records("runs", runs_formula, max_records=5)
        pattern_scores: dict[str, list[float]] = {}
        for r in run_records:
            rf = r.get("fields", {})
            # Skip baseline sub-runs
            if rf.get("Analysis Type") == "single_meeting" and rf.get("Baseline Pack"):
                continue
            parsed_str = rf.get("Parsed JSON") or "{}"
            try:
                parsed = json.loads(parsed_str)
                for p in parsed.get("pattern_snapshot", []):
                    pid = p.get("pattern_id")
                    ratio = p.get("ratio")
                    if pid and p.get("evaluable_status") == "evaluable" and ratio is not None:
                        pattern_scores.setdefault(pid, []).append(float(ratio))
            except Exception:
                pass
        pattern_avg = {
            pid: sum(vals) / len(vals)
            for pid, vals in pattern_scores.items()
        }
    except Exception:
        logger.warning("get_experiment_options: could not compute pattern scores for ranking")

    # Merge proposed + parked, tag with origin, sort by pattern weakness
    tagged: list[tuple[str, ExperimentResponse]] = []
    for exp in proposed:
        tagged.append(("proposed", exp))
    for exp in parked:
        tagged.append(("parked", exp))

    def _sort_key(item: tuple[str, ExperimentResponse]) -> float:
        # Lower score = weaker pattern = higher priority.
        # Patterns not in the map get score 0 (highest priority / unknown).
        return pattern_avg.get(item[1].pattern_id, 0.0)

    tagged.sort(key=_sort_key)

    ranked = [
        RankedExperimentItem(experiment=exp, origin=origin, rank=i + 1)
        for i, (origin, exp) in enumerate(tagged[:3])
    ]

    # If fewer than 3 options and no active experiment, generate more synchronously.
    # This covers existing users who only got 1 experiment from their baseline pack.
    if len(ranked) < 3 and not at_client.get_active_experiment_for_user(user.airtable_user_record_id):
        try:
            from ..core.workers import process_next_experiment_suggestion
            process_next_experiment_suggestion(user.airtable_user_record_id, client=at_client)
            logger.info("get_experiment_options: backfill generation completed for user %s",
                        user.airtable_user_record_id)

            # Re-query to include the newly created experiments
            proposed_records = at_client.get_proposed_experiments_for_user(
                user.airtable_user_record_id, max_records=3
            )
            proposed = [_build_experiment_response(r) for r in proposed_records]

            tagged = [("proposed", exp) for exp in proposed] + [("parked", exp) for exp in parked]
            tagged.sort(key=_sort_key)
            ranked = [
                RankedExperimentItem(experiment=exp, origin=origin, rank=i + 1)
                for i, (origin, exp) in enumerate(tagged[:3])
            ]
        except Exception:
            logger.warning("get_experiment_options: backfill failed for user %s",
                           user.airtable_user_record_id, exc_info=True)

    return ExperimentOptionsResponse(
        proposed=proposed,
        parked=parked,
        ranked=ranked,
        at_park_cap=len(parked) >= 3,
    )


@router.post(
    "/api/client/experiments/{experiment_record_id}/confirm_attempt",
    response_model=HumanConfirmResponse,
)
async def confirm_experiment_attempt(
    experiment_record_id: str,
    body: HumanConfirmBody,
    user: UserAuth = Depends(get_current_user),
):
    """
    Human override for experiment detection.
    When confirmed=True, creates an experiment_event with human_confirmed=True.
    When confirmed=False, records that the coachee did not attempt it.
    """
    if not user.airtable_user_record_id:
        return error_response("FORBIDDEN", "No Airtable user record.", 403)

    at_client = AirtableClient()

    try:
        exp_rec = at_client.get_experiment(experiment_record_id)
    except Exception:
        return error_response("NOT_FOUND", "Experiment not found.", 404)

    ef = exp_rec.get("fields", {})
    if ef.get("Status") != "active":
        return error_response("INVALID_STATE", "Can only confirm attempts on active experiments.", 400)

    exp_id = ef.get("Experiment ID", "")

    # Get meeting date from the run
    meeting_date = None
    try:
        run_rec = at_client.get_run(body.run_id)
        transcript_links = run_rec.get("fields", {}).get("Transcript ID", [])
        if transcript_links:
            tr_rec = at_client.get_transcript(transcript_links[0])
            meeting_date = tr_rec.get("fields", {}).get("Meeting Date")
    except Exception as e:
        logger.warning("Could not get meeting date for confirm_attempt: %s", e)

    # Build idempotency key — human confirmation variant
    idem_key = f"human:{body.run_id}:{exp_id}"
    existing = at_client.find_experiment_event_by_idempotency_key(idem_key)
    if existing:
        return HumanConfirmResponse(
            event_record_id=existing["id"],
            experiment_record_id=experiment_record_id,
            confirmed=body.confirmed,
        )

    attempt_value = "yes" if body.confirmed else "no"
    user_confirmation_value = "confirmed_attempt" if body.confirmed else "confirmed_no_attempt"

    fields: dict = {
        "Experiment": [experiment_record_id],
        "Run": [body.run_id],
        "Attempt Enum": attempt_value,
        "User Confirmation": user_confirmation_value,
        "Idempotency Key": idem_key,
    }
    if user.airtable_user_record_id:
        fields["User"] = [user.airtable_user_record_id]
    if meeting_date:
        fields["Meeting Date"] = meeting_date

    event_rec = at_client.create_experiment_event(fields)

    if body.confirmed:
        try:
            at_client.update_experiment_attempt_fields(
                experiment_record_id,
                attempt=attempt_value,
                attempt_date=meeting_date,
            )
        except Exception as e:
            logger.warning("Could not update experiment attempt fields on confirm: %s", e)

    logger.info(
        "Human confirmation for experiment %s run %s: confirmed=%s",
        experiment_record_id, body.run_id, body.confirmed,
    )

    return HumanConfirmResponse(
        event_record_id=event_rec["id"],
        experiment_record_id=experiment_record_id,
        confirmed=body.confirmed,
    )


# ── Client dashboard ──────────────────────────────────────────────────────────

@router.get("/api/client/summary", response_model=ClientSummaryResponse)
async def client_summary(
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()

    active_exp_resp: Optional[ExperimentResponse] = None
    proposed_exps: list[ExperimentResponse] = []
    parked_count: int = 0
    bp_status: Optional[str] = None
    bp_id: Optional[str] = None
    recent_runs: list[dict] = []

    if user.airtable_user_record_id:
        try:
            # ── Phase 1: fetch user record (needed to determine what else to fetch)
            user_rec = await asyncio.to_thread(
                at_client.get_user, user.airtable_user_record_id
            )
            u_fields = user_rec.get("fields", {})
            user_primary_id = u_fields.get("User ID", "")

            # ── Phase 2: launch independent fetches in parallel ───────────
            ae_links = u_fields.get("Active Experiment", [])
            bp_links = u_fields.get("Active Baseline Pack", [])

            futures = []
            future_keys = []

            # Active experiment detail
            if ae_links:
                futures.append(asyncio.to_thread(at_client.get_experiment, ae_links[0]))
                future_keys.append("active_exp")

            # Proposed experiments — pass user_primary_id to skip redundant user fetch
            futures.append(asyncio.to_thread(
                at_client.get_proposed_experiments_for_user,
                user.airtable_user_record_id, 3, user_primary_id,
            ))
            future_keys.append("proposed")

            # Parked experiments — pass user_primary_id to skip redundant user fetch
            futures.append(asyncio.to_thread(
                at_client.get_parked_experiments_for_user,
                user.airtable_user_record_id, user_primary_id,
            ))
            future_keys.append("parked")

            # Baseline pack status
            if bp_links:
                bp_id = bp_links[0]
                futures.append(asyncio.to_thread(at_client.get_baseline_pack, bp_links[0]))
                future_keys.append("baseline_pack")

            # Recent runs
            runs_formula = f"{{Coachee ID}} = '{user.airtable_user_record_id}'"
            futures.append(asyncio.to_thread(
                at_client.search_records, "runs", runs_formula, None, 10,
            ))
            future_keys.append("runs")

            results = await asyncio.gather(*futures, return_exceptions=True)
            results_map: dict = {}
            for key, result in zip(future_keys, results):
                if isinstance(result, Exception):
                    logger.warning("client_summary parallel fetch %s failed: %s", key, result)
                    results_map[key] = None
                else:
                    results_map[key] = result

            # ── Process results ───────────────────────────────────────────
            # Active experiment
            active_exp_rec = results_map.get("active_exp")
            if active_exp_rec:
                active_exp_resp = _build_experiment_response(active_exp_rec, at_client)

            # Proposed experiments
            proposed_records = results_map.get("proposed") or []
            proposed_exps = [_build_experiment_response(r) for r in proposed_records]

            # Parked experiments
            parked_records = results_map.get("parked") or []
            parked_count = len(parked_records)

            # Baseline pack
            bp_rec = results_map.get("baseline_pack")
            if bp_rec:
                bp_status = bp_rec.get("fields", {}).get("Status")

            # ── Recent runs — transcript metadata from lookup fields ─────
            run_records = results_map.get("runs") or []

            def _first(val: object) -> object:
                """Extract scalar from Airtable lookup field (single-element array)."""
                return val[0] if isinstance(val, list) and val else val if not isinstance(val, list) else None

            for r in run_records:
                rf = r.get("fields", {})
                if rf.get("baseline_pack_items"):
                    continue

                run_entry: dict = {
                    "run_id": r["id"],
                    "analysis_type": rf.get("Analysis Type"),
                    "gate1_pass": rf.get("Gate1 Pass"),
                    "focus_pattern": rf.get("Focus Pattern"),
                    "created_at": r.get("createdTime"),
                    "title": _first(rf.get("Title (from Transcript ID)")),
                    "transcript_id": _first(rf.get("Transcript ID (from Transcript)")),
                    "meeting_date": _first(rf.get("Meeting Date (from Transcript ID)")),
                    "meeting_type": _first(rf.get("Meeting Type (from Transcript ID)")),
                    "target_role": rf.get("Target Speaker Role"),
                }
                if rf.get("Analysis Type") == "baseline_pack":
                    bp_run_links = rf.get("baseline_packs (Last Run)", [])
                    run_entry["baseline_pack_id"] = bp_run_links[0] if bp_run_links else None
                recent_runs.append(run_entry)

            # Sort newest meeting date first; runs with no date go to the end
            recent_runs.sort(
                key=lambda x: (x.get("meeting_date") is None, x.get("meeting_date") or ""),
                reverse=True,
            )

        except Exception as e:
            logger.warning("Error building client summary: %s", e)

    return ClientSummaryResponse(
        user=MeResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            coach_id=user.coach_id,
            airtable_user_record_id=user.airtable_user_record_id,
            last_login=user.last_login,
        ),
        active_experiment=active_exp_resp,
        proposed_experiments=proposed_exps,
        parked_experiment_count=parked_count,
        baseline_pack_status=bp_status,
        baseline_pack_id=bp_id,
        recent_runs=recent_runs,
    )


@router.get("/api/client/active_experiment", response_model=ActiveExperimentResponse)
async def active_experiment(
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    if not user.airtable_user_record_id:
        return ActiveExperimentResponse(experiment=None)

    try:
        user_rec = at_client.get_user(user.airtable_user_record_id)
        ae_links = user_rec.get("fields", {}).get("Active Experiment", [])
        if not ae_links:
            return ActiveExperimentResponse(experiment=None)

        exp_rec = at_client.get_experiment(ae_links[0])
        exp_resp = _build_experiment_response(exp_rec, at_client)

        # Recent events
        exp_primary_id = exp_rec.get("fields", {}).get("Experiment ID", "")
        events_formula = f"FIND('{exp_primary_id}', ARRAYJOIN({{Experiment}}))"
        event_records = at_client.search_records("experiment_events", events_formula, max_records=10)
        events_out = []
        for er in event_records:
            erf = er.get("fields", {})
            events_out.append({
                "event_id": er["id"],
                "attempt": erf.get("Attempt Enum"),
                "meeting_date": erf.get("Meeting Date"),
                "human_confirmed": erf.get("User Confirmation"),
                "notes": erf.get("Notes"),
            })

        return ActiveExperimentResponse(experiment=exp_resp, recent_events=events_out)

    except Exception:
        return ActiveExperimentResponse(experiment=None)

@router.get("/api/client/progress", response_model=ClientProgressResponse)
async def client_progress(
    user: UserAuth = Depends(get_current_user),
):
    """
    Return pattern history (for the trend chart) and past experiments
    (completed or abandoned) for the authenticated coachee.
    """
    at_client = AirtableClient()

    pattern_history = []
    past_experiments = []

    if not user.airtable_user_record_id:
        return ClientProgressResponse(pattern_history=[], past_experiments=[])

    # ── Fetch eligible runs ───────────────────────────────────────────────────
    runs_formula = (
        f"AND({{Coachee ID}} = '{user.airtable_user_record_id}', {{Gate1 Pass}} = TRUE())"
    )
    try:
        run_records = at_client.search_records("runs", runs_formula, max_records=60)
    except Exception as e:
        logger.warning("client_progress: error fetching runs: %s", e)
        run_records = []

    for run_rec in run_records:
        rf = run_rec.get("fields", {})
        analysis_type = rf.get("Analysis Type", "")

        # Skip baseline sub-runs — baseline_pack_items is a reverse-link field
        # set on any run belonging to a baseline pack item, regardless of whether
        # baseline_pack was set at run creation time (pre-existing runs won't have it).
        if rf.get("baseline_pack_items"):
            continue

        is_baseline = analysis_type == "baseline_pack"

        # Get meeting date from the linked transcript
        meeting_date: Optional[str] = None
        transcript_links = rf.get("Transcript ID", [])
        if transcript_links:
            try:
                tr_rec = at_client.get_transcript(transcript_links[0])
                meeting_date = tr_rec.get("fields", {}).get("Meeting Date")
            except Exception as e:
                logger.warning("client_progress: could not fetch transcript %s: %s", transcript_links[0], e)

        # Parse pattern_snapshot from Parsed JSON
        patterns = []
        parsed_json_str = rf.get("Parsed JSON") or "{}"
        try:
            parsed = json.loads(parsed_json_str)
            snapshot = parsed.get("pattern_snapshot", [])
            for p in snapshot:
                pid = p.get("pattern_id", "")
                if not pid:
                    continue
                ratio_val = p.get("ratio")
                if ratio_val is None:
                    continue  # non-evaluable pattern — skip
                # opportunity_count is optional; fall back to denominator
                opp = p.get("opportunity_count") or p.get("denominator") or 0
                patterns.append({
                    "pattern_id": pid,
                    "ratio": float(ratio_val),
                    "opportunity_count": int(opp) if opp else 0,
                })
        except Exception as e:
            logger.warning("client_progress: could not parse run %s JSON: %s", run_rec["id"], e)

        if not patterns:
            continue

        pattern_history.append({
            "run_id": run_rec["id"],
            "meeting_date": meeting_date,
            "is_baseline": is_baseline,
            "analysis_type": analysis_type,
            "patterns": patterns,
        })

    # Sort chronologically (runs with no date go last)
    pattern_history.sort(
        key=lambda x: (x["meeting_date"] is None, x["meeting_date"] or "")
    )

    # ── Fetch past experiments ────────────────────────────────────────────────
    user_primary_id = ""
    try:
        user_rec = at_client.get_user(user.airtable_user_record_id)
        user_primary_id = user_rec.get("fields", {}).get("User ID", "")
    except Exception as e:
        logger.warning("client_progress: could not fetch user primary ID: %s", e)

    exp_formula = (
        f"AND("
        f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
        f"OR({{Status}} = 'completed', {{Status}} = 'abandoned', {{Status}} = 'parked')"
        f")"
    )
    try:
        exp_records = at_client.search_records("experiments", exp_formula, max_records=30)
    except Exception as e:
        logger.warning("client_progress: error fetching past experiments: %s", e)
        exp_records = []

    for exp_rec in exp_records:
        ef = exp_rec.get("fields", {})
        attempt_count, meeting_count = at_client.count_experiment_attempts_and_meetings(exp_rec["id"])
        past_experiments.append({
            "experiment_record_id": exp_rec["id"],
            "experiment_id": ef.get("Experiment ID", ""),
            "title": ef.get("Title", ""),
            "pattern_id": ef.get("Pattern ID", ""),
            "status": ef.get("Status", ""),
            "started_at": ef.get("Started At"),
            "ended_at": ef.get("Ended At"),
            "attempt_count": attempt_count,
            "meeting_count": meeting_count,
        })

    # Most recent first (by ended_at)
    past_experiments.sort(key=lambda x: (x["ended_at"] or ""), reverse=True)

    # ── Read trend window size from config ─────────────────────────────────
    from ..core.airtable_client import F_CFG_TREND_WINDOW_SIZE
    trend_window_size = 3  # default
    try:
        active_cfg = at_client.get_active_config()
        if active_cfg:
            cfg_val = active_cfg.get("fields", {}).get(F_CFG_TREND_WINDOW_SIZE)
            if cfg_val is not None:
                trend_window_size = max(1, int(cfg_val))
    except Exception as e:
        logger.warning("client_progress: could not read trend window size: %s", e)

    return ClientProgressResponse(
        pattern_history=pattern_history,
        past_experiments=past_experiments,
        trend_window_size=trend_window_size,
    )


@router.get("/api/client/runs/{run_id}/meta")
async def get_run_meta(
    run_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """
    Returns lightweight transcript metadata for the run detail page header.
    """
    at_client = AirtableClient()
    try:
        run_rec = at_client.get_run(run_id)
        rf = run_rec.get("fields", {})

        # Ownership check
        if user.role == "coachee":
            coachee_id = rf.get("Coachee ID")
            if coachee_id != user.airtable_user_record_id:
                return error_response("FORBIDDEN", "You do not have access to this run.", 403)

        transcript_meta: dict = {
            "run_id": run_id,
            "analysis_type": rf.get("Analysis Type"),
            "title": None,
            "transcript_id": None,
            "meeting_date": None,
            "meeting_type": None,
            "target_role": None,
        }

        transcript_links = rf.get("Transcript ID", [])
        if transcript_links:
            try:
                tr_rec = at_client.get_transcript(transcript_links[0])
                trf = tr_rec.get("fields", {})
                transcript_meta.update({
                    "title": trf.get("Title"),
                    "transcript_id": trf.get("Transcript ID"),
                    "meeting_date": trf.get("Meeting Date"),
                    "meeting_type": trf.get("Meeting Type"),
                    "target_role": trf.get("Target Role"),
                })
            except Exception as te:
                logger.warning("get_run_meta: could not fetch transcript for run %s: %s", run_id, te)

        return transcript_meta

    except Exception as e:
        logger.warning("get_run_meta: error for run %s: %s", run_id, e)
        return error_response("NOT_FOUND", "Run not found.", 404)

@router.delete("/api/client/runs/{run_id}")
async def delete_run(
    run_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """
    Delete a single-meeting run and its linked transcript and run_requests.
    Baseline pack runs cannot be deleted via this endpoint.
    """
    at_client = AirtableClient()
    try:
        run_rec = at_client.get_run(run_id)
    except Exception:
        return error_response("NOT_FOUND", "Run not found.", 404)

    rf = run_rec.get("fields", {})

    # Ownership check
    if user.role == "coachee":
        if rf.get("Coachee ID") != user.airtable_user_record_id:
            return error_response("FORBIDDEN", "You do not have access to this run.", 403)

    # Block deletion of baseline pack runs (both aggregate and sub-runs)
    if rf.get("baseline_pack") or rf.get("Analysis Type") == "baseline_pack":
        return error_response(
            "FORBIDDEN", "Baseline pack analyses cannot be deleted here.", 403
        )

    # Delete linked run_requests
    for rr_id in rf.get("run_requests", []):
        try:
            at_client.delete_run_request(rr_id)
        except Exception as e:
            logger.warning("delete_run: could not delete run_request %s: %s", rr_id, e)

    # Delete linked transcript
    for tr_id in rf.get("Transcript ID", []):
        try:
            at_client.delete_transcript(tr_id)
        except Exception as e:
            logger.warning("delete_run: could not delete transcript %s: %s", tr_id, e)

    # Delete the run itself
    try:
        at_client.delete_run(run_id)
    except Exception as e:
        logger.warning("delete_run: failed to delete run %s: %s", run_id, e)
        return error_response("SERVER_ERROR", "Failed to delete run.", 500)

    return {"deleted": True, "run_id": run_id}