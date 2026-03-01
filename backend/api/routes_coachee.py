"""
api/routes_coachee.py — Endpoints for coachee / client users.
"""
from __future__ import annotations

import json
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
    ExperimentResponse,
    MeResponse,
    SingleMeetingEnqueueResponse,
)
from .errors import error_response, invalid_input
from ..queue.tasks import enqueue_single_meeting, enqueue_baseline_pack_build

router = APIRouter()


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateBaselinePackBody(BaseModel):
    transcript_ids: list[str]           # exactly 3 Airtable transcript record IDs
    target_speaker_name: str
    target_speaker_label: str
    target_role: str


class SingleMeetingBody(BaseModel):
    transcript_id: str
    target_speaker_name: str
    target_speaker_label: str
    target_role: str
    analysis_type: str = "single_meeting"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/baseline_packs", response_model=BaselinePackCreateResponse)
async def create_baseline_pack(
    body: CreateBaselinePackBody,
    user: UserAuth = Depends(get_current_user),
):
    if len(body.transcript_ids) != 3:
        return invalid_input("Exactly 3 transcript IDs are required for a baseline pack.")

    at_client = AirtableClient()

    # Create the baseline_pack record
    bp_record = at_client.create_record("baseline_packs", {
        "Target Role": body.target_role,
        "Speaker Label": body.target_speaker_label,
        "Status": "draft",
        "users": [user.airtable_user_record_id] if user.airtable_user_record_id else [],
    })
    bp_record_id = bp_record["id"]

    # Create baseline_pack_items
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
    job = enqueue_baseline_pack_build.delay(bp_id)
    return BaselinePackBuildResponse(
        baseline_pack_id=bp_id,
        job_id=job.id,
        status="queued",
    )


@router.post("/api/analyses/single_meeting", response_model=SingleMeetingEnqueueResponse)
async def enqueue_analysis(
    body: SingleMeetingBody,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()

    # Create run_request record
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
    # Look up user's active experiment
    try:
        user_rec = at_client.get_user(user.airtable_user_record_id or "")
        ae_links = user_rec.get("fields", {}).get("Active Experiment", [])
        if ae_links:
            rr_fields["Active Experiment"] = ae_links
    except Exception:
        pass

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

@router.get("/api/client/summary", response_model=ClientSummaryResponse)
async def client_summary(
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()

    active_exp_resp: Optional[ExperimentResponse] = None
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
                ef = exp_rec.get("fields", {})
                active_exp_resp = ExperimentResponse(
                    experiment_record_id=exp_rec["id"],
                    experiment_id=ef.get("Experiment ID", ""),
                    title=ef.get("Title", ""),
                    instruction=ef.get("Instructions", ""),
                    success_marker=ef.get("Success Marker", ""),
                    pattern_id=ef.get("Pattern ID", ""),
                    status=ef.get("Status", ""),
                    created_at=exp_rec.get("createdTime"),
                )

            # Baseline pack status
            bp_links = u_fields.get("Active Baseline Pack", [])
            if bp_links:
                bp_rec = at_client.get_baseline_pack(bp_links[0])
                bp_status = bp_rec.get("fields", {}).get("Status")

            # Recent runs (last 5)
            runs_formula = f"FIND('{user.airtable_user_record_id}', ARRAYJOIN({{users}}))"
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

        except Exception:
            pass

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
        ef = exp_rec.get("fields", {})
        exp_resp = ExperimentResponse(
            experiment_record_id=exp_rec["id"],
            experiment_id=ef.get("Experiment ID", ""),
            title=ef.get("Title", ""),
            instruction=ef.get("Instructions", ""),
            success_marker=ef.get("Success Marker", ""),
            pattern_id=ef.get("Pattern ID", ""),
            status=ef.get("Status", ""),
            created_at=exp_rec.get("createdTime"),
        )

        # Recent events
        events_formula = f"{{Experiment}} = '{ae_links[0]}'"
        event_records = at_client.search_records("experiment_events", events_formula, max_records=10)
        events_out = []
        for er in event_records:
            erf = er.get("fields", {})
            events_out.append({
                "event_id": er["id"],
                "attempt": erf.get("Attempt (enum)"),
                "meeting_date": erf.get("Meeting Date"),
                "human_confirmed": erf.get("Human Confirmed"),
                "notes": erf.get("Notes"),
            })

        return ActiveExperimentResponse(experiment=exp_resp, recent_events=events_out)

    except Exception:
        return ActiveExperimentResponse(experiment=None)
