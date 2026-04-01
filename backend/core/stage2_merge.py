"""
stage2_merge.py — Merge Stage 2 coaching output with Stage 1 scoring output.

This is the production merge logic. The eval script (run_stage2.py) should
import from here to ensure a single implementation.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from .editor import _process_oe_removals, _recalculate_pattern_score

logger = logging.getLogger(__name__)


def merge_stage2_output(
    stage1_output: dict,
    stage2_output: dict,
) -> tuple[dict, list[dict]]:
    """Merge Stage 2 coaching output into Stage 1 scoring.

    Processing order:
    1. OE removals -> score recalculation -> possible demotion
    2. Overlay coaching fields from Stage 2
    3. Add experiment_tracking from Stage 2

    Args:
        stage1_output: The full Stage 1 scoring-only output (will be deep-copied).
        stage2_output: The Stage 2 coaching output (coaching fields + oe_removals + changes).

    Returns:
        Tuple of (merged_output, changelog).
    """
    merged = copy.deepcopy(stage1_output)
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

    # 3. Add experiment_tracking from Stage 2
    if "experiment_tracking" in stage2_output:
        merged["experiment_tracking"] = stage2_output["experiment_tracking"]

    return merged, changelog
