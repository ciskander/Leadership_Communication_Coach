#!/usr/bin/env python3
"""
Pattern Scoring Diagnostics — Root-cause analysis of scoring anomalies.

Operates on raw analysis JSON outputs (the full mvp.v0.4.0 schema objects)
to diagnose specific failure modes observed in the scoring pipeline.

Four diagnostic tests, each with a clear hypothesis:

  TEST 1: PF Element B Anchoring
    Hypothesis: Element B count is anchored at exactly 3 regardless of
    opportunity count, suggesting the LLM uses a fixed allocation rather
    than evaluating each opportunity independently.

  TEST 2: PM Aggregate Lock
    Hypothesis: Participation Management always produces a 0.5 aggregate
    even though per-opportunity scores vary, because the LLM applies a
    stable interpretive template that yields the same tier distribution.

  TEST 3: R&A Element A Triviality
    Hypothesis: Element A (named resolution) is trivially satisfied —
    scoring 100% in every meeting — so all R&A variation comes from
    Element B. This means Element A has zero discriminative value.

  TEST 4: Cross-Meeting Noise Floor
    Hypothesis: Near-duplicate transcripts (M-000203 vs M-000205) show
    ~0.15 score deltas from LLM non-determinism, establishing a noise
    floor below which score differences are not meaningful signal.

Usage:
    python scripts/pattern_scoring_diagnostics.py analysis1.json analysis2.json ...

    Pass one or more analysis JSON files as arguments. The script will run
    all applicable tests and print a structured diagnostic report.

    You can also pass a directory, and the script will process all .json files in it.
"""

import json
import math
import sys
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────

def load_analyses(paths: list[str]) -> list[dict[str, Any]]:
    """Load analysis JSON files from paths (files or directories)."""
    analyses = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.glob("*.json")):
                analyses.append(_load_one(f))
        elif path.is_file():
            analyses.append(_load_one(path))
        else:
            print(f"  WARNING: skipping {p} (not a file or directory)")
    return analyses


