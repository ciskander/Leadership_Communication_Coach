"""
test_gate1_validator.py — Tests for Gate1 validation: valid outputs pass,
mutated/invalid outputs fail with correct error codes.
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
# Coaching output cardinality failures
# ---------------------------------------------------------------------------

def test_focus_must_be_exactly_one(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching_output"]["focus"] = []  # zero items
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_focus_two_items_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    focus_item = bad["coaching_output"]["focus"][0]
    bad["coaching_output"]["focus"] = [focus_item, focus_item]  # two items
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_micro_experiment_must_be_exactly_one(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching_output"]["micro_experiment"] = []
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_strengths_max_two(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    strength = bad["coaching_output"]["strengths"][0]
    bad["coaching_output"]["strengths"] = [strength] * 3
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
    bad["coaching_output"]["micro_experiment"][0]["experiment_id"] = "EXP-1"
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
# success_evidence_span_ids / rewrite consistency checks
# ---------------------------------------------------------------------------

def _make_output_with_oe(valid_single_meeting_output):
    """Build a test output with opportunity_events and success_evidence_span_ids
    on a tiered_rubric pattern (participation_management, idx=2).
    Uses ES-004 (turns 5-5, score 1.0) and ES-005 (turns 15-15, score 0.25).
    """
    out = copy.deepcopy(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]  # participation_management
    pm["score"] = 0.625
    pm["opportunity_count"] = 2
    pm["opportunity_events_considered"] = 2
    pm["opportunity_events_counted"] = 2
    pm["success_evidence_span_ids"] = ["ES-004"]
    pm["opportunity_events"] = [
        {
            "event_id": "OE-001",
            "turn_start_id": 5,
            "turn_end_id": 5,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 1.0,
            "reason_code": "named_invitation",
        },
        {
            "event_id": "OE-002",
            "turn_start_id": 15,
            "turn_end_id": 15,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 0.25,
            "reason_code": "generic_open_floor",
        },
    ]
    return out


def test_success_span_missing_warns(valid_single_meeting_output):
    """A span with OE score 1.0 not in success_evidence_span_ids triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Remove ES-004 (score 1.0) from success list
    pm["success_evidence_span_ids"] = []
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_MISSING" in codes


def test_success_span_incorrect_warns(valid_single_meeting_output):
    """A span with OE score 0.25 in success_evidence_span_ids triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Add ES-005 (score 0.25) to success list
    pm["success_evidence_span_ids"] = ["ES-004", "ES-005"]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes


def test_success_span_correct_no_warning(valid_single_meeting_output):
    """Correctly classified spans produce no success consistency warnings."""
    out = _make_output_with_oe(valid_single_meeting_output)
    # ES-004 (1.0) in success, ES-005 (0.25) not — correct
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_MISSING" not in codes
    assert "SUCCESS_SPAN_INCORRECT" not in codes


def test_rewrite_targets_success_warns(valid_single_meeting_output):
    """rewrite_for_span_id pointing at a high-scored span triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Rewrite targets ES-004 (score 1.0) — should be a missed opportunity
    pm["rewrite_for_span_id"] = "ES-004"
    pm["suggested_rewrite"] = "Bob, what's your take on the Q2 projections?"
    pm["coaching_note"] = "Test coaching note."
    # Must remove ES-004 from success list (workers.py would do this)
    pm["success_evidence_span_ids"] = []
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_TARGETS_SUCCESS" in codes


def test_rewrite_content_mismatch_warns(valid_single_meeting_output):
    """Zero content word overlap between rewrite and excerpt triggers warning."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # Rewrite targets ES-005 (turns 15-15, about risk analysis)
    pm["rewrite_for_span_id"] = "ES-005"
    pm["success_evidence_span_ids"] = ["ES-004"]
    pm["coaching_note"] = "Test coaching note."
    # Rewrite text about a completely different topic (pricing/budget)
    pm["suggested_rewrite"] = (
        "We should finalize the pricing tiers and overage threshold "
        "before the finance review on Friday."
    )
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_CONTENT_MISMATCH" in codes


def test_rewrite_content_match_no_warning(valid_single_meeting_output):
    """Rewrite sharing topic words with excerpt does not trigger mismatch."""
    out = _make_output_with_oe(valid_single_meeting_output)
    pm = out["pattern_snapshot"][2]
    # ES-005 excerpt is "Carol, can you walk us through the risk analysis?"
    pm["rewrite_for_span_id"] = "ES-005"
    pm["success_evidence_span_ids"] = ["ES-004"]
    pm["coaching_note"] = "Test coaching note."
    # Rewrite shares topic words: "Carol", "risk", "analysis"
    pm["suggested_rewrite"] = (
        "Carol, before we move on I'd like your risk analysis "
        "perspective on this proposal."
    )
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "REWRITE_CONTENT_MISMATCH" not in codes


def test_success_threshold_binary_requires_1_0(valid_single_meeting_output):
    """For binary scoring, only success=1.0 qualifies as success."""
    out = copy.deepcopy(valid_single_meeting_output)
    qq = out["pattern_snapshot"][6]  # question_quality (binary)
    qq["score"] = 0.5
    qq["opportunity_count"] = 2
    qq["opportunity_events_considered"] = 2
    qq["opportunity_events_counted"] = 2
    qq["evidence_span_ids"] = ["ES-008", "ES-009"]
    # ES-009 scored 0.0 but listed as success — wrong for binary
    qq["success_evidence_span_ids"] = ["ES-008", "ES-009"]
    qq["opportunity_events"] = [
        {
            "event_id": "OE-010",
            "turn_start_id": 25,
            "turn_end_id": 25,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 1.0,
            "reason_code": "decision_linked_question",
        },
        {
            "event_id": "OE-011",
            "turn_start_id": 30,
            "turn_end_id": 30,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 0.0,
            "reason_code": "generic_question",
        },
    ]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes


def test_success_threshold_dual_element_requires_1_0(valid_single_meeting_output):
    """For dual_element scoring, success=0.5 (one element only) is not a success."""
    out = copy.deepcopy(valid_single_meeting_output)
    ra = out["pattern_snapshot"][4]  # resolution_and_alignment (dual_element)
    ra["score"] = 0.5
    ra["opportunity_count"] = 2
    ra["element_a_count"] = 2
    ra["element_b_count"] = 0
    ra["opportunity_events_considered"] = 2
    ra["opportunity_events_counted"] = 2
    ra["evidence_span_ids"] = ["ES-006", "ES-007"]
    # ES-006 scored 0.5 but listed as success — wrong for dual_element
    ra["success_evidence_span_ids"] = ["ES-006"]
    ra["opportunity_events"] = [
        {
            "event_id": "OE-020",
            "turn_start_id": 20,
            "turn_end_id": 21,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 0.5,
            "reason_code": "named_resolution_without_alignment_check",
        },
        {
            "event_id": "OE-021",
            "turn_start_id": 22,
            "turn_end_id": 22,
            "target_control": "yes",
            "count_decision": "counted",
            "success": 0.5,
            "reason_code": "named_resolution_without_alignment_check",
        },
    ]
    result = validate(json.dumps(out))
    codes = {i.issue_code for i in result.issues}
    assert "SUCCESS_SPAN_INCORRECT" in codes
