"""
api/quote_helpers.py — Shared helpers for resolving evidence_span_ids into QuoteObjects.

Used by routes_runs.py (single meeting) and routes_coachee.py (baseline pack).
"""
from __future__ import annotations

import logging
import os
import re

import json
from typing import Optional

from ..core.airtable_client import AirtableClient
from ..core.models import Turn
from ..core.quote_cleanup import cleanup_quotes
from ..core.transcript_parser import parse_transcript
from .dto import (
    ExperimentCoachingItem,
    ExperimentDetectionWithQuotes,
    HighlightItem,
    MicroExperimentWithQuotes,
    PatternCoachingItem,
    PatternSnapshotItem,
    QuoteObject,
)

# Feature flag: set QUOTE_CLEANUP_ENABLED=1 to enable post-processing cleanup.
_CLEANUP_ENABLED = os.getenv("QUOTE_CLEANUP_ENABLED", "0") == "1"

_QUOTE_MAX_CHARS = 2000

# Matches a leading "Speaker_Label: " prefix that the LLM sometimes bakes into
# single-speaker excerpts.  Handles common formats like "Chris:", "SPEAKER_00:",
# "Dr. Smith:", etc.
_SPEAKER_PREFIX_RE = re.compile(r"^[A-Za-z0-9_.'\-]+(?:\s+[A-Za-z0-9_.'\-]+)?:\s+", re.UNICODE)


def _strip_speaker_prefix(excerpt: str) -> str:
    """Remove a leading 'Speaker: ' prefix from a single-speaker excerpt."""
    return _SPEAKER_PREFIX_RE.sub("", excerpt, count=1)


def format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS for display."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_turn_map(
    at_client: AirtableClient,
    transcript_record_id: Optional[str],
) -> dict[int, Turn]:
    """Parse the transcript and return a {turn_id: Turn} lookup."""
    if not transcript_record_id:
        return {}
    try:
        tr_record = at_client.get_transcript(transcript_record_id)
        return build_turn_map_from_record(tr_record)
    except Exception:
        return {}


def build_turn_map_from_record(tr_record: dict) -> dict[int, Turn]:
    """Build a turn map from an already-fetched transcript record."""
    try:
        tr_fields = tr_record.get("fields", {})
        transcript_text = (
            tr_fields.get("Transcript (extracted)")
            or tr_fields.get("Raw Transcript Text")
            or ""
        )
        if not transcript_text:
            return {}
        parsed = parse_transcript(
            data=transcript_text.encode("utf-8"),
            filename="transcript.txt",
            source_id=tr_fields.get("Transcript ID") or tr_record.get("id", ""),
        )
        return {t.turn_id: t for t in parsed.turns}
    except Exception:
        return {}


