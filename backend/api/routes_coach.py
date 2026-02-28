"""
api/routes_coach.py — Coach-facing endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from .auth import list_coachees_for_coach
from .dependencies import get_current_user
from .dto import (
    CoacheeListItem,
    CoacheeSummaryResponse,
    ExperimentResponse,
    SingleMeetingEnqueueResponse,
)
from .errors import error_response, forbidden
from ..queue.tasks import enqueue_single_meeting

router = APIRouter()


class CoachAnalyzeBody(BaseModel):
    transcript_id: str
    target_speaker_name: str
    target_speaker_label: str
    target_role: str


def _require_coach(user: UserAuth) -> UserAuth:
    if user.role not in ("coach", "admin"):
        raise HTTPException(status_code=403, detail="Coach access required.")
    return user


@router.get("/api/coach/coachees", response_model=list[CoacheeListItem])
async def list_coachees(user: UserAuth = Depends(get_current_user)):
    _require_coach(user)
    coachees = list_coachees_for_coach(user.id)
    return [
        CoacheeListItem(
            id=c.id,
            email=c.email,
            display_name=c.display_name,
            airtable_user_record_id=c.airtable_user_record_id,
        )
        for c in coachees
    ]


@router.get("/api/coach/coachees/{coachee_auth_id}/summary", response_model=CoacheeSummaryResponse)
async def coachee_summary(
    coachee_auth_id: str,
    user: UserAuth = Depends(get_current_user),
):
    _require_coach(user)

    # Validate the coachee belongs to this coach (unless admin)
    from .auth import get_user_by_id
    coachee = get_user_by_id(coachee_auth_id)
    if not coachee:
        raise HTTPException(status_code=404, detail="Coachee not found.")
    if user.role == "coach" and coachee.coach_id != user.id:
        raise HTTPException(status_code=403, detail="This coachee is not under your coaching.")

    at_client = AirtableClient()

    active_bp: Optional[dict] = None
    active_exp_resp: Optional[ExperimentResponse] = None
    recent_runs: list[dict] = []

    if coachee.airtable_user_record_id:
        try:
            at_user = at_client.get_user(coachee.airtable_user_record_id)
            uf = at_user.get("fields", {})

            bp_links = uf.get("Active Baseline Pack", [])
            if bp_links:
                bp_rec = at_client.get_baseline_pack(bp_links[0])
                bpf = bp_rec.get("fields", {})
                active_bp = {
                    "record_id": bp_rec["id"],
                    "status": bpf.get("Status"),
                    "target_role": bpf.get("Target Role"),
                }

            ae_links = uf.get("Active Experiment", [])
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

            run_formula = f"{{Coachee ID}} = '{coachee.airtable_user_record_id}'"
            run_records = at_client.search_records("runs", run_formula, max_records=10)
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

    return CoacheeSummaryResponse(
        coachee=CoacheeListItem(
            id=coachee.id,
            email=coachee.email,
            display_name=coachee.display_name,
            airtable_user_record_id=coachee.airtable_user_record_id,
        ),
        active_baseline_pack=active_bp,
        active_experiment=active_exp_resp,
        recent_runs=recent_runs,
    )


@router.post("/api/coach/coachees/{coachee_auth_id}/analyze", response_model=SingleMeetingEnqueueResponse)
async def coach_analyze(
    coachee_auth_id: str,
    body: CoachAnalyzeBody,
    user: UserAuth = Depends(get_current_user),
):
    _require_coach(user)

    from .auth import get_user_by_id
    coachee = get_user_by_id(coachee_auth_id)
    if not coachee:
        raise HTTPException(status_code=404, detail="Coachee not found.")
    if user.role == "coach" and coachee.coach_id != user.id:
        raise HTTPException(status_code=403, detail="This coachee is not under your coaching.")

    at_client = AirtableClient()
    rr_fields: dict = {
        "Analysis Type": "single_meeting",
        "Transcript": [body.transcript_id],
        "Target Speaker Name": body.target_speaker_name,
        "Target Speaker Label": body.target_speaker_label,
        "Target Role": body.target_role,
        "Status": "queued",
    }
    if coachee.airtable_user_record_id:
        rr_fields["User"] = [coachee.airtable_user_record_id]

    rr_record = at_client.create_record("run_requests", rr_fields)
    rr_id = rr_record["id"]
    job = enqueue_single_meeting.delay(rr_id)
    return SingleMeetingEnqueueResponse(
        run_request_id=rr_id,
        job_id=job.id,
        status="queued",
    )
