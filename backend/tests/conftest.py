"""
conftest.py — Shared fixtures for all backend tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_PATH = Path(__file__).parent.parent / "core" / "schema_version_mvp_v0_2_1.json"

# ---------------------------------------------------------------------------
# Minimal valid single-meeting OpenAI output (synthesised from the example)
# ---------------------------------------------------------------------------

VALID_SINGLE_MEETING_OUTPUT: dict[str, Any] = {
    "schema_version": "mvp.v0.2.1",
    "meta": {
        "analysis_id": "A-260227",
        "analysis_type": "single_meeting",
        "generated_at": "2026-02-27T15:32:50.638-05:00",
        "taxonomy_version": "v1.4",
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
    "evaluation_summary": {
        "patterns_evaluated": [
            "agenda_clarity",
            "objective_signaling",
            "turn_allocation",
            "decision_closure",
            "owner_timeframe_specification",
            "summary_checkback",
            "question_quality",
            "listener_response_quality",
            "conversational_balance",
        ],
        "patterns_insufficient_signal": [],
        "patterns_not_evaluable": ["facilitative_inclusion"],
    },
    "pattern_snapshot": [
        {
            "pattern_id": "agenda_clarity",
            "tier": 1,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_agenda_or_transition",
            "min_required_threshold": 1,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-001", "ES-002"],
        },
        {
            "pattern_id": "objective_signaling",
            "tier": 1,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_outcome_or_intent_statement",
            "min_required_threshold": 1,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-001", "ES-003"],
        },
        {
            "pattern_id": "turn_allocation",
            "tier": 2,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "direct_question_or_named_invite",
            "min_required_threshold": 1,
            "opportunity_count": 5,
            "numerator": 5,
            "denominator": 5,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-004", "ES-005"],
        },
        {
            "pattern_id": "facilitative_inclusion",
            "tier": 1,
            "evaluable_status": "not_evaluable",
            "denominator_rule_id": "facilitative_inclusion_chair",
            "min_required_threshold": 2,
            "evidence_span_ids": [],
        },
        {
            "pattern_id": "decision_closure",
            "tier": 1,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "explicit_decision_moment_chair",
            "min_required_threshold": 2,
            "opportunity_count": 3,
            "numerator": 3,
            "denominator": 3,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-006"],
        },
        {
            "pattern_id": "owner_timeframe_specification",
            "tier": 1,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "assignment_moment_chair",
            "min_required_threshold": 2,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-007"],
        },
        {
            "pattern_id": "summary_checkback",
            "tier": 1,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "transition_moment_chair",
            "min_required_threshold": 2,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-008"],
        },
        {
            "pattern_id": "question_quality",
            "tier": 2,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "question_to_target",
            "min_required_threshold": 2,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-009"],
        },
        {
            "pattern_id": "listener_response_quality",
            "tier": 2,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "question_to_target",
            "min_required_threshold": 2,
            "opportunity_count": 2,
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
            "evidence_span_ids": ["ES-010"],
        },
        {
            "pattern_id": "conversational_balance",
            "tier": 2,
            "evaluable_status": "evaluable",
            "denominator_rule_id": "speaker_word_share",
            "min_required_threshold": 1,
            "balance_assessment": "balanced",
            "evidence_span_ids": [],
        },
    ],
    "coaching_output": {
        "strengths": [
            {
                "pattern_id": "agenda_clarity",
                "message": "You consistently framed each topic with clear objectives.",
                "evidence_span_ids": ["ES-001"],
            }
        ],
        "focus": [
            {
                "pattern_id": "decision_closure",
                "message": "Try ending each decision moment with an explicit verbal closure.",
                "evidence_span_ids": ["ES-006"],
            }
        ],
        "micro_experiment": [
            {
                "experiment_id": "EXP-000001",
                "title": "Close every decision out loud",
                "instruction": "At the end of each agenda item, say aloud who owns the decision and what was decided.",
                "success_marker": "At least 2 out of 3 decision moments have explicit verbal closure in the next meeting.",
                "pattern_id": "decision_closure",
                "evidence_span_ids": ["ES-006"],
            }
        ],
    },
    "experiment_tracking": {
        "active_experiment": {"experiment_id": None, "status": "none"},
        "detection_in_this_meeting": None,
    },
    "evidence_spans": [
        {
            "evidence_span_id": "ES-001",
            "turn_start_id": 1,
            "turn_end_id": 2,
            "excerpt": "Alright, let's get started. Today we have three main items...",
        },
        {
            "evidence_span_id": "ES-002",
            "turn_start_id": 10,
            "turn_end_id": 11,
            "excerpt": "Moving to the second item on our agenda...",
        },
        {
            "evidence_span_id": "ES-003",
            "turn_start_id": 3,
            "turn_end_id": 3,
            "excerpt": "We need to decide on the budget allocation by end of this meeting.",
        },
        {
            "evidence_span_id": "ES-004",
            "turn_start_id": 5,
            "turn_end_id": 5,
            "excerpt": "Bob, what's your take on the Q2 projections?",
        },
        {
            "evidence_span_id": "ES-005",
            "turn_start_id": 15,
            "turn_end_id": 15,
            "excerpt": "Carol, can you walk us through the risk analysis?",
        },
        {
            "evidence_span_id": "ES-006",
            "turn_start_id": 20,
            "turn_end_id": 21,
            "excerpt": "So we're agreed: the budget is approved at 1.2M. Final decision.",
        },
        {
            "evidence_span_id": "ES-007",
            "turn_start_id": 22,
            "turn_end_id": 22,
            "excerpt": "Bob owns the vendor selection, due by Friday.",
        },
        {
            "evidence_span_id": "ES-008",
            "turn_start_id": 25,
            "turn_end_id": 25,
            "excerpt": "To recap: we've decided on the budget, Carol is on risk, Bob has vendor selection.",
        },
        {
            "evidence_span_id": "ES-009",
            "turn_start_id": 30,
            "turn_end_id": 30,
            "excerpt": "What are the key constraints we need to consider?",
        },
        {
            "evidence_span_id": "ES-010",
            "turn_start_id": 31,
            "turn_end_id": 32,
            "excerpt": "That's a good point. The main constraint is timeline, not budget.",
        },
    ],
}


@pytest.fixture
def valid_single_meeting_output() -> dict:
    """Return the canonical valid single-meeting output dict."""
    import copy
    return copy.deepcopy(VALID_SINGLE_MEETING_OUTPUT)


@pytest.fixture
def valid_single_meeting_json(valid_single_meeting_output) -> str:
    return json.dumps(valid_single_meeting_output)


# ---------------------------------------------------------------------------
# Mock Airtable client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_airtable():
    """Return a MagicMock that replaces AirtableClient."""
    with patch("backend.core.airtable_client.AirtableClient") as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance
        # Default return values for common methods
        instance.get_run_request.return_value = {
            "id": "rec_rr_001",
            "fields": {
                "Request ID": "rr-001",
                "Transcript Record ID": "rec_tr_001",
                "Target Speaker Name": "Alice",
                "Target Speaker Label": "Alice",
                "Target Role": "chair",
                "Analysis Type": "single_meeting",
                "Status": "queued",
                "Coachee User Record ID": "rec_user_001",
            },
        }
        instance.get_transcript.return_value = {
            "id": "rec_tr_001",
            "fields": {
                "Transcript ID": "T-000001",
                "Raw Text": "Alice: Let's get started.\nBob: Sounds good.",
                "Meeting Type": "exec_staff",
                "Meeting Date": "2026-02-12",
                "Speaker Labels": '["Alice", "Bob"]',
            },
        }
        instance.create_run.return_value = {
            "id": "rec_run_001",
            "fields": {"Run ID": "R-000001"},
        }
        instance.update_run.return_value = {"id": "rec_run_001"}
        instance.update_run_request_status.return_value = None
        yield instance


# ---------------------------------------------------------------------------
# Mock OpenAI client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_openai(valid_single_meeting_output):
    """Return a mock that makes OpenAI return the valid fixture output."""
    with patch("backend.core.openai_client.OpenAIClient") as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance
        instance.chat_completion.return_value = json.dumps(valid_single_meeting_output)
        yield instance


@pytest.fixture
def mock_openai_raw():
    """Return the mock OpenAI client without pre-configured output."""
    with patch("backend.core.openai_client.OpenAIClient") as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance
        yield instance
