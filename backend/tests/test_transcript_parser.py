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

TXT_BRACKETED_TIMESTAMP = """\
Meeting:  LongBeachCC_08092022
Duration: 334 minutes
======================================================================
[00:00:00] spk_0: So But now
[00:00:04] spk_0: Councilman Sabina
[00:00:06] spk_1: I'm here
[00:00:07] spk_0: Councilwoman Mango
[00:00:09] spk_2: Here
[00:00:10] spk_0: Councilwoman Sarah Present Councilmember Karenga Present Councilman Austin
[00:00:16] spk_1: Here
[00:00:17] spk_0: Vice Mayor Richardson
[00:00:18] spk_3: President
[00:00:20] spk_0: Eric Garcia We have a quorum
[00:00:22] spk_4: Thank you And I'm going to ask Councilman Mongo to lead us in the pledge in a moment of silence
[00:00:29] spk_2: Thank you
"""


def test_txt_bracketed_timestamp_format():
    """Transcripts with [HH:MM:SS] speaker: text lines should be parsed correctly."""
    result = parse_transcript(
        TXT_BRACKETED_TIMESTAMP.encode("utf-8"), "transcript.txt", "test"
    )
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "unknown" not in labels_lower, (
        f"Expected speaker labels, got: {result.speaker_labels}"
    )
    assert "spk_0" in labels_lower
    assert "spk_1" in labels_lower
    assert "spk_2" in labels_lower
    assert "spk_3" in labels_lower
    assert "spk_4" in labels_lower
    assert len(result.turns) >= 5  # consecutive spk_0 turns get merged
    # Header lines should not appear as speakers
    assert "meeting" not in labels_lower
    assert "duration" not in labels_lower


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


# ---------------------------------------------------------------------------
# Platform-Specific: Zoom
# ---------------------------------------------------------------------------

ZOOM_VTT_NO_SPEAKERS = """\
WEBVTT

00:00:01.000 --> 00:00:05.000
Welcome everyone to today's quarterly review meeting.

00:00:06.000 --> 00:00:10.000
Thank you for joining, let's get started with the agenda.

00:00:11.000 --> 00:00:18.000
First item is the budget review for this quarter and next quarter projections.
"""

ZOOM_VTT_GENERIC_SPEAKERS = """\
WEBVTT

00:00:01.000 --> 00:00:06.000
<v Speaker 1>Welcome everyone to today's quarterly review meeting.

00:00:07.000 --> 00:00:12.000
<v Speaker 2>Thank you for having us, glad to be here today.

00:00:13.000 --> 00:00:18.000
<v Speaker 1>Let's start with the budget review for the quarter.
"""


def test_zoom_vtt_no_speakers():
    """Zoom VTT without speaker attribution — all turns should be Unknown."""
    result = parse_transcript(ZOOM_VTT_NO_SPEAKERS.encode("utf-8"), "meeting.vtt", "test")
    assert result.metadata.original_format == "vtt"
    assert all(t.speaker_label == "Unknown" for t in result.turns)
    assert len(result.turns) >= 1
    # Timestamps should still be extracted
    assert result.turns[0].start_time_sec is not None
    assert result.turns[0].start_time_sec == pytest.approx(1.0)


def test_zoom_vtt_generic_speakers():
    """Zoom VTT with generic 'Speaker 1', 'Speaker 2' labels."""
    result = parse_transcript(ZOOM_VTT_GENERIC_SPEAKERS.encode("utf-8"), "meeting.vtt", "test")
    assert "Speaker 1" in result.speaker_labels
    assert "Speaker 2" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].speaker_label == "Speaker 1"
    assert result.turns[1].speaker_label == "Speaker 2"


# ---------------------------------------------------------------------------
# Platform-Specific: Microsoft Teams
# ---------------------------------------------------------------------------

TEAMS_VTT_CLOSING_TAGS = """\
WEBVTT

00:00:03.663 --> 00:00:07.903
<v Alice Johnson>Good morning everyone, welcome to the standup.</v>

00:00:08.063 --> 00:00:12.103
<v Bob Smith>Morning Alice, I have an update on the backend work.</v>

00:00:13.000 --> 00:00:18.000
<v Alice Johnson>Great, go ahead Bob and then Carol can share next.</v>
"""


def test_teams_vtt_closing_v_tags():
    """MS Teams VTT with closing </v> tags — no tag residue in text."""
    result = parse_transcript(TEAMS_VTT_CLOSING_TAGS.encode("utf-8"), "meeting.vtt", "test")
    assert "Alice Johnson" in result.speaker_labels
    assert "Bob Smith" in result.speaker_labels
    assert len(result.turns) == 3
    for t in result.turns:
        assert "</v>" not in t.text
        assert "<v" not in t.text


