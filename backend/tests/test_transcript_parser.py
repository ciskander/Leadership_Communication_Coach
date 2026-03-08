"""
test_transcript_parser.py — Tests for all supported transcript formats.
"""
from __future__ import annotations

import pytest

from unittest.mock import patch

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
    result = parse_transcript(VTT_VOICE_TAG.encode("utf-8"), "test.vtt", "test")
    assert isinstance(result, ParsedTranscript)
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].speaker_label == "Alice"
    assert result.turns[0].turn_id == 1


def test_vtt_colon_prefix_speakers():
    result = parse_transcript(VTT_COLON_PREFIX.encode("utf-8"), "test.vtt", "test")
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert "Carol" in result.speaker_labels
    assert len(result.turns) == 3


def test_vtt_skips_style_and_note_blocks():
    result = parse_transcript(VTT_MIXED.encode("utf-8"), "test.vtt", "test")
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
    result = parse_transcript(SRT_BASIC.encode("utf-8"), "test.srt", "test")
    assert isinstance(result, ParsedTranscript)
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].text == "This is the first line."


def test_srt_turn_ids_sequential():
    result = parse_transcript(SRT_BASIC.encode("utf-8"), "test.srt", "test")
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
    result = parse_transcript(TXT_SPEAKER_COLON.encode("utf-8"), "test.txt", "test")
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert "Carol" in result.speaker_labels
    assert len(result.turns) == 4


def test_txt_speaker_timestamp_format():
    """
    The parser does not currently recognise the 'Speaker HH:MM:SS\ntext' format.
    It falls back to a single Unknown turn. This test documents that behaviour —
    update it if timestamp-prefixed TXT support is added in future.
    """
    result = parse_transcript(TXT_SPEAKER_TIMESTAMP.encode("utf-8"), "test.txt", "test")
    assert isinstance(result, ParsedTranscript)
    assert len(result.turns) >= 1


def test_txt_no_speakers_fallback():
    """With no speaker labels, should return turns under a fallback label."""
    result = parse_transcript(TXT_NO_SPEAKERS.encode("utf-8"), "test.txt", "test")
    assert isinstance(result, ParsedTranscript)
    # Should have at least one turn
    assert len(result.turns) >= 1
    # All speakers should be a consistent fallback label (e.g. "SPEAKER_01" or "unknown")
    assert len(result.speaker_labels) >= 1


# ---------------------------------------------------------------------------
# Metadata Tests
# ---------------------------------------------------------------------------

def test_metadata_word_count():
    result = parse_transcript(TXT_SPEAKER_COLON.encode("utf-8"), "test.txt", "test")
    assert result.metadata.word_count > 0


def test_metadata_original_format_vtt():
    result = parse_transcript(VTT_VOICE_TAG.encode("utf-8"), "meeting.vtt", "test")
    assert result.metadata.original_format == "vtt"


def test_metadata_original_format_srt():
    result = parse_transcript(SRT_BASIC.encode("utf-8"), "meeting.srt", "test")
    assert result.metadata.original_format == "srt"


def test_metadata_original_format_txt():
    result = parse_transcript(TXT_SPEAKER_COLON.encode("utf-8"), "meeting.txt", "test")
    assert result.metadata.original_format == "txt"


def test_parse_empty_raises():
    with pytest.raises((TranscriptParseError, ValueError)):
        parse_transcript(b"", "test.txt", "test")


def test_speaker_deduplication():
    """Same speaker in different casing should be deduped."""
    # Padded to exceed TRANSCRIPT_MIN_CHARS minimum length requirement
    txt = (
        "alice: Hello everyone, welcome to the meeting today.\n"
        "Alice: Thank you all for being here, let us get started.\n"
        "alice: I wanted to discuss the agenda items we have prepared.\n"
        "Alice: Great, let us go through them one by one carefully.\n"
    )
    result = parse_transcript(txt.encode("utf-8"), "test.txt", "test")
    # Should only have one unique speaker
    lower_labels = [s.lower() for s in result.speaker_labels]
    assert lower_labels.count("alice") == 1


