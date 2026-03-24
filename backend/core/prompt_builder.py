"""
prompt_builder.py — Assembles the OpenAI user message for single_meeting and baseline_pack.

Also provides taxonomy loading utilities that read from the canonical
``clearvoice_pattern_taxonomy_v3.0.txt`` file (single source of truth).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .config import OUTPUT_MODE, SCHEMA_VERSION, TAXONOMY_VERSION
from .models import MemoryBlock, ParsedTranscript, PromptPayload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy loading — single source of truth
# ---------------------------------------------------------------------------

_TAXONOMY_FILE = Path(__file__).resolve().parent.parent.parent / "clearvoice_pattern_taxonomy_v3.0.txt"

_SECTION_BEGIN_RE = re.compile(r"^### BEGIN:(.+?) ###$", re.MULTILINE)
_SECTION_END_RE_TEMPLATE = "### END:{name} ###"


@lru_cache(maxsize=1)
def _load_taxonomy_raw() -> str:
    """Read the canonical taxonomy file. Cached after first call."""
    if not _TAXONOMY_FILE.exists():
        raise FileNotFoundError(f"Canonical taxonomy file not found at {_TAXONOMY_FILE}")
    return _TAXONOMY_FILE.read_text(encoding="utf-8")


def _extract_section(raw: str, section_name: str) -> str:
    """Extract content between ``### BEGIN:<name> ###`` and ``### END:<name> ###`` markers.

    Returns the content between the markers (excluding the marker lines themselves),
    stripped of leading/trailing whitespace.
    """
    begin_marker = f"### BEGIN:{section_name} ###"
    end_marker = f"### END:{section_name} ###"

    begin_idx = raw.find(begin_marker)
    if begin_idx == -1:
        raise ValueError(f"Section marker '{begin_marker}' not found in taxonomy file")

    content_start = begin_idx + len(begin_marker)
    end_idx = raw.find(end_marker, content_start)
    if end_idx == -1:
        raise ValueError(f"Section marker '{end_marker}' not found in taxonomy file")

    return raw[content_start:end_idx].strip()


def extract_pattern_ids() -> list[str]:
    """Return ordered list of pattern IDs from the taxonomy file.

    Parses ``### BEGIN:PATTERN:<id> ###`` markers in document order.
    """
    raw = _load_taxonomy_raw()
    ids: list[str] = []
    for m in _SECTION_BEGIN_RE.finditer(raw):
        section_name = m.group(1)
        if section_name.startswith("PATTERN:"):
            ids.append(section_name[len("PATTERN:"):])
    if not ids:
        raise ValueError("No PATTERN sections found in taxonomy file")
    return ids


def build_developer_message() -> str:
    """Build the full developer message from the canonical taxonomy file.

    Returns the entire taxonomy file content, which is used as the
    ``developer_message`` for single_meeting and baseline_pack LLM calls.
    This replaces the Airtable "Taxonomy Compact Block".
    """
    return _load_taxonomy_raw().strip()


def build_experiment_taxonomy_block() -> str:
    """Build the experiment-design-focused taxonomy summary.

    For each pattern, extracts from the canonical file:
    - What it measures
    - What good looks like (derived from success criteria)
    - Common failure mode
    - Experiment focus

    Returns a formatted block matching the structure previously embedded
    in ``system_prompt_next_experiment_v0_3_0.txt``.
    """
    raw = _load_taxonomy_raw()
    pattern_ids = extract_pattern_ids()

    lines = [
        "═══════════════════════════════════════════════════════════════",
        "PATTERN TAXONOMY — EXPERIMENT DESIGN GUIDE",
        "═══════════════════════════════════════════════════════════════",
        "",
        "The following 9 patterns define the coaching taxonomy. Use these definitions to understand what each pattern measures, what good looks like, and what kinds of interventions help.",
        "",
    ]

    for pid in pattern_ids:
        section = _extract_section(raw, f"PATTERN:{pid}")
        what_it_measures = _extract_field(section, "What it measures:")
        what_good = _extract_field(section, "What good looks like:")
        common_failure = _extract_field(section, "Common failure mode:")
        experiment_focus = _extract_field(section, "Experiment focus:")

        lines.append(f"── {pid} ──")
        lines.append(f"What it measures: {what_it_measures}")
        lines.append(f"What good looks like: {what_good}")
        lines.append(f"Common failure mode: {common_failure}")
        lines.append(f"Experiment focus: {experiment_focus}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _extract_field(section_text: str, field_label: str) -> str:
    """Extract a field value from a pattern section.

    Handles two formats:
    - Single-line after label: ``Field: value``
    - Next-line with dash: ``Field:\\n- value``

    For multi-line fields under "Experiment guidance:", looks within that sub-block.
    """
    # First check inside "Experiment guidance:" block
    exp_marker = "Experiment guidance:"
    exp_idx = section_text.find(exp_marker)

    search_text = section_text
    if field_label in ("What good looks like:", "Common failure mode:", "Experiment focus:") and exp_idx != -1:
        search_text = section_text[exp_idx:]

    # Find the field label with "- " prefix (inside Experiment guidance block)
    prefixed_label = f"- {field_label}"
    idx = search_text.find(prefixed_label)
    if idx != -1:
        value_start = idx + len(prefixed_label)
        # Value runs until the next "- " field or end of block
        rest = search_text[value_start:]
        next_field = rest.find("\n- ")
        if next_field != -1:
            return rest[:next_field].strip()
        return rest.strip()

    # Fall back to non-prefixed label
    idx = search_text.find(field_label)
    if idx == -1:
        return ""

    value_start = idx + len(field_label)
    rest = search_text[value_start:]

    # Check if value is on the same line
    first_newline = rest.find("\n")
    if first_newline == -1:
        return rest.strip()

    same_line = rest[:first_newline].strip()
    if same_line:
        return same_line

    # Value is on next line(s), starting with "- "
    after_newline = rest[first_newline + 1:]
    if after_newline.startswith("- "):
        end = after_newline.find("\n\n")
        if end != -1:
            return after_newline[2:end].strip()
        return after_newline[2:].strip()

    return same_line



# Appended to every user message to reinforce rules the model tends to violate.
_HARD_REMINDERS = """

