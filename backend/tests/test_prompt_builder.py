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
)
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
                    "pattern_id": "agenda_clarity",
                    "evaluable_status": "evaluable",
                    "numerator": 2,
                    "denominator": 2,
                    "ratio": 1.0,
                    "evidence_span_ids": ["ES-001"],
                    "notes": "Strong agenda framing.",
                }
            ],
            "coaching_output": {
                "strengths": [{"pattern_id": "agenda_clarity", "message": "Good work."}],
                "focus": [{"pattern_id": "decision_closure", "message": "Improve."}],
                "micro_experiment": {
                    "title": "Close decisions out loud",
                    "instruction": "State the decision.",
                    "success_marker": "Decision stated.",
                    "pattern_id": "decision_closure",
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
        focus_pattern="decision_closure",
        active_experiment={
            "experiment_id": "EXP-000001",
            "title": "Close decisions out loud",
            "instruction": "Say it aloud.",
            "success_marker": "2 of 3 closures explicit.",
            "pattern_id": "decision_closure",
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
    # agenda_clarity is in the summaries and should appear in the packed message
    assert "agenda_clarity" in payload.raw_user_message


# ---------------------------------------------------------------------------
# build_memory_block
# ---------------------------------------------------------------------------

def test_build_memory_block_null_when_no_baseline_or_experiment():
    memory = build_memory_block()
    assert memory.baseline_profile is None
    assert memory.active_experiment is None
    assert memory.recent_pattern_snapshots == []


def test_build_memory_block_with_baseline():
    memory = build_memory_block(
        baseline_pack_id="BP-000001",
        strengths=["agenda_clarity"],
        focus_pattern="decision_closure",
    )
    assert memory.baseline_profile is not None
    assert memory.baseline_profile["baseline_pack_id"] == "BP-000001"
    assert memory.baseline_profile["focus"] == "decision_closure"
    assert "agenda_clarity" in memory.baseline_profile["strengths"]


def test_build_memory_block_with_active_experiment():
    memory = build_memory_block(
        active_experiment={
            "experiment_id": "EXP-000001",
            "title": "Test",
            "instruction": "Do it.",
            "success_marker": "Done.",
            "pattern_id": "decision_closure",
            "status": "active",
        }
    )
    assert memory.active_experiment is not None
    assert memory.active_experiment["experiment_id"] == "EXP-000001"
    assert memory.active_experiment["status"] == "active"
