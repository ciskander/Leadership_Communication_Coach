# Taxonomy v4.0 — Phase 2 Coaching Quality Refinement: Continuation Prompt

## Context

We completed the Phase 2 taxonomy implementation (Active Listening + Recognition patterns, 9 → 11 patterns) and ran multiple validation rounds with LLM-as-judge evaluation. The structural taxonomy work is done — this session is about improving **coaching output quality** (primarily Stage 2 coaching prompt changes, plus minor taxonomy detection note additions).

IMPORTANT NOTE FOR THE SESSION: Never make assumptions. If anything is ambiguous, inconsistent, underspecified, or otherwise unclear, always stop and ask questions before proceeding. Precision and correctness are 10x more important than development speed.

Three goals:
1. Reduce pedantic coaching (currently 13% of judge ratings)
2. Eliminate empty pattern cards (some evaluable patterns produce scores with no coaching content)
3. Improve coaching relevance — coaching should reflect what a senior executive coach would actually say

## Problem Analysis

We ran `judge_eval` on 3 transcripts x 5 runs (results at `backend/evals/results/v4p2_recognition_fix`). Analysis of all 14 pedantic judge ratings revealed 3 themes:

### Theme A: "Taxonomy-filling" — praising trivial competence (7 of 14 pedantic ratings)

The system generates technically-accurate positive observations that aren't worth mentioning. A senior coach would never bother saying these things.

Judge feedback examples:
- **CC on M-000003:** "Alex was clear, but clarity is not the interesting issue here"
- **CC on M-000004:** "clarity is not the interesting issue here... risks rewarding bluntness detached from judgment"
- **QQ on M-000004:** "His questions are mostly operational prompts after he has already foreclosed debate. This feels taxonomy-driven."
- **AC on M-000005:** "'follow up with them directly' is basic meeting hygiene, not meaningful evidence of a coaching strength"
- **Recognition on M-000003:** "'good call' is not a meaningful coaching theme for a senior leader"
- **AL on M-000005:** "Jordan does occasionally validate intent, but the bigger truth is that he repeatedly fails to respond to Avery's direct requests"

### Theme B: "Overplayed marginal development point" (3 of 14)

The leader is already competent on the pattern. Minor gaps get inflated into coaching points that aren't the real growth edge.

- **PF on M-000003 (x2):** "the main growth edge is crisper transitions feels like taxonomy-driven nitpicking" — the leader already framed well
- **AC on M-000005:** "technically true for the narrow follow-up... but not coaching-relevant to the core developmental issue"

### Theme C: "Praising mechanics while ignoring substance failure" (4 of 14)

The system praises pattern-level technical competence when the broader meeting dynamic makes that praise tone-deaf.

- **R&A on M-000004:** "praises closure mechanics without grappling with the fact that the alignment was largely coerced"
- **QQ on M-000004:** "questions are mostly operational prompts after he has already foreclosed debate" (Note: this same judge comment also appears under Theme A — it exhibits both themes simultaneously)
- **AL on M-000005:** "system is mistaking occasional reassurance for active listening. The deeper meeting reality is that Jordan does not listen well when Avery asks for clarification."

**Existing precedents:** QQ and CC already have "behavioral context" detection notes in the taxonomy that address Theme C for those specific patterns. See QQ detection notes (search for "Behavioral context") and CC detection notes (same search). The principle needs to be generalized to all patterns.

## What This Session Changes

### 1. General coaching quality principle (taxonomy + coaching prompt)

Add guidance that applies to ALL pattern coaching output. Two parts:

**Part 1 — Coaching relevance (Themes A + B):** Before generating coaching for any pattern, ask whether the observation is worth pointing out to this leader in the context of the meeting as a whole and their broader coaching journey. Trivially true, unremarkably competent, or marginal observations are not worth coaching space. When an observation doesn't clear this bar, connect it to something that DOES matter rather than generating filler.

**Part 2 — Behavioral context (Theme C):** When the meeting shows a dominant interpersonal or substance failure (dismissiveness, avoidance, coercion), pattern-level coaching that praises surface mechanics without acknowledging the larger dynamic is tone-deaf. The coaching should either name the real dynamic or connect the pattern observation to it. This generalizes the existing QQ/CC behavioral context notes to all patterns.

**Where to put this:** Either in COACHING OUTPUT RULES within CORE_RULES, or in GENERAL_DETECTION_GUIDANCE. Read both sections and decide which is the better fit. The principle must be concise — the taxonomy is already long.

### 2. No empty pattern cards

Currently, some evaluable pattern cards in the UI show a score with no coaching content (both `notes` and `coaching_note` are null). This is a UX bug that needs to be eliminated.

**Rule:** Every evaluable pattern must have at least `notes` or `coaching_note` (or both). When a pattern's observation is secondary to the meeting's main coaching point, the card should still speak:
- Brief acknowledgment: "You're consistently strong here; no developmental notes."
- Cross-reference: "For detailed feedback on the dynamic that affected this pattern, see [theme/pattern]."
- Contextual framing: "Your [pattern behavior] was technically solid, but in this meeting the more consequential issue was X."

