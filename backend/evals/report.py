"""
report.py - Shared reporting utilities for eval scripts.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def compute_pattern_stats(scores: list[float | None]) -> dict[str, Any]:
    """Compute summary statistics for a list of pattern scores.

    Returns dict with mean, median, stdev, iqr, min, max, n, n_missing.
    Scores of None (from insufficient_signal) are tracked separately.
    """
    valid = [s for s in scores if s is not None]
    n_missing = len(scores) - len(valid)

    if not valid:
        return {
            "mean": None, "median": None, "stdev": None,
            "iqr": None, "q1": None, "q3": None,
            "min": None, "max": None,
            "n": 0, "n_missing": n_missing,
        }

    mean = statistics.mean(valid)
    median = statistics.median(valid)
    stdev = statistics.stdev(valid) if len(valid) >= 2 else 0.0

    sorted_v = sorted(valid)
    n = len(sorted_v)
    q1 = sorted_v[n // 4] if n >= 4 else sorted_v[0]
    q3 = sorted_v[(3 * n) // 4] if n >= 4 else sorted_v[-1]

    return {
        "mean": round(mean, 4),
        "median": round(median, 4),
        "stdev": round(stdev, 4),
        "iqr": round(q3 - q1, 4),
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "min": round(min(valid), 4),
        "max": round(max(valid), 4),
        "n": len(valid),
        "n_missing": n_missing,
    }


def compute_int_stats(values: list[int | None]) -> dict[str, Any]:
    """Compute summary statistics for integer values (e.g., opportunity_count)."""
    valid = [v for v in values if v is not None]
    if not valid:
        return {"mean": None, "stdev": None, "min": None, "max": None, "n": 0}

    mean = statistics.mean(valid)
    stdev = statistics.stdev(valid) if len(valid) >= 2 else 0.0
    return {
        "mean": round(mean, 2),
        "stdev": round(stdev, 2),
        "min": min(valid),
        "max": max(valid),
        "n": len(valid),
    }


def format_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format a list of rows into a markdown table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def _pad_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)) + " |"

    lines = [
        _pad_row(headers),
        "| " + " | ".join("-" * w for w in col_widths) + " |",
    ]
    for row in rows:
        lines.append(_pad_row(row))
    return "\n".join(lines)


def format_intra_transcript_report(
    transcript_id: str,
    n_runs: int,
    gate1_pass_rate: float,
    pattern_results: dict[str, dict],
) -> str:
    """Format the intra-transcript repeatability report as markdown."""
    lines = [
        f"# Intra-Transcript Repeatability Report",
        f"",
        f"**Transcript**: {transcript_id}",
        f"**Runs**: {n_runs}",
        f"**Gate1 pass rate**: {gate1_pass_rate:.0%}",
        f"",
        f"## Score Stability (lower IQR = more repeatable)",
        f"",
    ]

    headers = ["Pattern", "Mean", "Median", "IQR", "StdDev", "Min", "Max", "N", "Insuff"]
    rows = []
    for pid, stats in pattern_results.items():
        s = stats["score"]
        rows.append([
            pid,
            _fmt(s["mean"]), _fmt(s["median"]), _fmt(s["iqr"]),
            _fmt(s["stdev"]), _fmt(s["min"]), _fmt(s["max"]),
            str(s["n"]), str(s["n_missing"]),
        ])
    lines.append(format_markdown_table(headers, rows))

    lines.extend(["", "## Opportunity Count Stability (lower StdDev = more stable)", ""])
    headers2 = ["Pattern", "Mean OppCount", "StdDev", "Min", "Max"]
    rows2 = []
    for pid, stats in pattern_results.items():
        o = stats["opportunity_count"]
        rows2.append([
            pid, _fmt(o["mean"]), _fmt(o["stdev"]),
            str(o["min"]) if o["min"] is not None else "-",
            str(o["max"]) if o["max"] is not None else "-",
        ])
    lines.append(format_markdown_table(headers2, rows2))

    return "\n".join(lines)


def format_inter_transcript_report(
    transcript_ids: list[str],
    per_transcript: dict[str, dict],
    cross_transcript: dict[str, dict],
) -> str:
    """Format the inter-transcript discriminant validity report as markdown."""
    lines = [
        f"# Inter-Transcript Discriminant Validity Report",
        f"",
        f"**Transcripts**: {len(transcript_ids)}",
        f"",
        f"## Per-Transcript Mean Scores",
        f"",
    ]

    headers = ["Pattern"] + transcript_ids
    rows = []
    for pid in cross_transcript:
        row = [pid]
        for tid in transcript_ids:
            ts = per_transcript.get(tid, {}).get(pid, {}).get("score", {})
            row.append(_fmt(ts.get("mean")))
        rows.append(row)
    lines.append(format_markdown_table(headers, rows))

    lines.extend([
        "", "## Cross-Transcript Distribution (wider IQR = better discrimination)", ""
    ])
    headers2 = ["Pattern", "Cross Min", "Cross Max", "Cross Mean", "Cross IQR", "Cross StdDev", "Mean Intra IQR", "Signal/Noise"]
    rows2 = []
    for pid, cs in cross_transcript.items():
        rows2.append([
            pid,
            _fmt(cs.get("cross_min")),
            _fmt(cs.get("cross_max")),
            _fmt(cs.get("cross_mean")),
            _fmt(cs.get("cross_iqr")),
            _fmt(cs.get("cross_stdev")),
            _fmt(cs.get("mean_intra_iqr")),
            _fmt(cs.get("signal_to_noise")),
        ])
    lines.append(format_markdown_table(headers2, rows2))

    return "\n".join(lines)


# ── Per-opportunity detail extraction ────────────────────────────────────────

_STANDARD_TIERS = [0.0, 0.25, 0.5, 0.75, 1.0]


def extract_opportunity_details(
    parsed_json: dict,
) -> dict[str, list[dict[str, Any]]]:
    """Extract per-opportunity detail from a single run's parsed JSON.

    Returns dict keyed by pattern_id → list of opportunity dicts with:
      event_id, pattern_id, success, reason_code, turn_range
    """
    details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for oe in parsed_json.get("opportunity_events", []):
        pid = oe.get("pattern_id")
        if not pid or oe.get("count_decision") != "counted":
            continue

        turn_start = oe.get("turn_start_id")
        turn_end = oe.get("turn_end_id")
        if turn_start is not None and turn_end is not None:
            turn_range = f"T{turn_start}" if turn_start == turn_end else f"T{turn_start}-{turn_end}"
        elif turn_start is not None:
            turn_range = f"T{turn_start}"
        else:
            turn_range = "?"

        details[pid].append({
            "event_id": oe.get("event_id", "?"),
            "pattern_id": pid,
            "success": oe.get("success"),
            "reason_code": oe.get("reason_code", ""),
            "notes": oe.get("notes", ""),
            "turn_range": turn_range,
            "turn_start_id": turn_start,
            "turn_end_id": turn_end,
        })
    return dict(details)


def compute_tier_distribution(
    all_opportunity_details: list[list[dict[str, Any]]],
    pattern_id: str,
) -> dict[str, Any]:
    """Compute tier distribution for a pattern across multiple runs.

    all_opportunity_details: list of per-run detail lists (each from extract_opportunity_details()[pid])
    Returns dict with tier counts, percentages, and total.
    """
    scores: list[float] = []
    for run_details in all_opportunity_details:
        for opp in run_details:
            if opp.get("success") is not None:
                scores.append(opp["success"])

    total = len(scores)
    if total == 0:
        return {"total": 0, "tiers": {}, "other_count": 0, "other_pct": 0}

    tier_counts: dict[str, int] = {}
    other_count = 0
    for tier in _STANDARD_TIERS:
        tier_counts[f"{tier:.2f}"] = 0

    for s in scores:
        # Check if score matches a standard tier (within float tolerance)
        matched = False
        for tier in _STANDARD_TIERS:
            if abs(s - tier) < 0.001:
                tier_counts[f"{tier:.2f}"] += 1
                matched = True
                break
        if not matched:
            other_count += 1

    tier_pcts: dict[str, float] = {
        k: round(v / total * 100, 1) for k, v in tier_counts.items()
    }

    # If there are non-standard scores, break them down too
    other_breakdown: dict[str, int] = {}
    if other_count > 0:
        for s in scores:
            matched = any(abs(s - tier) < 0.001 for tier in _STANDARD_TIERS)
            if not matched:
                key = f"{s:.2f}"
                other_breakdown[key] = other_breakdown.get(key, 0) + 1

    return {
        "total": total,
        "tiers": tier_counts,
        "tier_pcts": tier_pcts,
        "other_count": other_count,
        "other_pct": round(other_count / total * 100, 1),
        "other_breakdown": other_breakdown,
    }


def collect_reason_codes(
    all_opportunity_details: list[list[dict[str, Any]]],
    transcript_id: str | None = None,
) -> list[dict[str, Any]]:
    """Collect reason codes with their associated score tiers.

    Returns list of dicts: {reason_code, tier, transcript_id, count}
    """
    code_counts: dict[tuple[str, float], int] = defaultdict(int)
    for run_details in all_opportunity_details:
        for opp in run_details:
            rc = opp.get("reason_code", "")
            score = opp.get("success")
            if rc and score is not None:
                code_counts[(rc, score)] += 1

    result = []
    for (rc, tier), count in sorted(code_counts.items(), key=lambda x: (-x[1], x[0][1], x[0][0])):
        entry: dict[str, Any] = {"reason_code": rc, "tier": tier, "count": count}
        if transcript_id:
            entry["transcript_id"] = transcript_id
        result.append(entry)
    return result


# ── Intra-meeting detail formatting ─────────────────────────────────────────

def format_tier_distribution_table(
    tier_distributions: dict[str, dict[str, Any]],
) -> str:
    """Format per-pattern tier distribution as a summary markdown table."""
    lines = ["", "## Per-Opportunity Tier Usage", ""]

    headers = ["Pattern", "n_opps", "0.0", "0.25", "0.5", "0.75", "1.0", "Other"]
    rows = []
    other_notes: list[str] = []
    for pid, dist in tier_distributions.items():
        total = dist["total"]
        if total == 0:
            rows.append([pid, "0", "-", "-", "-", "-", "-", "-"])
            continue
        pcts = dist["tier_pcts"]
        other_label = "0%"
        if dist["other_count"] > 0:
            other_label = f"{dist['other_pct']:.0f}%"
            # Build breakdown note
            breakdown = dist.get("other_breakdown", {})
            if breakdown:
                parts = [f"{k}={v}" for k, v in sorted(breakdown.items())]
                other_notes.append(f"- **{pid}** Other breakdown: {', '.join(parts)}")
        rows.append([
            pid,
            str(total),
            f"{pcts.get('0.00', 0):.0f}%",
            f"{pcts.get('0.25', 0):.0f}%",
            f"{pcts.get('0.50', 0):.0f}%",
            f"{pcts.get('0.75', 0):.0f}%",
            f"{pcts.get('1.00', 0):.0f}%",
            other_label,
        ])
    lines.append(format_markdown_table(headers, rows))

    if other_notes:
        lines.extend(["", "**Non-standard tier breakdown:**"] + other_notes)

    return "\n".join(lines)


def format_opportunity_alignment_table(
    pattern_id: str,
    all_run_details: list[list[dict[str, Any]]],
    n_runs: int,
    parsed_transcript: Any | None = None,
    include_text: bool = False,
) -> str:
    """Format per-opportunity alignment across runs for a single pattern.

    Shows how each evidence span was scored in each run, with optional transcript text.
    """
    # Collect all unique turn_ranges across all runs
    all_turn_ranges: list[str] = []
    seen: set[str] = set()
    for run_details in all_run_details:
        for opp in run_details:
            tr = opp["turn_range"]
            if tr not in seen:
                all_turn_ranges.append(tr)
                seen.add(tr)

    # Sort turn_ranges by numeric value of first turn
    def _sort_key(tr: str) -> int:
        num_str = tr.lstrip("T").split("-")[0]
        try:
            return int(num_str)
        except ValueError:
            return 9999
    all_turn_ranges.sort(key=_sort_key)

    if not all_turn_ranges:
        return ""

    lines = [f"### {pattern_id}", ""]

    # Build header
    header_parts = ["Turn"]
    if include_text and parsed_transcript:
        header_parts.append("Text (truncated)")
    for i in range(n_runs):
        header_parts.append(f"Run {i+1}")

    rows = []
    for tr in all_turn_ranges:
        row_parts = [tr]

        # Add transcript text if requested
        if include_text and parsed_transcript:
            text = _lookup_turn_text(tr, parsed_transcript)
            row_parts.append(text)

        # For each run, find the matching opportunity
        for run_details in all_run_details:
            match = [o for o in run_details if o["turn_range"] == tr]
            if match:
                opp = match[0]
                score = opp["success"]
                rc = opp["reason_code"]
                row_parts.append(f"{score} {rc}")
            else:
                row_parts.append("-")
        rows.append(row_parts)

    lines.append(format_markdown_table(header_parts, rows))
    return "\n".join(lines)


def _lookup_turn_text(turn_range: str, parsed_transcript: Any, max_chars: int = 200) -> str:
    """Look up transcript text for a turn range like 'T5' or 'T5-7'."""
    try:
        parts = turn_range.lstrip("T").split("-")
        start = int(parts[0])
        end = int(parts[-1]) if len(parts) > 1 else start
    except (ValueError, IndexError):
        return "?"

    turns = getattr(parsed_transcript, "turns", [])
    texts = []
    extra_turns = 0
    for turn in turns:
        turn_id = getattr(turn, "turn_id", None)
        if turn_id is not None and start <= turn_id <= end:
            speaker = getattr(turn, "speaker_label", "?")
            text = getattr(turn, "text", "")
            if not texts:
                truncated = text[:max_chars] + ("..." if len(text) > max_chars else "")
                texts.append(f"({speaker}) {truncated}")
            else:
                extra_turns += 1

    result = texts[0] if texts else "?"
    if extra_turns > 0:
        result += f" (+{extra_turns} more turns)"
    return result


# ── Inter-meeting detail formatting ──────────────────────────────────────────

def format_cross_meeting_tier_distributions(
    pattern_id: str,
    transcript_ids: list[str],
    per_transcript_tiers: dict[str, dict[str, Any]],
) -> str:
    """Format cross-meeting tier distribution table for a single pattern."""
    lines = [f"### {pattern_id}", ""]

    headers = ["Meeting", "n_opps", "0.0", "0.25", "0.5", "0.75", "1.0", "Other"]
    rows = []
    other_notes: list[str] = []
    for tid in transcript_ids:
        dist = per_transcript_tiers.get(tid)
        if not dist or dist["total"] == 0:
            rows.append([tid, "0", "-", "-", "-", "-", "-", "-"])
            continue
        pcts = dist["tier_pcts"]
        other_label = "0%"
        if dist["other_count"] > 0:
            other_label = f"{dist['other_pct']:.0f}%"
            breakdown = dist.get("other_breakdown", {})
            if breakdown:
                parts = [f"{k}={v}" for k, v in sorted(breakdown.items())]
                other_notes.append(f"- **{tid}**: {', '.join(parts)}")
        rows.append([
            tid,
            str(dist["total"]),
            f"{pcts.get('0.00', 0):.0f}%",
            f"{pcts.get('0.25', 0):.0f}%",
            f"{pcts.get('0.50', 0):.0f}%",
            f"{pcts.get('0.75', 0):.0f}%",
            f"{pcts.get('1.00', 0):.0f}%",
            other_label,
        ])
    lines.append(format_markdown_table(headers, rows))

    if other_notes:
        lines.extend(["", "Non-standard tier breakdown:"] + other_notes)

    return "\n".join(lines)


def format_reason_code_analysis_by_tier(
    pattern_id: str,
    all_reason_codes: list[dict[str, Any]],
    transcript_ids: list[str],
) -> str:
    """Format reason codes grouped by tier for a single pattern.

    all_reason_codes: combined list from collect_reason_codes() across all transcripts.
    Each entry has: reason_code, tier, count, transcript_id.
    """
    if not all_reason_codes:
        return ""

    lines = [f"### {pattern_id}", ""]

    # Group by tier
    by_tier: dict[float, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for entry in all_reason_codes:
        tier = entry["tier"]
        rc = entry["reason_code"]
        tid = entry.get("transcript_id", "?")
        by_tier[tier][rc][tid] += entry["count"]

    for tier in sorted(by_tier.keys(), reverse=True):
        lines.append(f"**Tier {tier}**")
        codes = by_tier[tier]
        # Sort by total count descending
        sorted_codes = sorted(
            codes.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True,
        )
        for rc, tid_counts in sorted_codes:
            total = sum(tid_counts.values())
            breakdown = ", ".join(
                f"{tid}={c}" for tid, c in sorted(tid_counts.items()) if c > 0
            )
            lines.append(f"- {rc} (x{total}: {breakdown})")
        lines.append("")

    return "\n".join(lines)


def format_reason_code_cross_tab(
    pattern_id: str,
    all_reason_codes: list[dict[str, Any]],
    transcript_ids: list[str],
) -> str:
    """Format raw reason code frequency cross-tabulation (--detail mode)."""
    if not all_reason_codes:
        return ""

    lines = [f"### {pattern_id} (raw cross-tabulation)", ""]

    # Build cross-tab: reason_code → {tier, per-transcript count}
    cross: dict[str, dict[str, Any]] = {}
    for entry in all_reason_codes:
        rc = entry["reason_code"]
        tid = entry.get("transcript_id", "?")
        if rc not in cross:
            cross[rc] = {"tier": entry["tier"]}
            for t in transcript_ids:
                cross[rc][t] = 0
        cross[rc][tid] = cross[rc].get(tid, 0) + entry["count"]

    # Sort by tier descending, then by total count descending
    sorted_codes = sorted(
        cross.items(),
        key=lambda x: (-x[1]["tier"], -sum(x[1].get(t, 0) for t in transcript_ids)),
    )

    headers = ["Reason Code", "Tier"] + transcript_ids + ["Total"]
    rows = []
    for rc, data in sorted_codes:
        total = sum(data.get(t, 0) for t in transcript_ids)
        row = [rc, f"{data['tier']:.2f}"]
        for tid in transcript_ids:
            row.append(str(data.get(tid, 0)))
        row.append(str(total))
        rows.append(row)

    lines.append(format_markdown_table(headers, rows))
    return "\n".join(lines)


# ── Cross-model OE comparison ─────────────────────────────────────────────


def build_evidence_span_index(parsed_json: dict) -> dict[str, str]:
    """Build event_id → excerpt lookup from evidence_spans."""
    index: dict[str, str] = {}
    for span in parsed_json.get("evidence_spans", []):
        excerpt = span.get("excerpt", "")
        for eid in span.get("event_ids", []):
            if eid not in index:
                index[eid] = excerpt
    return index


def extract_opportunity_details_with_excerpts(
    parsed_json: dict,
) -> dict[str, list[dict[str, Any]]]:
    """Like extract_opportunity_details but also resolves transcript excerpts."""
    excerpt_index = build_evidence_span_index(parsed_json)
    details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for oe in parsed_json.get("opportunity_events", []):
        pid = oe.get("pattern_id")
        if not pid or oe.get("count_decision") != "counted":
            continue
        turn_start = oe.get("turn_start_id")
        turn_end = oe.get("turn_end_id")
        if turn_start is not None and turn_end is not None:
            turn_range = f"T{turn_start}" if turn_start == turn_end else f"T{turn_start}-{turn_end}"
        elif turn_start is not None:
            turn_range = f"T{turn_start}"
        else:
            turn_range = "?"
        event_id = oe.get("event_id", "?")
        details[pid].append({
            "event_id": event_id,
            "pattern_id": pid,
            "success": oe.get("success"),
            "reason_code": oe.get("reason_code", ""),
            "notes": oe.get("notes", ""),
            "excerpt": excerpt_index.get(event_id, ""),
            "turn_range": turn_range,
            "turn_start_id": turn_start,
            "turn_end_id": turn_end,
        })
    return dict(details)


def align_opportunities_cross_model(
    a_run_details: list[dict[str, list[dict]]],
    b_run_details: list[dict[str, list[dict]]],
    pattern_id: str,
) -> list[dict[str, Any]]:
    """Align OEs across two models by turn_start_id for a given pattern.

    a_run_details / b_run_details: list of per-run dicts from
        extract_opportunity_details_with_excerpts(), one per run.

    Returns list of OpportunitySlot dicts sorted by turn_start_id.
    """
    # Collect all unique turn_start_ids
    all_starts: set[int] = set()
    for rd in a_run_details:
        for oe in rd.get(pattern_id, []):
            if oe.get("turn_start_id") is not None:
                all_starts.add(oe["turn_start_id"])
    for rd in b_run_details:
        for oe in rd.get(pattern_id, []):
            if oe.get("turn_start_id") is not None:
                all_starts.add(oe["turn_start_id"])

    if not all_starts:
        return []

    a_total = len(a_run_details)
    b_total = len(b_run_details)

    slots: list[dict[str, Any]] = []
    for ts in sorted(all_starts):
        slot: dict[str, Any] = {
            "turn_start_id": ts,
            "pattern_id": pattern_id,
            "a_total_runs": a_total,
            "b_total_runs": b_total,
            "a_scores": [],
            "b_scores": [],
            "a_reason_codes": [],
            "b_reason_codes": [],
            "a_notes": [],
            "b_notes": [],
            "a_turn_ends": [],
            "b_turn_ends": [],
            "a_excerpts": [],
            "b_excerpts": [],
        }

        # Collect from model A runs
        for rd in a_run_details:
            matched = False
            for oe in rd.get(pattern_id, []):
                if oe.get("turn_start_id") == ts and not matched:
                    slot["a_scores"].append(oe["success"])
                    slot["a_reason_codes"].append(oe.get("reason_code", ""))
                    slot["a_notes"].append(oe.get("notes", ""))
                    slot["a_turn_ends"].append(oe.get("turn_end_id"))
                    slot["a_excerpts"].append(oe.get("excerpt", ""))
                    matched = True

        # Collect from model B runs
        for rd in b_run_details:
            matched = False
            for oe in rd.get(pattern_id, []):
                if oe.get("turn_start_id") == ts and not matched:
                    slot["b_scores"].append(oe["success"])
                    slot["b_reason_codes"].append(oe.get("reason_code", ""))
                    slot["b_notes"].append(oe.get("notes", ""))
                    slot["b_turn_ends"].append(oe.get("turn_end_id"))
                    slot["b_excerpts"].append(oe.get("excerpt", ""))
                    matched = True

        slot["a_count"] = len(slot["a_scores"])
        slot["b_count"] = len(slot["b_scores"])
        slot["a_rate"] = slot["a_count"] / a_total if a_total else 0
        slot["b_rate"] = slot["b_count"] / b_total if b_total else 0

        slots.append(slot)

    return slots


def classify_opportunity_slots(
    slots: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Classify slots into consensus, a_only, b_only, disputed."""
    result: dict[str, list[dict[str, Any]]] = {
        "consensus": [], "a_only": [], "b_only": [], "disputed": [],
    }
    for slot in slots:
        a_rate = slot["a_rate"]
        b_rate = slot["b_rate"]
        if a_rate > 0.50 and b_rate > 0.50:
            result["consensus"].append(slot)
        elif a_rate > 0.50 and b_rate < 0.25:
            result["a_only"].append(slot)
        elif b_rate > 0.50 and a_rate < 0.25:
            result["b_only"].append(slot)
        else:
            result["disputed"].append(slot)
    return result


