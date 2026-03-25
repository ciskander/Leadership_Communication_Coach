"""
replay_eval.py — Layer 1: Score Stability & Discriminant Validity.

Two modes:
  --mode repeat   Run one transcript N times, measure intra-transcript IQR.
  --mode compare  Run multiple transcripts (optionally N times each),
                  measure inter-transcript distribution per pattern.

Usage:
  python -m backend.evals.replay_eval --mode repeat \
    --transcript backend/evals/transcripts/t001_m000223 --runs 5

  python -m backend.evals.replay_eval --mode compare \
    --transcripts-dir backend/evals/transcripts --runs 3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so imports work when run as module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.config import OPENAI_MODEL_DEFAULT, OPENAI_MAX_TOKENS, PATTERN_ORDER
from backend.core.gate1_validator import validate as gate1_validate
from backend.core.llm_client import call_llm
from backend.core.models import MemoryBlock, ParsedTranscript, Turn, TranscriptMetadata
from backend.core.openai_client import load_system_prompt
from backend.core.prompt_builder import build_developer_message, build_single_meeting_prompt
from backend.evals.report import (
    compute_pattern_stats,
    compute_int_stats,
    format_intra_transcript_report,
    format_inter_transcript_report,
    save_report,
    save_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────

_RESULTS_DIR = Path(__file__).parent / "results"


# ── Transcript loading ───────────────────────────────────────────────────────

def load_transcript_case(case_dir: Path) -> tuple[dict, ParsedTranscript, MemoryBlock]:
    """Load a transcript case from a directory containing transcript.json and metadata.json."""
    meta_path = case_dir / "metadata.json"
    transcript_path = case_dir / "transcript.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json not found in {case_dir}")
    if not transcript_path.exists():
        raise FileNotFoundError(f"transcript.json not found in {case_dir}")

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    transcript_data = json.loads(transcript_path.read_text(encoding="utf-8"))

    turns = [Turn(**t) for t in transcript_data["turns"]]
    parsed_transcript = ParsedTranscript(
        source_id=transcript_data["source_id"],
        turns=turns,
        speaker_labels=list({t.speaker_label for t in turns}),
        metadata=TranscriptMetadata(
            original_format="json",
            turn_count=len(turns),
            word_count=sum(len(t.text.split()) for t in turns),
        ),
    )

    mem_data = metadata.get("memory", {})
    memory = MemoryBlock(
        baseline_profile=mem_data.get("baseline_profile"),
        recent_pattern_snapshots=mem_data.get("recent_pattern_snapshots", []),
        active_experiment=mem_data.get("active_experiment"),
    )

    return metadata, parsed_transcript, memory


# ── Single analysis run ──────────────────────────────────────────────────────

def run_single_analysis(
    metadata: dict,
    parsed_transcript: ParsedTranscript,
    memory: MemoryBlock,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Run one analysis through the full pipeline (prompt → LLM → gate1).

    Returns dict with: raw_text, parsed_json, gate1_passed, gate1_issues,
    pattern_scores, pattern_opp_counts, pattern_statuses.
    """
    model = model or OPENAI_MODEL_DEFAULT
    max_tokens = max_tokens or OPENAI_MAX_TOKENS

    # Build prompt
    prompt_payload = build_single_meeting_prompt(
        meeting_id=metadata["meeting_id"],
        meeting_type=metadata["meeting_type"],
        target_role=metadata["target_role"],
        meeting_date=metadata["meeting_date"],
        target_speaker_name=metadata["target_speaker_name"],
        target_speaker_label=metadata["target_speaker_label"],
        parsed_transcript=parsed_transcript,
        memory=memory,
    )

    # Load system prompt and developer message
    sys_prompt = load_system_prompt()
    dev_message = build_developer_message()

    # Call LLM
    t0 = time.time()
    response = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=model,
        max_tokens=max_tokens,
    )
    elapsed = time.time() - t0

    # Gate1 validation
    gate1_result = gate1_validate(response.raw_text)

    # Extract pattern-level data
    parsed = response.parsed
    pattern_scores: dict[str, float | None] = {}
    pattern_opp_counts: dict[str, int | None] = {}
    pattern_statuses: dict[str, str] = {}
    pattern_oe_counts: dict[str, int] = defaultdict(int)

    for snap in parsed.get("pattern_snapshot", []):
        pid = snap.get("pattern_id")
        if pid:
            pattern_scores[pid] = snap.get("score")
            pattern_opp_counts[pid] = snap.get("opportunity_count")
            pattern_statuses[pid] = snap.get("evaluable_status", "unknown")

    # Count OEs per pattern
    for oe in parsed.get("opportunity_events", []):
        pid = oe.get("pattern_id")
        if pid and oe.get("count_decision") == "counted":
            pattern_oe_counts[pid] += 1

    return {
        "raw_text": response.raw_text,
        "parsed_json": parsed,
        "model": response.model,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "elapsed_sec": round(elapsed, 1),
        "gate1_passed": gate1_result.passed,
        "gate1_issues": [
            {"severity": i.severity, "code": i.issue_code, "path": i.path, "message": i.message}
            for i in gate1_result.issues
        ],
        "pattern_scores": dict(pattern_scores),
        "pattern_opp_counts": dict(pattern_opp_counts),
        "pattern_statuses": dict(pattern_statuses),
        "pattern_oe_counts": dict(pattern_oe_counts),
    }


