"""
variance_eval.py — Phase K: Variance Decomposition.

Tests editor and judge consistency in isolation by holding input constant
and varying only the target layer's LLM call.

Two modes:
  --mode editor   Run the editor N times on a fixed pre-editor input.
  --mode judge    Run the judge N times on a fixed post-editor input.

Usage:
  python -m backend.evals.variance_eval --mode editor \
    --input backend/evals/results/M-000001_.../run_001_*.json \
    --transcript backend/evals/transcripts/M-000001_strong_facilitator.txt \
    --runs 10

  python -m backend.evals.variance_eval --mode judge \
    --input backend/evals/results/Phase_J2/M-000001_.../run_001_*.json \
    --transcript backend/evals/transcripts/M-000001_strong_facilitator.txt \
    --runs 10
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so imports work when run as module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.config import OPENAI_MODEL_DEFAULT, PATTERN_ORDER
from backend.core.editor import build_experiment_context, run_editor, merge_editor_output
from backend.core.llm_client import is_anthropic_model
from backend.core.models import MemoryBlock
from backend.core.transcript_parser import parse_transcript
from backend.evals.judge_eval import judge_analysis, load_transcript_for_judge
from backend.evals.report import save_json, save_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_RESULTS_DIR = Path(__file__).parent / "results" / "variance_tests"

# Sentinel to distinguish "field absent from delta" from "field is None"
_ABSENT = object()


# ── Input loading helpers ────────────────────────────────────────────────────


def _load_input_json(path: Path) -> dict:
    """Load a run_*.json analysis output file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _get_evaluable_patterns(parsed_output: dict) -> set[str]:
    """Return pattern_ids with evaluable_status == 'evaluable'."""
    return {
        ps["pattern_id"]
        for ps in parsed_output.get("pattern_snapshot", [])
        if ps.get("evaluable_status") == "evaluable"
    }


def _get_coached_patterns(parsed_output: dict, evaluable: set[str]) -> set[str]:
    """Return evaluable pattern_ids that have coaching content (notes or coaching_note non-null).

    Matches the judge formatter's skip logic (judge_eval.py _format_pattern_coaching).
    """
    coached = set()
    for pc in parsed_output.get("coaching", {}).get("pattern_coaching", []):
        pid = pc.get("pattern_id")
        if pid in evaluable and (pc.get("notes") or pc.get("coaching_note")):
            coached.add(pid)
    return coached


def _load_transcript_turns(transcript_path: Path) -> list[dict]:
    """Load transcript and return turns as list[dict] for run_editor().

    Returns 4-field dicts: {turn_id, speaker_label, text, speaker_role_hint}.
    """
    raw_bytes = transcript_path.read_bytes()
    parsed = parse_transcript(raw_bytes, transcript_path.name, transcript_path.stem)
    return [
        {
            "turn_id": t.turn_id,
            "speaker_label": t.speaker_label,
            "text": t.text,
            "speaker_role_hint": t.speaker_role_hint,
        }
        for t in parsed.turns
    ]


# ── Editor variance ──────────────────────────────────────────────────────────


def _run_editor_once(
    i: int,
    parsed_output: dict,
    transcript_turns: list[dict],
    experiment_context: str,
    model: str | None,
) -> tuple[int, dict]:
    """Run the editor once and return (index, result_dict)."""
    t0 = time.time()
    try:
        editor_delta, prompt_tokens, completion_tokens = run_editor(
            parsed_output, transcript_turns, experiment_context, model=model,
        )
        merged, changelog = merge_editor_output(parsed_output, editor_delta)
        elapsed = time.time() - t0
        logger.info("  Editor run %d: %d changes, %.1fs", i + 1, len(changelog), elapsed)
        return i, {
            "editor_delta": editor_delta,
            "merged": merged,
            "changelog": changelog,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "elapsed_sec": round(elapsed, 1),
        }
    except Exception as e:
        logger.error("  Editor run %d failed: %s", i + 1, e)
        return i, {"error": str(e)}


