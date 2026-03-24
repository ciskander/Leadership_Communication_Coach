"""
test_gate1_validator.py — Tests for Gate1 validation: valid outputs pass,
mutated/invalid outputs fail with correct error codes.

Updated for v0.4.0 schema: top-level OEs, scoring-only pattern_snapshot,
unified coaching section.
"""
from __future__ import annotations

import copy
import json

import pytest

from backend.core.gate1_validator import validate
from backend.core.models import Gate1Result


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_output_passes(valid_single_meeting_json):
    result = validate(valid_single_meeting_json)
    assert isinstance(result, Gate1Result)
    assert result.passed is True
    assert len([i for i in result.issues if i.severity == "error"]) == 0


def test_gate1_result_has_no_errors_for_valid_output(valid_single_meeting_output):
    raw = json.dumps(valid_single_meeting_output)
    result = validate(raw)
    error_codes = {i.issue_code for i in result.issues if i.severity == "error"}
    assert len(error_codes) == 0


# ---------------------------------------------------------------------------
# Top-level structure failures
# ---------------------------------------------------------------------------

def test_missing_required_top_level_key_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    del bad["evidence_spans"]
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_wrong_schema_version_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["schema_version"] = "mvp.v0.1.0"
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_invalid_json_fails():
    result = validate("{ this is not valid JSON }")
    assert result.passed is False


def test_empty_string_fails():
    result = validate("")
    assert result.passed is False


# ---------------------------------------------------------------------------
# Pattern snapshot failures
# ---------------------------------------------------------------------------

def test_wrong_pattern_count_fails(valid_single_meeting_output):
    """Removing a pattern should cause failure (must have exactly 9)."""
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["pattern_snapshot"] = bad["pattern_snapshot"][:8]
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_wrong_pattern_order_fails(valid_single_meeting_output):
    """Swapping two patterns violates the required order."""
    bad = copy.deepcopy(valid_single_meeting_output)
    snap = bad["pattern_snapshot"]
    snap[0], snap[1] = snap[1], snap[0]  # swap purposeful_framing and focus_management
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_invalid_pattern_id_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["pattern_snapshot"][0]["pattern_id"] = "made_up_pattern"
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_numeric_pattern_missing_score_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    # Find first evaluable pattern and remove its score
    for p in bad["pattern_snapshot"]:
        if p.get("evaluable_status") == "evaluable":
            del p["score"]
            break
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_score_exceeds_one_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    for p in bad["pattern_snapshot"]:
        if p.get("evaluable_status") == "evaluable":
            p["score"] = 1.5  # score must be <= 1.0
            break
    result = validate(json.dumps(bad))
    assert result.passed is False


# ---------------------------------------------------------------------------
# Coaching cardinality failures (v0.4.0: coaching section, not coaching_output)
# ---------------------------------------------------------------------------

