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
    """Removing a pattern should cause failure (must have exactly 10)."""
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["pattern_snapshot"] = bad["pattern_snapshot"][:9]
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_wrong_pattern_order_fails(valid_single_meeting_output):
    """Swapping two patterns violates the required order."""
    bad = copy.deepcopy(valid_single_meeting_output)
    snap = bad["pattern_snapshot"]
    snap[0], snap[1] = snap[1], snap[0]  # swap agenda_clarity and objective_signaling
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_invalid_pattern_id_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["pattern_snapshot"][0]["pattern_id"] = "made_up_pattern"
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_numeric_pattern_missing_ratio_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    # Find first evaluable numeric pattern
    for p in bad["pattern_snapshot"]:
        if p.get("evaluable_status") == "evaluable" and p["pattern_id"] != "conversational_balance":
            del p["ratio"]
            break
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_numerator_exceeds_denominator_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    for p in bad["pattern_snapshot"]:
        if p.get("evaluable_status") == "evaluable" and p["pattern_id"] != "conversational_balance":
            p["numerator"] = p["denominator"] + 1
            p["ratio"] = round(p["numerator"] / p["denominator"], 4)
            break
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_conversational_balance_must_not_have_ratio(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    for p in bad["pattern_snapshot"]:
        if p["pattern_id"] == "conversational_balance":
            p["ratio"] = 0.5  # should not be present
            break
    result = validate(json.dumps(bad))
    assert result.passed is False


def test_conversational_balance_missing_balance_assessment_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    for p in bad["pattern_snapshot"]:
        if p["pattern_id"] == "conversational_balance":
            del p["balance_assessment"]
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


def test_bad_experiment_id_format_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["coaching_output"]["micro_experiment"][0]["experiment_id"] = "EXP-1"
    result = validate(json.dumps(bad))
    assert result.passed is False


# ---------------------------------------------------------------------------
# Extra / forbidden keys
# ---------------------------------------------------------------------------

def test_forbidden_key_confidence_fails(valid_single_meeting_output):
    bad = copy.deepcopy(valid_single_meeting_output)
    bad["confidence"] = 0.99
    result = validate(json.dumps(bad))
    assert result.passed is False
