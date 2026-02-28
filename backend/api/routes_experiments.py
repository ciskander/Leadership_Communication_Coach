"""
api/routes_experiments.py — Experiment lifecycle and attempt confirmation endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from ..core.workers import instantiate_experiment_from_run
from .dependencies import get_current_user
from .dto import ExperimentResponse
from .errors import error_response, invalid_input

router = APIRouter()


class ConfirmAttemptBody(BaseModel):
    human_confirmed: bool
    notes: Optional[str] = None


class ActivateFromRunBody(BaseModel):
    run_id: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/experiments/{exp_id}/complete")
async def complete_experiment(
    exp_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        at_client.update_record("experiments", exp_id, {"Status": "completed"})
    except Exception as exc:
        return error_response("UPDATE_FAILED", str(exc), 500)
    return {"experiment_id": exp_id, "status": "completed"}


@router.post("/api/experiments/{exp_id}/abandon")
async def abandon_experiment(
    exp_id: str,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    try:
        at_client.update_record("experiments", exp_id, {"Status": "abandoned"})
    except Exception as exc:
        return error_response("UPDATE_FAILED", str(exc), 500)
    return {"experiment_id": exp_id, "status": "abandoned"}


@router.post("/api/experiment_events/{event_id}/confirm_attempt")
async def confirm_attempt(
    event_id: str,
    body: ConfirmAttemptBody,
    user: UserAuth = Depends(get_current_user),
):
    at_client = AirtableClient()
    fields: dict = {"Human Confirmed": body.human_confirmed}
    if body.notes:
        fields["Notes"] = body.notes
    try:
        at_client.update_record("experiment_events", event_id, fields)
    except Exception as exc:
        return error_response("UPDATE_FAILED", str(exc), 500)
    return {"event_id": event_id, "human_confirmed": body.human_confirmed}


@router.post("/api/experiments/activate_from_run")
async def activate_from_run(
    body: ActivateFromRunBody,
    user: UserAuth = Depends(get_current_user),
):
    """Accept the next experiment suggestion from a run's micro_experiment output."""
    at_client = AirtableClient()

    # Instantiate experiment from run (idempotent)
    try:
        exp_record_id = instantiate_experiment_from_run(
            body.run_id,
            client=at_client,
            user_record_id=user.airtable_user_record_id,
        )
    except Exception as exc:
        return error_response("EXPERIMENT_CREATION_FAILED", str(exc), 500)

    if not exp_record_id:
        return error_response(
            "NO_EXPERIMENT",
            "No micro_experiment found in the specified run.",
            400,
        )

    # Set status to active
    at_client.update_record("experiments", exp_record_id, {"Status": "active"})

    return {"experiment_id": exp_record_id, "status": "active"}
