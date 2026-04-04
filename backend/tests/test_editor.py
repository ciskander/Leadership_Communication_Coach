"""
test_editor.py — Unit tests for the coaching editor merge logic.

Tests the merge_editor_output function and its sub-operations:
- Delta-based coaching text edits
- OE removal and score recalculation
- Coaching discard for demoted patterns
- Span reference validation
- Top-level text edits (executive_summary, coaching_themes, etc.)
"""
from __future__ import annotations

import copy

import pytest

from backend.core.editor import merge_editor_output


# ---------------------------------------------------------------------------
# Test fixtures — minimal analysis output for merge testing
# ---------------------------------------------------------------------------

def _make_analysis_output() -> dict:
    """Build a minimal but complete analysis output for merge tests."""
    return {
        "schema_version": "mvp.v0.4.0",
        "meta": {
            "analysis_id": "A-000001",
            "analysis_type": "single_meeting",
            "generated_at": "2026-03-01T10:00:00Z",
        },
        "opportunity_events": [
            {
                "event_id": "OE-001",
                "pattern_id": "purposeful_framing",
                "turn_start_id": 1,
                "turn_end_id": 2,
                "target_control": "yes",
                "count_decision": "counted",
                "success": 1.0,
                "reason_code": "clear_framing",
            },
            {
                "event_id": "OE-002",
                "pattern_id": "purposeful_framing",
                "turn_start_id": 10,
                "turn_end_id": 11,
                "target_control": "yes",
                "count_decision": "counted",
                "success": 0.5,
                "reason_code": "partial_framing",
            },
            {
                "event_id": "OE-003",
                "pattern_id": "purposeful_framing",
                "turn_start_id": 15,
                "turn_end_id": 16,
                "target_control": "yes",
                "count_decision": "counted",
                "success": 0.0,
                "reason_code": "weak_framing",
            },
            {
                "event_id": "OE-004",
                "pattern_id": "focus_management",
                "turn_start_id": 3,
                "turn_end_id": 3,
                "target_control": "yes",
                "count_decision": "counted",
                "success": 0.75,
                "reason_code": "intent_stated",
            },
            {
                "event_id": "OE-005",
                "pattern_id": "communication_clarity",
                "turn_start_id": 20,
                "turn_end_id": 20,
                "target_control": "yes",
                "count_decision": "counted",
                "success": 1.0,
                "reason_code": "clear_response",
            },
        ],
        "evidence_spans": [
            {"evidence_span_id": "ES-T001-002", "turn_start_id": 1, "turn_end_id": 2, "excerpt": "Test span 1", "event_ids": ["OE-001"]},
            {"evidence_span_id": "ES-T010-011", "turn_start_id": 10, "turn_end_id": 11, "excerpt": "Test span 2", "event_ids": ["OE-002"]},
            {"evidence_span_id": "ES-T015-016", "turn_start_id": 15, "turn_end_id": 16, "excerpt": "Test span 3", "event_ids": ["OE-003"]},
            {"evidence_span_id": "ES-T003", "turn_start_id": 3, "turn_end_id": 3, "excerpt": "Test span 4", "event_ids": ["OE-004"]},
            {"evidence_span_id": "ES-T020", "turn_start_id": 20, "turn_end_id": 20, "excerpt": "Test span 5", "event_ids": ["OE-005"]},
        ],
        "pattern_snapshot": [
            {
                "pattern_id": "purposeful_framing",
                "cluster_id": "meeting_structure",
                "scoring_type": "tiered_rubric",
                "evaluable_status": "evaluable",
                "denominator_rule_id": "explicit_agenda_or_transition",
                "min_required_threshold": 1,
                "opportunity_count": 3,
                "score": 0.5,
                "evidence_span_ids": ["ES-T001-002", "ES-T010-011", "ES-T015-016"],
                "success_evidence_span_ids": ["ES-T001-002"],
            },
            {
                "pattern_id": "focus_management",
                "cluster_id": "meeting_structure",
                "scoring_type": "tiered_rubric",
                "evaluable_status": "evaluable",
                "denominator_rule_id": "explicit_outcome_or_intent_statement",
                "min_required_threshold": 1,
                "opportunity_count": 1,
                "score": 0.75,
                "evidence_span_ids": ["ES-T003"],
                "success_evidence_span_ids": ["ES-T003"],
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
                "evidence_span_ids": ["ES-T020"],
                "success_evidence_span_ids": ["ES-T020"],
            },
        ],
        "evaluation_summary": {
            "patterns_evaluated": ["purposeful_framing", "focus_management", "communication_clarity"],
            "patterns_insufficient_signal": [],
            "patterns_not_evaluable": [],
        },
        "experiment_tracking": {
            "active_experiment": {"experiment_id": "EXP-000000", "status": "none"},
            "detection_in_this_meeting": None,
            "graduation_recommendation": None,
        },
        "coaching": {
            "executive_summary": "Original executive summary.",
            "coaching_themes": [
                {"theme": "Original theme", "explanation": "Original explanation", "related_patterns": ["purposeful_framing"], "priority": "primary", "nature": "developmental", "best_success_span_id": None, "coaching_note": None, "suggested_rewrite": None, "rewrite_for_span_id": None},
            ],
            "focus": [
                {"pattern_id": "focus_management", "message": "Original focus message."},
            ],
            "micro_experiment": [
                {
                    "experiment_id": "EXP-000001",
                    "title": "Original title",
                    "instruction": "Original instruction",
                    "success_marker": "Original success marker",
                    "pattern_id": "focus_management",
                    "evidence_span_ids": ["ES-T003"],
                },
            ],
            "pattern_coaching": [
                {
                    "pattern_id": "purposeful_framing",
                    "notes": "Original positive note for PF.",
                    "coaching_note": "Original coaching note for PF.",
                    "suggested_rewrite": "Original suggested rewrite for PF.",
                    "rewrite_for_span_id": "ES-T015-016",
                    "best_success_span_id": "ES-T001-002",
                },
                {
                    "pattern_id": "focus_management",
                    "notes": "Original positive note for FM.",
                    "coaching_note": "Original coaching note for FM.",
                    "suggested_rewrite": "Original suggested rewrite for FM.",
                    "rewrite_for_span_id": None,
                    "best_success_span_id": "ES-T003",
                },
                {
                    "pattern_id": "communication_clarity",
                    "notes": "Original positive note for CC.",
                    "coaching_note": "Original coaching note for CC.",
                    "suggested_rewrite": None,
                    "rewrite_for_span_id": None,
                    "best_success_span_id": "ES-T020",
                },
            ],
            "experiment_coaching": {
                "coaching_note": "Original experiment coaching note.",
                "suggested_rewrite": "Original experiment rewrite.",
                "rewrite_for_span_id": None,
            },
        },
    }


