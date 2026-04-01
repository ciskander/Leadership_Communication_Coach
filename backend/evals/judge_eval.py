"""
judge_eval.py — Layer 2: LLM-as-Judge Quality Assessment.

Uses a second LLM call to evaluate coaching output quality. The judge
evaluates as an experienced executive coach reviewing session notes —
it does NOT have access to the scoring taxonomy.

Accepts raw transcript files (.vtt, .txt, etc.) — same formats as the UI.

Usage:
  python -m backend.evals.judge_eval \
    --transcript backend/evals/transcripts/meeting.vtt \
    --output backend/evals/results/meeting/run_001.json

  python -m backend.evals.judge_eval \
    --transcript backend/evals/transcripts/meeting.vtt \
    --output-dir backend/evals/results/meeting \
    --all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.core.config import OPENAI_MODEL_DEFAULT, PATTERN_ORDER
from backend.core.llm_client import call_llm
from backend.core.transcript_parser import parse_transcript
from backend.evals.report import save_json, save_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_RESULTS_DIR = Path(__file__).parent / "results"

# ── Judge system prompt ──────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """\
You are an experienced executive coach with 20+ years of experience coaching \
senior leaders. You are reviewing the output of an AI coaching system that \
analyzes meeting transcripts and provides feedback to leaders.

Your job is to evaluate whether the AI's coaching output is genuinely useful, \
well-grounded, and would be valued by a senior leader — or whether it feels \
like the system is pattern-matching for its own sake.

You will be given:
1. The original meeting transcript (speaker turns)
2. The AI system's coaching output (scores, coaching notes, evidence quotes, \
   and suggested rewrites)

Evaluate each dimension below and return a JSON object with your assessment. \
Be direct and critical — the purpose of this review is to improve the system, \
not to be polite about its output.

IMPORTANT: You are evaluating coaching quality from a COACH'S perspective. \
You do NOT have access to the system's internal scoring rubrics or taxonomy. \
Evaluate based on whether the coaching would genuinely help this leader.\
"""

# ── Judge user prompt template ───────────────────────────────────────────────

_JUDGE_USER_PROMPT = """\
## Meeting Transcript

{transcript_text}

## AI Coaching Output

### Executive Summary
{executive_summary}

### Coaching Themes
{coaching_themes_text}

### Strengths Identified
{strengths_text}

### Focus Area
{focus_text}

### Per-Pattern Coaching Notes
{pattern_coaching_text}

### Experiment Coaching
{experiment_coaching_text}

---

## Your Evaluation

Evaluate the AI coaching output on each dimension below. Return a JSON object \
with the following structure:

