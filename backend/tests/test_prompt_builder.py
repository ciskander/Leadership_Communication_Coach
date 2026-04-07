"""
test_prompt_builder.py — Verify payload structure from prompt_builder matches
the expected format from the example API calls.
"""
from __future__ import annotations

import json
import pytest

from backend.core.prompt_builder import (
    build_single_meeting_prompt,
    build_baseline_pack_prompt,
    build_memory_block,
    build_developer_message,
    build_experiment_taxonomy_block,
    extract_pattern_ids,
    _extract_section,
    _extract_field,
    _load_taxonomy_raw,
)
from backend.core.openai_client import load_next_experiment_system_prompt
from backend.core.models import MemoryBlock, ParsedTranscript, PromptPayload, Turn, TranscriptMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(speaker: str = "Alice", n_turns: int = 5) -> ParsedTranscript:
    turns = [
        Turn(
            turn_id=i + 1,
            speaker_label=speaker if i % 2 == 0 else "Bob",
            text=f"Turn {i + 1} text.",
        )
        for i in range(n_turns)
    ]
    return ParsedTranscript(
        source_id="test-transcript-001",
        turns=turns,
        speaker_labels=[speaker, "Bob"],
        metadata=TranscriptMetadata(
            original_format="txt",
            turn_count=n_turns,
            word_count=n_turns * 3,
        ),
    )


def _null_memory() -> MemoryBlock:
    """Return a null memory block (no baseline, no experiment)."""
    return build_memory_block()


def _make_meetings_meta(meeting_ids: list[str], meeting_type: str = "exec_staff") -> list[dict]:
    return [
        {
            "meeting_id": mid,
            "meeting_type": meeting_type,
            "target_speaker_name": "Alice",
            "target_speaker_label": "Alice",
            "target_speaker_role": "chair",
        }
        for mid in meeting_ids
    ]


def _make_meeting_summaries(meeting_ids: list[str]) -> list[dict]:
    """Minimal enriched meeting summary dicts matching _build_slim_meeting_summary output."""
    return [
        {
            "meeting_id": mid,
            "meeting_type": "exec_staff",
            "target_role": "chair",
            "target_speaker_name": "Alice",
            "pattern_snapshot": [
                {
                    "pattern_id": "purposeful_framing",
                    "evaluable_status": "evaluable",
                    "opportunity_count": 2,
                    "score": 1.0,
                    "evidence_span_ids": ["ES-001"],
                    "notes": "Strong agenda framing.",
                }
            ],
            "coaching_output": {
                "strengths": [{"pattern_id": "purposeful_framing", "message": "Good work."}],
                "focus": [{"pattern_id": "resolution_and_alignment", "message": "Improve."}],
                "micro_experiment": {
                    "title": "Close decisions out loud",
                    "instruction": "State the decision.",
                    "success_marker": "Decision stated.",
                    "pattern_id": "resolution_and_alignment",
                    "evidence_span_ids": ["ES-002"],
                },
            },
            "evidence_spans": [
                {
                    "evidence_span_id": "ES-001",
                    "turn_start_id": 1,
                    "turn_end_id": 1,
                    "excerpt": "Let us start with the agenda.",
                    "meeting_id": mid,
                },
                {
                    "evidence_span_id": "ES-002",
                    "turn_start_id": 5,
                    "turn_end_id": 5,
                    "excerpt": "So we will move on.",
                    "meeting_id": mid,
                },
            ],
        }
        for mid in meeting_ids
    ]


# ---------------------------------------------------------------------------
# Single meeting prompt — structure
# ---------------------------------------------------------------------------

def test_single_meeting_prompt_returns_prompt_payload():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert isinstance(payload, PromptPayload)


def test_single_meeting_prompt_has_raw_user_message():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert payload.raw_user_message
    assert len(payload.raw_user_message) > 100


def test_single_meeting_prompt_user_message_contains_meeting_id():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000042",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert "M-000042" in payload.raw_user_message


def test_single_meeting_prompt_contains_target_speaker():
    transcript = _make_transcript(speaker="Carol")
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="one_on_one",
        target_role="manager_1to1",
        target_speaker_name="Carol",
        target_speaker_label="Carol",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert "Carol" in payload.raw_user_message


def test_single_meeting_prompt_contains_transcript_turns():
    transcript = _make_transcript(n_turns=4)
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="participant",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    for turn in transcript.turns:
        assert turn.text in payload.raw_user_message


def test_single_meeting_prompt_contains_target_role():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="presenter",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert "presenter" in payload.raw_user_message.lower()


def test_single_meeting_prompt_analysis_type_is_single_meeting():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert payload.analysis_type == "single_meeting"


def test_single_meeting_prompt_contains_meeting_date():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=_null_memory(),
        meeting_date="2026-02-12",
    )
    assert "2026-02-12" in payload.raw_user_message