# ---------------------------------------------------------------------------
# Delta merge basics
# ---------------------------------------------------------------------------

class TestDeltaMergeBasics:
    """Test that the delta format correctly applies changes and preserves unchanged fields."""

    def test_empty_editor_output_preserves_original(self):
        original = _make_analysis_output()
        merged, changelog = merge_editor_output(original, {"changes": []})
        assert merged["coaching"]["executive_summary"] == "Original executive summary."
        assert len(merged["opportunity_events"]) == 5

    def test_empty_dict_preserves_original(self):
        original = _make_analysis_output()
        merged, changelog = merge_editor_output(original, {})
        assert merged["coaching"]["executive_summary"] == "Original executive summary."

    def test_omitted_pattern_unchanged(self):
        """Patterns not in pattern_coaching_edits should be completely unchanged."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "Rewritten PF note."},
            },
            "changes": [{"field": "coaching_note", "action": "rewritten", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        # PF was edited
        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["coaching_note"] == "Rewritten PF note."

        # FM and CC were not in edits — should be unchanged
        fm = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "focus_management")
        assert fm["coaching_note"] == "Original coaching note for FM."
        cc = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "communication_clarity")
        assert cc["coaching_note"] == "Original coaching note for CC."

    def test_suppress_coaching_note(self):
        """SUPPRESS convention nulls out coaching_note, suggested_rewrite, and rewrite_for_span_id."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "SUPPRESS"},
            },
            "changes": [{"field": "coaching_note", "action": "suppressed", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["coaching_note"] is None
        assert pf["suggested_rewrite"] is None
        assert pf["rewrite_for_span_id"] is None
        # notes (positive observation) should still be there
        assert pf["notes"] == "Original positive note for PF."

    def test_rewrite_coaching_note_preserves_other_fields(self):
        """Rewriting a coaching_note should not affect other fields in the same pattern."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "Better coaching note."},
            },
            "changes": [{"field": "coaching_note", "action": "rewritten", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["coaching_note"] == "Better coaching note."
        assert pf["notes"] == "Original positive note for PF."
        assert pf["suggested_rewrite"] == "Original suggested rewrite for PF."
        assert pf["best_success_span_id"] == "ES-T001-002"

    def test_does_not_mutate_original(self):
        """merge_editor_output should not modify the original dict."""
        original = _make_analysis_output()
        original_copy = copy.deepcopy(original)
        editor_output = {
            "executive_summary": "New summary.",
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "SUPPRESS"},
            },
            "changes": [{"field": "executive_summary", "action": "rewritten", "reason": "test"}],
        }
        merge_editor_output(original, editor_output)
        assert original == original_copy


# ---------------------------------------------------------------------------
# OE removal + score recalculation
# ---------------------------------------------------------------------------

class TestOERemoval:
    """Test OE removal, score recalculation, and insufficient_signal demotion."""

    def test_remove_one_oe_recalculates_score(self):
        """Remove 1 of 3 PF OEs → score = sum(remaining) / 2."""
        original = _make_analysis_output()
        editor_output = {
            "oe_removals": [
                {"pattern_id": "purposeful_framing", "oe_index": 2, "reason": "Not a real PF moment"},
            ],
            "changes": [{"field": "oe_removal", "action": "removed", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        # Should have 4 OEs now (was 5)
        assert len(merged["opportunity_events"]) == 4

        # PF score should be (1.0 + 0.5) / 2 = 0.75
        pf_snap = next(ps for ps in merged["pattern_snapshot"] if ps["pattern_id"] == "purposeful_framing")
        assert pf_snap["score"] == 0.75
        assert pf_snap["opportunity_count"] == 2
        assert pf_snap["evaluable_status"] == "evaluable"

    def test_remove_all_oes_demotes_to_insufficient_signal(self):
        """Remove all OEs for a pattern → insufficient_signal, score removed."""
        original = _make_analysis_output()
        editor_output = {
            "oe_removals": [
                {"pattern_id": "focus_management", "oe_index": 0, "reason": "Not a real FM moment"},
            ],
            "changes": [{"field": "oe_removal", "action": "removed", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        fm_snap = next(ps for ps in merged["pattern_snapshot"] if ps["pattern_id"] == "focus_management")
        assert fm_snap["evaluable_status"] == "insufficient_signal"
        assert "score" not in fm_snap
        assert fm_snap["opportunity_count"] == 0
        assert fm_snap["evidence_span_ids"] == []
        assert "success_evidence_span_ids" not in fm_snap

    def test_remove_below_min_threshold_demotes(self):
        """Remove enough OEs to drop below min_required_threshold → insufficient_signal."""
        original = _make_analysis_output()
        # communication_clarity has min_required_threshold=2 and 1 OE
        # Remove its only OE
        editor_output = {
            "oe_removals": [
                {"pattern_id": "communication_clarity", "oe_index": 0, "reason": "Not a real CC moment"},
            ],
            "changes": [{"field": "oe_removal", "action": "removed", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        cc_snap = next(ps for ps in merged["pattern_snapshot"] if ps["pattern_id"] == "communication_clarity")
        assert cc_snap["evaluable_status"] == "insufficient_signal"
        assert "score" not in cc_snap

    def test_only_counted_oes_contribute_to_score(self):
        """Excluded OEs should not affect score recalculation."""
        original = _make_analysis_output()
        # Change one PF OE to excluded
        pf_oes = [oe for oe in original["opportunity_events"] if oe["pattern_id"] == "purposeful_framing"]
        pf_oes[1]["count_decision"] = "excluded"
        # Now counted PF OEs: index 0 (1.0) and index 2 (0.0)
        # Remove index 2 (the 0.0 one)
        editor_output = {
            "oe_removals": [
                {"pattern_id": "purposeful_framing", "oe_index": 2, "reason": "Weak moment"},
            ],
            "changes": [{"field": "oe_removal", "action": "removed", "reason": "test"}],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf_snap = next(ps for ps in merged["pattern_snapshot"] if ps["pattern_id"] == "purposeful_framing")
        # Only 1 counted OE remains (the 1.0 one), excluded one doesn't count
        assert pf_snap["score"] == 1.0
        assert pf_snap["opportunity_count"] == 1

    def test_invalid_oe_index_ignored(self):
        """Invalid OE index should be safely ignored."""
        original = _make_analysis_output()
        editor_output = {
            "oe_removals": [
                {"pattern_id": "purposeful_framing", "oe_index": 99, "reason": "Invalid index"},
            ],
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        # No OEs should have been removed
        assert len(merged["opportunity_events"]) == 5


# ---------------------------------------------------------------------------
# Coaching discard for demoted patterns
# ---------------------------------------------------------------------------

class TestCoachingDiscardForDemoted:
    """When OE removal demotes a pattern, all coaching should be discarded."""

    def test_demoted_pattern_coaching_nulled(self):
        original = _make_analysis_output()
        editor_output = {
            "oe_removals": [
                {"pattern_id": "focus_management", "oe_index": 0, "reason": "Not FM"},
            ],
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        fm = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "focus_management")
        assert fm["coaching_note"] is None
        assert fm["suggested_rewrite"] is None
        assert fm["rewrite_for_span_id"] is None
        assert fm["best_success_span_id"] is None
        assert fm["notes"] is None

    def test_editor_edits_for_demoted_pattern_ignored(self):
        """If the editor tried to rewrite a pattern that also got demoted, the rewrite is discarded."""
        original = _make_analysis_output()
        editor_output = {
            "oe_removals": [
                {"pattern_id": "focus_management", "oe_index": 0, "reason": "Not FM"},
            ],
            "pattern_coaching_edits": {
                "focus_management": {"coaching_note": "This should be ignored."},
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        fm = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "focus_management")
        assert fm["coaching_note"] is None  # Discarded, not the editor's rewrite


# ---------------------------------------------------------------------------
# Span reference validation
# ---------------------------------------------------------------------------

class TestSpanValidation:
    """Test span reference validation and revert logic."""

    def test_invalid_best_success_span_reverted(self):
        """best_success_span_id not in success_evidence_span_ids → revert to original."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {
                    "best_success_span_id": "ES-T999",  # doesn't exist
                },
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["best_success_span_id"] == "ES-T001-002"  # reverted to original

    def test_changed_rewrite_span_without_new_rewrite_reverted(self):
        """If rewrite_for_span_id changed but suggested_rewrite didn't → revert both."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {
                    # Change span target but don't change the rewrite text
                    "rewrite_for_span_id": "ES-T010-011",
                },
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["rewrite_for_span_id"] == "ES-T015-016"  # reverted
        assert pf["suggested_rewrite"] == "Original suggested rewrite for PF."  # reverted

    def test_changed_rewrite_span_with_new_rewrite_accepted(self):
        """If both rewrite_for_span_id and suggested_rewrite changed → accept both."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "purposeful_framing": {
                    "rewrite_for_span_id": "ES-T010-011",
                    "suggested_rewrite": "New rewrite matching the new span.",
                },
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        pf = next(pc for pc in merged["coaching"]["pattern_coaching"] if pc["pattern_id"] == "purposeful_framing")
        assert pf["rewrite_for_span_id"] == "ES-T010-011"
        assert pf["suggested_rewrite"] == "New rewrite matching the new span."


