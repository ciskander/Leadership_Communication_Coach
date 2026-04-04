"""
conftest.py — Shared fixtures for all backend tests.
"""
from __future__ import annotations

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("AIRTABLE_TOKEN", "test-token")
os.environ.setdefault("AIRTABLE_BASE_ID", "test-base-id")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Canonical valid single-meeting OpenAI output
# ---------------------------------------------------------------------------

VALID_SINGLE_MEETING_OUTPUT: dict[str, Any] = {
    "schema_version": "mvp.v0.6.0",
    "meta": {
        "analysis_id": "A-260227",
        "analysis_type": "single_meeting",
        "generated_at": "2026-02-27T15:32:50.638-05:00",
        "taxonomy_version": "v3.1",
        "output_mode": "coaching_first_2s1e",
    },
    "context": {
        "meeting_id": "M-000001",
        "meeting_type": "exec_staff",
        "target_role": "chair",
        "meeting_date": "2026-02-12T05:00:00.000Z",
        "target_speaker_name": "Alice",
        "target_speaker_label": "Alice",
    },
    "opportunity_events": [
        {"event_id": "OE-001", "pattern_id": "purposeful_framing", "turn_start_id": 1, "turn_end_id": 2, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "clear_framing"},
        {"event_id": "OE-002", "pattern_id": "purposeful_framing", "turn_start_id": 10, "turn_end_id": 11, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "transition_framing"},
        {"event_id": "OE-003", "pattern_id": "focus_management", "turn_start_id": 1, "turn_end_id": 2, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "outcome_stated"},
        {"event_id": "OE-004", "pattern_id": "focus_management", "turn_start_id": 3, "turn_end_id": 3, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "intent_stated"},
        {"event_id": "OE-005", "pattern_id": "disagreement_navigation", "turn_start_id": 5, "turn_end_id": 5, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "perspective_sought"},
        {"event_id": "OE-006", "pattern_id": "disagreement_navigation", "turn_start_id": 15, "turn_end_id": 15, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "risk_solicited"},
        {"event_id": "OE-007", "pattern_id": "disagreement_navigation", "turn_start_id": 31, "turn_end_id": 32, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "acknowledged_reframed"},
        {"event_id": "OE-100", "pattern_id": "trust_and_credibility", "turn_start_id": 5, "turn_end_id": 5, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "evidence_cited"},
        {"event_id": "OE-008", "pattern_id": "resolution_and_alignment", "turn_start_id": 20, "turn_end_id": 21, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "explicit_closure"},
        {"event_id": "OE-009", "pattern_id": "assignment_clarity", "turn_start_id": 22, "turn_end_id": 22, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "owner_deadline_stated"},
        {"event_id": "OE-010", "pattern_id": "question_quality", "turn_start_id": 25, "turn_end_id": 25, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "substantive_question"},
        {"event_id": "OE-011", "pattern_id": "communication_clarity", "turn_start_id": 30, "turn_end_id": 30, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "clear_response"},
        {"event_id": "OE-012", "pattern_id": "feedback_quality", "turn_start_id": 31, "turn_end_id": 32, "target_control": "yes", "count_decision": "counted", "success": 1.0, "reason_code": "specific_feedback"},
    ],
    "evidence_spans": [
        {
            "evidence_span_id": "ES-T001-002",
            "turn_start_id": 1,
            "turn_end_id": 2,
            "excerpt": "Alright, let's get started. Today we have three main items.",
            "event_ids": ["OE-001", "OE-003"],
        },
        {
            "evidence_span_id": "ES-T010-011",
            "turn_start_id": 10,
            "turn_end_id": 11,
            "excerpt": "Moving to the second item on our agenda.",
            "event_ids": ["OE-002"],
        },
        {
            "evidence_span_id": "ES-T003",
            "turn_start_id": 3,
            "turn_end_id": 3,
            "excerpt": "We need to decide on the budget allocation by end of this meeting.",
            "event_ids": ["OE-004"],
        },
        {
            "evidence_span_id": "ES-T005",
            "turn_start_id": 5,
            "turn_end_id": 5,
            "excerpt": "Bob, what's your take on the Q2 projections?",
            "event_ids": ["OE-005", "OE-100"],
        },
        {
            "evidence_span_id": "ES-T015",
            "turn_start_id": 15,
            "turn_end_id": 15,
            "excerpt": "Carol, can you walk us through the risk analysis?",
            "event_ids": ["OE-006"],
        },
        {
            "evidence_span_id": "ES-T020-021",
            "turn_start_id": 20,
            "turn_end_id": 21,
            "excerpt": "So we're agreed: the budget is approved at 1.2M. Final decision.",
            "event_ids": ["OE-008"],
        },
        {
            "evidence_span_id": "ES-T022",
            "turn_start_id": 22,
            "turn_end_id": 22,
            "excerpt": "Bob owns the vendor selection, due by Friday.",
            "event_ids": ["OE-009"],
        },
        {
            "evidence_span_id": "ES-T025",
            "turn_start_id": 25,
            "turn_end_id": 25,
            "excerpt": "To recap: we've decided on the budget, Carol is on risk, Bob has vendor selection.",
            "event_ids": ["OE-010"],
        },
        {
            "evidence_span_id": "ES-T030",
            "turn_start_id": 30,
            "turn_end_id": 30,
            "excerpt": "What are the key constraints we need to consider?",
            "event_ids": ["OE-011"],
        },
        {
            "evidence_span_id": "ES-T031-032",
            "turn_start_id": 31,
            "turn_end_id": 32,
            "excerpt": "That's a good point. The main constraint is timeline, not budget.",
            "event_ids": ["OE-007", "OE-012"],
        },
        {
            "evidence_span_id": "CT-T020",
            "turn_start_id": 20,
            "turn_end_id": 21,
            "excerpt": "So we're agreed: the budget is approved at 1.2M. Final decision.",
            "event_ids": [],
        },
    ],
    "evaluation_summary": {
        "patterns_evaluated": [
            "purposeful_framing", "focus_management",
            "disagreement_navigation", "trust_and_credibility",
            "resolution_and_alignment", "assignment_clarity",
            "question_quality", "communication_clarity", "feedback_quality",
        ],
        "patterns_insufficient_signal": [],
        "patterns_not_evaluable": [],
    },
    "pattern_snapshot": [
        {
            "pattern_id": "purposeful_framing",
            "cluster_id": "meeting_structure",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_agenda_or_transition",
            "min_required_threshold": 1,
            "opportunity_count": 2,
            "score": 1.0,
            "evidence_span_ids": ["ES-T001-002", "ES-T010-011"],
            "success_evidence_span_ids": ["ES-T001-002", "ES-T010-011"],
        },
        {
            "pattern_id": "focus_management",
            "cluster_id": "meeting_structure",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_outcome_or_intent_statement",
            "min_required_threshold": 1,
            "opportunity_count": 2,
            "score": 1.0,
            "evidence_span_ids": ["ES-T001-002", "ES-T003"],
            "success_evidence_span_ids": ["ES-T001-002", "ES-T003"],
        },
        {
            "pattern_id": "disagreement_navigation",
            "cluster_id": "participation_dynamics",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "disagreement_moment",
            "min_required_threshold": 1,
            "opportunity_count": 3,
            "score": 1.0,
            "evidence_span_ids": ["ES-T005", "ES-T015", "ES-T031-032"],
            "success_evidence_span_ids": ["ES-T005", "ES-T015", "ES-T031-032"],
        },
        {
            "pattern_id": "trust_and_credibility",
            "cluster_id": "participation_dynamics",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "credibility_moment",
            "min_required_threshold": 1,
            "opportunity_count": 1,
            "score": 1.0,
            "evidence_span_ids": ["ES-T005"],
            "success_evidence_span_ids": ["ES-T005"],
        },
        {
            "pattern_id": "resolution_and_alignment",
            "cluster_id": "decisions_accountability",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_decision_moment_chair",
            "min_required_threshold": 2,
            "opportunity_count": 1,
            "score": 1.0,
            "evidence_span_ids": ["ES-T020-021"],
            "success_evidence_span_ids": ["ES-T020-021"],
        },
        {
            "pattern_id": "assignment_clarity",
            "cluster_id": "decisions_accountability",
            "scoring_type": "complexity_tiered",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "assignment_moment_chair",
            "min_required_threshold": 2,
            "opportunity_count": 1,
            "simple_count": 1,
            "complex_count": 0,
            "score": 1.0,
            "evidence_span_ids": ["ES-T022"],
            "success_evidence_span_ids": ["ES-T022"],
        },
        {
            "pattern_id": "question_quality",
            "cluster_id": "communication_quality",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "question_to_target",
            "min_required_threshold": 2,
            "opportunity_count": 1,
            "score": 1.0,
            "evidence_span_ids": ["ES-T025"],
            "success_evidence_span_ids": ["ES-T025"],
        },
        {
            "pattern_id": "communication_clarity",
            "cluster_id": "communication_quality",
            "scoring_type": "tiered_rubric",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "response_quality_check",
            "min_required_threshold": 2,
            "opportunity_count": 1,
            "score": 1.0,
            "evidence_span_ids": ["ES-T030"],
            "success_evidence_span_ids": ["ES-T030"],
        },
        {
            "pattern_id": "feedback_quality",
            "cluster_id": "communication_quality",
            "scoring_type": "multi_element",
            "evaluable_status": "evaluable",
            "denominator_rule_id": "feedback_moment",
            "min_required_threshold": 1,
            "opportunity_count": 1,
            "score": 1.0,
            "evidence_span_ids": ["ES-T031-032"],
            "success_evidence_span_ids": ["ES-T031-032"],
        },
    ],
    "experiment_tracking": {
        "active_experiment": {"experiment_id": "EXP-000000", "status": "none"},
        "detection_in_this_meeting": None,
        "graduation_recommendation": None,
    },
    "coaching": {
        "executive_summary": "You showed strong purposeful framing throughout the meeting. Focus on closing decisions with explicit verbal alignment to strengthen resolution patterns.",
        "coaching_themes": [
            {
                "theme": "Decision closure",
                "explanation": "Strengthen how you close out decisions explicitly.",
                "related_patterns": ["resolution_and_alignment"],
                "priority": "primary",
                "nature": "developmental",
                "best_success_span_id": None,
                "coaching_note": "You moved through decisions efficiently but didn't always pause to confirm alignment.",
                "suggested_rewrite": "Before we move on, let me confirm — we've agreed that Alex owns the timeline review by Friday. Does that work for everyone?",
                "rewrite_for_span_id": "CT-T020",
            }
        ],
        "micro_experiment": [
            {
                "experiment_id": "EXP-000001",
                "title": "Close every decision out loud",
                "instruction": "At the end of each agenda item, say aloud who owns the decision and what was decided.",
                "success_marker": "At least 2 out of 3 decision moments have explicit verbal closure in the next meeting.",
                "related_patterns": ["resolution_and_alignment"],
                "evidence_span_ids": ["ES-T020-021"],
            }
        ],
        "pattern_coaching": [],
        "experiment_coaching": None,
    },
}