# ---------------------------------------------------------------------------
# Single meeting prompt — memory block
# ---------------------------------------------------------------------------

def test_single_meeting_prompt_with_active_experiment_in_message():
    """When an active experiment exists, it should appear in the user message."""
    transcript = _make_transcript()
    memory = build_memory_block(
        baseline_pack_id="BP-000001",
        active_experiment={
            "experiment_id": "EXP-000001",
            "title": "Close decisions out loud",
            "instruction": "Say it aloud.",
            "success_marker": "2 of 3 closures explicit.",
            "related_patterns": ["resolution_and_alignment"],
            "pattern_id": "resolution_and_alignment",
            "status": "active",
        },
    )
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=memory,
        meeting_date="2026-02-12",
    )
    assert "EXP-000001" in payload.raw_user_message


def test_single_meeting_prompt_null_memory_produces_valid_payload():
    """A null memory block (no baseline, no experiment) should not raise."""
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        parsed_transcript=transcript,
        memory=build_memory_block(),
        meeting_date="2026-02-12",
    )
    assert isinstance(payload, PromptPayload)


# ---------------------------------------------------------------------------
# Baseline pack prompt — structure
# ---------------------------------------------------------------------------

def test_baseline_pack_prompt_returns_prompt_payload():
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    assert isinstance(payload, PromptPayload)


def test_baseline_pack_prompt_includes_pack_id():
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    assert "BP-000001" in payload.raw_user_message


