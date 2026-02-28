"""
prompt_builder.py — Assembles the OpenAI user message for single_meeting and baseline_pack.

Replicates the exact payload structure observed in the example API calls.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .config import OUTPUT_MODE, SCHEMA_VERSION, TAXONOMY_VERSION
from .models import MemoryBlock, ParsedTranscript, PromptPayload

logger = logging.getLogger(__name__)


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
        "Analyze and return ONLY one JSON object conforming to mvp.v0.2.1.\n\n"
        "INPUT_PAYLOAD\n"
        + json.dumps(input_payload, ensure_ascii=False, indent=2)
    )

    return PromptPayload(
        analysis_type="single_meeting",
        meta=meta,
        context=context,
        memory=memory,
        transcript_payload=transcript_payload,
        raw_user_message=user_message,
    )


def build_baseline_pack_prompt(
    *,
    baseline_pack_id: str,
    pack_size: int,
    target_role: str,
    role_consistency: Optional[str],
    meeting_type_consistency: Optional[str],
    meetings_meta: list[dict],  # [{meeting_id, meeting_type, target_speaker_name, target_speaker_label, target_speaker_role}]
    meeting_summaries: list[dict],  # slim run output dicts
    analysis_id: Optional[str] = None,
) -> PromptPayload:
    """
    Build the user message payload for a baseline_pack analysis.
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
    }

    memory = MemoryBlock()  # always null for baseline pack

    # PACK CONTEXT block (freeform text section in the turns pseudo-payload)
    pack_context_lines = [
        "BASELINE PACK INPUT ({} meetings). Task: compute a role-conditioned baseline snapshot using the {} single_meeting analyses below.".format(pack_size, pack_size),
        "",
        "AGGREGATION RULES:",
        "1) For each pattern_id, compute the baseline ratio as the median of the meeting-level ratios across meetings where that pattern is evaluable (not insufficient_signal and not not_evaluable).",
        "2) If a pattern is insufficient_signal in >=2 meetings, treat it as insufficient_signal in the baseline pack.",
        "3) Use the baseline snapshot to select: 0\u20132 strengths, exactly 1 focus, exactly 1 micro-experiment (highest leverage).",
        "4) Baseline pack: do NOT do experiment attempt detection (detection_in_this_meeting must be null).",
        "5) Per-meeting micro_experiment suggestions are candidates only. For baseline_pack, choose exactly one experiment based on the aggregated baseline snapshot; do not continue any per-meeting experiment.",
        "IMPORTANT: Only use the information in this pack. Do not invent missing denominators or opportunities.",
        "",
        "PACK CONTEXT:",
        f"- baseline_pack_id: {baseline_pack_id}",
        f"- pack_size: {pack_size}",
        f"- target_role: {effective_role}",
        f"- role_consistency: {role_consistency}",
        f"- meeting_type_consistency: {meeting_type_consistency}",
        "- meetings: " + json.dumps(meetings_meta, ensure_ascii=False),
        "",
        "MEETING SUMMARIES (each is a JSON object; do not assume missing fields):",
    ]

    for summary in meeting_summaries:
        pack_context_lines.append("")
        pack_context_lines.append(json.dumps(summary, ensure_ascii=False))

    pack_context_text = "\n".join(pack_context_lines)

    # Mimic the exact structure seen in example: transcript.turns is the pack context blob
    transcript_payload = {
        "source_id": baseline_pack_id,
        "turns": [pack_context_text],
    }

    input_payload = {
        "meta": meta,
        "context": context,
        "memory": memory.model_dump(),
        "transcript": transcript_payload,
    }

    user_message = (
        "Analyze and return ONLY one JSON object conforming to mvp.v0.2.1.\n\n"
        "INPUT_PAYLOAD\n"
        + json.dumps(input_payload, ensure_ascii=False, indent=2)
    )

    return PromptPayload(
        analysis_type="baseline_pack",
        meta=meta,
        context=context,
        memory=memory,
        transcript_payload=transcript_payload,
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
