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
from backend.core.gate1_validator import validate as gate1_validate
from backend.core.llm_client import call_llm, is_anthropic_model
from backend.core.models import MemoryBlock, ParsedTranscript
from backend.core.openai_client import load_system_prompt
from backend.core.prompt_builder import build_developer_message, build_single_meeting_prompt
from backend.core.transcript_parser import parse_transcript
from backend.evals.report import (
    collect_reason_codes,
    compute_pattern_stats,
    compute_int_stats,
    compute_tier_distribution,
    extract_opportunity_details,
    format_cross_meeting_tier_distributions,
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
        "recent_pattern_snapshots": [],
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
        recent_pattern_snapshots=mem_data.get("recent_pattern_snapshots", []) if isinstance(mem_data, dict) else [],
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

    sys_prompt = load_system_prompt()
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
            return i, result
        except Exception as e:
            logger.error("  Run %d failed: %s", i + 1, e)
            return i, {"error": str(e), "gate1_passed": False}

    with ThreadPoolExecutor(max_workers=n_runs) as executor:
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

    # Save results
    results_dir = _RESULTS_DIR / transcript_id
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for i, run_data in enumerate(runs):
        if "parsed_json" in run_data:
            save_json(run_data["parsed_json"], results_dir / f"run_{i+1:03d}_{timestamp}.json")

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

def run_compare_offline(outputs_dir: Path, detail: bool = False) -> dict[str, Any]:
    """Load existing output JSON files and compute cross-meeting discriminant validity.

    Groups files by context.meeting_id (falls back to filename stem).
    Multiple files with the same meeting_id are treated as multiple runs.
    No LLM calls are made.
    """
    json_files = sorted(outputs_dir.rglob("*.json"))
    if not json_files:
        logger.error("No JSON files found in %s", outputs_dir)
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

        if "pattern_snapshot" not in data:
            logger.warning("Skipping %s: no pattern_snapshot", f.name)
            skipped += 1
            continue

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

            for run_data in runs:
                found = False
                for snap in run_data.get("pattern_snapshot", []):
                    if snap.get("pattern_id") == pid:
                        scores.append(snap.get("score"))
                        opp_counts.append(snap.get("opportunity_count"))
                        statuses[snap.get("evaluable_status", "unknown")] += 1
                        found = True
                        break
                if not found:
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
""",
    )
    parser.add_argument("--mode", choices=["repeat", "compare"], required=True)
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
            run_compare_offline(args.outputs_dir, detail=args.detail)
        elif args.transcripts_dir:
            run_compare(args.transcripts_dir, args.runs, model=args.model, detail=args.detail)
        else:
            parser.error("--transcripts-dir or --outputs-dir is required for compare mode")


if __name__ == "__main__":
    main()