def _compute_editor_metrics(
    runs: list[dict],
    evaluable_patterns: set[str],
) -> dict:
    """Compute consistency metrics across N editor runs."""
    n_runs = len(runs)
    valid_runs = [r for r in runs if "error" not in r]
    n_valid = len(valid_runs)

    if n_valid == 0:
        return {"n_runs": n_runs, "n_valid": 0, "error": "All runs failed"}

    # ── Per-pattern action distribution ──
    # For each pattern × field, classify: suppress / rewrite / pass
    per_pattern: dict[str, dict[str, Counter]] = {}
    for pid in sorted(evaluable_patterns & set(PATTERN_ORDER), key=PATTERN_ORDER.index):
        per_pattern[pid] = {"notes": Counter(), "coaching_note": Counter()}
        for r in valid_runs:
            edits = r["editor_delta"].get("pattern_coaching_edits", {}).get(pid, {})
            for field in ("notes", "coaching_note"):
                val = edits.get(field, _ABSENT)
                if val is _ABSENT or val is None:
                    action = "pass"
                elif val == "SUPPRESS":
                    action = "suppress"
                else:
                    action = "rewrite"
                per_pattern[pid][field][action] += 1

    # ── Unanimous rate ──
    total_combos = 0
    unanimous_combos = 0
    flip_patterns = []
    for pid, fields in per_pattern.items():
        for field, counts in fields.items():
            total_combos += 1
            if len(counts) == 1:
                unanimous_combos += 1
            else:
                flip_patterns.append({
                    "pattern_id": pid,
                    "field": field,
                    "distribution": dict(counts),
                })
    unanimous_rate = unanimous_combos / total_combos if total_combos > 0 else 1.0

    # ── Top-level field change rates ──
    exec_summary_changed = sum(
        1 for r in valid_runs
        if r["editor_delta"].get("executive_summary") is not None
    )
    coaching_themes_changed = sum(
        1 for r in valid_runs
        if r["editor_delta"].get("coaching_themes") is not None
    )
    focus_message_changed = sum(
        1 for r in valid_runs
        if r["editor_delta"].get("focus_message") is not None
    )

    # ── OE removal agreement ──
    all_oe_keys: set[tuple[str, int]] = set()
    oe_counts: Counter[tuple[str, int]] = Counter()
    for r in valid_runs:
        for rem in r["editor_delta"].get("oe_removals", []):
            key = (rem["pattern_id"], rem["oe_index"])
            all_oe_keys.add(key)
            oe_counts[key] += 1

    oe_items = []
    oe_agreed = 0
    for key in sorted(all_oe_keys):
        count = oe_counts[key]
        oe_items.append({"pattern_id": key[0], "oe_index": key[1], "flagged_in": count})
        if count == n_valid:  # flagged in all runs
            oe_agreed += 1
    # OEs never flagged are implicitly agreed (not in the set at all)
    oe_agreement_rate = (oe_agreed / len(all_oe_keys)) if all_oe_keys else 1.0

    # ── Total changes per run ──
    changes_per_run = []
    for r in valid_runs:
        count = len(r["changelog"])
        changes_per_run.append(count)

    return {
        "n_runs": n_runs,
        "n_valid": n_valid,
        "evaluable_patterns": sorted(evaluable_patterns & set(PATTERN_ORDER), key=PATTERN_ORDER.index),
        "per_pattern": {pid: {f: dict(c) for f, c in fields.items()} for pid, fields in per_pattern.items()},
        "unanimous_rate": round(unanimous_rate, 4),
        "unanimous_combos": unanimous_combos,
        "total_combos": total_combos,
        "flip_patterns": flip_patterns,
        "exec_summary_changed_rate": round(exec_summary_changed / n_valid, 4),
        "coaching_themes_changed_rate": round(coaching_themes_changed / n_valid, 4),
        "focus_message_changed_rate": round(focus_message_changed / n_valid, 4),
        "oe_removals": {"items": oe_items, "agreement_rate": round(oe_agreement_rate, 4)},
        "changes_per_run": {
            "values": changes_per_run,
            "min": min(changes_per_run),
            "max": max(changes_per_run),
            "mean": round(statistics.mean(changes_per_run), 1),
        },
    }


