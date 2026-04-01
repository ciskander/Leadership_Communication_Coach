"""
run_stage2.py — Run Stage 2 coaching synthesis on existing Stage 1 (run_*.json) outputs.

Takes existing run_*.json files from a phase directory, strips coaching fields,
combines with the meeting transcript, calls the Stage 2 LLM, and merges the
result back with Stage 1 scoring to produce a complete analysis output.

Usage:
  python -m backend.evals.run_stage2 \
    --phase-dir backend/evals/results/Phase_M \
    --output-phase Phase_N_stage2 \
    --transcripts-dir backend/evals/transcripts

  # Override model:
  python -m backend.evals.run_stage2 \
    --phase-dir backend/evals/results/Phase_M \
    --output-phase Phase_N_stage2 \
    --transcripts-dir backend/evals/transcripts \
    --model claude-sonnet-4-5-20250514
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.config import OPENAI_MODEL_DEFAULT
from backend.core.editor import _process_oe_removals, _recalculate_pattern_score
from backend.core.llm_client import call_llm
from backend.core.prompt_builder import build_single_meeting_prompt
from backend.evals.replay_eval import load_raw_transcript, _load_eval_config
from backend.evals.report import save_json
from backend.evals.strip_to_stage1 import strip_coaching, discover_run_files

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Estimated tokens per Stage 2 call (transcript + Stage 1 JSON + output)
_TOKENS_PER_CALL = 35_000


# ── Prompt loading ───────────────────────────────────────────────────────────

def _load_stage2_prompt() -> str:
    """Load the Stage 2 system prompt from the repo file."""
    p = _REPO_ROOT / "system_prompt_stage2_v0.1.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Stage 2 system prompt not found at {p}")


def _load_stage2_pattern_definitions() -> str:
    """Load the Stage 2 pattern definitions (includes DQ)."""
    p = _REPO_ROOT / "stage2_pattern_definitions_v0.1.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Stage 2 pattern definitions not found at {p}")


def _build_stage2_system_prompt(experiment_context: str = "") -> str:
    """Assemble the full Stage 2 system prompt with substitutions."""
    raw = _load_stage2_prompt()
    pattern_defs = _load_stage2_pattern_definitions()
    return (
        raw
        .replace("__PATTERN_DEFINITIONS__", pattern_defs)
        .replace("__EXPERIMENT_CONTEXT__", experiment_context)
    )


def _build_stage2_user_message(
    stage1_output: dict,
    transcript_turns: list[dict],
) -> str:
    """Build the user message for the Stage 2 LLM call.

    Contains the transcript and the stripped Stage 1 output.
    """
    transcript_json = json.dumps(transcript_turns, ensure_ascii=False, indent=2)
    stage1_json = json.dumps(stage1_output, ensure_ascii=False, indent=2)

    return (
        "=== MEETING TRANSCRIPT (speaker turns) ===\n\n"
        f"{transcript_json}\n\n"
        "=== STAGE 1 ANALYSIS OUTPUT (scoring only — no coaching) ===\n\n"
        f"{stage1_json}"
    )


# ── Merge Stage 2 output with Stage 1 ──────────────────────────────────────

def merge_stage2_output(
    stage1_original: dict,
    stage2_output: dict,
) -> tuple[dict, list[dict]]:
    """Merge Stage 2 coaching output into Stage 1 scoring.

    Processing order:
    1. OE removals → score recalculation → possible demotion
    2. Overlay coaching fields from Stage 2

    Returns (merged_output, changelog).
    """
    merged = copy.deepcopy(stage1_original)
    changelog = stage2_output.get("changes", [])

    # 1. OE removals (reuses editor.py logic)
    oe_removals = stage2_output.get("oe_removals", [])
    demoted: set[str] = set()
    if oe_removals:
        demoted = _process_oe_removals(merged, oe_removals)
        if demoted:
            logger.info("  Patterns demoted after OE removal: %s", sorted(demoted))

    # 2. Overlay coaching fields
    coaching = merged.setdefault("coaching", {})

    # Replace coaching fields from Stage 2
    for field in [
        "executive_summary", "coaching_themes", "strengths",
        "focus", "micro_experiment", "experiment_coaching",
    ]:
        if field in stage2_output:
            coaching[field] = stage2_output[field]

    # Pattern coaching: Stage 2 provides its own array
    if "pattern_coaching" in stage2_output:
        coaching["pattern_coaching"] = stage2_output["pattern_coaching"]

    # Null out coaching for demoted patterns
    if demoted and "pattern_coaching" in coaching:
        for pc in coaching["pattern_coaching"]:
            if pc.get("pattern_id") in demoted:
                pc["notes"] = None
                pc["coaching_note"] = None
                pc["suggested_rewrite"] = None
                pc["rewrite_for_span_id"] = None

    return merged, changelog


# ── Meeting discovery ────────────────────────────────────────────────────────

def _discover_meetings(phase_dir: Path) -> list[str]:
    """Auto-discover meeting directories in a phase results directory."""
    meetings = []
    for d in sorted(phase_dir.iterdir()):
        if d.is_dir() and not d.name.startswith(("Phase_", ".", "_")):
            if list(d.glob("run_*.json")):
                meetings.append(d.name)
    return meetings


def _match_transcript(meeting_name: str, transcripts_dir: Path) -> Optional[Path]:
    """Find the transcript file for a meeting directory name.

    Meeting dirs are named like 'M-000003_contentious_meeting'.
    Transcript files are named like 'M-000003_contentious_meeting.txt'.
    """
    transcript_path = transcripts_dir / f"{meeting_name}.txt"
    if transcript_path.exists():
        return transcript_path
    # Fallback: try just the meeting ID prefix
    meeting_id = meeting_name.split("_")[0]  # e.g., 'M-000003'
    for ext in (".txt", ".vtt", ".srt"):
        p = transcripts_dir / f"{meeting_id}{ext}"
        if p.exists():
            return p
    return None


# ── Single-run processing ───────────────────────────────────────────────────

def _process_one_run(
    run_file: Path,
    output_dir: Path,
    transcript_turns: list[dict],
    system_prompt: str,
    timestamp: str,
    model: Optional[str] = None,
) -> tuple[str, int, int]:
    """Process a single run file through Stage 2.

    Returns (run_filename, prompt_tokens, completion_tokens).
    """
    # Load and strip Stage 1 output
    stage1_full = json.loads(run_file.read_text(encoding="utf-8"))
    stage1_stripped = strip_coaching(stage1_full)

    # Build Stage 2 user message
    user_message = _build_stage2_user_message(stage1_stripped, transcript_turns)

    # Call Stage 2 LLM
    response = call_llm(
        system_prompt=system_prompt,
        developer_message="",
        user_message=user_message,
        model=model,
    )

    stage2_raw = response.parsed

    # Save Stage 2 raw output (delta)
    stage2_path = output_dir / f"stage2_{run_file.stem}_{timestamp}.json"
    save_json(stage2_raw, stage2_path)

    # Merge Stage 1 scoring + Stage 2 coaching
    merged, changelog = merge_stage2_output(stage1_full, stage2_raw)

    # Save merged output (what the judge will evaluate)
    merged_path = output_dir / f"stage2_merged_{run_file.stem}_{timestamp}.json"
    save_json(merged, merged_path)

    logger.info(
        "  %s: %d changes, %d OE removals, %d+%d tokens",
        run_file.name,
        len(changelog),
        len(stage2_raw.get("oe_removals", [])),
        response.prompt_tokens,
        response.completion_tokens,
    )

    return run_file.name, response.prompt_tokens, response.completion_tokens


# ── Concurrency ──────────────────────────────────────────────────────────────

def _max_concurrent(tpm_limit: int) -> int:
    """Calculate max concurrent Stage 2 calls based on token budget."""
    safe_limit = int(tpm_limit * 0.8)
    return max(1, safe_limit // _TOKENS_PER_CALL)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stage 2 coaching synthesis on existing Stage 1 outputs."
    )
    parser.add_argument(
        "--phase-dir", type=Path, required=True,
        help="Directory containing source Stage 1 results (e.g., backend/evals/results/Phase_M)",
    )
    parser.add_argument(
        "--output-phase", type=str, required=True,
        help="Name for the output phase directory (e.g., Phase_N_stage2)",
    )
    parser.add_argument(
        "--transcripts-dir", type=Path, required=True,
        help="Directory containing transcript files",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help=f"LLM model override (default: {OPENAI_MODEL_DEFAULT})",
    )
    parser.add_argument(
        "--tpm-limit", type=int, default=4_000_000,
        help="Token-per-minute limit for concurrency calculation",
    )
    parser.add_argument(
        "--meetings", type=str, nargs="*", default=None,
        help="Specific meeting directories to process (default: all)",
    )
    args = parser.parse_args()

    if not args.phase_dir.exists():
        logger.error("Phase directory does not exist: %s", args.phase_dir)
        sys.exit(1)

    # Output directory
    output_base = args.phase_dir.parent / args.output_phase
    output_base.mkdir(parents=True, exist_ok=True)

    # Load eval config and Stage 2 prompt
    eval_config = _load_eval_config(args.transcripts_dir)
    system_prompt = _build_stage2_system_prompt()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Discover meetings
    all_meetings = _discover_meetings(args.phase_dir)
    if args.meetings:
        meetings = [m for m in all_meetings if m in args.meetings]
    else:
        meetings = all_meetings

    if not meetings:
        logger.error("No meetings found in %s", args.phase_dir)
        sys.exit(1)

    logger.info("Found %d meetings: %s", len(meetings), meetings)

    # Collect all tasks
    tasks: list[tuple] = []
    for meeting in meetings:
        transcript_path = _match_transcript(meeting, args.transcripts_dir)
        if transcript_path is None:
            logger.warning("No transcript found for %s, skipping", meeting)
            continue

        # Source run files
        source_dir = args.phase_dir / meeting
        run_files = sorted(
            f for f in source_dir.glob("run_*.json")
            if not f.name.startswith(("editor_", "judge_", "post_editor_", "stage2_"))
        )
        if not run_files:
            logger.warning("No run files in %s, skipping", source_dir)
            continue

        # Output directory for this meeting
        output_dir = output_base / meeting
        output_dir.mkdir(parents=True, exist_ok=True)

        # Skip runs that already have Stage 2 output
        pending_runs = []
        for rf in run_files:
            existing = list(output_dir.glob(f"stage2_merged_{rf.stem}_*.json"))
            if existing:
                logger.info("  Skipping %s (already has Stage 2 output)", rf.name)
            else:
                pending_runs.append(rf)

        if not pending_runs:
            logger.info("=== %s: all done, skipping ===", meeting)
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

        logger.info("=== %s: %d pending runs ===", meeting, len(pending_runs))
        for rf in pending_runs:
            tasks.append((
                rf, output_dir, transcript_turns,
                system_prompt, timestamp, args.model,
            ))

    if not tasks:
        logger.info("No tasks to process.")
        return

    logger.info("Total tasks: %d", len(tasks))

    # Run all tasks with concurrency control
    max_workers = _max_concurrent(args.tpm_limit)
    logger.info("Max concurrent workers: %d (TPM limit: %d)", max_workers, args.tpm_limit)

    total_prompt_tokens = 0
    total_completion_tokens = 0
    succeeded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_one_run, *task): task[0].name
            for task in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, pt, ct = future.result()
                total_prompt_tokens += pt
                total_completion_tokens += ct
                succeeded += 1
            except Exception as e:
                logger.error("  FAILED %s: %s", name, e, exc_info=True)
                failed += 1

    logger.info(
        "Done. %d succeeded, %d failed. Total tokens: %d prompt + %d completion",
        succeeded, failed, total_prompt_tokens, total_completion_tokens,
    )


if __name__ == "__main__":
    main()
