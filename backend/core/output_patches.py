"""
output_patches.py — Shared post-LLM-call output patching.

Extracted from workers.py so that both the production pipeline (workers.py)
and the eval pipeline (replay_eval.py) apply identical corrections to raw
LLM output before the editor and Gate1 steps.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Legacy field cleanup (formerly _patch_parsed_output in workers.py) ────────

def _patch_legacy_fields(parsed: dict) -> dict:
    """
    Apply legacy-migration corrections to a parsed output dict.
    Returns a new deep-copied dict — does not mutate the input.

    Covers:
    - Strip legacy numeric fields (numerator, denominator, ratio, tier)
    - Backfill missing denominator_rule_id and min_required_threshold
    - Coerce zero-opportunity evaluable patterns to insufficient_signal
    - Backfill null denominator_rule_id on not_evaluable patterns
    - Coerce legacy 'assigned' experiment status to 'proposed'
    """
    parsed = copy.deepcopy(parsed)

    # Strip legacy fields the model may still emit
    for snap in parsed.get("pattern_snapshot", []):
        for field in ("numerator", "denominator", "ratio", "tier"):
            snap.pop(field, None)
        # Backfill required base fields the model sometimes omits
        snap.setdefault("denominator_rule_id", "unknown")
        snap.setdefault("min_required_threshold", None)

    # Coerce zero-opportunity evaluable patterns to insufficient_signal
    for snap in parsed.get("pattern_snapshot", []):
        if (
            snap.get("evaluable_status") == "evaluable"
            and snap.get("opportunity_count") == 0
        ):
            snap["evaluable_status"] = "insufficient_signal"
            snap.pop("score", None)

    # Backfill null denominator_rule_id on not_evaluable patterns
    for snap in parsed.get("pattern_snapshot", []):
        if snap.get("denominator_rule_id") is None:
            snap["denominator_rule_id"] = "not_evaluable"

    # Coerce legacy 'assigned' experiment status to 'proposed'
    exp_track = parsed.get("experiment_tracking", {})
    active_exp = exp_track.get("active_experiment", {})
    if isinstance(active_exp, dict) and active_exp.get("status") == "assigned":
        active_exp["status"] = "proposed"

    return parsed


# ── Main patch function ───────────────────────────────────────────────────────

def patch_analysis_output(
    parsed_output: dict,
    *,
    prompt_meta: Optional[dict] = None,
    active_experiment: Optional[dict] = None,
    has_active_experiment: bool = False,
    cleanup_enabled: bool = False,
    scoring_only: bool = False,
) -> dict:
    """Apply all post-LLM corrections to a parsed analysis output dict.

    This function is the single source of truth for output patching. Both
    the production pipeline (workers.py) and the eval pipeline (replay_eval.py)
    should call this before the editor and Gate1 steps.

    Args:
        parsed_output: Raw parsed JSON from the LLM response.
        prompt_meta: Meta dict from the prompt payload (analysis_id, etc.).
            If None, meta-field injection is skipped.
        active_experiment: The active experiment dict from memory (with
            pattern_id, experiment_id, status). If None, focus override
            is skipped.
        has_active_experiment: Whether an active experiment record exists
            in Airtable. Used for the focus override safety gate.
        cleanup_enabled: Whether to run ASR quote cleanup.

    Returns:
        A new dict with all patches applied. Does NOT mutate the input.
    """
    # Work on a deep copy so callers keep the original
    output = copy.deepcopy(parsed_output)

    # 1. Inject/fix meta fields the model may omit
    if prompt_meta and "meta" in output:
        output["meta"].setdefault("analysis_id", prompt_meta.get("analysis_id"))
        output["meta"].setdefault("analysis_type", prompt_meta.get("analysis_type"))
        output["meta"].setdefault("generated_at", prompt_meta.get("generated_at"))

    # Steps 2-6 only apply to full (coaching-included) output.
    # For scoring-only Stage 1 output, skip directly to legacy patches.
    if not scoring_only:
        # 2. Fix experiment_tracking detection structure
        exp_track = output.get("experiment_tracking", {})
        active_exp_data = exp_track.get("active_experiment", {})
        active_status = (active_exp_data or {}).get("status", "none")

        if active_status == "active":
            detection = exp_track.get("detection_in_this_meeting")
            if not isinstance(detection, dict):
                exp_track["detection_in_this_meeting"] = {
                    "experiment_id": (active_exp_data or {}).get("experiment_id", "EXP-000000"),
                    "attempt": "no",
                    "count_attempts": 0,
                    "evidence_span_ids": [],
                }
        else:
            exp_track["detection_in_this_meeting"] = {
                "experiment_id": "EXP-000000",
                "attempt": "no",
                "count_attempts": 0,
                "evidence_span_ids": [],
            }

        if active_exp_data:
            if active_exp_data.get("experiment_id") is None:
                exp_track["active_experiment"] = {"experiment_id": "EXP-000000", "status": "none"}
                exp_track["detection_in_this_meeting"] = None

        # 3. Coerce missing evidence_span_ids on micro_experiment items
        coaching = output.get("coaching", {})
        for item in coaching.get("micro_experiment", []):
            if isinstance(item, dict):
                item.setdefault("evidence_span_ids", [])

        # 4. Ensure coaching.pattern_coaching and experiment_coaching exist
        coaching.setdefault("pattern_coaching", [])
        coaching.setdefault("experiment_coaching", None)

        # 5. Focus override safety gate: when an active experiment exists, force
        # the focus pattern_id to match the experiment's pattern_id.
        if has_active_experiment and active_experiment:
            expected_pattern = active_experiment.get("pattern_id")
            focus_items = coaching.get("focus", [])
            if expected_pattern and focus_items:
                actual_pattern = focus_items[0].get("pattern_id")
                if actual_pattern != expected_pattern:
                    logger.warning(
                        "Focus override: LLM returned '%s' but active experiment requires '%s'",
                        actual_pattern, expected_pattern,
                    )
                    focus_items[0]["pattern_id"] = expected_pattern
                    # Replace the message with the coaching_note from the matching
                    # pattern_coaching entry so the text is relevant to the
                    # overridden pattern.
                    pattern_coaching = coaching.get("pattern_coaching", [])
                    match = next(
                        (pc for pc in pattern_coaching
                         if pc.get("pattern_id") == expected_pattern),
                        None,
                    )
                    if match and match.get("coaching_note"):
                        focus_items[0]["message"] = match["coaching_note"]

        # 6. Ensure rewrite_for_span_id references in coaching.pattern_coaching are
        # included in the corresponding pattern's evidence_span_ids and NOT in
        # success_evidence_span_ids (it is always a failure).
        _pc_rewrite_by_pattern = {
            pc.get("pattern_id"): pc.get("rewrite_for_span_id")
            for pc in coaching.get("pattern_coaching", [])
            if pc.get("rewrite_for_span_id")
        }
        for ps in output.get("pattern_snapshot", []):
            rewrite_span = _pc_rewrite_by_pattern.get(ps.get("pattern_id"))
            if not rewrite_span:
                continue
            es_ids = ps.get("evidence_span_ids", [])
            if rewrite_span not in es_ids:
                es_ids.append(rewrite_span)
            success_ids = ps.get("success_evidence_span_ids", [])
            if rewrite_span in success_ids:
                success_ids.remove(rewrite_span)

    # 7. Legacy field cleanup (strip old numeric fields, backfill defaults, etc.)
    output = _patch_legacy_fields(output)

    # 8. Clean up ASR artifacts in evidence_span excerpts and coaching blurbs
    if cleanup_enabled:
        try:
            from .quote_cleanup import cleanup_parsed_json
            cleanup_parsed_json(output)  # mutates in-place
        except Exception:
            logger.warning(
                "Quote cleanup failed in output_patches; raw text will be persisted",
                exc_info=True,
            )

    return output