@pytest.fixture
def valid_single_meeting_output() -> dict:
    import copy
    return copy.deepcopy(VALID_SINGLE_MEETING_OUTPUT)


@pytest.fixture
def valid_single_meeting_json(valid_single_meeting_output) -> str:
    return json.dumps(valid_single_meeting_output)


# ---------------------------------------------------------------------------
# Airtable mock
#
# Workers accept an optional `client` argument, so the cleanest approach is
# to build a MagicMock and pass it in directly rather than patching the class.
# This avoids having to know the precise import path and is more robust.
# ---------------------------------------------------------------------------

def _make_run_request_record(
    analysis_type: str = "single_meeting",
    baseline_pack_id: str | None = None,
) -> dict:
    fields: dict = {
        "Transcript": ["rec_tr_001"],
        "Target Speaker Name": "Alice",
        "Target Speaker Label": "Alice",
        "Target Role": "chair",
        "Analysis Type": analysis_type,
        "Status": "queued",
        "User": ["rec_user_001"],
        "Config": [],
    }
    if baseline_pack_id:
        fields["Baseline Pack"] = [baseline_pack_id]
    return {"id": "rec_rr_001", "fields": fields}


def _make_transcript_record() -> dict:
    return {
        "id": "rec_tr_001",
        "fields": {
            "Transcript ID": "T-000001",
            "Transcript (extracted)": (
                "Alice: Let's get started. Today we have three main items.\n"
                "Bob: Sounds good, ready when you are.\n"
                "Alice: First item is the Q2 budget approval."
            ),
            "Meeting Type": "exec_staff",
            "Meeting Date": "2026-02-12",
            "Title": "Q2 Budget Review",
            "Speaker Labels": json.dumps(["Alice", "Bob"]),
        },
    }