# ---------------------------------------------------------------------------
# Top-level text edits
# ---------------------------------------------------------------------------

class TestToplevelEdits:
    """Test top-level text field edits."""

    def test_executive_summary_replacement(self):
        original = _make_analysis_output()
        editor_output = {
            "executive_summary": "New executive summary.",
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        assert merged["coaching"]["executive_summary"] == "New executive summary."

    def test_coaching_themes_replacement(self):
        original = _make_analysis_output()
        new_themes = [
            {"theme": "New theme", "explanation": "New explanation", "related_patterns": [], "priority": "primary"},
        ]
        editor_output = {
            "coaching_themes": new_themes,
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        assert merged["coaching"]["coaching_themes"] == new_themes

    def test_focus_message_rewrite(self):
        original = _make_analysis_output()
        editor_output = {
            "focus_message": "Better focus message.",
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        assert merged["coaching"]["focus"][0]["message"] == "Better focus message."
        assert merged["coaching"]["focus"][0]["pattern_id"] == "focus_management"  # unchanged

    def test_micro_experiment_text_edits(self):
        original = _make_analysis_output()
        editor_output = {
            "micro_experiment_edits": {
                "title": "Better title",
                "instruction": "Better instruction",
                # success_marker omitted — should stay original
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        me = merged["coaching"]["micro_experiment"][0]
        assert me["title"] == "Better title"
        assert me["instruction"] == "Better instruction"
        assert me["success_marker"] == "Original success marker"  # unchanged
        assert me["pattern_id"] == "focus_management"  # structural — unchanged

    def test_experiment_coaching_edits(self):
        original = _make_analysis_output()
        editor_output = {
            "experiment_coaching_edits": {
                "coaching_note": "Better experiment coaching.",
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        assert merged["coaching"]["experiment_coaching"]["coaching_note"] == "Better experiment coaching."
        assert merged["coaching"]["experiment_coaching"]["suggested_rewrite"] == "Original experiment rewrite."  # unchanged


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_unknown_pattern_id_ignored(self):
        """Editor references a pattern_id not in the analysis → ignored."""
        original = _make_analysis_output()
        editor_output = {
            "pattern_coaching_edits": {
                "nonexistent_pattern": {"coaching_note": "This should be ignored."},
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)
        # All original coaching should be unchanged
        for pc in merged["coaching"]["pattern_coaching"]:
            orig_pc = next(
                o for o in _make_analysis_output()["coaching"]["pattern_coaching"]
                if o["pattern_id"] == pc["pattern_id"]
            )
            assert pc["coaching_note"] == orig_pc["coaching_note"]

    def test_structural_fields_never_modified(self):
        """Scores, evidence_spans, pattern_snapshot structure should never change from coaching edits."""
        original = _make_analysis_output()
        editor_output = {
            "executive_summary": "New summary.",
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "New note."},
                "focus_management": {"coaching_note": "SUPPRESS"},
            },
            "changes": [],
        }
        merged, _ = merge_editor_output(original, editor_output)

        # Scores unchanged
        pf_snap = next(ps for ps in merged["pattern_snapshot"] if ps["pattern_id"] == "purposeful_framing")
        assert pf_snap["score"] == 0.5
        assert pf_snap["opportunity_count"] == 3

        # Evidence spans unchanged
        assert len(merged["evidence_spans"]) == 5
        assert len(merged["opportunity_events"]) == 5

    def test_changelog_returned(self):
        """The changes array from the editor should be returned as the changelog."""
        original = _make_analysis_output()
        changes = [
            {"field": "coaching_note", "action": "rewritten", "reason": "More specific"},
            {"field": "executive_summary", "action": "rewritten", "reason": "Buried the lead"},
        ]
        editor_output = {
            "executive_summary": "New summary.",
            "pattern_coaching_edits": {
                "purposeful_framing": {"coaching_note": "New note."},
            },
            "changes": changes,
        }
        _, changelog = merge_editor_output(original, editor_output)
        assert changelog == changes