def test_focus_must_be_exactly_one(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching"]["focus"] = []  # zero items
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_focus_two_items_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    focus_item = bad["coaching"]["focus"][0]
    bad["coaching"]["focus"] = [focus_item, focus_item]  # two items
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_micro_experiment_must_be_exactly_one(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching"]["micro_experiment"] = []
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_strengths_max_two(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    strength = bad["coaching"]["strengths"][0]
    bad["coaching"]["strengths"] = [strength] * 3
    result = validate(json.dumps(bad))
    assert result.passed is False


# ---------------------------------------------------------------------------
# Evidence span failures
# ---------------------------------------------------------------------------

def test_evidence_span_turn_id_must_be_integer(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["evidence_spans"][0]["turn_start_id"] = "T-001"  # string, not integer
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_evidence_span_id_format(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["evidence_spans"][0]["evidence_span_id"] = "SPAN-1"  # wrong format
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_evidence_span_missing_excerpt_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    del bad["evidence_spans"][0]["excerpt"]
    result = validate(json.dumps(bad))
    assert result.passed is False


# ---------------------------------------------------------------------------
# ID format failures
# ---------------------------------------------------------------------------

def test_bad_analysis_id_format_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["meta"]["analysis_id"] = "A-99"  # too short
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_bad_experiment_id_format_sanitised(valid_single_meeting_output):
    """Sanitiser auto-corrects short experiment IDs (EXP-1 → EXP-000001), so gate1 passes."""
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching"]["micro_experiment"][0]["experiment_id"] = "EXP-1"
    result = validate(json.dumps(bad))
    assert result.passed is True


# ---------------------------------------------------------------------------
# Extra / forbidden keys
# ---------------------------------------------------------------------------

def test_forbidden_key_confidence_sanitised(valid_single_meeting_output):
    """Sanitiser strips forbidden keys like 'confidence', so gate1 passes."""
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["confidence"] = 0.99
    result = validate(json.dumps(bad))
    assert result.passed is True


# ---------------------------------------------------------------------------
# success_evidence_span_ids / rewrite consistency checks (v0.4.0)
#
# In v0.4.0: OEs are top-level, rewrite fields are in coaching.pattern_coaching.
# ---------------------------------------------------------------------------

def _make_output_with_oe(valid_single_meeting_output):
    """Build a test output with mixed success scores on participation_management.

    Modifies OE-006 (turns 15-15) from success=1.0 to success=0.25.
    ES-T005 (event_ids=["OE-005"], success=1.0) → success span.
    ES-T015 (event_ids=["OE-006"], success=0.25) → missed opportunity.
    """
    out = copy.deepcopy(valid_single_meeting_output)

    # Modify top-level OEs: change OE-006 success from 1.0 to 0.25
    for oe in out["opportunity_events"]:
        if oe["event_id"] == "OE-006":
            oe["success"] = 0.25
            oe["reason_code"] = "generic_open_floor"
            break

    # Update pattern_snapshot[2] (participation_management) — scoring only
    pm = out["pattern_snapshot"][2]
    pm["score"] = 0.625  # (1.0 + 0.25) / 2
    pm["success_evidence_span_ids"] = ["ES-T005"]  # Only OE-005 (1.0) >= 0.75 threshold

    return out


def test_success_span_missing_warns(valid_single_meeting_output):
    """A span with OE score 1.0 not in success_evidence_span_ids triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Remove ES-T005 (score 1.0) from success list
    pm["success_evidence_span_ids"] = []
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_MISSING" in codes


def test_success_span_incorrect_warns(valid_single_meeting_output):
    """A span with OE score 0.25 in success_evidence_span_ids triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Add ES-T015 (score 0.25) to success list — incorrect for tiered_rubric
    pm["success_evidence_span_ids"] = ["ES-T005", "ES-T015"]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes


def test_success_span_correct_no_warning(valid_single_meeting_output):
    """Correctly classified spans produce no success consistency warnings."""
    out = _make_output_with_oe(valid_single_meeting_output)
    # ES-T005 (1.0) in success, ES-T015 (0.25) not — correct
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_MISSING" not in codes
    assert "SUCCESS_SPAN_INCORRECT" not in codes


def test_rewrite_targets_success_warns(valid_single_meeting_output):
    """rewrite_for_span_id pointing at a high-scored span triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    # Add pattern_coaching with rewrite targeting ES-T005 (success span, score 1.0)
    out["coaching"]["pattern_coaching"] = [
        {
            "pattern_id": "participation_management",
            "notes": "Good participation management overall.",
            "coaching_note": "Test coaching note.",
            "suggested_rewrite": "Bob, what's your take on the Q2 projections?",
            "rewrite_for_span_id": "ES-T005",
        }
    ]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_TARGETS_SUCCESS" in codes


def test_rewrite_content_mismatch_warns(valid_single_meeting_output):
    """Zero content word overlap between rewrite and excerpt triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    # Rewrite targets ES-T015 (Carol's risk analysis) but text about pricing/budget
    out["coaching"]["pattern_coaching"] = [
        {
            "pattern_id": "participation_management",
            "notes": "Good participation management overall.",
            "coaching_note": "Test coaching note.",
            "suggested_rewrite": (
                "We should finalize the pricing tiers and overage threshold "
                "before the finance review on Friday."
            ),
            "rewrite_for_span_id": "ES-T015",
        }
    ]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_CONTENT_MISMATCH" in codes


def test_rewrite_content_match_no_warning(valid_single_meeting_output):
    """Rewrite sharing topic words with excerpt does not trigger mismatch."""
    out = _make_output_with_oe(valid_single_meeting_output)
    # ES-T015 excerpt is "Carol, can you walk us through the risk analysis?"
    out["coaching"]["pattern_coaching"] = [
        {
            "pattern_id": "participation_management",
            "notes": "Good participation management overall.",
            "coaching_note": "Test coaching note.",
            "suggested_rewrite": (
                "Carol, before we move on I'd like your risk analysis "
                "perspective on this proposal."
            ),
            "rewrite_for_span_id": "ES-T015",
        }
    ]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_CONTENT_MISMATCH" not in codes


def test_success_threshold_binary_requires_1_0(valid_single_meeting_output):
    """For binary scoring, only success=1.0 qualifies as success."""
    out = copy.deepcopy(valid_single_meeting_output)

    # Add a second question_quality OE with score 0.0
    out["opportunity_events"].append({
        "event_id": "OE-013",
        "pattern_id": "question_quality",
        "turn_start_id": 35,
        "turn_end_id": 35,
        "target_control": "yes",
        "count_decision": "counted",
        "success": 0.0,
        "reason_code": "generic_question",
    })

    # Add corresponding evidence span
    out["evidence_spans"].append({
        "evidence_span_id": "ES-T035",
        "turn_start_id": 35,
        "turn_end_id": 35,
        "excerpt": "Did everyone get the calendar invite for next week?",
        "event_ids": ["OE-013"],
    })

    # Update question_quality pattern
    qq = out["pattern_snapshot"][6]
    qq["score"] = 0.5  # (1.0 + 0.0) / 2
    qq["opportunity_count"] = 2
    qq["evidence_span_ids"] = ["ES-T025", "ES-T035"]
    # ES-T035 (score 0.0) listed as success — wrong for binary
    qq["success_evidence_span_ids"] = ["ES-T025", "ES-T035"]

    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes


def test_success_threshold_dual_element_requires_1_0(valid_single_meeting_output):
    """For dual_element scoring, success=0.5 (one element only) is not a success."""
    out = copy.deepcopy(valid_single_meeting_output)

    # Change OE-008 (resolution_and_alignment) success from 1.0 to 0.5
    for oe in out["opportunity_events"]:
        if oe["event_id"] == "OE-008":
            oe["success"] = 0.5
            oe["reason_code"] = "named_resolution_without_alignment_check"
            break

    # Add a second resolution_and_alignment OE
    out["opportunity_events"].append({
        "event_id": "OE-013",
        "pattern_id": "resolution_and_alignment",
        "turn_start_id": 38,
        "turn_end_id": 39,
        "target_control": "yes",
        "count_decision": "counted",
        "success": 0.5,
        "reason_code": "named_resolution_without_alignment_check",
    })

    # Add evidence span
    out["evidence_spans"].append({
        "evidence_span_id": "ES-T038-039",
        "turn_start_id": 38,
        "turn_end_id": 39,
        "excerpt": "Let's go with option B for the rollout plan.",
        "event_ids": ["OE-013"],
    })

    # Update resolution_and_alignment pattern
    ra = out["pattern_snapshot"][4]
    ra["score"] = 0.5  # (0.5 + 0.5) / 2
    ra["opportunity_count"] = 2
    ra["element_a_count"] = 2
    ra["element_b_count"] = 0
    ra["evidence_span_ids"] = ["ES-T020-021", "ES-T038-039"]
    # ES-T020-021 has OE-008 score 0.5, listed as success — wrong for dual_element
    ra["success_evidence_span_ids"] = ["ES-T020-021"]

    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes


# ---------------------------------------------------------------------------
# OPP_COUNT_COUNTED_MISMATCH: baseline_pack skip
# ---------------------------------------------------------------------------

def test_opp_count_mismatch_skipped_for_baseline_pack(valid_single_meeting_output):
    """OPP_COUNT_COUNTED_MISMATCH must NOT fire for baseline_pack analysis type."""
    out = copy.deepcopy(valid_single_meeting_output)
    out["meta"]["analysis_type"] = "baseline_pack"

    # Simulate baseline_pack stripping: clear evidence arrays but keep opportunity_count
    out["evidence_spans"] = []
    out["opportunity_events"] = []
    for ps in out["pattern_snapshot"]:
        ps["evidence_span_ids"] = []
        ps["success_evidence_span_ids"] = []
        # opportunity_count stays non-zero (e.g. aggregate from sub-runs)

    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "OPP_COUNT_COUNTED_MISMATCH" not in codes


def test_opp_count_mismatch_fires_for_single_meeting(valid_single_meeting_output):
    """OPP_COUNT_COUNTED_MISMATCH fires for single_meeting when count is wrong."""
    out = copy.deepcopy(valid_single_meeting_output)
    # Set wrong opportunity_count on first evaluable pattern
    out["pattern_snapshot"][0]["opportunity_count"] = 99
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "OPP_COUNT_COUNTED_MISMATCH" in codes


# ---------------------------------------------------------------------------
# Gate1FailureError is non-retryable
# ---------------------------------------------------------------------------

def test_gate1_failure_error_is_not_retryable():
    """Gate1FailureError must be classified as non-retryable by _is_retryable."""
    import importlib
    import sys
    from unittest.mock import MagicMock

    # The tasks module imports anthropic at module level; stub it if unavailable.
    if "anthropic" not in sys.modules:
        sys.modules["anthropic"] = MagicMock()

    from backend.queue.tasks import _is_retryable
    from backend.core.models import Gate1FailureError

    assert _is_retryable(Gate1FailureError("Run failed Gate1")) is False


# ---------------------------------------------------------------------------
# Baseline score auto-correction
# ---------------------------------------------------------------------------

def _make_slim_snapshot(pattern_id, score, opportunity_count, evaluable_status="evaluable"):
    return {
        "pattern_id": pattern_id,
        "cluster_id": "test",
        "scoring_type": "tiered_rubric",
        "evaluable_status": evaluable_status,
        "score": score,
        "opportunity_count": opportunity_count,
    }


def test_baseline_score_autocorrected():
    """Weighted average mismatch triggers BASELINE_SCORE_AUTOCORRECTED."""
    from backend.core.workers import _auto_correct_baseline_scores

    parsed = {
        "pattern_snapshot": [
            {
                "pattern_id": "focus_management",
                "evaluable_status": "evaluable",
                "score": 0.9999,  # wrong — should be 0.7
                "opportunity_count": 8,
            }
        ]
    }
    meeting_run_data = [
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.6, 5),
        ]}},
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.8, 3),
        ]}},
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.5, 0, "insufficient_signal"),
        ]}},
    ]
    issues = _auto_correct_baseline_scores(parsed, meeting_run_data)
    codes = {i.issue_code for i in issues}
    assert "BASELINE_SCORE_AUTOCORRECTED" in codes
    # Expected: (0.6*5 + 0.8*3) / (5+3) = 5.4/8 = 0.675
    assert parsed["pattern_snapshot"][0]["score"] == 0.675