# ---------------------------------------------------------------------------
# Platform-Specific: Otter.ai
# ---------------------------------------------------------------------------

OTTER_SRT = """\
1
00:00:05,000 --> 00:00:10,000
Alice Chen: Hello everyone, welcome to this meeting and thanks for joining.

2
00:00:10,500 --> 00:00:15,000
Bob Park: Thanks for being here today, glad we could all make it.

3
00:00:16,000 --> 00:00:22,000
Alice Chen: Let's review the action items from last week's session.

4
00:00:23,000 --> 00:00:28,000
Carol Davis: I finished the report draft and sent it to the team yesterday.
"""

OTTER_TXT_FORMAT_B = """\
Alice Chen  0:01
Hello everyone, welcome to this meeting today.

Bob Park  0:05
Thanks for being here today, glad we made it.

Alice Chen  0:10
Let's review the action items from last week.

Carol Davis  0:16
I finished the report and sent it yesterday morning.
"""


def test_otter_srt():
    """Otter.ai SRT export with 'Speaker: text' in cue bodies."""
    result = parse_transcript(OTTER_SRT.encode("utf-8"), "meeting.srt", "test")
    assert result.metadata.original_format == "srt"
    assert "Alice Chen" in result.speaker_labels
    assert "Bob Park" in result.speaker_labels
    assert "Carol Davis" in result.speaker_labels
    assert len(result.turns) == 4
    assert result.turns[0].start_time_sec == pytest.approx(5.0)


def test_otter_txt_format_b():
    """Otter.ai TXT export with 'Speaker  HH:MM' blocks."""
    result = parse_transcript(OTTER_TXT_FORMAT_B.encode("utf-8"), "transcript.txt", "test")
    assert result.metadata.original_format == "txt"
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "alice chen" in labels_lower
    assert "bob park" in labels_lower
    assert len(result.turns) >= 3  # consecutive Alice turns may merge


# ---------------------------------------------------------------------------
# Platform-Specific: Google Meet
# ---------------------------------------------------------------------------

GMEET_TXT_SINGLE_SPACE = """\
Sarah Miller 0:00:01
Good morning everyone, thanks for joining this call today.

James Wilson 0:00:15
Morning Sarah, I wanted to share an update on the project status.

Sarah Miller 0:00:30
Great, please go ahead James, we are all ears for the update.

Emily Brown 0:00:45
I also have some notes to add after James finishes his update.
"""


def test_gmeet_txt_single_space_hhmmss():
    """Google Meet TXT with single space + HH:MM:SS timestamps."""
    result = parse_transcript(GMEET_TXT_SINGLE_SPACE.encode("utf-8"), "transcript.txt", "test")
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "sarah miller" in labels_lower
    assert "james wilson" in labels_lower
    assert "emily brown" in labels_lower
    assert len(result.turns) >= 3
    # Check timestamps are parsed
    assert result.turns[0].start_time_sec is not None
    assert result.turns[0].start_time_sec == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Platform-Specific: Rev.com CSV
# ---------------------------------------------------------------------------

REV_CSV_WITH_HEADER = """\
Speaker,Text,Timestamp
Alice Chen,"Good morning everyone, welcome to our quarterly review.",0:00:01
Bob Park,"Thank you Alice, let's jump right into the numbers.",0:00:08
Alice Chen,"Revenue is up fifteen percent from last quarter overall.",0:00:15
Carol Davis,"The marketing campaign drove most of that growth for us.",0:00:22
"""

REV_CSV_NO_HEADER = """\
Alice Chen,"Good morning everyone, welcome to this meeting today.",0:00:01
Bob Park,"Thank you Alice for the warm welcome and introduction.",0:00:08
Carol Davis,"I have the quarterly numbers ready for the group.",0:00:15
"""


def test_rev_csv_with_header():
    """Rev.com CSV with header row — columns detected by name."""
    result = parse_transcript(REV_CSV_WITH_HEADER.encode("utf-8"), "transcript.csv", "test")
    assert result.metadata.original_format == "csv"
    assert "Alice Chen" in result.speaker_labels
    assert "Bob Park" in result.speaker_labels
    assert "Carol Davis" in result.speaker_labels
    assert len(result.turns) == 4
    assert result.turns[0].start_time_sec == pytest.approx(1.0)