def _format_editor_report(metrics: dict, input_stem: str, model: str) -> str:
    """Format editor variance metrics as a markdown report."""
    lines = [
        "# Editor Variance Report",
        "",
        f"**Input**: `{input_stem}`  ",
        f"**Model**: `{model}`  ",
        f"**Runs**: {metrics['n_valid']}/{metrics['n_runs']} valid  ",
        f"**Evaluable patterns**: {len(metrics['evaluable_patterns'])}",
        "",
        "---",
        "",
        "## Overall Consistency",
        "",
        f"- **Unanimous rate**: {metrics['unanimous_rate']:.1%} "
        f"({metrics['unanimous_combos']}/{metrics['total_combos']} pattern+field decisions)",
        f"- Executive summary changed: {metrics['exec_summary_changed_rate']:.0%} of runs",
        f"- Coaching themes changed: {metrics['coaching_themes_changed_rate']:.0%} of runs",
        f"- Focus message changed: {metrics['focus_message_changed_rate']:.0%} of runs",
        f"- Changes/run: min={metrics['changes_per_run']['min']}, "
        f"max={metrics['changes_per_run']['max']}, "
        f"mean={metrics['changes_per_run']['mean']:.1f}",
        "",
    ]

    # ── Per-pattern actions table ──
    lines.append("## Per-Pattern Action Distribution")
    lines.append("")
    lines.append("| Pattern | Notes:sup | Notes:rew | Notes:pass | CNote:sup | CNote:rew | CNote:pass |")
    lines.append("|---------|-----------|-----------|------------|-----------|-----------|------------|")
    for pid in metrics["evaluable_patterns"]:
        pdata = metrics["per_pattern"].get(pid, {})
        n = pdata.get("notes", {})
        c = pdata.get("coaching_note", {})
        lines.append(
            f"| {pid} | {n.get('suppress', 0)} | {n.get('rewrite', 0)} | {n.get('pass', 0)} "
            f"| {c.get('suppress', 0)} | {c.get('rewrite', 0)} | {c.get('pass', 0)} |"
        )
    lines.append("")

    # ── Flip patterns ──
    if metrics["flip_patterns"]:
        lines.append("## Flip Patterns (mixed decisions)")
        lines.append("")
        lines.append("| Pattern | Field | Distribution |")
        lines.append("|---------|-------|-------------|")
        for fp in metrics["flip_patterns"]:
            dist_str = ", ".join(f"{k}={v}" for k, v in sorted(fp["distribution"].items()))
            lines.append(f"| {fp['pattern_id']} | {fp['field']} | {dist_str} |")
        lines.append("")
    else:
        lines.append("## Flip Patterns")
        lines.append("")
        lines.append("None — all decisions were unanimous.")
        lines.append("")

    # ── OE removal agreement ──
    oe = metrics["oe_removals"]
    if oe["items"]:
        lines.append("## OE Removal Agreement")
        lines.append("")
        lines.append(f"Overall agreement rate: {oe['agreement_rate']:.1%}")
        lines.append("")
        lines.append("| Pattern | OE Index | Flagged In |")
        lines.append("|---------|----------|-----------|")
        for item in oe["items"]:
            lines.append(
                f"| {item['pattern_id']} | {item['oe_index']} "
                f"| {item['flagged_in']}/{metrics['n_valid']} |"
            )
        lines.append("")
    else:
        lines.append("## OE Removals")
        lines.append("")
        lines.append("No OE removals in any run.")
        lines.append("")

    return "\n".join(lines)


def _run_editor_mode(
    args: argparse.Namespace,
    parsed_output: dict,
    evaluable: set[str],
    model: str,
    results_dir: Path,
    timestamp: str,
) -> None:
    """Execute editor variance mode."""
    logger.info("=== Editor Variance Mode ===")
    logger.info("Input: %s", args.input.name)
    logger.info("Transcript: %s", args.transcript.name)
    logger.info("Runs: %d | Model: %s", args.runs, model)

    # Load transcript turns for editor
    transcript_turns = _load_transcript_turns(args.transcript)
    logger.info("Loaded %d transcript turns", len(transcript_turns))

    # Build experiment context (default no-experiment)
    memory = MemoryBlock()
    experiment_context = build_experiment_context(memory, parsed_output)

    # Run editor N times in parallel
    runs: list[dict] = [{}] * args.runs
    max_workers = min(2 if is_anthropic_model(model) else args.runs, 10)
    logger.info("Running %d editor calls (max_workers=%d) ...", args.runs, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_editor_once, i, parsed_output, transcript_turns,
                experiment_context, model,
            )
            for i in range(args.runs)
        ]
        for future in as_completed(futures):
            idx, result = future.result()
            runs[idx] = result

    # Save individual outputs
    for i, r in enumerate(runs):
        if "error" not in r:
            save_json(r["editor_delta"], results_dir / f"editor_var_{i+1:03d}_{timestamp}.json")

    # Compute metrics and report
    metrics = _compute_editor_metrics(runs, evaluable)
    report = _format_editor_report(metrics, args.input.stem, model)

    save_json(metrics, results_dir / f"variance_report_editor_{timestamp}.json")
    save_report(report, results_dir / f"variance_report_editor_{timestamp}.md")

    logger.info("Results saved to %s", results_dir)
    print("\n" + report)


# ── Judge variance ───────────────────────────────────────────────────────────


def _run_judge_once(
    i: int,
    transcript_data: dict,
    parsed_json: dict,
    model: str | None,
) -> tuple[int, dict]:
    """Run the judge once and return (index, judge_output)."""
    t0 = time.time()
    try:
        result = judge_analysis(transcript_data, parsed_json, model=model)
        elapsed = time.time() - t0
        logger.info("  Judge run %d: %.1fs", i + 1, elapsed)
        result["_elapsed_sec"] = round(elapsed, 1)
        return i, result
    except Exception as e:
        logger.error("  Judge run %d failed: %s", i + 1, e)
        return i, {"error": str(e)}