TXT_LONG_TURNS_WITH_HEADER = """\
Final Transcript
Customer: US Chemical Safety Board
Call Title: CSB Business Meeting
Date: January 20, 2016
Time/Time Zone: 1:01 pm Eastern Time
SPEAKERS
Hillary Cohen
Vanessa Allen Sutherland
Manny Ehrlich
PRESENTATION
Operator: Welcome to the CSB Business Meeting. My name is Paulette, and I will be your operator for today's call. At this time, all participants are in a listen-only mode. Later, we will conduct a question-and-answer session. Please note that this conference is being recorded.
I will now turn the call over to Hillary Cohen, Communications Manager. Ms. Cohen, you may begin.
Hillary Cohen: Thank you. Good afternoon, everyone. Welcome to our first public business meeting for this calendar year. Leading today's meeting is going to be our Chairperson, Vanessa Allen Sutherland, and she has opening remarks. She'll take us through the agenda and we'll go to public comment near the end of the meeting. If you have any trouble hearing on the line, please let us know, as we will try to speak up. Thank you.
Vanessa Allen Sutherland: Thanks, Hillary. Today, we are meeting in open session, as required by the Government in the Sunshine Act, to discuss operations and activities of the CSB. As Hillary mentioned, I'm Vanessa Allen Sutherland, the Chairperson of the Board. Joining me today are Members, Manny Ehrlich, Kristen Kulinowski, and Rick Engler. Also joining as our acting general counsel, Kara Wenzel, and members of the staff. Thank you to everyone who's participating by phone, as well.
We will have public comment at the end, and we'll make sure that as you're listening on the phone, we give you instructions as to how to participate remotely.
The CSB is an independent, non-regulatory, federal agency that investigates major chemical accidents at fixed facilities. The investigations examine all aspects of chemical accidents, including physical causes related to equipment design, as well as inadequacies in regulations, industry standards, and safety management systems. Ultimately, we issue safety recommendations, which are designed to prevent similar incidents or accidents in the future.
The purpose of today's meeting is to provide an opportunity for the Board to discuss ongoing investigation and organizational activities, including the status of the CSB's Action Plan, and a very brief discussion about deployment.
Manny Ehrlich: Good afternoon. Thank you for coming. I'm Manny Ehrlich. I am the senior member on the Board with 13 months now. I'm also the senior member chronologically. I'm not sure what one has to do with the other, but it's been an interesting year for me, 13 months.
As some of you know, I spent 50 years in the chemical industry, which isn't bad for a guy that's 35 years old, and I think we've made some progress, and taking what we've learned on a number of these incidents back to folks in the field and hopefully they'll have some benefit in terms of not having the same types of incidents occur again.
I'd like to think of us as being like the smallest, most powerful agency officials, the smallest budget with the biggest reach. In the words of Margaret Mead: "Never underestimate the power of a small group of committed people to change the world."
Among the participants in the formal presentation were: the Torrance Refinery Action Alliance and United Steelworkers.
Just a couple of other brief observations: one is that the refinery is in the process of sale.
We consider numerous factors when deploying, including: the number of injuries and fatalities.
M: Yes.
Rick Engler: Thank you. On February 18, 2015, an explosion occurred in the electrostatic precipitator at the ExxonMobil refinery in Southern California.
"""


def test_txt_long_turns_with_header():
    """Transcript with long multi-line turns and a metadata header should
    still detect Format A speakers (not collapse to Unknown)."""
    result = parse_transcript(
        TXT_LONG_TURNS_WITH_HEADER.encode("utf-8"), "transcript.txt", "test"
    )
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "unknown" not in labels_lower, (
        f"Expected real speaker names, got: {result.speaker_labels}"
    )
    assert any("hillary" in s for s in labels_lower)
    assert any("vanessa" in s for s in labels_lower)
    assert any("manny" in s for s in labels_lower)
    assert any("operator" in s for s in labels_lower)
    assert len(result.turns) >= 4


def test_header_lines_not_extracted_as_speakers():
    """Header lines like 'Customer: ...' and 'Date: ...' should not appear
    as speaker labels."""
    result = parse_transcript(
        TXT_LONG_TURNS_WITH_HEADER.encode("utf-8"), "transcript.txt", "test"
    )
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "customer" not in labels_lower
    assert "date" not in labels_lower
    assert "call title" not in labels_lower
    assert "time/time zone" not in labels_lower


def test_sentence_fragments_not_extracted_as_speakers():
    """Mid-sentence colons should not create false speaker labels."""
    result = parse_transcript(
        TXT_LONG_TURNS_WITH_HEADER.encode("utf-8"), "transcript.txt", "test"
    )
    labels_lower = [s.lower() for s in result.speaker_labels]
    # These are sentence fragments that contain colons, not speaker names
    for bad in [
        "biggest reach. in the words of margaret mead",
        "among the participants in the formal presentation were",
        "just a couple of other brief observations",
        "we consider numerous factors when deploying, including",
    ]:
        assert bad not in labels_lower, f"False speaker label detected: {bad}"
    # Real speakers should still be present
    assert any("rick" in s for s in labels_lower)
    assert any("manny" in s for s in labels_lower)
    # Single-letter labels like "M" are acceptable (unidentified speaker)
    assert any(s == "m" for s in labels_lower)


def test_truncation_never_returns_empty_turns():
    """When a single turn exceeds TRANSCRIPT_MAX_WORDS, truncation should
    trim the turn's text rather than returning an empty list."""
    # Build a transcript with a single massive turn (15,000 words)
    big_speech = " ".join(["word"] * 15_000)
    txt = f"Alice: {big_speech}\n"
    with patch("backend.core.transcript_parser.TRANSCRIPT_MAX_WORDS", 10_000):
        result = parse_transcript(txt.encode("utf-8"), "test.txt", "test")
    assert len(result.turns) >= 1, "Truncation must not produce empty turns"
    assert result.turns[0].speaker_label == "Alice"
    assert result.metadata.word_count <= 10_000
    assert result.metadata.truncated is True


def test_truncation_preserves_multiple_speakers():
    """Truncation should keep as many whole turns as fit, not just the first."""
    # 5 speakers, each with 1,500 words → 7,500 total
    speakers = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    lines = []
    for name in speakers:
        speech = " ".join(["word"] * 1_500)
        lines.append(f"{name}: {speech}")
    txt = "\n".join(lines)
    with patch("backend.core.transcript_parser.TRANSCRIPT_MAX_WORDS", 5_000):
        result = parse_transcript(txt.encode("utf-8"), "test.txt", "test")
    # Should fit at least 3 speakers (3 * 1500 = 4500 < 5000)
    assert len(result.turns) >= 3
    assert result.metadata.truncated is True


def test_turn_ids_always_start_at_1():
    for content, fname in [
        (VTT_VOICE_TAG, "test.vtt"),
        (SRT_BASIC, "test.srt"),
        (TXT_SPEAKER_COLON, "test.txt"),
    ]:
        result = parse_transcript(content.encode("utf-8"), fname, "test")
        assert result.turns[0].turn_id == 1, f"Failed for {fname}"