def test_rev_csv_no_header():
    """Rev.com CSV without header — positional column fallback."""
    result = parse_transcript(REV_CSV_NO_HEADER.encode("utf-8"), "transcript.csv", "test")
    assert result.metadata.original_format == "csv"
    assert "Alice Chen" in result.speaker_labels
    assert len(result.turns) == 3


# ---------------------------------------------------------------------------
# Platform-Specific: Fireflies.ai JSON
# ---------------------------------------------------------------------------

FIREFLIES_JSON_SEGMENTS = """\
{
  "title": "Weekly Standup",
  "segments": [
    {"speaker": "Alice Chen", "text": "Good morning everyone, let's start the standup meeting.", "start": 1.0, "end": 5.0},
    {"speaker": "Bob Park", "text": "I worked on the API integration yesterday and made good progress.", "start": 6.0, "end": 10.0},
    {"speaker": "Carol Davis", "text": "I reviewed the pull requests and left feedback on each one.", "start": 11.0, "end": 15.0},
    {"speaker": "Alice Chen", "text": "Great work team, let's sync again tomorrow morning at nine.", "start": 16.0, "end": 20.0}
  ]
}
"""

FIREFLIES_JSON_UTTERANCES = """\
{
  "meeting_id": "abc123",
  "utterances": [
    {"speaker_name": "Alice Chen", "content": "Hello everyone, thanks for joining this morning.", "start_time": 0.5},
    {"speaker_name": "Bob Park", "content": "Hi Alice, glad to be here for the sync today.", "start_time": 4.2},
    {"speaker_name": "Carol Davis", "content": "I have updates on the frontend and design work.", "start_time": 8.0}
  ]
}
"""

FIREFLIES_JSON_WORDS = """\
{
  "segments": [
    {
      "speaker": "Alice",
      "words": [
        {"word": "Good", "start": 0.0},
        {"word": "morning", "start": 0.2},
        {"word": "everyone,", "start": 0.4},
        {"word": "welcome", "start": 0.6},
        {"word": "to", "start": 0.8},
        {"word": "the", "start": 0.9},
        {"word": "meeting.", "start": 1.0}
      ]
    },
    {
      "speaker": "Bob",
      "words": [
        {"word": "Thanks", "start": 2.0},
        {"word": "Alice,", "start": 2.2},
        {"word": "glad", "start": 2.4},
        {"word": "to", "start": 2.5},
        {"word": "be", "start": 2.6},
        {"word": "here", "start": 2.7},
        {"word": "today.", "start": 2.8}
      ]
    }
  ]
}
"""


def test_fireflies_json_segments():
    """Fireflies JSON with 'segments' array."""
    result = parse_transcript(FIREFLIES_JSON_SEGMENTS.encode("utf-8"), "meeting.json", "test")
    assert result.metadata.original_format == "json"
    assert "Alice Chen" in result.speaker_labels
    assert "Bob Park" in result.speaker_labels
    assert "Carol Davis" in result.speaker_labels
    assert len(result.turns) == 4
    assert result.turns[0].start_time_sec == pytest.approx(1.0)


def test_fireflies_json_utterances():
    """Fireflies JSON with 'utterances' key and alternative field names."""
    result = parse_transcript(FIREFLIES_JSON_UTTERANCES.encode("utf-8"), "meeting.json", "test")
    assert result.metadata.original_format == "json"
    assert "Alice Chen" in result.speaker_labels
    assert "Bob Park" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].start_time_sec == pytest.approx(0.5)


def test_fireflies_json_words_array():
    """JSON with words arrays instead of text strings."""
    result = parse_transcript(FIREFLIES_JSON_WORDS.encode("utf-8"), "meeting.json", "test")
    assert result.metadata.original_format == "json"
    assert "Alice" in result.speaker_labels
    assert "Bob" in result.speaker_labels
    assert len(result.turns) == 2
    assert "Good morning everyone," in result.turns[0].text


# ---------------------------------------------------------------------------
# Platform-Specific: Fireflies.ai Markdown
# ---------------------------------------------------------------------------

FIREFLIES_MARKDOWN = """\
# Weekly Standup - March 15, 2026

## Participants
- Alice Chen
- Bob Park
- Carol Davis

---

**Alice Chen** 0:01
Good morning everyone, let's start the standup meeting today.

**Bob Park** 0:08
I worked on the API integration and made progress yesterday afternoon.

**Alice Chen** 0:15
Great work Bob, that sounds like a solid update for the team.

**Carol Davis** 0:22
I reviewed the pull requests and left detailed feedback on each one.
"""


