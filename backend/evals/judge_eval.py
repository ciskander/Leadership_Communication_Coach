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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

### Coaching Themes (with evidence)
{coaching_themes_text}

### Focus Area
{focus_text}

### Per-Pattern Coaching Notes
{pattern_coaching_text}

### Experiment Coaching
{experiment_coaching_text}

---

## Your Evaluation

Evaluate the AI coaching output on each dimension below. Return a JSON object \
with the following structure.

IMPORTANT — Status cards vs substantive cards:
Patterns marked [STATUS CARD] are intentional brief acknowledgments. The system \
deliberately chose not to give substantive coaching on these patterns because \
they are not central to the meeting's coaching story. Rate status cards \
differently from substantive cards:
- Substantive cards (no [STATUS CARD] label): set card_type to "substantive" \
and rate as "insightful", "adequate", "pedantic", or "wrong" based on coaching \
quality.
- Status cards (marked [STATUS CARD]): set card_type to "status" and rate as \
"appropriate" (accurate, doesn't mislead), "over_coaching" (contains coaching \
advice better suited to a substantive card), or "misleading" (misrepresents \
performance).

```json
{{
  "coaching_insight_quality": {{
    "items": [
      {{
        "pattern_id": "<pattern>",
        "card_type": "substantive|status",
        "rating": "<see rating rules below>",
        "explanation": "<why this rating>"
      }}
    ],
    "pedantic_count": <number of SUBSTANTIVE items rated 'pedantic' in the items array above — do NOT count status cards>,
    "total_patterns_judged": <total number of items in the items array above>,
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
        "nature": "<strength|developmental|mixed>",
        "rating": "insightful|adequate|generic|stretching",
        "nature_accurate": <true if the nature classification is correct>,
        "nature_explanation": "<Is the classification correct? Is a 'strength' theme \
actually showing strong behavior? Is 'developmental' actually a gap? Does a 'mixed' \
theme genuinely show capability in some moments and missed opportunities in others?>",
        "evidence_grounding": "well_grounded|adequate|weak|misaligned",
        "evidence_explanation": "<Does the selected evidence quote genuinely support \
this theme's claims? For strength themes: does the best_success quote show the \
behavior done well? For developmental/mixed: does the rewrite quote show the \
coachable moment?>",
        "coaching_note_quality": "actionable|generic|misaligned|null",
        "coaching_note_explanation": "<For developmental/mixed themes: is the coaching \
note specific to THIS leader in THIS meeting and actionable? null for strength themes.>",
        "rewrite_quality": "strong_model|generic|misaligned|null",
        "rewrite_explanation": "<For developmental/mixed themes: does the suggested \
rewrite genuinely improve on what was said while staying natural? null for strength themes.>",
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

        # Detect status cards: exactly one content field, no supporting fields.
        # Status cards are intentional brief acknowledgments, not substantive coaching.
        has_notes = bool(pc.get("notes"))
        has_cn = bool(pc.get("coaching_note"))
        has_supporting = bool(pc.get("best_success_span_id")) or bool(pc.get("suggested_rewrite")) or bool(pc.get("rewrite_for_span_id"))
        is_status_card = (has_notes != has_cn) and not has_supporting

        if is_status_card:
            lines = [f"#### {pid} [STATUS CARD]"]
        else:
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


def _format_coaching_themes(coaching: dict, evidence_spans: list | None = None) -> str:
    """Format coaching_themes with nature and evidence for the judge.

    Each theme includes its nature classification, evidence grounding,
    and coaching artifacts (coaching_note, suggested_rewrite for
    developmental/mixed; best_success quote for strength themes).
    """
    themes = coaching.get("coaching_themes", [])
    if not themes:
        return "(none)"

    # Build evidence span lookup for resolving IDs to quotes
    span_map: dict[str, dict] = {}
    if evidence_spans:
        span_map = {es.get("evidence_span_id", ""): es for es in evidence_spans}

    parts = []
    for t in themes:
        nature = t.get("nature", "developmental")
        lines = [
            f"#### {t.get('theme', '?')} "
            f"(priority: {t.get('priority', '?')}, nature: {nature})"
        ]
        if t.get("explanation"):
            lines.append(f"**Explanation**: {t['explanation']}")

        rp = t.get("related_patterns", [])
        if rp:
            lines.append(f"**Related patterns**: {', '.join(rp)}")

        # Evidence grounding
        if nature == "strength":
            best_span_id = t.get("best_success_span_id")
            if best_span_id and best_span_id in span_map:
                span = span_map[best_span_id]
                lines.append(
                    f"**Strength evidence** [{best_span_id}]: "
                    f"\"{span.get('excerpt', '')}\""
                )
            elif best_span_id:
                logger.warning(
                    "Theme '%s': best_success_span_id %s not found in evidence_spans",
                    t.get("theme", "?"), best_span_id,
                )
                lines.append(f"**Strength evidence**: {best_span_id} (quote not resolved)")
        else:
            # Developmental or mixed — show coaching artifacts
            if t.get("coaching_note"):
                lines.append(f"**Coaching Note**: {t['coaching_note']}")

            rewrite_span_id = t.get("rewrite_for_span_id")
            if rewrite_span_id and rewrite_span_id not in span_map:
                logger.warning(
                    "Theme '%s': rewrite_for_span_id %s not found in evidence_spans",
                    t.get("theme", "?"), rewrite_span_id,
                )
            if rewrite_span_id and rewrite_span_id in span_map:
                span = span_map[rewrite_span_id]
                lines.append(
                    f"**Original (from transcript)** [{rewrite_span_id}]: "
                    f"\"{span.get('excerpt', '')}\""
                )
            if t.get("suggested_rewrite"):
                lines.append(f"**Suggested Rewrite**: {t['suggested_rewrite']}")

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
        coaching_themes_text=_format_coaching_themes(coaching, evidence_spans),
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
        # Judge all run_*.json files in the directory, skipping already-judged
        output_files = sorted(args.output_dir.glob("run_*.json"))
        if not output_files:
            logger.error("No run_*.json files found in %s", args.output_dir)
            sys.exit(1)

        # Skip runs that already have judge output
        existing_judges = {f.name for f in args.output_dir.glob("judge_*.json")}
        to_judge = []
        for output_file in output_files:
            # Check if any judge file exists for this run stem
            has_judge = any(j.startswith(f"judge_{output_file.stem}_") for j in existing_judges)
            if has_judge:
                logger.info("Skipping %s (already judged)", output_file.name)
            else:
                to_judge.append(output_file)

        if not to_judge:
            logger.info("All %d runs already judged, nothing to do", len(output_files))
        else:
            logger.info("Judging %d runs (%d skipped)", len(to_judge), len(output_files) - len(to_judge))

            def _judge_one(output_file: Path) -> tuple[Path, dict]:
                parsed_json = json.loads(output_file.read_text(encoding="utf-8"))
                result = judge_analysis(transcript_data, parsed_json, model=args.model)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                out_path = args.output_dir / f"judge_{output_file.stem}_{timestamp}.json"
                save_json(result, out_path)
                return output_file, result

            with ThreadPoolExecutor(max_workers=len(to_judge)) as pool:
                futures = {pool.submit(_judge_one, f): f for f in to_judge}
                for future in as_completed(futures):
                    output_file = futures[future]
                    try:
                        _, result = future.result()
                        logger.info("Completed %s", output_file.name)
                        _print_summary(result)
                    except Exception as exc:
                        logger.error("Failed %s: %s", output_file.name, exc)
    else:
        parser.error("Provide either --output or --output-dir with --all")


def _print_summary(result: dict) -> None:
    """Print a brief summary of the judge's findings."""
    gut = result.get("executive_coach_gut_check", {})
    print(f"\n  Overall coaching value: {gut.get('overall_coaching_value', '?')}")
    print(f"  Would approve for delivery: {gut.get('would_approve_for_delivery', '?')}")
    print(f"  Leader would feel respected: {gut.get('leader_would_feel_respected', '?')}")

    insight = result.get("coaching_insight_quality", {})
    pedantic = insight.get("pedantic_count", 0)
    total = insight.get("total_patterns_judged", 0)
    if pedantic:
        print(f"  WARNING: {pedantic}/{total} patterns rated pedantic")

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
