"""Longitudinal-specific judge dimensions.

Three judge types:
1. **Series judge** — evaluates the full coaching arc for one persona
2. **A/B comparative judge** — per follow-up meeting, compares with-history
   vs without-history coaching (randomized to avoid position bias)
3. **Standard per-meeting judge** — reuses ``judge_eval.judge_analysis()``
   on the with-history output

Usage:
    python -m backend.evals.longitudinal_judge \\
        --phase-dir backend/evals/results/Long_20260402
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.llm_client import call_llm
from backend.evals.judge_eval import judge_analysis, load_transcript_for_judge
from backend.evals.longitudinal_transcript_gen import build_condensed_history
from backend.evals.report import save_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASELINE_MEETING_COUNT = 3
_TOKENS_PER_JUDGE = 15_000


# ── Series Judge ─────────────────────────────────────────────────────────────

_SERIES_JUDGE_SYSTEM_PROMPT = """\
You are an experienced executive coach with 20+ years of experience. You are \
reviewing the output of an AI coaching system that analyzes meeting transcripts \
and provides longitudinal coaching feedback to a leader over multiple meetings.

Your job is to evaluate whether the coaching ARC across meetings is coherent, \
evolving, and genuinely useful — or whether the system is repeating itself, \
contradicting earlier feedback, or failing to build on its own observations.

You will receive a condensed timeline of coaching output across all meetings \
for one coachee. Each meeting entry includes the executive summary, coaching \
themes, experiment status, and selected pattern scores.

Evaluate from a COACH'S perspective: would a real coach find this series of \
outputs useful as session-over-session working notes? Would they feel confident \
that the system is tracking the coachee's development trajectory?\
"""

_SERIES_JUDGE_USER_PROMPT = """\
## Coachee Profile

{persona_summary}

## Coaching Timeline ({num_meetings} meetings)

{condensed_history}

---

## Your Evaluation

Evaluate the coaching arc across all meetings. Return a JSON object:

```json
{{
  "coaching_theme_evolution": {{
    "rating": "evolving|stagnant|contradictory",
    "themes_that_persist": ["<theme names that appear across multiple meetings>"],
    "themes_that_resolve": ["<themes that appear early but are addressed/dropped later>"],
    "new_themes_introduced": ["<themes that appear for the first time in later meetings>"],
    "explanation": "<How well do themes evolve? Does the system build on prior \
observations or just repeat them?>"
  }},
  "executive_summary_arc": {{
    "rating": "coherent_arc|disconnected|generic",
    "references_prior_context": <true if later summaries reference or build on earlier ones>,
    "tracks_growth": <true if summaries note improvement or persistent issues over time>,
    "explanation": "<Does the summary narrative build meaningfully across meetings, \
or could each one stand alone with no loss?>"
  }},
  "experiment_coaching_quality": {{
    "rating": "strong_progression|adequate|illogical",
    "detection_seems_accurate": <true|false|"cannot_assess">,
    "experiment_sequencing_logical": <true if experiment transitions make sense>,
    "explanation": "<Is the experiment journey coherent? Do transitions happen at \
sensible moments? Does detection seem to match what you'd expect from the summaries?>"
  }},
  "score_narrative_coherence": {{
    "rating": "coherent|minor_inconsistencies|contradictory",
    "explanation": "<Do the pattern scores and coaching narrative agree? If scores \
improve but coaching says things are getting worse (or vice versa), flag it.>"
  }},
  "coaching_freshness": {{
    "rating": "fresh_and_deepening|some_repetition|stale",
    "verbatim_repetitions_noted": <number of times you noticed near-identical phrasing \
across meetings>,
    "explanation": "<Does the coaching deepen over time, or does it just say the same \
things meeting after meeting? Progressively nuanced is good; copy-paste is bad.>"
  }},
  "overall_longitudinal_value": {{
    "rating": "high|medium|low",
    "explanation": "<As an executive coach, would you find this series of outputs \
useful as session-over-session working notes? Would you trust this system to track \
a real coachee's development?>"
  }}
}}
```