def resolve_quotes(
    evidence_span_ids: list[str],
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
    turn_map: Optional[dict[int, Turn]] = None,
    target_speaker_label: Optional[str] = None,
) -> list[QuoteObject]:
    # Collect (sort_key, quote) tuples so we can sort by turn order at the end.
    # This ensures correct chronological ordering even if evidence_span_ids
    # are not in turn order (e.g., sub-spans from a long behavioral arc).
    keyed_quotes: list[tuple[int, QuoteObject]] = []
    norm_target = target_speaker_label.replace("\\_", "_").strip().lower() if target_speaker_label else None
    for es_id in evidence_span_ids:
        span = spans_by_id.get(es_id)
        if not span:
            continue
        turn_start = span.get("turn_start_id")
        turn_end = span.get("turn_end_id")
        mid = span.get("meeting_id") or meeting_id

        # Check whether the span covers multiple speakers
        is_multi_speaker = False
        if (
            turn_map
            and isinstance(turn_start, int)
            and isinstance(turn_end, int)
        ):
            span_speakers = {
                turn_map[tid].speaker_label.replace("\\_", "_")
                for tid in range(turn_start, turn_end + 1)
                if tid in turn_map
            }
            is_multi_speaker = len(span_speakers) > 1

        if is_multi_speaker:
            _logger = logging.getLogger(__name__)
            _logger.info(
                "multi-speaker span %s: norm_target=%r, speakers=%s",
                es_id, norm_target,
                [(tid, turn_map[tid].speaker_label) for tid in range(turn_start, turn_end + 1) if tid in turn_map],
            )
            for tid in range(turn_start, turn_end + 1):
                turn = turn_map.get(tid)
                if not turn:
                    continue
                ts = (
                    format_timestamp(turn.start_time_sec)
                    if turn.start_time_sec is not None
                    else None
                )
                # Determine if this turn is from the target speaker
                is_target: Optional[bool] = None
                if norm_target is not None:
                    is_target = turn.speaker_label.replace("\\_", "_").strip().lower() == norm_target
                keyed_quotes.append((
                    tid,
                    QuoteObject(
                        speaker_label=turn.speaker_label,
                        quote_text=turn.text[:_QUOTE_MAX_CHARS],
                        meeting_id=mid,
                        transcript_id=transcript_id,
                        span_id=es_id,
                        start_timestamp=ts,
                        is_target_speaker=is_target,
                    ),
                ))
        else:
            excerpt = _strip_speaker_prefix((span.get("excerpt") or ""))[:_QUOTE_MAX_CHARS]
            start_ts: Optional[str] = None
            if turn_map and isinstance(turn_start, int):
                turn = turn_map.get(turn_start)
                if turn and turn.start_time_sec is not None:
                    start_ts = format_timestamp(turn.start_time_sec)
            # Single-speaker spans are selected by the LLM as evidence for a
            # specific pattern — leave is_target_speaker as None so the
            # frontend falls back to its default (target) styling.
            keyed_quotes.append((
                turn_start if isinstance(turn_start, int) else 0,
                QuoteObject(
                    speaker_label=None,
                    quote_text=excerpt,
                    meeting_id=mid,
                    transcript_id=transcript_id,
                    span_id=es_id,
                    start_timestamp=start_ts,
                ),
            ))
    # Sort by turn order for correct chronological rendering
    keyed_quotes.sort(key=lambda kq: kq[0])
    return [q for _, q in keyed_quotes]


def resolve_coaching_output(
    parsed_json: dict,
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
    turn_map: Optional[dict[int, Turn]] = None,
    target_speaker_label: Optional[str] = None,
) -> tuple[
    list[HighlightItem],
    Optional[HighlightItem],
    Optional[MicroExperimentWithQuotes],
]:
    """Resolve coaching strengths, focus, and micro_experiment.

    Strengths and focus are lightweight HighlightItems (pattern_id + message only).
    Detailed evidence, rewrites, and quotes live on coaching.pattern_coaching.
    """
    coaching = parsed_json.get("coaching", {})

    # Build a score lookup from pattern_snapshot to filter low-score strengths
    score_by_pattern = {
        ps.get("pattern_id"): ps.get("score")
        for ps in parsed_json.get("pattern_snapshot", [])
    }

    strengths: list[HighlightItem] = []
    for s in coaching.get("strengths", []):
        # Guardrail: skip strengths whose pattern score is below 50%
        if (score_by_pattern.get(s.get("pattern_id")) or 0) < 0.5:
            continue
        strengths.append(
            HighlightItem(
                pattern_id=s.get("pattern_id", ""),
                message=s.get("message", ""),
            )
        )

    focus: Optional[HighlightItem] = None
    focus_list = coaching.get("focus", [])
    if focus_list:
        f = focus_list[0]
        focus = HighlightItem(
            pattern_id=f.get("pattern_id", ""),
            message=f.get("message", ""),
        )

    micro_exp: Optional[MicroExperimentWithQuotes] = None
    micro_list = coaching.get("micro_experiment", [])
    if micro_list:
        m = micro_list[0]
        quotes = resolve_quotes(m.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id, turn_map, target_speaker_label)
        micro_exp = MicroExperimentWithQuotes(
            experiment_id=m.get("experiment_id", ""),
            title=m.get("title", ""),
            instruction=m.get("instruction", ""),
            success_marker=m.get("success_marker", ""),
            related_patterns=m.get("related_patterns", []),
            quotes=quotes,
        )

    return strengths, focus, micro_exp