def compute_consensus_comparison(slot: dict[str, Any]) -> dict[str, Any]:
    """Compute score comparison for a consensus slot."""
    a_scores = [s for s in slot["a_scores"] if s is not None]
    b_scores = [s for s in slot["b_scores"] if s is not None]

    a_mean = statistics.mean(a_scores) if a_scores else None
    b_mean = statistics.mean(b_scores) if b_scores else None
    delta = round(a_mean - b_mean, 4) if a_mean is not None and b_mean is not None else None

    # Reason code overlap (Jaccard)
    a_codes = set(slot["a_reason_codes"])
    b_codes = set(slot["b_reason_codes"])
    a_codes.discard("")
    b_codes.discard("")
    union = a_codes | b_codes
    overlap = len(a_codes & b_codes) / len(union) if union else 1.0

    # Pick representative excerpt
    excerpt = ""
    if slot["a_excerpts"]:
        excerpt = slot["a_excerpts"][0]
    elif slot["b_excerpts"]:
        excerpt = slot["b_excerpts"][0]

    # Dominant reason codes
    def _dominant(codes: list[str]) -> str:
        filtered = [c for c in codes if c]
        if not filtered:
            return ""
        from collections import Counter
        return Counter(filtered).most_common(1)[0][0]

    return {
        **slot,
        "a_mean_score": round(a_mean, 4) if a_mean is not None else None,
        "b_mean_score": round(b_mean, 4) if b_mean is not None else None,
        "score_delta": delta,
        "reason_code_overlap": round(overlap, 4),
        "a_dominant_reason": _dominant(slot["a_reason_codes"]),
        "b_dominant_reason": _dominant(slot["b_reason_codes"]),
        "transcript_excerpt": excerpt,
    }


