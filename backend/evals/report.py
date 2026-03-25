"""
report.py — Shared reporting utilities for eval scripts.
"""
from __future__ import annotations

import json
import statistics
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
    headers2 = ["Pattern", "Cross IQR", "Cross StdDev", "Mean Intra IQR", "Signal/Noise"]
    rows2 = []
    for pid, cs in cross_transcript.items():
        rows2.append([
            pid,
            _fmt(cs.get("cross_iqr")),
            _fmt(cs.get("cross_stdev")),
            _fmt(cs.get("mean_intra_iqr")),
            _fmt(cs.get("signal_to_noise")),
        ])
    lines.append(format_markdown_table(headers2, rows2))

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
