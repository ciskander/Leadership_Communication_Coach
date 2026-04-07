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

_TAXONOMY_FILE = Path(__file__).resolve().parent.parent.parent / "clearvoice_pattern_taxonomy_v4.0.txt"

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


def extract_stage2_pattern_definitions() -> str:
    """Extract condensed pattern definitions for the Stage 2 coaching prompt.

    For each pattern, extracts from the canonical taxonomy file:
    - What it measures (from "What it measures:" field)
    - NOT this pattern (from "Excluded from both numerator AND denominator" section)
    - Disambiguation (from "Detection notes:" focusing on cross-pattern distinctions)

    Produces output matching the format of ``stage2_pattern_definitions_v0.1.txt``,
    replacing that separate file with programmatic extraction from the single
    source of truth.
    """
    raw = _load_taxonomy_raw()
    pattern_ids = extract_pattern_ids()

    lines: list[str] = []
    for pid in pattern_ids:
        section = _extract_section(raw, f"PATTERN:{pid}")

        # Extract "What it measures"
        what_it_measures = _extract_stage2_field(section, "What it measures:")

        # Extract "NOT this pattern" from the exclusion section
        not_this = _extract_stage2_exclusion_summary(section)

        # Extract disambiguation hints from detection notes
        disambiguation = _extract_stage2_disambiguation(section)

        lines.append(f"--- {pid} ---")
        lines.append(f"What it measures: {what_it_measures}")
        if not_this:
            lines.append(f"NOT this pattern: {not_this}")
        if disambiguation:
            lines.append(f"Disambiguation: {disambiguation}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _extract_stage2_field(section_text: str, field_label: str) -> str:
    """Extract a simple field value that follows a label, up to the next blank line or section."""
    idx = section_text.find(field_label)
    if idx == -1:
        return ""
    value_start = idx + len(field_label)
    rest = section_text[value_start:]
    # Take up to the next double newline or next section header
    end = rest.find("\n\n")
    if end == -1:
        return rest.strip()
    return rest[:end].strip().lstrip("- ")


def _extract_stage2_exclusion_summary(section_text: str) -> str:
    """Extract a concise NOT-this-pattern summary from the exclusion rules."""
    # Look for "Excluded from both numerator AND denominator" section
    markers = [
        "Excluded from both numerator AND denominator",
        "Excluded from both numerator and denominator",
    ]
    idx = -1
    for marker in markers:
        idx = section_text.find(marker)
        if idx != -1:
            break
    if idx == -1:
        return ""

    # Find the content after the marker (skip the header line)
    rest = section_text[idx:]
    first_newline = rest.find("\n")
    if first_newline == -1:
        return ""
    content = rest[first_newline + 1:]

    # Collect bullet points until we hit a non-bullet section
    items: list[str] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            # Take just the core description, strip examples in parens
            item = stripped[2:]
            # Truncate at first example parenthetical for brevity
            paren_idx = item.find("(e.g.,")
            if paren_idx == -1:
                paren_idx = item.find("(e.g.")
            if paren_idx > 0:
                item = item[:paren_idx].rstrip(" ,;—")
            items.append(item.rstrip("."))
            if len(items) >= 4:  # Keep it concise
                break
        elif stripped and not stripped.startswith("-"):
            break  # Hit the next section

    return "; ".join(items) + "." if items else ""


def _extract_stage2_disambiguation(section_text: str) -> str:
    """Extract disambiguation hints relevant for coaching alignment checks.

    Looks for cross-pattern distinction notes in the Detection notes section
    and Role notes that clarify what does/doesn't belong to this pattern.
    """
    # Look for explicit "Disambiguation" or cross-pattern notes in Detection notes
    detection_idx = section_text.find("Detection notes:")
    if detection_idx == -1:
        return ""

    detection_section = section_text[detection_idx:]
    # Find the end of detection notes (next major section)
    next_section = detection_section.find("\nExperiment guidance:")
    if next_section == -1:
        next_section = detection_section.find("\n### END:")
    if next_section != -1:
        detection_section = detection_section[:next_section]

    # Look for lines that mention other patterns (cross-pattern disambiguation)
    disambiguation_parts: list[str] = []
    for line in detection_section.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") and any(
            kw in stripped.lower()
            for kw in ["not this pattern", "belongs to", "classify under",
                       "distinct from", "not ", "rather than", "repackag"]
        ):
            item = stripped[2:].rstrip(".")
            disambiguation_parts.append(item)
            if len(disambiguation_parts) >= 2:
                break

    # Also check for a dedicated "Coaching materiality" or similar note
    materiality_idx = section_text.find("Coaching materiality:")
    if materiality_idx != -1:
        rest = section_text[materiality_idx:]
        end = rest.find("\n\n")
        if end != -1:
            note = rest[len("Coaching materiality:"):end].strip().lstrip("- ")
            disambiguation_parts.append(note)

    return " ".join(disambiguation_parts) if disambiguation_parts else ""