# ── Repeat mode ──────────────────────────────────────────────────────────────

def run_repeat(
    case_dir: Path,
    n_runs: int,
    model: str | None = None,
) -> dict[str, Any]:
    """Run one transcript N times and compute intra-transcript stats."""
    metadata, parsed_transcript, memory = load_transcript_case(case_dir)
    transcript_id = case_dir.name

    logger.info("=== Repeat mode: %s x %d runs ===", transcript_id, n_runs)

    runs: list[dict] = []
    for i in range(n_runs):
        logger.info("Run %d/%d for %s ...", i + 1, n_runs, transcript_id)
        try:
            result = run_single_analysis(metadata, parsed_transcript, memory, model=model)
            runs.append(result)
            logger.info(
                "  Gate1: %s | Tokens: %d | Time: %ss",
                "PASS" if result["gate1_passed"] else "FAIL",
                result["prompt_tokens"] + result["completion_tokens"],
                result["elapsed_sec"],
            )
        except Exception as e:
            logger.error("  Run %d failed: %s", i + 1, e)
            runs.append({"error": str(e), "gate1_passed": False})

    # Compute stats
    gate1_passes = sum(1 for r in runs if r.get("gate1_passed"))
    gate1_pass_rate = gate1_passes / len(runs) if runs else 0

    pattern_results: dict[str, dict] = {}
    for pid in PATTERN_ORDER:
        scores = [r["pattern_scores"].get(pid) for r in runs if "pattern_scores" in r]
        opp_counts = [r["pattern_opp_counts"].get(pid) for r in runs if "pattern_opp_counts" in r]
        oe_counts = [r["pattern_oe_counts"].get(pid, 0) for r in runs if "pattern_oe_counts" in r]
        statuses = [r["pattern_statuses"].get(pid, "unknown") for r in runs if "pattern_statuses" in r]

        status_counts: dict[str, int] = defaultdict(int)
        for s in statuses:
            status_counts[s] += 1

        pattern_results[pid] = {
            "score": compute_pattern_stats(scores),
            "opportunity_count": compute_int_stats(opp_counts),
            "oe_count": compute_int_stats(oe_counts),
            "status_distribution": dict(status_counts),
        }

    # Save results
    results_dir = _RESULTS_DIR / transcript_id
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for i, run_data in enumerate(runs):
        if "parsed_json" in run_data:
            save_json(run_data["parsed_json"], results_dir / f"run_{i+1:03d}_{timestamp}.json")

    report_data = {
        "transcript_id": transcript_id,
        "n_runs": n_runs,
        "gate1_pass_rate": gate1_pass_rate,
        "model": runs[0].get("model", "unknown") if runs else "unknown",
        "timestamp": timestamp,
        "pattern_results": pattern_results,
    }
    save_json(report_data, results_dir / f"repeat_report_{timestamp}.json")

    # Markdown report
    md = format_intra_transcript_report(transcript_id, n_runs, gate1_pass_rate, pattern_results)
    save_report(md, results_dir / f"repeat_report_{timestamp}.md")

    return report_data