def _load_one(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Tag with source file for reporting
    data["_source_file"] = str(path)
    return data


def get_meeting_id(analysis: dict) -> str:
    return analysis.get("context", {}).get("meeting_id", "unknown")


def get_pattern(analysis: dict, pattern_id: str) -> dict | None:
    """Extract a pattern from the pattern_snapshot by ID."""
    for p in analysis.get("pattern_snapshot", []):
        if p.get("pattern_id") == pattern_id:
            return p
    return None


# ─────────────────────────────────────────────────────────────
# TEST 1: Purposeful Framing — Element B Anchoring
# ─────────────────────────────────────────────────────────────

def test_pf_element_b_anchoring(analyses: list[dict]) -> dict:
    """
    Hypothesis: Element B count is fixed at a constant value regardless of
    opportunity count.

    We check:
    1. Is element_b_count the same across all evaluable meetings?
    2. Does element_b_count correlate with opportunity_count?
    3. Is element_a_count always == opportunity_count (trivially satisfied)?
    """
    results = {
        "test_name": "PF Element B Anchoring",
        "hypothesis": "Element B count is anchored at a fixed value regardless of opportunity count",
        "meetings_analyzed": 0,
        "observations": [],
        "element_b_values": [],
        "element_a_ratios": [],
        "verdict": "",
    }

    for a in analyses:
        pf = get_pattern(a, "purposeful_framing")
        if not pf or pf.get("evaluable_status") != "evaluable":
            continue

        mid = get_meeting_id(a)
        opp = pf.get("opportunity_count", 0)
        ea = pf.get("element_a_count", 0)
        eb = pf.get("element_b_count", 0)
        score = pf.get("score", 0)

        results["meetings_analyzed"] += 1
        results["element_b_values"].append(eb)
        results["element_a_ratios"].append(ea / opp if opp > 0 else 0)

        results["observations"].append({
            "meeting_id": mid,
            "opportunity_count": opp,
            "element_a_count": ea,
            "element_b_count": eb,
            "element_a_ratio": round(ea / opp, 3) if opp > 0 else 0,
            "element_b_ratio": round(eb / opp, 3) if opp > 0 else 0,
            "score": score,
        })

    n = results["meetings_analyzed"]
    if n < 2:
        results["verdict"] = f"INSUFFICIENT DATA — only {n} evaluable meeting(s)"
        return results

    # Check Element B anchoring
    eb_vals = results["element_b_values"]
    eb_unique = set(eb_vals)
    eb_mean = sum(eb_vals) / len(eb_vals)
    eb_sd = math.sqrt(sum((v - eb_mean) ** 2 for v in eb_vals) / len(eb_vals))

    # Check Element A triviality
    ea_ratios = results["element_a_ratios"]
    ea_all_100 = all(r == 1.0 for r in ea_ratios)

    # Check if Element B is independent of opportunity count
    opps = [o["opportunity_count"] for o in results["observations"]]
    if len(set(opps)) > 1:
        # Compute Pearson correlation between opp_count and element_b
        mean_opp = sum(opps) / len(opps)
        cov = sum((o - mean_opp) * (b - eb_mean) for o, b in zip(opps, eb_vals)) / len(opps)
        sd_opp = math.sqrt(sum((o - mean_opp) ** 2 for o in opps) / len(opps))
        correlation = cov / (sd_opp * eb_sd) if sd_opp > 0 and eb_sd > 0 else 0
    else:
        correlation = None

    # Build verdict
    verdicts = []

    if len(eb_unique) == 1:
        verdicts.append(
            f"CONFIRMED: Element B count is FIXED at {eb_vals[0]} across all "
            f"{n} meetings regardless of opportunity count ({min(opps)}-{max(opps)}). "
            f"The LLM is anchoring, not evaluating independently."
        )
    elif eb_sd < 0.5:
        verdicts.append(
            f"LIKELY: Element B count has very low variance (mean={eb_mean:.1f}, "
            f"sd={eb_sd:.2f}, values={sorted(eb_unique)}). Near-anchoring."
        )
    else:
        verdicts.append(
            f"NOT CONFIRMED: Element B varies meaningfully (mean={eb_mean:.1f}, "
            f"sd={eb_sd:.2f}, values={sorted(eb_unique)})."
        )

    if ea_all_100:
        verdicts.append(
            f"CONFIRMED: Element A is trivially satisfied — 100% in all {n} meetings. "
            f"Zero discriminative value."
        )
    else:
        low = [o for o in results["observations"] if o["element_a_ratio"] < 1.0]
        verdicts.append(
            f"PARTIAL: Element A < 100% in {len(low)} of {n} meetings: "
            f"{[(o['meeting_id'], o['element_a_ratio']) for o in low]}"
        )

    if correlation is not None:
        verdicts.append(
            f"Element B vs opportunity_count correlation: r={correlation:.3f} "
            f"({'no relationship' if abs(correlation) < 0.3 else 'some relationship'})"
        )

    results["verdict"] = " | ".join(verdicts)
    results["summary_stats"] = {
        "element_b_unique_values": sorted(eb_unique),
        "element_b_mean": round(eb_mean, 2),
        "element_b_sd": round(eb_sd, 3),
        "element_a_always_100pct": ea_all_100,
        "element_b_vs_opp_correlation": round(correlation, 3) if correlation is not None else None,
    }
    return results


# ─────────────────────────────────────────────────────────────
# TEST 2: Participation Management — Aggregate Lock
# ─────────────────────────────────────────────────────────────

def test_pm_aggregate_lock(analyses: list[dict]) -> dict:
    """
    Hypothesis: PM always produces a 0.5 aggregate regardless of
    opportunity count, meeting type, or meeting content.

    We check:
    1. How many evaluable PM scores are exactly 0.5?
    2. What is the range and SD of PM scores?
    3. Is the coaching note text substantively similar across meetings?
    """
    results = {
        "test_name": "PM Aggregate Lock",
        "hypothesis": "PM score is locked at 0.5 across all meetings",
        "meetings_analyzed": 0,
        "observations": [],
        "scores": [],
        "verdict": "",
    }

    for a in analyses:
        pm = get_pattern(a, "participation_management")
        if not pm or pm.get("evaluable_status") != "evaluable":
            continue

        mid = get_meeting_id(a)
        score = pm.get("score", -1)
        opp = pm.get("opportunity_count", 0)
        balance = pm.get("balance_assessment", "")
        success_spans = pm.get("success_evidence_span_ids", [])
        total_spans = pm.get("evidence_span_ids", [])

        # In v0.4.0, coaching notes live in coaching.pattern_coaching[]
        coaching_note = ""
        for pc in a.get("coaching", {}).get("pattern_coaching", []):
            if pc.get("pattern_id") == "participation_management":
                coaching_note = pc.get("coaching_note", "") or pc.get("notes", "") or ""
                break

        results["meetings_analyzed"] += 1
        results["scores"].append(score)

        results["observations"].append({
            "meeting_id": mid,
            "score": score,
            "opportunity_count": opp,
            "balance_assessment": balance,
            "success_spans": len(success_spans),
            "total_spans": len(total_spans),
            "coaching_note_preview": coaching_note[:100] + "..." if len(coaching_note) > 100 else coaching_note,
        })

    n = results["meetings_analyzed"]
    if n < 2:
        results["verdict"] = f"INSUFFICIENT DATA — only {n} evaluable meeting(s)"
        return results

    scores = results["scores"]
    exactly_05 = sum(1 for s in scores if s == 0.5)
    score_mean = sum(scores) / len(scores)
    score_sd = math.sqrt(sum((s - score_mean) ** 2 for s in scores) / len(scores))
    score_range = max(scores) - min(scores)

    # Check coaching note similarity
    coaching_notes = [o["coaching_note_preview"] for o in results["observations"]]
    unique_coaching = len(set(coaching_notes))

    verdicts = []
    if exactly_05 == n:
        verdicts.append(
            f"CONFIRMED: PM score is exactly 0.50 in ALL {n} evaluable meetings. "
            f"The aggregate is locked."
        )
    elif score_range < 0.1:
        verdicts.append(
            f"LIKELY: PM scores cluster tightly (range={score_range:.3f}, "
            f"sd={score_sd:.3f}). Near-locked."
        )
    else:
        verdicts.append(
            f"NOT CONFIRMED: PM scores show variation (range={score_range:.3f}, "
            f"sd={score_sd:.3f}, values={[o['score'] for o in results['observations']]})."
        )

    if unique_coaching < n:
        verdicts.append(
            f"COACHING SIMILARITY: Only {unique_coaching} unique coaching note(s) "
            f"across {n} meetings — formulaic feedback."
        )

    results["verdict"] = " | ".join(verdicts)
    results["summary_stats"] = {
        "exactly_0.5_count": exactly_05,
        "score_mean": round(score_mean, 4),
        "score_sd": round(score_sd, 4),
        "score_range": round(score_range, 4),
        "unique_coaching_notes": unique_coaching,
    }
    return results


# ─────────────────────────────────────────────────────────────
# TEST 3: R&A Element A Triviality
# ─────────────────────────────────────────────────────────────

def test_ra_element_a_triviality(analyses: list[dict]) -> dict:
    """
    Hypothesis: Element A (named resolution) is always 100%, meaning
    all R&A score variation comes from Element B (alignment check).

    We check:
    1. What fraction of meetings have element_a_count == opportunity_count?
    2. How does Element B vary compared to Element A?
    3. What is the effective scoring model if Element A is trivial?
    """
    results = {
        "test_name": "R&A Element A Triviality",
        "hypothesis": "Element A is trivially satisfied (always 100%), so all variation comes from Element B",
        "meetings_analyzed": 0,
        "observations": [],
        "verdict": "",
    }

    for a in analyses:
        ra = get_pattern(a, "resolution_and_alignment")
        if not ra or ra.get("evaluable_status") != "evaluable":
            continue

        mid = get_meeting_id(a)
        opp = ra.get("opportunity_count", 0)
        ea = ra.get("element_a_count", 0)
        eb = ra.get("element_b_count", 0)
        score = ra.get("score", 0)

        results["meetings_analyzed"] += 1

        # Compute what the score would be if Element A were removed
        # (i.e., score based only on Element B)
        eb_only_score = eb / opp if opp > 0 else 0
        # And the effective score formula: (ea + eb) / (2 * opp)
        expected_score = (ea + eb) / (2 * opp) if opp > 0 else 0

        results["observations"].append({
            "meeting_id": mid,
            "opportunity_count": opp,
            "element_a_count": ea,
            "element_b_count": eb,
            "element_a_pct": round(ea / opp * 100, 1) if opp > 0 else 0,
            "element_b_pct": round(eb / opp * 100, 1) if opp > 0 else 0,
            "actual_score": score,
            "expected_score": round(expected_score, 4),
            "eb_only_score": round(eb_only_score, 4),
        })

    n = results["meetings_analyzed"]
    if n < 2:
        results["verdict"] = f"INSUFFICIENT DATA — only {n} evaluable meeting(s)"
        return results

    ea_pcts = [o["element_a_pct"] for o in results["observations"]]
    eb_pcts = [o["element_b_pct"] for o in results["observations"]]
    ea_always_100 = all(p == 100.0 for p in ea_pcts)
    ea_mean = sum(ea_pcts) / len(ea_pcts)

    eb_mean = sum(eb_pcts) / len(eb_pcts)
    eb_sd = math.sqrt(sum((p - eb_mean) ** 2 for p in eb_pcts) / len(eb_pcts))

    # If Element A is always 100%, the score formula simplifies:
    # score = (opp + eb) / (2 * opp) = 0.5 + eb / (2 * opp)
    # So the floor is 0.5 and the ceiling is 1.0, with Element B as the only driver.

    verdicts = []
    if ea_always_100:
        verdicts.append(
            f"CONFIRMED: Element A = 100% in ALL {n} meetings. "
            f"The dual-element structure is effectively single-element. "
            f"Score floor is 0.50, ceiling is 1.00. "
            f"Element A provides zero information."
        )
        verdicts.append(
            f"Effective formula: score = 0.5 + (element_b_count / (2 * opportunity_count)). "
            f"Element B varies: mean={eb_mean:.1f}%, sd={eb_sd:.1f}%."
        )
    else:
        low_ea = [o for o in results["observations"] if o["element_a_pct"] < 100]
        verdicts.append(
            f"PARTIAL: Element A < 100% in {len(low_ea)} of {n} meetings. "
            f"Not fully trivial. Mean={ea_mean:.1f}%."
        )

    # Check if score matches the formula exactly
    formula_matches = all(
        abs(o["actual_score"] - o["expected_score"]) < 0.001
        for o in results["observations"]
    )
    if formula_matches:
        verdicts.append("Score matches (ea+eb)/(2*opp) formula exactly in all meetings.")
    else:
        mismatches = [
            (o["meeting_id"], o["actual_score"], o["expected_score"])
            for o in results["observations"]
            if abs(o["actual_score"] - o["expected_score"]) >= 0.001
        ]
        verdicts.append(f"Score formula mismatches: {mismatches}")

    results["verdict"] = " | ".join(verdicts)
    results["summary_stats"] = {
        "element_a_always_100pct": ea_always_100,
        "element_a_mean_pct": round(ea_mean, 1),
        "element_b_mean_pct": round(eb_mean, 1),
        "element_b_sd_pct": round(eb_sd, 1),
        "score_floor_if_ea_trivial": 0.5,
    }
    return results


# ─────────────────────────────────────────────────────────────
# TEST 4: Cross-Meeting Noise Floor
# ─────────────────────────────────────────────────────────────

def test_noise_floor(analyses: list[dict]) -> dict:
    """
    Hypothesis: Near-duplicate transcripts produce ~0.15 score deltas
    from LLM non-determinism, establishing a noise floor.

    We find meeting pairs with highly similar evidence (based on shared
    evidence span text) and compute per-pattern score deltas.
    """
    results = {
        "test_name": "Cross-Meeting Noise Floor",
        "hypothesis": "Near-duplicate transcripts show ~0.15 score deltas from LLM non-determinism",
        "pairs_found": 0,
        "pair_analyses": [],
        "verdict": "",
    }

    # Build a map of meeting_id -> evidence excerpts
    def get_excerpts(a: dict) -> set[str]:
        return {
            es.get("excerpt", "")[:80]
            for es in a.get("evidence_spans", [])
            if es.get("excerpt")
        }

    # Find pairs with high overlap
    for i in range(len(analyses)):
        for j in range(i + 1, len(analyses)):
            a1, a2 = analyses[i], analyses[j]
            mid1 = get_meeting_id(a1)
            mid2 = get_meeting_id(a2)

            exc1 = get_excerpts(a1)
            exc2 = get_excerpts(a2)

            if not exc1 or not exc2:
                continue

            overlap = len(exc1 & exc2)
            total = len(exc1 | exc2)
            jaccard = overlap / total if total > 0 else 0

            if jaccard < 0.3:
                continue

            results["pairs_found"] += 1

            # Compare scores per pattern
            pattern_deltas = {}
            all_patterns = [
                "purposeful_framing", "focus_management", "participation_management",
                "disagreement_navigation", "resolution_and_alignment", "assignment_clarity",
                "question_quality", "communication_clarity", "feedback_quality",
            ]

            for pid in all_patterns:
                p1 = get_pattern(a1, pid)
                p2 = get_pattern(a2, pid)
                if (p1 and p2 and
                    p1.get("evaluable_status") == "evaluable" and
                    p2.get("evaluable_status") == "evaluable"):
                    s1 = p1.get("score", 0)
                    s2 = p2.get("score", 0)
                    pattern_deltas[pid] = {
                        "score_1": s1,
                        "score_2": s2,
                        "delta": round(abs(s1 - s2), 4),
                    }

            deltas = [v["delta"] for v in pattern_deltas.values()]
            mean_delta = sum(deltas) / len(deltas) if deltas else 0
            max_delta = max(deltas) if deltas else 0

            # Identify which patterns had zero delta (locked)
            locked = [pid for pid, v in pattern_deltas.items() if v["delta"] == 0]
            variable = [pid for pid, v in pattern_deltas.items() if v["delta"] > 0]

            results["pair_analyses"].append({
                "meeting_1": mid1,
                "meeting_2": mid2,
                "evidence_jaccard": round(jaccard, 3),
                "evidence_overlap": overlap,
                "pattern_deltas": pattern_deltas,
                "mean_delta": round(mean_delta, 4),
                "max_delta": round(max_delta, 4),
                "locked_patterns": locked,
                "variable_patterns": variable,
            })

    if results["pairs_found"] == 0:
        results["verdict"] = (
            "NO NEAR-DUPLICATE PAIRS FOUND. "
            "To run this test, provide analyses of the same or very similar transcripts."
        )
        return results

    # Aggregate across pairs
    all_deltas = []
    for pair in results["pair_analyses"]:
        all_deltas.extend(v["delta"] for v in pair["pattern_deltas"].values())

    overall_mean = sum(all_deltas) / len(all_deltas) if all_deltas else 0
    overall_max = max(all_deltas) if all_deltas else 0
    overall_p90 = sorted(all_deltas)[int(0.9 * len(all_deltas))] if all_deltas else 0

    verdicts = []
    verdicts.append(
        f"Found {results['pairs_found']} near-duplicate pair(s). "
        f"Mean per-pattern delta: {overall_mean:.3f}, "
        f"max: {overall_max:.3f}, p90: {overall_p90:.3f}."
    )

    if overall_mean > 0.10:
        verdicts.append(
            f"SIGNIFICANT NOISE: Mean delta {overall_mean:.3f} is substantial. "
            f"Score movements below ~{overall_p90:.2f} may be noise, not signal."
        )
    elif overall_mean > 0.05:
        verdicts.append(
            f"MODERATE NOISE: Mean delta {overall_mean:.3f}. "
            f"Score movements below ~{overall_p90:.2f} should be treated cautiously."
        )
    else:
        verdicts.append(f"LOW NOISE: Mean delta {overall_mean:.3f}. Good reproducibility.")

    # Report which patterns are locked vs variable
    for pair in results["pair_analyses"]:
        if pair["locked_patterns"]:
            verdicts.append(
                f"Locked patterns (delta=0) in {pair['meeting_1']} vs {pair['meeting_2']}: "
                f"{pair['locked_patterns']} — these may be structurally unable to vary."
            )

    results["verdict"] = " | ".join(verdicts)
    results["summary_stats"] = {
        "overall_mean_delta": round(overall_mean, 4),
        "overall_max_delta": round(overall_max, 4),
        "overall_p90_delta": round(overall_p90, 4),
        "noise_floor_estimate": round(overall_p90, 2),
    }
    return results


# ─────────────────────────────────────────────────────────────
# Bonus: Cross-pattern summary table
# ─────────────────────────────────────────────────────────────

def cross_pattern_summary(analyses: list[dict]) -> dict:
    """
    Aggregate all evaluable scores per pattern across meetings.
    Report mean, SD, range, and evaluability rate.
    """
    all_patterns = [
        "purposeful_framing", "focus_management", "participation_management",
        "disagreement_navigation", "resolution_and_alignment", "assignment_clarity",
        "question_quality", "communication_clarity", "feedback_quality",
    ]

    summary = {}
    for pid in all_patterns:
        scores = []
        evaluable = 0
        total = 0
        for a in analyses:
            p = get_pattern(a, pid)
            if not p:
                continue
            total += 1
            if p.get("evaluable_status") == "evaluable":
                evaluable += 1
                scores.append(p.get("score", 0))

        if scores:
            mean = sum(scores) / len(scores)
            sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / len(scores))
            summary[pid] = {
                "evaluable_count": evaluable,
                "total_count": total,
                "evaluability_rate": round(evaluable / total, 2) if total > 0 else 0,
                "scores": [round(s, 4) for s in scores],
                "mean": round(mean, 4),
                "sd": round(sd, 4),
                "min": round(min(scores), 4),
                "max": round(max(scores), 4),
                "range": round(max(scores) - min(scores), 4),
            }
        else:
            summary[pid] = {
                "evaluable_count": 0,
                "total_count": total,
                "evaluability_rate": 0,
                "scores": [],
                "mean": None,
                "sd": None,
                "min": None,
                "max": None,
                "range": None,
            }

    return summary