def _compute_judge_metrics(
    runs: list[dict],
    coached_patterns: set[str],
) -> dict:
    """Compute consistency metrics across N judge runs."""
    n_runs = len(runs)
    valid_runs = [r for r in runs if "error" not in r]
    n_valid = len(valid_runs)

    if n_valid == 0:
        return {"n_runs": n_runs, "n_valid": 0, "error": "All runs failed"}

    ordered_coached = sorted(coached_patterns & set(PATTERN_ORDER), key=PATTERN_ORDER.index)

    # ── Per-pattern rating distribution ──
    per_pattern_ratings: dict[str, Counter] = {pid: Counter() for pid in ordered_coached}
    for r in valid_runs:
        items = r.get("coaching_insight_quality", {}).get("items", [])
        rated_pids = set()
        for item in items:
            pid = item.get("pattern_id")
            if pid in coached_patterns:
                per_pattern_ratings[pid][item.get("rating", "unknown")] += 1
                rated_pids.add(pid)
        # Patterns not rated in this run (judge skipped them) — count as missing
        for pid in ordered_coached:
            if pid not in rated_pids:
                per_pattern_ratings[pid]["_not_rated"] += 1

    # ── Unanimous rate ──
    unanimous = 0
    flip_patterns = []
    for pid in ordered_coached:
        counts = per_pattern_ratings[pid]
        # Filter out _not_rated for unanimity check
        rating_counts = {k: v for k, v in counts.items() if k != "_not_rated"}
        if len(rating_counts) == 1:
            unanimous += 1
        elif len(rating_counts) > 1:
            flip_patterns.append({"pattern_id": pid, "ratings": dict(counts)})
    total_patterns = len(ordered_coached)
    unanimous_rate = unanimous / total_patterns if total_patterns > 0 else 1.0

    # ── Aggregate rating percentages per run ──
    per_run_pcts: dict[str, list[float]] = {
        "insightful": [], "adequate": [], "pedantic": [], "wrong": [],
    }
    for r in valid_runs:
        items = r.get("coaching_insight_quality", {}).get("items", [])
        run_counts: Counter[str] = Counter()
        for item in items:
            if item.get("pattern_id") in coached_patterns:
                run_counts[item.get("rating", "unknown")] += 1
        total = sum(run_counts.values()) or 1
        for rating in per_run_pcts:
            per_run_pcts[rating].append(run_counts.get(rating, 0) / total)

    aggregate_pcts = {}
    for rating, values in per_run_pcts.items():
        aggregate_pcts[rating] = {
            "mean": round(statistics.mean(values), 4) if values else 0,
            "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
        }

    # ── Coaching value distribution ──
    coaching_value: Counter[str] = Counter()
    for r in valid_runs:
        val = r.get("executive_coach_gut_check", {}).get("overall_coaching_value", "unknown")
        coaching_value[val] += 1

    # ── Would approve for delivery ──
    approve_counts: Counter[str] = Counter()
    for r in valid_runs:
        approved = r.get("executive_coach_gut_check", {}).get("would_approve_for_delivery")
        approve_counts[str(approved)] += 1
    approve_true = approve_counts.get("True", 0)
    approve_rate = max(approve_true, n_valid - approve_true) / n_valid if n_valid > 0 else 1.0

    # ── Pattern alignment consistency ──
    alignment: dict[str, dict[str, list[bool]]] = {
        pid: {"fits_pattern": [], "stretching_to_fill": []}
        for pid in ordered_coached
    }
    for r in valid_runs:
        items = r.get("coaching_pattern_alignment", {}).get("items", [])
        for item in items:
            pid = item.get("pattern_id")
            if pid in alignment:
                if "fits_pattern" in item:
                    alignment[pid]["fits_pattern"].append(bool(item["fits_pattern"]))
                if "stretching_to_fill" in item:
                    alignment[pid]["stretching_to_fill"].append(bool(item["stretching_to_fill"]))

    alignment_summary = {}
    for pid in ordered_coached:
        a = alignment[pid]
        fits = a["fits_pattern"]
        stretch = a["stretching_to_fill"]
        fits_agree = (max(Counter(fits).values()) / len(fits)) if fits else 1.0
        stretch_agree = (max(Counter(stretch).values()) / len(stretch)) if stretch else 1.0
        alignment_summary[pid] = {
            "fits_pattern_agree": round(fits_agree, 4),
            "stretching_to_fill_agree": round(stretch_agree, 4),
            "fits_pattern_values": dict(Counter(fits)),
            "stretching_to_fill_values": dict(Counter(stretch)),
        }

    return {
        "n_runs": n_runs,
        "n_valid": n_valid,
        "coached_patterns": ordered_coached,
        "per_pattern_ratings": {pid: dict(c) for pid, c in per_pattern_ratings.items()},
        "unanimous_rate": round(unanimous_rate, 4),
        "unanimous_count": unanimous,
        "total_patterns": total_patterns,
        "flip_patterns": flip_patterns,
        "aggregate_pcts": aggregate_pcts,
        "coaching_value": dict(coaching_value),
        "would_approve": {
            "counts": dict(approve_counts),
            "agreement_rate": round(approve_rate, 4),
        },
        "pattern_alignment": alignment_summary,
    }


