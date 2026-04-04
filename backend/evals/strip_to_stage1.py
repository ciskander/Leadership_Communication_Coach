"""
strip_to_stage1.py — Strip coaching fields from run_*.json to produce Stage 1 only output.

Takes Phase M (or any phase) run_*.json files and produces stripped JSON
containing only scoring data (OEs, evidence spans, pattern snapshot, etc.)
with all coaching fields removed. This represents what Stage 1 would produce
in the two-stage architecture.

Usage:
  python -m backend.evals.strip_to_stage1 \
    --phase-dir backend/evals/results/Phase_M

  # Dry run (show what would be created without writing):
  python -m backend.evals.strip_to_stage1 \
    --phase-dir backend/evals/results/Phase_M --dry-run
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Fields to remove from the coaching object
_COACHING_FIELDS_TO_STRIP = [
    "executive_summary",
    "coaching_themes",
    "focus",
    "micro_experiment",
    "pattern_coaching",
    "experiment_coaching",
]


def strip_coaching(data: dict) -> dict:
    """Return a deep copy of *data* with coaching fields removed.

    Keeps:
      - meta, context, opportunity_events (including OE notes),
        evidence_spans, evaluation_summary, pattern_snapshot,
        experiment_tracking
    Removes:
      - coaching.executive_summary, coaching_themes, focus,
        micro_experiment, pattern_coaching, experiment_coaching
    """
    stripped = copy.deepcopy(data)

    coaching = stripped.get("coaching")
    if coaching is None:
        return stripped

    for field in _COACHING_FIELDS_TO_STRIP:
        coaching.pop(field, None)

    # If coaching is now empty, remove the key entirely
    if not coaching:
        stripped.pop("coaching", None)

    return stripped


def discover_run_files(phase_dir: Path) -> list[Path]:
    """Find all run_*.json files under phase_dir (excluding editor/judge/post-editor/stage2)."""
    run_files = []
    for f in sorted(phase_dir.rglob("run_*.json")):
        name = f.name
        # Skip editor, judge, post-editor, and stage2 outputs
        if any(name.startswith(prefix) for prefix in (
            "editor_run_", "judge_run_", "post_editor_", "stage2_run_",
            "judge_post_editor_", "judge_stage2_",
        )):
            continue
        run_files.append(f)
    return run_files


def strip_phase(phase_dir: Path, *, dry_run: bool = False) -> int:
    """Strip coaching from all run files in a phase directory.

    Returns number of files processed.
    """
    run_files = discover_run_files(phase_dir)
    if not run_files:
        logger.warning("No run_*.json files found in %s", phase_dir)
        return 0

    logger.info("Found %d run files in %s", len(run_files), phase_dir)

    processed = 0
    for run_file in run_files:
        # Build output filename: run_001_TIMESTAMP.json → stage1_run_001_TIMESTAMP.json
        out_name = f"stage1_{run_file.name}"
        out_path = run_file.parent / out_name

        if out_path.exists():
            logger.info("  SKIP (exists): %s", out_path.relative_to(phase_dir))
            continue

        if dry_run:
            logger.info("  DRY RUN: would create %s", out_path.relative_to(phase_dir))
            processed += 1
            continue

        data = json.loads(run_file.read_text(encoding="utf-8"))
        stripped = strip_coaching(data)

        out_path.write_text(
            json.dumps(stripped, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("  Created: %s", out_path.relative_to(phase_dir))
        processed += 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strip coaching fields from run_*.json to produce Stage 1 only output."
    )
    parser.add_argument(
        "--phase-dir",
        type=Path,
        required=True,
        help="Directory containing phase results (e.g., backend/evals/results/Phase_M)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )
    args = parser.parse_args()

    if not args.phase_dir.exists():
        logger.error("Phase directory does not exist: %s", args.phase_dir)
        sys.exit(1)

    count = strip_phase(args.phase_dir, dry_run=args.dry_run)
    logger.info("Done. Processed %d files.", count)


if __name__ == "__main__":
    main()