def resolve_pattern_snapshot(
    parsed_json: dict,
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
    turn_map: Optional[dict[int, Turn]] = None,
    target_speaker_label: Optional[str] = None,
) -> list[PatternSnapshotItem]:
    """Resolve pattern_snapshot items with per-pattern quotes (scoring only)."""
    raw_snapshot = parsed_json.get("pattern_snapshot") or []
    snapshot_items: list[PatternSnapshotItem] = []
    for ps in raw_snapshot:
        # Skip resolving quotes for non-evaluable patterns — they should not
        # have evidence spans, but some older model outputs include them.
        es_ids = ps.get("evidence_span_ids", []) if ps.get("evaluable_status") == "evaluable" else []
        ps_quotes = resolve_quotes(
            es_ids, spans_by_id, transcript_id, meeting_id, turn_map, target_speaker_label
        )
        snapshot_items.append(PatternSnapshotItem(
            pattern_id=ps.get("pattern_id", ""),
            cluster_id=ps.get("cluster_id"),
            scoring_type=ps.get("scoring_type"),
            evaluable_status=ps.get("evaluable_status", "not_evaluable"),
            score=ps.get("score"),
            opportunity_count=ps.get("opportunity_count"),
            quotes=ps_quotes,
            success_span_ids=ps.get("success_evidence_span_ids", []),
        ))
    return snapshot_items


def resolve_pattern_coaching(
    parsed_json: dict,
) -> list[PatternCoachingItem]:
    """Resolve coaching.pattern_coaching items into PatternCoachingItem DTOs."""
    coaching = parsed_json.get("coaching", {})
    raw_items = coaching.get("pattern_coaching", [])
    return [
        PatternCoachingItem(
            pattern_id=pc.get("pattern_id", ""),
            notes=pc.get("notes"),
            coaching_note=pc.get("coaching_note"),
            suggested_rewrite=pc.get("suggested_rewrite"),
            rewrite_for_span_id=pc.get("rewrite_for_span_id"),
            best_success_span_id=pc.get("best_success_span_id"),
        )
        for pc in raw_items
    ]


def resolve_experiment_coaching(
    parsed_json: dict,
) -> Optional[ExperimentCoachingItem]:
    """Resolve coaching.experiment_coaching into ExperimentCoachingItem DTO."""
    coaching = parsed_json.get("coaching", {})
    ec = coaching.get("experiment_coaching")
    if not isinstance(ec, dict):
        return None
    return ExperimentCoachingItem(
        coaching_note=ec.get("coaching_note"),
        suggested_rewrite=ec.get("suggested_rewrite"),
        rewrite_for_span_id=ec.get("rewrite_for_span_id"),
    )


def build_spans_lookup(parsed_json: dict) -> dict[str, dict]:
    """Build {evidence_span_id: span_dict} from parsed JSON."""
    evidence_spans: list[dict] = parsed_json.get("evidence_spans", [])
    return {s.get("evidence_span_id", ""): s for s in evidence_spans}


# ── Quote cleanup integration ────────────────────────────────────────────────


def _collect_quotes_for_cleanup(
    micro_exp: Optional[MicroExperimentWithQuotes],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection_quotes: Optional[list[QuoteObject]] = None,
) -> list[QuoteObject]:
    """Collect all QuoteObjects from the resolved coaching/snapshot output."""
    all_quotes: list[QuoteObject] = []
    if micro_exp:
        all_quotes.extend(micro_exp.quotes)
    for snap in snapshot_items:
        all_quotes.extend(snap.quotes)
    if experiment_detection_quotes:
        all_quotes.extend(experiment_detection_quotes)
    return all_quotes


def _collect_coaching_blurbs(
    strengths: list[HighlightItem],
    focus: Optional[HighlightItem],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection: Optional[ExperimentDetectionWithQuotes] = None,
) -> list[dict]:
    """Collect coaching text fields for cleanup as {id, text, category} dicts.

    Each item gets a unique id so we can write the cleaned text back to the
    correct DTO field. Returns only non-empty text fields.
    """
    blurbs: list[dict] = []

    for i, s in enumerate(strengths):
        if s.message:
            blurbs.append({"id": f"str:{i}:message", "text": s.message, "category": "coaching_blurb"})

    if focus and focus.message:
        blurbs.append({"id": "focus:message", "text": focus.message, "category": "coaching_blurb"})

    for i, snap in enumerate(snapshot_items):
        if snap.notes:
            blurbs.append({"id": f"snap:{i}:notes", "text": snap.notes, "category": "coaching_blurb"})
        if snap.coaching_note:
            blurbs.append({"id": f"snap:{i}:coaching_note", "text": snap.coaching_note, "category": "coaching_blurb"})
        if snap.suggested_rewrite:
            blurbs.append({"id": f"snap:{i}:rewrite", "text": snap.suggested_rewrite, "category": "coaching_blurb"})

    if experiment_detection:
        if experiment_detection.coaching_note:
            blurbs.append({"id": "det:coaching_note", "text": experiment_detection.coaching_note, "category": "coaching_blurb"})
        if experiment_detection.suggested_rewrite:
            blurbs.append({"id": "det:rewrite", "text": experiment_detection.suggested_rewrite, "category": "coaching_blurb"})

    return blurbs