def compute_cross_pattern_summary(
    all_results: dict[str, dict[str, dict[str, list[dict]]]],
    pattern_order: list[str],
) -> dict[str, dict[str, Any]]:
    """Aggregate cross-model results across all meetings per pattern.

    all_results: meeting_id → pattern_id → {"consensus": [...], "a_only": [...], ...}
    Returns: pattern_id → summary stats.
    """
    summary: dict[str, dict[str, Any]] = {}
    for pid in pattern_order:
        total = 0
        consensus = 0
        a_only = 0
        b_only = 0
        disputed = 0
        abs_deltas: list[float] = []
        overlaps: list[float] = []

        for mid, patterns in all_results.items():
            classified = patterns.get(pid, {})
            consensus_slots = classified.get("consensus", [])
            a_only_slots = classified.get("a_only", [])
            b_only_slots = classified.get("b_only", [])
            disputed_slots = classified.get("disputed", [])

            n = len(consensus_slots) + len(a_only_slots) + len(b_only_slots) + len(disputed_slots)
            total += n
            consensus += len(consensus_slots)
            a_only += len(a_only_slots)
            b_only += len(b_only_slots)
            disputed += len(disputed_slots)

            for s in consensus_slots:
                comp = compute_consensus_comparison(s)
                if comp["score_delta"] is not None:
                    abs_deltas.append(abs(comp["score_delta"]))
                overlaps.append(comp["reason_code_overlap"])

        summary[pid] = {
            "total_slots": total,
            "consensus": consensus,
            "consensus_pct": round(100 * consensus / total, 1) if total else 0,
            "a_only": a_only,
            "b_only": b_only,
            "disputed": disputed,
            "mean_abs_score_delta": round(statistics.mean(abs_deltas), 4) if abs_deltas else None,
            "max_abs_score_delta": round(max(abs_deltas), 4) if abs_deltas else None,
            "mean_reason_overlap": round(statistics.mean(overlaps), 4) if overlaps else None,
        }
    return summary