def _format_judge_report(metrics: dict, input_stem: str, model: str) -> str:
    """Format judge variance metrics as a markdown report."""
    lines = [
        "# Judge Variance Report",
        "",
        f"**Input**: `{input_stem}`  ",
        f"**Model**: `{model}`  ",
        f"**Runs**: {metrics['n_valid']}/{metrics['n_runs']} valid  ",
        f"**Coached patterns evaluated**: {len(metrics['coached_patterns'])}",
        "",
        "---",
        "",
        "## Overall Consistency",
        "",
        f"- **Rating unanimous rate**: {metrics['unanimous_rate']:.1%} "
        f"({metrics['unanimous_count']}/{metrics['total_patterns']} patterns)",
        f"- Would approve for delivery: {metrics['would_approve']['agreement_rate']:.0%} agreement "
        f"({metrics['would_approve']['counts']})",
        f"- Coaching value: {metrics['coaching_value']}",
        "",
    ]

    # ── Per-pattern ratings table ──
    lines.append("## Per-Pattern Rating Distribution")
    lines.append("")
    lines.append("| Pattern | Insightful | Adequate | Pedantic | Wrong |")
    lines.append("|---------|-----------|----------|----------|-------|")
    for pid in metrics["coached_patterns"]:
        r = metrics["per_pattern_ratings"].get(pid, {})
        lines.append(
            f"| {pid} | {r.get('insightful', 0)} | {r.get('adequate', 0)} "
            f"| {r.get('pedantic', 0)} | {r.get('wrong', 0)} |"
        )
    lines.append("")

    # ── Flip patterns ──
    if metrics["flip_patterns"]:
        lines.append("## Flip Patterns (mixed ratings)")
        lines.append("")
        lines.append("| Pattern | Ratings |")
        lines.append("|---------|---------|")
        for fp in metrics["flip_patterns"]:
            ratings_str = ", ".join(
                f"{k}={v}" for k, v in sorted(fp["ratings"].items()) if k != "_not_rated"
            )
            lines.append(f"| {fp['pattern_id']} | {ratings_str} |")
        lines.append("")
    else:
        lines.append("## Flip Patterns")
        lines.append("")
        lines.append("None — all ratings were unanimous.")
        lines.append("")

    # ── Aggregate rating percentages ──
    agg = metrics["aggregate_pcts"]
    lines.append("## Aggregate Rating Distribution (mean +/- stdev across runs)")
    lines.append("")
    for rating in ("insightful", "adequate", "pedantic", "wrong"):
        vals = agg.get(rating, {})
        lines.append(f"- **{rating.title()}**: {vals.get('mean', 0):.1%} +/- {vals.get('stdev', 0):.1%}")
    lines.append("")

    # ── Pattern alignment consistency ──
    lines.append("## Pattern Alignment Consistency")
    lines.append("")
    lines.append("| Pattern | fits_pattern agree | stretching_to_fill agree |")
    lines.append("|---------|-------------------|-------------------------|")
    for pid in metrics["coached_patterns"]:
        a = metrics["pattern_alignment"].get(pid, {})
        lines.append(
            f"| {pid} | {a.get('fits_pattern_agree', 1.0):.0%} "
            f"| {a.get('stretching_to_fill_agree', 1.0):.0%} |"
        )
    lines.append("")

    return "\n".join(lines)


