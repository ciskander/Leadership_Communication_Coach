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