def build_stage2_system_prompt(memory: MemoryBlock) -> str:
    """Assemble the full Stage 2 coaching system prompt with substitutions.

    Loads ``system_prompt_coaching_v1.0.txt``, substitutes:
    - ``__COACHEE_HISTORY__`` with prior meeting coaching context
    - ``__PATTERN_DEFINITIONS__`` with extracted taxonomy definitions
    - ``__EXPERIMENT_CONTEXT__`` with experiment context from memory

    Args:
        memory: The coachee's memory block (may contain active experiment,
                coaching history, and experiment history).

    Returns:
        Complete system prompt string ready for the LLM call.
    """
    prompt_path = Path(__file__).resolve().parent.parent.parent / "system_prompt_coaching_v1.0.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Stage 2 coaching prompt not found at {prompt_path}")

    raw = prompt_path.read_text(encoding="utf-8").strip()

    # Substitute coachee history (prior meeting context)
    coachee_history = _build_coachee_history_for_stage2(memory)
    raw = raw.replace("__COACHEE_HISTORY__", coachee_history)

    # Substitute pattern definitions from canonical taxonomy
    pattern_defs = extract_stage2_pattern_definitions()
    raw = raw.replace("__PATTERN_DEFINITIONS__", pattern_defs)

    # Substitute experiment context
    experiment_context = _build_experiment_context_for_stage2(memory)
    raw = raw.replace("__EXPERIMENT_CONTEXT__", experiment_context)

    return raw


def _build_experiment_context_for_stage2(memory: MemoryBlock) -> str:
    """Build experiment context string for the Stage 2 coaching prompt.

    Mirrors the logic from ``editor.py::build_experiment_context()`` but
    reads from the MemoryBlock directly.
    """
    if not memory or not memory.active_experiment:
        return ""

    exp = memory.active_experiment
    status = exp.get("status", "none")
    if status not in ("active", "assigned"):
        return ""

    exp_id = exp.get("experiment_id", "unknown")
    title = exp.get("title", "")
    instruction = exp.get("instruction", "")
    success_marker = exp.get("success_marker", "")
    pattern_id = exp.get("pattern_id", "")

    related_patterns = exp.get("related_patterns", [])
    # Backward compat: if experiment has legacy pattern_id but no related_patterns,
    # convert to related_patterns list.
    if not related_patterns and pattern_id:
        related_patterns = [pattern_id]

    lines = [
        "",
        "===============================================================",
        "ACTIVE EXPERIMENT CONTEXT",
        "===============================================================",
        "",
        f"The coachee has an active experiment (status: {status}):",
        f"- Experiment ID: {exp_id}",
        f"- Title: {title}",
        f"- Instruction: {instruction}",
        f"- Success marker: {success_marker}",
    ]
    if related_patterns:
        lines.append(f"- Related patterns: {', '.join(related_patterns)}")

    # Attempt history from prior meetings
    if memory.experiment_progress:
        lines.append("")
        lines.append("── ATTEMPT HISTORY (most recent first) ──")
        for entry in memory.experiment_progress:
            meeting_date = entry.get("meeting_date", "unknown")
            attempt = entry.get("attempt", "unknown")
            count = entry.get("count_attempts", 0)
            note = entry.get("coaching_note")
            note_part = f" — \"{note}\"" if note else ""
            lines.append(f"  Meeting {meeting_date}: {attempt} ({count} instances){note_part}")

    lines.extend([
        "",
        "You MUST evaluate whether the target speaker attempted this experiment in this meeting.",
        "Search the transcript for moments matching the experiment's instruction and success marker.",
        "Report your findings in experiment_tracking.detection_in_this_meeting.",
        "",
        "Use this attempt history AND your experiment detection from the current transcript to evaluate",
        "whether the experiment should graduate, continue, or be parked.",
        "Set experiment_tracking.graduation_recommendation accordingly.",
        "",
        "micro_experiment: Refine or evolve the current experiment (reuse experiment_id:",
        f"{exp_id}). Do not propose an unrelated experiment while this one is active.",
        "Exception: if graduation_recommendation is 'graduate' or 'park', echo the current",
        "experiment unchanged (same experiment_id, title, instruction, success_marker).",
    ])

    return "\n".join(lines)