def _run_judge_mode(
    args: argparse.Namespace,
    parsed_output: dict,
    evaluable: set[str],
    model: str,
    results_dir: Path,
    timestamp: str,
) -> None:
    """Execute judge variance mode."""
    coached = _get_coached_patterns(parsed_output, evaluable)
    logger.info("=== Judge Variance Mode ===")
    logger.info("Input: %s", args.input.name)
    logger.info("Transcript: %s", args.transcript.name)
    logger.info("Runs: %d | Model: %s", args.runs, model)
    logger.info("Coached patterns: %d", len(coached))

    # Load transcript for judge
    transcript_data = load_transcript_for_judge(args.transcript)
    logger.info("Loaded transcript: %s (%d turns)", transcript_data["source_id"], len(transcript_data["turns"]))

    # Run judge N times in parallel
    runs: list[dict] = [{}] * args.runs
    max_workers = min(2 if is_anthropic_model(model) else args.runs, 10)
    logger.info("Running %d judge calls (max_workers=%d) ...", args.runs, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_run_judge_once, i, transcript_data, parsed_output, model)
            for i in range(args.runs)
        ]
        for future in as_completed(futures):
            idx, result = future.result()
            runs[idx] = result

    # Save individual outputs
    prefix = getattr(args, "output_prefix", None) or "judge"
    for i, r in enumerate(runs):
        if "error" not in r:
            save_json(r, results_dir / f"{prefix}_var_{i+1:03d}_{timestamp}.json")

    # Compute metrics and report
    metrics = _compute_judge_metrics(runs, coached)
    report = _format_judge_report(metrics, args.input.stem, model)

    save_json(metrics, results_dir / f"variance_report_{prefix}_{timestamp}.json")
    save_report(report, results_dir / f"variance_report_{prefix}_{timestamp}.md")

    logger.info("Results saved to %s", results_dir)
    print("\n" + report)


# ── Propagation test ─────────────────────────────────────────────────────────


def _compute_propagation_metrics(
    judge_results: list[dict],
    coached_patterns: set[str],
    editor_actions: list[dict],
) -> dict:
    """Compare judge ratings across editor-variant inputs.

    Each judge_result was produced from a different editor variant of the same
    pre-editor input. This measures whether editor flip decisions propagate to
    different judge ratings.
    """
    n = len(judge_results)
    valid = [(i, r) for i, r in enumerate(judge_results) if "error" not in r]
    n_valid = len(valid)

    if n_valid == 0:
        return {"n_variants": n, "n_valid": 0, "error": "All judge calls failed"}

    ordered_coached = sorted(coached_patterns & set(PATTERN_ORDER), key=PATTERN_ORDER.index)

    # ── Per-pattern rating distribution across variants ──
    per_pattern_ratings: dict[str, Counter] = {pid: Counter() for pid in ordered_coached}
    per_variant_ratings: list[dict[str, str]] = []

    for _, r in valid:
        variant_ratings: dict[str, str] = {}
        for item in r.get("coaching_insight_quality", {}).get("items", []):
            pid = item.get("pattern_id")
            if pid in coached_patterns:
                per_pattern_ratings[pid][item.get("rating", "unknown")] += 1
                variant_ratings[pid] = item.get("rating", "unknown")
        per_variant_ratings.append(variant_ratings)

    # ── Unanimous rate ──
    unanimous = 0
    flip_patterns = []
    for pid in ordered_coached:
        counts = per_pattern_ratings[pid]
        if len(counts) == 1:
            unanimous += 1
        elif len(counts) > 1:
            flip_patterns.append({"pattern_id": pid, "ratings": dict(counts)})
    total_patterns = len(ordered_coached)
    unanimous_rate = unanimous / total_patterns if total_patterns > 0 else 1.0

    # ── Correlate editor actions with judge rating changes ──
    # For each flip pattern, show what the editor did differently across variants
    flip_details = []
    for fp in flip_patterns:
        pid = fp["pattern_id"]
        variant_detail = []
        for idx, (orig_i, _) in enumerate(valid):
            actions = editor_actions[orig_i] if orig_i < len(editor_actions) else {}
            edits = actions.get("pattern_coaching_edits", {}).get(pid, {})
            notes_action = "pass"
            cnote_action = "pass"
            if edits.get("notes") == "SUPPRESS":
                notes_action = "suppress"
            elif edits.get("notes") not in (None, _ABSENT) and edits.get("notes") is not None:
                notes_action = "rewrite"
            if edits.get("coaching_note") == "SUPPRESS":
                cnote_action = "suppress"
            elif edits.get("coaching_note") not in (None, _ABSENT) and edits.get("coaching_note") is not None:
                cnote_action = "rewrite"

            variant_detail.append({
                "variant": orig_i + 1,
                "editor_notes": notes_action,
                "editor_cnote": cnote_action,
                "judge_rating": per_variant_ratings[idx].get(pid, "n/a"),
            })
        flip_details.append({"pattern_id": pid, "variants": variant_detail})

    # ── Aggregate rating percentages ──
    per_variant_pcts: dict[str, list[float]] = {
        "insightful": [], "adequate": [], "pedantic": [], "wrong": [],
    }
    for vr in per_variant_ratings:
        counts: Counter[str] = Counter(vr.values())
        total = sum(counts.values()) or 1
        for rating in per_variant_pcts:
            per_variant_pcts[rating].append(counts.get(rating, 0) / total)

    aggregate_pcts = {}
    for rating, values in per_variant_pcts.items():
        aggregate_pcts[rating] = {
            "mean": round(statistics.mean(values), 4) if values else 0,
            "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
        }

    # ── Coaching value + approve ──
    coaching_value: Counter[str] = Counter()
    approve_counts: Counter[str] = Counter()
    for _, r in valid:
        val = r.get("executive_coach_gut_check", {}).get("overall_coaching_value", "unknown")
        coaching_value[val] += 1
        approved = r.get("executive_coach_gut_check", {}).get("would_approve_for_delivery")
        approve_counts[str(approved)] += 1

    return {
        "n_variants": n,
        "n_valid": n_valid,
        "coached_patterns": ordered_coached,
        "per_pattern_ratings": {pid: dict(c) for pid, c in per_pattern_ratings.items()},
        "unanimous_rate": round(unanimous_rate, 4),
        "unanimous_count": unanimous,
        "total_patterns": total_patterns,
        "flip_patterns": flip_patterns,
        "flip_details": flip_details,
        "aggregate_pcts": aggregate_pcts,
        "coaching_value": dict(coaching_value),
        "would_approve": dict(approve_counts),
    }