Hard reminders:
- JSON only; no prose/markdown.
- evaluation_summary: Every one of the 9 pattern_ids must appear in EXACTLY ONE of patterns_evaluated, patterns_insufficient_signal, or patterns_not_evaluable. No pattern may be omitted.
- CRITICAL: evaluation_summary MUST be consistent with pattern_snapshot. A pattern is in patterns_evaluated if and only if its evaluable_status is "evaluable" in pattern_snapshot. A pattern is in patterns_insufficient_signal if and only if its evaluable_status is "insufficient_signal". A pattern is in patterns_not_evaluable if and only if its evaluable_status is "not_evaluable". Any mismatch between these two sections is a hard error.
- pattern_snapshot must include all 9 pattern IDs in required order, each with cluster_id and scoring_type. pattern_snapshot contains SCORING ONLY — no notes, coaching_note, suggested_rewrite, or rewrite_for_span_id.
- participation_management includes balance_assessment annotation when evaluable.
- evidence_spans: turn_start_id/turn_end_id must be integers. evidence_span_id must be turn-anchored: ES-T{start} or ES-T{start}-{end}. Each span must include event_ids linking to its source opportunity_events.
- opportunity_events: top-level array. Each OE must include pattern_id. OE event_ids must be referenced by evidence_spans.
- coaching.focus length=1, coaching.micro_experiment length=1. Focus and strengths items only need {pattern_id, message}.
- coaching.pattern_coaching: array of per-pattern coaching items. Each has pattern_id, notes, coaching_note, suggested_rewrite, rewrite_for_span_id. rewrite_for_span_id must be chosen from a missed-opportunity span (NOT in success_evidence_span_ids). Pick the clearest example for a meaningful rewrite. Avoid rewriting very short or garbled excerpts.
- coaching.experiment_coaching: set for partial experiment attempts only (coaching_note + suggested_rewrite + rewrite_for_span_id). Null otherwise.
- Before finalizing, re-check that each evidence span counted in a pattern's opportunity_count is a genuine opportunity per the taxonomy definition. Remove clear mismatches (e.g., a non-question counted under question_quality, or a 2-word fragment). For question_quality specifically, exclude procedural/technical questions (audio checks, roll call, scheduling logistics) from both scoring and opportunity_count — never quote them as evidence or in coaching. Do NOT remove spans simply because the transcript has rough ASR formatting — read past missing punctuation and filler words to assess the speaker's actual behavior.
- CRITICAL: Every notes and coaching_note field in coaching.pattern_coaching must specifically reference the behavior observed in the cited evidence spans. Do not write generic observations disconnected from the actual quotes.
- CRITICAL: success_evidence_span_ids must be consistent with opportunity event scores. binary/dual_element require success >= 1.0; tiered_rubric/complexity_tiered require success >= 0.75; multi_element requires success >= 0.8. Classify spans BEFORE selecting rewrite_for_span_id — do NOT adjust the success list to satisfy the rewrite constraint.
- CRITICAL: After writing suggested_rewrite in coaching.pattern_coaching, re-read the excerpt of rewrite_for_span_id and confirm the rewrite addresses the SAME topic and conversational moment. If the topics differ, either fix the span ID or rewrite the text.
- CRITICAL: Before finalizing, self-audit: (1) every counted OE must have a corresponding evidence span; (2) every evidence_span_id in pattern_snapshot must exist in evidence_spans; (3) opportunity_count must equal counted OEs; (4) rewrite_for_span_id must reference an existing, non-success span.
- CRITICAL: Never reference turn numbers, evidence_span_ids, event_ids, or any internal identifier in coaching text (notes, coaching_note, executive_summary, strengths, focus). Describe moments by what the speaker said or did."""


def _generate_analysis_id() -> str:
    """Generate a date-stamped analysis ID (A-YYMMDD format)."""
    now = datetime.now(timezone.utc)
    return f"A-{now.strftime('%y%m%d')}"


def _meta_block(analysis_type: str, analysis_id: Optional[str] = None) -> dict:
    return {
        "analysis_id": analysis_id or _generate_analysis_id(),
        "analysis_type": analysis_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": TAXONOMY_VERSION,
        "output_mode": OUTPUT_MODE,
        "schema_hash": None,
    }


def build_single_meeting_prompt(
    *,
    meeting_id: str,
    meeting_type: str,
    target_role: str,
    meeting_date: str,
    target_speaker_name: str,
    target_speaker_label: str,
    parsed_transcript: ParsedTranscript,
    memory: MemoryBlock,
    analysis_id: Optional[str] = None,
) -> PromptPayload:
    """
    Build the user message payload for a single_meeting analysis.
    """
    meta = _meta_block("single_meeting", analysis_id)

    context = {
        "meeting_id": meeting_id,
        "meeting_type": meeting_type,
        "target_role": target_role,
        "meeting_date": meeting_date,
        "target_speaker_name": target_speaker_name,
        "target_speaker_label": target_speaker_label,
    }

    # Turns: include speaker_role_hint (null OK)
    turns_payload = [
        {
            "speaker_label": t.speaker_label,
            "text": t.text,
            "turn_id": t.turn_id,
            "speaker_role_hint": t.speaker_role_hint,
        }
        for t in parsed_transcript.turns
    ]

    transcript_payload = {
        "source_id": parsed_transcript.source_id,
        "turns": turns_payload,
    }

    input_payload = {
        "meta": meta,
        "context": context,
        "memory": memory.model_dump(),
        "transcript": transcript_payload,
    }

    user_message = (
        "Analyze and return ONLY one JSON object conforming to mvp.v0.4.0.\n\n"
        "INPUT_PAYLOAD\n"
        + json.dumps(input_payload, ensure_ascii=False, indent=2)
        + _HARD_REMINDERS
    )

    return PromptPayload(
        analysis_type="single_meeting",
        meta=meta,
        context=context,
        memory=memory,
        transcript_payload=transcript_payload,
        raw_user_message=user_message,
    )


_BASELINE_HARD_REMINDERS = """