def build_stage2_user_message(
    stage1_output: dict,
    transcript_turns: list[dict],
) -> str:
    """Build the user message for the Stage 2 coaching LLM call.

    Contains the transcript (speaker turns) and the Stage 1 scoring output.
    This is the canonical format used by both the production pipeline and
    the eval scripts.

    Args:
        stage1_output: The Stage 1 JSON output (scoring only, no coaching fields).
        transcript_turns: List of transcript turn dicts from the prompt payload.

    Returns:
        Formatted user message string.
    """
    import json as _json
    transcript_json = _json.dumps(transcript_turns, ensure_ascii=False, indent=2)
    stage1_json = _json.dumps(stage1_output, ensure_ascii=False, indent=2)

    return (
        "=== MEETING TRANSCRIPT (speaker turns) ===\n\n"
        f"{transcript_json}\n\n"
        "=== STAGE 1 ANALYSIS OUTPUT (scoring only — no coaching) ===\n\n"
        f"{stage1_json}"
    )


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
- evidence_spans: turn_start_id/turn_end_id must be integers. evidence_span_id must be turn-anchored: ES-T{start} or ES-T{start}-{end}. Each span must include event_ids linking to its source opportunity_events.
- opportunity_events: top-level array. Each OE must include pattern_id. OE event_ids must be referenced by evidence_spans.
- coaching.focus length=1, coaching.micro_experiment length=1. Focus items only need {pattern_id, message}.
- coaching.pattern_coaching: array of per-pattern coaching items. Each has pattern_id, notes, coaching_note, suggested_rewrite, rewrite_for_span_id. rewrite_for_span_id must be chosen from a missed-opportunity span (NOT in success_evidence_span_ids). Pick the clearest example for a meaningful rewrite. Avoid rewriting very short or garbled excerpts.
- coaching.experiment_coaching: set for partial experiment attempts only (coaching_note + suggested_rewrite + rewrite_for_span_id). Null otherwise.
- Before finalizing, re-check that each evidence span counted in a pattern's opportunity_count is a genuine opportunity per the taxonomy definition. Remove clear mismatches (e.g., a non-question counted under question_quality, or a 2-word fragment). For question_quality specifically, exclude procedural/technical questions (audio checks, roll call, scheduling logistics) from both scoring and opportunity_count — never quote them as evidence or in coaching. Do NOT remove spans simply because the transcript has rough ASR formatting — read past missing punctuation and filler words to assess the speaker's actual behavior.
- CRITICAL: Every notes and coaching_note field in coaching.pattern_coaching must specifically reference the behavior observed in the cited evidence spans. Do not write generic observations disconnected from the actual quotes.
- CRITICAL: success_evidence_span_ids must be consistent with opportunity event scores. binary requires success >= 1.0; tiered_rubric/complexity_tiered require success >= 0.75; multi_element requires success >= 0.8. Classify spans BEFORE selecting rewrite_for_span_id — do NOT adjust the success list to satisfy the rewrite constraint.
- CRITICAL: After writing suggested_rewrite in coaching.pattern_coaching, re-read the excerpt of rewrite_for_span_id and confirm the rewrite addresses the SAME topic and conversational moment. If the topics differ, either fix the span ID or rewrite the text.
- CRITICAL: Before finalizing, self-audit: (1) every counted OE must have a corresponding evidence span; (2) every evidence_span_id in pattern_snapshot must exist in evidence_spans; (3) opportunity_count must equal counted OEs; (4) rewrite_for_span_id must reference an existing, non-success span.
- CRITICAL: Never reference turn numbers, evidence_span_ids, event_ids, or any internal identifier in coaching text (notes, coaching_note, executive_summary, focus). Describe moments by what the speaker said or did.
- If a pattern's counted OE count is below its min_required_threshold, mark it insufficient_signal with evidence_span_ids=[]. Do NOT mark it evaluable without providing score and opportunity_count.
- For feedback_quality and question_quality: apply the taxonomy's inclusion tests and exclusion bright lines strictly. When uncertain whether a moment qualifies as an opportunity, exclude it. Consistency across runs matters more than completeness — undercounting is better than inconsistent counting."""


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
        "Analyze and return ONLY one JSON object conforming to mvp.v0.5.0.\n\n"
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
- coaching.focus length=1, coaching.micro_experiment length=1. Focus items only need {pattern_id, message}.
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
        "Synthesize and return ONLY one JSON object conforming to mvp.v0.6.0.\n\n"
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
    active_experiment: Optional[dict] = None,
    coaching_history: Optional[list[dict]] = None,
    experiment_history: Optional[list[dict]] = None,
    experiment_progress: Optional[list[dict]] = None,
) -> MemoryBlock:
    """
    Assemble the memory block for a single_meeting prompt.

    If there is no active baseline or experiment, returns a null memory block
    (but may still carry coaching_history and experiment_history).
    """
    baseline_profile: Optional[dict] = None
    if baseline_pack_id:
        baseline_profile = {
            "baseline_pack_id": baseline_pack_id,
        }

    active_exp_block: Optional[dict] = None
    if active_experiment:
        # Backward compat: convert legacy pattern_id to related_patterns
        related_patterns = active_experiment.get("related_patterns", [])
        if not related_patterns and active_experiment.get("pattern_id"):
            related_patterns = [active_experiment["pattern_id"]]
        active_exp_block = {
            "experiment_id": active_experiment.get("experiment_id"),
            "title": active_experiment.get("title"),
            "instruction": active_experiment.get("instruction"),
            "success_marker": active_experiment.get("success_marker"),
            "related_patterns": related_patterns,
            "status": active_experiment.get("status"),
        }

    return MemoryBlock(
        baseline_profile=baseline_profile,
        active_experiment=active_exp_block,
        coaching_history=coaching_history or [],
        experiment_history=experiment_history or [],
        experiment_progress=experiment_progress or [],
    )