Return ONLY the JSON object, no other text.\
"""


# ── A/B Comparative Judge ────────────────────────────────────────────────────

_AB_JUDGE_SYSTEM_PROMPT = """\
You are an experienced executive coach comparing two versions of AI-generated \
coaching feedback for the same meeting. One version had access to the coachee's \
prior coaching history (themes, summaries, experiment status from earlier \
meetings). The other version analyzed the meeting in isolation.

You will see:
1. The meeting transcript
2. A condensed coaching history from prior meetings (so you can assess whether \
   history references are accurate)
3. Two coaching outputs labeled "System A" and "System B" (randomized — you do \
   NOT know which had history access)

Evaluate which system produced more useful coaching. Be specific about WHY one \
is better — vague preferences don't help improve the system.\
"""

_AB_JUDGE_USER_PROMPT = """\
## Coaching History (prior meetings)

{coaching_history}

## Current Meeting Transcript

{transcript_text}

## System A — Coaching Output

### Executive Summary
{system_a_summary}

### Coaching Themes
{system_a_themes}

### Experiment Coaching
{system_a_experiment}

## System B — Coaching Output

### Executive Summary
{system_b_summary}

### Coaching Themes
{system_b_themes}

### Experiment Coaching
{system_b_experiment}

---

## Your Evaluation

Compare the two systems. Return a JSON object:

```json
{{
  "preferred": "system_a|system_b|tie",
  "confidence": "high|medium|low",
  "reason": "<1-2 sentences: why you prefer this system>",
  "dimensions": {{
    "specificity": {{
      "preferred": "system_a|system_b|tie",
      "explanation": "<Which system's coaching is more specific to THIS leader \
in THIS meeting?>"
    }},
    "context_use": {{
      "preferred": "system_a|system_b|tie",
      "explanation": "<Which system better uses (or would benefit from) knowledge \
of the coachee's history? Does either reference prior themes or growth patterns?>"
    }},
    "freshness": {{
      "preferred": "system_a|system_b|tie",
      "explanation": "<Which system avoids repeating what the coachee has already \
heard? (Use the coaching history to assess whether themes are stale.)>"
    }},
    "leader_value": {{
      "preferred": "system_a|system_b|tie",
      "explanation": "<Which output would a senior leader find more useful and \
respectful of their time?>"
    }}
  }}
}}
```

Return ONLY the JSON object, no other text.\
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_coaching_for_ab(analysis: dict) -> dict[str, str]:
    """Extract formatted coaching sections from an analysis for A/B comparison."""
    coaching = analysis.get("coaching", {}) or {}

    # Executive summary
    summary = coaching.get("executive_summary", "(none)")

    # Coaching themes
    themes = coaching.get("coaching_themes", [])
    theme_lines = []
    for t in themes:
        if isinstance(t, dict):
            priority = t.get("priority", "")
            nature = t.get("nature", "")
            label = t.get("theme", "")
            explanation = t.get("explanation", "")
            rp = t.get("related_patterns", [])
            theme_lines.append(
                f"- **{label}** (priority: {priority}, nature: {nature})\n"
                f"  {explanation}\n"
                f"  Related patterns: {', '.join(rp) if rp else '(none)'}"
            )
    themes_text = "\n\n".join(theme_lines) if theme_lines else "(none)"

    # Experiment coaching
    exp_coaching = coaching.get("experiment_coaching")
    if exp_coaching and isinstance(exp_coaching, dict):
        exp_text = exp_coaching.get("coaching_note", "(none)")
    else:
        exp_text = "(none)"

    return {
        "summary": summary,
        "themes": themes_text,
        "experiment": exp_text,
    }


def _format_transcript_text(transcript_data: dict) -> str:
    """Format transcript turns into readable text."""
    lines = []
    for turn in transcript_data.get("turns", []):
        lines.append(f"[Turn {turn['turn_id']}] {turn['speaker_label']}: {turn['text']}")
    return "\n".join(lines)


# ── Series Judge Runner ──────────────────────────────────────────────────────

def judge_longitudinal_series(
    persona_name: str,
    meeting_analyses: list[dict],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the longitudinal series judge for one persona.

    Args:
        persona_name: The persona's name (for context).
        meeting_analyses: List of dicts, each with keys ``meeting_number``,
            ``meeting_type``, ``role``, and ``analysis`` (the merged JSON).
            Must be ordered by meeting number.
        model: LLM model override.

    Returns:
        The judge's structured evaluation dict.
    """
    condensed = build_condensed_history(meeting_analyses)

    persona_summary = f"Coachee: {persona_name}"

    user_msg = _SERIES_JUDGE_USER_PROMPT.format(
        persona_summary=persona_summary,
        num_meetings=len(meeting_analyses),
        condensed_history=condensed,
    )

    response = call_llm(
        system_prompt=_SERIES_JUDGE_SYSTEM_PROMPT,
        developer_message="",
        user_message=user_msg,
        model=model,
    )

    result = response.parsed
    result["_meta"] = {
        "judge_type": "longitudinal_series",
        "persona": persona_name,
        "num_meetings": len(meeting_analyses),
        "model": response.model,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
    }
    return result