# ─────────────────────────────────────────────────────────────
# Report printer
# ─────────────────────────────────────────────────────────────

def print_report(test_result: dict, indent: int = 0):
    """Pretty-print a test result."""
    pad = "  " * indent
    print(f"\n{pad}{'=' * 70}")
    print(f"{pad}{test_result['test_name']}")
    print(f"{pad}{'=' * 70}")
    print(f"{pad}Hypothesis: {test_result['hypothesis']}")
    print(f"{pad}Meetings analyzed: {test_result.get('meetings_analyzed', test_result.get('pairs_found', 0))}")
    print()

    # Print observations table if present
    observations = test_result.get("observations", [])
    if observations:
        # Determine columns from first observation
        cols = list(observations[0].keys())
        # Print header
        header = pad + "  ".join(f"{c[:18]:>18}" for c in cols)
        print(header)
        print(pad + "-" * len(header.strip()))
        for obs in observations:
            row = pad + "  ".join(f"{str(obs.get(c, ''))[:18]:>18}" for c in cols)
            print(row)
        print()

    # Print pair analyses if present
    for pair in test_result.get("pair_analyses", []):
        print(f"{pad}  Pair: {pair['meeting_1']} vs {pair['meeting_2']} "
              f"(Jaccard={pair['evidence_jaccard']}, overlap={pair['evidence_overlap']})")
        print(f"{pad}  Mean delta: {pair['mean_delta']:.4f}, Max delta: {pair['max_delta']:.4f}")
        print(f"{pad}  Locked (delta=0): {pair['locked_patterns']}")
        for pid, v in pair["pattern_deltas"].items():
            marker = " *" if v["delta"] > 0.10 else ""
            print(f"{pad}    {pid:<28s}  {v['score_1']:.4f}  {v['score_2']:.4f}  "
                  f"delta={v['delta']:.4f}{marker}")
        print()

    # Print summary stats
    stats = test_result.get("summary_stats", {})
    if stats:
        print(f"{pad}Summary stats:")
        for k, v in stats.items():
            print(f"{pad}  {k}: {v}")
        print()

    # Print verdict
    print(f"{pad}VERDICT:")
    for part in test_result["verdict"].split(" | "):
        print(f"{pad}  {part}")
    print()