def _build_coachee_history_for_stage2(memory: MemoryBlock) -> str:
    """Build the coachee history context string for the Stage 2 coaching prompt.

    Serializes coaching_history (recent meeting themes + summaries) and
    experiment_history (completed/parked/abandoned experiments) into a
    structured text block that replaces ``__COACHEE_HISTORY__``.

    Returns empty string if both lists are empty (new coachee).
    """
    if not memory or (not memory.coaching_history and not memory.experiment_history):
        return ""

    lines: list[str] = [
        "",
        "===============================================================",
        "COACHEE HISTORY \u2014 PRIOR MEETING CONTEXT",
        "===============================================================",
        "",
        "This coachee has been coached across multiple meetings. Use this history to:",
        "- Build on prior coaching themes rather than repeating them verbatim",
        "- Reference growth or persistent patterns when writing the executive summary",
        "- Note when a prior coaching theme reappears or resolves",
        "- When a prior strength or theme reappears, describe it using fresh language — different phrasing, a new angle, or new evidence from THIS meeting. The coachee should never feel they are reading the same sentence twice across meetings.",
    "- Do NOT let this history override what you observe in the current transcript",
    ]

    # ── Recent meeting analyses ──
    if memory.coaching_history:
        lines.append("")
        lines.append("\u2500\u2500 Recent Meeting Analyses (most recent first) \u2500\u2500")

        for entry in memory.coaching_history:
            meeting_date = entry.get("meeting_date", "unknown")
            lines.append("")
            lines.append(f"Meeting: {meeting_date}")

            exec_summary = entry.get("executive_summary", "")
            if exec_summary:
                lines.append(f'  Executive summary: "{exec_summary}"')

            themes = entry.get("coaching_themes", [])
            if themes:
                lines.append("  Coaching themes:")
                for theme in themes:
                    if isinstance(theme, dict):
                        label = theme.get("theme", "unknown")
                        explanation = theme.get("explanation", "")
                        priority = theme.get("priority", "")
                        prefix = f"    {priority.capitalize()}: " if priority else "    Theme: "
                        lines.append(f'{prefix}"{label}" \u2014 {explanation}')
                    elif isinstance(theme, str):
                        lines.append(f"    Theme: {theme}")

    # ── Experiment journey ──
    if memory.experiment_history:
        lines.append("")
        lines.append("\u2500\u2500 Experiment Journey \u2500\u2500")

        for exp in memory.experiment_history:
            title = exp.get("title", "unknown")
            status = exp.get("status", "unknown")
            instruction = exp.get("instruction", "")
            related = exp.get("related_patterns", [])
            journey = exp.get("journey_summary", "")

            patterns_str = f" ({', '.join(related)})" if related else ""
            lines.append("")
            lines.append(f"{status.capitalize()}: \"{title}\"{patterns_str}")
            if instruction:
                lines.append(f"  Instruction: {instruction}")
            if journey:
                lines.append(f'  Journey: "{journey}"')

    return "\n".join(lines)
