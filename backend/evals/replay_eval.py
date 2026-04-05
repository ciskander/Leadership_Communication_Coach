"""
replay_eval.py — Layer 1: Score Stability & Discriminant Validity.

Two modes:
  --mode repeat   Run one transcript N times, measure intra-transcript IQR.
  --mode compare  Run all transcripts in a directory (optionally N times each),
                  measure inter-transcript distribution per pattern.
                  Supports offline mode via --outputs-dir to analyze existing
                  output JSON files without making LLM calls.

Accepts raw transcript files (.vtt, .txt, .srt, .docx, .pdf) — the same
formats you upload through the UI. Files are parsed automatically using the
existing transcript parser.

Transcript directory layout:
  backend/evals/transcripts/
    eval_config.json           # shared defaults (meeting_type, target_role, etc.)
    meeting_alpha.vtt          # raw transcript files
    meeting_beta.txt
    meeting_beta.meta.json     # optional per-transcript metadata overrides

Usage:
  # Repeat: run one transcript 5 times
  python -m backend.evals.replay_eval --mode repeat \
    --transcript backend/evals/transcripts/meeting_alpha.vtt --runs 5

  # Repeat with per-opportunity alignment tables and evidence text
  python -m backend.evals.replay_eval --mode repeat \
    --transcript backend/evals/transcripts/meeting_alpha.vtt --runs 5 --detail

  # Compare: run all transcripts in directory, 3 times each
  python -m backend.evals.replay_eval --mode compare \
    --transcripts-dir backend/evals/transcripts --runs 3

  # Compare with raw reason code cross-tabulation
  python -m backend.evals.replay_eval --mode compare \
    --transcripts-dir backend/evals/transcripts --runs 3 --detail

  # Compare (offline): analyze existing output JSON files (no LLM calls)
  python -m backend.evals.replay_eval --mode compare \
    --outputs-dir path/to/output/json/files

  # Compare (offline + detail): includes raw reason code cross-tabulation
  python -m backend.evals.replay_eval --mode compare \
    --outputs-dir path/to/output/json/files --detail

Reports always include:
  - Score stability / discriminant validity tables
  - Per-opportunity tier usage (0.0 / 0.25 / 0.5 / 0.75 / 1.0 distribution)
  - Cross-meeting tier distributions per pattern (compare mode)
  - Reason code analysis grouped by tier (compare mode)

With --detail, reports additionally include:
  - Per-opportunity alignment tables (scores + reason codes across runs)
  - Truncated transcript evidence text per opportunity
  - Raw reason code frequency cross-tabulation (compare mode)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root to path so imports work when run as module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.config import OPENAI_MODEL_DEFAULT, OPENAI_MAX_TOKENS, ANTHROPIC_MAX_TOKENS, PATTERN_ORDER
from backend.core.editor import build_experiment_context, run_editor, merge_editor_output
from backend.core.gate1_validator import validate as gate1_validate
from backend.core.llm_client import call_llm, is_anthropic_model
from backend.core.models import MemoryBlock, OpenAIResponse, ParsedTranscript
from backend.core.openai_client import load_scoring_system_prompt
from backend.core.output_patches import patch_analysis_output
from backend.core.prompt_builder import (
    build_developer_message,
    build_single_meeting_prompt,
    build_stage2_system_prompt,
    build_stage2_user_message,
)
from backend.core.stage2_merge import merge_stage2_output
from backend.core.transcript_parser import parse_transcript
from backend.evals.report import (
    align_opportunities_cross_model,
    classify_opportunity_slots,
    collect_reason_codes,
    compute_consensus_comparison,
    compute_cross_pattern_summary,
    compute_pattern_stats,
    compute_int_stats,
    compute_tier_distribution,
    extract_opportunity_details,
    extract_opportunity_details_with_excerpts,
    format_cross_meeting_tier_distributions,
    format_cross_model_report,
    format_intra_transcript_report,
    format_inter_transcript_report,
    format_opportunity_alignment_table,
    format_reason_code_analysis_by_tier,
    format_reason_code_cross_tab,
    format_tier_distribution_table,
    save_report,
    save_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_EDITOR_ENABLED = os.getenv("EDITOR_ENABLED", "0") == "1"

_RESULTS_DIR = Path(__file__).parent / "results"

_SUPPORTED_EXTENSIONS = {".vtt", ".txt", ".srt", ".docx", ".pdf"}

# ── Default eval config ──────────────────────────────────────────────────────

_DEFAULT_EVAL_CONFIG = {
    "meeting_type": "cross_functional",
    "target_role": "chair",
    "meeting_date": "2026-01-01",
    "target_speaker_name": "Speaker",
    "target_speaker_label": "Speaker",
    "memory": {
        "baseline_profile": None,
        "coaching_history": [],
        "experiment_history": [],
        "active_experiment": None,
    },
}


# ── Transcript loading ───────────────────────────────────────────────────────

def _load_eval_config(transcripts_dir: Path) -> dict:
    """Load eval_config.json from the transcripts directory, or use defaults."""
    config_path = transcripts_dir / "eval_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        # Merge with defaults (config overrides defaults)
        merged = {**_DEFAULT_EVAL_CONFIG, **config}
        if "memory" not in config:
            merged["memory"] = _DEFAULT_EVAL_CONFIG["memory"]
        return merged
    return dict(_DEFAULT_EVAL_CONFIG)


def _load_per_transcript_meta(transcript_path: Path) -> dict | None:
    """Load optional per-transcript metadata override (e.g., meeting_alpha.meta.json)."""
    meta_path = transcript_path.with_suffix(".meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return None


def load_raw_transcript(
    transcript_path: Path,
    eval_config: dict,
) -> tuple[dict, ParsedTranscript, MemoryBlock]:
    """Load and parse a raw transcript file using the existing parser.

    Returns (metadata_dict, ParsedTranscript, MemoryBlock).
    """
    # Parse the transcript using the same parser as the UI upload
    raw_bytes = transcript_path.read_bytes()
    source_id = transcript_path.stem  # filename without extension as ID
    parsed = parse_transcript(raw_bytes, transcript_path.name, source_id)

    # Build metadata: start with eval_config, override with per-transcript meta
    per_meta = _load_per_transcript_meta(transcript_path) or {}
    metadata = {**eval_config, **per_meta}

    # Auto-detect target_speaker_label if not set and there's a dominant speaker
    if metadata.get("target_speaker_label") == "Speaker" and parsed.speaker_labels:
        # Use the most frequent speaker as target
        speaker_counts: dict[str, int] = defaultdict(int)
        for turn in parsed.turns:
            speaker_counts[turn.speaker_label] += 1
        most_frequent = max(speaker_counts, key=speaker_counts.get)  # type: ignore[arg-type]
        metadata["target_speaker_label"] = most_frequent
        if metadata.get("target_speaker_name") == "Speaker":
            metadata["target_speaker_name"] = most_frequent

    # Ensure meeting_id exists
    if "meeting_id" not in metadata:
        metadata["meeting_id"] = f"EVAL-{source_id}"

    # Build memory block
    mem_data = metadata.get("memory", {})
    memory = MemoryBlock(
        baseline_profile=mem_data.get("baseline_profile") if isinstance(mem_data, dict) else None,
        coaching_history=mem_data.get("coaching_history", []) if isinstance(mem_data, dict) else [],
        experiment_history=mem_data.get("experiment_history", []) if isinstance(mem_data, dict) else [],
        active_experiment=mem_data.get("active_experiment") if isinstance(mem_data, dict) else None,
    )

    return metadata, parsed, memory


def find_transcript_files(transcripts_dir: Path) -> list[Path]:
    """Find all supported transcript files in a directory."""
    files = []
    for ext in _SUPPORTED_EXTENSIONS:
        files.extend(transcripts_dir.glob(f"*{ext}"))
    return sorted(files)


# ── Single analysis run ──────────────────────────────────────────────────────

def run_single_analysis(
    metadata: dict,
    parsed_transcript: ParsedTranscript,
    memory: MemoryBlock,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Run one analysis through the full pipeline (prompt -> LLM -> gate1)."""
    model = model or OPENAI_MODEL_DEFAULT
    if max_tokens is None:
        max_tokens = ANTHROPIC_MAX_TOKENS if is_anthropic_model(model) else OPENAI_MAX_TOKENS

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

    sys_prompt = load_scoring_system_prompt()
    dev_message = build_developer_message()

    t0 = time.time()
    response = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=model,
        max_tokens=max_tokens,
    )
    elapsed = time.time() - t0

    # Apply shared post-LLM patches (same as production pipeline)
    patched_output = patch_analysis_output(
        response.parsed,
        prompt_meta=prompt_payload.meta,
        active_experiment=memory.active_experiment if memory else None,
        has_active_experiment=bool(memory and memory.active_experiment),
    )

    # Editor pass (optional 2nd LLM call)
    editor_changes_count = 0
    editor_prompt_tokens = 0
    editor_completion_tokens = 0
    editor_changelog: list[dict] = []
    editor_raw_output: dict | None = None
    if _EDITOR_ENABLED:
        exp_context = build_experiment_context(memory, patched_output)
        transcript_turns = prompt_payload.transcript_payload["turns"]
        editor_result, editor_prompt_tokens, editor_completion_tokens = run_editor(
            patched_output, transcript_turns, exp_context, model=model,
        )
        editor_raw_output = editor_result  # preserve full editor response
        patched_output, editor_changelog = merge_editor_output(
            patched_output, editor_result,
        )
        editor_changes_count = len(editor_changelog)
        logger.info(
            "Editor: %d changes, %d prompt tokens, %d completion tokens",
            editor_changes_count, editor_prompt_tokens, editor_completion_tokens,
        )

    # Rebuild response with patched output for Gate1
    patched_raw = json.dumps(patched_output, ensure_ascii=False, indent=2)
    response = OpenAIResponse(
        parsed=patched_output,
        raw_text=patched_raw,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
    )

    gate1_result = gate1_validate(response.raw_text)

    # Use corrected data when gate1 auto-fixed arithmetic errors
    parsed = gate1_result.corrected_data if gate1_result.corrected_data else response.parsed
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
        "editor_enabled": _EDITOR_ENABLED,
        "editor_changes_count": editor_changes_count,
        "editor_prompt_tokens": editor_prompt_tokens,
        "editor_completion_tokens": editor_completion_tokens,
        "editor_changelog": editor_changelog,
        "editor_raw_output": editor_raw_output,
    }


