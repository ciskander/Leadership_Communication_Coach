# Taxonomy v4.0 — Phase 2 Coaching Quality Refinement: Continuation Prompt

## Context

We completed the Phase 2 taxonomy implementation (Active Listening + Recognition patterns, 9 -> 11 patterns) and ran multiple rounds of validation with judge evaluation. The final validation run is at `backend/evals/results/v4p2_recognition_fix`.

The plan file for this work is at: `.claude/plans/atomic-launching-dragonfly.md`

Read the plan file before doing anything. It contains the full analysis of the problem, the judge feedback data, and the proposed approach.

This session implements the coaching quality refinements described in the plan.

## What This Session Changes

Three categories of changes, all aimed at reducing pedantic coaching output:

### 1. General coaching quality principle (taxonomy + coaching prompt)

Add guidance that applies to ALL pattern coaching output — not per-pattern, but as a general principle. Two parts:

**Part 1 — Coaching relevance:** Before generating coaching for any pattern, ask whether the observation is worth pointing out to this leader in the context of the meeting as a whole and their broader coaching journey. The goal is coaching a senior executive coach would actually deliver.

**Part 2 — Behavioral context:** Generalize the existing QQ/CC behavioral context notes into a principle that applies to all patterns. When the meeting shows a dominant failure (dismissiveness, avoidance, coercion), pattern-level coaching that praises surface mechanics without acknowledging the larger dynamic is tone-deaf.

### 2. No empty pattern cards

Every evaluable pattern must say something to the coachee. Options when a pattern's observation is secondary:
- Brief acknowledgment: "You're consistently strong here; no developmental notes."
- Cross-reference: "See [theme/pattern] for the dynamic that affected this."
- Contextual framing: connect the pattern observation to the meeting's real issue.

Every evaluable pattern should have at least `notes` or `coaching_note` (or both). No nulls on both fields.

### 3. Pattern-specific tightening

- **R&A:** Add detection note about coerced alignment
- **AL:** Add detection note distinguishing genuine absorption from selective hearing/reassurance

## Files to Modify

| File | Change |
|------|--------|
| `clearvoice_pattern_taxonomy_v4.0.txt` | Add general coaching quality principle to COACHING OUTPUT RULES or GENERAL_DETECTION_GUIDANCE; R&A and AL detection notes |
| `system_prompt_coaching_v1.0.txt` | Strengthen guidance on pattern_coaching generation — no empty cards, coaching relevance bar, behavioral context awareness |
| `system_prompt_baseline_pack_v0_6_0.txt` | Same if applicable (baseline pack also generates pattern_coaching) |

## Critical Constraints

- Do NOT change scoring logic or denominators — this is purely about coaching output quality
- Do NOT add pattern-specific behavioral context notes to all 7 affected patterns — use a general principle instead
- The general principle must be concise — the taxonomy is already long, don't bloat it
- The "no empty cards" rule must be implemented carefully — the LLM should generate useful content, not boilerplate filler
- All changes are to prompt text only — no schema, backend, or frontend code changes

## Eval Approach

Run the same 3 test transcripts used throughout Phase 2 validation:
- Transcripts are in `backend/evals/transcripts_v4_test/` (M-000003, M-000004, M-000005)
- Run as `--phase v4p2_coaching_quality` using `run_pipeline.py`
- Keep previous results (`v4p2_recognition_fix`, `v4p2_validation`) for comparison

Compare:
- Per-pattern pedantic rates (target: reduce across all 7 affected patterns)
- Per-pattern insightful rates (target: maintain or improve)
- Empty pattern card count (target: zero)
- Overall coaching value ratings

## Reference Data

Phase O (v3.1, same 3 meetings): 40% insightful, 15% pedantic (N=108)
v4p2_recognition_fix (current): 35% insightful, 13% pedantic (N=109)

Patterns with 0% pedantic that we want to keep clean: FM, BI, DN, FQ
