"""
test_transcript_parser.py — Tests for all supported transcript formats.
"""
from __future__ import annotations

import pytest

from backend.core.transcript_parser import parse_transcript, TranscriptParseError
from backend.core.models import ParsedTranscript


# ---------------------------------------------------------------------------
# VTT Tests
# ---------------------------------------------------------------------------

VTT_VOICE_TAG = """\
WEBVTT

00:00:01.000 --> 00:00:05.000
<v Alice>Let's get started. We have three items today.

00:00:06.000 --> 00:00:10.000
<v Bob>Ready when you are.

00:00:11.000 --> 00:00:15.000
<v Alice>First item: budget approval.
"""

VTT_COLON_PREFIX = """\
WEBVTT

00:00:01.000 --> 00:00:05.000
Alice: Let's get started.

00:00:06.000 --> 00:00:10.000
Bob: Ready when you are.

00:00:11.000 --> 00:00:15.000
Carol: I have questions.
"""

VTT_MIXED = """\
WEBVTT

NOTE This is a comment

STYLE
::cue { color: white; }

00:00:01.000 --> 00:00:05.000
<v Alice>Welcome everyone.

00:00:06.000 --> 00:00:10.000
Bob: Thanks for having us.
"""


def test_vtt_voice_tags_extracts_speakers():
    result = parse_transcript(VTT_VOICE_TAG, source_id="test", filename="test.vtt")
    assert isinstance(result, ParsedTranscript)
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].speaker_label == "Alice"
    assert result.turns[0].turn_id == 1


def test_vtt_colon_prefix_speakers():
    result = parse_transcript(VTT_COLON_PREFIX, source_id="test", filename="test.vtt")
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert "Carol" in result.speaker_labels
    assert len(result.turns) == 3


def test_vtt_skips_style_and_note_blocks():
    result = parse_transcript(VTT_MIXED, source_id="test", filename="test.vtt")
    # Should not include STYLE/NOTE in turns
    for turn in result.turns:
        assert "STYLE" not in turn.text
        assert "::cue" not in turn.text


# ---------------------------------------------------------------------------
# SRT Tests
# ---------------------------------------------------------------------------

SRT_BASIC = """\
1
00:00:00,000 --> 00:00:04,000
Alice: This is the first line.

2
00:00:05,000 --> 00:00:09,000
Bob: And this is the second.

3
00:00:10,000 --> 00:00:14,000
Alice: Wrapping up now.
"""


def test_srt_basic_parsing():
    result = parse_transcript(SRT_BASIC, source_id="test", filename="test.srt")
    assert isinstance(result, ParsedTranscript)
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].text == "This is the first line."


def test_srt_turn_ids_sequential():
    result = parse_transcript(SRT_BASIC, source_id="test", filename="test.srt")
    ids = [t.turn_id for t in result.turns]
    assert ids == list(range(1, len(result.turns) + 1))


# ---------------------------------------------------------------------------
# TXT Tests
# ---------------------------------------------------------------------------

TXT_SPEAKER_COLON = """\
Alice: Good morning everyone.
Bob: Good morning.
Alice: Let's start with the agenda.
Carol: I have a quick question first.
"""

TXT_SPEAKER_TIMESTAMP = """\
Alice 00:00:01
Good morning everyone.

Bob 00:00:05
Good morning.

Alice 00:00:10
Let's start with the agenda.
"""

TXT_NO_SPEAKERS = """\
Good morning everyone.
Let's start with the agenda.
I have a quick question first.
"""


def test_txt_speaker_colon_format():
    result = parse_transcript(TXT_SPEAKER_COLON, source_id="test", filename="test.txt")
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert "Carol" in result.speaker_labels
    assert len(result.turns) == 4


def test_txt_speaker_timestamp_format():
    result = parse_transcript(TXT_SPEAKER_TIMESTAMP, source_id="test", filename="test.txt")
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) >= 2


def test_txt_no_speakers_fallback():
    """With no speaker labels, should return turns under a fallback label."""
    result = parse_transcript(TXT_NO_SPEAKERS, source_id="test", filename="test.txt")
    assert isinstance(result, ParsedTranscript)
    # Should have at least one turn
    assert len(result.turns) >= 1
    # All speakers should be a consistent fallback label (e.g. "SPEAKER_01" or "unknown")
    assert len(result.speaker_labels) >= 1


# ---------------------------------------------------------------------------
# Metadata Tests
# ---------------------------------------------------------------------------

def test_metadata_word_count():
    result = parse_transcript(TXT_SPEAKER_COLON, source_id="test", filename="test.txt")
    assert result.metadata.word_count > 0


def test_metadata_original_format_vtt():
    result = parse_transcript(VTT_VOICE_TAG, source_id="test", filename="meeting.vtt")
    assert result.metadata.original_format == "vtt"


def test_metadata_original_format_srt():
    result = parse_transcript(SRT_BASIC, source_id="test", filename="meeting.srt")
    assert result.metadata.original_format == "srt"


def test_metadata_original_format_txt():
    result = parse_transcript(TXT_SPEAKER_COLON, source_id="test", filename="meeting.txt")
    assert result.metadata.original_format == "txt"


def test_parse_empty_raises():
    with pytest.raises((TranscriptParseError, ValueError)):
        parse_transcript("", source_id="test", filename="test.txt")


def test_speaker_deduplication():
    """Same speaker in different casing should be deduped."""
    txt = "alice: Hello.\nAlice: World."
    result = parse_transcript(txt, source_id="test", filename="test.txt")
    # Should only have one unique speaker
    lower_labels = [s.lower() for s in result.speaker_labels]
    assert lower_labels.count("alice") == 1


def test_turn_ids_always_start_at_1():
    for content, fname in [
        (VTT_VOICE_TAG, "test.vtt"),
        (SRT_BASIC, "test.srt"),
        (TXT_SPEAKER_COLON, "test.txt"),
    ]:
        result = parse_transcript(content, source_id="test", filename=fname)
        assert result.turns[0].turn_id == 1, f"Failed for {fname}"