```json
{{
  "coaching_insight_quality": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "rating": "insightful|adequate|pedantic|wrong",
        "explanation": "<why this rating>"
      }}
    ],
    "pattern_first_detected": <true if any items feel like pattern-matching \
rather than genuine coaching>,
    "overall_notes": "<summary>"
  }},
  "evidence_quality": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "evidence_excerpt_start": "<first 10 words of the quote>",
        "rating": "strong_evidence|weak_evidence|misaligned",
        "explanation": "<why>",
        "better_evidence_exists": <true|false>,
        "better_evidence_description": "<if true, describe what was missed>"
      }}
    ],
    "overall_notes": "<summary>"
  }},
  "success_evidence_quality": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "evidence_span_id": "<span ID>",
        "evidence_excerpt_start": "<first 10 words of the quote>",
        "genuinely_demonstrates_pattern": <true|false>,
        "explanation": "<does this quote genuinely show the speaker doing this \
pattern well, or is it a stretch?>"
      }}
    ],
    "best_example_chosen_well": [
      {{
        "pattern_id": "<pattern>",
        "rating": "best_available|acceptable|better_exists",
        "explanation": "<why — is the BEST-marked quote the most compelling \
example of this pattern, or was there a stronger moment?>",
        "better_span_description": "<if better_exists, describe what was missed>"
      }}
    ],
    "overall_notes": "<summary>"
  }},
  "rewrite_quality": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "rating": "strong_model|generic|misaligned|worse",
        "matches_coaching_note": <true|false>,
        "matches_conversational_moment": <true|false>,
        "explanation": "<why>"
      }}
    ],
    "overall_notes": "<summary>"
  }},
  "coaching_pattern_alignment": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "fits_pattern": <true|false>,
        "better_pattern": "<if false, which pattern would be more natural>",
        "stretching_to_fill": <true|false>,
        "explanation": "<why>"
      }}
    ],
    "overall_notes": "<summary>"
  }},
  "executive_summary_quality": {{
    "rating": "insightful|adequate|generic|misleading",
    "captures_meeting_essence": <true|false>,
    "identifies_key_development_edge": <true|false>,
    "specific_to_this_leader": <true|false>,
    "explanation": "<1-2 sentences: why this rating? An 'insightful' summary captures \
what actually happened in THIS meeting and names a specific development edge for THIS \
leader. 'Generic' means it could describe any competent/struggling leader. 'Misleading' \
means it misrepresents what happened.>"
  }},
  "coaching_themes_quality": {{
    "items": [
      {{
        "theme_text": "<first 15 words of the theme>",
        "rating": "insightful|adequate|generic|stretching",
        "transcends_taxonomy": <true if this theme captures something beyond any single \
communication pattern — e.g. avoidance habits, pace compression, relational dynamics>,
        "names_behavioral_habit": <true if the theme names a specific repeating behavior \
rather than restating a pattern label>,
        "explanation": "<why this rating>"
      }}
    ],
    "themes_vs_patterns": "themes_add_value|themes_just_restate_patterns|no_themes_present",
    "overall_notes": "<Do the themes tell the leader something they wouldn't already \
get from reading the per-pattern coaching notes? Or are they just grouping pattern \
observations under a new heading?>"
  }},
  "internal_consistency": {{
    "score_coaching_aligned": <true|false>,
    "experiment_detection_coherent": <true|false>,
    "executive_summary_reflects_findings": <true|false>,
    "issues": ["<list any inconsistencies found>"]
  }},
  "executive_coach_gut_check": {{
    "balanced": <true|false>,
    "right_growth_areas": <true|false>,
    "leader_would_feel_respected": <true|false>,
    "anything_important_ignored": "<null or description>",
    "anything_over_weighted": "<null or description>",
    "overall_coaching_value": "high|medium|low",
    "would_approve_for_delivery": <true|false>,
    "explanation": "<your overall assessment as an executive coach>"
  }},
  "scoring_arithmetic": {{
    "checked_patterns": [
      {{
        "pattern_id": "<pattern>",
        "reported_score": <score>,
        "computed_score": <recomputed>,
        "match": <true|false>
      }}
    ]
  }}
}}
```

Return ONLY the JSON object, no other text.\
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_transcript_for_judge(transcript_path: Path) -> dict:
    """Load a transcript file (raw or pre-parsed JSON) into a turns dict."""
    if transcript_path.suffix == ".json":
        return json.loads(transcript_path.read_text(encoding="utf-8"))
    else:
        # Raw file — parse it with the transcript parser
        raw_bytes = transcript_path.read_bytes()
        parsed = parse_transcript(raw_bytes, transcript_path.name, transcript_path.stem)
        return {
            "source_id": parsed.source_id,
            "turns": [
                {"turn_id": t.turn_id, "speaker_label": t.speaker_label, "text": t.text}
                for t in parsed.turns
            ],
        }


def _format_transcript_for_judge(transcript_data: dict) -> str:
    """Format transcript turns into readable text for the judge."""
    lines = []
    for turn in transcript_data.get("turns", []):
        lines.append(f"[Turn {turn['turn_id']}] {turn['speaker_label']}: {turn['text']}")
    return "\n".join(lines)


def _format_strengths(coaching: dict) -> str:
    items = coaching.get("strengths", [])
    if not items:
        return "(none)"
    return "\n".join(
        f"- **{s.get('pattern_id', '?')}**: {s.get('message', '')}" for s in items
    )


def _format_focus(coaching: dict) -> str:
    items = coaching.get("focus", [])
    if not items:
        return "(none)"
    return "\n".join(
        f"- **{f.get('pattern_id', '?')}**: {f.get('message', '')}" for f in items
    )