Hard reminders (baseline_pack):
- JSON only; no prose/markdown.
- You are SYNTHESISING pre-analysed meetings — do NOT fabricate evidence. Every evidence_span_id, turn_start_id, turn_end_id, and excerpt in your output must be copied exactly from the input meeting summaries.
- Every evidence_span MUST include meeting_id. This is required for baseline_pack.
- evaluation_summary: Every one of the 9 pattern_ids must appear in EXACTLY ONE of patterns_evaluated, patterns_insufficient_signal, or patterns_not_evaluable. Must be consistent with pattern_snapshot evaluable_status.
- pattern_snapshot must include all 9 pattern IDs in required order, each with cluster_id and scoring_type. pattern_snapshot contains SCORING ONLY — no coaching fields.
- Score = WEIGHTED AVERAGE of meeting-level scores (weighted by opportunity_count). Opportunity_count = SUM of meeting opportunity_counts.
- participation_management includes balance_assessment annotation when evaluable.
- coaching.focus length=1, coaching.micro_experiment length=1. Focus and strengths items only need {pattern_id, message}.
- coaching.pattern_coaching: array of per-pattern coaching items (pattern_id, notes, coaching_note, suggested_rewrite, rewrite_for_span_id).
- coaching.experiment_coaching MUST be null for baseline_pack.
- detection_in_this_meeting MUST be null for baseline_pack.
- opportunity_events MUST be an empty array for baseline_pack.
- CRITICAL: Every notes and coaching_note field in coaching.pattern_coaching must reference specific behaviour from the cited evidence spans. Do not write generic observations.
- In notes and coaching_note fields, describe behaviour in plain language. Do NOT reference evidence_span_ids (e.g. "ES-T051") or meeting_ids (e.g. "M-000153") in the text — these are internal identifiers that are not meaningful to the coachee.
- Do NOT generate new evidence_span_ids. Only use IDs from the input meeting summaries."""


def build_baseline_pack_prompt(
    *,
    baseline_pack_id: str,
    pack_size: int,
    target_role: str,
    role_consistency: Optional[str],
    meeting_type_consistency: Optional[str],
    meetings_meta: list[dict],  # [{meeting_id, meeting_type, target_speaker_name, target_speaker_label, target_speaker_role}]
    meeting_summaries: list[dict],  # enriched run output dicts with evidence_spans
    analysis_id: Optional[str] = None,
) -> PromptPayload:
    """
    Build the user message payload for a baseline_pack analysis.

    The meeting_summaries contain enriched single-meeting outputs including
    evidence_spans, per-pattern notes/coaching, and coaching messages so the
    LLM can select and pass through real evidence.
    """
    meta = _meta_block("baseline_pack", analysis_id)

    # Determine if roles differ
    roles = {m.get("target_speaker_role") for m in meetings_meta}
    if len(roles) > 1:
        effective_role = "mixed"
    else:
        effective_role = target_role

    meetings_list_for_context = [
        {"meeting_id": m["meeting_id"], "meeting_type": m["meeting_type"]}
        for m in meetings_meta
    ]

    context = {
        "baseline_pack_id": baseline_pack_id,
        "pack_size": pack_size,
        "meetings": meetings_list_for_context,
        "target_role": effective_role,
        "role_consistency": role_consistency == "consistent",
        "meeting_type_consistency": meeting_type_consistency == "consistent",
    }

    memory = MemoryBlock()  # always null for baseline pack

    input_payload = {
        "meta": meta,
        "context": context,
        "memory": memory.model_dump(),
        "meeting_summaries": meeting_summaries,
    }

    user_message = (
        "Synthesize and return ONLY one JSON object conforming to mvp.v0.4.0.\n\n"
        "INPUT_PAYLOAD\n"
        + json.dumps(input_payload, ensure_ascii=False, indent=2)
        + _BASELINE_HARD_REMINDERS
    )

    return PromptPayload(
        analysis_type="baseline_pack",
        meta=meta,
        context=context,
        memory=memory,
        transcript_payload={"source_id": baseline_pack_id, "meeting_summaries": meeting_summaries},
        raw_user_message=user_message,
    )


def build_memory_block(
    *,
    baseline_pack_id: Optional[str] = None,
    strengths: Optional[list[str]] = None,
    focus_pattern: Optional[str] = None,
    active_experiment: Optional[dict] = None,
    recent_snapshots: Optional[list[dict]] = None,
) -> MemoryBlock:
    """
    Assemble the memory block for a single_meeting prompt.

    If there is no active baseline or experiment, returns a null memory block.
    """
    if not baseline_pack_id and not active_experiment:
        return MemoryBlock(
            baseline_profile=None,
            active_experiment=None,
            recent_pattern_snapshots=[],
        )

    baseline_profile: Optional[dict] = None
    if baseline_pack_id:
        baseline_profile = {
            "strengths": strengths or [],
            "focus": focus_pattern,
            "baseline_pack_id": baseline_pack_id,
        }

    active_exp_block: Optional[dict] = None
    if active_experiment:
        active_exp_block = {
            "experiment_id": active_experiment.get("experiment_id"),
            "title": active_experiment.get("title"),
            "instruction": active_experiment.get("instruction"),
            "success_marker": active_experiment.get("success_marker"),
            "pattern_id": active_experiment.get("pattern_id"),
            "status": active_experiment.get("status"),
        }

    return MemoryBlock(
        baseline_profile=baseline_profile,
        active_experiment=active_exp_block,
        recent_pattern_snapshots=recent_snapshots or [],
    )