def test_baseline_opp_count_autocorrected():
    """Opportunity count sum mismatch triggers BASELINE_OPP_COUNT_AUTOCORRECTED."""
    from backend.core.workers import _auto_correct_baseline_scores

    parsed = {
        "pattern_snapshot": [
            {
                "pattern_id": "focus_management",
                "evaluable_status": "evaluable",
                "score": 0.675,
                "opportunity_count": 99,  # wrong — should be 8
            }
        ]
    }
    meeting_run_data = [
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.6, 5),
        ]}},
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.8, 3),
        ]}},
    ]
    issues = _auto_correct_baseline_scores(parsed, meeting_run_data)
    codes = {i.issue_code for i in issues}
    assert "BASELINE_OPP_COUNT_AUTOCORRECTED" in codes
    assert parsed["pattern_snapshot"][0]["opportunity_count"] == 8


def test_baseline_score_correct_no_correction():
    """Correct weighted average produces no correction issues."""
    from backend.core.workers import _auto_correct_baseline_scores

    parsed = {
        "pattern_snapshot": [
            {
                "pattern_id": "focus_management",
                "evaluable_status": "evaluable",
                "score": 0.675,
                "opportunity_count": 8,
            }
        ]
    }
    meeting_run_data = [
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.6, 5),
        ]}},
        {"slim_summary": {"pattern_snapshot": [
            _make_slim_snapshot("focus_management", 0.8, 3),
        ]}},
    ]
    issues = _auto_correct_baseline_scores(parsed, meeting_run_data)
    assert len(issues) == 0