def _format_propagation_report(metrics: dict, input_stem: str, model: str) -> str:
    """Format propagation test metrics as a markdown report."""
    lines = [
        "# Editor-to-Judge Propagation Report",
        "",
        f"**Pre-editor input**: `{input_stem}`  ",
        f"**Model**: `{model}`  ",
        f"**Editor variants judged**: {metrics['n_valid']}/{metrics['n_variants']}  ",
        f"**Coached patterns**: {len(metrics['coached_patterns'])}",
        "",
        "Each variant = same 1st-pass output, different editor run, judged once.",
        "Measures whether editor flip decisions change judge ratings.",
        "",
        "**Question answered**: When the editor flips on a borderline pattern,",
        "does the judge notice?",
        "",
        "---",
        "",
        "## Overall",
        "",
        f"- **Rating unanimous rate**: {metrics['unanimous_rate']:.1%} "
        f"({metrics['unanimous_count']}/{metrics['total_patterns']} patterns same across all variants)",
        f"- Coaching value: {metrics['coaching_value']}",
        f"- Would approve: {metrics['would_approve']}",
        "",
    ]

    # ── Per-pattern ratings ──
    lines.append("## Per-Pattern Rating Distribution (across editor variants)")
    lines.append("")
    lines.append("| Pattern | Insightful | Adequate | Pedantic | Wrong |")
    lines.append("|---------|-----------|----------|----------|-------|")
    for pid in metrics["coached_patterns"]:
        r = metrics["per_pattern_ratings"].get(pid, {})
        lines.append(
            f"| {pid} | {r.get('insightful', 0)} | {r.get('adequate', 0)} "
            f"| {r.get('pedantic', 0)} | {r.get('wrong', 0)} |"
        )
    lines.append("")

    # ── Flip details (editor action -> judge rating) ──
    if metrics["flip_details"]:
        lines.append("## Propagation Details (editor action -> judge rating)")
        lines.append("")
        for fd in metrics["flip_details"]:
            lines.append(f"### {fd['pattern_id']}")
            lines.append("")
            lines.append("| Variant | Editor notes | Editor cnote | Judge rating |")
            lines.append("|---------|-------------|-------------|-------------|")
            for v in fd["variants"]:
                lines.append(
                    f"| {v['variant']} | {v['editor_notes']} | {v['editor_cnote']} "
                    f"| {v['judge_rating']} |"
                )
            lines.append("")
    else:
        lines.append("## Propagation Details")
        lines.append("")
        lines.append("No rating changes across editor variants — editor variance does not propagate.")
        lines.append("")

    # ── Aggregate ──
    agg = metrics["aggregate_pcts"]
    lines.append("## Aggregate (mean +/- stdev across variants)")
    lines.append("")
    for rating in ("insightful", "adequate", "pedantic", "wrong"):
        vals = agg.get(rating, {})
        lines.append(f"- **{rating.title()}**: {vals.get('mean', 0):.1%} +/- {vals.get('stdev', 0):.1%}")
    lines.append("")

    return "\n".join(lines)