# ── Repeat mode ──────────────────────────────────────────────────────────────

def run_repeat(
    transcript_path: Path,
    n_runs: int,
    eval_config: dict,
    model: str | None = None,
    detail: bool = False,
) -> dict[str, Any]:
    """Run one transcript N times and compute intra-transcript stats."""
    metadata, parsed_transcript, memory = load_raw_transcript(transcript_path, eval_config)
    transcript_id = transcript_path.stem

    logger.info("=== Repeat mode: %s x %d runs ===", transcript_id, n_runs)
    logger.info("  Target speaker: %s", metadata["target_speaker_label"])
    logger.info("  Meeting type: %s", metadata["meeting_type"])
    logger.info("  Turns: %d | Words: %d", len(parsed_transcript.turns), parsed_transcript.metadata.word_count)

    runs: list[dict] = [{}] * n_runs  # preserve order

    # Prepare output dir and timestamp for incremental JSON saves
    results_dir = _RESULTS_DIR / transcript_id
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    def _run_one(i: int) -> tuple[int, dict]:
        logger.info("Run %d/%d for %s ...", i + 1, n_runs, transcript_id)
        try:
            result = run_single_analysis(metadata, parsed_transcript, memory, model=model)
            logger.info(
                "  Run %d: Gate1=%s | Tokens=%d | Time=%ss",
                i + 1,
                "PASS" if result["gate1_passed"] else "FAIL",
                result["prompt_tokens"] + result["completion_tokens"],
                result["elapsed_sec"],
            )
            # Save JSON immediately so results survive crashes
            if "parsed_json" in result:
                save_json(result["parsed_json"], results_dir / f"run_{i+1:03d}_{timestamp}.json")
            # Save editor output if present
            if result.get("editor_raw_output"):
                save_json(
                    result["editor_raw_output"],
                    results_dir / f"editor_{i+1:03d}_{timestamp}.json",
                )
            return i, result
        except Exception as e:
            logger.error("  Run %d failed: %s", i + 1, e)
            return i, {"error": str(e), "gate1_passed": False}

    # Cap concurrency at 2 for Anthropic to stay within 90K output TPM limit
    max_workers = 2 if is_anthropic_model(model) else n_runs
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_one, i) for i in range(n_runs)]
        for future in as_completed(futures):
            idx, result = future.result()
            runs[idx] = result

    gate1_passes = sum(1 for r in runs if r.get("gate1_passed"))
    gate1_pass_rate = gate1_passes / len(runs) if runs else 0

    # ── Extract per-opportunity details from each run ──
    per_run_opp_details: list[dict[str, list[dict]]] = []
    for r in runs:
        if "parsed_json" in r:
            per_run_opp_details.append(extract_opportunity_details(r["parsed_json"]))
        else:
            per_run_opp_details.append({})

    pattern_results: dict[str, dict] = {}
    tier_distributions: dict[str, dict] = {}
    reason_codes_by_pattern: dict[str, list[dict]] = {}

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

        # Collect per-run opportunity details for this pattern
        pattern_run_details = [rd.get(pid, []) for rd in per_run_opp_details]
        tier_distributions[pid] = compute_tier_distribution(pattern_run_details, pid)
        reason_codes_by_pattern[pid] = collect_reason_codes(
            pattern_run_details, transcript_id=transcript_id,
        )

    # Run JSONs already saved incrementally above; save report + markdown below

    report_data: dict[str, Any] = {
        "transcript_id": transcript_id,
        "n_runs": n_runs,
        "gate1_pass_rate": gate1_pass_rate,
        "model": runs[0].get("model", "unknown") if runs else "unknown",
        "timestamp": timestamp,
        "pattern_results": pattern_results,
        "tier_distributions": tier_distributions,
    }
    if detail:
        report_data["reason_codes"] = reason_codes_by_pattern

    save_json(report_data, results_dir / f"repeat_report_{timestamp}.json")

    # ── Build markdown report ──
    md = format_intra_transcript_report(transcript_id, n_runs, gate1_pass_rate, pattern_results)

    # Always: tier distribution summary table
    md += "\n" + format_tier_distribution_table(tier_distributions)

    # --detail: per-pattern opportunity alignment tables
    if detail:
        md += "\n\n## Opportunity Event Detail\n"
        for pid in PATTERN_ORDER:
            pattern_run_details = [rd.get(pid, []) for rd in per_run_opp_details]
            if any(pattern_run_details):
                md += "\n" + format_opportunity_alignment_table(
                    pid, pattern_run_details, n_runs,
                    parsed_transcript=parsed_transcript,
                    include_text=True,
                )
                md += "\n"

    save_report(md, results_dir / f"repeat_report_{timestamp}.md")

    # Return extra data for use by run_compare()
    report_data["_tier_distributions"] = tier_distributions
    report_data["_reason_codes"] = reason_codes_by_pattern
    return report_data


