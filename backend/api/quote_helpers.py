"""
api/quote_helpers.py — Shared helpers for resolving evidence_span_ids into QuoteObjects.

Used by routes_runs.py (single meeting) and routes_coachee.py (baseline pack).
"""
from __future__ import annotations

import logging
import os

import json
from typing import Optional

from ..core.airtable_client import AirtableClient
from ..core.models import Turn
from ..core.quote_cleanup import cleanup_quotes
from ..core.transcript_parser import parse_transcript
from .dto import (
    CoachingItemWithQuotes,
    MicroExperimentWithQuotes,
    PatternSnapshotItem,
    QuoteObject,
)

# Feature flag: set QUOTE_CLEANUP_ENABLED=1 to enable post-processing cleanup.
_CLEANUP_ENABLED = os.getenv("QUOTE_CLEANUP_ENABLED", "0") == "1"

_QUOTE_MAX_CHARS = 2000


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
            source_id=tr_fields.get("Transcript ID") or transcript_record_id,
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
    quotes: list[QuoteObject] = []
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
                quotes.append(
                    QuoteObject(
                        speaker_label=turn.speaker_label,
                        quote_text=turn.text[:_QUOTE_MAX_CHARS],
                        meeting_id=mid,
                        transcript_id=transcript_id,
                        span_id=es_id,
                        start_timestamp=ts,
                        is_target_speaker=is_target,
                    )
                )
        else:
            excerpt = (span.get("excerpt") or "")[:_QUOTE_MAX_CHARS]
            start_ts: Optional[str] = None
            if turn_map and isinstance(turn_start, int):
                turn = turn_map.get(turn_start)
                if turn and turn.start_time_sec is not None:
                    start_ts = format_timestamp(turn.start_time_sec)
            # Single-speaker spans are selected by the LLM as evidence for a
            # specific pattern — leave is_target_speaker as None so the
            # frontend falls back to its default (target) styling.
            quotes.append(
                QuoteObject(
                    speaker_label=None,
                    quote_text=excerpt,
                    meeting_id=mid,
                    transcript_id=transcript_id,
                    span_id=es_id,
                    start_timestamp=start_ts,
                )
            )
    return quotes


def resolve_coaching_output(
    parsed_json: dict,
    spans_by_id: dict[str, dict],
    transcript_id: Optional[str],
    meeting_id: Optional[str],
    turn_map: Optional[dict[int, Turn]] = None,
    target_speaker_label: Optional[str] = None,
) -> tuple[
    list[CoachingItemWithQuotes],
    Optional[CoachingItemWithQuotes],
    Optional[MicroExperimentWithQuotes],
]:
    """Resolve coaching_output strengths, focus, and micro_experiment with quotes."""
    coaching = parsed_json.get("coaching_output", {})

    strengths: list[CoachingItemWithQuotes] = []
    for s in coaching.get("strengths", []):
        quotes = resolve_quotes(s.get("evidence_span_ids", []), spans_by_id, transcript_id, meeting_id, turn_map, target_speaker_label)
        strengths.append(
            CoachingItemWithQuotes(
                pattern_id=s.get("pattern_id", ""),
                message=s.get("message", ""),
                quotes=quotes,
            )
        )

    focus: Optional[CoachingItemWithQuotes] = None
    focus_list = coaching.get("focus", [])
    if focus_list:
        f = focus_list[0]
        rewrite_span_id = f.get("rewrite_for_span_id")
        all_es_ids = f.get("evidence_span_ids", [])

        if rewrite_span_id and rewrite_span_id in all_es_ids:
            primary_ids = [rewrite_span_id]
            additional_ids = [eid for eid in all_es_ids if eid != rewrite_span_id]
        else:
            primary_ids = all_es_ids[:1]
            additional_ids = all_es_ids[1:]

        primary_quotes = resolve_quotes(primary_ids, spans_by_id, transcript_id, meeting_id, turn_map, target_speaker_label)
        additional_quotes = resolve_quotes(additional_ids, spans_by_id, transcript_id, meeting_id, turn_map, target_speaker_label)

        focus = CoachingItemWithQuotes(
            pattern_id=f.get("pattern_id", ""),
            message=f.get("message", ""),
            quotes=primary_quotes,
            suggested_rewrite=f.get("suggested_rewrite"),
            rewrite_for_span_id=rewrite_span_id,
            additional_quotes=additional_quotes,
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
            pattern_id=m.get("pattern_id", ""),
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
    """Resolve pattern_snapshot items with per-pattern quotes."""
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
            tier=ps.get("tier"),
            evaluable_status=ps.get("evaluable_status", "not_evaluable"),
            numerator=ps.get("numerator"),
            denominator=ps.get("denominator"),
            ratio=ps.get("ratio"),
            balance_assessment=ps.get("balance_assessment"),
            notes=ps.get("notes"),
            quotes=ps_quotes,
            coaching_note=ps.get("coaching_note"),
            suggested_rewrite=ps.get("suggested_rewrite"),
            rewrite_for_span_id=ps.get("rewrite_for_span_id"),
        ))
    return snapshot_items