# ── A/B Comparative Judge Runner ─────────────────────────────────────────────

def judge_ab_comparison(
    transcript_data: dict,
    with_history_analysis: dict,
    no_history_analysis: dict,
    prior_meeting_analyses: list[dict],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the A/B comparative judge for one follow-up meeting.

    The two coaching outputs are randomized to positions A/B to avoid
    position bias. The result is de-randomized before returning.

    Args:
        transcript_data: Parsed transcript dict with "turns" key.
        with_history_analysis: The analysis.json (with coaching history).
        no_history_analysis: The analysis_no_history.json (without history).
        prior_meeting_analyses: Condensed history of prior meetings for
            the judge to assess accuracy of history references.
        model: LLM model override.

    Returns:
        Dict with ``preferred`` ("with_history"|"no_history"|"tie"),
        ``reason``, ``dimensions``, and ``_meta``.
    """
    # Randomize assignment
    coin = random.random() < 0.5
    if coin:
        system_a = with_history_analysis
        system_b = no_history_analysis
        a_label = "with_history"
        b_label = "no_history"
    else:
        system_a = no_history_analysis
        system_b = with_history_analysis
        a_label = "no_history"
        b_label = "with_history"

    a_fmt = _format_coaching_for_ab(system_a)
    b_fmt = _format_coaching_for_ab(system_b)

    coaching_history = build_condensed_history(prior_meeting_analyses)
    transcript_text = _format_transcript_text(transcript_data)

    user_msg = _AB_JUDGE_USER_PROMPT.format(
        coaching_history=coaching_history,
        transcript_text=transcript_text,
        system_a_summary=a_fmt["summary"],
        system_a_themes=a_fmt["themes"],
        system_a_experiment=a_fmt["experiment"],
        system_b_summary=b_fmt["summary"],
        system_b_themes=b_fmt["themes"],
        system_b_experiment=b_fmt["experiment"],
    )

    response = call_llm(
        system_prompt=_AB_JUDGE_SYSTEM_PROMPT,
        developer_message="",
        user_message=user_msg,
        model=model,
    )

    result = response.parsed

    # De-randomize
    label_map = {"system_a": a_label, "system_b": b_label, "tie": "tie"}
    raw_preferred = result.get("preferred", "tie")
    result["preferred"] = label_map.get(raw_preferred, raw_preferred)

    for dim_name, dim_val in result.get("dimensions", {}).items():
        if isinstance(dim_val, dict) and "preferred" in dim_val:
            raw = dim_val["preferred"]
            dim_val["preferred"] = label_map.get(raw, raw)

    result["_meta"] = {
        "judge_type": "ab_comparison",
        "randomization": {"system_a": a_label, "system_b": b_label},
        "model": response.model,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
    }
    return result


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_longitudinal_judges(
    phase_dir: Path,
    *,
    model: str | None = None,
    tpm_limit: int = 4_000_000,
    skip_series: bool = False,
    skip_ab: bool = False,
    skip_standard: bool = False,
) -> dict[str, Any]:
    """Run all judge types across all personas in a longitudinal eval.

    Returns summary stats dict.
    """
    judges_dir = phase_dir / "judges"
    judges_dir.mkdir(parents=True, exist_ok=True)

    persona_dirs = sorted(
        d for d in phase_dir.iterdir()
        if d.is_dir() and d.name.startswith("persona_")
    )

    if not persona_dirs:
        logger.error("No persona directories found in %s", phase_dir)
        return {}

    stats: dict[str, Any] = {
        "series_completed": 0,
        "ab_completed": 0,
        "standard_completed": 0,
        "errors": 0,
    }

    max_workers = max(1, min(50, int(tpm_limit * 0.8 / _TOKENS_PER_JUDGE)))

    for p_dir in persona_dirs:
        p_name = p_dir.name
        p_judges_dir = judges_dir / p_name
        p_judges_dir.mkdir(parents=True, exist_ok=True)

        # Load persona info
        persona_path = p_dir / "persona.json"
        if not persona_path.exists():
            logger.warning("No persona.json in %s, skipping", p_dir)
            continue
        persona = json.loads(persona_path.read_text(encoding="utf-8"))
        persona_name = persona.get("name", "unknown")

        # Collect all meeting analyses
        meeting_analyses = _collect_meeting_analyses(p_dir)
        if not meeting_analyses:
            logger.warning("No analyses found for %s, skipping", p_name)
            continue

        # ── Series judge ─────────────────────────────────────────────
        if not skip_series:
            series_path = p_judges_dir / "longitudinal_series.json"
            if series_path.exists():
                logger.info("%s: series judge exists, skipping", p_name)
            else:
                try:
                    logger.info("%s: running series judge (%d meetings)", p_name, len(meeting_analyses))
                    result = judge_longitudinal_series(
                        persona_name, meeting_analyses, model=model,
                    )
                    save_json(result, series_path)
                    stats["series_completed"] += 1
                    logger.info(
                        "%s: series judge → %s",
                        p_name,
                        result.get("overall_longitudinal_value", {}).get("rating", "?"),
                    )
                except Exception as exc:
                    logger.error("%s: series judge failed: %s", p_name, exc, exc_info=True)
                    stats["errors"] += 1

        # ── A/B and standard judges (parallel across meetings) ───────
        ab_tasks = []
        standard_tasks = []

        for entry in meeting_analyses:
            m_num = entry["meeting_number"]
            if m_num <= BASELINE_MEETING_COUNT:
                continue  # only follow-ups

            m_dir = p_dir / f"meeting_{m_num:02d}"
            analysis_path = m_dir / "analysis.json"
            ab_analysis_path = m_dir / "analysis_no_history.json"

            # A/B judge
            if not skip_ab and ab_analysis_path.exists():
                ab_out = p_judges_dir / f"meeting_{m_num:02d}_ab_comparison.json"
                if not ab_out.exists():
                    # Prior meetings for history context
                    prior = [
                        e for e in meeting_analyses if e["meeting_number"] < m_num
                    ]
                    ab_tasks.append((m_dir, m_num, prior, ab_out))

            # Standard per-meeting judge
            if not skip_standard and analysis_path.exists():
                std_out = p_judges_dir / f"meeting_{m_num:02d}_standard.json"
                if not std_out.exists():
                    standard_tasks.append((m_dir, m_num, std_out))

        # Run A/B judges
        if ab_tasks:
            logger.info("%s: running %d A/B judges", p_name, len(ab_tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {}
                for m_dir, m_num, prior, out_path in ab_tasks:
                    futures[pool.submit(
                        _run_ab_judge_task, m_dir, m_num, prior, out_path, model,
                    )] = m_num
                for future in as_completed(futures):
                    m_num = futures[future]
                    try:
                        future.result()
                        stats["ab_completed"] += 1
                    except Exception as exc:
                        logger.error(
                            "%s M%02d: A/B judge failed: %s", p_name, m_num, exc,
                        )
                        stats["errors"] += 1

        # Run standard judges
        if standard_tasks:
            logger.info("%s: running %d standard judges", p_name, len(standard_tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {}
                for m_dir, m_num, out_path in standard_tasks:
                    futures[pool.submit(
                        _run_standard_judge_task, m_dir, m_num, out_path, model,
                    )] = m_num
                for future in as_completed(futures):
                    m_num = futures[future]
                    try:
                        future.result()
                        stats["standard_completed"] += 1
                    except Exception as exc:
                        logger.error(
                            "%s M%02d: standard judge failed: %s", p_name, m_num, exc,
                        )
                        stats["errors"] += 1

    logger.info(
        "Judge run complete: %d series, %d A/B, %d standard, %d errors",
        stats["series_completed"], stats["ab_completed"],
        stats["standard_completed"], stats["errors"],
    )
    return stats


def _collect_meeting_analyses(persona_dir: Path) -> list[dict]:
    """Collect all meeting analyses for a persona, ordered by meeting number."""
    results = []
    for m_dir in sorted(persona_dir.iterdir()):
        if not m_dir.is_dir() or not m_dir.name.startswith("meeting_"):
            continue
        analysis_path = m_dir / "analysis.json"
        metadata_path = m_dir / "metadata.json"
        if not analysis_path.exists() or not metadata_path.exists():
            continue

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

        results.append({
            "meeting_number": metadata.get("meeting_number", 0),
            "meeting_type": metadata.get("meeting_type", "single_meeting"),
            "role": metadata.get("target_role", "participant"),
            "analysis": analysis,
        })

    results.sort(key=lambda x: x["meeting_number"])
    return results


def _run_ab_judge_task(
    m_dir: Path,
    m_num: int,
    prior_analyses: list[dict],
    out_path: Path,
    model: str | None,
) -> None:
    """Run A/B judge for one meeting (thread-pool task)."""
    analysis = json.loads((m_dir / "analysis.json").read_text(encoding="utf-8"))
    no_hist = json.loads((m_dir / "analysis_no_history.json").read_text(encoding="utf-8"))

    transcript_path = m_dir / "transcript.txt"
    transcript_data = load_transcript_for_judge(transcript_path)

    result = judge_ab_comparison(
        transcript_data, analysis, no_hist, prior_analyses, model=model,
    )
    result["_meta"]["meeting_number"] = m_num
    save_json(result, out_path)
    logger.info(
        "  M%02d A/B: preferred=%s (%s)",
        m_num, result.get("preferred", "?"),
        result.get("confidence", "?"),
    )


def _run_standard_judge_task(
    m_dir: Path,
    m_num: int,
    out_path: Path,
    model: str | None,
) -> None:
    """Run standard per-meeting judge for one meeting (thread-pool task)."""
    analysis = json.loads((m_dir / "analysis.json").read_text(encoding="utf-8"))

    transcript_path = m_dir / "transcript.txt"
    transcript_data = load_transcript_for_judge(transcript_path)

    result = judge_analysis(transcript_data, analysis, model=model)
    result["_meta"] = {"meeting_number": m_num}
    save_json(result, out_path)

    gut = result.get("executive_coach_gut_check", {})
    logger.info(
        "  M%02d standard: value=%s, approve=%s",
        m_num,
        gut.get("overall_coaching_value", "?"),
        gut.get("would_approve_for_delivery", "?"),
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run longitudinal judge evaluations.",
    )
    parser.add_argument(
        "--phase-dir", type=Path, required=True,
        help="Path to longitudinal eval results (e.g., backend/evals/results/Long_20260402)",
    )
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--tpm-limit", type=int, default=4_000_000)
    parser.add_argument("--skip-series", action="store_true")
    parser.add_argument("--skip-ab", action="store_true")
    parser.add_argument("--skip-standard", action="store_true")
    args = parser.parse_args()

    run_longitudinal_judges(
        args.phase_dir,
        model=args.model,
        tpm_limit=args.tpm_limit,
        skip_series=args.skip_series,
        skip_ab=args.skip_ab,
        skip_standard=args.skip_standard,
    )


if __name__ == "__main__":
    main()