# ── Compare mode ─────────────────────────────────────────────────────────────

def run_compare(
    transcripts_dir: Path,
    n_runs: int,
    model: str | None = None,
    detail: bool = False,
) -> dict[str, Any]:
    """Run all transcripts in a directory and compute cross-transcript stats."""
    eval_config = _load_eval_config(transcripts_dir)
    transcript_files = find_transcript_files(transcripts_dir)

    if len(transcript_files) < 2:
        logger.error("Compare mode requires at least 2 transcript files. Found %d.", len(transcript_files))
        sys.exit(1)

    logger.info("=== Compare mode: %d transcripts x %d runs ===", len(transcript_files), n_runs)
    for f in transcript_files:
        logger.info("  %s", f.name)

    per_transcript: dict[str, dict] = {}
    per_transcript_tiers: dict[str, dict[str, dict]] = {}   # tid → pid → tier_dist
    per_transcript_reasons: dict[str, dict[str, list]] = {}  # tid → pid → reason_code list
    for transcript_path in transcript_files:
        report = run_repeat(transcript_path, n_runs, eval_config, model=model, detail=detail)
        tid = transcript_path.stem
        per_transcript[tid] = report["pattern_results"]
        per_transcript_tiers[tid] = report.get("_tier_distributions", {})
        per_transcript_reasons[tid] = report.get("_reason_codes", {})

    transcript_ids = [f.stem for f in transcript_files]
    cross_transcript: dict[str, dict] = {}

    for pid in PATTERN_ORDER:
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

        signal_to_noise = None
        if cross_stats["iqr"] is not None and mean_intra_iqr and mean_intra_iqr > 0:
            signal_to_noise = round(cross_stats["iqr"] / mean_intra_iqr, 2)

        cross_transcript[pid] = {
            "cross_iqr": cross_stats["iqr"],
            "cross_stdev": cross_stats["stdev"],
            "cross_mean": cross_stats["mean"],
            "cross_min": cross_stats["min"],
            "cross_max": cross_stats["max"],
            "mean_intra_iqr": mean_intra_iqr,
            "signal_to_noise": signal_to_noise,
        }

    # ── Build cross-meeting tier distributions and reason code analysis ──
    cross_tier_distributions: dict[str, dict[str, dict]] = {}  # pid → tid → tier_dist
    reason_code_analysis: dict[str, list[dict]] = {}  # pid → combined reason code list

    for pid in PATTERN_ORDER:
        cross_tier_distributions[pid] = {}
        all_reasons: list[dict] = []
        for tid in transcript_ids:
            cross_tier_distributions[pid][tid] = per_transcript_tiers.get(tid, {}).get(pid, {
                "total": 0, "tiers": {}, "tier_pcts": {}, "other_count": 0, "other_pct": 0,
            })
            all_reasons.extend(per_transcript_reasons.get(tid, {}).get(pid, []))
        reason_code_analysis[pid] = all_reasons

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    report_data: dict[str, Any] = {
        "transcript_ids": transcript_ids,
        "n_runs_per_transcript": n_runs,
        "timestamp": timestamp,
        "per_transcript": per_transcript,
        "cross_transcript": cross_transcript,
        "cross_tier_distributions": {
            pid: {tid: dist for tid, dist in tids.items()}
            for pid, tids in cross_tier_distributions.items()
        },
        "reason_code_analysis": {
            pid: codes for pid, codes in reason_code_analysis.items() if codes
        },
    }
    save_json(report_data, _RESULTS_DIR / f"compare_report_{timestamp}.json")

    # ── Build markdown report ──
    md = format_inter_transcript_report(transcript_ids, per_transcript, cross_transcript)

    # Always: cross-meeting tier distributions
    md += "\n\n## Cross-Meeting Tier Distributions\n"
    for pid in PATTERN_ORDER:
        md += "\n" + format_cross_meeting_tier_distributions(
            pid, transcript_ids, cross_tier_distributions[pid],
        )
        md += "\n"

    # Always: tier-grouped reason code analysis
    md += "\n## Reason Code Analysis (by tier)\n"
    for pid in PATTERN_ORDER:
        if reason_code_analysis.get(pid):
            md += "\n" + format_reason_code_analysis_by_tier(
                pid, reason_code_analysis[pid], transcript_ids,
            )

    # --detail: raw reason code cross-tabulation
    if detail:
        md += "\n\n## Reason Code Cross-Tabulation (raw)\n"
        for pid in PATTERN_ORDER:
            if reason_code_analysis.get(pid):
                md += "\n" + format_reason_code_cross_tab(
                    pid, reason_code_analysis[pid], transcript_ids,
                )
                md += "\n"

    save_report(md, _RESULTS_DIR / f"compare_report_{timestamp}.md")

    return report_data


# ── Offline compare mode ─────────────────────────────────────────────────────