# ── Cross-model report formatting ─────────────────────────────────────────


def format_cross_model_report(
    model_a_label: str,
    model_b_label: str,
    common_meetings: list[str],
    all_results: dict[str, dict[str, dict[str, list[dict]]]],
    cross_pattern_summary: dict[str, dict[str, Any]],
    pattern_order: list[str],
    detail: bool = False,
) -> str:
    """Render the full cross-model comparison markdown report."""
    lines: list[str] = []

    # Header
    lines.append("# Cross-Model OE Comparison Report\n")
    lines.append(f"**Model A**: {model_a_label}  ")
    lines.append(f"**Model B**: {model_b_label}  ")
    lines.append(f"**Meetings**: {len(common_meetings)}\n")

    # Section 1: Cross-pattern agreement summary
    lines.append("## Cross-Pattern Agreement Summary\n")
    lines.append(f"| Pattern | Slots | Consensus | A-only | B-only | Disputed | Consens% | Mean|Δ| | ReasonOverlap |")
    lines.append(f"| ------- | ----- | --------- | ------ | ------ | -------- | -------- | ------- | ------------- |")
    for pid in pattern_order:
        s = cross_pattern_summary.get(pid, {})
        if s.get("total_slots", 0) == 0:
            continue
        lines.append(
            f"| {pid} | {s['total_slots']} | {s['consensus']} | {s['a_only']} "
            f"| {s['b_only']} | {s['disputed']} | {s['consensus_pct']:.1f}% "
            f"| {_fmt(s['mean_abs_score_delta'])} | {_fmt(s['mean_reason_overlap'])} |"
        )
    lines.append("")

    # Section 2: Per-meeting × per-pattern summary
    lines.append("## Per-Meeting Summary\n")
    for mid in common_meetings:
        lines.append(f"### {mid}\n")
        lines.append("| Pattern | Consensus | A-only | B-only | Disputed | Mean Δ (A−B) |")
        lines.append("| ------- | --------- | ------ | ------ | -------- | ------------ |")
        for pid in pattern_order:
            classified = all_results.get(mid, {}).get(pid, {})
            cons = classified.get("consensus", [])
            ao = classified.get("a_only", [])
            bo = classified.get("b_only", [])
            disp = classified.get("disputed", [])
            if not cons and not ao and not bo and not disp:
                continue
            deltas = []
            for s in cons:
                comp = compute_consensus_comparison(s)
                if comp["score_delta"] is not None:
                    deltas.append(comp["score_delta"])
            mean_d = round(statistics.mean(deltas), 4) if deltas else None
            sign = "+" if mean_d and mean_d > 0 else ""
            lines.append(
                f"| {pid} | {len(cons)} | {len(ao)} | {len(bo)} | {len(disp)} "
                f"| {sign}{_fmt(mean_d)} |"
            )
        lines.append("")

    # Section 3: Consensus OE detail tables
    lines.append("## Consensus OE Detail\n")
    for mid in common_meetings:
        for pid in pattern_order:
            classified = all_results.get(mid, {}).get(pid, {})
            cons = classified.get("consensus", [])
            if not cons:
                continue
            lines.append(f"### {mid} — {pid}\n")
            lines.append("| Turn | Transcript Text | A Mean | B Mean | Δ | A Reason | B Reason |")
            lines.append("| ---- | --------------- | ------ | ------ | - | -------- | -------- |")
            for slot in cons:
                comp = compute_consensus_comparison(slot)
                ts = slot["turn_start_id"]
                a_ends = slot["a_turn_ends"]
                b_ends = slot["b_turn_ends"]
                max_end = max((a_ends or [ts]) + (b_ends or [ts]))
                turn_label = f"T{ts}" if max_end == ts else f"T{ts}-{max_end}"
                excerpt = comp["transcript_excerpt"][:120].replace("|", "\\|").replace("\n", " ")
                if len(comp["transcript_excerpt"]) > 120:
                    excerpt += "..."
                sign = "+" if comp["score_delta"] and comp["score_delta"] > 0 else ""
                lines.append(
                    f"| {turn_label} | {excerpt} "
                    f"| {_fmt(comp['a_mean_score'])} | {_fmt(comp['b_mean_score'])} "
                    f"| {sign}{_fmt(comp['score_delta'])} "
                    f"| {comp['a_dominant_reason']} | {comp['b_dominant_reason']} |"
                )
                # Show notes for large deltas
                if comp["score_delta"] is not None and abs(comp["score_delta"]) > 0.25:
                    a_note = (slot["a_notes"][0] if slot["a_notes"] else "").replace("\n", " ")[:200]
                    b_note = (slot["b_notes"][0] if slot["b_notes"] else "").replace("\n", " ")[:200]
                    lines.append(f"| | **A notes**: {a_note} | | | | | |")
                    lines.append(f"| | **B notes**: {b_note} | | | | | |")
            lines.append("")

    # Section 4: Model-specific OE lists
    lines.append("## Model-Specific Opportunities\n")
    for mid in common_meetings:
        has_exclusive = False
        for pid in pattern_order:
            classified = all_results.get(mid, {}).get(pid, {})
            ao = classified.get("a_only", [])
            bo = classified.get("b_only", [])
            if ao or bo:
                has_exclusive = True
                break
        if not has_exclusive:
            continue

        lines.append(f"### {mid}\n")
        for pid in pattern_order:
            classified = all_results.get(mid, {}).get(pid, {})
            ao = classified.get("a_only", [])
            bo = classified.get("b_only", [])
            if not ao and not bo:
                continue
            lines.append(f"#### {pid}\n")
            if ao:
                lines.append(f"**Model A only** ({model_a_label}):\n")
                for slot in ao:
                    ts = slot["turn_start_id"]
                    a_mean = statistics.mean(slot["a_scores"]) if slot["a_scores"] else None
                    excerpt = (slot["a_excerpts"][0] if slot["a_excerpts"] else "")[:150].replace("\n", " ")
                    note = (slot["a_notes"][0] if slot["a_notes"] else "")[:200].replace("\n", " ")
                    from collections import Counter
                    rc = Counter(c for c in slot["a_reason_codes"] if c).most_common(1)
                    rc_str = rc[0][0] if rc else ""
                    lines.append(
                        f"- **T{ts}** (rate={slot['a_rate']:.0%}, score={_fmt(a_mean)}): "
                        f"`{rc_str}`"
                    )
                    if excerpt:
                        lines.append(f"  > {excerpt}...")
                    if note:
                        lines.append(f"  > *{note}*")
                lines.append("")
            if bo:
                lines.append(f"**Model B only** ({model_b_label}):\n")
                for slot in bo:
                    ts = slot["turn_start_id"]
                    b_mean = statistics.mean(slot["b_scores"]) if slot["b_scores"] else None
                    excerpt = (slot["b_excerpts"][0] if slot["b_excerpts"] else "")[:150].replace("\n", " ")
                    note = (slot["b_notes"][0] if slot["b_notes"] else "")[:200].replace("\n", " ")
                    from collections import Counter
                    rc = Counter(c for c in slot["b_reason_codes"] if c).most_common(1)
                    rc_str = rc[0][0] if rc else ""
                    lines.append(
                        f"- **T{ts}** (rate={slot['b_rate']:.0%}, score={_fmt(b_mean)}): "
                        f"`{rc_str}`"
                    )
                    if excerpt:
                        lines.append(f"  > {excerpt}...")
                    if note:
                        lines.append(f"  > *{note}*")
                lines.append("")

    # Section 5: Disputed OEs
    has_disputed = any(
        classified.get("disputed")
        for mid_patterns in all_results.values()
        for classified in mid_patterns.values()
    )
    if has_disputed:
        lines.append("## Disputed Opportunities\n")
        for mid in common_meetings:
            for pid in pattern_order:
                classified = all_results.get(mid, {}).get(pid, {})
                disp = classified.get("disputed", [])
                if not disp:
                    continue
                lines.append(f"### {mid} — {pid}\n")
                for slot in disp:
                    ts = slot["turn_start_id"]
                    a_mean = statistics.mean(slot["a_scores"]) if slot["a_scores"] else None
                    b_mean = statistics.mean(slot["b_scores"]) if slot["b_scores"] else None
                    excerpt = ""
                    if slot["a_excerpts"]:
                        excerpt = slot["a_excerpts"][0][:150].replace("\n", " ")
                    elif slot["b_excerpts"]:
                        excerpt = slot["b_excerpts"][0][:150].replace("\n", " ")
                    lines.append(
                        f"- **T{ts}** A rate={slot['a_rate']:.0%} score={_fmt(a_mean)} | "
                        f"B rate={slot['b_rate']:.0%} score={_fmt(b_mean)}"
                    )
                    if excerpt:
                        lines.append(f"  > {excerpt}...")
                lines.append("")

    return "\n".join(lines)


def _fmt(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.4f}"


def save_report(content: str, path: Path) -> None:
    """Save a report string to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Report saved to {path}")


def save_json(data: Any, path: Path) -> None:
    """Save data as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