def _run_propagation_mode(
    args: argparse.Namespace,
    parsed_output: dict,
    evaluable: set[str],
    model: str,
    results_dir: Path,
    timestamp: str,
) -> None:
    """Merge each editor delta with pre-editor input, judge each variant once."""
    logger.info("=== Propagation Mode ===")
    logger.info("Pre-editor input: %s", args.input.name)
    logger.info("Editor dir: %s", args.editor_dir)

    # Load editor delta files
    editor_dir = Path(args.editor_dir)
    delta_files = sorted(editor_dir.glob("editor_var_*.json"))
    if not delta_files:
        logger.error("No editor_var_*.json files found in %s", editor_dir)
        return
    logger.info("Found %d editor delta files", len(delta_files))

    # Load all deltas
    deltas = []
    for f in delta_files:
        deltas.append(_load_input_json(f))

    # Merge each delta with pre-editor input to create post-editor variants
    merged_variants = []
    for i, delta in enumerate(deltas):
        merged, changelog = merge_editor_output(parsed_output, delta)
        merged_variants.append(merged)
        logger.info("  Variant %d: %d changes", i + 1, len(changelog))

    # Determine coached patterns from each merged variant (may differ!)
    # Use the union to track all, but report per-variant
    all_coached = set()
    for mv in merged_variants:
        all_coached |= _get_coached_patterns(mv, evaluable)

    logger.info("Coached patterns (union across variants): %d", len(all_coached))

    # Load transcript for judge
    transcript_data = load_transcript_for_judge(args.transcript)

    # Run judge once per merged variant, in parallel
    n = len(merged_variants)
    judge_results: list[dict] = [{}] * n
    max_workers = min(2 if is_anthropic_model(model) else n, 10)
    logger.info("Running %d judge calls (max_workers=%d) ...", n, max_workers)

    def _judge_one(i: int) -> tuple[int, dict]:
        return _run_judge_once(i, transcript_data, merged_variants[i], model)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_judge_one, i) for i in range(n)]
        for future in as_completed(futures):
            idx, result = future.result()
            judge_results[idx] = result

    # Save individual judge outputs
    for i, r in enumerate(judge_results):
        if "error" not in r:
            save_json(r, results_dir / f"prop_judge_{i+1:03d}_{timestamp}.json")

    # Compute metrics
    metrics = _compute_propagation_metrics(judge_results, all_coached, deltas)
    report = _format_propagation_report(metrics, args.input.stem, model)

    save_json(metrics, results_dir / f"variance_report_propagation_{timestamp}.json")
    save_report(report, results_dir / f"variance_report_propagation_{timestamp}.md")

    logger.info("Results saved to %s", results_dir)
    print("\n" + report)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Variance eval: test editor or judge consistency in isolation.",
    )
    parser.add_argument(
        "--mode", choices=["editor", "judge", "propagation"], required=True,
        help="editor = run editor N times on fixed input; "
             "judge = run judge N times on fixed input; "
             "propagation = merge editor variants + judge each once",
    )
    parser.add_argument(
        "--input", type=Path, required=True,
        help="Path to a run_*.json file (pre-editor for editor/propagation, post-editor for judge)",
    )
    parser.add_argument(
        "--transcript", type=Path, required=True,
        help="Path to transcript file (.txt, .vtt, etc.)",
    )
    parser.add_argument("--runs", type=int, default=10, help="Number of runs (default: 10)")
    parser.add_argument("--model", type=str, default=None, help="Model override")
    parser.add_argument(
        "--editor-dir", type=Path, default=None,
        help="(propagation mode) Directory containing editor_var_*.json files",
    )
    parser.add_argument(
        "--output-prefix", type=str, default=None,
        help="(judge mode) Prefix for output files, e.g. 'judge_pre' for pre-editor inputs",
    )
    args = parser.parse_args()

    model = args.model or OPENAI_MODEL_DEFAULT
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Output directory: results/variance_tests/{transcript_stem}/
    results_dir = _RESULTS_DIR / args.transcript.stem
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load input
    parsed_output = _load_input_json(args.input)
    evaluable = _get_evaluable_patterns(parsed_output)
    logger.info("Loaded input: %d patterns (%d evaluable)", len(parsed_output.get("pattern_snapshot", [])), len(evaluable))

    if args.mode == "editor":
        _run_editor_mode(args, parsed_output, evaluable, model, results_dir, timestamp)
    elif args.mode == "judge":
        _run_judge_mode(args, parsed_output, evaluable, model, results_dir, timestamp)
    elif args.mode == "propagation":
        if not args.editor_dir:
            parser.error("--editor-dir is required for propagation mode")
        _run_propagation_mode(args, parsed_output, evaluable, model, results_dir, timestamp)


if __name__ == "__main__":
    main()