def run_compare_offline(outputs_dir: Path, detail: bool = False, file_prefix: str = "run_") -> dict[str, Any]:
    """Load existing output JSON files and compute cross-meeting discriminant validity.

    Groups files by context.meeting_id (falls back to filename stem).
    Multiple files with the same meeting_id are treated as multiple runs.
    No LLM calls are made.
    """
    # Only load files matching the prefix to avoid contamination from editor,
    # judge, post_editor, and report files in the same directory tree.
    glob_pattern = f"{file_prefix}*.json"
    json_files = sorted(outputs_dir.rglob(glob_pattern))
    if not json_files:
        logger.error("No %s files found in %s", glob_pattern, outputs_dir)
        sys.exit(1)

    # Load and group by meeting_id
    meetings: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping %s: %s", f.name, e)
            skipped += 1
            continue

        if "pattern_snapshot" not in data and "opportunity_events" not in data:
            logger.warning("Skipping %s: no pattern_snapshot or opportunity_events", f.name)
            skipped += 1
            continue
        if "pattern_snapshot" not in data:
            logger.info("No pattern_snapshot in %s; will reconstruct from opportunity_events", f.name)

        meeting_id = None
        if isinstance(data.get("context"), dict):
            meeting_id = data["context"].get("meeting_id")
        if not meeting_id:
            meeting_id = f.stem
            logger.warning("No context.meeting_id in %s, using filename: %s", f.name, meeting_id)

        meetings[meeting_id].append(data)

    meeting_ids = sorted(meetings.keys())
    if len(meeting_ids) < 2:
        logger.error("Offline compare requires at least 2 distinct meeting_ids. Found %d.", len(meeting_ids))
        sys.exit(1)

    logger.info(
        "=== Offline compare: %d meetings, %d files (%d skipped) ===",
        len(meeting_ids), sum(len(v) for v in meetings.values()), skipped,
    )
    for mid in meeting_ids:
        logger.info("  %s: %d run(s)", mid, len(meetings[mid]))

    # Compute per-meeting pattern stats (mirrors run_repeat's pattern_results)
    per_transcript: dict[str, dict] = {}
    per_transcript_tiers: dict[str, dict[str, dict]] = {}   # mid → pid → tier_dist
    per_transcript_reasons: dict[str, dict[str, list]] = {}  # mid → pid → reason_code list

    for mid in meeting_ids:
        runs = meetings[mid]
        pattern_results: dict[str, dict] = {}

        # Extract per-opportunity details from each run's full JSON
        per_run_opp_details: list[dict[str, list[dict]]] = []
        for run_data in runs:
            if "opportunity_events" in run_data:
                per_run_opp_details.append(extract_opportunity_details(run_data))
            else:
                per_run_opp_details.append({})

        tier_distributions: dict[str, dict] = {}
        reason_codes_by_pattern: dict[str, list[dict]] = {}

        for pid in PATTERN_ORDER:
            scores: list[float | None] = []
            opp_counts: list[int | None] = []
            statuses: dict[str, int] = defaultdict(int)

            for run_idx, run_data in enumerate(runs):
                found = False
                for snap in run_data.get("pattern_snapshot", []):
                    if snap.get("pattern_id") == pid:
                        scores.append(snap.get("score"))
                        opp_counts.append(snap.get("opportunity_count"))
                        statuses[snap.get("evaluable_status", "unknown")] += 1
                        found = True
                        break
                if not found:
                    # Reconstruct from opportunity_events if available
                    oe_details = per_run_opp_details[run_idx].get(pid, [])
                    oe_scores = [o["success"] for o in oe_details if o.get("success") is not None]
                    if oe_scores:
                        reconstructed = sum(oe_scores) / len(oe_scores)
                        scores.append(reconstructed)
                        opp_counts.append(len(oe_scores))
                        statuses["reconstructed_from_oe"] += 1
                        logger.info("Reconstructed %s score (%.4f, %d opps) from OE data for run %d",
                                    pid, reconstructed, len(oe_scores), run_idx + 1)
                    else:
                        scores.append(None)
                        opp_counts.append(None)

            # Compute per-opportunity tier distributions and reason codes
            pattern_run_details = [rd.get(pid, []) for rd in per_run_opp_details]
            tier_distributions[pid] = compute_tier_distribution(pattern_run_details, pid)
            reason_codes_by_pattern[pid] = collect_reason_codes(
                pattern_run_details, transcript_id=mid,
            )

            pattern_results[pid] = {
                "score": compute_pattern_stats(scores),
                "opportunity_count": compute_int_stats(opp_counts),
                "oe_count": compute_int_stats([]),  # not available offline
                "status_distribution": dict(statuses),
            }

        per_transcript[mid] = pattern_results
        per_transcript_tiers[mid] = tier_distributions
        per_transcript_reasons[mid] = reason_codes_by_pattern

    # Compute cross-meeting stats (same logic as run_compare)
    cross_transcript: dict[str, dict] = {}
    for pid in PATTERN_ORDER:
        means: list[float] = []
        intra_iqrs: list[float] = []
        for mid in meeting_ids:
            tr = per_transcript.get(mid, {}).get(pid, {}).get("score", {})
            if tr.get("mean") is not None:
                means.append(tr["mean"])
            if tr.get("iqr") is not None:
                intra_iqrs.append(tr["iqr"])

        cross_stats = compute_pattern_stats(means)
        mean_intra_iqr = (
            round(sum(intra_iqrs) / len(intra_iqrs), 4) if intra_iqrs else None
        )
        signal_to_noise = None
        if cross_stats["iqr"] is not None and mean_intra_iqr and mean_intra_iqr > 0:
            signal_to_noise = round(cross_stats["iqr"] / mean_intra_iqr, 2)

        cross_transcript[pid] = {
            "cross_iqr": cross_stats["iqr"],
            "cross_stdev": cross_stats["stdev"],
            "cross_mean": cross_stats["mean"],
            "cross_min": cross_stats["min"],
            "cross_max": cross_stats["max"],
            "mean_intra_iqr": mean_intra_iqr,
            "signal_to_noise": signal_to_noise,
        }

    # ── Build cross-meeting tier distributions and reason code analysis ──
    cross_tier_distributions: dict[str, dict[str, dict]] = {}  # pid → mid → tier_dist
    reason_code_analysis: dict[str, list[dict]] = {}  # pid → combined reason code list

    for pid in PATTERN_ORDER:
        cross_tier_distributions[pid] = {}
        all_reasons: list[dict] = []
        for mid in meeting_ids:
            cross_tier_distributions[pid][mid] = per_transcript_tiers.get(mid, {}).get(pid, {
                "total": 0, "tiers": {}, "tier_pcts": {}, "other_count": 0, "other_pct": 0,
            })
            all_reasons.extend(per_transcript_reasons.get(mid, {}).get(pid, []))
        reason_code_analysis[pid] = all_reasons

    # Save reports
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    report_data: dict[str, Any] = {
        "transcript_ids": meeting_ids,
        "n_runs_per_transcript": {mid: len(meetings[mid]) for mid in meeting_ids},
        "source": "offline",
        "timestamp": timestamp,
        "per_transcript": per_transcript,
        "cross_transcript": cross_transcript,
        "cross_tier_distributions": {
            pid: {mid: dist for mid, dist in mids.items()}
            for pid, mids in cross_tier_distributions.items()
        },
        "reason_code_analysis": {
            pid: codes for pid, codes in reason_code_analysis.items() if codes
        },
    }
    save_json(report_data, _RESULTS_DIR / f"compare_offline_report_{timestamp}.json")

    # ── Build markdown report ──
    md = format_inter_transcript_report(meeting_ids, per_transcript, cross_transcript)

    # Always: cross-meeting tier distributions
    md += "\n\n## Cross-Meeting Tier Distributions\n"
    for pid in PATTERN_ORDER:
        md += "\n" + format_cross_meeting_tier_distributions(
            pid, meeting_ids, cross_tier_distributions[pid],
        )
        md += "\n"

    # Always: tier-grouped reason code analysis
    md += "\n## Reason Code Analysis (by tier)\n"
    for pid in PATTERN_ORDER:
        if reason_code_analysis.get(pid):
            md += "\n" + format_reason_code_analysis_by_tier(
                pid, reason_code_analysis[pid], meeting_ids,
            )

    # --detail: raw reason code cross-tabulation
    if detail:
        md += "\n\n## Reason Code Cross-Tabulation (raw)\n"
        for pid in PATTERN_ORDER:
            if reason_code_analysis.get(pid):
                md += "\n" + format_reason_code_cross_tab(
                    pid, reason_code_analysis[pid], meeting_ids,
                )
                md += "\n"

    save_report(md, _RESULTS_DIR / f"compare_offline_report_{timestamp}.md")

    return report_data


# ── Cross-model comparison ───────────────────────────────────────────────


def _load_model_runs(
    model_dir: Path,
) -> dict[str, list[dict]]:
    """Load run JSONs from a model directory, grouped by meeting subdirectory.

    Returns meeting_id → list of parsed JSON dicts.
    """
    meetings: dict[str, list[dict]] = defaultdict(list)
    for subdir in sorted(model_dir.iterdir()):
        if not subdir.is_dir():
            continue
        meeting_id = subdir.name
        for f in sorted(subdir.glob("*.json")):
            # Skip report files
            if "report" in f.name or "compare" in f.name:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Skipping %s: %s", f, e)
                continue
            if "opportunity_events" not in data and "pattern_snapshot" not in data:
                logger.warning("Skipping %s: no opportunity_events or pattern_snapshot", f.name)
                continue
            meetings[meeting_id].append(data)
    return dict(meetings)


