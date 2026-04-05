"""Longitudinal test transcript generation via LLM.

Wraps the 3 prompt files in ``longitudinal_test/`` to generate personas,
baseline transcripts, and follow-up transcripts for longitudinal coaching
evaluation.

All functions call ``call_llm()`` from ``backend.core.llm_client`` and return
plain-text outputs (not JSON-mode).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "longitudinal_test"

# ── Default models ───────────────────────────────────────────────────────────

_DEFAULT_TRANSCRIPT_MODEL = "claude-sonnet-4-6"


# ── Prompt loading ───────────────────────────────────────────────────────────

def _load_prompt(filename: str) -> str:
    """Load a prompt template from the longitudinal_test directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


# ── Persona generation ───────────────────────────────────────────────────────

def generate_persona(
    *,
    model: Optional[str] = None,
    diversity_context: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict:
    """Generate a coachee persona using the persona prompt template.

    Args:
        model: LLM model to use. Defaults to ``_DEFAULT_TRANSCRIPT_MODEL``.
        diversity_context: Optional string listing previously generated personas
            (name, role, key traits) to encourage diversity across personas.
        max_tokens: Maximum tokens for the LLM response.

    Returns:
        Dict with keys:
        - ``persona_text``: The full generated persona (for pasting into
          subsequent prompts).
        - ``name``: Extracted persona name (best-effort).
        - ``raw_response``: The full LLM response object.
    """
    prompt_text = _load_prompt("01_persona_generation_prompt.md")

    if diversity_context:
        prompt_text += (
            "\n\n## Diversity Constraint\n\n"
            "The following personas have already been created. Create a persona "
            "that is DIFFERENT from these — different industry, different seniority "
            "level, different communication profile:\n\n"
            f"{diversity_context}"
        )

    response = call_llm(
        system_prompt="You are a creative writer specializing in realistic professional personas.",
        developer_message="",
        user_message=prompt_text,
        model=model or _DEFAULT_TRANSCRIPT_MODEL,
        max_tokens=max_tokens,
        json_mode=False,
    )

    persona_text = response.raw_text.strip()

    # Best-effort name extraction: look for "Name:" or "# " at the start
    name = _extract_persona_name(persona_text)

    logger.info(
        "generate_persona: name=%s, %d chars, %d tokens",
        name, len(persona_text), response.total_tokens,
    )

    return {
        "persona_text": persona_text,
        "name": name,
        "raw_response": {
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        },
    }


def _extract_persona_name(persona_text: str) -> str:
    """Best-effort extraction of the persona's name from the generated text."""
    # Try JSON: {"name": "Priya Anand", ...}
    try:
        data = json.loads(persona_text)
        if isinstance(data, dict) and data.get("name"):
            return data["name"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try "Name: Nadia Petrov" or "**Name:** Nadia Petrov"
    match = re.search(r"(?:\*\*)?Name(?:\*\*)?:\s*(.+)", persona_text, re.IGNORECASE)
    if match:
        name = match.group(1).strip().strip("*").strip()
        # Take just the first few words (avoid grabbing a whole sentence)
        return " ".join(name.split()[:3])

    # Try markdown header: "# Nadia Petrov" or "## Nadia Petrov"
    match = re.search(r"^#+\s+(.+)", persona_text, re.MULTILINE)
    if match:
        name = match.group(1).strip().strip("*").strip()
        return " ".join(name.split()[:3])

    return "unknown"


# ── Baseline transcript generation ───────────────────────────────────────────

def generate_baseline_transcripts(
    persona_text: str,
    *,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> tuple[list[dict], str]:
    """Generate 3 baseline meeting transcripts from a persona.

    Args:
        persona_text: The full persona text to paste into the prompt.
        model: LLM model to use.
        max_tokens: Maximum tokens for the LLM response.

    Returns:
        Tuple of:
        - List of 3 transcript dicts, each with keys: ``transcript_text``,
          ``meeting_title``, ``role``, ``participants_line``, ``meeting_number``.
        - The ``story_so_far`` string for use in follow-up prompts.
    """
    prompt_text = _load_prompt("02_baseline_transcript_prompt.md")
    prompt_text = prompt_text.replace("{{PASTE PERSONA HERE}}", persona_text)

    response = call_llm(
        system_prompt=(
            "You are a creative writer generating realistic meeting transcripts "
            "for leadership communication evaluation. Follow the format and "
            "guidelines in the prompt exactly."
        ),
        developer_message="",
        user_message=prompt_text,
        model=model or _DEFAULT_TRANSCRIPT_MODEL,
        max_tokens=max_tokens,
        json_mode=False,
    )

    raw_text = response.raw_text.strip()

    # Parse the response into individual transcripts
    transcripts = _parse_baseline_response(raw_text)

    # Extract the "INITIAL STORY SO FAR" section
    story_so_far = _extract_story_so_far(raw_text, prefix="INITIAL STORY SO FAR")

    logger.info(
        "generate_baseline_transcripts: %d transcripts parsed, "
        "story_so_far=%d chars, %d tokens",
        len(transcripts), len(story_so_far), response.total_tokens,
    )

    return transcripts, story_so_far


def _parse_baseline_response(raw_text: str) -> list[dict]:
    """Parse baseline LLM response into individual transcript dicts.

    Splits on ``=== MEETING N:`` delimiters and extracts metadata from
    the header lines (Role, Participants).
    """
    # Split on meeting headers
    pattern = r"===\s*MEETING\s+(\d+)\s*:\s*(.+?)\s*==="
    splits = re.split(pattern, raw_text)

    # splits structure: [preamble, num1, title1, body1, num2, title2, body2, ...]
    transcripts = []
    i = 1  # skip preamble
    while i + 2 < len(splits):
        meeting_num = int(splits[i])
        meeting_title = splits[i + 1].strip()
        body = splits[i + 2].strip()

        role, participants_line, transcript_text = _parse_meeting_body(body)

        transcripts.append({
            "meeting_number": meeting_num,
            "meeting_title": meeting_title,
            "role": role,
            "participants_line": participants_line,
            "transcript_text": transcript_text,
        })
        i += 3

    return transcripts


def _parse_meeting_body(body: str) -> tuple[str, str, str]:
    """Extract role, participants, and transcript text from a meeting body."""
    lines = body.split("\n")
    role = ""
    participants_line = ""
    transcript_start = 0

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("role:"):
            role = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("participants:"):
            participants_line = stripped.split(":", 1)[1].strip()
        elif stripped and ":" in stripped and not stripped.lower().startswith(("role:", "participants:")):
            # First line that looks like dialogue (Speaker: text)
            transcript_start = idx
            break
        elif not stripped:
            continue
        else:
            transcript_start = idx
            break

    transcript_text = "\n".join(lines[transcript_start:]).strip()

    # Remove any trailing "INITIAL STORY SO FAR" section from the last transcript
    story_marker = "INITIAL STORY SO FAR"
    story_idx = transcript_text.find(story_marker)
    if story_idx != -1:
        transcript_text = transcript_text[:story_idx].strip()

    return role, participants_line, transcript_text


def _extract_story_so_far(raw_text: str, prefix: str = "STORY SO FAR") -> str:
    """Extract the story-so-far section from the LLM response."""
    # Look for the section marker
    patterns = [
        rf"{prefix}\s*(?:\(.*?\))?\s*:\s*\n(.*)",
        rf"{prefix}\s*:\s*\n(.*)",
    ]
    for pat in patterns:
        match = re.search(pat, raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            text = match.group(1).strip()
            # Stop at the next major section if any
            next_section = re.search(r"\n(?:===|---|\n#{1,3}\s)", text)
            if next_section:
                text = text[:next_section.start()].strip()
            return text

    logger.warning("Could not extract '%s' section from LLM response", prefix)
    return ""


# ── Follow-up transcript generation ──────────────────────────────────────────

def generate_followup_transcript(
    persona_text: str,
    coaching_context: str,
    story_so_far: str,
    *,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> dict:
    """Generate a follow-up meeting transcript with coaching context.

    Args:
        persona_text: The full persona text.
        coaching_context: Formatted coaching context from the prior analysis
            (use ``format_coaching_context_for_prompt()`` to produce this).
        story_so_far: The running narrative of the coaching arc.
        model: LLM model to use.
        max_tokens: Maximum tokens for the LLM response.

    Returns:
        Dict with keys: ``transcript_text``, ``meeting_title``, ``role``,
        ``participants_line``, ``design_note``, ``design_note_structured``,
        ``updated_story_so_far``, ``raw_response``.
    """
    prompt_text = _load_prompt("03_followup_transcript_prompt.md")

    # Substitute placeholders
    prompt_text = prompt_text.replace("{{PASTE PERSONA HERE}}", persona_text)
    prompt_text = prompt_text.replace(
        "{{PASTE THE FOLLOWING FROM THE MOST RECENT ANALYSIS OUTPUT, using this format:}}",
        coaching_context,
    )
    prompt_text = prompt_text.replace(
        "{{PROVIDE A BRIEF RUNNING NARRATIVE OF THE COACHING ARC:}}",
        story_so_far,
    )

    response = call_llm(
        system_prompt=(
            "You are a creative writer generating realistic meeting transcripts "
            "for leadership communication evaluation. Follow the format and "
            "guidelines in the prompt exactly."
        ),
        developer_message="",
        user_message=prompt_text,
        model=model or _DEFAULT_TRANSCRIPT_MODEL,
        max_tokens=max_tokens,
        json_mode=False,
    )

    raw_text = response.raw_text.strip()

    # Parse the response
    design_note = _extract_design_note(raw_text)
    design_note_structured = _parse_design_note_structured(design_note)
    transcript_data = _parse_single_transcript(raw_text)
    updated_story = _extract_story_so_far(raw_text, prefix="UPDATED STORY SO FAR")

    logger.info(
        "generate_followup_transcript: meeting=%s, role=%s, "
        "intended_attempt=%s, story=%d chars, %d tokens",
        transcript_data.get("meeting_title", "?"),
        transcript_data.get("role", "?"),
        design_note_structured.get("intended_attempt_level", "?"),
        len(updated_story),
        response.total_tokens,
    )

    return {
        **transcript_data,
        "design_note": design_note,
        "design_note_structured": design_note_structured,
        "updated_story_so_far": updated_story,
        "raw_response": {
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
        },
    }


def _extract_design_note(raw_text: str) -> str:
    """Extract the MEETING DESIGN NOTE section from the LLM response."""
    match = re.search(
        r"MEETING DESIGN NOTE:\s*\n(.*?)(?=\n===\s*MEETING|\Z)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    logger.warning("Could not extract MEETING DESIGN NOTE from LLM response")
    return ""


def _parse_design_note_structured(design_note: str) -> dict:
    """Parse the prose design note into a structured dict.

    Attempts to extract meeting_type, role, intended_attempt_level, and
    narrative from the prose. Falls back to best-effort extraction.
    """
    result: dict = {
        "meeting_type": "",
        "role": "",
        "intended_experiment_behavior": "",
        "intended_attempt_level": "unknown",
        "narrative": design_note,
    }

    if not design_note:
        return result

    # Try to detect attempt level from prose
    note_lower = design_note.lower()
    if any(phrase in note_lower for phrase in [
        "no attempt", "doesn't try", "doesn't attempt", "reverts entirely",
        "no clear attempt", "no opportunity", "doesn't consciously",
    ]):
        result["intended_attempt_level"] = "no"
    elif any(phrase in note_lower for phrase in [
        "clear attempt", "demonstrates", "multiple times", "naturally",
        "consistently", "several moments", "strong attempt",
    ]):
        result["intended_attempt_level"] = "yes"
    elif any(phrase in note_lower for phrase in [
        "partial", "tries once", "tries twice", "inconsistent",
        "attempts but", "starts to", "one moment", "reverts",
    ]):
        result["intended_attempt_level"] = "partial"

    return result


def _parse_single_transcript(raw_text: str) -> dict:
    """Parse a single-transcript LLM response (follow-up format)."""
    # Find the meeting header
    match = re.search(r"===\s*MEETING\s+(\d+)\s*:\s*(.+?)\s*===", raw_text)
    if not match:
        logger.warning("Could not find MEETING header in follow-up response")
        return {
            "meeting_number": 0,
            "meeting_title": "unknown",
            "role": "",
            "participants_line": "",
            "transcript_text": raw_text,
        }

    meeting_num = int(match.group(1))
    meeting_title = match.group(2).strip()

    # Get everything after the header
    body = raw_text[match.end():].strip()

    # Remove the "UPDATED STORY SO FAR" section from the transcript
    for marker in ["UPDATED STORY SO FAR", "MEETING DESIGN NOTE"]:
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx].strip()

    role, participants_line, transcript_text = _parse_meeting_body(body)

    return {
        "meeting_number": meeting_num,
        "meeting_title": meeting_title,
        "role": role,
        "participants_line": participants_line,
        "transcript_text": transcript_text,
    }


# ── Coaching context formatting ──────────────────────────────────────────────

def format_coaching_context_for_prompt(analysis_json: dict) -> str:
    """Format a Stage 2 merged analysis output for the follow-up prompt.

    Extracts the fields specified in ``03_followup_transcript_prompt.md``
    and formats them into the template structure expected by the prompt.

    Args:
        analysis_json: The full merged Stage 1 + Stage 2 analysis output dict.

    Returns:
        Formatted coaching context string ready to paste into the prompt.
    """
    coaching = analysis_json.get("coaching", {}) or {}
    exp_tracking = analysis_json.get("experiment_tracking", {}) or {}

    # Executive summary
    exec_summary = coaching.get("executive_summary", "")

    # Coaching themes
    themes = coaching.get("coaching_themes", [])
    theme_lines = []
    for theme in themes:
        if isinstance(theme, dict):
            priority = theme.get("priority", "")
            nature = theme.get("nature", "")
            label = theme.get("theme", "")
            explanation = theme.get("explanation", "")
            nature_tag = f" ({nature})" if nature else ""
            theme_lines.append(f'- {priority}{nature_tag}: "{label}" \u2014 {explanation}')
        elif isinstance(theme, str):
            theme_lines.append(f"- {theme}")
    themes_text = "\n".join(theme_lines) if theme_lines else "None"

    # Active experiment (from micro_experiment)
    micro_exps = coaching.get("micro_experiment", [])
    if micro_exps and isinstance(micro_exps, list) and len(micro_exps) > 0:
        exp = micro_exps[0]
        exp_title = exp.get("title", "N/A")
        exp_instruction = exp.get("instruction", "N/A")
        exp_success = exp.get("success_marker", "N/A")
    else:
        exp_title = "N/A"
        exp_instruction = "N/A"
        exp_success = "N/A"

    # Experiment detection
    detection = exp_tracking.get("detection_in_this_meeting")
    if detection and isinstance(detection, dict):
        attempt = detection.get("attempt", "N/A")
        count = detection.get("count_attempts", "N/A")
    else:
        attempt = "N/A"
        count = "N/A"

    # Experiment coaching note
    exp_coaching = coaching.get("experiment_coaching")
    if exp_coaching and isinstance(exp_coaching, dict):
        coaching_note = exp_coaching.get("coaching_note", "none")
    else:
        coaching_note = "none"

    # Notable pattern coaching (top 2-3 most specific)
    pattern_coaching = coaching.get("pattern_coaching", [])
    notable_lines = []
    for pc in pattern_coaching:
        if not isinstance(pc, dict):
            continue
        note = pc.get("coaching_note")
        if note and isinstance(note, str) and len(note) > 30:
            pid = pc.get("pattern_id", "unknown")
            notable_lines.append(f'- {pid}: "{note}"')
        if len(notable_lines) >= 3:
            break
    notable_text = "\n".join(notable_lines) if notable_lines else "None notable"

    return (
        f"EXECUTIVE SUMMARY:\n{exec_summary}\n\n"
        f"COACHING THEMES:\n{themes_text}\n\n"
        f"ACTIVE EXPERIMENT:\n"
        f"- Title: {exp_title}\n"
        f"- Instruction: {exp_instruction}\n"
        f"- Success marker: {exp_success}\n\n"
        f"EXPERIMENT DETECTION (from most recent meeting):\n"
        f"- Attempt: {attempt}\n"
        f"- Count: {count}\n"
        f"- Coaching note: {coaching_note}\n\n"
        f"NOTABLE PATTERN COACHING (2-3 most insightful):\n{notable_text}"
    )


# ── Transcript quality heuristics ────────────────────────────────────────────

def check_transcript_quality(transcript_text: str) -> dict:
    """Run lightweight heuristic checks on a generated transcript.

    Returns a dict with ``passed`` (bool) and ``issues`` (list of strings).
    This is NOT a quality judgment — it catches obvious generation failures
    (empty output, broken format, stage directions).
    """
    issues: list[str] = []

    if not transcript_text or len(transcript_text.strip()) < 200:
        issues.append(f"Transcript too short ({len(transcript_text.strip())} chars)")

    # Count turns (lines matching "Speaker: text" pattern)
    turn_pattern = re.compile(r"^[A-Z][a-zA-Z\s]+:\s+.+", re.MULTILINE)
    turns = turn_pattern.findall(transcript_text)
    if len(turns) < 20:
        issues.append(f"Too few turns detected ({len(turns)})")
    elif len(turns) > 300:
        issues.append(f"Unusually many turns ({len(turns)})")

    # Check speaker distribution
    speakers: dict[str, int] = {}
    for turn in turns:
        speaker = turn.split(":")[0].strip()
        speakers[speaker] = speakers.get(speaker, 0) + 1

    if speakers:
        total_turns = sum(speakers.values())
        max_speaker_pct = max(speakers.values()) / total_turns
        if max_speaker_pct > 0.70:
            top_speaker = max(speakers, key=speakers.get)  # type: ignore[arg-type]
            issues.append(
                f"Speaker '{top_speaker}' dominates with "
                f"{max_speaker_pct:.0%} of turns"
            )
        if len(speakers) < 2:
            issues.append(f"Only {len(speakers)} speaker(s) detected")

    # Check for stage directions
    stage_direction_pattern = re.compile(r"\[.{3,50}\]")
    stage_directions = stage_direction_pattern.findall(transcript_text)
    if len(stage_directions) > 2:
        issues.append(
            f"Possible stage directions detected ({len(stage_directions)}): "
            f"{stage_directions[:3]}"
        )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "stats": {
            "char_count": len(transcript_text),
            "turn_count": len(turns),
            "speaker_count": len(speakers),
            "speakers": speakers,
        },
    }


# ── Condensed history builder (for judge context) ────────────────────────────

def build_condensed_history(
    meeting_analyses: list[dict],
    relevant_patterns: Optional[list[str]] = None,
) -> str:
    """Build a condensed coaching history string for judge context.

    Produces ~300-400 words per meeting: executive summary (verbatim),
    coaching themes (name + explanation + priority), experiment status,
    and scores for relevant patterns.

    Args:
        meeting_analyses: List of dicts, each with keys ``meeting_number``,
            ``meeting_type``, ``role``, and ``analysis`` (the merged JSON).
        relevant_patterns: Optional list of pattern_ids to include scores for.
            If None, includes the 5 patterns with the most score variation.

    Returns:
        Formatted string for pasting into judge prompts.
    """
    if not meeting_analyses:
        return "No prior meeting analyses available."

    # Auto-detect relevant patterns if not specified
    if relevant_patterns is None:
        relevant_patterns = _auto_detect_relevant_patterns(meeting_analyses)

    lines: list[str] = []

    for entry in meeting_analyses:
        m_num = entry.get("meeting_number", "?")
        m_type = entry.get("meeting_type", "?")
        m_role = entry.get("role", "?")
        analysis = entry.get("analysis", {})
        coaching = analysis.get("coaching", {}) or {}
        exp_tracking = analysis.get("experiment_tracking", {}) or {}
        snapshot = analysis.get("pattern_snapshot", [])

        lines.append(f"--- Meeting {m_num} ({m_type}, role: {m_role}) ---")

        # Executive summary (verbatim)
        exec_summary = coaching.get("executive_summary", "")
        if exec_summary:
            lines.append(f"Executive summary: {exec_summary}")

        # Coaching themes
        themes = coaching.get("coaching_themes", [])
        if themes:
            for theme in themes:
                if isinstance(theme, dict):
                    priority = theme.get("priority", "")
                    nature = theme.get("nature", "")
                    label = theme.get("theme", "")
                    explanation = theme.get("explanation", "")
                    nature_tag = f" [{nature}]" if nature else ""
                    lines.append(f"  {priority}{nature_tag}: \"{label}\" \u2014 {explanation}")

        # Experiment status
        active_exp = exp_tracking.get("active_experiment", {})
        detection = exp_tracking.get("detection_in_this_meeting")
        if active_exp and isinstance(active_exp, dict):
            exp_id = active_exp.get("experiment_id", "")
            exp_status = active_exp.get("status", "")
            if exp_id:
                lines.append(f"  Experiment: {exp_id} (status: {exp_status})")
        if detection and isinstance(detection, dict):
            attempt = detection.get("attempt", "N/A")
            count = detection.get("count_attempts", 0)
            lines.append(f"  Detection: attempt={attempt}, count={count}")

        # Graduation recommendation (if present)
        grad_rec = exp_tracking.get("graduation_recommendation")
        if grad_rec and isinstance(grad_rec, dict):
            recommendation = grad_rec.get("recommendation", "")
            rationale = grad_rec.get("rationale", "")
            park_reason = grad_rec.get("park_reason")
            rec_str = recommendation
            if park_reason:
                rec_str += f" ({park_reason})"
            lines.append(f"  Graduation recommendation: {rec_str}")
            if rationale:
                lines.append(f"    Rationale: {rationale}")

        # Relevant pattern scores
        if relevant_patterns and snapshot:
            score_parts = []
            for ps in snapshot:
                pid = ps.get("pattern_id", "")
                if pid in relevant_patterns and ps.get("evaluable_status") == "evaluable":
                    score = ps.get("score")
                    if score is not None:
                        score_parts.append(f"{pid}={score:.2f}")
            if score_parts:
                lines.append(f"  Scores: {', '.join(score_parts)}")

        lines.append("")

    return "\n".join(lines)


def _auto_detect_relevant_patterns(meeting_analyses: list[dict]) -> list[str]:
    """Identify the 5 patterns with the most score variation across meetings."""
    from collections import defaultdict

    scores_by_pattern: dict[str, list[float]] = defaultdict(list)

    for entry in meeting_analyses:
        analysis = entry.get("analysis", {})
        snapshot = analysis.get("pattern_snapshot", [])
        for ps in snapshot:
            pid = ps.get("pattern_id", "")
            if ps.get("evaluable_status") == "evaluable":
                score = ps.get("score")
                if score is not None:
                    scores_by_pattern[pid].append(score)

    # Compute variance for each pattern
    variances: list[tuple[str, float]] = []
    for pid, scores in scores_by_pattern.items():
        if len(scores) >= 2:
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            variances.append((pid, variance))

    # Sort by variance descending, take top 5
    variances.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in variances[:5]]
