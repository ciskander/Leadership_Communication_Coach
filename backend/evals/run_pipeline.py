"""
run_pipeline.py — Full eval pipeline orchestrator.

Runs the complete eval sequence in one command:
  1. Replay (1st pass analysis) — all meetings in parallel
  2. Compare report (offline, no LLM calls) — SNR, IQR, OE stability
  3. Editor (2nd pass) — all runs in parallel
  4. Judge (pre-editor + post-editor) — all runs in parallel
  5. Synthesis reports with baseline comparisons

Usage:
  python -m backend.evals.run_pipeline \\
    --phase Phase_L3 \\
    --transcripts-dir backend/evals/transcripts \\
    --runs 10 \\
    --editor \\
    --judge \\
    --baseline-dir backend/evals/results/Phase_I2 \\
    --post-editor-baseline-dir backend/evals/results/Phase_J2 \\
    --tpm-limit 4000000

  # Replay only (no editor, no judge):
  python -m backend.evals.run_pipeline \\
    --phase Phase_M \\
    --transcripts-dir backend/evals/transcripts \\
    --runs 5

  # Skip replay, run editor + judge on existing outputs:
  python -m backend.evals.run_pipeline \\
    --phase Phase_L3 \\
    --transcripts-dir backend/evals/transcripts \\
    --skip-replay \\
    --editor \\
    --judge
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from backend.evals.judge_eval import judge_analysis, load_transcript_for_judge
from backend.evals.judge_synthesis import run_synthesis, compare_phases, format_report
from backend.evals.replay_eval import (
    find_transcript_files,
    load_raw_transcript,
    run_repeat,
    _load_eval_config,
    _RESULTS_DIR,
)
from backend.evals.report import save_json, save_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Token estimates for concurrency calculation ──────────────────────────────

_TOKENS_PER_REPLAY = 95_000  # Stage 1 + Stage 2
_TOKENS_PER_JUDGE = 12_000


def _max_concurrent(tokens_per_call: int, tpm_limit: int) -> int:
    """Estimate max concurrent calls that stay within TPM limit.

    Assumes each call takes ~60s, so concurrent calls all contribute to the
    same 1-minute TPM window. Uses 80% of limit as safety margin.
    """
    safe_limit = tpm_limit * 0.8
    return max(1, int(safe_limit / tokens_per_call))


# ── Step 1: Replay ───────────────────────────────────────────────────────────

def step_replay(
    transcripts_dir: Path,
    phase_dir: Path,
    n_runs: int,
    model: str | None,
    tpm_limit: int,
) -> None:
    """Run replay eval on all transcripts, all meetings in parallel."""
    logger.info("=" * 60)
    logger.info("STEP 1: REPLAY — %d runs per meeting", n_runs)
    logger.info("=" * 60)

    transcript_files = find_transcript_files(transcripts_dir)
    eval_config = _load_eval_config(transcripts_dir)

    if not transcript_files:
        logger.error("No transcript files found in %s", transcripts_dir)
        return

    logger.info("Found %d transcripts", len(transcript_files))

    # Override the global _RESULTS_DIR so run_repeat saves into our phase dir
    import backend.evals.replay_eval as replay_mod
    original_results_dir = replay_mod._RESULTS_DIR
    replay_mod._RESULTS_DIR = phase_dir

    try:
        # Run all meetings in parallel — run_repeat handles per-meeting concurrency
        max_workers = len(transcript_files)  # One thread per meeting
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_repeat, tf, n_runs, eval_config, model=model): tf.stem
                for tf in transcript_files
            }
            for future in as_completed(futures):
                meeting = futures[future]
                try:
                    future.result()
                    logger.info("✓ Replay complete: %s", meeting)
                except Exception as e:
                    logger.error("✗ Replay FAILED: %s — %s", meeting, e)
    finally:
        replay_mod._RESULTS_DIR = original_results_dir

    # Verify
    total_runs = sum(
        len(list((phase_dir / tf.stem).glob("run_*.json")))
        for tf in transcript_files
    )
    logger.info("Replay complete: %d run files", total_runs)


# ── Step 2: Compare report ───────────────────────────────────────────────────

def step_compare(phase_dir: Path) -> None:
    """Generate offline compare report from run_*.json files only."""
    logger.info("=" * 60)
    logger.info("STEP 2: COMPARE REPORT (offline, no LLM calls)")
    logger.info("=" * 60)

    # Import the compare logic
    from backend.evals.replay_eval import run_compare_offline

    # Temporarily patch to filter only run_*.json files
    import backend.evals.replay_eval as replay_mod
    original_results_dir = replay_mod._RESULTS_DIR
    replay_mod._RESULTS_DIR = phase_dir

    try:
        run_compare_offline(phase_dir, detail=False)
    finally:
        replay_mod._RESULTS_DIR = original_results_dir


# ── Step 3: Judge ────────────────────────────────────────────────────────────

def _judge_one_file(
    output_file: Path,
    transcript_data: dict,
    model: str | None,
) -> tuple[str, Path]:
    """Judge a single output file and save the result."""
    parsed_json = json.loads(output_file.read_text(encoding="utf-8"))
    result = judge_analysis(transcript_data, parsed_json, model=model)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = output_file.parent / f"judge_{output_file.stem}_{timestamp}.json"
    save_json(result, out_path)

    # Brief summary
    gut = result.get("executive_coach_gut_check", {})
    items = result.get("coaching_insight_quality", {}).get("items", [])
    ped_count = sum(1 for i in items if i.get("rating") == "pedantic")
    logger.info("  Judge: %s — %s, %d pedantic",
                output_file.name, gut.get("overall_coaching_value", "?"), ped_count)
    return output_file.name, out_path


def step_judge(
    transcripts_dir: Path,
    phase_dir: Path,
    tpm_limit: int,
    model: str | None = None,
) -> None:
    """Run judge eval on analysis outputs."""
    logger.info("=" * 60)
    logger.info("STEP 3: JUDGE")
    logger.info("=" * 60)

    max_workers = _max_concurrent(_TOKENS_PER_JUDGE, tpm_limit)
    logger.info("Judge concurrency: %d", max_workers)

    meeting_dirs = sorted([
        d for d in phase_dir.iterdir()
        if d.is_dir() and not d.name.startswith("Phase_") and not d.name.startswith(".")
    ])

    tasks: list[tuple[Path, dict, str | None]] = []

    for meeting_dir in meeting_dirs:
        meeting_name = meeting_dir.name
        transcript_path = transcripts_dir / f"{meeting_name}.txt"
        if not transcript_path.exists():
            for ext in [".vtt", ".srt", ".docx", ".pdf"]:
                alt = transcripts_dir / f"{meeting_name}{ext}"
                if alt.exists():
                    transcript_path = alt
                    break
            else:
                logger.warning("No transcript for %s, skipping judge", meeting_name)
                continue

        transcript_data = load_transcript_for_judge(transcript_path)

        for rf in sorted(meeting_dir.glob("run_*.json")):
            # Skip if already judged
            existing = list(meeting_dir.glob(f"judge_{rf.stem}_*.json"))
            if not existing:
                tasks.append((rf, transcript_data, model))

    logger.info("Judge tasks: %d", len(tasks))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_judge_one_file, *task): task[0].name
            for task in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error("  Judge FAILED %s: %s", name, e)

    # Count results
    total = sum(len(list(d.glob("judge_run_*.json"))) for d in meeting_dirs)
    logger.info("Judge complete: %d judge files", total)


# ── Step 5: Synthesis ────────────────────────────────────────────────────────

def step_synthesis(
    phase_dir: Path,
    baseline_dir: Path | None,
) -> None:
    """Run judge synthesis on results."""
    logger.info("=" * 60)
    logger.info("STEP 4: SYNTHESIS")
    logger.info("=" * 60)

    synthesis = run_synthesis(phase_dir, latest_batch_only=True)
    if synthesis:
        comparison = None
        if baseline_dir:
            baseline_synthesis = run_synthesis(baseline_dir, latest_batch_only=True)
            if baseline_synthesis:
                comparison = compare_phases(synthesis, baseline_synthesis)
        md = format_report(synthesis, comparison)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        save_json(synthesis, phase_dir / f"judge_synthesis_{timestamp}.json")
        save_report(md, phase_dir / f"judge_synthesis_{timestamp}.md")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Full eval pipeline: replay (S1+S2) -> compare -> judge -> synthesis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--phase", type=str, required=True,
                        help="Phase name for output directory (e.g., Phase_L3)")
    parser.add_argument("--transcripts-dir", type=Path, required=True,
                        help="Directory containing transcript files")
    parser.add_argument("--runs", type=int, default=5,
                        help="Number of runs per transcript (default: 5)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model override (e.g., claude-sonnet-4-6)")
    parser.add_argument("--judge", action="store_true",
                        help="Run judge eval on outputs")
    parser.add_argument("--skip-replay", action="store_true",
                        help="Skip replay step (use existing run_*.json files)")
    parser.add_argument("--skip-compare", action="store_true",
                        help="Skip compare report generation")
    parser.add_argument("--baseline-dir", type=Path, default=None,
                        help="Baseline phase directory for synthesis comparison")
    parser.add_argument("--tpm-limit", type=int, default=4_000_000,
                        help="API tokens-per-minute limit (default: 4000000)")
    args = parser.parse_args()

    # Set up phase output directory
    phase_dir = _RESULTS_DIR / args.phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Phase directory: %s", phase_dir)
    logger.info("TPM limit: %d", args.tpm_limit)

    start_time = time.time()

    # Step 1: Replay (Stage 1 scoring + Stage 2 coaching)
    if not args.skip_replay:
        step_replay(args.transcripts_dir, phase_dir, args.runs, args.model, args.tpm_limit)
    else:
        logger.info("Skipping replay (--skip-replay)")

    # Gate: check that replay produced output before continuing
    total_runs = sum(
        len(list(d.glob("run_*.json")))
        for d in phase_dir.iterdir()
        if d.is_dir() and not d.name.startswith(("Phase_", ".", "_"))
    )
    if total_runs == 0 and not args.skip_replay:
        logger.error("ABORTING: No run files produced. Check API quota/connectivity.")
        sys.exit(1)
    logger.info("Gate check: %d run files available", total_runs)

    # Step 2: Compare report
    if not args.skip_compare:
        step_compare(phase_dir)
    else:
        logger.info("Skipping compare (--skip-compare)")

    # Step 3: Judge
    if args.judge:
        step_judge(args.transcripts_dir, phase_dir, args.tpm_limit, model=args.model)

    # Step 4: Synthesis
    if args.judge:
        step_synthesis(phase_dir, args.baseline_dir)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("Results: %s", phase_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