def run_cross_model(
    model_a_dir: Path,
    model_b_dir: Path,
    model_a_label: str | None = None,
    model_b_label: str | None = None,
    detail: bool = False,
) -> dict:
    """Compare OE-level results between two models.

    No LLM calls — purely offline analysis of existing run JSONs.
    """
    # Load runs
    a_meetings = _load_model_runs(model_a_dir)
    b_meetings = _load_model_runs(model_b_dir)

    # Find common meetings
    common = sorted(set(a_meetings) & set(b_meetings))
    a_only_meetings = sorted(set(a_meetings) - set(b_meetings))
    b_only_meetings = sorted(set(b_meetings) - set(a_meetings))

    if not common:
        logger.error("No common meetings found between %s and %s", model_a_dir, model_b_dir)
        sys.exit(1)

    label_a = model_a_label or model_a_dir.name
    label_b = model_b_label or model_b_dir.name

    logger.info("=== Cross-model comparison: %s vs %s ===", label_a, label_b)
    logger.info("  Common meetings: %d", len(common))
    for mid in common:
        logger.info("    %s: A=%d runs, B=%d runs", mid, len(a_meetings[mid]), len(b_meetings[mid]))
    if a_only_meetings:
        logger.info("  Model A only: %s", a_only_meetings)
    if b_only_meetings:
        logger.info("  Model B only: %s", b_only_meetings)

    # Extract OE details with excerpts for each run
    a_run_details: dict[str, list[dict]] = {}
    b_run_details: dict[str, list[dict]] = {}
    for mid in common:
        a_run_details[mid] = [
            extract_opportunity_details_with_excerpts(run_data)
            for run_data in a_meetings[mid]
        ]
        b_run_details[mid] = [
            extract_opportunity_details_with_excerpts(run_data)
            for run_data in b_meetings[mid]
        ]

    # Align and classify per meeting × pattern
    all_results: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for mid in common:
        all_results[mid] = {}
        for pid in PATTERN_ORDER:
            slots = align_opportunities_cross_model(
                a_run_details[mid], b_run_details[mid], pid,
            )
            classified = classify_opportunity_slots(slots)
            all_results[mid][pid] = classified

            # Log summary
            n_cons = len(classified["consensus"])
            n_ao = len(classified["a_only"])
            n_bo = len(classified["b_only"])
            n_disp = len(classified["disputed"])
            total = n_cons + n_ao + n_bo + n_disp
            if total > 0:
                logger.info(
                    "  %s/%s: %d slots — %d consensus, %d A-only, %d B-only, %d disputed",
                    mid, pid, total, n_cons, n_ao, n_bo, n_disp,
                )

    # Cross-pattern summary
    cross_summary = compute_cross_pattern_summary(all_results, PATTERN_ORDER)

    # Build report data
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    report_data = {
        "model_a_label": label_a,
        "model_b_label": label_b,
        "model_a_dir": str(model_a_dir),
        "model_b_dir": str(model_b_dir),
        "common_meetings": common,
        "a_only_meetings": a_only_meetings,
        "b_only_meetings": b_only_meetings,
        "timestamp": timestamp,
        "cross_pattern_summary": cross_summary,
        "per_meeting_pattern": {},
    }

    # Serialize per-meeting detail for JSON (compute consensus comparisons)
    for mid in common:
        report_data["per_meeting_pattern"][mid] = {}
        for pid in PATTERN_ORDER:
            classified = all_results[mid][pid]
            serialized: dict[str, list] = {}
            for category in ["consensus", "a_only", "b_only", "disputed"]:
                items = []
                for slot in classified.get(category, []):
                    if category == "consensus":
                        items.append(compute_consensus_comparison(slot))
                    else:
                        items.append({
                            "turn_start_id": slot["turn_start_id"],
                            "a_rate": slot["a_rate"],
                            "b_rate": slot["b_rate"],
                            "a_count": slot["a_count"],
                            "b_count": slot["b_count"],
                            "a_scores": slot["a_scores"],
                            "b_scores": slot["b_scores"],
                            "a_reason_codes": slot["a_reason_codes"],
                            "b_reason_codes": slot["b_reason_codes"],
                        })
                serialized[category] = items
            report_data["per_meeting_pattern"][mid][pid] = serialized

    # Save JSON
    save_json(report_data, _RESULTS_DIR / f"cross_model_report_{timestamp}.json")

    # Generate and save markdown
    md = format_cross_model_report(
        model_a_label=label_a,
        model_b_label=label_b,
        common_meetings=common,
        all_results=all_results,
        cross_pattern_summary=cross_summary,
        pattern_order=PATTERN_ORDER,
        detail=detail,
    )
    save_report(md, _RESULTS_DIR / f"cross_model_report_{timestamp}.md")

    return report_data


# ── Long-stability mode ─────────────────────────────────────────────────────


def _enumerate_longitudinal_meetings(
    phase_dirs: list[Path],
    persona_filter: list[int] | None = None,
    meeting_filter: list[int] | None = None,
) -> list[dict]:
    """Scan longitudinal phase directories for persona/meeting subdirectories.

    Returns a list of meeting descriptors with metadata and a phase-prefixed
    label to avoid collisions across phase dirs (e.g., "LS01-P01-M01").
    """
    meetings = []
    for phase_dir in phase_dirs:
        phase_dir = phase_dir.resolve()
        if not phase_dir.is_dir():
            logger.warning("Phase dir does not exist: %s", phase_dir)
            continue

        # Derive short prefix: Long_Scale_01 → LS01
        dir_name = phase_dir.name
        m = re.match(r"Long_Scale_(\d+)", dir_name)
        prefix = f"LS{m.group(1)}" if m else dir_name[:4]

        for persona_dir in sorted(phase_dir.iterdir()):
            pm = re.match(r"persona_(\d+)", persona_dir.name)
            if not pm or not persona_dir.is_dir():
                continue
            persona_idx = int(pm.group(1))
            if persona_filter and persona_idx not in persona_filter:
                continue

            for meeting_dir in sorted(persona_dir.iterdir()):
                mm = re.match(r"meeting_(\d+)", meeting_dir.name)
                if not mm or not meeting_dir.is_dir():
                    continue
                meeting_number = int(mm.group(1))
                if meeting_filter and meeting_number not in meeting_filter:
                    continue

                transcript_path = meeting_dir / "transcript.txt"
                metadata_path = meeting_dir / "metadata.json"
                if not transcript_path.exists() or not metadata_path.exists():
                    logger.warning(
                        "Skipping %s/%s: missing transcript.txt or metadata.json",
                        persona_dir.name, meeting_dir.name,
                    )
                    continue

                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                meetings.append({
                    "persona_idx": persona_idx,
                    "meeting_number": meeting_number,
                    "meeting_dir": meeting_dir,
                    "transcript_path": transcript_path,
                    "metadata": metadata,
                    "meeting_label": f"{prefix}-P{persona_idx:02d}-M{meeting_number:02d}",
                    "phase_dir": phase_dir,
                })

    logger.info("Enumerated %d meetings from %d phase dir(s)", len(meetings), len(phase_dirs))
    return meetings


def _load_longitudinal_transcript(meeting_dir: Path, metadata: dict) -> ParsedTranscript:
    """Load and parse a transcript from a longitudinal eval meeting directory."""
    transcript_path = meeting_dir / "transcript.txt"
    return parse_transcript(
        data=transcript_path.read_bytes(),
        filename="transcript.txt",
        source_id=metadata["meeting_id"],
    )


