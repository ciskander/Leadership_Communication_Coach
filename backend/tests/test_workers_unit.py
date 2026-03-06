"""
test_workers_unit.py — Unit tests for pure helper functions and the inline
pattern-snapshot patching logic in workers.py.

These tests have zero external dependencies (no Airtable, no OpenAI) and
should always be fast and deterministic.
"""
from __future__ import annotations

import copy
import json

import pytest

from backend.core.workers import (
    _extract_fields,
    _get_link_ids,
    _get_str,
    _extract_coaching_from_run,
    _build_slim_meeting_summary,
    _safe_json_dumps,
)


# ── _extract_fields ───────────────────────────────────────────────────────────

class TestExtractFields:
    def test_returns_fields_dict(self):
        record = {"id": "rec_001", "fields": {"Name": "Alice"}}
        assert _extract_fields(record) == {"Name": "Alice"}

    def test_missing_fields_key_returns_empty_dict(self):
        assert _extract_fields({}) == {}

    def test_none_fields_key_returns_empty_dict(self):
        assert _extract_fields({"id": "rec_001"}) == {}


# ── _get_link_ids ─────────────────────────────────────────────────────────────

class TestGetLinkIds:
    def test_returns_list_of_record_ids(self):
        fields = {"Transcript": ["rec_tr_001", "rec_tr_002"]}
        assert _get_link_ids(fields, "Transcript") == ["rec_tr_001", "rec_tr_002"]

    def test_missing_key_returns_empty_list(self):
        assert _get_link_ids({}, "Transcript") == []

    def test_non_list_value_returns_empty_list(self):
        # Airtable occasionally returns None for an empty link field
        assert _get_link_ids({"Transcript": None}, "Transcript") == []

    def test_single_item_list(self):
        fields = {"User": ["rec_user_001"]}
        assert _get_link_ids(fields, "User") == ["rec_user_001"]

    def test_empty_list_returns_empty_list(self):
        assert _get_link_ids({"Transcript": []}, "Transcript") == []


# ── _get_str ──────────────────────────────────────────────────────────────────

class TestGetStr:
    def test_returns_string_value(self):
        assert _get_str({"Name": "Alice"}, "Name") == "Alice"

    def test_list_value_returns_first_element_as_string(self):
        assert _get_str({"IDs": ["rec_001", "rec_002"]}, "IDs") == "rec_001"

    def test_missing_key_returns_none(self):
        assert _get_str({}, "Name") is None

    def test_none_value_returns_none(self):
        assert _get_str({"Name": None}, "Name") is None

    def test_integer_value_coerced_to_string(self):
        result = _get_str({"Count": 5}, "Count")
        assert result == "5"


# ── _safe_json_dumps ──────────────────────────────────────────────────────────

class TestSafeJsonDumps:
    def test_serialises_dict(self):
        result = _safe_json_dumps({"key": "value"})
        assert json.loads(result) == {"key": "value"}

    def test_handles_non_ascii(self):
        result = _safe_json_dumps({"name": "André"})
        parsed = json.loads(result)
        assert parsed["name"] == "André"

    def test_ensure_ascii_false(self):
        # Characters should not be escaped as \\uXXXX
        result = _safe_json_dumps({"emoji": "✓"})
        assert "✓" in result


# ── _extract_coaching_from_run ────────────────────────────────────────────────

