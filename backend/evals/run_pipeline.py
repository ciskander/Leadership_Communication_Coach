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
import copy
import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.editor import build_experiment_context, merge_editor_output, run_editor
from backend.core.prompt_builder import build_single_meeting_prompt
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

_TOKENS_PER_REPLAY = 48_000
_TOKENS_PER_EDITOR = 18_000
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


# ── Step 3: Editor ───────────────────────────────────────────────────────────

def _run_editor_on_one(
    run_file: Path,
    results_subdir: Path,
    transcript_turns: list[dict],
    memory: Any,
    timestamp: str,
) -> tuple[str, int]:
    """Process a single run file through the editor."""
    parsed_output = json.loads(run_file.read_text(encoding="utf-8"))
    exp_context = build_experiment_context(memory, parsed_output)

    editor_result, ed_prompt_tokens, ed_completion_tokens = run_editor(
        parsed_output, transcript_turns, exp_context,
    )

    # Save editor delta
    editor_path = results_subdir / f"editor_{run_file.stem}_{timestamp}.json"
    save_json(editor_result, editor_path)

    # Merge to create post-editor version
    pre_editor = copy.deepcopy(parsed_output)
    merged, changelog = merge_editor_output(pre_editor, editor_result)

    # Save post-editor merged output
    post_editor_path = results_subdir / f"post_editor_{run_file.stem}_{timestamp}.json"
    save_json(merged, post_editor_path)

    logger.info("  Editor: %s — %d changes", run_file.name, len(changelog))
    return run_file.name, len(changelog)


def step_editor(
    transcripts_dir: Path,
    phase_dir: Path,
    tpm_limit: int,
) -> None:
    """Run editor on all pre-editor outputs."""
    logger.info("=" * 60)
    logger.info("STEP 3: EDITOR")
    logger.info("=" * 60)

    eval_config = _load_eval_config(transcripts_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    max_workers = _max_concurrent(_TOKENS_PER_EDITOR, tpm_limit)
    logger.info("Editor concurrency: %d", max_workers)

    # Discover meetings from phase_dir subdirectories
    meeting_dirs = sorted([
        d for d in phase_dir.iterdir()
        if d.is_dir() and not d.name.startswith("Phase_") and not d.name.startswith(".")
    ])

    tasks = []
    for meeting_dir in meeting_dirs:
        meeting_name = meeting_dir.name
        transcript_path = transcripts_dir / f"{meeting_name}.txt"
        if not transcript_path.exists():
            # Try other extensions
            for ext in [".vtt", ".srt", ".docx", ".pdf"]:
                alt = transcripts_dir / f"{meeting_name}{ext}"
                if alt.exists():
                    transcript_path = alt
                    break
            else:
                logger.warning("No transcript for %s, skipping", meeting_name)
                continue

        run_files = sorted(meeting_dir.glob("run_*.json"))
        if not run_files:
            continue

        # Skip runs that already have post-editor output
        pending_runs = []
        for rf in run_files:
            existing = list(meeting_dir.glob(f"post_editor_{rf.stem}_*.json"))
            if existing:
                logger.info("  Skipping %s/%s (already has post-editor)", meeting_name, rf.name)
            else:
                pending_runs.append(rf)

        if not pending_runs:
            logger.info("  %s: all editor runs complete, skipping", meeting_name)
            continue

        # Load transcript once per meeting
        metadata, parsed_transcript, memory = load_raw_transcript(transcript_path, eval_config)
        prompt_payload = build_single_meeting_prompt(
            meeting_id=metadata["meeting_id"],
            meeting_type=metadata["meeting_type"],
            meeting_date=metadata.get("meeting_date", "2026-01-01"),
            target_role=metadata["target_role"],
            target_speaker_name=metadata["target_speaker_name"],
            target_speaker_label=metadata["target_speaker_label"],
            parsed_transcript=parsed_transcript,
            memory=memory,
        )
        transcript_turns = prompt_payload.transcript_payload["turns"]

        for rf in pending_runs:
            tasks.append((rf, meeting_dir, transcript_turns, memory, timestamp))

    logger.info("Editor tasks: %d", len(tasks))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_editor_on_one, *task): task[0].name
            for task in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error("  Editor FAILED %s: %s", name, e)

    # Verify
    total_post = sum(len(list(d.glob("post_editor_*.json"))) for d in meeting_dirs)
    logger.info("Editor complete: %d post-editor files", total_post)


# ── Step 4: Judge ────────────────────────────────────────────────────────────

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
    judge_pre: bool = True,
    judge_post: bool = True,
) -> None:
    """Run judge eval on pre-editor and/or post-editor outputs."""
    logger.info("=" * 60)
    logger.info("STEP 4: JUDGE (pre=%s, post=%s)", judge_pre, judge_post)
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

        if judge_pre:
            for rf in sorted(meeting_dir.glob("run_*.json")):
                # Skip if already judged
                existing = list(meeting_dir.glob(f"judge_{rf.stem}_*.json"))
                if not existing:
                    tasks.append((rf, transcript_data, model))

        if judge_post:
            for pf in sorted(meeting_dir.glob("post_editor_*.json")):
                existing = list(meeting_dir.glob(f"judge_{pf.stem}_*.json"))
                if not existing:
                    tasks.append((pf, transcript_data, model))

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
    total_pre = sum(len(list(d.glob("judge_run_*.json"))) for d in meeting_dirs)
    total_post = sum(len(list(d.glob("judge_post_editor_*.json"))) for d in meeting_dirs)
    logger.info("Judge complete: %d pre-editor, %d post-editor", total_pre, total_post)


# ── Step 5: Synthesis ────────────────────────────────────────────────────────