def _run_two_stage_analysis(
    metadata: dict,
    parsed_transcript: ParsedTranscript,
    memory: MemoryBlock,
    model: str | None,
    scoring_sys_prompt: str,
    dev_message: str,
) -> dict[str, Any]:
    """Run the production two-stage pipeline (scoring + coaching).

    Mirrors _process_meeting() in longitudinal_eval.py but returns a flat dict
    suitable for stability analysis. Uses pre-loaded system prompts for efficiency.
    """
    t0 = time.time()
    model = model or OPENAI_MODEL_DEFAULT

    # ── Stage 1: Scoring ──
    prompt_payload = build_single_meeting_prompt(
        meeting_id=metadata["meeting_id"],
        meeting_type=metadata.get("meeting_type", "single_meeting"),
        meeting_date=metadata.get("meeting_date", "2026-01-01"),
        target_role=metadata.get("target_role", "participant"),
        target_speaker_name=metadata.get("target_speaker_name", "Speaker"),
        target_speaker_label=metadata.get("target_speaker_label", "Speaker"),
        parsed_transcript=parsed_transcript,
        memory=memory,
    )

    s1_response = call_llm(
        system_prompt=scoring_sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=model,
    )
    stage1_tokens = s1_response.prompt_tokens + s1_response.completion_tokens

    # Post-LLM patches (scoring-only)
    stage1_parsed = patch_analysis_output(
        s1_response.parsed,
        prompt_meta=prompt_payload.meta,
        scoring_only=True,
        cleanup_enabled=False,
    )

    # Gate1 validation (scoring-only)
    stage1_raw = json.dumps(stage1_parsed, ensure_ascii=False, indent=2)
    gate1_result = gate1_validate(stage1_raw, mode="scoring_only")
    if gate1_result.corrected_data:
        stage1_parsed = gate1_result.corrected_data

    if not gate1_result.passed:
        elapsed = time.time() - t0
        return {
            "parsed_json": stage1_parsed,
            "pattern_scores": {},
            "pattern_opp_counts": {},
            "pattern_statuses": {},
            "pattern_oe_counts": {},
            "gate1_passed": False,
            "stage1_tokens": stage1_tokens,
            "stage2_tokens": 0,
            "elapsed_sec": round(elapsed, 1),
            "error": f"Stage 1 Gate1 failed: {len(gate1_result.issues)} issues",
        }

    # ── Stage 2: Coaching ──
    s2_sys_prompt = build_stage2_system_prompt(memory)
    transcript_turns = prompt_payload.transcript_payload["turns"]
    s2_user_msg = build_stage2_user_message(stage1_parsed, transcript_turns)

    s2_response = call_llm(
        system_prompt=s2_sys_prompt,
        developer_message="",
        user_message=s2_user_msg,
        model=model,
    )
    stage2_tokens = s2_response.prompt_tokens + s2_response.completion_tokens

    # Merge Stage 2 into Stage 1
    merged, _changelog = merge_stage2_output(stage1_parsed, s2_response.parsed)
    patched = patch_analysis_output(merged, scoring_only=False)

    # Gate1 validation (full)
    gate1_result_full = gate1_validate(
        json.dumps(patched, ensure_ascii=False, indent=2), mode="full"
    )
    final = gate1_result_full.corrected_data or patched

    # Extract pattern data (same logic as run_single_analysis)
    pattern_scores: dict[str, float | None] = {}
    pattern_opp_counts: dict[str, int | None] = {}
    pattern_statuses: dict[str, str] = {}
    pattern_oe_counts: dict[str, int] = defaultdict(int)

    for snap in final.get("pattern_snapshot", []):
        pid = snap.get("pattern_id")
        if pid:
            pattern_scores[pid] = snap.get("score")
            pattern_opp_counts[pid] = snap.get("opportunity_count")
            pattern_statuses[pid] = snap.get("evaluable_status", "unknown")

    for oe in final.get("opportunity_events", []):
        pid = oe.get("pattern_id")
        if pid and oe.get("count_decision") == "counted":
            pattern_oe_counts[pid] += 1

    elapsed = time.time() - t0
    return {
        "parsed_json": final,
        "pattern_scores": dict(pattern_scores),
        "pattern_opp_counts": dict(pattern_opp_counts),
        "pattern_statuses": dict(pattern_statuses),
        "pattern_oe_counts": dict(pattern_oe_counts),
        "gate1_passed": gate1_result_full.passed,
        "stage1_tokens": stage1_tokens,
        "stage2_tokens": stage2_tokens,
        "elapsed_sec": round(elapsed, 1),
        "error": None,
    }