def test_fireflies_markdown():
    """Fireflies markdown export with **bold** speakers and timestamps."""
    result = parse_transcript(FIREFLIES_MARKDOWN.encode("utf-8"), "transcript.md", "test")
    assert result.metadata.original_format == "md"
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "alice chen" in labels_lower
    assert "bob park" in labels_lower
    assert "carol davis" in labels_lower
    assert len(result.turns) >= 3


# ---------------------------------------------------------------------------
# SRT Bracketed Speakers
# ---------------------------------------------------------------------------

SRT_BRACKETED = """\
1
00:00:00,000 --> 00:00:04,000
[Alice Chen] Good morning everyone, let's get this meeting started today.

2
00:00:05,000 --> 00:00:09,000
[Bob Park] Thanks Alice, I have an update on the backend integration work.

3
00:00:10,000 --> 00:00:14,000
[Alice Chen] Great Bob, please go ahead and share your update with us.
"""


def test_srt_bracketed_speakers():
    """SRT with [Speaker Name] text pattern."""
    result = parse_transcript(SRT_BRACKETED.encode("utf-8"), "meeting.srt", "test")
    assert result.metadata.original_format == "srt"
    assert "Alice Chen" in result.speaker_labels
    assert "Bob Park" in result.speaker_labels
    assert len(result.turns) == 3
    assert result.turns[0].speaker_label == "Alice Chen"


# ---------------------------------------------------------------------------
# Edge Cases: CSV
# ---------------------------------------------------------------------------

CSV_EXTRA_COLUMNS = """\
Speaker,Text,Timestamp,Duration,Confidence
Alice,"Good morning everyone, let us start with the agenda.",0:00:01,4.5,0.95
Bob,"Thanks Alice, ready to discuss the quarterly review.",0:00:06,3.2,0.92
Carol,"I have the updated numbers from our finance team.",0:00:10,5.1,0.98
"""

CSV_QUOTED_COMMAS = """\
Speaker,Text,Timestamp
Alice,"Hello, everyone, welcome to our meeting today.",0:00:01
Bob,"Thanks, Alice, for the warm welcome and introduction.",0:00:05
Carol,"I have updates on items one, two, and three.",0:00:10
"""


def test_csv_extra_columns():
    """CSV with extra columns (duration, confidence) should be ignored."""
    result = parse_transcript(CSV_EXTRA_COLUMNS.encode("utf-8"), "transcript.csv", "test")
    assert len(result.turns) == 3
    assert "Alice" in result.speaker_labels


def test_csv_quoted_commas():
    """CSV with commas inside quoted fields should parse correctly."""
    result = parse_transcript(CSV_QUOTED_COMMAS.encode("utf-8"), "transcript.csv", "test")
    assert len(result.turns) == 3
    assert "everyone, welcome" in result.turns[0].text


# ---------------------------------------------------------------------------
# Edge Cases: JSON
# ---------------------------------------------------------------------------

JSON_NESTED = """\
{
  "data": {
    "results": {
      "segments": [
        {"speaker": "Alice", "text": "Nested segments should still be found by the parser.", "start": 1.0},
        {"speaker": "Bob", "text": "Yes the parser searches two levels deep for segment arrays.", "start": 5.0}
      ]
    }
  }
}
"""

JSON_NUMERIC_SPEAKER = """\
{
  "segments": [
    {"speaker": 0, "text": "Channel zero speaker says hello everyone this morning.", "start": 0.0},
    {"speaker": 1, "text": "Channel one speaker responds with a greeting for all.", "start": 3.0}
  ]
}
"""

JSON_MALFORMED = """\
{this is not valid json at all and should not crash the parser}
"""


def test_json_nested_segments():
    """JSON with segments nested under data.results.segments."""
    result = parse_transcript(JSON_NESTED.encode("utf-8"), "meeting.json", "test")
    assert result.metadata.original_format == "json"
    assert "Alice" in result.speaker_labels
    assert len(result.turns) == 2


def test_json_numeric_speaker():
    """JSON with numeric speaker IDs (channel numbers)."""
    result = parse_transcript(JSON_NUMERIC_SPEAKER.encode("utf-8"), "meeting.json", "test")
    assert len(result.turns) == 2
    # Numeric speakers should be converted to strings
    assert result.turns[0].speaker_label in ("0", "Unknown")


def test_json_malformed():
    """Malformed JSON should not crash — falls back gracefully."""
    result = parse_transcript(JSON_MALFORMED.encode("utf-8"), "meeting.json", "test")
    # Should produce at least a fallback turn (the raw text)
    assert len(result.turns) >= 1


