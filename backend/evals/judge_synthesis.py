"""
judge_synthesis.py — Aggregate and synthesize judge_eval outputs.

Usage:
  # Synthesize most recent judge batch in results dir
  python -m backend.evals.judge_synthesis --results-dir backend/evals/results

  # Compare against a baseline phase
  python -m backend.evals.judge_synthesis \\
    --results-dir backend/evals/results \\
    --baseline-dir backend/evals/results/Phase_A

  # Synthesize ALL judge files (skip timestamp filtering)
  python -m backend.evals.judge_synthesis --results-dir backend/evals/results --all-judges
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.evals.report import save_json, save_report

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

PATTERN_ORDER = [
    "purposeful_framing", "focus_management",
    "disagreement_navigation", "trust_and_credibility", "resolution_and_alignment",
    "assignment_clarity", "question_quality", "communication_clarity", "feedback_quality",
]

# ── Judge file discovery ─────────────────────────────────────────────────────

_JUDGE_FILENAME_RE = re.compile(
    r"^judge_(?:stage2_merged_)?run_(\d{3})_(\d{8}T\d{6})_(?:\d{8}T\d{6}_)?(\d{8}T\d{6})\.json$"
)


def discover_judge_files(results_dir: Path, latest_batch_only: bool = True) -> dict[str, list[Path]]:
    """Find judge JSON files grouped by meeting.

    Returns {meeting_id: [judge_file_paths]}.
    When latest_batch_only=True, only returns judges from the most recent
    run-timestamp batch per meeting.
    """
    meetings: dict[str, list[Path]] = {}

    for subdir in sorted(results_dir.iterdir()):
        if not subdir.is_dir():
            continue
        meeting_id = subdir.name

        judge_files: list[tuple[str, Path]] = []  # (run_timestamp, path)
        for f in sorted(subdir.glob("judge_*.json")):
            m = _JUDGE_FILENAME_RE.match(f.name)
            if m:
                judge_files.append((m.group(2), f))

        if not judge_files:
            continue

        if latest_batch_only:
            # Group by run_timestamp, take the most recent batch
            latest_ts = max(ts for ts, _ in judge_files)
            selected = [p for ts, p in judge_files if ts == latest_ts]
        else:
            selected = [p for _, p in judge_files]

        if selected:
            meetings[meeting_id] = selected

    return meetings


def load_judge_data(files: list[Path]) -> list[dict]:
    """Load and return parsed judge JSON objects."""
    results = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_file"] = f.name
        data["_meeting"] = f.parent.name
        results.append(data)
    return results


# ── Synthesis functions ──────────────────────────────────────────────────────

def synthesize_ratings(judge_data: list[dict]) -> dict[str, Any]:
    """Compute aggregate and per-pattern rating distributions."""
    all_ratings: dict[str, list[str]] = defaultdict(list)
    per_meeting: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for d in judge_data:
        meeting = d["_meeting"]
        items = d.get("coaching_insight_quality", {}).get("items", [])
        for item in items:
            pid = item.get("pattern_id", "")
            rating = item.get("rating", "")
            if pid and rating:
                all_ratings[pid].append(rating)
                per_meeting[meeting][pid].append(rating)

    def _dist(ratings: list[str]) -> dict[str, Any]:
        n = len(ratings)
        if n == 0:
            return {"n": 0, "insightful": 0, "adequate": 0, "pedantic": 0, "wrong": 0}
        c = Counter(ratings)
        return {
            "n": n,
            "insightful": c.get("insightful", 0),
            "adequate": c.get("adequate", 0),
            "pedantic": c.get("pedantic", 0),
            "wrong": c.get("wrong", 0),
            "insightful_pct": round(100 * c.get("insightful", 0) / n, 1),
            "adequate_pct": round(100 * c.get("adequate", 0) / n, 1),
            "pedantic_pct": round(100 * c.get("pedantic", 0) / n, 1),
            "wrong_pct": round(100 * c.get("wrong", 0) / n, 1),
        }

    # Aggregate across all
    all_flat = [r for ratings in all_ratings.values() for r in ratings]
    aggregate = _dist(all_flat)

    # Per pattern
    per_pattern = {}
    for pid in PATTERN_ORDER:
        if pid in all_ratings:
            per_pattern[pid] = _dist(all_ratings[pid])

    # Per meeting (all patterns)
    per_meeting_agg = {}
    for meeting in sorted(per_meeting.keys()):
        flat = [r for ratings in per_meeting[meeting].values() for r in ratings]
        per_meeting_agg[meeting] = _dist(flat)

    # Heat maps: pattern × meeting
    pedantic_heat = {}
    insightful_heat = {}
    for pid in PATTERN_ORDER:
        ped_row = {}
        ins_row = {}
        for meeting in sorted(per_meeting.keys()):
            ratings = per_meeting[meeting].get(pid, [])
            n = len(ratings)
            if n > 0:
                ped_row[meeting] = f"{sum(1 for r in ratings if r == 'pedantic')}/{n}"
                ins_row[meeting] = f"{sum(1 for r in ratings if r == 'insightful')}/{n}"
            else:
                ped_row[meeting] = "-"
                ins_row[meeting] = "-"
        pedantic_heat[pid] = ped_row
        insightful_heat[pid] = ins_row

    return {
        "aggregate": aggregate,
        "per_pattern": per_pattern,
        "per_meeting": per_meeting_agg,
        "pedantic_heatmap": pedantic_heat,
        "insightful_heatmap": insightful_heat,
    }


def synthesize_evidence_quality(judge_data: list[dict]) -> dict[str, Any]:
    """Aggregate evidence_quality and success_evidence_quality."""
    evidence: dict[str, Counter] = defaultdict(Counter)
    success_evidence: dict[str, dict[str, int]] = defaultdict(lambda: {"demonstrates": 0, "doesnt_demonstrate": 0, "total": 0})

    for d in judge_data:
        for item in d.get("evidence_quality", {}).get("items", []):
            pid = item.get("pattern_id", "")
            rating = item.get("rating", "")
            if pid and rating:
                evidence[pid][rating] += 1

        for item in d.get("success_evidence_quality", {}).get("items", []):
            pid = item.get("pattern_id", "")
            demonstrates = item.get("genuinely_demonstrates_pattern", True)
            success_evidence[pid]["total"] += 1
            if demonstrates:
                success_evidence[pid]["demonstrates"] += 1
            else:
                success_evidence[pid]["doesnt_demonstrate"] += 1

    return {
        "evidence_quality": {pid: dict(evidence[pid]) for pid in sorted(evidence)},
        "success_evidence_quality": {pid: dict(success_evidence[pid]) for pid in sorted(success_evidence)},
    }


def synthesize_rewrite_quality(judge_data: list[dict]) -> dict[str, dict[str, int]]:
    """Aggregate rewrite_quality ratings per pattern."""
    rewrites: dict[str, Counter] = defaultdict(Counter)
    for d in judge_data:
        for item in d.get("rewrite_quality", {}).get("items", []):
            pid = item.get("pattern_id", "")
            rating = item.get("rating", "")
            if pid and rating:
                rewrites[pid][rating] += 1
    return {pid: dict(rewrites[pid]) for pid in sorted(rewrites)}


def synthesize_gut_check(judge_data: list[dict]) -> dict[str, Any]:
    """Aggregate executive_coach_gut_check fields."""
    coaching_values = Counter()
    aii_texts: dict[str, list[str]] = defaultdict(list)
    total = 0

    for d in judge_data:
        gut = d.get("executive_coach_gut_check", {})
        total += 1
        coaching_values[gut.get("overall_coaching_value", "unknown")] += 1

        aii = gut.get("anything_important_ignored", "")
        if aii and aii.strip() and aii.strip().lower() not in ("null", "no", "none", "no.", "nothing significant."):
            aii_texts[d["_meeting"]].append(aii)

    # Keyword analysis on anything_important_ignored
    all_aii = [text for texts in aii_texts.values() for text in texts]
    keyword_counts = {}
    for keyword in ["trust", "credib", "decision", "pre-meeting", "prework", "courage", "avoidance"]:
        keyword_counts[keyword] = sum(1 for t in all_aii if keyword.lower() in t.lower())

    return {
        "overall_coaching_value": dict(coaching_values),
        "total_runs": total,
        "anything_important_ignored": {
            "runs_with_content": len(all_aii),
            "total_runs": total,
            "keyword_counts": keyword_counts,
            "by_meeting": {m: texts for m, texts in sorted(aii_texts.items())},
        },
    }


def synthesize_internal_consistency(judge_data: list[dict]) -> dict[str, Any]:
    """Aggregate internal_consistency flags."""
    total = 0
    sc_aligned = 0
    exp_coherent = 0
    exec_reflects = 0

    for d in judge_data:
        ic = d.get("internal_consistency", {})
        total += 1
        if ic.get("score_coaching_aligned", True):
            sc_aligned += 1
        if ic.get("experiment_detection_coherent", True):
            exp_coherent += 1
        if ic.get("executive_summary_reflects_findings", True):
            exec_reflects += 1

    return {
        "total": total,
        "score_coaching_aligned": sc_aligned,
        "experiment_detection_coherent": exp_coherent,
        "executive_summary_reflects_findings": exec_reflects,
    }


def synthesize_pattern_alignment(judge_data: list[dict]) -> dict[str, list[dict]]:
    """Aggregate coaching_pattern_alignment misfits."""
    misfits: dict[str, list[dict]] = defaultdict(list)

    for d in judge_data:
        cpa = d.get("coaching_pattern_alignment", {})
        for item in cpa.get("items", []):
            pid = item.get("pattern_id", "")
            fits = item.get("fits_pattern", True)
            better = item.get("better_pattern", "")
            if not fits or better:
                misfits[pid].append({
                    "meeting": d["_meeting"],
                    "fits": fits,
                    "better_pattern": better,
                })

    return dict(misfits)


def synthesize_executive_summary_quality(judge_data: list[dict]) -> dict[str, Any]:
    """Aggregate executive_summary_quality ratings."""
    ratings: Counter = Counter()
    booleans: dict[str, int] = {"captures_meeting_essence": 0, "identifies_key_development_edge": 0, "specific_to_this_leader": 0}
    per_meeting: dict[str, list[str]] = defaultdict(list)
    total = 0

    for d in judge_data:
        esq = d.get("executive_summary_quality", {})
        if not esq:
            continue
        total += 1
        rating = esq.get("rating", "unknown")
        ratings[rating] += 1
        per_meeting[d["_meeting"]].append(rating)
        for key in booleans:
            if esq.get(key, False):
                booleans[key] += 1

    return {
        "total": total,
        "ratings": dict(ratings),
        "booleans": {k: {"true": v, "total": total, "pct": round(100 * v / max(total, 1), 1)} for k, v in booleans.items()},
        "per_meeting": {m: dict(Counter(rs)) for m, rs in sorted(per_meeting.items())},
    }


def synthesize_coaching_themes_quality(judge_data: list[dict]) -> dict[str, Any]:
    """Aggregate coaching_themes_quality ratings."""
    item_ratings: Counter = Counter()
    transcends_count = 0
    behavioral_count = 0
    total_items = 0
    tvp: Counter = Counter()  # themes_vs_patterns
    per_meeting_tvp: dict[str, list[str]] = defaultdict(list)
    total_runs = 0

    for d in judge_data:
        ctq = d.get("coaching_themes_quality", {})
        if not ctq:
            continue
        total_runs += 1

        tvp_val = ctq.get("themes_vs_patterns", "unknown")
        tvp[tvp_val] += 1
        per_meeting_tvp[d["_meeting"]].append(tvp_val)

        for item in ctq.get("items", []):
            total_items += 1
            rating = item.get("rating", "unknown")
            item_ratings[rating] += 1
            if item.get("transcends_taxonomy", False):
                transcends_count += 1
            if item.get("names_behavioral_habit", False):
                behavioral_count += 1

    return {
        "total_runs": total_runs,
        "total_theme_items": total_items,
        "item_ratings": dict(item_ratings),
        "transcends_taxonomy_count": transcends_count,
        "names_behavioral_habit_count": behavioral_count,
        "themes_vs_patterns": dict(tvp),
        "per_meeting_themes_vs_patterns": {m: dict(Counter(vs)) for m, vs in sorted(per_meeting_tvp.items())},
    }


def synthesize_run_profiles(judge_data: list[dict]) -> dict[str, list[dict]]:
    """Per-run rating profiles: how many patterns in each bucket per run."""
    profiles: dict[str, list[dict]] = defaultdict(list)

    for d in judge_data:
        items = d.get("coaching_insight_quality", {}).get("items", [])
        ins = sum(1 for i in items if i.get("rating") == "insightful")
        ade = sum(1 for i in items if i.get("rating") == "adequate")
        ped = sum(1 for i in items if i.get("rating") == "pedantic")
        wrg = sum(1 for i in items if i.get("rating") == "wrong")
        profiles[d["_meeting"]].append({
            "file": d["_file"],
            "insightful": ins,
            "adequate": ade,
            "pedantic": ped,
            "wrong": wrg,
            "total": len(items),
        })

    return dict(profiles)


# ── Phase comparison ─────────────────────────────────────────────────────────

def compare_phases(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare two synthesis results."""
    comparison = {}

    # Aggregate deltas
    ca = current["ratings"]["aggregate"]
    ba = baseline["ratings"]["aggregate"]
    comparison["aggregate_delta"] = {
        "insightful_pct": round(ca.get("insightful_pct", 0) - ba.get("insightful_pct", 0), 1),
        "pedantic_pct": round(ca.get("pedantic_pct", 0) - ba.get("pedantic_pct", 0), 1),
        "wrong_pct": round(ca.get("wrong_pct", 0) - ba.get("wrong_pct", 0), 1),
        "current_n": ca.get("n", 0),
        "baseline_n": ba.get("n", 0),
    }

    # Per-pattern deltas (shared patterns only)
    pattern_deltas = {}
    for pid in PATTERN_ORDER:
        cp = current["ratings"]["per_pattern"].get(pid, {})
        bp = baseline["ratings"]["per_pattern"].get(pid, {})
        if cp and bp:
            pattern_deltas[pid] = {
                "insightful_pct_delta": round(cp.get("insightful_pct", 0) - bp.get("insightful_pct", 0), 1),
                "pedantic_pct_delta": round(cp.get("pedantic_pct", 0) - bp.get("pedantic_pct", 0), 1),
                "current_n": cp.get("n", 0),
                "baseline_n": bp.get("n", 0),
            }
        elif cp and not bp:
            pattern_deltas[pid] = {"new_pattern": True, **cp}
    comparison["per_pattern_delta"] = pattern_deltas

    # anything_important_ignored keyword comparison
    c_aii = current["gut_check"]["anything_important_ignored"]
    b_aii = baseline["gut_check"]["anything_important_ignored"]
    comparison["aii_keyword_delta"] = {
        k: {
            "current": c_aii["keyword_counts"].get(k, 0),
            "baseline": b_aii["keyword_counts"].get(k, 0),
            "current_total": c_aii["total_runs"],
            "baseline_total": b_aii["total_runs"],
        }
        for k in set(list(c_aii["keyword_counts"]) + list(b_aii["keyword_counts"]))
    }

    return comparison


