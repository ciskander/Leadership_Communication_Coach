"""Longitudinal eval reporting — per-persona and aggregate.

Reads the output directory from ``longitudinal_eval.py`` and judge results
from ``longitudinal_judge.py``, then produces markdown reports.

Usage:
    python -m backend.evals.longitudinal_report \\
        --phase-dir backend/evals/results/Long_20260402
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.evals.report import format_markdown_table, save_json, save_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASELINE_MEETING_COUNT = 3


# ── Data Loading ─────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_persona_data(persona_dir: Path) -> dict:
    """Load all data for one persona into a structured dict."""
    persona = _load_json(persona_dir / "persona.json") or {}
    state = _load_json(persona_dir / "state.json") or {}
    quality = _load_json(persona_dir / "quality.json") or {}
    synthesis = _load_json(persona_dir / "baseline_synthesis.json")

    meetings: list[dict] = []
    for m_dir in sorted(persona_dir.iterdir()):
        if not m_dir.is_dir() or not m_dir.name.startswith("meeting_"):
            continue
        metadata = _load_json(m_dir / "metadata.json") or {}
        analysis = _load_json(m_dir / "analysis.json")
        stage1 = _load_json(m_dir / "stage1.json")
        design_note = _load_json(m_dir / "design_note.json")
        ab = _load_json(m_dir / "analysis_no_history.json")

        meetings.append({
            "dir_name": m_dir.name,
            "metadata": metadata,
            "analysis": analysis,
            "stage1": stage1,
            "design_note": design_note,
            "analysis_no_history": ab,
        })

    return {
        "persona": persona,
        "state": state,
        "quality": quality,
        "synthesis": synthesis,
        "meetings": meetings,
    }


def _load_judge_data(judges_dir: Path, persona_name: str) -> dict:
    """Load judge results for one persona."""
    p_dir = judges_dir / persona_name
    if not p_dir.exists():
        return {}

    series = _load_json(p_dir / "longitudinal_series.json")
    ab_judges: dict[int, dict] = {}
    standard_judges: dict[int, dict] = {}

    for f in sorted(p_dir.iterdir()):
        if f.name.endswith("_ab_comparison.json"):
            # meeting_04_ab_comparison.json → 4
            try:
                m_num = int(f.name.split("_")[1])
                ab_judges[m_num] = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, IndexError):
                pass
        elif f.name.endswith("_standard.json"):
            try:
                m_num = int(f.name.split("_")[1])
                standard_judges[m_num] = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, IndexError):
                pass

    return {
        "series": series,
        "ab": ab_judges,
        "standard": standard_judges,
    }


# ── Per-Persona Report ───────────────────────────────────────────────────────

def generate_persona_report(
    persona_data: dict,
    judge_data: dict,
) -> str:
    """Generate a markdown report for one persona."""
    persona = persona_data["persona"]
    state = persona_data["state"]
    meetings = persona_data["meetings"]
    quality = persona_data["quality"]

    lines: list[str] = []

    # Header
    name = persona.get("name", "Unknown")
    lines.append(f"# Longitudinal Report: {name}")
    lines.append("")

    # Persona summary
    lines.append("## Persona")
    persona_text = persona.get("persona_text", "")
    if persona_text:
        # First 500 chars as summary
        summary = persona_text[:500]
        if len(persona_text) > 500:
            summary += "..."
        lines.append(summary)
    lines.append("")

    # Meeting timeline table
    lines.append("## Meeting Timeline")
    lines.append("")
    headers = ["Meeting", "Phase", "Date", "Role", "Gate1", "Analysis", "Themes", "Experiment"]
    rows: list[list[str]] = []
    for m in meetings:
        meta = m["metadata"]
        analysis = m["analysis"]
        m_num = meta.get("meeting_number", "?")
        phase = meta.get("meeting_phase", "?")
        m_date = meta.get("meeting_date", "?")
        role = meta.get("target_role", "?")

        gate1 = "N/A"
        if m.get("stage1"):
            # stage1.json may have gate1_passed (old wrapper format) or be
            # just the parsed analysis (new format). If analysis.json exists,
            # Stage 1 must have passed (pipeline aborts otherwise).
            if m["stage1"].get("gate1_passed") is not None:
                gate1 = "Pass" if m["stage1"]["gate1_passed"] else "Fail"
            elif analysis:
                gate1 = "Pass"
            else:
                gate1 = "?"

        has_analysis = "Yes" if analysis else "No"

        # Theme count
        themes = ""
        exp_status = ""
        if analysis:
            coaching = analysis.get("coaching", {}) or {}
            theme_list = coaching.get("coaching_themes", [])
            themes = str(len(theme_list))

            # Experiment info
            exp_tracking = analysis.get("experiment_tracking", {}) or {}
            detection = exp_tracking.get("detection_in_this_meeting")
            if detection and isinstance(detection, dict):
                attempt = detection.get("attempt", "")
                exp_status = attempt
            elif meta.get("meeting_phase") == "baseline":
                exp_status = "-"

        rows.append([
            str(m_num), phase, m_date, role, gate1, has_analysis, themes, exp_status,
        ])
    lines.append(format_markdown_table(headers, rows))
    lines.append("")

    # Score trajectories
    lines.append("## Pattern Score Trajectories")
    lines.append("")
    _append_score_trajectories(lines, meetings, state)

    # Coaching theme evolution
    lines.append("## Coaching Theme Evolution")
    lines.append("")
    _append_theme_evolution(lines, meetings)

    # Experiment journey
    lines.append("## Experiment Journey")
    lines.append("")
    _append_experiment_journey(lines, state)

    # Transcript quality
    if quality.get("meetings"):
        lines.append("## Transcript Quality")
        lines.append("")
        qm = quality["meetings"]
        failed = [k for k, v in qm.items() if not v.get("passed")]
        if failed:
            lines.append(f"**{len(failed)} transcript(s) with issues:** {', '.join(failed)}")
            for k in failed:
                issues = qm[k].get("issues", [])
                for issue in issues:
                    lines.append(f"- {k}: {issue}")
        else:
            lines.append("All transcripts passed quality checks.")
        lines.append("")

    # Design note vs detection comparison (follow-ups)
    lines.append("## Design Note vs Detection (Follow-ups)")
    lines.append("")
    _append_design_vs_detection(lines, meetings)

    # Judge results
    if judge_data:
        _append_judge_results(lines, judge_data)

    return "\n".join(lines)


def _append_score_trajectories(
    lines: list[str],
    meetings: list[dict],
    state: dict,
) -> None:
    """Append pattern score trajectory table."""
    # Collect scores across meetings
    pattern_scores: dict[str, list[tuple[int, float | None]]] = defaultdict(list)

    for m in meetings:
        analysis = m.get("analysis")
        if not analysis:
            continue
        m_num = m["metadata"].get("meeting_number", 0)
        for ps in analysis.get("pattern_snapshot", []):
            pid = ps.get("pattern_id", "")
            if ps.get("evaluable_status") == "evaluable":
                pattern_scores[pid].append((m_num, ps.get("score")))

    if not pattern_scores:
        lines.append("No evaluable pattern scores found.")
        lines.append("")
        return

    # Find patterns with most variation (interesting to track)
    variances: list[tuple[str, float]] = []
    for pid, scores in pattern_scores.items():
        vals = [s for _, s in scores if s is not None]
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            variances.append((pid, var))
    variances.sort(key=lambda x: x[1], reverse=True)
    top_patterns = [pid for pid, _ in variances[:8]]

    # Highlight experiment-targeted patterns
    active_exp = state.get("active_experiment") or {}
    exp_patterns = set(active_exp.get("related_patterns", []))
    for eh in state.get("experiment_history", []):
        exp_patterns.update(eh.get("related_patterns", []))

    # Build table
    meeting_nums = sorted({m["metadata"].get("meeting_number", 0) for m in meetings if m.get("analysis")})
    headers = ["Pattern"] + [f"M{n}" for n in meeting_nums]
    rows = []
    for pid in top_patterns:
        score_map = {m_num: score for m_num, score in pattern_scores[pid]}
        marker = " *" if pid in exp_patterns else ""
        row = [f"{pid}{marker}"]
        for n in meeting_nums:
            s = score_map.get(n)
            row.append(f"{s:.2f}" if s is not None else "-")
        rows.append(row)

    lines.append(format_markdown_table(headers, rows))
    if exp_patterns:
        lines.append("")
        lines.append("\\* = experiment-targeted pattern")
    lines.append("")


def _append_theme_evolution(lines: list[str], meetings: list[dict]) -> None:
    """Append coaching theme evolution across meetings, categorized by nature."""
    theme_appearances: dict[str, list[int]] = defaultdict(list)
    theme_natures: dict[str, list[str]] = defaultdict(list)

    nature_counts: dict[str, int] = defaultdict(int)

    for m in meetings:
        analysis = m.get("analysis")
        if not analysis:
            continue
        m_num = m["metadata"].get("meeting_number", 0)
        coaching = analysis.get("coaching", {}) or {}
        for t in coaching.get("coaching_themes", []):
            if isinstance(t, dict):
                label = t.get("theme", "")
                nature = t.get("nature", "developmental")
                if label:
                    theme_appearances[label].append(m_num)
                    theme_natures[label].append(nature)
                    nature_counts[nature] += 1

    if not theme_appearances:
        lines.append("No coaching themes found.")
        lines.append("")
        return

    # Nature distribution summary
    total = sum(nature_counts.values())
    dist_parts = [f"{n}={c}" for n, c in sorted(nature_counts.items())]
    lines.append(f"**Nature distribution** (n={total}): {', '.join(dist_parts)}")
    lines.append("")

    # Categorize
    persisting = []
    one_off = []
    for theme, appearances in sorted(theme_appearances.items()):
        natures = theme_natures[theme]
        # Most common nature for this theme
        nature_label = max(set(natures), key=natures.count) if natures else "?"
        if len(appearances) >= 2:
            persisting.append((theme, appearances, nature_label))
        else:
            one_off.append((theme, appearances, nature_label))

    if persisting:
        lines.append("**Persisting themes** (appear in 2+ meetings):")
        for theme, apps, nature in persisting:
            lines.append(f"- {theme} [{nature}] (M{', M'.join(str(a) for a in apps)})")
        lines.append("")

    if one_off:
        lines.append(f"**One-off themes** ({len(one_off)} themes appeared once only):")
        for theme, apps, nature in one_off:
            lines.append(f"- {theme} [{nature}] (M{apps[0]})")
        lines.append("")


def _append_experiment_journey(lines: list[str], state: dict) -> None:
    """Append experiment journey timeline."""
    active = state.get("active_experiment")
    history = state.get("experiment_history", [])
    transitions = state.get("experiment_transitions", [])

    if not active and not history:
        lines.append("No experiments recorded.")
        lines.append("")
        return

    for exp in history:
        lines.append(
            f"- **{exp.get('title', '?')}** ({exp.get('experiment_id', '?')}) "
            f"— {exp.get('status', '?')}"
        )
        rp = exp.get("related_patterns", [])
        if rp:
            lines.append(f"  Patterns: {', '.join(rp)}")
        js = exp.get("journey_summary", "")
        if js:
            lines.append(f"  Journey: {js}")
        lines.append("")

    if active:
        lines.append(
            f"- **{active.get('title', '?')}** ({active.get('experiment_id', '?')}) "
            f"— ACTIVE"
        )
        rp = active.get("related_patterns", [])
        if rp:
            lines.append(f"  Patterns: {', '.join(rp)}")
        lines.append("")

    if transitions:
        lines.append("**Transitions:**")
        for t in transitions:
            lines.append(
                f"- Meeting {t.get('meeting', '?')}: "
                f"{t.get('from', '?')} -> {t.get('to', '?')}"
            )
        lines.append("")


def _append_design_vs_detection(lines: list[str], meetings: list[dict]) -> None:
    """Compare transcript design note intent vs analysis detection."""
    headers = ["Meeting", "Intended", "Detected", "Match"]
    rows = []

    for m in meetings:
        meta = m["metadata"]
        if meta.get("meeting_phase") != "follow_up":
            continue
        m_num = meta.get("meeting_number", "?")
        dn = m.get("design_note") or {}
        analysis = m.get("analysis")

        intended = dn.get("intended_attempt_level", "?")

        detected = "?"
        if analysis:
            exp_tracking = analysis.get("experiment_tracking", {}) or {}
            detection = exp_tracking.get("detection_in_this_meeting")
            if detection and isinstance(detection, dict):
                detected = detection.get("attempt", "?")

        match = "Yes" if intended == detected else ("~" if intended == "?" or detected == "?" else "No")
        rows.append([str(m_num), intended, detected, match])

    if rows:
        lines.append(format_markdown_table(headers, rows))
        # Accuracy
        matched = sum(1 for r in rows if r[3] == "Yes")
        total = sum(1 for r in rows if r[3] != "~")
        if total > 0:
            lines.append(f"\nDetection accuracy: {matched}/{total} ({matched/total:.0%})")
    else:
        lines.append("No follow-up meetings with design notes.")
    lines.append("")


def _append_judge_results(lines: list[str], judge_data: dict) -> None:
    """Append judge evaluation results."""
    series = judge_data.get("series")
    ab = judge_data.get("ab", {})
    standard = judge_data.get("standard", {})

    if series:
        lines.append("## Longitudinal Series Judge")
        lines.append("")
        for dim in [
            "coaching_theme_evolution", "executive_summary_arc",
            "experiment_coaching_quality", "score_narrative_coherence",
            "coaching_freshness", "overall_longitudinal_value",
        ]:
            val = series.get(dim, {})
            if isinstance(val, dict):
                rating = val.get("rating", "?")
                explanation = val.get("explanation", "")
                lines.append(f"- **{dim}**: {rating}")
                if explanation:
                    lines.append(f"  {explanation}")
            else:
                lines.append(f"- **{dim}**: {val}")
        lines.append("")

    if ab:
        lines.append("## A/B Comparison Results")
        lines.append("")
        headers = ["Meeting", "Preferred", "Confidence", "Specificity", "Context Use", "Freshness", "Leader Value"]
        rows = []
        for m_num in sorted(ab.keys()):
            result = ab[m_num]
            dims = result.get("dimensions", {})
            rows.append([
                f"M{m_num:02d}",
                result.get("preferred", "?"),
                result.get("confidence", "?"),
                dims.get("specificity", {}).get("preferred", "?") if isinstance(dims.get("specificity"), dict) else "?",
                dims.get("context_use", {}).get("preferred", "?") if isinstance(dims.get("context_use"), dict) else "?",
                dims.get("freshness", {}).get("preferred", "?") if isinstance(dims.get("freshness"), dict) else "?",
                dims.get("leader_value", {}).get("preferred", "?") if isinstance(dims.get("leader_value"), dict) else "?",
            ])
        lines.append(format_markdown_table(headers, rows))
        lines.append("")

    if standard:
        lines.append("## Standard Judge Results (Follow-ups)")
        lines.append("")
        headers = ["Meeting", "Overall Value", "Approve", "Respected"]
        rows = []
        for m_num in sorted(standard.keys()):
            result = standard[m_num]
            gut = result.get("executive_coach_gut_check", {})
            rows.append([
                f"M{m_num:02d}",
                str(gut.get("overall_coaching_value", "?")),
                str(gut.get("would_approve_for_delivery", "?")),
                str(gut.get("leader_would_feel_respected", "?")),
            ])
        lines.append(format_markdown_table(headers, rows))
        lines.append("")


# ── Aggregate Report ─────────────────────────────────────────────────────────

def generate_aggregate_report(
    phase_dir: Path,
    persona_reports: list[tuple[str, dict, dict]],
) -> str:
    """Generate the aggregate report across all personas.

    Args:
        phase_dir: Path to the phase results directory.
        persona_reports: List of (persona_name, persona_data, judge_data) tuples.
    """
    lines: list[str] = []
    manifest = _load_json(phase_dir / "manifest.json") or {}

    lines.append("# Longitudinal Eval — Aggregate Report")
    lines.append("")

    # Config summary
    config = manifest.get("config", {})
    lines.append("## Configuration")
    lines.append(f"- Personas: {config.get('num_personas', '?')}")
    lines.append(f"- Meetings per persona: {config.get('meetings_per_persona', '?')}")
    lines.append(f"- Model: {config.get('model', '?')}")
    lines.append(f"- Status: {manifest.get('status', '?')}")
    lines.append(f"- Started: {manifest.get('started_at', '?')}")
    lines.append(f"- Completed: {manifest.get('completed_at', '?')}")
    lines.append("")

    # Coaching arc coherence rate
    lines.append("## Coaching Arc Coherence")
    lines.append("")
    _append_coherence_stats(lines, persona_reports)

    # Experiment detection accuracy
    lines.append("## Experiment Detection Accuracy")
    lines.append("")
    _append_detection_accuracy(lines, persona_reports)

    # A/B win rate
    lines.append("## A/B Win Rate")
    lines.append("")
    _append_ab_win_rate(lines, persona_reports)

    # Score trajectory analysis
    lines.append("## Score Trajectory Analysis")
    lines.append("")
    _append_score_trajectory_analysis(lines, persona_reports)

    # Per-persona summary table
    lines.append("## Per-Persona Summary")
    lines.append("")
    _append_persona_summary_table(lines, persona_reports)

    return "\n".join(lines)


def _append_coherence_stats(
    lines: list[str],
    persona_reports: list[tuple[str, dict, dict]],
) -> None:
    """Coaching arc coherence: % with evolving themes + medium/high value."""
    total = 0
    coherent = 0
    ratings: dict[str, int] = defaultdict(int)
    value_ratings: dict[str, int] = defaultdict(int)

    for name, _pdata, jdata in persona_reports:
        series = jdata.get("series")
        if not series:
            continue
        total += 1

        theme_evo = series.get("coaching_theme_evolution", {})
        overall = series.get("overall_longitudinal_value", {})

        t_rating = theme_evo.get("rating", "?") if isinstance(theme_evo, dict) else "?"
        o_rating = overall.get("rating", "?") if isinstance(overall, dict) else "?"

        ratings[t_rating] += 1
        value_ratings[o_rating] += 1

        if t_rating == "evolving" and o_rating in ("high", "medium"):
            coherent += 1

    if total > 0:
        lines.append(f"**Coherence rate**: {coherent}/{total} ({coherent/total:.0%})")
        lines.append(f"  (evolving themes AND medium/high overall value)")
        lines.append("")
        lines.append(f"Theme evolution: {dict(ratings)}")
        lines.append(f"Overall value: {dict(value_ratings)}")
    else:
        lines.append("No series judge results available.")
    lines.append("")


def _append_detection_accuracy(
    lines: list[str],
    persona_reports: list[tuple[str, dict, dict]],
) -> None:
    """Design note intent vs detection result agreement rate."""
    total = 0
    matched = 0
    by_level: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for name, pdata, _jdata in persona_reports:
        for m in pdata.get("meetings", []):
            meta = m.get("metadata", {})
            if meta.get("meeting_phase") != "follow_up":
                continue
            dn = m.get("design_note") or {}
            analysis = m.get("analysis")
            if not analysis:
                continue

            intended = dn.get("intended_attempt_level", "unknown")
            if intended == "unknown":
                continue

            exp_tracking = analysis.get("experiment_tracking", {}) or {}
            detection = exp_tracking.get("detection_in_this_meeting")
            detected = "unknown"
            if detection and isinstance(detection, dict):
                detected = detection.get("attempt", "unknown")

            total += 1
            if intended == detected:
                matched += 1
            by_level[intended][detected] += 1

    if total > 0:
        lines.append(f"**Overall accuracy**: {matched}/{total} ({matched/total:.0%})")
        lines.append("")
        # Confusion-style breakdown
        lines.append("**Breakdown (intended -> detected):**")
        for intended in sorted(by_level.keys()):
            detections = by_level[intended]
            parts = [f"{detected}={count}" for detected, count in sorted(detections.items())]
            lines.append(f"- {intended}: {', '.join(parts)}")
    else:
        lines.append("No design notes with detection results available.")
    lines.append("")


def _append_ab_win_rate(
    lines: list[str],
    persona_reports: list[tuple[str, dict, dict]],
) -> None:
    """A/B win rate: overall + by meeting number + by dimension."""
    overall: dict[str, int] = defaultdict(int)
    by_meeting: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_dimension: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for name, _pdata, jdata in persona_reports:
        for m_num, result in jdata.get("ab", {}).items():
            pref = result.get("preferred", "tie")
            overall[pref] += 1
            by_meeting[m_num][pref] += 1

            for dim_name, dim_val in result.get("dimensions", {}).items():
                if isinstance(dim_val, dict):
                    dim_pref = dim_val.get("preferred", "tie")
                    by_dimension[dim_name][dim_pref] += 1

    total = sum(overall.values())
    if total == 0:
        lines.append("No A/B comparison results available.")
        lines.append("")
        return

    # Overall
    wh = overall.get("with_history", 0)
    nh = overall.get("no_history", 0)
    ties = overall.get("tie", 0)
    lines.append(f"**Overall**: with_history={wh}, no_history={nh}, tie={ties} (n={total})")
    if wh + nh > 0:
        lines.append(f"  With-history win rate: {wh/(wh+nh):.0%} (excluding ties)")
    lines.append("")

    # By meeting number
    if by_meeting:
        lines.append("**By meeting number** (does advantage grow with more history?):")
        headers = ["Meeting", "With History", "No History", "Tie"]
        rows = []
        for m_num in sorted(by_meeting.keys()):
            counts = by_meeting[m_num]
            rows.append([
                f"M{m_num:02d}",
                str(counts.get("with_history", 0)),
                str(counts.get("no_history", 0)),
                str(counts.get("tie", 0)),
            ])
        lines.append(format_markdown_table(headers, rows))
        lines.append("")

    # By dimension
    if by_dimension:
        lines.append("**By dimension:**")
        headers = ["Dimension", "With History", "No History", "Tie"]
        rows = []
        for dim in sorted(by_dimension.keys()):
            counts = by_dimension[dim]
            rows.append([
                dim,
                str(counts.get("with_history", 0)),
                str(counts.get("no_history", 0)),
                str(counts.get("tie", 0)),
            ])
        lines.append(format_markdown_table(headers, rows))
        lines.append("")


def _append_score_trajectory_analysis(
    lines: list[str],
    persona_reports: list[tuple[str, dict, dict]],
) -> None:
    """Score trajectory: targeted vs non-targeted pattern improvement."""
    targeted_deltas: list[float] = []
    non_targeted_deltas: list[float] = []

    for name, pdata, _jdata in persona_reports:
        state = pdata.get("state", {})
        meetings = pdata.get("meetings", [])

        # Collect experiment-targeted patterns
        exp_patterns: set[str] = set()
        active = state.get("active_experiment") or {}
        exp_patterns.update(active.get("related_patterns", []))
        for eh in state.get("experiment_history", []):
            exp_patterns.update(eh.get("related_patterns", []))

        # Collect first and last scores per pattern
        first_scores: dict[str, float] = {}
        last_scores: dict[str, float] = {}

        for m in meetings:
            analysis = m.get("analysis")
            if not analysis:
                continue
            for ps in analysis.get("pattern_snapshot", []):
                pid = ps.get("pattern_id", "")
                if ps.get("evaluable_status") != "evaluable":
                    continue
                score = ps.get("score")
                if score is None:
                    continue
                if pid not in first_scores:
                    first_scores[pid] = score
                last_scores[pid] = score

        for pid in first_scores:
            if pid in last_scores:
                delta = last_scores[pid] - first_scores[pid]
                if pid in exp_patterns:
                    targeted_deltas.append(delta)
                else:
                    non_targeted_deltas.append(delta)

    if targeted_deltas:
        avg_t = sum(targeted_deltas) / len(targeted_deltas)
        improved_t = sum(1 for d in targeted_deltas if d > 0)
        lines.append(f"**Experiment-targeted patterns** (n={len(targeted_deltas)}):")
        lines.append(f"  Avg score delta: {avg_t:+.3f}")
        lines.append(f"  Improved: {improved_t}/{len(targeted_deltas)} ({improved_t/len(targeted_deltas):.0%})")
    else:
        lines.append("No experiment-targeted pattern scores to compare.")
    lines.append("")

    if non_targeted_deltas:
        avg_nt = sum(non_targeted_deltas) / len(non_targeted_deltas)
        improved_nt = sum(1 for d in non_targeted_deltas if d > 0)
        lines.append(f"**Non-targeted patterns** (n={len(non_targeted_deltas)}):")
        lines.append(f"  Avg score delta: {avg_nt:+.3f}")
        lines.append(f"  Improved: {improved_nt}/{len(non_targeted_deltas)} ({improved_nt/len(non_targeted_deltas):.0%})")
    else:
        lines.append("No non-targeted pattern scores to compare.")
    lines.append("")


def _append_persona_summary_table(
    lines: list[str],
    persona_reports: list[tuple[str, dict, dict]],
) -> None:
    """Summary table across all personas."""
    headers = [
        "Persona", "Meetings", "Experiments", "Arc Rating",
        "A/B History Wins", "Std Value",
    ]
    rows = []

    for name, pdata, jdata in persona_reports:
        meetings = pdata.get("meetings", [])
        state = pdata.get("state", {})
        n_meetings = len([m for m in meetings if m.get("analysis")])
        n_exps = len(state.get("experiment_history", []))
        if state.get("active_experiment"):
            n_exps += 1

        # Series judge
        series = jdata.get("series", {})
        overall = series.get("overall_longitudinal_value", {})
        arc_rating = overall.get("rating", "?") if isinstance(overall, dict) else "?"

        # A/B
        ab = jdata.get("ab", {})
        wh_wins = sum(1 for r in ab.values() if r.get("preferred") == "with_history")
        ab_total = len(ab)
        ab_str = f"{wh_wins}/{ab_total}" if ab_total else "-"

        # Standard judge avg
        standard = jdata.get("standard", {})
        values = []
        for r in standard.values():
            gut = r.get("executive_coach_gut_check", {})
            v = gut.get("overall_coaching_value", "")
            if v:
                values.append(v)
        value_str = ", ".join(values) if values else "-"

        rows.append([name, str(n_meetings), str(n_exps), arc_rating, ab_str, value_str])

    lines.append(format_markdown_table(headers, rows))
    lines.append("")


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_longitudinal_reports(phase_dir: Path) -> None:
    """Generate all reports for a longitudinal eval phase."""
    reports_dir = phase_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    judges_dir = phase_dir / "judges"

    persona_dirs = sorted(
        d for d in phase_dir.iterdir()
        if d.is_dir() and d.name.startswith("persona_")
    )

    if not persona_dirs:
        logger.error("No persona directories in %s", phase_dir)
        return

    all_persona_data: list[tuple[str, dict, dict]] = []

    for p_dir in persona_dirs:
        p_name = p_dir.name
        logger.info("Loading data for %s", p_name)

        pdata = _load_persona_data(p_dir)
        jdata = _load_judge_data(judges_dir, p_name)

        persona_name = pdata["persona"].get("name", p_name)
        all_persona_data.append((persona_name, pdata, jdata))

        # Per-persona report
        report = generate_persona_report(pdata, jdata)
        report_path = reports_dir / f"{p_name}_longitudinal.md"
        save_report(report, report_path)

    # Aggregate report
    logger.info("Generating aggregate report")
    agg = generate_aggregate_report(phase_dir, all_persona_data)
    save_report(agg, reports_dir / "aggregate_report.md")

    # Save aggregate stats as JSON for programmatic access
    stats = _compute_aggregate_stats(all_persona_data)
    save_json(stats, reports_dir / "aggregate_stats.json")

    logger.info("Reports saved to %s", reports_dir)


def _compute_aggregate_stats(
    persona_reports: list[tuple[str, dict, dict]],
) -> dict:
    """Compute aggregate stats as a JSON-serializable dict."""
    stats: dict[str, Any] = {
        "num_personas": len(persona_reports),
        "coherence": {"total": 0, "coherent": 0},
        "ab": {"with_history": 0, "no_history": 0, "tie": 0},
        "detection": {"total": 0, "matched": 0},
    }

    for name, pdata, jdata in persona_reports:
        series = jdata.get("series")
        if series:
            stats["coherence"]["total"] += 1
            theme_evo = series.get("coaching_theme_evolution", {})
            overall = series.get("overall_longitudinal_value", {})
            t_r = theme_evo.get("rating", "") if isinstance(theme_evo, dict) else ""
            o_r = overall.get("rating", "") if isinstance(overall, dict) else ""
            if t_r == "evolving" and o_r in ("high", "medium"):
                stats["coherence"]["coherent"] += 1

        for result in jdata.get("ab", {}).values():
            pref = result.get("preferred", "tie")
            if pref in stats["ab"]:
                stats["ab"][pref] += 1

        for m in pdata.get("meetings", []):
            if m.get("metadata", {}).get("meeting_phase") != "follow_up":
                continue
            dn = m.get("design_note") or {}
            analysis = m.get("analysis")
            if not analysis:
                continue
            intended = dn.get("intended_attempt_level", "unknown")
            if intended == "unknown":
                continue
            exp_tracking = analysis.get("experiment_tracking", {}) or {}
            detection = exp_tracking.get("detection_in_this_meeting")
            if detection and isinstance(detection, dict):
                detected = detection.get("attempt", "unknown")
                stats["detection"]["total"] += 1
                if intended == detected:
                    stats["detection"]["matched"] += 1

    return stats


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate longitudinal eval reports.",
    )
    parser.add_argument(
        "--phase-dir", type=Path, required=True,
        help="Path to longitudinal eval results directory",
    )
    args = parser.parse_args()

    run_longitudinal_reports(args.phase_dir)


if __name__ == "__main__":
    main()