# ── Compare mode ─────────────────────────────────────────────────────────────

def run_compare(
    transcripts_dir: Path,
    n_runs: int,
    model: str | None = None,
) -> dict[str, Any]:
    """Run multiple transcripts (optionally N times each) and compute cross-transcript stats."""
    case_dirs = sorted([
        d for d in transcripts_dir.iterdir()
        if d.is_dir() and (d / "transcript.json").exists()
    ])

    if len(case_dirs) < 2:
        logger.error("Compare mode requires at least 2 transcripts. Found %d.", len(case_dirs))
        sys.exit(1)

    logger.info("=== Compare mode: %d transcripts x %d runs ===", len(case_dirs), n_runs)

    # Run repeat for each transcript
    per_transcript: dict[str, dict] = {}
    for case_dir in case_dirs:
        report = run_repeat(case_dir, n_runs, model=model)
        per_transcript[case_dir.name] = report["pattern_results"]

    # Compute cross-transcript stats
    transcript_ids = [d.name for d in case_dirs]
    cross_transcript: dict[str, dict] = {}

    for pid in PATTERN_ORDER:
        # Collect mean scores across transcripts
        means = []
        intra_iqrs = []
        for tid in transcript_ids:
            tr = per_transcript.get(tid, {}).get(pid, {}).get("score", {})
            if tr.get("mean") is not None:
                means.append(tr["mean"])
            if tr.get("iqr") is not None:
                intra_iqrs.append(tr["iqr"])

        cross_stats = compute_pattern_stats(means)
        mean_intra_iqr = (
            round(sum(intra_iqrs) / len(intra_iqrs), 4) if intra_iqrs else None
        )

        # Signal-to-noise: cross_iqr / mean_intra_iqr
        signal_to_noise = None
        if cross_stats["iqr"] is not None and mean_intra_iqr and mean_intra_iqr > 0:
            signal_to_noise = round(cross_stats["iqr"] / mean_intra_iqr, 2)

        cross_transcript[pid] = {
            "cross_iqr": cross_stats["iqr"],
            "cross_stdev": cross_stats["stdev"],
            "cross_mean": cross_stats["mean"],
            "mean_intra_iqr": mean_intra_iqr,
            "signal_to_noise": signal_to_noise,
        }

    # Save report
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    report_data = {
        "transcript_ids": transcript_ids,
        "n_runs_per_transcript": n_runs,
        "timestamp": timestamp,
        "per_transcript": per_transcript,
        "cross_transcript": cross_transcript,
    }
    save_json(report_data, _RESULTS_DIR / f"compare_report_{timestamp}.json")

    md = format_inter_transcript_report(transcript_ids, per_transcript, cross_transcript)
    save_report(md, _RESULTS_DIR / f"compare_report_{timestamp}.md")

    return report_data


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Layer 1: Score Stability & Discriminant Validity")
    parser.add_argument("--mode", choices=["repeat", "compare"], required=True)
    parser.add_argument("--transcript", type=Path, help="Path to transcript case dir (repeat mode)")
    parser.add_argument("--transcripts-dir", type=Path, help="Path to transcripts dir (compare mode)")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs per transcript")
    parser.add_argument("--model", type=str, default=None, help="Model override")
    args = parser.parse_args()

    if args.mode == "repeat":
        if not args.transcript:
            parser.error("--transcript is required for repeat mode")
        run_repeat(args.transcript, args.runs, model=args.model)

    elif args.mode == "compare":
        if not args.transcripts_dir:
            parser.error("--transcripts-dir is required for compare mode")
        run_compare(args.transcripts_dir, args.runs, model=args.model)


if __name__ == "__main__":
    main()
