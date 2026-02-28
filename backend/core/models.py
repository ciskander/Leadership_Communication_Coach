"""
models.py — Pydantic models for internal data flow.

These models represent the *engine's* internal state, NOT the OpenAI JSON output
(which is validated by the JSON schema in gate1_validator.py).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Transcript Parser ─────────────────────────────────────────────────────────

class Turn(BaseModel):
    turn_id: int
    speaker_label: str
    text: str
    speaker_role_hint: Optional[str] = None


class TranscriptMetadata(BaseModel):
    original_format: str
    turn_count: int
    word_count: int
    truncated: bool = False


class ParsedTranscript(BaseModel):
    source_id: str
    turns: list[Turn]
    speaker_labels: list[str]
    metadata: TranscriptMetadata


# ── Gate1 Validator ───────────────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    severity: str          # "error" | "warning"
    issue_code: str
    path: str
    message: str


class Gate1Result(BaseModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


# ── Airtable / domain objects ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    record_id: str
    request_id: str
    transcript_record_id: str
    target_speaker_name: str
    target_speaker_label: str
    target_role: str
    analysis_type: str                 # "single_meeting" | "baseline_pack"
    config_name: Optional[str] = None
    status: str
    baseline_pack_record_id: Optional[str] = None
    user_record_id: Optional[str] = None
    active_experiment_record_id: Optional[str] = None
    active_experiment_id: Optional[str] = None   # EXP-xxxxxx


class Run(BaseModel):
    record_id: str
    run_id: str
    transcript_record_id: str
    model_name: str
    request_payload_json: str
    raw_model_output: str
    parsed_json: Optional[str] = None
    parse_ok: bool = False
    schema_ok: bool = False
    business_ok: bool = False
    gate1_pass: bool = False
    schema_version_out: Optional[str] = None
    focus_pattern: Optional[str] = None
    micro_experiment_pattern: Optional[str] = None
    strengths_patterns: Optional[str] = None    # JSON array string
    evaluated_patterns_count: Optional[int] = None
    evidence_span_count: Optional[int] = None
    target_speaker_name: Optional[str] = None
    target_speaker_label: Optional[str] = None
    target_speaker_role: Optional[str] = None
    analysis_type: Optional[str] = None
    attempt_model: Optional[str] = None
    experiment_status_model: Optional[str] = None
    experiment_id_out: Optional[str] = None
    idempotency_key: Optional[str] = None
    coachee_id: Optional[str] = None


class BaselinePackItem(BaseModel):
    record_id: str
    item_id: str
    baseline_pack_record_id: str
    transcript_record_id: Optional[str] = None
    run_record_id: Optional[str] = None
    meeting_summary_json: Optional[str] = None
    status: Optional[str] = None


class BaselinePack(BaseModel):
    record_id: str
    pack_id: str            # BP-xxxxxx
    client_name: Optional[str] = None
    target_role: Optional[str] = None
    status: Optional[str] = None
    speaker_label: Optional[str] = None
    active_experiment_record_id: Optional[str] = None
    items: list[BaselinePackItem] = Field(default_factory=list)


class Experiment(BaseModel):
    record_id: str
    experiment_id: str      # EXP-xxxxxx
    title: str
    instructions: str
    success_criteria: Optional[str] = None
    pattern_id: str
    status: str             # assigned | active | completed | abandoned
    baseline_pack_record_id: Optional[str] = None
    proposed_by_run_record_id: Optional[str] = None
    created_from_run_id: Optional[str] = None
    user_record_id: Optional[str] = None


class ExperimentEvent(BaseModel):
    record_id: str
    event_id: str
    experiment_record_id: str
    run_record_id: str
    user_record_id: Optional[str] = None
    transcript_record_id: Optional[str] = None
    meeting_date: Optional[str] = None
    detection_model: Optional[str] = None
    evidence_span_ids_model: Optional[str] = None
    attempt_enum: Optional[str] = None
    attempt_count: Optional[int] = None
    idempotency_key: Optional[str] = None


# ── Prompt Builder ────────────────────────────────────────────────────────────

class MemoryBlock(BaseModel):
    baseline_profile: Optional[dict[str, Any]] = None
    recent_pattern_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    active_experiment: Optional[dict[str, Any]] = None


class PromptPayload(BaseModel):
    """Full user message content assembled by prompt_builder."""
    analysis_type: str
    meta: dict[str, Any]
    context: dict[str, Any]
    memory: MemoryBlock
    transcript_payload: dict[str, Any]   # {"source_id": ..., "turns": [...]}
    raw_user_message: str                # final string sent to OpenAI


# ── OpenAI response wrapper ───────────────────────────────────────────────────

class OpenAIResponse(BaseModel):
    parsed: dict[str, Any]
    raw_text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