def build_spans_lookup(parsed_json: dict) -> dict[str, dict]:
    """Build {evidence_span_id: span_dict} from parsed JSON."""
    evidence_spans: list[dict] = parsed_json.get("evidence_spans", [])
    return {s.get("evidence_span_id", ""): s for s in evidence_spans}


# ── Quote cleanup integration ────────────────────────────────────────────────


def _collect_quotes_for_cleanup(
    strengths: list[CoachingItemWithQuotes],
    focus: Optional[CoachingItemWithQuotes],
    micro_exp: Optional[MicroExperimentWithQuotes],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection_quotes: Optional[list[QuoteObject]] = None,
) -> list[QuoteObject]:
    """Collect all QuoteObjects from the resolved coaching/snapshot output."""
    all_quotes: list[QuoteObject] = []
    for s in strengths:
        all_quotes.extend(s.quotes)
    if focus:
        all_quotes.extend(focus.quotes)
        all_quotes.extend(focus.additional_quotes)
    if micro_exp:
        all_quotes.extend(micro_exp.quotes)
    for snap in snapshot_items:
        all_quotes.extend(snap.quotes)
    if experiment_detection_quotes:
        all_quotes.extend(experiment_detection_quotes)
    return all_quotes


def apply_quote_cleanup(
    strengths: list[CoachingItemWithQuotes],
    focus: Optional[CoachingItemWithQuotes],
    micro_exp: Optional[MicroExperimentWithQuotes],
    snapshot_items: list[PatternSnapshotItem],
    experiment_detection_quotes: Optional[list[QuoteObject]] = None,
) -> None:
    """Apply post-processing cleanup to all quote texts in-place.

    This function collects all quotes, sends them through the cleanup LLM in a
    single batch call, then writes the cleaned text back. If cleanup is disabled
    or fails, quotes are left unchanged.
    """
    if not _CLEANUP_ENABLED:
        return

    all_quotes = _collect_quotes_for_cleanup(
        strengths, focus, micro_exp, snapshot_items, experiment_detection_quotes
    )
    if not all_quotes:
        return

    # Deduplicate by (span_id, quote_text) to avoid sending the same text twice.
    # Multiple QuoteObjects may share the same underlying text (e.g., same span
    # referenced by both pattern_snapshot and coaching_output).
    seen: dict[str, list[QuoteObject]] = {}
    cleanup_input: list[dict] = []
    for idx, q in enumerate(all_quotes):
        dedup_key = f"{q.span_id}:{q.quote_text}"
        if dedup_key in seen:
            seen[dedup_key].append(q)
            continue
        seen[dedup_key] = [q]
        cleanup_input.append({
            "id": dedup_key,
            "text": q.quote_text,
            "abbreviate": q.is_target_speaker is False,  # non-target in multi-speaker
        })

    if not cleanup_input:
        return

    logger = logging.getLogger(__name__)
    logger.info("Running quote cleanup on %d unique quotes", len(cleanup_input))

    cleaned = cleanup_quotes(cleanup_input)

    # Write cleaned text back to all QuoteObjects
    for dedup_key, quote_list in seen.items():
        cleaned_text = cleaned.get(dedup_key)
        if cleaned_text:
            for q in quote_list:
                q.quote_text = cleaned_text