**Where to implement:** In `system_prompt_coaching_v1.0.txt` (Stage 2 coaching generation instructions) and in `system_prompt_baseline_pack_v0_6_0.txt` (also generates pattern_coaching). Look for the existing pattern_coaching generation section in each file — that's where the "no empty cards" rule goes.

**Important:** The LLM should generate genuinely useful content, not boilerplate filler. "No notes for this pattern" repeated across 5 cards is worse than selective nulls.

**Existing guidance to replace:** The coaching prompt and taxonomy currently contain multiple instructions that say "set coaching_note to null" in various situations (e.g., when a theme already covers the insight, when the observation is redundant with another pattern, when the BI repackaging check fails). These instructions need to be replaced — not just supplemented — with guidance that always produces useful content for evaluable, detected patterns. At the end of this session, there should be NO remaining "set coaching_note to null" instructions for patterns that are evaluable and detected. Instead, the guidance should tell the LLM what to write in each situation (brief acknowledgment, cross-reference to relevant theme/pattern, contextual framing, etc.). Read the existing coaching prompt and taxonomy carefully and identify ALL such null instructions before making changes.

### 3. Pattern-specific tightening

Two patterns had specific judge feedback that points to detection-level issues (not just coaching output):

- **R&A:** The judge flagged "praises closure mechanics without grappling with the fact that the alignment was largely coerced." Add a detection note that helps the LLM recognize coerced alignment — if "alignment" was achieved through authority override rather than genuine agreement, the closure is procedural, not substantive. This is detection guidance (helps the LLM score more accurately), not a scoring rule change. Coaching should name the coercion dynamic rather than praising the closure mechanics.

- **AL:** The judge flagged "system is mistaking occasional reassurance for active listening." Add a detection note distinguishing genuine absorption (paraphrasing, building, integrating substance) from selective hearing — "I hear you" followed by ignoring the substance is not active listening, it's a social signal that masks non-engagement.

## Files to Modify

| File | Change |
|------|--------|
| `clearvoice_pattern_taxonomy_v4.0.txt` | General coaching quality principle; R&A and AL detection notes |
| `system_prompt_coaching_v1.0.txt` | No-empty-cards rule in pattern_coaching section; coaching relevance guidance |
| `system_prompt_baseline_pack_v0_6_0.txt` | Same no-empty-cards rule if this file generates pattern_coaching |

## Critical Constraints

- Do NOT change scoring logic or denominators — scoring is validated and stable
- Do NOT add per-pattern behavioral context notes to all 7 affected patterns — use a general principle
- The general principle must be concise
- The "no empty cards" rule must produce genuinely useful content, not boilerplate
- All changes are prompt text only — no schema, backend, or frontend code changes
- Preserve the existing QQ and CC behavioral context notes (they're battle-tested); the general principle supplements rather than replaces them

## Eval Approach

Run the same 3 test transcripts:
- Transcripts in `backend/evals/transcripts_v4_test/` (copies of M-000003, M-000004, M-000005 from `backend/evals/transcripts/`)
- Command: `python -m backend.evals.run_pipeline --phase v4p2_coaching_quality --transcripts-dir backend/evals/transcripts_v4_test --runs 5 --judge`
- Keep `v4p2_recognition_fix` and `v4p2_validation` results for comparison

Compare:
- Per-pattern pedantic rates (target: reduce across the 7 patterns listed below)
- Per-pattern insightful rates (target: maintain or improve)
- Empty pattern card count (target: zero — check every evaluable pattern across all 15 runs)
- Overall coaching value ratings

## Reference Data

### Current per-pattern ratings (v4p2_recognition_fix, 3 meetings x 5 runs):

| Pattern | Ins% | Ade% | Ped% | N |
|---------|------|------|------|---|
| purposeful_framing | 15% | 69% | **15%** | 13 |
| focus_management | 40% | 60% | 0% | 5 |
| resolution_and_alignment | 60% | 30% | **10%** | 10 |
| assignment_clarity | 0% | 80% | **20%** | 15 |
| question_quality | 58% | 25% | **17%** | 12 |
| communication_clarity | 0% | 75% | **25%** | 12 |
| active_listening | 20% | 60% | **20%** | 10 |
| recognition | 10% | 80% | **10%** | 10 |
| behavioral_integrity | 100% | 0% | 0% | 6 |
| disagreement_navigation | 67% | 33% | 0% | 9 |
| feedback_quality | 100% | 0% | 0% | 1 |
| **Aggregate** | **35%** | **52%** | **13%** | **109** |

### Phase O baseline (v3.1, same 3 meetings, 9 patterns):
Aggregate: 40% insightful, 45% adequate, 15% pedantic, 0% wrong (N=108)

### Transcripts used:
- M-000003_contentious_meeting: cross-functional project review, chair role, multiple disagreements (Alex)
- M-000004_avoider: project review, chair role, leader dismisses substantive input (Alex)
- M-000005_weak_feedback: 1:1 manager meeting, weak feedback delivery with vague unnamed sourcing (Jordan)