class TestExtractCoachingFromRun:
    def _make_parsed_json(
        self,
        focus_pattern="decision_closure",
        micro_pattern="decision_closure",
        micro_exp_id="EXP-000001",
        strengths_patterns=("agenda_clarity",),
    ) -> dict:
        return {
            "coaching_output": {
                "strengths": [{"pattern_id": p, "message": "Good."} for p in strengths_patterns],
                "focus": [{"pattern_id": focus_pattern, "message": "Improve this."}],
                "micro_experiment": [
                    {
                        "experiment_id": micro_exp_id,
                        "title": "Test experiment",
                        "instruction": "Do the thing.",
                        "success_marker": "Did the thing.",
                        "pattern_id": micro_pattern,
                    }
                ],
            }
        }

    def test_extracts_focus_pattern(self):
        result = _extract_coaching_from_run(self._make_parsed_json())
        assert result["focus_pattern"] == "decision_closure"

    def test_extracts_micro_experiment_pattern(self):
        result = _extract_coaching_from_run(self._make_parsed_json())
        assert result["micro_experiment_pattern"] == "decision_closure"

    def test_extracts_experiment_id(self):
        result = _extract_coaching_from_run(self._make_parsed_json(micro_exp_id="EXP-000042"))
        assert result["experiment_id"] == "EXP-000042"

    def test_extracts_strengths_as_json_array(self):
        result = _extract_coaching_from_run(
            self._make_parsed_json(strengths_patterns=("agenda_clarity", "summary_checkback"))
        )
        strengths = json.loads(result["strengths_patterns"])
        assert strengths == ["agenda_clarity", "summary_checkback"]

    def test_empty_focus_returns_none(self):
        parsed = {"coaching_output": {"strengths": [], "focus": [], "micro_experiment": []}}
        result = _extract_coaching_from_run(parsed)
        assert result["focus_pattern"] is None

    def test_empty_micro_experiment_returns_none(self):
        parsed = {"coaching_output": {"strengths": [], "focus": [], "micro_experiment": []}}
        result = _extract_coaching_from_run(parsed)
        assert result["experiment_id"] is None

    def test_missing_coaching_output_returns_nones(self):
        result = _extract_coaching_from_run({})
        assert result["focus_pattern"] is None
        assert result["experiment_id"] is None


# ── _build_slim_meeting_summary ───────────────────────────────────────────────