def test_baseline_pack_prompt_references_all_meetings():
    meeting_ids = ["M-000010", "M-000011", "M-000012"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000002",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    for mid in meeting_ids:
        assert mid in payload.raw_user_message


def test_baseline_pack_prompt_analysis_type_in_message():
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    assert "baseline_pack" in payload.raw_user_message.lower()


def test_baseline_pack_prompt_analysis_type_is_baseline_pack():
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    assert payload.analysis_type == "baseline_pack"


def test_baseline_pack_prompt_pack_size_in_message():
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    assert "3" in payload.raw_user_message


def test_baseline_pack_prompt_meeting_summaries_in_message():
    """Meeting summary data should be serialised into the user message."""
    meeting_ids = ["M-000001", "M-000002", "M-000003"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        role_consistency="consistent",
        meeting_type_consistency="consistent",
        meetings_meta=_make_meetings_meta(meeting_ids),
        meeting_summaries=_make_meeting_summaries(meeting_ids),
    )
    # purposeful_framing is in the summaries and should appear in the packed message
    assert "purposeful_framing" in payload.raw_user_message


# ---------------------------------------------------------------------------
# build_memory_block
# ---------------------------------------------------------------------------

def test_build_memory_block_null_when_no_baseline_or_experiment():
    memory = build_memory_block()
    assert memory.baseline_profile is None
    assert memory.active_experiment is None
    assert memory.coaching_history == []
    assert memory.experiment_history == []


def test_build_memory_block_with_baseline():
    memory = build_memory_block(
        baseline_pack_id="BP-000001",
    )
    assert memory.baseline_profile is not None
    assert memory.baseline_profile["baseline_pack_id"] == "BP-000001"


def test_build_memory_block_with_active_experiment():
    memory = build_memory_block(
        active_experiment={
            "experiment_id": "EXP-000001",
            "title": "Test",
            "instruction": "Do it.",
            "success_marker": "Done.",
            "pattern_id": "resolution_and_alignment",
            "status": "active",
        }
    )
    assert memory.active_experiment is not None
    assert memory.active_experiment["experiment_id"] == "EXP-000001"
    assert memory.active_experiment["status"] == "active"


# ---------------------------------------------------------------------------
# Taxonomy parsing — single source of truth verification
# ---------------------------------------------------------------------------

EXPECTED_PATTERN_IDS = [
    "purposeful_framing",
    "focus_management",
    "resolution_and_alignment",
    "assignment_clarity",
    "question_quality",
    "communication_clarity",
    "active_listening",
    "recognition",
    "behavioral_integrity",
    "disagreement_navigation",
    "feedback_quality",
]


class TestTaxonomyParsing:
    """Verify the taxonomy file is correctly parsed for all prompt types."""

    def test_extract_pattern_ids_returns_all_11(self):
        ids = extract_pattern_ids()
        assert ids == EXPECTED_PATTERN_IDS

    def test_extract_pattern_ids_preserves_order(self):
        ids = extract_pattern_ids()
        assert ids[0] == "purposeful_framing"
        assert ids[-1] == "feedback_quality"

    def test_core_rules_section_extractable(self):
        raw = _load_taxonomy_raw()
        core_rules = _extract_section(raw, "CORE_RULES")
        assert "Evaluate ONLY the target speaker" in core_rules
        assert "OPPORTUNITY vs. NON-OPPORTUNITY" in core_rules

    def test_each_pattern_section_extractable(self):
        raw = _load_taxonomy_raw()
        for pid in EXPECTED_PATTERN_IDS:
            section = _extract_section(raw, f"PATTERN:{pid}")
            assert len(section) > 50, f"PATTERN:{pid} section is too short"

    def test_general_detection_guidance_extractable(self):
        raw = _load_taxonomy_raw()
        guidance = _extract_section(raw, "GENERAL_DETECTION_GUIDANCE")
        assert len(guidance) > 20


class TestDeveloperMessage:
    """Verify the full taxonomy (used by single_meeting & baseline_pack)."""

    def test_contains_all_pattern_begin_markers(self):
        msg = build_developer_message()
        for pid in EXPECTED_PATTERN_IDS:
            assert f"### BEGIN:PATTERN:{pid} ###" in msg

    def test_contains_all_pattern_end_markers(self):
        msg = build_developer_message()
        for pid in EXPECTED_PATTERN_IDS:
            assert f"### END:PATTERN:{pid} ###" in msg

    def test_contains_core_rules(self):
        msg = build_developer_message()
        assert "### BEGIN:CORE_RULES ###" in msg
        assert "### END:CORE_RULES ###" in msg

    def test_contains_general_detection_guidance(self):
        msg = build_developer_message()
        assert "### BEGIN:GENERAL_DETECTION_GUIDANCE ###" in msg

    def test_is_nonempty_and_substantial(self):
        msg = build_developer_message()
        # Taxonomy should be substantial (hundreds of lines)
        assert len(msg) > 5000


class TestExperimentTaxonomyBlock:
    """Verify the experiment-focused taxonomy extraction."""

    def test_contains_header(self):
        block = build_experiment_taxonomy_block()
        assert "PATTERN TAXONOMY — EXPERIMENT DESIGN GUIDE" in block

    def test_contains_all_pattern_ids(self):
        block = build_experiment_taxonomy_block()
        for pid in EXPECTED_PATTERN_IDS:
            assert f"── {pid} ──" in block

    def test_extracts_four_fields_per_pattern(self):
        block = build_experiment_taxonomy_block()
        for pid in EXPECTED_PATTERN_IDS:
            # Each pattern section should have these four fields
            # Find the pattern's block in the output
            pid_idx = block.index(f"── {pid} ──")
            # Get text until next pattern or end
            next_pattern_idx = len(block)
            for other_pid in EXPECTED_PATTERN_IDS:
                other_idx = block.find(f"── {other_pid} ──", pid_idx + 1)
                if other_idx != -1 and other_idx < next_pattern_idx:
                    next_pattern_idx = other_idx
            pattern_block = block[pid_idx:next_pattern_idx]

            assert "What it measures:" in pattern_block, f"{pid} missing 'What it measures'"
            assert "What good looks like:" in pattern_block, f"{pid} missing 'What good looks like'"
            assert "Common failure mode:" in pattern_block, f"{pid} missing 'Common failure mode'"
            assert "Experiment focus:" in pattern_block, f"{pid} missing 'Experiment focus'"

    def test_extracted_fields_are_nonempty(self):
        raw = _load_taxonomy_raw()
        for pid in EXPECTED_PATTERN_IDS:
            section = _extract_section(raw, f"PATTERN:{pid}")
            what_it_measures = _extract_field(section, "What it measures:")
            what_good = _extract_field(section, "What good looks like:")
            common_failure = _extract_field(section, "Common failure mode:")
            experiment_focus = _extract_field(section, "Experiment focus:")

            assert what_it_measures, f"{pid}: 'What it measures' is empty"
            assert what_good, f"{pid}: 'What good looks like' is empty"
            assert common_failure, f"{pid}: 'Common failure mode' is empty"
            assert experiment_focus, f"{pid}: 'Experiment focus' is empty"


class TestNextExperimentPromptSubstitution:
    """Verify the {{EXPERIMENT_TAXONOMY}} placeholder is replaced."""

    def test_placeholder_is_substituted(self):
        prompt = load_next_experiment_system_prompt()
        assert "{{EXPERIMENT_TAXONOMY}}" not in prompt

    def test_substituted_prompt_contains_taxonomy(self):
        prompt = load_next_experiment_system_prompt()
        assert "PATTERN TAXONOMY — EXPERIMENT DESIGN GUIDE" in prompt

    def test_substituted_prompt_contains_all_patterns(self):
        prompt = load_next_experiment_system_prompt()
        for pid in EXPECTED_PATTERN_IDS:
            assert pid in prompt, f"{pid} missing from next_experiment prompt"

    def test_substituted_prompt_retains_surrounding_content(self):
        prompt = load_next_experiment_system_prompt()
        # Content before the placeholder
        assert "EXPERIMENT DESIGN PHILOSOPHY" in prompt
        # Content after the placeholder
        assert "OUTPUT FORMAT" in prompt