# ---------------------------------------------------------------------------
# Edge Cases: Markdown
# ---------------------------------------------------------------------------

MD_INLINE_TEXT = """\
**Alice** 0:01 Good morning everyone, welcome to this meeting today.
**Bob** 0:05 Thanks Alice, I have updates from the engineering team.
**Carol** 0:10 I also have notes to share from the design review meeting.
"""

MD_NO_TIMESTAMPS = """\
**Alice**
Good morning everyone, welcome to this meeting today.

**Bob**
Thanks Alice, I have updates from the engineering team.

**Carol**
I also have notes to share from the design review meeting.
"""


def test_md_inline_text():
    """Markdown with text on the same line as **bold speaker** and timestamp."""
    result = parse_transcript(MD_INLINE_TEXT.encode("utf-8"), "transcript.md", "test")
    assert result.metadata.original_format == "md"
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "alice" in labels_lower
    assert "bob" in labels_lower
    assert len(result.turns) >= 2


def test_md_no_timestamps():
    """Markdown with bold speakers but no timestamps — Format D fallback."""
    result = parse_transcript(MD_NO_TIMESTAMPS.encode("utf-8"), "transcript.md", "test")
    assert result.metadata.original_format == "md"
    labels_lower = [s.lower() for s in result.speaker_labels]
    assert "alice" in labels_lower
    assert "bob" in labels_lower
    assert len(result.turns) >= 2


# ---------------------------------------------------------------------------
# Cross-Format Consistency
# ---------------------------------------------------------------------------

# Same 3-turn conversation encoded in every supported format
_CROSS_VTT = """\
WEBVTT

00:00:01.000 --> 00:00:05.000
<v Alice>Good morning everyone, welcome to this meeting today.

00:00:06.000 --> 00:00:10.000
<v Bob>Thanks Alice for the welcome and the introduction today.

00:00:11.000 --> 00:00:15.000
<v Carol>I have the quarterly numbers ready for the group.
"""

_CROSS_SRT = """\
1
00:00:01,000 --> 00:00:05,000
Alice: Good morning everyone, welcome to this meeting today.

2
00:00:06,000 --> 00:00:10,000
Bob: Thanks Alice for the welcome and the introduction today.

3
00:00:11,000 --> 00:00:15,000
Carol: I have the quarterly numbers ready for the group.
"""

_CROSS_TXT = """\
Alice: Good morning everyone, welcome to this meeting today.
Bob: Thanks Alice for the welcome and the introduction today.
Carol: I have the quarterly numbers ready for the group.
"""

_CROSS_CSV = """\
Speaker,Text,Timestamp
Alice,"Good morning everyone, welcome to this meeting today.",0:00:01
Bob,"Thanks Alice for the welcome and the introduction today.",0:00:06
Carol,"I have the quarterly numbers ready for the group.",0:00:11
"""

_CROSS_JSON = """\
{
  "segments": [
    {"speaker": "Alice", "text": "Good morning everyone, welcome to this meeting today.", "start": 1.0},
    {"speaker": "Bob", "text": "Thanks Alice for the welcome and the introduction today.", "start": 6.0},
    {"speaker": "Carol", "text": "I have the quarterly numbers ready for the group.", "start": 11.0}
  ]
}
"""

_CROSS_MD = """\
**Alice** 0:01
Good morning everyone, welcome to this meeting today.

**Bob** 0:06
Thanks Alice for the welcome and the introduction today.

**Carol** 0:11
I have the quarterly numbers ready for the group.
"""


def test_same_content_all_formats():
    """Same conversation in VTT, SRT, TXT, CSV, JSON, MD should produce
    matching speaker labels and turn counts."""
    cases = [
        (_CROSS_VTT, "test.vtt"),
        (_CROSS_SRT, "test.srt"),
        (_CROSS_TXT, "test.txt"),
        (_CROSS_CSV, "test.csv"),
        (_CROSS_JSON, "test.json"),
        (_CROSS_MD, "test.md"),
    ]
    results = []
    for content, fname in cases:
        r = parse_transcript(content.encode("utf-8"), fname, "test")
        results.append((fname, r))

    for fname, r in results:
        assert len(r.turns) == 3, f"{fname}: expected 3 turns, got {len(r.turns)}"
        labels = sorted(s.lower() for s in r.speaker_labels)
        assert labels == ["alice", "bob", "carol"], f"{fname}: speakers = {r.speaker_labels}"
        assert r.turns[0].turn_id == 1, f"{fname}: first turn_id != 1"
        assert r.metadata.word_count > 0, f"{fname}: word count = 0"