def print_summary_table(summary: dict):
    """Print the cross-pattern summary as a table."""
    print("\n" + "=" * 90)
    print("CROSS-PATTERN SUMMARY")
    print("=" * 90)
    print(f"  {'Pattern':<28s}  {'Eval':>4}  {'Mean':>6}  {'SD':>6}  "
          f"{'Min':>6}  {'Max':>6}  {'Range':>6}  {'Scores'}")
    print(f"  {'-'*28}  {'-'*4}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*20}")

    for pid, stats in summary.items():
        if stats["mean"] is not None:
            scores_str = ", ".join(f"{s:.2f}" for s in stats["scores"])
            print(f"  {pid:<28s}  {stats['evaluable_count']:>4}  "
                  f"{stats['mean']:>6.3f}  {stats['sd']:>6.3f}  "
                  f"{stats['min']:>6.3f}  {stats['max']:>6.3f}  "
                  f"{stats['range']:>6.3f}  [{scores_str}]")
        else:
            print(f"  {pid:<28s}  {stats['evaluable_count']:>4}  "
                  f"{'—':>6}  {'—':>6}  {'—':>6}  {'—':>6}  {'—':>6}  "
                  f"[no evaluable data]")

    print()

    # Flag patterns with potential issues
    print("  Diagnostic flags:")
    for pid, stats in summary.items():
        flags = []
        if stats["evaluability_rate"] < 0.5:
            flags.append(f"low evaluability ({stats['evaluability_rate']:.0%})")
        if stats["range"] is not None and stats["range"] < 0.05:
            flags.append(f"near-zero range ({stats['range']:.3f})")
        if stats["range"] is not None and stats["range"] < 0.15 and stats["evaluable_count"] >= 3:
            flags.append(f"range below noise floor estimate")
        if stats["sd"] is not None and stats["sd"] < 0.02:
            flags.append(f"near-zero SD ({stats['sd']:.3f})")

        if flags:
            print(f"    {pid}: {', '.join(flags)}")

    print()


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Error: provide one or more analysis JSON files or directories.")
        sys.exit(1)

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  ClearVoice v3.0 — Pattern Scoring Diagnostics                     ║")
    print("║  Root-cause analysis of scoring anomalies                          ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    analyses = load_analyses(sys.argv[1:])
    print(f"Loaded {len(analyses)} analysis file(s):")
    for a in analyses:
        mid = get_meeting_id(a)
        mtype = a.get("context", {}).get("meeting_type", "?")
        role = a.get("context", {}).get("target_role", "?")
        evaluated = len(a.get("evaluation_summary", {}).get("patterns_evaluated", []))
        print(f"  {mid} — {mtype} / {role} — {evaluated} patterns evaluated")
    print()

    # Run all tests
    test_results = [
        test_pf_element_b_anchoring(analyses),
        test_pm_aggregate_lock(analyses),
        test_ra_element_a_triviality(analyses),
        test_noise_floor(analyses),
    ]

    for tr in test_results:
        print_report(tr)

    # Cross-pattern summary
    summary = cross_pattern_summary(analyses)
    print_summary_table(summary)

    # Final synthesis
    print("=" * 90)
    print("DIAGNOSTIC SYNTHESIS")
    print("=" * 90)
    print()

    confirmed = [tr["test_name"] for tr in test_results if "CONFIRMED" in tr["verdict"]]
    likely = [tr["test_name"] for tr in test_results if "LIKELY" in tr["verdict"]]
    not_confirmed = [tr["test_name"] for tr in test_results if "NOT CONFIRMED" in tr["verdict"]]

    if confirmed:
        print(f"  Confirmed issues:  {', '.join(confirmed)}")
    if likely:
        print(f"  Likely issues:     {', '.join(likely)}")
    if not_confirmed:
        print(f"  Not confirmed:     {', '.join(not_confirmed)}")

    # Estimate noise floor
    noise_test = test_results[3]
    noise_floor = noise_test.get("summary_stats", {}).get("noise_floor_estimate", "unknown")
    print(f"\n  Estimated noise floor: {noise_floor}")
    if isinstance(noise_floor, (int, float)):
        print(f"  Score deltas below {noise_floor:.2f} should NOT be interpreted as signal.")

    print()
    print("  Next steps:")
    if confirmed:
        print("  1. Fix confirmed structural issues before re-running analyses")
    print("  2. Run reproducibility test (same transcript, N=5 runs) to refine noise floor")
    print("  3. Test with deliberately different speakers to verify patterns CAN discriminate")
    print()


if __name__ == "__main__":
    main()
