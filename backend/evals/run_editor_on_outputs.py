"""Run the editor on existing pre-editor run_*.json files and save both
the editor delta and the merged post-editor output.

Usage:
    python -m backend.evals.run_editor_on_outputs \
        --results-dir backend/evals/results \
        --transcripts-dir backend/evals/transcripts
"""

import argparse
import copy
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from backend.core.editor import build_experiment_context, merge_editor_output, run_editor
from backend.core.prompt_builder import build_single_meeting_prompt
from backend.evals.replay_eval import load_raw_transcript, _load_eval_config
from backend.evals.report import save_json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

def _discover_meetings(results_dir: Path) -> list[str]:
    """Auto-discover meeting directories (any subdir containing run_*.json files)."""
    meetings = []
    for d in sorted(results_dir.iterdir()):
        if d.is_dir() and not d.name.startswith(("Phase_", ".", "_")):
            if list(d.glob("run_*.json")):
                meetings.append(d.name)
    return meetings


def _process_one_run(run_file, results_subdir, transcript_turns, memory, timestamp):
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

    logger.info("  %s: %d changes, %d+%d tokens",
                run_file.name, len(changelog), ed_prompt_tokens, ed_completion_tokens)
    return run_file.name, len(changelog)


def main():
    parser = argparse.ArgumentParser(description="Run editor on existing pre-editor outputs")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--transcripts-dir", type=Path, required=True)
    args = parser.parse_args()

    eval_config = _load_eval_config(args.transcripts_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Collect all tasks across all meetings
    meetings = _discover_meetings(args.results_dir)
    logger.info("Discovered %d meetings: %s", len(meetings), meetings)
    tasks = []
    for meeting in meetings:
        transcript_path = args.transcripts_dir / f"{meeting}.txt"
        if not transcript_path.exists():
            logger.warning("Transcript not found: %s", transcript_path)
            continue

        results_subdir = args.results_dir / meeting
        run_files = sorted(results_subdir.glob("run_*.json"))
        if not run_files:
            logger.warning("No run files in %s", results_subdir)
            continue

        # Skip runs that already have post-editor output
        pending_runs = []
        for rf in run_files:
            existing = list(results_subdir.glob(f"post_editor_{rf.stem}_*.json"))
            if existing:
                logger.info("  Skipping %s (already has post-editor output)", rf.name)
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

        logger.info("=== %s: %d pending run files ===", meeting, len(pending_runs))
        for rf in pending_runs:
            tasks.append((rf, results_subdir, transcript_turns, memory, timestamp))

    logger.info("Total tasks: %d", len(tasks))

    # Run all tasks in parallel (up to 7 concurrent — one per meeting max)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(_process_one_run, *task): task[0].name
            for task in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error("  FAILED %s: %s", name, e)


if __name__ == "__main__":
    main()