class TestBuildSlimMeetingSummary:
    def _make_inputs(self) -> tuple[dict, dict]:
        run_fields = {
            "Target Speaker Name": "Alice",
            "Target Speaker Label": "Alice",
        }
        parsed_json = {
            "meta": {"analysis_id": "A-000001"},
            "context": {
                "meeting_id": "M-000001",
                "meeting_type": "exec_staff",
                "target_role": "chair",
            },
            "evaluation_summary": {"score": 0.8},
            "pattern_snapshot": [
                {
                    "pattern_id": "agenda_clarity",
                    "evaluable_status": "evaluable",
                    "numerator": 2,
                    "denominator": 2,
                    "ratio": 1.0,
                    "balance_assessment": None,
                }
            ],
            "coaching_output": {
                "focus": [{"pattern_id": "decision_closure", "message": "Improve."}],
                "micro_experiment": [
                    {
                        "title": "Close decisions",
                        "instruction": "Say it aloud.",
                        "pattern_id": "decision_closure",
                    }
                ],
            },
        }
        return run_fields, parsed_json

    def test_returns_dict(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert isinstance(result, dict)

    def test_includes_meeting_id(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["meeting_id"] == "M-000001"

    def test_includes_meeting_type(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["meeting_type"] == "exec_staff"

    def test_includes_target_role(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["target_role"] == "chair"

    def test_includes_speaker_name(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["target_speaker_name"] == "Alice"

    def test_pattern_snapshot_is_slimmed(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        snap = result["pattern_snapshot"]
        assert isinstance(snap, list)
        assert len(snap) == 1
        # Only key fields should be present in the slim version
        assert "pattern_id" in snap[0]
        assert "evaluable_status" in snap[0]
        # Full evidence_span_ids should NOT appear in slim snapshot
        assert "evidence_span_ids" not in snap[0]

    def test_coaching_compact_includes_focus_pattern(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["coaching_output_compact"]["focus_pattern_id"] == "decision_closure"

    def test_coaching_compact_includes_micro_experiment_title(self):
        run_fields, parsed_json = self._make_inputs()
        result = _build_slim_meeting_summary(run_fields, parsed_json)
        assert result["coaching_output_compact"]["micro_experiment_title"] == "Close decisions"

    def test_empty_parsed_json_does_not_raise(self):
        result = _build_slim_meeting_summary({}, {})
        assert result["meeting_id"] is None
        assert result["pattern_snapshot"] == []


# ── Pattern snapshot patching logic ──────────────────────────────────────────
#
# The patching logic is currently inlined inside process_single_meeting_analysis
# and process_baseline_pack_build. These tests drive out the correct behaviour
# and will serve as a contract for when this logic is extracted into a
# standalone _patch_parsed_output() function.
#
# To make these runnable today without refactoring, we duplicate the logic
# into a local helper that mirrors exactly what the workers do. Once extracted,
# replace the local helper with an import.
# ─────────────────────────────────────────────────────────────────────────────

from backend.core.workers import _patch_parsed_output as _apply_snapshot_patches


class TestSnapshotPatching:
    """
    Tests for the pattern snapshot patching logic.
    This logic has caused production bugs twice — keep these thorough.
    """

    def _snap(self, pattern_id="agenda_clarity", evaluable_status="evaluable", **kwargs) -> dict:
        base = {
            "pattern_id": pattern_id,
            "evaluable_status": evaluable_status,
            "denominator_rule_id": "some_rule",
            "min_required_threshold": 1,
        }
        base.update(kwargs)
        return base

    # ── conversational_balance stripping ─────────────────────────────────────

    def test_conversational_balance_ratio_stripped(self):
        parsed = {"pattern_snapshot": [
            self._snap("conversational_balance", numerator=3, denominator=5, ratio=0.6)
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert "ratio" not in snap
        assert "numerator" not in snap
        assert "denominator" not in snap

    def test_conversational_balance_opportunity_count_stripped(self):
        parsed = {"pattern_snapshot": [
            self._snap("conversational_balance", opportunity_count=10)
        ]}
        result = _apply_snapshot_patches(parsed)
        assert "opportunity_count" not in result["pattern_snapshot"][0]

    def test_conversational_balance_opportunity_events_stripped(self):
        parsed = {"pattern_snapshot": [
            self._snap("conversational_balance",
                       opportunity_events=["e1"],
                       opportunity_events_considered=["e1"],
                       opportunity_events_counted=["e1"])
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert "opportunity_events" not in snap
        assert "opportunity_events_considered" not in snap
        assert "opportunity_events_counted" not in snap

    def test_other_patterns_ratio_not_stripped(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", numerator=2, denominator=3, ratio=0.67)
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert snap["ratio"] == 0.67

    # ── zero-denominator coercion ─────────────────────────────────────────────

    def test_zero_denominator_evaluable_coerced_to_insufficient_signal(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", numerator=0, denominator=0, ratio=0.0)
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert snap["evaluable_status"] == "insufficient_signal"

    def test_zero_denominator_strips_numeric_fields(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", numerator=0, denominator=0, ratio=0.0)
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert "numerator" not in snap
        assert "denominator" not in snap
        assert "ratio" not in snap

    def test_zero_denominator_conversational_balance_not_coerced(self):
        """conversational_balance is exempt from zero-denominator coercion."""
        parsed = {"pattern_snapshot": [
            self._snap("conversational_balance", evaluable_status="evaluable")
        ]}
        result = _apply_snapshot_patches(parsed)
        snap = result["pattern_snapshot"][0]
        assert snap["evaluable_status"] == "evaluable"

    def test_nonzero_denominator_not_coerced(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", numerator=1, denominator=3, ratio=0.33)
        ]}
        result = _apply_snapshot_patches(parsed)
        assert result["pattern_snapshot"][0]["evaluable_status"] == "evaluable"

    def test_already_insufficient_signal_not_double_coerced(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", evaluable_status="insufficient_signal")
        ]}
        result = _apply_snapshot_patches(parsed)
        assert result["pattern_snapshot"][0]["evaluable_status"] == "insufficient_signal"

    # ── denominator_rule_id backfill ─────────────────────────────────────────

    def test_null_denominator_rule_id_backfilled(self):
        parsed = {"pattern_snapshot": [
            {
                "pattern_id": "agenda_clarity",
                "evaluable_status": "not_evaluable",
                "denominator_rule_id": None,
                "min_required_threshold": 1,
            }
        ]}
        result = _apply_snapshot_patches(parsed)
        assert result["pattern_snapshot"][0]["denominator_rule_id"] == "not_evaluable"

    def test_existing_denominator_rule_id_not_overwritten(self):
        parsed = {"pattern_snapshot": [
            self._snap("agenda_clarity", denominator_rule_id="my_rule")
        ]}
        result = _apply_snapshot_patches(parsed)
        assert result["pattern_snapshot"][0]["denominator_rule_id"] == "my_rule"

    # ── denominator_rule_id and min_required_threshold backfill ──────────────

    def test_missing_denominator_rule_id_backfilled_with_default(self):
        parsed = {"pattern_snapshot": [
            {
                "pattern_id": "agenda_clarity",
                "evaluable_status": "evaluable",
                "numerator": 1,
                "denominator": 2,
                "ratio": 0.5,
            }
        ]}
        result = _apply_snapshot_patches(parsed)
        assert "denominator_rule_id" in result["pattern_snapshot"][0]

    def test_missing_min_required_threshold_backfilled(self):
        parsed = {"pattern_snapshot": [
            {
                "pattern_id": "agenda_clarity",
                "evaluable_status": "evaluable",
                "numerator": 1,
                "denominator": 2,
                "ratio": 0.5,
                "denominator_rule_id": "my_rule",
            }
        ]}
        result = _apply_snapshot_patches(parsed)
        assert "min_required_threshold" in result["pattern_snapshot"][0]

    # ── experiment_tracking coercion ─────────────────────────────────────────

    def test_assigned_status_coerced_to_proposed(self):
        parsed = {
            "pattern_snapshot": [],
            "experiment_tracking": {
                "active_experiment": {"experiment_id": "EXP-000001", "status": "assigned"},
                "detection_in_this_meeting": None,
            },
        }
        result = _apply_snapshot_patches(parsed)
        assert result["experiment_tracking"]["active_experiment"]["status"] == "proposed"

    def test_active_status_not_coerced(self):
        parsed = {
            "pattern_snapshot": [],
            "experiment_tracking": {
                "active_experiment": {"experiment_id": "EXP-000001", "status": "active"},
            },
        }
        result = _apply_snapshot_patches(parsed)
        assert result["experiment_tracking"]["active_experiment"]["status"] == "active"

    # ── multiple patterns together ────────────────────────────────────────────

    def test_mixed_snapshot_patched_correctly(self):
        """Realistic snapshot with several patterns requiring different patches."""
        parsed = {"pattern_snapshot": [
            # Normal evaluable pattern — should be unchanged
            self._snap("agenda_clarity", numerator=2, denominator=3, ratio=0.67),
            # Zero denominator — should be coerced to insufficient_signal
            self._snap("decision_closure", numerator=0, denominator=0, ratio=0.0),
            # conversational_balance — numeric fields stripped
            self._snap("conversational_balance", numerator=5, denominator=10, ratio=0.5,
                       opportunity_count=10),
            # not_evaluable with null rule_id — should be backfilled
            {
                "pattern_id": "facilitative_inclusion",
                "evaluable_status": "not_evaluable",
                "denominator_rule_id": None,
                "min_required_threshold": 2,
            },
        ]}

        result = _apply_snapshot_patches(parsed)
        snaps = {s["pattern_id"]: s for s in result["pattern_snapshot"]}

        # agenda_clarity unchanged
        assert snaps["agenda_clarity"]["evaluable_status"] == "evaluable"
        assert snaps["agenda_clarity"]["ratio"] == 0.67

        # decision_closure coerced
        assert snaps["decision_closure"]["evaluable_status"] == "insufficient_signal"
        assert "ratio" not in snaps["decision_closure"]

        # conversational_balance stripped
        assert "ratio" not in snaps["conversational_balance"]
        assert "opportunity_count" not in snaps["conversational_balance"]

        # facilitative_inclusion backfilled
        assert snaps["facilitative_inclusion"]["denominator_rule_id"] == "not_evaluable"

    def test_empty_snapshot_does_not_raise(self):
        result = _apply_snapshot_patches({"pattern_snapshot": []})
        assert result["pattern_snapshot"] == []

    def test_patching_does_not_mutate_input(self):
        """Input dict should be untouched — patching must work on a deep copy."""
        original = {"pattern_snapshot": [
            self._snap("agenda_clarity", numerator=0, denominator=0, ratio=0.0)
        ]}
        import copy
        before = copy.deepcopy(original)
        _apply_snapshot_patches(original)
        assert original == before
