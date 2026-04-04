"""Longitudinal eval orchestrator.

Generates synthetic personas, runs them through the full coaching pipeline
(baseline + follow-up meetings), accumulates coaching memory across meetings,
and optionally runs A/B comparison (with vs without longitudinal context).

Usage:
    python -m backend.evals.longitudinal_eval \\
        --num-personas 2 --meetings-per-persona 5 \\
        --model claude-sonnet-4-5-20250514

See ``--help`` for all options.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.gate1_validator import validate as gate1_validate
from backend.core.llm_client import call_llm
from backend.core.models import MemoryBlock
from backend.core.output_patches import patch_analysis_output
from backend.core.prompt_builder import (
    build_baseline_pack_prompt,
    build_memory_block,
    build_single_meeting_prompt,
    build_stage2_system_prompt,
    build_stage2_user_message,
)
from backend.core.stage2_merge import merge_stage2_output
from backend.core.transcript_parser import parse_transcript
from backend.core.workers import _build_slim_meeting_summary  # pure data transform
from backend.core.openai_client import load_baseline_system_prompt
from backend.evals.longitudinal_transcript_gen import (
    check_transcript_quality,
    format_coaching_context_for_prompt,
    generate_baseline_transcripts,
    generate_followup_transcript,
    generate_persona,
)
from backend.evals.replay_eval import run_single_analysis
from backend.evals.report import save_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MAX_COACHING_HISTORY_MEETINGS = 3  # match production (workers.py)
MAX_EXPERIMENT_HISTORY = 5         # match production (workers.py)
EXPERIMENT_SAFETY_CAP = 5          # meetings before story nudge
BASELINE_MEETING_COUNT = 3

_BASE_DATE = date(2026, 1, 5)  # a Monday; deterministic across runs
_TOKENS_PER_STEP = 95_000       # transcript gen + S1 + S2
_TOKENS_PER_AB = 35_000         # S2 only

_RESULTS_DIR = Path(__file__).resolve().parent / "results"

_TAXONOMY_PATH = _PROJECT_ROOT / "clearvoice_pattern_taxonomy_v3.1.txt"


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class LongitudinalConfig:
    num_personas: int = 5
    meetings_per_persona: int = 8
    phase_name: str = ""
    model: str | None = None
    transcript_model: str | None = None
    tpm_limit: int = 4_000_000
    no_pause: bool = False
    skip_generation: bool = False
    skip_analysis: bool = False
    skip_ab: bool = False
    skip_judge: bool = False
    only_report: bool = False
    output_dir: Path | None = None


@dataclass
class RunConfig:
    meetings_per_persona: int
    model: str | None
    transcript_model: str | None
    no_pause: bool
    skip_generation: bool
    skip_analysis: bool


@dataclass
class MeetingResult:
    meeting_number: int
    meeting_phase: str           # "baseline" or "follow_up"
    meeting_id: str
    stage1_passed: bool = False
    analysis_passed: bool = False
    has_analysis: bool = False
    error: str | None = None
    design_note: dict | None = None
    token_counts: dict | None = None


@dataclass
class PersonaResult:
    persona_idx: int
    persona_name: str
    meetings: list[MeetingResult] = field(default_factory=list)
    experiment_transitions: list[dict] = field(default_factory=list)
    final_state: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _meeting_date(meeting_number: int) -> str:
    """Deterministic meeting date: weekly from 2026-01-05."""
    return (_BASE_DATE + timedelta(weeks=meeting_number - 1)).isoformat()


def _meeting_id(persona_idx: int, meeting_number: int) -> str:
    return f"EVAL-L-P{persona_idx:02d}-M{meeting_number:02d}"


def _experiment_id(persona_idx: int, exp_number: int) -> str:
    return f"EXP-EVAL-P{persona_idx:02d}-{exp_number:03d}"


def _meeting_dir(persona_dir: Path, meeting_number: int) -> Path:
    d = persona_dir / f"meeting_{meeting_number:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_taxonomy() -> str:
    """Load the canonical pattern taxonomy for developer_message."""
    return _TAXONOMY_PATH.read_text(encoding="utf-8").strip()


def _initial_state() -> dict:
    return {
        "last_completed_meeting": 0,
        "story_so_far": "",
        "coaching_history": [],
        "experiment_history": [],
        "active_experiment": None,
        "experiment_progress": [],  # attempt history for the CURRENT experiment
        "experiment_transitions": [],
        "next_experiment_number": 1,
        "baseline_pack_id": None,
    }


def _save_state(persona_dir: Path, state: dict) -> None:
    save_json(state, persona_dir / "state.json")


def _load_state(persona_dir: Path) -> dict:
    path = persona_dir / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return _initial_state()


def _save_quality(persona_dir: Path, meeting_key: str, qr: dict, quality: dict) -> dict:
    """Update and save quality.json incrementally."""
    quality.setdefault("meetings", {})
    quality["meetings"][meeting_key] = qr
    failed = sum(1 for m in quality["meetings"].values() if not m.get("passed"))
    quality["all_passed"] = failed == 0
    quality["failed_count"] = failed
    save_json(quality, persona_dir / "quality.json")
    return quality


def _build_memory_from_state(state: dict) -> MemoryBlock:
    """Build a MemoryBlock from the accumulated state, applying windowing."""
    ch = state.get("coaching_history", [])
    eh = state.get("experiment_history", [])
    ae = state.get("active_experiment")
    ep = state.get("experiment_progress", [])
    bp_id = state.get("baseline_pack_id")

    return build_memory_block(
        baseline_pack_id=bp_id,
        coaching_history=ch[-MAX_COACHING_HISTORY_MEETINGS:] if ch else None,
        experiment_history=eh[-MAX_EXPERIMENT_HISTORY:] if eh else None,
        active_experiment=ae,
        experiment_progress=ep if ep else None,
    )


def _extract_speaker_label(persona_name: str) -> str:
    """Extract first name from persona name for speaker label."""
    return persona_name.split()[0] if persona_name else "Speaker"


# ── Stage 2 pipeline (shared by baseline, follow-up, and A/B) ───────────────

def _run_stage2(
    stage1_parsed: dict,
    transcript_turns: list[dict],
    memory: MemoryBlock,
    *,
    model: str | None = None,
) -> tuple[dict, dict, int, int]:
    """Run the Stage 2 coaching pipeline.

    Returns (analysis_json, stage2_raw, prompt_tokens, completion_tokens).
    """
    sys_prompt = build_stage2_system_prompt(memory)
    user_msg = build_stage2_user_message(stage1_parsed, transcript_turns)

    response = call_llm(
        system_prompt=sys_prompt,
        developer_message="",
        user_message=user_msg,
        model=model,
    )

    stage2_raw = response.parsed
    merged, _changelog = merge_stage2_output(stage1_parsed, stage2_raw)
    patched = patch_analysis_output(merged, scoring_only=False)

    gate_result = gate1_validate(
        json.dumps(patched, ensure_ascii=False, indent=2), mode="full"
    )
    analysis = gate_result.corrected_data or patched

    return analysis, stage2_raw, response.prompt_tokens, response.completion_tokens


def _get_transcript_turns(
    meeting_id: str,
    meeting_type: str,
    meeting_date_str: str,
    target_role: str,
    target_speaker_name: str,
    target_speaker_label: str,
    parsed_transcript: Any,
    memory: MemoryBlock,
) -> list[dict]:
    """Build prompt payload to extract transcript_turns for Stage 2."""
    payload = build_single_meeting_prompt(
        meeting_id=meeting_id,
        meeting_type=meeting_type,
        meeting_date=meeting_date_str,
        target_role=target_role,
        target_speaker_name=target_speaker_name,
        target_speaker_label=target_speaker_label,
        parsed_transcript=parsed_transcript,
        memory=memory,
    )
    return payload.transcript_payload["turns"]


# ── Baseline synthesis ───────────────────────────────────────────────────────

def _run_baseline_synthesis(
    persona_dir: Path,
    persona_idx: int,
    target_role: str,
    target_speaker_name: str,
    target_speaker_label: str,
    *,
    model: str | None = None,
) -> dict:
    """Run the baseline pack synthesis (4th LLM call after 3 sub-runs).

    Returns the synthesis parsed JSON.
    """
    # Build slim summaries from the 3 sub-run analyses
    summaries = []
    meetings_meta = []
    for i in range(1, BASELINE_MEETING_COUNT + 1):
        m_dir = persona_dir / f"meeting_{i:02d}"
        analysis = json.loads((m_dir / "analysis.json").read_text(encoding="utf-8"))
        metadata = json.loads((m_dir / "metadata.json").read_text(encoding="utf-8"))

        # _build_slim_meeting_summary expects run_fields with Airtable field names
        run_fields = {
            "Target Speaker Name": target_speaker_name,
            "Target Speaker Label": target_speaker_label,
        }
        summaries.append(_build_slim_meeting_summary(run_fields, analysis))

        meetings_meta.append({
            "meeting_id": metadata["meeting_id"],
            "meeting_type": metadata.get("meeting_type", "single_meeting"),
            "target_speaker_name": target_speaker_name,
            "target_speaker_label": target_speaker_label,
            "target_speaker_role": metadata.get("target_role", target_role),
        })

    # Determine consistency
    roles = {m["target_speaker_role"] for m in meetings_meta}
    role_consistency = "consistent" if len(roles) == 1 else "mixed"
    mtypes = {m["meeting_type"] for m in meetings_meta}
    mtype_consistency = "consistent" if len(mtypes) == 1 else "mixed"

    # Build prompt
    bp_id = f"EVAL-L-P{persona_idx:02d}-BP"
    prompt_payload = build_baseline_pack_prompt(
        baseline_pack_id=bp_id,
        pack_size=BASELINE_MEETING_COUNT,
        target_role=target_role,
        role_consistency=role_consistency,
        meeting_type_consistency=mtype_consistency,
        meetings_meta=meetings_meta,
        meeting_summaries=summaries,
    )

    sys_prompt = load_baseline_system_prompt()
    dev_message = _load_taxonomy()

    response = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=model,
        max_tokens=16384,
    )

    parsed = response.parsed

    # Post-process: strip evidence spans (namespace collision across meetings)
    for ps in parsed.get("pattern_snapshot", []):
        ps["evidence_span_ids"] = []
        ps["success_evidence_span_ids"] = []
    for pc in (parsed.get("coaching", {}) or {}).get("pattern_coaching", []):
        pc["rewrite_for_span_id"] = None
    for me in (parsed.get("coaching", {}) or {}).get("micro_experiment", []):
        me["evidence_span_ids"] = []
    parsed["evidence_spans"] = []

    # Gate1 validate
    gate_result = gate1_validate(
        json.dumps(parsed, ensure_ascii=False, indent=2), mode="full"
    )
    synthesis = gate_result.corrected_data or parsed

    save_json(synthesis, persona_dir / "baseline_synthesis.json")

    logger.info(
        "Baseline synthesis P%02d: %d+%d tokens",
        persona_idx, response.prompt_tokens, response.completion_tokens,
    )

    return synthesis


# ── Single meeting pipeline ──────────────────────────────────────────────────

def _process_meeting(
    m_dir: Path,
    metadata: dict,
    memory: MemoryBlock,
    *,
    model: str | None = None,
) -> MeetingResult:
    """Run Stage 1 + Stage 2 for one meeting. Returns MeetingResult."""
    mid = metadata["meeting_id"]
    m_num = metadata["meeting_number"]
    phase = metadata.get("meeting_phase", "follow_up")
    result = MeetingResult(
        meeting_number=m_num,
        meeting_phase=phase,
        meeting_id=mid,
    )
    tokens: dict[str, int] = {}

    # ── Stage 1 ──
    stage1_path = m_dir / "stage1.json"
    if stage1_path.exists():
        stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
        result.stage1_passed = stage1.get("gate1_passed", False)
    else:
        transcript_path = m_dir / "transcript.txt"
        if not transcript_path.exists():
            result.error = f"transcript.txt missing in {m_dir.name}"
            return result
        parsed = parse_transcript(
            data=transcript_path.read_bytes(),
            filename="transcript.txt",
            source_id=mid,
        )
        stage1 = run_single_analysis(metadata, parsed, memory, model=model)
        save_json(stage1, stage1_path)
        result.stage1_passed = stage1.get("gate1_passed", False)
        tokens["stage1"] = (
            stage1.get("prompt_tokens", 0) + stage1.get("completion_tokens", 0)
        )

    if not result.stage1_passed:
        result.error = "Stage 1 failed Gate1 validation"
        result.token_counts = tokens or None
        return result

    # ── Stage 2 ──
    analysis_path = m_dir / "analysis.json"
    if analysis_path.exists():
        result.has_analysis = True
        result.analysis_passed = True
        result.token_counts = tokens or None
        return result

    # Need transcript_turns for Stage 2
    transcript_path = m_dir / "transcript.txt"
    if not transcript_path.exists():
        result.error = f"transcript.txt missing for Stage 2 in {m_dir.name}"
        result.token_counts = tokens or None
        return result
    parsed = parse_transcript(
        data=transcript_path.read_bytes(),
        filename="transcript.txt",
        source_id=mid,
    )
    transcript_turns = _get_transcript_turns(
        meeting_id=mid,
        meeting_type=metadata.get("meeting_type", "single_meeting"),
        meeting_date_str=metadata.get("meeting_date", "2026-01-01"),
        target_role=metadata.get("target_role", "participant"),
        target_speaker_name=metadata.get("target_speaker_name", "Speaker"),
        target_speaker_label=metadata.get("target_speaker_label", "Speaker"),
        parsed_transcript=parsed,
        memory=memory,
    )

    analysis, stage2_raw, s2_prompt, s2_completion = _run_stage2(
        stage1["parsed_json"], transcript_turns, memory, model=model,
    )
    save_json(stage2_raw, m_dir / "stage2_raw.json")
    save_json(analysis, analysis_path)

    tokens["stage2"] = s2_prompt + s2_completion
    result.has_analysis = True
    result.analysis_passed = True
    result.token_counts = tokens or None
    return result


# ── Persona series ───────────────────────────────────────────────────────────

def run_persona_series(
    persona_idx: int,
    persona: dict,
    config: RunConfig,
    persona_dir: Path,
) -> PersonaResult:
    """Run the full sequential pipeline for one persona."""
    persona_dir.mkdir(parents=True, exist_ok=True)
    persona_name = persona.get("name", "unknown")
    speaker_label = _extract_speaker_label(persona_name)
    persona_text = persona.get("persona_text", "")

    state = _load_state(persona_dir)
    quality: dict = {}
    qpath = persona_dir / "quality.json"
    if qpath.exists():
        quality = json.loads(qpath.read_text(encoding="utf-8"))

    pr = PersonaResult(persona_idx=persona_idx, persona_name=persona_name)

    # ── Phase A: Baseline ────────────────────────────────────────────────

    # Step 0: Generate all 3 baseline transcripts (one LLM call)
    if not config.skip_generation:
        all_exist = all(
            (persona_dir / f"meeting_{i:02d}" / "transcript.txt").exists()
            for i in range(1, BASELINE_MEETING_COUNT + 1)
        )
        if not all_exist:
            logger.info("P%02d: Generating baseline transcripts", persona_idx)
            transcripts, story_so_far = generate_baseline_transcripts(
                persona_text, model=config.transcript_model,
            )
            state["story_so_far"] = story_so_far

            for i, t in enumerate(transcripts[:BASELINE_MEETING_COUNT], start=1):
                m_dir = _meeting_dir(persona_dir, i)
                (m_dir / "transcript.txt").write_text(
                    t["transcript_text"], encoding="utf-8"
                )
                meta = {
                    "meeting_id": _meeting_id(persona_idx, i),
                    "meeting_number": i,
                    "meeting_type": "single_meeting",
                    "meeting_phase": "baseline",
                    "meeting_date": _meeting_date(i),
                    "target_role": t.get("role", "participant"),
                    "target_speaker_name": persona_name,
                    "target_speaker_label": speaker_label,
                }
                save_json(meta, m_dir / "metadata.json")

                qr = check_transcript_quality(t["transcript_text"])
                quality = _save_quality(
                    persona_dir, f"meeting_{i:02d}", qr, quality,
                )

            _save_state(persona_dir, state)

    # Process each baseline meeting (Stage 1 + Stage 2 with empty memory)
    if not config.skip_analysis:
        for i in range(1, BASELINE_MEETING_COUNT + 1):
            m_dir = _meeting_dir(persona_dir, i)
            analysis_path = m_dir / "analysis.json"
            mid = _meeting_id(persona_idx, i)

            if analysis_path.exists():
                logger.info("P%02d M%02d: analysis.json exists, skipping", persona_idx, i)
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="baseline",
                    meeting_id=mid, has_analysis=True, analysis_passed=True,
                ))
                continue

            meta_path = m_dir / "metadata.json"
            if not meta_path.exists():
                logger.warning("P%02d M%02d: no metadata.json, skipping", persona_idx, i)
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="baseline",
                    meeting_id=mid, error="metadata.json missing",
                ))
                continue

            metadata = json.loads(meta_path.read_text(encoding="utf-8"))

            try:
                mr = _process_meeting(
                    m_dir, metadata, MemoryBlock(), model=config.model,
                )
                pr.meetings.append(mr)
                state["last_completed_meeting"] = i
                _save_state(persona_dir, state)
            except Exception as exc:
                logger.error(
                    "P%02d M%02d: failed: %s", persona_idx, i, exc, exc_info=True,
                )
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="baseline",
                    meeting_id=mid, error=str(exc),
                ))

        # Step 4: Baseline synthesis
        synthesis_path = persona_dir / "baseline_synthesis.json"
        all_baseline_done = all(
            (persona_dir / f"meeting_{i:02d}" / "analysis.json").exists()
            for i in range(1, BASELINE_MEETING_COUNT + 1)
        )
        if all_baseline_done and not synthesis_path.exists():
            logger.info("P%02d: Running baseline synthesis", persona_idx)
            # Determine target_role from meeting_01 metadata
            m1_meta = json.loads(
                (persona_dir / "meeting_01" / "metadata.json").read_text(encoding="utf-8")
            )
            try:
                synthesis = _run_baseline_synthesis(
                    persona_dir, persona_idx,
                    target_role=m1_meta.get("target_role", "participant"),
                    target_speaker_name=persona_name,
                    target_speaker_label=speaker_label,
                    model=config.model,
                )

                # Record baseline pack ID in state
                state["baseline_pack_id"] = f"EVAL-L-P{persona_idx:02d}-BP"

                # Extract coaching history entry from synthesis
                coaching = synthesis.get("coaching", {}) or {}
                state["coaching_history"].append({
                    "meeting_date": _meeting_date(BASELINE_MEETING_COUNT),
                    "executive_summary": coaching.get("executive_summary", ""),
                    "coaching_themes": coaching.get("coaching_themes", []),
                })

                # Adopt first experiment from synthesis
                micro_exps = coaching.get("micro_experiment", [])
                if micro_exps and isinstance(micro_exps, list) and len(micro_exps) > 0:
                    exp = micro_exps[0]
                    exp_num = state["next_experiment_number"]
                    state["active_experiment"] = {
                        "experiment_id": _experiment_id(persona_idx, exp_num),
                        "title": exp.get("title", ""),
                        "instruction": exp.get("instruction", ""),
                        "success_marker": exp.get("success_marker", ""),
                        "related_patterns": exp.get("related_patterns", []),
                        "status": "active",
                    }
                    state["next_experiment_number"] = exp_num + 1

                _save_state(persona_dir, state)
            except Exception as exc:
                logger.error(
                    "P%02d: Baseline synthesis failed: %s",
                    persona_idx, exc, exc_info=True,
                )

    # ── Phase B: Follow-up Meetings ──────────────────────────────────────

    for i in range(BASELINE_MEETING_COUNT + 1, config.meetings_per_persona + 1):
        m_dir = _meeting_dir(persona_dir, i)
        mid = _meeting_id(persona_idx, i)

        # Check: can't proceed if baseline synthesis isn't done
        if not (persona_dir / "baseline_synthesis.json").exists():
            logger.warning(
                "P%02d M%02d: baseline_synthesis.json missing, skipping follow-ups",
                persona_idx, i,
            )
            pr.meetings.append(MeetingResult(
                meeting_number=i, meeting_phase="follow_up",
                meeting_id=mid, error="baseline synthesis missing",
            ))
            break

        # Skip check
        if (m_dir / "analysis.json").exists():
            logger.info("P%02d M%02d: analysis.json exists, skipping", persona_idx, i)
            pr.meetings.append(MeetingResult(
                meeting_number=i, meeting_phase="follow_up",
                meeting_id=mid, has_analysis=True, analysis_passed=True,
            ))
            # Ensure state reflects this meeting
            if state["last_completed_meeting"] < i:
                analysis = json.loads(
                    (m_dir / "analysis.json").read_text(encoding="utf-8")
                )
                _update_state_from_analysis(
                    state, analysis, i, persona_idx, m_dir,
                )
                _save_state(persona_dir, state)
            continue

        # ── Transcript generation ──
        transcript_path = m_dir / "transcript.txt"
        if not config.skip_generation and not transcript_path.exists():
            try:
                # Load most recent coaching output
                if i == BASELINE_MEETING_COUNT + 1:
                    prev_coaching = json.loads(
                        (persona_dir / "baseline_synthesis.json").read_text(encoding="utf-8")
                    )
                else:
                    prev_dir = persona_dir / f"meeting_{i - 1:02d}"
                    prev_coaching = json.loads(
                        (prev_dir / "analysis.json").read_text(encoding="utf-8")
                    )

                coaching_context = format_coaching_context_for_prompt(prev_coaching)
                fu_result = generate_followup_transcript(
                    persona_text, coaching_context, state["story_so_far"],
                    model=config.transcript_model,
                )

                (m_dir / "transcript.txt").write_text(
                    fu_result["transcript_text"], encoding="utf-8",
                )
                meta = {
                    "meeting_id": mid,
                    "meeting_number": i,
                    "meeting_type": "single_meeting",
                    "meeting_phase": "follow_up",
                    "meeting_date": _meeting_date(i),
                    "target_role": fu_result.get("role", "participant"),
                    "target_speaker_name": persona_name,
                    "target_speaker_label": speaker_label,
                }
                save_json(meta, m_dir / "metadata.json")

                # Save design note
                save_json({
                    "design_note_text": fu_result.get("design_note", ""),
                    "intended_attempt_level": fu_result.get(
                        "design_note_structured", {}
                    ).get("intended_attempt_level", "unknown"),
                    "meeting_type": fu_result.get(
                        "design_note_structured", {}
                    ).get("meeting_type", ""),
                    "role": fu_result.get("role", ""),
                }, m_dir / "design_note.json")

                # Update story
                updated_story = fu_result.get("updated_story_so_far", "")
                if updated_story:
                    state["story_so_far"] = updated_story
                    _save_state(persona_dir, state)

                # Quality check
                qr = check_transcript_quality(fu_result["transcript_text"])
                quality = _save_quality(
                    persona_dir, f"meeting_{i:02d}", qr, quality,
                )

            except Exception as exc:
                logger.error(
                    "P%02d M%02d: transcript gen failed: %s",
                    persona_idx, i, exc, exc_info=True,
                )
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="follow_up",
                    meeting_id=mid, error=f"transcript gen: {exc}",
                ))
                continue

        # ── Stage 1 + Stage 2 ──
        if not config.skip_analysis:
            meta_path = m_dir / "metadata.json"
            if not meta_path.exists():
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="follow_up",
                    meeting_id=mid, error="metadata.json missing",
                ))
                continue

            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            memory = _build_memory_from_state(state)

            try:
                mr = _process_meeting(m_dir, metadata, memory, model=config.model)
                mr.meeting_phase = "follow_up"

                # Load design note if present
                dn_path = m_dir / "design_note.json"
                if dn_path.exists():
                    mr.design_note = json.loads(dn_path.read_text(encoding="utf-8"))

                pr.meetings.append(mr)

                if mr.has_analysis:
                    analysis = json.loads(
                        (m_dir / "analysis.json").read_text(encoding="utf-8")
                    )
                    _update_state_from_analysis(
                        state, analysis, i, persona_idx, m_dir,
                    )
                    _save_state(persona_dir, state)
            except Exception as exc:
                logger.error(
                    "P%02d M%02d: analysis failed: %s",
                    persona_idx, i, exc, exc_info=True,
                )
                pr.meetings.append(MeetingResult(
                    meeting_number=i, meeting_phase="follow_up",
                    meeting_id=mid, error=str(exc),
                ))

    pr.experiment_transitions = state.get("experiment_transitions", [])
    pr.final_state = state
    return pr


def _update_state_from_analysis(
    state: dict,
    analysis: dict,
    meeting_number: int,
    persona_idx: int,
    m_dir: Path,
) -> None:
    """Update state after a completed follow-up meeting analysis.

    Handles the full experiment lifecycle:
    - Tracks attempt history (experiment_progress) for the active experiment
    - Acts on graduation_recommendation: graduate, park, or continue
    - On graduate/park: moves experiment to history, clears progress,
      so the NEXT meeting's analysis will propose a new experiment
    - On continue: keeps experiment active, applies safety cap nudge if needed
    """
    coaching = analysis.get("coaching", {}) or {}
    exp_tracking = analysis.get("experiment_tracking", {}) or {}

    # ── Append coaching history ──
    state["coaching_history"].append({
        "meeting_date": _meeting_date(meeting_number),
        "executive_summary": coaching.get("executive_summary", ""),
        "coaching_themes": coaching.get("coaching_themes", []),
    })
    state["last_completed_meeting"] = meeting_number

    # ── Track experiment attempt for this meeting ──
    detection = exp_tracking.get("detection_in_this_meeting")
    if detection and isinstance(detection, dict):
        exp_coaching = coaching.get("experiment_coaching")
        coaching_note = ""
        if exp_coaching and isinstance(exp_coaching, dict):
            coaching_note = exp_coaching.get("coaching_note", "")

        state["experiment_progress"].append({
            "meeting_date": _meeting_date(meeting_number),
            "meeting_number": meeting_number,
            "attempt": detection.get("attempt", "unknown"),
            "count_attempts": detection.get("count_attempts", 0),
            "coaching_note": coaching_note,
        })

    # ── Process graduation_recommendation ──
    active = state.get("active_experiment")
    grad_rec = exp_tracking.get("graduation_recommendation")

    if active and isinstance(grad_rec, dict):
        recommendation = grad_rec.get("recommendation", "continue")
        rationale = grad_rec.get("rationale", "")
        park_reason = grad_rec.get("park_reason")

        if recommendation == "graduate":
            # Move to history as completed
            journey = _compose_journey_summary(state, meeting_number, "completed")
            _transition_experiment(
                state, persona_idx, meeting_number,
                new_status="completed", journey_summary=journey,
            )
            logger.info(
                "P%02d M%02d: Experiment graduated: %s",
                persona_idx, meeting_number, active.get("title", "?"),
            )

        elif recommendation == "park":
            # Move to history as parked
            journey = _compose_journey_summary(state, meeting_number, "parked")
            if park_reason == "pivot" and rationale:
                journey += f" Pivot reason: {rationale}"
            _transition_experiment(
                state, persona_idx, meeting_number,
                new_status="parked", journey_summary=journey,
                park_reason=park_reason, rationale=rationale,
            )
            logger.info(
                "P%02d M%02d: Experiment parked (%s): %s",
                persona_idx, meeting_number, park_reason, active.get("title", "?"),
            )

        elif recommendation == "continue":
            # Keep active — check safety cap
            active_since = _experiment_active_since(state)
            meetings_active = meeting_number - active_since + 1
            if meetings_active >= EXPERIMENT_SAFETY_CAP:
                state["story_so_far"] += (
                    f"\n\nNote: The current experiment '{active['title']}' has been "
                    f"active for {meetings_active} meetings. Consider whether the "
                    "coachee might be ready for a new challenge."
                )

    elif active is None:
        # No active experiment — check if the analysis proposed one
        micro_exps = coaching.get("micro_experiment", [])
        if micro_exps and isinstance(micro_exps, list) and len(micro_exps) > 0:
            new_exp = micro_exps[0]
            exp_num = state["next_experiment_number"]
            state["active_experiment"] = {
                "experiment_id": _experiment_id(persona_idx, exp_num),
                "title": new_exp.get("title", ""),
                "instruction": new_exp.get("instruction", ""),
                "success_marker": new_exp.get("success_marker", ""),
                "related_patterns": new_exp.get("related_patterns", []),
                "status": "active",
            }
            state["next_experiment_number"] = exp_num + 1
            state["experiment_progress"] = []  # fresh progress for new experiment
            logger.info(
                "P%02d M%02d: New experiment adopted: %s",
                persona_idx, meeting_number, new_exp.get("title", "?"),
            )


def _transition_experiment(
    state: dict,
    persona_idx: int,
    meeting_number: int,
    *,
    new_status: str,
    journey_summary: str,
    park_reason: str | None = None,
    rationale: str = "",
) -> None:
    """Move the active experiment to history and clear state for next experiment.

    After this, active_experiment is None. The NEXT meeting's analysis
    (with no active experiment) will propose a new one via micro_experiment.

    Also updates story_so_far so the transcript generator knows the coaching
    arc has shifted — this is a lightweight substitute for the production
    ``process_next_experiment_suggestion`` flow, which synthesizes 3 candidates
    from the full coaching theme history. We can't call that directly (Airtable
    dependency), so instead we carry forward the transition context so Stage 2
    and the transcript generator produce a well-grounded next experiment.
    """
    old_exp = dict(state["active_experiment"])
    old_title = old_exp.get("title", "unknown")
    old_exp["status"] = new_status
    old_exp["journey_summary"] = journey_summary
    if park_reason:
        old_exp["park_reason"] = park_reason
    state["experiment_history"].append(old_exp)

    state["experiment_transitions"].append({
        "meeting": meeting_number,
        "from": old_exp["experiment_id"],
        "to": None,  # next experiment will be proposed by the next meeting's analysis
        "recommendation": new_status,  # "completed" or "parked"
        "journey_summary": journey_summary,
    })

    state["active_experiment"] = None
    state["experiment_progress"] = []  # clear for next experiment

    # Nudge story_so_far so the transcript generator and Stage 2 know about
    # the transition and can orient the next experiment appropriately.
    if new_status == "completed":
        state["story_so_far"] += (
            f"\n\nThe leader's experiment '{old_title}' has been completed — "
            f"the behavior is integrating naturally. The coaching focus should "
            f"now shift to the next highest-leverage growth area."
        )
    elif new_status == "parked" and park_reason == "pivot":
        state["story_so_far"] += (
            f"\n\nThe leader's experiment '{old_title}' has been parked "
            f"because a more pressing priority emerged. "
        )
        if rationale:
            state["story_so_far"] += (
                f"The coaching system identified this priority: \"{rationale}\" "
                f"The next experiment should address this area."
            )
    elif new_status == "parked" and park_reason == "stale":
        state["story_so_far"] += (
            f"\n\nThe leader's experiment '{old_title}' has been parked — "
            f"the leader wasn't engaging with it across recent meetings. "
            f"The next experiment should target a behavior the leader is more "
            f"likely to practice in their typical meeting contexts."
        )


def _compose_journey_summary(
    state: dict, current_meeting: int, final_status: str,
) -> str:
    """Compose a journey summary from the experiment_progress history."""
    progress = state.get("experiment_progress", [])
    active_since = _experiment_active_since(state)
    duration = current_meeting - active_since + 1

    # Build per-meeting detection line
    detection_parts = []
    for entry in progress:
        m_num = entry.get("meeting_number", "?")
        attempt = entry.get("attempt", "?")
        detection_parts.append(f"M{m_num:02d}={attempt}")

    summary = f"Active for {duration} meetings (M{active_since:02d}-M{current_meeting:02d}). "
    summary += f"Status: {final_status}. "

    if detection_parts:
        summary += f"Detection: {', '.join(detection_parts)}. "

    # Include last coaching note if available
    if progress:
        last_note = progress[-1].get("coaching_note", "")
        if last_note:
            summary += f'Final coaching note: "{last_note}"'

    return summary.strip()


def _experiment_active_since(state: dict) -> int:
    """Determine which meeting the current experiment became active."""
    transitions = state.get("experiment_transitions", [])
    if transitions:
        # The experiment became active in the meeting AFTER the last transition
        return transitions[-1]["meeting"] + 1
    # First experiment — active since after baseline
    return BASELINE_MEETING_COUNT + 1


# ── A/B comparison ───────────────────────────────────────────────────────────

def _run_ab_for_meeting(
    m_dir: Path, *, model: str | None = None,
) -> tuple[str, bool]:
    """Re-run Stage 2 with empty memory for one follow-up meeting.

    Returns (meeting_dir_name, success).
    """
    stage1_path = m_dir / "stage1.json"
    analysis_path = m_dir / "analysis.json"
    ab_path = m_dir / "analysis_no_history.json"

    if ab_path.exists():
        return m_dir.name, True

    if not stage1_path.exists() or not analysis_path.exists():
        return m_dir.name, False

    stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
    metadata = json.loads((m_dir / "metadata.json").read_text(encoding="utf-8"))

    # Parse transcript for turns
    parsed = parse_transcript(
        data=(m_dir / "transcript.txt").read_bytes(),
        filename="transcript.txt",
        source_id=metadata["meeting_id"],
    )
    transcript_turns = _get_transcript_turns(
        meeting_id=metadata["meeting_id"],
        meeting_type=metadata.get("meeting_type", "single_meeting"),
        meeting_date_str=metadata.get("meeting_date", "2026-01-01"),
        target_role=metadata.get("target_role", "participant"),
        target_speaker_name=metadata.get("target_speaker_name", "Speaker"),
        target_speaker_label=metadata.get("target_speaker_label", "Speaker"),
        parsed_transcript=parsed,
        memory=MemoryBlock(),
    )

    analysis, _raw, _pt, _ct = _run_stage2(
        stage1["parsed_json"], transcript_turns, MemoryBlock(), model=model,
    )
    save_json(analysis, ab_path)
    return m_dir.name, True


# ── Top-level orchestrator ───────────────────────────────────────────────────

def run_longitudinal_eval(config: LongitudinalConfig) -> Path:
    """Run the full longitudinal eval pipeline."""
    # Output directory
    if config.output_dir:
        output_dir = config.output_dir
    else:
        phase = config.phase_name or f"Long_{date.today().strftime('%Y%m%d')}"
        output_dir = _RESULTS_DIR / phase
    output_dir.mkdir(parents=True, exist_ok=True)

    # Manifest
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "phase": output_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "config": asdict(config),
        "status": "running",
        "personas_completed": 0,
        "total_tokens": {"stage1": 0, "stage2": 0, "transcript_gen": 0},
    }
    # Convert Path to string for JSON
    manifest["config"]["output_dir"] = str(config.output_dir) if config.output_dir else None
    save_json(manifest, manifest_path)

    # ── Generate personas ────────────────────────────────────────────────
    personas: list[dict] = []
    for p_idx in range(1, config.num_personas + 1):
        p_dir = output_dir / f"persona_{p_idx:02d}"
        p_dir.mkdir(parents=True, exist_ok=True)
        p_path = p_dir / "persona.json"

        if p_path.exists():
            personas.append(json.loads(p_path.read_text(encoding="utf-8")))
            logger.info("Loaded existing persona %d: %s", p_idx, personas[-1].get("name"))
        elif not config.skip_generation:
            diversity = "\n".join(
                f"- {p['name']} ({p.get('persona_text', '')[:200]}...)"
                for p in personas
            ) if personas else None

            result = generate_persona(
                model=config.transcript_model, diversity_context=diversity,
            )
            persona_data = {
                "persona_idx": p_idx,
                "name": result["name"],
                "persona_text": result["persona_text"],
                "generated_with": result["raw_response"],
            }
            save_json(persona_data, p_path)
            personas.append(persona_data)
            logger.info("Generated persona %d: %s", p_idx, result["name"])
        else:
            logger.warning("Persona %d: no persona.json and --skip-generation set", p_idx)

    if not personas:
        logger.error("No personas available. Exiting.")
        return output_dir

    # ── Pause checkpoint ─────────────────────────────────────────────────
    if not config.no_pause and not config.skip_generation:
        # Run persona_01 baseline transcripts first
        p1_dir = output_dir / "persona_01"
        rc = RunConfig(
            meetings_per_persona=config.meetings_per_persona,
            model=config.model,
            transcript_model=config.transcript_model,
            no_pause=True,
            skip_generation=False,
            skip_analysis=True,  # only generate transcripts for now
        )
        run_persona_series(1, personas[0], rc, p1_dir)

        resp = input(
            "\nReview persona_01 baseline transcripts in:\n"
            f"  {p1_dir}\n"
            "Continue? [y/n] "
        ).strip().lower()
        if resp != "y":
            logger.info("User declined to continue. Exiting.")
            manifest["status"] = "paused"
            save_json(manifest, manifest_path)
            return output_dir

    # ── Run persona series (parallel) ────────────────────────────────────
    rc = RunConfig(
        meetings_per_persona=config.meetings_per_persona,
        model=config.model,
        transcript_model=config.transcript_model,
        no_pause=True,
        skip_generation=config.skip_generation,
        skip_analysis=config.skip_analysis,
    )

    persona_workers = max(1, min(
        config.num_personas,
        int(config.tpm_limit * 0.8 / _TOKENS_PER_STEP),
    ))
    logger.info(
        "Running %d personas with %d workers", config.num_personas, persona_workers,
    )

    results: list[PersonaResult] = []
    with ThreadPoolExecutor(max_workers=persona_workers) as pool:
        futures = {
            pool.submit(
                run_persona_series,
                p_idx,
                personas[p_idx - 1],
                rc,
                output_dir / f"persona_{p_idx:02d}",
            ): p_idx
            for p_idx in range(1, len(personas) + 1)
        }
        for future in as_completed(futures):
            p_idx = futures[future]
            try:
                pr = future.result()
                results.append(pr)
                manifest["personas_completed"] += 1
                save_json(manifest, manifest_path)
                logger.info(
                    "Persona %d (%s) complete: %d meetings",
                    p_idx, pr.persona_name, len(pr.meetings),
                )
            except Exception as exc:
                logger.error("Persona %d failed: %s", p_idx, exc, exc_info=True)

    # ── A/B comparison ───────────────────────────────────────────────────
    if not config.skip_ab:
        ab_tasks: list[Path] = []
        for p_idx in range(1, len(personas) + 1):
            p_dir = output_dir / f"persona_{p_idx:02d}"
            for i in range(BASELINE_MEETING_COUNT + 1, config.meetings_per_persona + 1):
                m_dir = p_dir / f"meeting_{i:02d}"
                if (m_dir / "analysis.json").exists() and not (m_dir / "analysis_no_history.json").exists():
                    ab_tasks.append(m_dir)

        if ab_tasks:
            ab_workers = max(1, min(
                len(ab_tasks),
                int(config.tpm_limit * 0.8 / _TOKENS_PER_AB),
            ))
            logger.info(
                "Running A/B comparison: %d tasks, %d workers",
                len(ab_tasks), ab_workers,
            )
            with ThreadPoolExecutor(max_workers=ab_workers) as pool:
                futures = {
                    pool.submit(_run_ab_for_meeting, m, model=config.model): m.name
                    for m in ab_tasks
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        _, success = future.result()
                        if not success:
                            logger.warning("A/B failed for %s", name)
                    except Exception as exc:
                        logger.error("A/B failed for %s: %s", name, exc)

    # ── Finalize ─────────────────────────────────────────────────────────
    manifest["status"] = "completed"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_json(manifest, manifest_path)

    logger.info("Longitudinal eval complete: %s", output_dir)
    return output_dir


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run longitudinal coaching eval pipeline.",
    )
    parser.add_argument("--num-personas", type=int, default=5)
    parser.add_argument("--meetings-per-persona", type=int, default=8)
    parser.add_argument("--phase", type=str, default="", dest="phase_name")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--transcript-model", type=str, default=None)
    parser.add_argument("--tpm-limit", type=int, default=4_000_000)
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--skip-ab", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--only-report", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    config = LongitudinalConfig(
        num_personas=args.num_personas,
        meetings_per_persona=args.meetings_per_persona,
        phase_name=args.phase_name,
        model=args.model,
        transcript_model=args.transcript_model,
        tpm_limit=args.tpm_limit,
        no_pause=args.no_pause,
        skip_generation=args.skip_generation,
        skip_analysis=args.skip_analysis,
        skip_ab=args.skip_ab,
        skip_judge=args.skip_judge,
        only_report=args.only_report,
        output_dir=args.output_dir,
    )

    run_longitudinal_eval(config)


if __name__ == "__main__":
    main()
