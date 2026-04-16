"""
pii_redactor.py — PII redaction for transcripts using Microsoft Presidio.

Redacts personally identifiable information from transcript turns before
they are sent to the LLM, while preserving speaker labels (meeting
participant names) so coaching can reference them by name.

Settings are read from the Airtable Config table. Missing fields gracefully
fall back to safe defaults.
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .models import ParsedTranscript, Turn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_AGGRESSIVENESS_LEVELS = {"conservative", "standard", "permissive"}

# Entities enabled per aggressiveness level
_ENTITIES_BY_LEVEL: dict[str, set[str]] = {
    "conservative": {
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
        "US_SSN", "CREDIT_CARD", "US_PASSPORT", "US_DRIVER_LICENSE",
        "IP_ADDRESS", "LOCATION", "URL", "NRP", "MEDICAL_LICENSE",
    },
    "standard": {
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
        "US_SSN", "CREDIT_CARD", "US_PASSPORT", "US_DRIVER_LICENSE",
        "IP_ADDRESS", "NRP", "MEDICAL_LICENSE",
    },
    "permissive": {
        "EMAIL_ADDRESS", "PHONE_NUMBER",
        "US_SSN", "CREDIT_CARD", "US_PASSPORT", "US_DRIVER_LICENSE",
        "MEDICAL_LICENSE",
    },
}


@dataclass
class RedactionConfig:
    enabled: bool = True
    aggressiveness: str = "standard"
    reversible: bool = True
    redact_org_names: bool = False
    speaker_whitelist: list[str] = field(default_factory=list)


@dataclass
class RedactionMapping:
    token_to_original: dict[str, str] = field(default_factory=dict)
    original_to_token: dict[str, str] = field(default_factory=dict)


@dataclass
class RedactionAuditEntry:
    entity_type: str
    replacement_token: str
    turn_id: int
    char_start: int
    char_end: int


@dataclass
class RedactionResult:
    redacted_transcript: ParsedTranscript
    mapping: RedactionMapping
    audit_entries: list[RedactionAuditEntry]
    entity_counts: dict[str, int]


# ---------------------------------------------------------------------------
# Lazy-loaded Presidio singleton
# ---------------------------------------------------------------------------

_analyzer_engine = None
_anonymizer_engine = None


def _get_analyzer():
    """Return a cached AnalyzerEngine (loads spaCy model on first call)."""
    global _analyzer_engine
    if _analyzer_engine is None:
        from presidio_analyzer import AnalyzerEngine
        logger.info("Initializing Presidio AnalyzerEngine (loading spaCy model)…")
        _analyzer_engine = AnalyzerEngine()
        logger.info("Presidio AnalyzerEngine ready.")
    return _analyzer_engine


def _get_anonymizer():
    global _anonymizer_engine
    if _anonymizer_engine is None:
        from presidio_anonymizer import AnonymizerEngine
        _anonymizer_engine = AnonymizerEngine()
    return _anonymizer_engine


# ---------------------------------------------------------------------------
# Speaker whitelist helpers
# ---------------------------------------------------------------------------

def _build_whitelist(speaker_labels: list[str]) -> list[str]:
    """Build a case-insensitive whitelist from speaker labels.

    Includes full names and individual name tokens so that references like
    "John mentioned..." are preserved when "John Smith" is a speaker.
    """
    whitelist: set[str] = set()
    for label in speaker_labels:
        label_clean = label.strip()
        if not label_clean:
            continue
        whitelist.add(label_clean)
        # Add individual name tokens (first name, last name, etc.)
        tokens = label_clean.split()
        for token in tokens:
            if len(token) >= 2:  # skip single-letter initials
                whitelist.add(token)
    return sorted(whitelist)


def _is_whitelisted(text: str, whitelist_lower: set[str]) -> bool:
    """Check if a detected entity text matches a whitelisted speaker name."""
    return text.strip().lower() in whitelist_lower


# ---------------------------------------------------------------------------
# Consistent tokenization
# ---------------------------------------------------------------------------

class _TokenCounter:
    """Assigns consistent replacement tokens across all turns."""

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._seen: dict[str, str] = {}  # normalized original → token

    def get_token(self, entity_type: str, original_text: str) -> str:
        """Return a stable token for the given entity text."""
        key = (entity_type, original_text.strip().lower())
        if key in self._seen:
            return self._seen[key]
        self._counters[entity_type] = self._counters.get(entity_type, 0) + 1
        token = f"<{entity_type}_{self._counters[entity_type]}>"
        self._seen[key] = token
        return token


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def load_redaction_config(
    cfg_fields: dict,
    speaker_labels: list[str],
) -> RedactionConfig:
    """Build a RedactionConfig from Airtable Config fields.

    Missing fields fall back to safe defaults.
    """
    return RedactionConfig(
        enabled=cfg_fields.get("Redaction Enabled", True),
        aggressiveness=cfg_fields.get("Redaction Aggressiveness", "standard"),
        reversible=cfg_fields.get("Redaction Reversible", True),
        redact_org_names=bool(cfg_fields.get("Redaction Org Names", False)),
        speaker_whitelist=list(speaker_labels),
    )


def redact_transcript(
    parsed: ParsedTranscript,
    config: RedactionConfig,
) -> RedactionResult:
    """Redact PII from a parsed transcript.

    Returns a deep copy of the transcript with PII replaced by consistent
    tokens (e.g., ``<PERSON_1>``, ``<EMAIL_1>``), plus a reversible mapping
    and audit log.
    """
    if not config.enabled:
        return RedactionResult(
            redacted_transcript=parsed,
            mapping=RedactionMapping(),
            audit_entries=[],
            entity_counts={},
        )

    # Validate aggressiveness
    level = config.aggressiveness if config.aggressiveness in _AGGRESSIVENESS_LEVELS else "standard"

    # Build entity list
    entities = set(_ENTITIES_BY_LEVEL[level])
    if config.redact_org_names and level != "permissive":
        entities.add("ORGANIZATION")

    # Build whitelist (lowered for comparison)
    whitelist_terms = _build_whitelist(config.speaker_whitelist)
    whitelist_lower = {t.lower() for t in whitelist_terms}

    analyzer = _get_analyzer()
    token_counter = _TokenCounter()
    audit_entries: list[RedactionAuditEntry] = []
    entity_counts: dict[str, int] = {}

    # Deep-copy turns so we don't mutate the original
    redacted_turns: list[Turn] = []

    for turn in parsed.turns:
        # Analyze the turn text
        results = analyzer.analyze(
            text=turn.text,
            entities=list(entities),
            language="en",
            allow_list=whitelist_terms,
        )

        if not results:
            redacted_turns.append(turn.model_copy(deep=True))
            continue

        # Sort results by start position descending so we can replace
        # from right to left without shifting offsets
        results_sorted = sorted(results, key=lambda r: r.start, reverse=True)

        new_text = turn.text
        for result in results_sorted:
            original_span = turn.text[result.start:result.end]

            # Double-check whitelist (Presidio's allow_list uses exact match;
            # we also want substring matching for partial names)
            if _is_whitelisted(original_span, whitelist_lower):
                continue

            token = token_counter.get_token(result.entity_type, original_span)
            new_text = new_text[:result.start] + token + new_text[result.end:]

            entity_counts[result.entity_type] = entity_counts.get(result.entity_type, 0) + 1
            audit_entries.append(RedactionAuditEntry(
                entity_type=result.entity_type,
                replacement_token=token,
                turn_id=turn.turn_id,
                char_start=result.start,
                char_end=result.end,
            ))

        redacted_turns.append(turn.model_copy(update={"text": new_text}))

    # Build the mapping from the token counter
    mapping = RedactionMapping(
        token_to_original={v: k[1] for k, v in token_counter._seen.items()},
        original_to_token={k[1]: v for k, v in token_counter._seen.items()},
    )
    # Fix token_to_original to use original-cased text
    # (the counter stores lowered keys; rebuild from audit entries)
    if config.reversible:
        _rebuild_mapping_casing(mapping, audit_entries, parsed.turns)

    redacted_transcript = parsed.model_copy(update={"turns": redacted_turns})

    if entity_counts:
        logger.info(
            "PII redaction complete: %s",
            ", ".join(f"{k}={v}" for k, v in sorted(entity_counts.items())),
        )

    return RedactionResult(
        redacted_transcript=redacted_transcript,
        mapping=mapping,
        audit_entries=audit_entries,
        entity_counts=entity_counts,
    )


def _rebuild_mapping_casing(
    mapping: RedactionMapping,
    audit_entries: list[RedactionAuditEntry],
    original_turns: list[Turn],
) -> None:
    """Rebuild token_to_original with original casing from the source text."""
    token_to_original: dict[str, str] = {}
    for entry in audit_entries:
        if entry.replacement_token in token_to_original:
            continue  # keep first occurrence
        for turn in original_turns:
            if turn.turn_id == entry.turn_id:
                original_span = turn.text[entry.char_start:entry.char_end]
                token_to_original[entry.replacement_token] = original_span
                break
    mapping.token_to_original = token_to_original
    mapping.original_to_token = {v: k for k, v in token_to_original.items()}


def turns_to_text(parsed: ParsedTranscript) -> str:
    """Reconstruct plain text from a ParsedTranscript's turns."""
    lines = []
    for turn in parsed.turns:
        lines.append(f"{turn.speaker_label}: {turn.text}")
    return "\n".join(lines)
