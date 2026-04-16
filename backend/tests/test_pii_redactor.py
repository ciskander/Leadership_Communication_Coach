"""
test_pii_redactor.py — Unit tests for the PII redaction module.
"""
from __future__ import annotations

import pytest

from backend.core.models import ParsedTranscript, TranscriptMetadata, Turn
from backend.core.pii_redactor import (
    RedactionConfig,
    _build_whitelist,
    _is_whitelisted,
    _TokenCounter,
    load_redaction_config,
    redact_transcript,
    turns_to_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(turns: list[tuple[str, str]], speakers: list[str] | None = None) -> ParsedTranscript:
    """Build a minimal ParsedTranscript from (speaker, text) pairs."""
    turn_objs = [
        Turn(turn_id=i, speaker_label=spk, text=txt)
        for i, (spk, txt) in enumerate(turns)
    ]
    if speakers is None:
        speakers = sorted({spk for spk, _ in turns})
    return ParsedTranscript(
        source_id="test",
        turns=turn_objs,
        speaker_labels=speakers,
        metadata=TranscriptMetadata(
            original_format="txt",
            turn_count=len(turn_objs),
            word_count=sum(len(t.text.split()) for t in turn_objs),
        ),
    )


def _default_config(**overrides) -> RedactionConfig:
    defaults = dict(
        enabled=True,
        aggressiveness="standard",
        reversible=True,
        redact_org_names=False,
        speaker_whitelist=["Alice Johnson", "Bob Smith"],
    )
    defaults.update(overrides)
    return RedactionConfig(**defaults)


# ---------------------------------------------------------------------------
# Whitelist helpers
# ---------------------------------------------------------------------------

class TestBuildWhitelist:
    def test_full_names_and_tokens(self):
        wl = _build_whitelist(["Alice Johnson", "Bob Smith"])
        assert "Alice Johnson" in wl
        assert "Alice" in wl
        assert "Johnson" in wl
        assert "Bob" in wl

    def test_single_name(self):
        wl = _build_whitelist(["Priya"])
        assert "Priya" in wl

    def test_skips_single_char_tokens(self):
        wl = _build_whitelist(["J Smith"])
        assert "J" not in wl
        assert "Smith" in wl

    def test_empty_labels(self):
        wl = _build_whitelist([])
        assert wl == []

    def test_strips_whitespace(self):
        wl = _build_whitelist(["  Alice  "])
        assert "Alice" in wl


class TestIsWhitelisted:
    def test_exact_match(self):
        assert _is_whitelisted("alice", {"alice", "bob"})

    def test_case_insensitive(self):
        assert _is_whitelisted("Alice", {"alice", "bob"})

    def test_no_match(self):
        assert not _is_whitelisted("Charlie", {"alice", "bob"})


# ---------------------------------------------------------------------------
# Token counter
# ---------------------------------------------------------------------------

class TestTokenCounter:
    def test_consistent_tokens(self):
        tc = _TokenCounter()
        t1 = tc.get_token("PERSON", "Jane Doe")
        t2 = tc.get_token("PERSON", "Jane Doe")
        assert t1 == t2 == "<PERSON_1>"

    def test_different_people_get_different_tokens(self):
        tc = _TokenCounter()
        t1 = tc.get_token("PERSON", "Jane Doe")
        t2 = tc.get_token("PERSON", "Mark Wilson")
        assert t1 == "<PERSON_1>"
        assert t2 == "<PERSON_2>"

    def test_different_entity_types(self):
        tc = _TokenCounter()
        t1 = tc.get_token("PERSON", "Jane")
        t2 = tc.get_token("EMAIL_ADDRESS", "jane@example.com")
        assert t1 == "<PERSON_1>"
        assert t2 == "<EMAIL_ADDRESS_1>"

    def test_case_insensitive_dedup(self):
        tc = _TokenCounter()
        t1 = tc.get_token("PERSON", "Jane Doe")
        t2 = tc.get_token("PERSON", "jane doe")
        assert t1 == t2


# ---------------------------------------------------------------------------
# load_redaction_config
# ---------------------------------------------------------------------------

class TestLoadRedactionConfig:
    def test_defaults_when_empty(self):
        cfg = load_redaction_config({}, speaker_labels=["Alice"])
        assert cfg.enabled is True
        assert cfg.aggressiveness == "standard"
        assert cfg.reversible is True
        assert cfg.redact_org_names is False
        assert cfg.speaker_whitelist == ["Alice"]

    def test_reads_airtable_fields(self):
        cfg = load_redaction_config(
            {
                "Redaction Enabled": False,
                "Redaction Aggressiveness": "conservative",
                "Redaction Reversible": False,
                "Redaction Org Names": True,
            },
            speaker_labels=["Bob"],
        )
        assert cfg.enabled is False
        assert cfg.aggressiveness == "conservative"
        assert cfg.reversible is False
        assert cfg.redact_org_names is True


# ---------------------------------------------------------------------------
# redact_transcript — requires Presidio + spaCy model
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _presidio_available():
    """Skip tests if Presidio or spaCy model not installed."""
    try:
        import presidio_analyzer  # noqa: F401
        import spacy
        spacy.load("en_core_web_lg")
    except (ImportError, OSError):
        pytest.skip("Presidio or spaCy en_core_web_lg model not available")


class TestRedactTranscript:
    """Integration tests requiring Presidio + spaCy."""

    def test_disabled_returns_unchanged(self):
        """Does not require Presidio."""
        transcript = _make_transcript([("Alice", "Hello world")])
        config = _default_config(enabled=False)
        result = redact_transcript(transcript, config)
        assert result.redacted_transcript.turns[0].text == "Hello world"
        assert result.audit_entries == []
        assert result.entity_counts == {}

    def test_email_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Send it to sarah@example.com please")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "sarah@example.com" not in text
        assert "<EMAIL_ADDRESS_1>" in text
        assert "EMAIL_ADDRESS" in result.entity_counts

    def test_phone_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Call me at 555-867-5309")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "555-867-5309" not in text

    def test_speaker_labels_preserved(self, _presidio_available):
        transcript = _make_transcript(
            [
                ("Alice Johnson", "I think we should ask Bob Smith about this."),
                ("Bob Smith", "Sure, Alice, let me check."),
            ],
            speakers=["Alice Johnson", "Bob Smith"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson", "Bob Smith"])
        result = redact_transcript(transcript, config)
        # Speaker names within text should NOT be redacted
        assert "Bob Smith" in result.redacted_transcript.turns[0].text or "Bob" in result.redacted_transcript.turns[0].text
        assert "Alice" in result.redacted_transcript.turns[1].text

    def test_non_participant_names_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "I spoke with Sarah Williams from accounting yesterday.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        # Sarah Williams should be redacted (not a speaker)
        assert "Sarah Williams" not in text

    def test_consistent_tokens_across_turns(self, _presidio_available):
        transcript = _make_transcript(
            [
                ("Alice Johnson", "Contact sarah@example.com for details."),
                ("Bob Smith", "I'll email sarah@example.com too."),
            ],
            speakers=["Alice Johnson", "Bob Smith"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson", "Bob Smith"])
        result = redact_transcript(transcript, config)
        t0 = result.redacted_transcript.turns[0].text
        t1 = result.redacted_transcript.turns[1].text
        # Same email should get the same token in both turns
        assert "<EMAIL_ADDRESS_1>" in t0
        assert "<EMAIL_ADDRESS_1>" in t1

    def test_reversible_mapping(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Email sarah@example.com please")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(reversible=True, speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        # Mapping should contain the original text
        assert len(result.mapping.token_to_original) > 0
        # At least the email should be in the mapping
        found_email = any("sarah@example.com" in v for v in result.mapping.token_to_original.values())
        assert found_email

    def test_permissive_skips_person(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "I met with Sarah Williams and she emailed me at sarah@example.com")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(aggressiveness="permissive", speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        # Permissive mode: PERSON is OFF, so Sarah Williams should remain
        assert "Sarah Williams" in text
        # But email should still be redacted
        assert "sarah@example.com" not in text

    def test_empty_transcript(self):
        """Does not require Presidio."""
        transcript = _make_transcript([], speakers=[])
        config = _default_config(speaker_whitelist=[])
        result = redact_transcript(transcript, config)
        assert result.redacted_transcript.turns == []
        assert result.entity_counts == {}

    def test_audit_entries_populated(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Email sarah@example.com or call 555-123-4567")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        assert len(result.audit_entries) > 0
        entity_types = {e.entity_type for e in result.audit_entries}
        assert "EMAIL_ADDRESS" in entity_types


# ---------------------------------------------------------------------------
# Custom recognizer tests
# ---------------------------------------------------------------------------

class TestCustomRecognizers:
    """Tests for custom PatternRecognizer-based PII types."""

    def test_us_address_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Send it to 4400 Riverside Drive, Suite 210, Columbus, OH 43215 please.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "4400 Riverside Drive" not in text
        assert "43215" not in text
        assert "<PHYSICAL_ADDRESS_1>" in text

    def test_canadian_address_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Our office is at 150 Elgin Street, Suite 400, Ottawa, ON K2P 1L4.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "150 Elgin Street" not in text
        assert "K2P 1L4" not in text

    def test_api_key_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "The API key is sk-staging-4kR9mXvL02pBqTnYwZeA and the webhook secret is whsec_7fGh3Jk2NmPqRs8TuVwXy.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "sk-staging-4kR9mXvL02pBqTnYwZeA" not in text
        assert "whsec_7fGh3Jk2NmPqRs8TuVwXy" not in text
        assert "<API_KEY_" in text

    def test_employee_id_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "His employee ID is EMP-77423 if you need it.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "EMP-77423" not in text
        assert "<EMPLOYEE_ID_1>" in text

    def test_partial_credit_card_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "We'll put this on the corporate Amex ending in 4491, expiry 09/27.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "4491" not in text
        assert "<PARTIAL_CREDIT_CARD_" in text

    def test_date_of_birth_redacted(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "The patient's DOB March 14, 1968 is on file.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "March 14, 1968" not in text
        assert "<DATE_OF_BIRTH_1>" in text

    def test_dob_numeric_format(self, _presidio_available):
        transcript = _make_transcript(
            [("Alice Johnson", "Date of birth: 03/14/1968.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        assert "03/14/1968" not in text

    def test_generic_date_not_redacted(self, _presidio_available):
        """Generic dates without DOB context should NOT be redacted."""
        transcript = _make_transcript(
            [("Alice Johnson", "The meeting is scheduled for March 14, 2026.")],
            speakers=["Alice Johnson"],
        )
        config = _default_config(speaker_whitelist=["Alice Johnson"])
        result = redact_transcript(transcript, config)
        text = result.redacted_transcript.turns[0].text
        # Generic date should remain (no DOB/born context)
        assert "March 14, 2026" in text


# ---------------------------------------------------------------------------
# turns_to_text
# ---------------------------------------------------------------------------

class TestTurnsToText:
    def test_basic(self):
        transcript = _make_transcript([("Alice", "Hello"), ("Bob", "Hi there")])
        text = turns_to_text(transcript)
        assert text == "Alice: Hello\nBob: Hi there"

    def test_empty(self):
        transcript = _make_transcript([], speakers=[])
        assert turns_to_text(transcript) == ""
