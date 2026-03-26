"""
api/dto.py — Pydantic response models for all API endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class MeResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    role: str
    coach_id: Optional[str]
    airtable_user_record_id: Optional[str]
    profile_photo_url: Optional[str] = None
    last_login: Optional[datetime]


# ── Transcripts ───────────────────────────────────────────────────────────────

class TranscriptUploadResponse(BaseModel):
    transcript_id: str          # Airtable record ID
    speaker_labels: list[str]
    word_count: Optional[int]
    meeting_type: Optional[str]
    meeting_date: Optional[str]
    detected_date: Optional[str] = None
    speaker_previews: dict[str, list[str]] = Field(default_factory=dict)


class TranscriptListItem(BaseModel):
    transcript_id: str
    title: Optional[str]
    meeting_type: Optional[str]
    meeting_date: Optional[str]
    created_at: Optional[str]
    speaker_labels: list[str] = []


# ── Runs ──────────────────────────────────────────────────────────────────────

class QuoteObject(BaseModel):
    speaker_label: Optional[str]
    quote_text: str
    meeting_id: Optional[str]
    transcript_id: Optional[str]
    span_id: Optional[str]
    start_timestamp: Optional[str] = None
    meeting_label: Optional[str] = None
    is_target_speaker: Optional[bool] = None


class HighlightItem(BaseModel):
    """Lightweight coaching highlight for strengths/focus — just pattern_id + message."""
    pattern_id: str
    message: str


class MicroExperimentWithQuotes(BaseModel):
    experiment_id: str
    title: str
    instruction: str
    success_marker: str
    pattern_id: str
    quotes: list[QuoteObject] = Field(default_factory=list)


class ExperimentDetectionWithQuotes(BaseModel):
    experiment_id: str
    attempt: str                         # yes | partial | no
    count_attempts: int = 0
    quotes: list[QuoteObject] = Field(default_factory=list)
    coaching_note: Optional[str] = None
    suggested_rewrite: Optional[str] = None
    rewrite_for_span_id: Optional[str] = None


class PatternSnapshotItem(BaseModel):
    """Scoring-only pattern measurement (v0.4.0: coaching fields moved to PatternCoachingItem)."""
    pattern_id: str
    cluster_id: Optional[str] = None
    scoring_type: Optional[str] = None
    evaluable_status: str
    score: Optional[float] = None
    opportunity_count: Optional[int] = None
    balance_assessment: Optional[str] = None
    quotes: list[QuoteObject] = Field(default_factory=list)
    success_span_ids: list[str] = Field(default_factory=list)


class PatternCoachingItem(BaseModel):
    """Per-pattern coaching output (v0.4.0: separated from pattern_snapshot)."""
    pattern_id: str
    notes: Optional[str] = None
    coaching_note: Optional[str] = None
    suggested_rewrite: Optional[str] = None
    rewrite_for_span_id: Optional[str] = None
    best_success_span_id: Optional[str] = None


class ExperimentCoachingItem(BaseModel):
    """Experiment coaching output for partial attempts (v0.4.0)."""
    coaching_note: Optional[str] = None
    suggested_rewrite: Optional[str] = None
    rewrite_for_span_id: Optional[str] = None


class RunStatusResponse(BaseModel):
    run_id: str
    status: str                         # queued | running | complete | error
    gate1_pass: Optional[bool] = None
    analysis_type: Optional[str] = None
    baseline_pack_id: Optional[str] = None   # set if this run is a baseline pack sub-run
    target_speaker_label: Optional[str] = None
    error: Optional[dict] = None
    # Populated when status=complete and gate1_pass=True
    executive_summary: Optional[str] = None
    strengths: list[HighlightItem] = Field(default_factory=list)
    focus: Optional[HighlightItem] = None
    micro_experiment: Optional[MicroExperimentWithQuotes] = None
    pattern_snapshot: Optional[list[PatternSnapshotItem]] = None
    pattern_coaching: list[PatternCoachingItem] = Field(default_factory=list)
    experiment_coaching: Optional[ExperimentCoachingItem] = None
    evaluation_summary: Optional[dict] = None
    experiment_tracking: Optional[dict] = None
    experiment_detection: Optional[ExperimentDetectionWithQuotes] = None
    human_confirmation: Optional[str] = None  # "confirmed_attempt" | "confirmed_no_attempt" | None
    active_experiment_detail: Optional[ExperimentResponse] = None
    active_experiment_events: list[dict] = Field(default_factory=list)


# ── Run Request status (lightweight poll) ─────────────────────────────────────

class TranscriptUpdateRequest(BaseModel):
    """Body for PATCH /api/transcripts/{id}."""
    meeting_date: Optional[str] = None   # ISO-8601 date string, or null to clear


class RunRequestStatusResponse(BaseModel):
    run_request_id: str
    status: str
    run_id: Optional[str] = None
    error: Optional[dict] = None
    progress_message: Optional[str] = None


# ── Baseline Packs ────────────────────────────────────────────────────────────

class BaselinePackCreateResponse(BaseModel):
    baseline_pack_id: str
    status: str


class BaselinePackBuildResponse(BaseModel):
    baseline_pack_id: str
    job_id: str
    status: str = "queued"


# ── Analyses ──────────────────────────────────────────────────────────────────

class SingleMeetingEnqueueResponse(BaseModel):
    run_request_id: str
    job_id: str
    status: str = "queued"


# ── Experiments ───────────────────────────────────────────────────────────────

class ExperimentResponse(BaseModel):
    experiment_record_id: str
    experiment_id: str
    title: str
    instruction: str
    success_marker: str
    pattern_id: str
    status: str
    created_at: Optional[str]
    attempt_count: Optional[int] = None
    meeting_count: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class ActiveExperimentResponse(BaseModel):
    experiment: Optional[ExperimentResponse]
    recent_events: list[dict] = Field(default_factory=list)


class ExperimentActionResponse(BaseModel):
    """Returned by accept / complete / abandon endpoints."""
    experiment_record_id: str
    status: str
    message: str


class HumanConfirmResponse(BaseModel):
    event_record_id: str
    experiment_record_id: str
    confirmed: bool


class RankedExperimentItem(BaseModel):
    """A proposed or parked experiment with its rank position and origin."""
    experiment: ExperimentResponse
    origin: str  # "proposed" or "parked"
    rank: int  # 1-based rank


class ExperimentOptionsResponse(BaseModel):
    """Combined proposed + parked experiments for the selection screen."""
    proposed: list[ExperimentResponse] = Field(default_factory=list)
    parked: list[ExperimentResponse] = Field(default_factory=list)
    ranked: list[RankedExperimentItem] = Field(default_factory=list)
    at_park_cap: bool = False


# ── Coach ─────────────────────────────────────────────────────────────────────

class CoacheeListItem(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    airtable_user_record_id: Optional[str]


class CoacheeSummaryResponse(BaseModel):
    coachee: CoacheeListItem
    active_baseline_pack: Optional[dict] = None
    active_experiment: Optional[ExperimentResponse] = None
    proposed_experiments: list[ExperimentResponse] = Field(default_factory=list)
    recent_runs: list[dict] = Field(default_factory=list)


# ── Client dashboard ─────────────────────────────────────────────────────────

class ClientSummaryResponse(BaseModel):
    user: MeResponse
    active_experiment: Optional[ExperimentResponse] = None
    proposed_experiments: list[ExperimentResponse] = Field(default_factory=list)
    parked_experiment_count: int = 0
    baseline_pack_status: Optional[str] = None
    baseline_pack_id: Optional[str] = None
    recent_runs: list[dict] = Field(default_factory=list)


# ── Invites ───────────────────────────────────────────────────────────────────

class InviteResponse(BaseModel):
    invite_url: str
    token: str
    expires_in_days: int = 7


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminUserListItem(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    role: str
    coach_id: Optional[str]
    created_at: Optional[datetime]
    last_login: Optional[datetime]

# ── Client Progress ──────────────────────────────────────────────────────────

class PatternDataPoint(BaseModel):
    pattern_id: str
    score: float
    opportunity_count: int


class RunHistoryPoint(BaseModel):
    run_id: str
    meeting_date: Optional[str]
    is_baseline: bool
    analysis_type: Optional[str]
    patterns: list[PatternDataPoint]


class PastExperiment(BaseModel):
    experiment_record_id: str
    experiment_id: str
    title: str
    pattern_id: str
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    attempt_count: Optional[int]
    meeting_count: Optional[int] = None


class ClientProgressResponse(BaseModel):
    pattern_history: list[RunHistoryPoint]
    past_experiments: list[PastExperiment]
    trend_window_size: int = 3