def _apply_blurb_results(
    cleaned: dict[str, str],
    strengths: list[HighlightItem],
    focus: Optional[HighlightItem],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection: Optional[ExperimentDetectionWithQuotes] = None,
) -> None:
    """Write cleaned coaching blurb text back to DTO objects in-place."""
    for i, s in enumerate(strengths):
        key = f"str:{i}:message"
        if key in cleaned:
            s.message = cleaned[key]

    if focus:
        if "focus:message" in cleaned:
            focus.message = cleaned["focus:message"]

    for i, snap in enumerate(snapshot_items):
        key_notes = f"snap:{i}:notes"
        key_cn = f"snap:{i}:coaching_note"
        key_rw = f"snap:{i}:rewrite"
        if key_notes in cleaned:
            snap.notes = cleaned[key_notes]
        if key_cn in cleaned:
            snap.coaching_note = cleaned[key_cn]
        if key_rw in cleaned:
            snap.suggested_rewrite = cleaned[key_rw]

    if experiment_detection:
        if "det:coaching_note" in cleaned:
            experiment_detection.coaching_note = cleaned["det:coaching_note"]
        if "det:rewrite" in cleaned:
            experiment_detection.suggested_rewrite = cleaned["det:rewrite"]


def apply_quote_cleanup(
    strengths: list[HighlightItem],
    focus: Optional[HighlightItem],
    micro_exp: Optional[MicroExperimentWithQuotes],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection_quotes: Optional[list[QuoteObject]] = None,
    experiment_detection: Optional[ExperimentDetectionWithQuotes] = None,
) -> None:
    """Apply post-processing cleanup to all quote texts and coaching blurbs in-place.

    This function collects all transcript quotes and coaching blurbs, sends them
    through the cleanup LLM in a single batch call, then writes the cleaned text
    back. If cleanup is disabled or fails, texts are left unchanged.
    """
    if not _CLEANUP_ENABLED:
        return

    all_quotes = _collect_quotes_for_cleanup(
        micro_exp, snapshot_items, experiment_detection_quotes
    )

    # Deduplicate transcript quotes by (span_id, quote_text) to avoid sending
    # the same text twice.
    seen: dict[str, list[QuoteObject]] = {}
    cleanup_input: list[dict] = []
    for q in all_quotes:
        dedup_key = f"{q.span_id}:{q.quote_text}"
        if dedup_key in seen:
            seen[dedup_key].append(q)
            continue
        seen[dedup_key] = [q]
        cleanup_input.append({
            "id": dedup_key,
            "text": q.quote_text,
            "abbreviate": q.is_target_speaker is False,  # non-target in multi-speaker
            "category": "transcript_quote",
        })

    # Collect coaching blurbs (messages, notes, coaching_notes, rewrites)
    blurb_items = _collect_coaching_blurbs(
        strengths, focus, snapshot_items, experiment_detection
    )
    cleanup_input.extend(blurb_items)

    if not cleanup_input:
        return

    logger = logging.getLogger(__name__)
    logger.info(
        "Running cleanup on %d transcript quotes + %d coaching blurbs",
        len(cleanup_input) - len(blurb_items),
        len(blurb_items),
    )

    cleaned = cleanup_quotes(cleanup_input)

    # Write cleaned text back to all QuoteObjects
    for dedup_key, quote_list in seen.items():
        cleaned_text = cleaned.get(dedup_key)
        if cleaned_text:
            for q in quote_list:
                q.quote_text = cleaned_text

    # Write cleaned text back to coaching blurb fields
    _apply_blurb_results(cleaned, strengths, focus, snapshot_items, experiment_detection)