# ── Markdown formatting ──────────────────────────────────────────────────────

def format_report(synthesis: dict[str, Any], comparison: dict[str, Any] | None = None) -> str:
    """Format synthesis results as markdown."""
    lines: list[str] = []
    lines.append("# Judge Synthesis Report")
    lines.append(f"\nGenerated: {synthesis['timestamp']}")
    lines.append(f"Meetings: {len(synthesis['meetings'])}")
    lines.append(f"Judge files: {synthesis['total_judge_files']}")

    # Aggregate
    agg = synthesis["ratings"]["aggregate"]
    lines.append("\n## Aggregate Judge Metrics\n")
    lines.append(f"| Metric | Count | % |")
    lines.append(f"|--------|------:|---:|")
    for r in ["insightful", "adequate", "pedantic", "wrong"]:
        lines.append(f"| {r.capitalize()} | {agg[r]} | {agg[f'{r}_pct']}% |")
    lines.append(f"| **Total** | **{agg['n']}** | |")

    # Per-pattern
    lines.append("\n## Per-Pattern Breakdown\n")
    lines.append(f"| Pattern | N | Ins% | Ade% | Ped% | Wrg% |")
    lines.append(f"|---------|---:|-----:|-----:|-----:|-----:|")
    for pid in PATTERN_ORDER:
        pp = synthesis["ratings"]["per_pattern"].get(pid)
        if pp:
            lines.append(f"| {pid} | {pp['n']} | {pp['insightful_pct']}% | {pp['adequate_pct']}% | {pp['pedantic_pct']}% | {pp['wrong_pct']}% |")

    # Per-meeting
    lines.append("\n## Per-Meeting Breakdown\n")
    lines.append(f"| Meeting | N | Ins% | Ped% |")
    lines.append(f"|---------|---:|-----:|-----:|")
    for meeting, pm in sorted(synthesis["ratings"]["per_meeting"].items()):
        lines.append(f"| {meeting} | {pm['n']} | {pm['insightful_pct']}% | {pm['pedantic_pct']}% |")

    # Pedantic heat map
    meetings = sorted(synthesis["ratings"]["per_meeting"].keys())
    short_meetings = [m.split("_")[0] for m in meetings]

    lines.append("\n## Pedantic Heat Map (pattern x meeting)\n")
    lines.append(f"| Pattern | {' | '.join(short_meetings)} |")
    lines.append(f"|---------|{'|'.join(['-----:'] * len(meetings))}|")
    for pid in PATTERN_ORDER:
        row = synthesis["ratings"]["pedantic_heatmap"].get(pid, {})
        cells = [row.get(m, "-") for m in meetings]
        lines.append(f"| {pid} | {' | '.join(cells)} |")

    # Insightful heat map
    lines.append("\n## Insightful Heat Map (pattern x meeting)\n")
    lines.append(f"| Pattern | {' | '.join(short_meetings)} |")
    lines.append(f"|---------|{'|'.join(['-----:'] * len(meetings))}|")
    for pid in PATTERN_ORDER:
        row = synthesis["ratings"]["insightful_heatmap"].get(pid, {})
        cells = [row.get(m, "-") for m in meetings]
        lines.append(f"| {pid} | {' | '.join(cells)} |")

    # Evidence quality
    lines.append("\n## Evidence Quality\n")
    eq = synthesis["evidence_quality"]["evidence_quality"]
    lines.append(f"| Pattern | Strong | Weak | Misaligned |")
    lines.append(f"|---------|-------:|-----:|-----------:|")
    for pid in PATTERN_ORDER:
        e = eq.get(pid, {})
        lines.append(f"| {pid} | {e.get('strong_evidence', 0)} | {e.get('weak_evidence', 0)} | {e.get('misaligned', 0)} |")

    # Success evidence quality
    lines.append("\n## Success Evidence Quality\n")
    seq = synthesis["evidence_quality"]["success_evidence_quality"]
    lines.append(f"| Pattern | Demonstrates | Doesn't | Total |")
    lines.append(f"|---------|------------:|--------:|------:|")
    for pid in PATTERN_ORDER:
        s = seq.get(pid, {})
        lines.append(f"| {pid} | {s.get('demonstrates', 0)} | {s.get('doesnt_demonstrate', 0)} | {s.get('total', 0)} |")

    # Rewrite quality
    lines.append("\n## Rewrite Quality\n")
    rq = synthesis["rewrite_quality"]
    lines.append(f"| Pattern | Strong | Generic | Misaligned | Worse |")
    lines.append(f"|---------|-------:|--------:|-----------:|------:|")
    for pid in PATTERN_ORDER:
        r = rq.get(pid, {})
        lines.append(f"| {pid} | {r.get('strong_model', 0)} | {r.get('generic', 0)} | {r.get('misaligned', 0)} | {r.get('worse', 0)} |")

    # Gut check
    gc = synthesis["gut_check"]
    lines.append("\n## Overall Coaching Value\n")
    for v, c in sorted(gc["overall_coaching_value"].items(), key=lambda x: -x[1]):
        lines.append(f"- {v}: {c}/{gc['total_runs']}")

    # Internal consistency
    ic = synthesis["internal_consistency"]
    lines.append("\n## Internal Consistency\n")
    lines.append(f"- score_coaching_aligned: {ic['score_coaching_aligned']}/{ic['total']}")
    lines.append(f"- experiment_detection_coherent: {ic['experiment_detection_coherent']}/{ic['total']}")
    lines.append(f"- executive_summary_reflects_findings: {ic['executive_summary_reflects_findings']}/{ic['total']}")

    # Executive summary quality
    esq = synthesis.get("executive_summary_quality", {})
    if esq.get("total", 0) > 0:
        lines.append("\n## Executive Summary Quality\n")
        lines.append(f"Total rated: {esq['total']}")
        lines.append(f"\n| Rating | Count | % |")
        lines.append(f"|--------|------:|---:|")
        for r in ["insightful", "adequate", "generic", "misleading"]:
            count = esq["ratings"].get(r, 0)
            pct = round(100 * count / max(esq["total"], 1), 1)
            lines.append(f"| {r.capitalize()} | {count} | {pct}% |")

        lines.append(f"\n| Boolean check | True | % |")
        lines.append(f"|---------------|-----:|---:|")
        for key, vals in esq.get("booleans", {}).items():
            lines.append(f"| {key} | {vals['true']}/{vals['total']} | {vals['pct']}% |")

    # Coaching themes quality
    ctq = synthesis.get("coaching_themes_quality", {})
    if ctq.get("total_runs", 0) > 0:
        lines.append("\n## Coaching Themes Quality\n")
        lines.append(f"Total runs: {ctq['total_runs']}, Total theme items: {ctq['total_theme_items']}")

        lines.append(f"\n### Theme Item Ratings\n")
        lines.append(f"| Rating | Count | % |")
        lines.append(f"|--------|------:|---:|")
        ti = ctq["total_theme_items"]
        for r in ["insightful", "adequate", "generic", "stretching"]:
            count = ctq["item_ratings"].get(r, 0)
            pct = round(100 * count / max(ti, 1), 1)
            lines.append(f"| {r.capitalize()} | {count} | {pct}% |")

        lines.append(f"\n- Transcends taxonomy: {ctq['transcends_taxonomy_count']}/{ti} ({round(100 * ctq['transcends_taxonomy_count'] / max(ti, 1), 1)}%)")
        lines.append(f"- Names behavioral habit: {ctq['names_behavioral_habit_count']}/{ti} ({round(100 * ctq['names_behavioral_habit_count'] / max(ti, 1), 1)}%)")

        lines.append(f"\n### Themes vs Patterns\n")
        lines.append(f"| Assessment | Count | % |")
        lines.append(f"|-----------|------:|---:|")
        tr = ctq["total_runs"]
        for val in ["themes_add_value", "themes_just_restate_patterns", "no_themes_present"]:
            count = ctq["themes_vs_patterns"].get(val, 0)
            pct = round(100 * count / max(tr, 1), 1)
            lines.append(f"| {val} | {count} | {pct}% |")

    # anything_important_ignored
    aii = gc["anything_important_ignored"]
    lines.append(f"\n## Anything Important Ignored\n")
    lines.append(f"Runs with content: {aii['runs_with_content']}/{aii['total_runs']}")
    lines.append(f"\nKeyword frequency:")
    for kw, count in sorted(aii["keyword_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"- '{kw}': {count}/{aii['total_runs']}")

    # Pattern alignment misfits
    misfits = synthesis["pattern_alignment"]
    if misfits:
        lines.append("\n## Pattern Alignment Misfits\n")
        for pid in PATTERN_ORDER:
            items = misfits.get(pid, [])
            if items:
                lines.append(f"\n**{pid}** ({len(items)} misfits):")
                for item in items[:5]:
                    short = item["meeting"].split("_", 1)[0]
                    lines.append(f"- [{short}] fits={item['fits']}, better={item['better_pattern'][:80]}")

    # Run profiles
    lines.append("\n## Per-Run Rating Profiles\n")
    for meeting, profiles in sorted(synthesis["run_profiles"].items()):
        avg_ins = sum(p["insightful"] for p in profiles) / len(profiles)
        avg_ped = sum(p["pedantic"] for p in profiles) / len(profiles)
        avg_tot = sum(p["total"] for p in profiles) / len(profiles)
        lines.append(f"- {meeting}: avg {avg_ins:.1f} ins / {avg_ped:.1f} ped / {avg_tot:.1f} total per run")

    # Phase comparison
    if comparison:
        lines.append("\n---\n## Phase Comparison\n")

        ad = comparison["aggregate_delta"]
        lines.append(f"| Metric | Baseline | Current | Delta |")
        lines.append(f"|--------|--------:|--------:|------:|")
        ba_n = ad["baseline_n"]
        ca_n = ad["current_n"]
        # Recompute baseline %s from current synthesis + delta
        for r in ["insightful", "pedantic", "wrong"]:
            cur = synthesis["ratings"]["aggregate"].get(f"{r}_pct", 0)
            delta = ad[f"{r}_pct"]
            base = round(cur - delta, 1)
            sign = "+" if delta >= 0 else ""
            lines.append(f"| {r.capitalize()}% | {base}% | {cur}% | {sign}{delta}pp |")
        lines.append(f"| Total ratings | {ba_n} | {ca_n} | {ca_n - ba_n:+d} |")

        lines.append(f"\n### Per-Pattern Deltas\n")
        lines.append(f"| Pattern | Ins% delta | Ped% delta | Cur N | Base N |")
        lines.append(f"|---------|----------:|-----------:|------:|-------:|")
        for pid in PATTERN_ORDER:
            pd = comparison["per_pattern_delta"].get(pid)
            if not pd:
                continue
            if pd.get("new_pattern"):
                lines.append(f"| {pid} | NEW | NEW | {pd.get('n', '?')} | - |")
            else:
                i_sign = "+" if pd["insightful_pct_delta"] >= 0 else ""
                p_sign = "+" if pd["pedantic_pct_delta"] >= 0 else ""
                lines.append(f"| {pid} | {i_sign}{pd['insightful_pct_delta']}pp | {p_sign}{pd['pedantic_pct_delta']}pp | {pd['current_n']} | {pd['baseline_n']} |")

        lines.append(f"\n### Anything Important Ignored Keywords\n")
        lines.append(f"| Keyword | Baseline | Current |")
        lines.append(f"|---------|--------:|--------:|")
        for kw, kd in sorted(comparison["aii_keyword_delta"].items()):
            lines.append(f"| {kw} | {kd['baseline']}/{kd['baseline_total']} | {kd['current']}/{kd['current_total']} |")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def run_synthesis(results_dir: Path, latest_batch_only: bool = True) -> dict[str, Any]:
    """Run full synthesis on judge files in results_dir."""
    meetings = discover_judge_files(results_dir, latest_batch_only=latest_batch_only)

    if not meetings:
        logger.error("No judge files found in %s", results_dir)
        return {}

    all_data: list[dict] = []
    for meeting_id, files in sorted(meetings.items()):
        logger.info("Loading %d judge files for %s", len(files), meeting_id)
        all_data.extend(load_judge_data(files))

    logger.info("Total: %d judge files across %d meetings", len(all_data), len(meetings))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    synthesis = {
        "timestamp": timestamp,
        "meetings": sorted(meetings.keys()),
        "total_judge_files": len(all_data),
        "ratings": synthesize_ratings(all_data),
        "evidence_quality": synthesize_evidence_quality(all_data),
        "rewrite_quality": synthesize_rewrite_quality(all_data),
        "gut_check": synthesize_gut_check(all_data),
        "internal_consistency": synthesize_internal_consistency(all_data),
        "pattern_alignment": synthesize_pattern_alignment(all_data),
        "run_profiles": synthesize_run_profiles(all_data),
        "executive_summary_quality": synthesize_executive_summary_quality(all_data),
        "coaching_themes_quality": synthesize_coaching_themes_quality(all_data),
    }

    return synthesis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize judge_eval outputs across meetings and runs.",
    )
    parser.add_argument("--results-dir", type=Path, required=True,
                        help="Directory containing per-meeting result subdirectories")
    parser.add_argument("--baseline-dir", type=Path, default=None,
                        help="Baseline phase results directory for comparison")
    parser.add_argument("--all-judges", action="store_true", default=False,
                        help="Use ALL judge files instead of most-recent-batch only")
    args = parser.parse_args()

    latest_batch_only = not args.all_judges

    # Current synthesis
    synthesis = run_synthesis(args.results_dir, latest_batch_only=latest_batch_only)
    if not synthesis:
        return

    # Baseline synthesis (if provided)
    comparison = None
    baseline_synthesis = None
    if args.baseline_dir:
        logger.info("Loading baseline from %s", args.baseline_dir)
        baseline_synthesis = run_synthesis(args.baseline_dir, latest_batch_only=latest_batch_only)
        if baseline_synthesis:
            comparison = compare_phases(synthesis, baseline_synthesis)
            synthesis["comparison"] = comparison

    # Save outputs
    timestamp = synthesis["timestamp"]
    out_json = args.results_dir / f"judge_synthesis_{timestamp}.json"
    out_md = args.results_dir / f"judge_synthesis_{timestamp}.md"

    save_json(synthesis, out_json)

    md = format_report(synthesis, comparison)
    save_report(md, out_md)

    # Print summary
    agg = synthesis["ratings"]["aggregate"]
    print(f"\n{'='*60}")
    print(f"Insightful: {agg['insightful_pct']}% | Pedantic: {agg['pedantic_pct']}% | Wrong: {agg['wrong_pct']}%")
    print(f"Total ratings: {agg['n']} across {len(synthesis['meetings'])} meetings")

    if comparison:
        ad = comparison["aggregate_delta"]
        print(f"\nvs Baseline: Ins {ad['insightful_pct']:+.1f}pp | Ped {ad['pedantic_pct']:+.1f}pp | Wrg {ad['wrong_pct']:+.1f}pp")


if __name__ == "__main__":
    main()