def _make_openai_response(output: dict):
    """Build a mock OpenAIResponse matching the real models.OpenAIResponse fields."""
    mock = MagicMock()
    mock.raw_text = json.dumps(output)
    mock.parsed = output
    mock.model = "gpt-4o"
    mock.prompt_tokens = 1000
    mock.completion_tokens = 500
    mock.total_tokens = 1500
    return mock


@pytest.fixture
def mock_at() -> MagicMock:
    """
    A pre-configured MagicMock that stands in for AirtableClient.
    Pass directly to worker functions via the `client=` argument.
    """
    at = MagicMock()
    at.get_run_request.return_value = _make_run_request_record()
    at.get_transcript.return_value = _make_transcript_record()
    at.create_run.return_value = {"id": "rec_run_001", "fields": {"Run ID": "R-000001"}}
    at.update_run.return_value = {"id": "rec_run_001"}
    at.update_record.return_value = None
    at.get_active_config.return_value = None          # no config → use defaults
    at.find_run_by_idempotency_key.return_value = None  # no prior run
    at.get_proposed_experiments_for_user.return_value = []
    at.get_active_experiment_for_user.return_value = None
    at.bulk_create_validation_issues.return_value = None
    # create_attempt_event_from_run fetches the run back to read Parsed JSON and Gate1 Pass.
    # Gate1 Pass=True triggers the event path; detection_in_this_meeting=None means no event
    # is created, so the function returns None cleanly without further Airtable calls.
    at.get_run.return_value = {
        "id": "rec_run_001",
        "fields": {
            "Run ID": "R-000001",
            "Gate1 Pass": True,
            "Parsed JSON": json.dumps(VALID_SINGLE_MEETING_OUTPUT),
        },
    }
    return at


@pytest.fixture
def mock_at_baseline(mock_at) -> MagicMock:
    """Variant of mock_at pre-configured for baseline pack scenarios."""
    mock_at.get_run_request.return_value = _make_run_request_record(
        analysis_type="single_meeting",
        baseline_pack_id="rec_bp_001",
    )
    return mock_at


# ---------------------------------------------------------------------------
# call_llm mock
#
# Workers call `call_llm(...)` which returns an OpenAIResponse object.
# Patch the function at its use-site inside workers.
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_call_openai(valid_single_meeting_output):
    """
    Patch call_llm inside workers to return a valid OpenAIResponse.
    Use as a context manager or via pytest fixture injection.
    """
    response = _make_openai_response(valid_single_meeting_output)
    with patch("backend.core.workers.call_llm", return_value=response) as mock:
        yield mock


@pytest.fixture
def mock_call_openai_raw():
    """call_llm mock without pre-configured output — configure per-test."""
    with patch("backend.core.workers.call_llm") as mock:
        yield mock