def run_longitudinal_stability(
    phase_dirs: list[Path],
    n_runs: int = 5,
    persona_filter: list[int] | None = None,
    meeting_filter: list[int] | None = None,
    model: str | None = None,
    detail: bool = False,
    phase_name: str = "Stability_Scale_01",
) -> dict[str, Any]:
    """Run stability analysis across longitudinal eval meetings.

    For each selected meeting, runs the two-stage pipeline n_runs times with
    empty memory, then computes intra-meeting (repeatability) and cross-meeting
    (discriminant validity) statistics.
    """
    # 1. Enumerate meetings
    meetings = _enumerate_longitudinal_meetings(phase_dirs, persona_filter, meeting_filter)
    if not meetings:
        logger.error("No meetings found in phase dirs: %s", phase_dirs)
        return {}

    # 2. Load system prompts once
    scoring_sys_prompt = load_scoring_system_prompt()
    dev_message = build_developer_message()
    empty_memory = MemoryBlock()

    # 3. Load all transcripts eagerly
    transcripts: dict[str, ParsedTranscript] = {}
    for m in meetings:
        label = m["meeting_label"]
        transcripts[label] = _load_longitudinal_transcript(m["meeting_dir"], m["metadata"])
    logger.info("Loaded %d transcripts", len(transcripts))

    # 4. Build flat task list with crash recovery
    tasks: list[tuple[dict, int]] = []
    existing_results: dict[str, dict[int, dict]] = defaultdict(dict)  # label → {run_idx → result}

    for m in meetings:
        label = m["meeting_label"]
        stability_dir = m["meeting_dir"] / "stability"
        stability_dir.mkdir(exist_ok=True)

        for run_idx in range(1, n_runs + 1):
            run_path = stability_dir / f"run_{run_idx:02d}.json"
            if run_path.exists():
                # Crash recovery: load existing run
                try:
                    run_data = json.loads(run_path.read_text(encoding="utf-8"))
                    # Extract pattern scores from saved results
                    scores: dict[str, float | None] = {}
                    opp_counts: dict[str, int | None] = {}
                    statuses: dict[str, str] = {}
                    oe_counts: dict[str, int] = defaultdict(int)
                    for snap in run_data.get("pattern_snapshot", []):
                        pid = snap.get("pattern_id")
                        if pid:
                            scores[pid] = snap.get("score")
                            opp_counts[pid] = snap.get("opportunity_count")
                            statuses[pid] = snap.get("evaluable_status", "unknown")
                    for oe in run_data.get("opportunity_events", []):
                        pid = oe.get("pattern_id")
                        if pid and oe.get("count_decision") == "counted":
                            oe_counts[pid] += 1

                    existing_results[label][run_idx] = {
                        "parsed_json": run_data,
                        "pattern_scores": scores,
                        "pattern_opp_counts": opp_counts,
                        "pattern_statuses": statuses,
                        "pattern_oe_counts": dict(oe_counts),
                        "gate1_passed": True,  # assume passed if saved
                        "error": None,
                    }
                    logger.info("Recovered existing run: %s/run_%02d", label, run_idx)
                except Exception as exc:
                    logger.warning("Failed to load existing %s: %s", run_path, exc)
                    tasks.append((m, run_idx))
            else:
                tasks.append((m, run_idx))

    logger.info(
        "Task list: %d new runs needed (%d recovered from prior runs)",
        len(tasks), sum(len(v) for v in existing_results.values()),
    )

    # 5. Execute all tasks concurrently
    max_workers = max(len(tasks), 1)
    completed_results: dict[str, dict[int, dict]] = defaultdict(dict)

    def _execute_task(meeting_desc: dict, run_idx: int) -> tuple[str, int, dict]:
        label = meeting_desc["meeting_label"]
        parsed_transcript = transcripts[label]
        stability_dir = meeting_desc["meeting_dir"] / "stability"

        # Retry wrapper: retry full two-stage once on failure
        for attempt in range(2):
            try:
                result = _run_two_stage_analysis(
                    metadata=meeting_desc["metadata"],
                    parsed_transcript=parsed_transcript,
                    memory=empty_memory,
                    model=model,
                    scoring_sys_prompt=scoring_sys_prompt,
                    dev_message=dev_message,
                )
                # Save result immediately
                save_json(result["parsed_json"], stability_dir / f"run_{run_idx:02d}.json")
                return label, run_idx, result
            except Exception as exc:
                if attempt == 0:
                    logger.warning(
                        "%s run_%02d attempt 1 failed (%s), retrying...",
                        label, run_idx, exc,
                    )
                else:
                    logger.error(
                        "%s run_%02d failed after retry: %s", label, run_idx, exc,
                    )
                    return label, run_idx, {
                        "parsed_json": {},
                        "pattern_scores": {},
                        "pattern_opp_counts": {},
                        "pattern_statuses": {},
                        "pattern_oe_counts": {},
                        "gate1_passed": False,
                        "error": str(exc),
                        "stage1_tokens": 0,
                        "stage2_tokens": 0,
                        "elapsed_sec": 0,
                    }
        # unreachable, but satisfies type checker
        raise RuntimeError("unreachable")

    if tasks:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_execute_task, m, ri): (m["meeting_label"], ri)
                for m, ri in tasks
            }
            for future in as_completed(futures):
                label, run_idx = futures[future]
                try:
                    lbl, ri, result = future.result()
                    completed_results[lbl][ri] = result
                    status = "OK" if not result.get("error") else f"ERROR: {result['error']}"
                    logger.info("Completed %s/run_%02d — %s", lbl, ri, status)
                except Exception as exc:
                    logger.error("Unexpected failure %s/run_%02d: %s", label, run_idx, exc)

    # 6. Merge existing + new results, compute per-meeting stats
    all_results: dict[str, dict[int, dict]] = {}
    for m in meetings:
        label = m["meeting_label"]
        merged_runs = {**existing_results.get(label, {}), **completed_results.get(label, {})}
        all_results[label] = merged_runs

    per_meeting_stats: dict[str, dict] = {}
    total_tokens = {"stage1": 0, "stage2": 0}
    total_gate1_passed = 0
    total_runs = 0

    for m in meetings:
        label = m["meeting_label"]
        runs = all_results[label]
        valid_runs = {ri: r for ri, r in runs.items() if not r.get("error")}
        n_valid = len(valid_runs)
        n_total = len(runs)

        # Token tracking
        for r in runs.values():
            total_tokens["stage1"] += r.get("stage1_tokens", 0)
            total_tokens["stage2"] += r.get("stage2_tokens", 0)
            total_runs += 1
            if r.get("gate1_passed"):
                total_gate1_passed += 1

        # Per-pattern stats
        pattern_results: dict[str, dict] = {}
        all_run_details: list[list[dict]] = []

        for pid in PATTERN_ORDER:
            scores = [r["pattern_scores"].get(pid) for r in valid_runs.values()]
            opp_counts = [r["pattern_opp_counts"].get(pid) for r in valid_runs.values()]
            oe_counts = [r["pattern_oe_counts"].get(pid, 0) for r in valid_runs.values()]

            pattern_results[pid] = {
                "score": compute_pattern_stats(scores),
                "opportunity_count": compute_int_stats(opp_counts),
                "oe_count": compute_int_stats(oe_counts),
            }

        # Opportunity details for tier distributions
        for ri in sorted(valid_runs.keys()):
            details = extract_opportunity_details(valid_runs[ri]["parsed_json"])
            all_run_details.append(
                [item for detail_list in details.values() for item in detail_list]
            )

        tier_distributions = {}
        reason_codes_all = []
        for pid in PATTERN_ORDER:
            tier_distributions[pid] = compute_tier_distribution(all_run_details, pid)
            reason_codes_all.extend(collect_reason_codes(all_run_details, label))

        gate1_pass_rate = sum(1 for r in valid_runs.values() if r.get("gate1_passed")) / max(n_valid, 1)

        # Save intra-meeting report
        stability_dir = m["meeting_dir"] / "stability"
        intra_report = {
            "meeting_label": label,
            "n_runs": n_total,
            "n_valid": n_valid,
            "gate1_pass_rate": gate1_pass_rate,
            "pattern_results": pattern_results,
            "tier_distributions": tier_distributions,
        }
        save_json(intra_report, stability_dir / "intra_report.json")

        # Generate intra-meeting markdown
        intra_md = format_intra_transcript_report(label, n_valid, gate1_pass_rate, pattern_results)
        save_report(intra_md, stability_dir / "intra_report.md")

        per_meeting_stats[label] = {
            "pattern_results": pattern_results,
            "n_valid": n_valid,
            "gate1_pass_rate": gate1_pass_rate,
        }

    # 7. Cross-meeting discriminant validity (SNR)
    cross_transcript: dict[str, dict] = {}
    per_transcript_for_report: dict[str, dict] = {}

    for pid in PATTERN_ORDER:
        # Collect per-meeting means for cross-meeting stats
        meeting_means: list[float | None] = []
        intra_iqrs: list[float] = []

        for label in sorted(per_meeting_stats.keys()):
            pr = per_meeting_stats[label]["pattern_results"].get(pid, {})
            score_stats = pr.get("score", {})
            meeting_means.append(score_stats.get("mean"))
            iqr = score_stats.get("iqr")
            if iqr is not None:
                intra_iqrs.append(iqr)

        cross_stats = compute_pattern_stats(meeting_means)
        mean_intra_iqr = round(sum(intra_iqrs) / len(intra_iqrs), 4) if intra_iqrs else None
        snr = (
            round(cross_stats["iqr"] / mean_intra_iqr, 2)
            if cross_stats["iqr"] is not None and mean_intra_iqr and mean_intra_iqr > 0
            else None
        )

        cross_transcript[pid] = {
            # Raw stats (for stability_stats.json)
            **cross_stats,
            "mean_intra_iqr": mean_intra_iqr,
            "snr": snr,
            # Aliased keys for format_inter_transcript_report()
            "cross_min": cross_stats.get("min"),
            "cross_max": cross_stats.get("max"),
            "cross_mean": cross_stats.get("mean"),
            "cross_iqr": cross_stats.get("iqr"),
            "cross_stdev": cross_stats.get("stdev"),
            "signal_to_noise": snr,
        }

    # Build per_transcript dict for format_inter_transcript_report
    # format expects: per_transcript[tid][pid]["score"]["mean"]
    for label in sorted(per_meeting_stats.keys()):
        per_transcript_for_report[label] = {}
        for pid in PATTERN_ORDER:
            pr = per_meeting_stats[label]["pattern_results"].get(pid, {})
            per_transcript_for_report[label][pid] = {"score": pr.get("score", {})}

    transcript_ids = sorted(per_meeting_stats.keys())

    # 8. Generate aggregate report
    aggregate_md = format_inter_transcript_report(transcript_ids, per_transcript_for_report, cross_transcript)

    # 9. Save aggregate outputs
    aggregate_dir = _RESULTS_DIR / phase_name
    aggregate_dir.mkdir(parents=True, exist_ok=True)

    save_report(aggregate_md, aggregate_dir / "stability_report.md")

    stability_stats = {
        "phase_name": phase_name,
        "phase_dirs": [str(d) for d in phase_dirs],
        "n_meetings": len(meetings),
        "n_runs_per_meeting": n_runs,
        "total_runs_executed": total_runs,
        "total_gate1_passed": total_gate1_passed,
        "total_tokens": total_tokens,
        "model": model or OPENAI_MODEL_DEFAULT,
        "cross_transcript": cross_transcript,
        "per_meeting": {
            label: {
                "n_valid": per_meeting_stats[label]["n_valid"],
                "gate1_pass_rate": per_meeting_stats[label]["gate1_pass_rate"],
                "pattern_score_stats": {
                    pid: per_meeting_stats[label]["pattern_results"].get(pid, {}).get("score", {})
                    for pid in PATTERN_ORDER
                },
            }
            for label in transcript_ids
        },
    }
    save_json(stability_stats, aggregate_dir / "stability_stats.json")

    manifest = {
        "phase_name": phase_name,
        "phase_dirs": [str(d) for d in phase_dirs],
        "meetings": [
            {
                "label": m["meeting_label"],
                "meeting_dir": str(m["meeting_dir"]),
                "persona_idx": m["persona_idx"],
                "meeting_number": m["meeting_number"],
            }
            for m in meetings
        ],
        "n_runs": n_runs,
        "model": model or OPENAI_MODEL_DEFAULT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_json(manifest, aggregate_dir / "manifest.json")

    logger.info(
        "Stability eval complete: %d meetings × %d runs, "
        "total tokens: stage1=%d stage2=%d",
        len(meetings), n_runs,
        total_tokens["stage1"], total_tokens["stage2"],
    )

    return stability_stats


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Layer 1: Score Stability & Discriminant Validity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # Run one transcript 5 times (repeatability test)
  python -m backend.evals.replay_eval --mode repeat \\
    --transcript backend/evals/transcripts/meeting.vtt --runs 5

  # Run all transcripts in a directory, 3 times each (discriminant validity)
  python -m backend.evals.replay_eval --mode compare \\
    --transcripts-dir backend/evals/transcripts --runs 3

  # Offline compare: analyze existing output JSON files (no LLM calls)
  python -m backend.evals.replay_eval --mode compare \\
    --outputs-dir path/to/output/json/files

  # Cross-model comparison: compare OEs from two model output dirs
  python -m backend.evals.replay_eval --mode cross-model \\
    --model-a-dir path/to/model_a/results \\
    --model-b-dir path/to/model_b/results
""",
    )
    parser.add_argument("--mode", choices=["repeat", "compare", "cross-model", "long-stability"], required=True)
    parser.add_argument(
        "--transcript", type=Path,
        help="Path to a raw transcript file (.vtt, .txt, .srt, .docx, .pdf) for repeat mode",
    )
    parser.add_argument(
        "--transcripts-dir", type=Path,
        help="Directory containing transcript files for compare mode",
    )
    parser.add_argument("--runs", type=int, default=5, help="Number of runs per transcript (default: 5)")
    parser.add_argument("--model", type=str, default=None, help="Model override (e.g., claude-sonnet-4-6)")
    parser.add_argument(
        "--outputs-dir", type=Path,
        help="Directory of existing output JSON files for offline compare (no LLM calls)",
    )
    parser.add_argument(
        "--detail", action="store_true", default=False,
        help="Include per-opportunity alignment tables, evidence text, and raw reason code cross-tabs",
    )
    parser.add_argument(
        "--file-prefix", type=str, default="run_",
        help="Glob prefix for JSON files in offline compare (default: 'run_'). "
             "Use 'stage2_merged_run_' for Stage 2 merged outputs, 'post_editor_' for PE outputs.",
    )
    parser.add_argument(
        "--model-a-dir", type=Path,
        help="Directory of Model A output JSON files for cross-model mode",
    )
    parser.add_argument(
        "--model-b-dir", type=Path,
        help="Directory of Model B output JSON files for cross-model mode",
    )
    parser.add_argument(
        "--model-a-label", type=str, default=None,
        help="Display label for Model A (default: inferred from directory name)",
    )
    parser.add_argument(
        "--model-b-label", type=str, default=None,
        help="Display label for Model B (default: inferred from directory name)",
    )
    # Long-stability mode arguments
    parser.add_argument(
        "--phase-dir", type=Path, action="append", default=None,
        help="Longitudinal phase directory (can be repeated for multiple phase dirs)",
    )
    parser.add_argument(
        "--phase", type=str, default=None,
        help="Name for the aggregate output directory (e.g., Stability_Scale_01)",
    )
    parser.add_argument(
        "--meetings", type=str, default=None,
        help="Comma-separated meeting numbers to include (e.g., '1,4,8')",
    )
    parser.add_argument(
        "--personas", type=str, default=None,
        help="Comma-separated persona indices to include (e.g., '1,2,3')",
    )
    args = parser.parse_args()

    if args.mode == "repeat":
        if not args.transcript:
            parser.error("--transcript is required for repeat mode")
        eval_config = _load_eval_config(args.transcript.parent)
        run_repeat(args.transcript, args.runs, eval_config, model=args.model, detail=args.detail)

    elif args.mode == "compare":
        if args.outputs_dir:
            # Offline mode: load existing output JSON files
            if args.transcripts_dir:
                logger.warning("--transcripts-dir is ignored in offline mode (--outputs-dir)")
            if args.model:
                logger.warning("--model is ignored in offline mode (--outputs-dir)")
            if args.runs != 5:
                logger.warning("--runs is ignored in offline mode (--outputs-dir)")
            run_compare_offline(args.outputs_dir, detail=args.detail, file_prefix=args.file_prefix)
        elif args.transcripts_dir:
            run_compare(args.transcripts_dir, args.runs, model=args.model, detail=args.detail)
        else:
            parser.error("--transcripts-dir or --outputs-dir is required for compare mode")

    elif args.mode == "cross-model":
        if not args.model_a_dir or not args.model_b_dir:
            parser.error("--model-a-dir and --model-b-dir are required for cross-model mode")
        run_cross_model(
            model_a_dir=args.model_a_dir,
            model_b_dir=args.model_b_dir,
            model_a_label=args.model_a_label,
            model_b_label=args.model_b_label,
            detail=args.detail,
        )

    elif args.mode == "long-stability":
        if not args.phase_dir:
            parser.error("--phase-dir is required for long-stability mode (can be repeated)")
        if not args.phase:
            parser.error("--phase is required for long-stability mode")
        meeting_filter = [int(x) for x in args.meetings.split(",")] if args.meetings else None
        persona_filter = [int(x) for x in args.personas.split(",")] if args.personas else None
        run_longitudinal_stability(
            phase_dirs=args.phase_dir,
            n_runs=args.runs,
            persona_filter=persona_filter,
            meeting_filter=meeting_filter,
            model=args.model,
            detail=args.detail,
            phase_name=args.phase,
        )


if __name__ == "__main__":
    main()
