"""
api/routes_coach.py — Coach-facing endpoints.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from ..auth.models import UserAuth
from ..core.airtable_client import AirtableClient
from .auth import list_coachees_for_coach
from .dependencies import get_current_user
from .dto import (
    ClientProgressResponse,
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


class AssignCoacheeBody(BaseModel):
    user_id: str


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


@router.get("/api/coach/users/search", response_model=list[CoacheeListItem])
async def search_users(
    q: str = Query(..., min_length=2),
    user: UserAuth = Depends(get_current_user),
):
    """Search existing coachee users by email or display name."""
    _require_coach(user)

    from .auth import get_conn
    q_lower = q.lower()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, display_name, airtable_user_record_id
                FROM users_auth
                WHERE (LOWER(email) LIKE %s OR LOWER(display_name) LIKE %s)
                  AND id != %s
                  AND role = 'coachee'
                LIMIT 10
                """,
                (f"%{q_lower}%", f"%{q_lower}%", user.id),
            )
            rows = cur.fetchall()

    return [
        CoacheeListItem(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            airtable_user_record_id=row["airtable_user_record_id"],
        )
        for row in rows
    ]


@router.post("/api/coach/assign_coachee", response_model=CoacheeListItem)
async def assign_coachee(
    body: AssignCoacheeBody,
    user: UserAuth = Depends(get_current_user),
):
    """Assign an existing coachee user to this coach."""
    _require_coach(user)

    from .auth import get_user_by_id, get_conn
    target = get_user_by_id(body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.role != "coachee":
        raise HTTPException(status_code=400, detail="User is not a coachee.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users_auth SET coach_id = %s WHERE id = %s",
                (user.id, body.user_id),
            )
        conn.commit()

    return CoacheeListItem(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        airtable_user_record_id=target.airtable_user_record_id,
    )


@router.get("/api/coach/coachees/{coachee_auth_id}/summary", response_model=CoacheeSummaryResponse)
async def coachee_summary(
    coachee_auth_id: str,
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

    active_bp: Optional[dict] = None
    active_exp_resp: Optional[ExperimentResponse] = None
    proposed_experiments: list[ExperimentResponse] = []
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
                attempt_count = None
                meeting_count = None
                try:
                    attempt_count, meeting_count = at_client.count_experiment_attempts_and_meetings(exp_rec["id"])
                except Exception:
                    pass
                active_exp_resp = ExperimentResponse(
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

            # Proposed experiments
            user_primary_id = uf.get("User ID", "")
            if user_primary_id:
                try:
                    exp_formula = (
                        f"AND("
                        f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
                        f"{{Status}} = 'proposed'"
                        f")"
                    )
                    prop_records = at_client.search_records("experiments", exp_formula, max_records=3)
                    # Sort so baseline-pack-linked experiment (focus pattern) appears first,
                    # then by creation time ascending (worker creates in priority order).
                    prop_records.sort(key=lambda r: (
                        0 if r.get("fields", {}).get("Baseline Pack") else 1,
                        r.get("createdTime", ""),
                    ))
                    for pe in prop_records:
                        pef = pe.get("fields", {})
                        proposed_experiments.append(ExperimentResponse(
                            experiment_record_id=pe["id"],
                            experiment_id=pef.get("Experiment ID", ""),
                            title=pef.get("Title", ""),
                            instruction=pef.get("Instructions") or pef.get("Instruction", ""),
                            success_marker=pef.get("Success Marker") or pef.get("Success Criteria", ""),
                            pattern_id=pef.get("Pattern ID", ""),
                            status=pef.get("Status", ""),
                            created_at=pe.get("createdTime"),
                        ))
                except Exception:
                    logger.warning("coachee_summary: could not fetch proposed experiments for %s", coachee_auth_id)

            run_formula = f"{{Coachee ID}} = '{coachee.airtable_user_record_id}'"
            run_records = at_client.search_records("runs", run_formula, sort=["-Created At"])
            for r in run_records:
                rf = r.get("fields", {})
                # Skip baseline sub-runs
                if rf.get("baseline_pack_items"):
                    continue
                # Enrich with transcript metadata (title, meeting_date, meeting_type)
                transcript_meta: dict = {}
                transcript_links = rf.get("Transcript ID", [])
                if transcript_links:
                    try:
                        tr_rec = at_client.get_transcript(transcript_links[0])
                        trf = tr_rec.get("fields", {})
                        transcript_meta = {
                            "title": trf.get("Title"),
                            "transcript_id": trf.get("Transcript ID"),
                            "meeting_date": trf.get("Meeting Date"),
                            "meeting_type": trf.get("Meeting Type"),
                            "target_role": trf.get("Target Role"),
                        }
                    except Exception as te:
                        logger.warning("coachee_summary: could not fetch transcript for run %s: %s", r["id"], te)
                run_entry: dict = {
                    "run_id": r["id"],
                    "analysis_type": rf.get("Analysis Type"),
                    "gate1_pass": rf.get("Gate1 Pass"),
                    "focus_pattern": rf.get("Focus Pattern"),
                    "created_at": r.get("createdTime"),
                    **transcript_meta,
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
        proposed_experiments=proposed_experiments,
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

    # Attach coachee's active experiment so the worker can populate experiment
    # tracking and create experiment_events — mirrors what enqueue_analysis does.
    if coachee.airtable_user_record_id:
        try:
            coachee_at_rec = at_client.get_user(coachee.airtable_user_record_id)
            ae_links = coachee_at_rec.get("fields", {}).get("Active Experiment", [])
            if ae_links:
                rr_fields["Active Experiment"] = ae_links
        except Exception as exc:
            logger.warning(
                "Could not attach active experiment to coach-initiated run_request for coachee %s: %s",
                coachee.airtable_user_record_id, exc,
            )

    rr_record = at_client.create_record("run_requests", rr_fields)
    rr_id = rr_record["id"]
    job = enqueue_single_meeting.delay(rr_id)
    return SingleMeetingEnqueueResponse(
        run_request_id=rr_id,
        job_id=job.id,
        status="queued",
    )


@router.get("/api/coach/coachees/{coachee_auth_id}/progress", response_model=ClientProgressResponse)
async def coachee_progress(
    coachee_auth_id: str,
    user: UserAuth = Depends(get_current_user),
):
    """Return pattern history and past experiments for a coach's coachee."""
    _require_coach(user)

    from .auth import get_user_by_id
    coachee = get_user_by_id(coachee_auth_id)
    if not coachee:
        raise HTTPException(status_code=404, detail="Coachee not found.")
    if user.role == "coach" and coachee.coach_id != user.id:
        raise HTTPException(status_code=403, detail="This coachee is not under your coaching.")

    at_client = AirtableClient()
    pattern_history: list[dict] = []
    past_experiments: list[dict] = []

    if not coachee.airtable_user_record_id:
        return ClientProgressResponse(pattern_history=[], past_experiments=[])

    # ── Fetch eligible runs ───────────────────────────────────────────────
    runs_formula = (
        f"AND({{Coachee ID}} = '{coachee.airtable_user_record_id}', {{Gate1 Pass}} = TRUE())"
    )
    try:
        run_records = at_client.search_records("runs", runs_formula, max_records=60)
    except Exception as e:
        logger.warning("coachee_progress: error fetching runs: %s", e)
        run_records = []

    for run_rec in run_records:
        rf = run_rec.get("fields", {})
        analysis_type = rf.get("Analysis Type", "")

        if rf.get("baseline_pack_items"):
            continue

        is_baseline = analysis_type == "baseline_pack"

        meeting_date: Optional[str] = None
        transcript_links = rf.get("Transcript ID", [])
        if transcript_links:
            try:
                tr_rec = at_client.get_transcript(transcript_links[0])
                meeting_date = tr_rec.get("fields", {}).get("Meeting Date")
            except Exception:
                pass

        patterns = []
        parsed_json_str = rf.get("Parsed JSON") or "{}"
        try:
            parsed = json.loads(parsed_json_str)
            snapshot = parsed.get("pattern_snapshot", [])
            for p in snapshot:
                pid = p.get("pattern_id", "")
                if not pid:
                    continue
                score_val = p.get("score")
                if score_val is None:
                    continue
                opp = p.get("opportunity_count") or 0
                patterns.append({
                    "pattern_id": pid,
                    "score": float(score_val),
                    "opportunity_count": int(opp) if opp else 0,
                })
        except Exception:
            pass

        if not patterns:
            continue

        pattern_history.append({
            "run_id": run_rec["id"],
            "meeting_date": meeting_date,
            "is_baseline": is_baseline,
            "analysis_type": analysis_type,
            "patterns": patterns,
        })

    pattern_history.sort(
        key=lambda x: (x["meeting_date"] is None, x["meeting_date"] or "")
    )

    # ── Fetch past experiments ────────────────────────────────────────────
    user_primary_id = ""
    try:
        user_rec = at_client.get_user(coachee.airtable_user_record_id)
        user_primary_id = user_rec.get("fields", {}).get("User ID", "")
    except Exception:
        pass

    if user_primary_id:
        exp_formula = (
            f"AND("
            f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
            f"OR({{Status}} = 'completed', {{Status}} = 'abandoned', {{Status}} = 'parked')"
            f")"
        )
        try:
            exp_records = at_client.search_records("experiments", exp_formula, max_records=30)
        except Exception:
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

        past_experiments.sort(key=lambda x: (x["ended_at"] or ""), reverse=True)

    # ── Read trend window size ────────────────────────────────────────────
    from ..core.airtable_client import F_CFG_TREND_WINDOW_SIZE
    trend_window_size = 3
    try:
        active_cfg = at_client.get_active_config()
        if active_cfg:
            cfg_val = active_cfg.get("fields", {}).get(F_CFG_TREND_WINDOW_SIZE)
            if cfg_val is not None:
                trend_window_size = max(1, int(cfg_val))
    except Exception:
        pass

    return ClientProgressResponse(
        pattern_history=pattern_history,
        past_experiments=past_experiments,
        trend_window_size=trend_window_size,
    )
