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
)
from backend.core.models import ParsedTranscript, Turn, TranscriptMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_transcript(speaker: str = "Alice", n_turns: int = 5) -> ParsedTranscript:
    turns = [
        Turn(turn_id=i + 1, speaker_label=speaker if i % 2 == 0 else "Bob", text=f"Turn {i+1} text.")
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


# ---------------------------------------------------------------------------
# Single meeting prompt structure
# ---------------------------------------------------------------------------

def test_single_meeting_prompt_returns_prompt_payload():
    from backend.core.models import PromptPayload
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    assert isinstance(payload, PromptPayload)


def test_single_meeting_prompt_includes_system_prompt():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    assert payload.system_prompt
    assert len(payload.system_prompt) > 100  # non-trivial system prompt


def test_single_meeting_prompt_user_message_contains_meeting_id():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000042",
        meeting_type="exec_staff",
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    assert "M-000042" in payload.user_message


def test_single_meeting_prompt_contains_target_speaker():
    transcript = _make_transcript(speaker="Carol")
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="one_on_one",
        target_role="manager_1to1",
        target_speaker_name="Carol",
        target_speaker_label="Carol",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    assert "Carol" in payload.user_message


def test_single_meeting_prompt_contains_transcript_turns():
    transcript = _make_transcript(n_turns=4)
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="participant",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    # All turn texts should appear in the user message
    for turn in transcript.turns:
        assert turn.text in payload.user_message


def test_single_meeting_prompt_contains_target_role():
    transcript = _make_transcript()
    payload = build_single_meeting_prompt(
        meeting_id="M-000001",
        meeting_type="exec_staff",
        target_role="presenter",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcript=transcript,
        meeting_date="2026-02-12",
    )
    assert "presenter" in payload.user_message.lower()


# ---------------------------------------------------------------------------
# Baseline pack prompt structure
# ---------------------------------------------------------------------------

def test_baseline_pack_prompt_includes_pack_id():
    transcripts = [_make_transcript() for _ in range(3)]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcripts=[
            {"meeting_id": f"M-00000{i+1}", "meeting_type": "exec_staff", "transcript": t}
            for i, t in enumerate(transcripts)
        ],
    )
    assert "BP-000001" in payload.user_message


def test_baseline_pack_prompt_references_all_meetings():
    transcripts = [_make_transcript() for _ in range(3)]
    meeting_ids = ["M-000010", "M-000011", "M-000012"]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000002",
        pack_size=3,
        target_role="participant",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcripts=[
            {"meeting_id": meeting_ids[i], "meeting_type": "exec_staff", "transcript": t}
            for i, t in enumerate(transcripts)
        ],
    )
    for mid in meeting_ids:
        assert mid in payload.user_message


def test_baseline_pack_prompt_analysis_type_in_message():
    transcripts = [_make_transcript() for _ in range(3)]
    payload = build_baseline_pack_prompt(
        baseline_pack_id="BP-000001",
        pack_size=3,
        target_role="chair",
        target_speaker_name="Alice",
        target_speaker_label="Alice",
        transcripts=[
            {"meeting_id": f"M-00000{i+1}", "meeting_type": "exec_staff", "transcript": t}
            for i, t in enumerate(transcripts)
        ],
    )
    assert "baseline_pack" in payload.user_message.lower()