def _format_pattern_coaching(coaching: dict, evidence_spans: list, pattern_snapshot: list) -> str:
    """Format per-pattern coaching with evidence quotes, rewrites, and success evidence."""
    # Build evidence span lookup
    span_map = {es.get("evidence_span_id"): es for es in evidence_spans}
    # Build pattern snapshot lookup
    snapshot_by_pid = {ps.get("pattern_id"): ps for ps in pattern_snapshot}

    items = coaching.get("pattern_coaching", [])
    if not items:
        return "(none)"

    parts = []
    for pc in items:
        pid = pc.get("pattern_id", "?")

        # Skip patterns where both notes and coaching_note are null —
        # these have been suppressed by the editor and won't be shown to
        # the user. Presenting them to the judge as empty headings causes
        # false "taxonomy-filling" pedantic ratings.
        if not pc.get("notes") and not pc.get("coaching_note"):
            continue

        lines = [f"#### {pid}"]

        if pc.get("notes"):
            lines.append(f"**Notes**: {pc['notes']}")
        if pc.get("coaching_note"):
            lines.append(f"**Coaching Note**: {pc['coaching_note']}")

        rewrite_span_id = pc.get("rewrite_for_span_id")
        if rewrite_span_id and rewrite_span_id in span_map:
            span = span_map[rewrite_span_id]
            lines.append(f"**Original (from transcript)**: {span.get('excerpt', '')}")
        if pc.get("suggested_rewrite"):
            lines.append(f"**Suggested Rewrite**: {pc['suggested_rewrite']}")

        # Success evidence quotes
        snap = snapshot_by_pid.get(pid, {})
        success_span_ids = snap.get("success_evidence_span_ids") or []
        best_span_id = pc.get("best_success_span_id")
        if success_span_ids:
            best_label = f" (best_success_span_id: {best_span_id})" if best_span_id else ""
            lines.append(f"**Success Evidence**{best_label}:")
            for sid in success_span_ids:
                span = span_map.get(sid)
                if span:
                    marker = " ← BEST" if sid == best_span_id else ""
                    lines.append(f"- [{sid}] \"{span.get('excerpt', '')}\"{marker}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _format_coaching_themes(coaching: dict) -> str:
    """Format coaching_themes for the judge."""
    themes = coaching.get("coaching_themes", [])
    if not themes:
        return "(none)"
    parts = []
    for t in themes:
        lines = [f"- **{t.get('theme', '?')}** (priority: {t.get('priority', '?')})"]
        if t.get("explanation"):
            lines.append(f"  {t['explanation']}")
        rp = t.get("related_patterns", [])
        if rp:
            lines.append(f"  Related patterns: {', '.join(rp)}")
        else:
            lines.append("  Related patterns: (none — theme transcends taxonomy)")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _format_experiment_coaching(coaching: dict) -> str:
    ec = coaching.get("experiment_coaching")
    if not ec:
        return "(none)"
    lines = []
    if ec.get("coaching_note"):
        lines.append(f"**Coaching Note**: {ec['coaching_note']}")
    if ec.get("suggested_rewrite"):
        lines.append(f"**Suggested Rewrite**: {ec['suggested_rewrite']}")
    return "\n".join(lines) if lines else "(none)"


def _compute_scoring_arithmetic(parsed_json: dict) -> list[dict]:
    """Deterministic check: recompute scores from OEs and compare."""
    oe_by_pattern: dict[str, list[float]] = defaultdict(list)
    for oe in parsed_json.get("opportunity_events", []):
        if oe.get("count_decision") == "counted":
            pid = oe.get("pattern_id")
            success = oe.get("success")
            if pid and success is not None:
                oe_by_pattern[pid].append(success)

    results = []
    for snap in parsed_json.get("pattern_snapshot", []):
        pid = snap.get("pattern_id")
        if snap.get("evaluable_status") != "evaluable" or pid not in oe_by_pattern:
            continue

        reported = snap.get("score")
        oes = oe_by_pattern[pid]
        computed = round(sum(oes) / len(oes), 4) if oes else None

        results.append({
            "pattern_id": pid,
            "reported_score": reported,
            "computed_score": computed,
            "match": reported is not None and computed is not None and abs(reported - computed) < 0.001,
        })
    return results


# ── Main judge function ──────────────────────────────────────────────────────

def judge_analysis(
    transcript_data: dict,
    parsed_json: dict,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the LLM judge on a completed analysis output.

    Returns the judge's structured evaluation.
    """
    model = model or OPENAI_MODEL_DEFAULT

    coaching = parsed_json.get("coaching", {})
    evidence_spans = parsed_json.get("evidence_spans", [])
    pattern_snapshot = parsed_json.get("pattern_snapshot", [])

    # Build the judge prompt
    transcript_text = _format_transcript_for_judge(transcript_data)
    user_message = _JUDGE_USER_PROMPT.format(
        transcript_text=transcript_text,
        executive_summary=coaching.get("executive_summary", "(none)"),
        coaching_themes_text=_format_coaching_themes(coaching),
        strengths_text=_format_strengths(coaching),
        focus_text=_format_focus(coaching),
        pattern_coaching_text=_format_pattern_coaching(coaching, evidence_spans, pattern_snapshot),
        experiment_coaching_text=_format_experiment_coaching(coaching),
    )

    logger.info("Calling judge LLM (model=%s) ...", model)
    t0 = time.time()
    response = call_llm(
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        developer_message="",
        user_message=user_message,
        model=model,
    )
    elapsed = time.time() - t0
    logger.info("Judge returned in %.1fs (%d tokens)", elapsed, response.total_tokens)

    judge_output = response.parsed

    # Add deterministic scoring arithmetic check
    judge_output["scoring_arithmetic"] = {
        "checked_patterns": _compute_scoring_arithmetic(parsed_json),
    }

    return judge_output


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Layer 2: LLM-as-Judge Quality Assessment")
    parser.add_argument("--transcript", type=Path, required=True, help="Path to transcript.json")
    parser.add_argument("--output", type=Path, help="Path to a single analysis output JSON to judge")
    parser.add_argument("--output-dir", type=Path, help="Directory of analysis outputs to judge")
    parser.add_argument("--all", action="store_true", help="Judge all outputs in output-dir")
    parser.add_argument("--model", type=str, default=None, help="Model for the judge LLM")
    args = parser.parse_args()

    transcript_data = load_transcript_for_judge(args.transcript)

    if args.output:
        # Judge a single output
        parsed_json = json.loads(args.output.read_text(encoding="utf-8"))
        result = judge_analysis(transcript_data, parsed_json, model=args.model)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_path = args.output.parent / f"judge_{args.output.stem}_{timestamp}.json"
        save_json(result, out_path)
        _print_summary(result)

    elif args.output_dir and args.all:
        # Judge all run_*.json files in the directory
        output_files = sorted(args.output_dir.glob("run_*.json"))
        if not output_files:
            logger.error("No run_*.json files found in %s", args.output_dir)
            sys.exit(1)

        for output_file in output_files:
            logger.info("Judging %s ...", output_file.name)
            parsed_json = json.loads(output_file.read_text(encoding="utf-8"))
            result = judge_analysis(transcript_data, parsed_json, model=args.model)

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            out_path = args.output_dir / f"judge_{output_file.stem}_{timestamp}.json"
            save_json(result, out_path)
            _print_summary(result)
    else:
        parser.error("Provide either --output or --output-dir with --all")


def _print_summary(result: dict) -> None:
    """Print a brief summary of the judge's findings."""
    gut = result.get("executive_coach_gut_check", {})
    print(f"\n  Overall coaching value: {gut.get('overall_coaching_value', '?')}")
    print(f"  Would approve for delivery: {gut.get('would_approve_for_delivery', '?')}")
    print(f"  Leader would feel respected: {gut.get('leader_would_feel_respected', '?')}")

    insight = result.get("coaching_insight_quality", {})
    if insight.get("pattern_first_detected"):
        print("  WARNING: Pattern-first coaching detected")

    items = insight.get("items", [])
    for item in items:
        if item.get("rating") in ("pedantic", "wrong"):
            print(f"  FLAG: {item['pattern_id']} rated '{item['rating']}': {item.get('explanation', '')[:80]}")

    success_ev = result.get("success_evidence_quality", {})
    for item in success_ev.get("items", []):
        if not item.get("genuinely_demonstrates_pattern"):
            print(f"  FLAG: {item.get('pattern_id', '?')} success evidence doesn't demonstrate pattern: {item.get('explanation', '')[:80]}")
    for item in success_ev.get("best_example_chosen_well", []):
        if item.get("rating") == "better_exists":
            print(f"  FLAG: {item.get('pattern_id', '?')} better success example exists: {item.get('explanation', '')[:80]}")

    arith = result.get("scoring_arithmetic", {})
    for check in arith.get("checked_patterns", []):
        if not check.get("match"):
            print(f"  ARITH MISMATCH: {check['pattern_id']} reported={check['reported_score']} computed={check['computed_score']}")

    print()


if __name__ == "__main__":
    main()
