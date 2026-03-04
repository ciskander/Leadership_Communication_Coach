"""
api/routes_coachee.py — Endpoints for coachee / client users.
"""
from __future__ import annotations

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
    ExperimentResponse,
    ClientProgressResponse,    
    HumanConfirmResponse,
    MeResponse,
    SingleMeetingEnqueueResponse,
)
from .errors import error_response, invalid_input
from ..queue.tasks import enqueue_single_meeting, enqueue_baseline_pack_build, enqueue_next_experiment_suggestion

logger = logging.getLogger(__name__)

router = APIRouter()


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

def _build_experiment_response(exp_rec: dict) -> ExperimentResponse:
    ef = exp_rec.get("fields", {})
    return ExperimentResponse(
        experiment_record_id=exp_rec["id"],
        experiment_id=ef.get("Experiment ID", ""),
        title=ef.get("Title", ""),
        instruction=ef.get("Instructions") or ef.get("Instruction", ""),
        success_marker=ef.get("Success Marker") or ef.get("Success Criteria", ""),
        pattern_id=ef.get("Pattern ID", ""),
        status=ef.get("Status", ""),
        created_at=exp_rec.get("createdTime"),
        attempt_count=ef.get("Attempt Count (model)"),
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
    except Exception:
        return error_response("NOT_FOUND", "Baseline pack not found.", 404)

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
    except Exception:
        return error_response("NOT_FOUND", "Baseline pack not found.", 404)

    # Ownership check: coachees can only view their own packs.
    if user.role == "coachee":
        bp_user_links = bp_rec.get("fields", {}).get("users", [])
        if not isinstance(bp_user_links, list) or user.airtable_user_record_id not in bp_user_links:
            return error_response("FORBIDDEN", "You do not have access to this baseline pack.", 403)

    bf = bp_rec.get("fields", {})

    strengths, focus, micro_experiment = [], None, None
    last_run_links = bf.get("Last Run", [])
    if last_run_links:
        try:
            run_rec = at_client.get_run(last_run_links[0])
            parsed_json_str = run_rec.get("fields", {}).get("Parsed JSON") or "{}"
            parsed = json.loads(parsed_json_str)
            coaching = parsed.get("coaching_output", {})
            strengths = coaching.get("strengths", [])
            focus = (coaching.get("focus") or [None])[0]
            micro_experiment = (coaching.get("micro_experiment") or [None])[0]
        except Exception:
            pass

    return {
        "baseline_pack_id": bp_rec["id"],
        "status": bf.get("Status"),
        "target_role": bf.get("Target Role"),
        "role_consistency": bf.get("Role Consistency"),
        "meeting_type_consistency": bf.get("Meeting Type Consistency"),
        "strengths": strengths,
        "focus": focus,
        "micro_experiment": micro_experiment,
        "created_at": bp_rec.get("createdTime"),
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
        enqueue_next_experiment_suggestion.delay(user.airtable_user_record_id)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="completed",
        message="Great work completing the experiment. Choose your next one when you're ready.",
    )


@router.post(
    "/api/client/experiments/{experiment_record_id}/abandon",
    response_model=ExperimentActionResponse,
)
async def abandon_experiment(
    experiment_record_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Abandon an active experiment."""
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
        return error_response("INVALID_STATE", f"Experiment cannot be abandoned from state: {ef.get('Status')}.", 400)

    at_client.abandon_experiment(experiment_record_id, user.airtable_user_record_id)
    logger.info("User %s abandoned experiment %s", user.airtable_user_record_id, experiment_record_id)

    # Fire-and-forget: generate next experiment suggestion in the background
    if user.airtable_user_record_id:
        enqueue_next_experiment_suggestion.delay(user.airtable_user_record_id)

    return ExperimentActionResponse(
        experiment_record_id=experiment_record_id,
        status="abandoned",
        message="Experiment abandoned.",
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
    bp_status: Optional[str] = None
    recent_runs: list[dict] = []

    if user.airtable_user_record_id:
        try:
            user_rec = at_client.get_user(user.airtable_user_record_id)
            u_fields = user_rec.get("fields", {})

            # Active experiment
            ae_links = u_fields.get("Active Experiment", [])
            if ae_links:
                exp_rec = at_client.get_experiment(ae_links[0])
                active_exp_resp = _build_experiment_response(exp_rec)

            # Proposed experiments (max 3)
            proposed_records = at_client.get_proposed_experiments_for_user(
                user.airtable_user_record_id, max_records=3
            )
            proposed_exps = [_build_experiment_response(r) for r in proposed_records]

            # Baseline pack status
            bp_links = u_fields.get("Active Baseline Pack", [])
            if bp_links:
                bp_rec = at_client.get_baseline_pack(bp_links[0])
                bp_status = bp_rec.get("fields", {}).get("Status")

            # Recent runs (last 5)
            runs_formula = f"{{Coachee ID}} = '{user.airtable_user_record_id}'"
            run_records = at_client.search_records("runs", runs_formula, max_records=5)
            for r in run_records:
                rf = r.get("fields", {})
                recent_runs.append({
                    "run_id": r["id"],
                    "analysis_type": rf.get("Analysis Type"),
                    "gate1_pass": rf.get("Gate1 Pass"),
                    "focus_pattern": rf.get("Focus Pattern"),
                    "created_at": r.get("createdTime"),
                })

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
        baseline_pack_status=bp_status,
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
        exp_resp = _build_experiment_response(exp_rec)

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
        baseline_pack_links = rf.get("baseline_pack", [])

        # Skip baseline sub-runs (single_meeting runs that belong to a baseline pack)
        if analysis_type == "single_meeting" and baseline_pack_links:
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
                patterns.append({
                    "pattern_id": pid,
                    "ratio": float(p.get("ratio", 0.0)),
                    "opportunity_count": int(p.get("opportunity_count", 0)),
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
        f"OR({{Status}} = 'completed', {{Status}} = 'abandoned')"
        f")"
    )
    try:
        exp_records = at_client.search_records("experiments", exp_formula, max_records=30)
    except Exception as e:
        logger.warning("client_progress: error fetching past experiments: %s", e)
        exp_records = []

    for exp_rec in exp_records:
        ef = exp_rec.get("fields", {})
        past_experiments.append({
            "experiment_record_id": exp_rec["id"],
            "experiment_id": ef.get("Experiment ID", ""),
            "title": ef.get("Title", ""),
            "pattern_id": ef.get("Pattern ID", ""),
            "status": ef.get("Status", ""),
            "started_at": ef.get("Started At"),
            "ended_at": ef.get("Ended At"),
            "attempt_count": ef.get("Attempt Count (model)"),
        })

    # Most recent first (by ended_at)
    past_experiments.sort(key=lambda x: (x["ended_at"] or ""), reverse=True)

    return ClientProgressResponse(
        pattern_history=pattern_history,
        past_experiments=past_experiments,
    )