def step_synthesis(
    phase_dir: Path,
    baseline_dir: Path | None,
    post_editor_baseline_dir: Path | None,
) -> None:
    """Run judge synthesis on pre-editor and post-editor results."""
    logger.info("=" * 60)
    logger.info("STEP 5: SYNTHESIS")
    logger.info("=" * 60)

    # Pre-editor synthesis — judge_run_*.json files are already in phase_dir
    logger.info("--- Pre-editor synthesis ---")
    pre_synthesis = run_synthesis(phase_dir, latest_batch_only=True)
    if pre_synthesis:
        comparison = None
        if baseline_dir:
            baseline_synthesis = run_synthesis(baseline_dir, latest_batch_only=True)
            if baseline_synthesis:
                comparison = compare_phases(pre_synthesis, baseline_synthesis)
        md = format_report(pre_synthesis, comparison)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        save_json(pre_synthesis, phase_dir / f"judge_synthesis_pre_{timestamp}.json")
        save_report(md, phase_dir / f"judge_synthesis_pre_{timestamp}.md")

    # Post-editor synthesis — need to set up a directory with correctly-named files
    post_judge_files = []
    for meeting_dir in sorted(phase_dir.iterdir()):
        if not meeting_dir.is_dir() or meeting_dir.name.startswith("Phase_") or meeting_dir.name.startswith("."):
            continue
        post_judge_files.extend(meeting_dir.glob("judge_post_editor_*.json"))

    if not post_judge_files:
        logger.info("No post-editor judge files found, skipping post-editor synthesis")
        return

    logger.info("--- Post-editor synthesis ---")
    post_dir = phase_dir / "_post_editor_synthesis"
    post_dir.mkdir(exist_ok=True)

    # Copy and rename post-editor judge files to match expected pattern
    import re
    for f in post_judge_files:
        meeting_name = f.parent.name
        dest_meeting = post_dir / meeting_name
        dest_meeting.mkdir(exist_ok=True)

        # Transform: judge_post_editor_run_NNN_TS1_TS2_TS3.json -> judge_run_NNN_TS1_TS3.json
        new_name = f.name.replace("judge_post_editor_", "judge_")
        # Collapse triple timestamp to double: keep first and last
        new_name = re.sub(
            r"(\d{8}T\d{6})_\d{8}T\d{6}_(\d{8}T\d{6})",
            r"\1_\2",
            new_name,
        )
        shutil.copy2(f, dest_meeting / new_name)

    post_synthesis = run_synthesis(post_dir, latest_batch_only=False)
    if post_synthesis:
        comparison = None
        if post_editor_baseline_dir:
            baseline_synthesis = run_synthesis(post_editor_baseline_dir, latest_batch_only=True)
            if baseline_synthesis:
                comparison = compare_phases(post_synthesis, baseline_synthesis)
        md = format_report(post_synthesis, comparison)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        save_json(post_synthesis, phase_dir / f"judge_synthesis_post_{timestamp}.json")
        save_report(md, phase_dir / f"judge_synthesis_post_{timestamp}.md")

    # Clean up temp directory
    shutil.rmtree(post_dir)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Full eval pipeline: replay -> compare -> editor -> judge -> synthesis",
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
    parser.add_argument("--editor", action="store_true",
                        help="Run editor (2nd pass) on replay outputs")
    parser.add_argument("--judge", action="store_true",
                        help="Run judge eval on outputs")
    parser.add_argument("--judge-pre-only", action="store_true",
                        help="Only judge pre-editor outputs (requires --judge)")
    parser.add_argument("--judge-post-only", action="store_true",
                        help="Only judge post-editor outputs (requires --judge and --editor)")
    parser.add_argument("--skip-replay", action="store_true",
                        help="Skip replay step (use existing run_*.json files)")
    parser.add_argument("--skip-compare", action="store_true",
                        help="Skip compare report generation")
    parser.add_argument("--baseline-dir", type=Path, default=None,
                        help="Baseline phase directory for pre-editor synthesis comparison")
    parser.add_argument("--post-editor-baseline-dir", type=Path, default=None,
                        help="Baseline phase directory for post-editor synthesis comparison")
    parser.add_argument("--tpm-limit", type=int, default=4_000_000,
                        help="API tokens-per-minute limit (default: 4000000)")
    args = parser.parse_args()

    # Set up phase output directory
    phase_dir = _RESULTS_DIR / args.phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Phase directory: %s", phase_dir)
    logger.info("TPM limit: %d", args.tpm_limit)

    start_time = time.time()

    # Ensure EDITOR_ENABLED=0 for replay (we run editor separately)
    os.environ["EDITOR_ENABLED"] = "0"

    # Step 1: Replay
    if not args.skip_replay:
        step_replay(args.transcripts_dir, phase_dir, args.runs, args.model, args.tpm_limit)
    else:
        logger.info("Skipping replay (--skip-replay)")

    # Step 2: Compare report
    if not args.skip_compare:
        step_compare(phase_dir)
    else:
        logger.info("Skipping compare (--skip-compare)")

    # Step 3: Editor
    if args.editor:
        step_editor(args.transcripts_dir, phase_dir, args.tpm_limit)

    # Step 4: Judge
    if args.judge:
        judge_pre = not args.judge_post_only
        judge_post = not args.judge_pre_only and args.editor
        step_judge(args.transcripts_dir, phase_dir, args.tpm_limit,
                   model=args.model, judge_pre=judge_pre, judge_post=judge_post)

    # Step 5: Synthesis
    if args.judge:
        step_synthesis(phase_dir, args.baseline_dir, args.post_editor_baseline_dir)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1f minutes", elapsed / 60)
    logger.info("Results: %s", phase_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
