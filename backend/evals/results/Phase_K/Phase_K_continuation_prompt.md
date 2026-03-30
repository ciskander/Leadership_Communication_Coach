# Phase L: Architecture Redesign — Continuation Prompt

## What this is

You are redesigning the analysis pipeline architecture to cleanly separate behavioral detection/scoring (Stage 1) from coaching synthesis (Stage 2). Read `Phase_K_synthesis.md` (same directory) for the variance decomposition findings that motivated this.

## The key insight

The current architecture asks the 1st LLM pass to simultaneously: (1) detect behavioral moments, (2) score them against rubrics, and (3) generate coaching text. These three functions have conflicting requirements:

- **Detection** needs MECE categories with bright lines
- **Scoring** needs nuanced rubrics that inevitably bleed into adjacent patterns
- **Coaching** needs holistic judgment that cuts across patterns

The taxonomy tried to handle all three through cross-pattern disambiguation rules, coaching-note distinctiveness tests, and reclassification instructions. Phases G-I2 proved the LLM ignores most of these. The editor (Phase J) was bolted on to fix coaching quality after the fact, but it became a suppression gate rather than a coaching intelligence.

94% of pedantic ratings come from misalignment (55%) and stretching-to-fill (39%) -- both caused by the detection layer trying to serve coaching needs it can't fulfill.

## Proposed two-stage architecture

**Stage 1: Detect + Score (tunnel vision, per-pattern)**
- Identifies behavioral moments (opportunity events) per pattern
- Scores each moment against that pattern's mechanical rubric
- Does NOT attempt cross-pattern reasoning or coaching generation
- Overlap is ALLOWED -- the same moment can appear under multiple patterns
- The taxonomy is simplified: remove cross-pattern reclassification rules, coaching-note distinctiveness tests, and detection notes that try to disambiguate overlapping patterns
- Keep: behavioral definitions, mechanical scoring rubrics, element-counting, evidence spans

**Stage 2: Coaching Synthesis (holistic, cross-pattern)**
- Receives the full Stage 1 output + transcript
- Applies executive coaching judgment to determine what's really going on
- Suppresses patterns that don't add value, elevates the ones that matter
- Synthesizes across patterns: "your handling of Quinn's concerns across FM, DN, and TC moments suggests a pattern of defensive focus management"
- Generates the actual coaching output (executive summary, strengths, focus area, micro-experiment)

## Open architectural questions (to decide before implementing)

### Q1: Does Stage 1 generate coaching text at all?

**Option A -- Stage 1 detects + scores only.** Stage 2 generates ALL coaching text from scratch using Stage 1's scored OEs and evidence spans. Cleaner separation, but Stage 2 becomes the primary coaching author (bigger rewrite). The current editor is a lightweight delta-based editor; this would make it the main coaching engine.

**Option B -- Stage 1 generates draft coaching, Stage 2 refines.** Keeps current architecture with simplified Stage 1 taxonomy (no cross-pattern rules). Stage 2 still synthesizes, suppresses, elevates, but works from draft coaching. Less disruptive but preserves the "edit bad coaching" pattern that produced the problems we measured.

**Trade-offs:** Option A is architecturally cleaner but a bigger change. Option B is incremental but may not fully resolve the pedantic problem because Stage 1 still generates coaching through per-pattern tunnel vision. Consider: is the coaching text from Stage 1 a useful starting point for Stage 2, or does it constrain Stage 2's judgment?

### Q2: What happens to scoring and progress tracking?

The current system tracks scores per pattern. With a two-stage architecture:
- Stage 1's mechanical scores (behavioral frequencies + quality rubric) are the progress metrics
- Stage 2's coaching doesn't need to map 1:1 to Stage 1's patterns

This means: scores track behavioral mechanics ("redirect quality went from 0.5 to 0.8"), coaching addresses holistic themes ("your defensive use of redirects is eroding trust"). Acting on the coaching should improve the behavioral scores because the coaching is grounded in the same rubric dimensions.

Key validation question: if a coachee improves their scores, does that actually represent better leadership? If the rubrics measure the right quality dimensions (not just frequency), then yes. The current rubrics already do this well -- e.g., FM's distinction between 1.0 (genuine tangent redirect) and 0.0 (suppressing a risk signal) is a meaningful quality dimension.

### Q3: How does the judge need to change?

The current judge evaluates per-pattern coaching quality. With Stage 2 producing synthesized cross-pattern coaching, the judge needs to evaluate:
- Is the coaching insight genuine and non-obvious? (keeps current `coaching_insight_quality`)
- Does the coaching address the most important leadership moments? (new)
- Is the synthesis accurate -- does the cross-pattern interpretation hold up against the transcript? (new)
- Are the behavioral scores from Stage 1 accurate? (keeps current `scoring_arithmetic` + `evidence_quality`)

## Current state

### What exists and can be reused
- **Stage 1 foundation**: The 1st-pass prompt + taxonomy (needs simplification, not replacement)
- **Stage 2 foundation**: `backend/core/editor.py` -- `run_editor()`, `merge_editor_output()`, delta format, pipeline integration at `backend/core/workers.py`
- **Eval infrastructure**: `backend/evals/replay_eval.py`, `backend/evals/judge_eval.py`, `backend/evals/variance_eval.py`
- **Scoring rubrics**: The 0.0-1.0 tier definitions in the taxonomy are valuable and well-designed
- **7 test transcripts** with extensive baseline data (Phases A-K)

### Codebase references
- **Branch**: `main`
- **Taxonomy**: `clearvoice_pattern_taxonomy_v3.0.txt` (project root)
- **System prompt**: `system_prompt_v0_4_0.txt` (project root)
- **Editor**: `backend/core/editor.py`, `system_prompt_editor_v1.0.txt`, `editor_pattern_definitions_v1.0.txt`
- **Pipeline**: `backend/core/workers.py` (editor integration at line ~622)
- **Config**: `backend/core/config.py` (`PATTERN_ORDER`, model defaults)
- **Eval results**: `backend/evals/results/Phase_I2/` (pre-editor baseline), `Phase_J2/` (post-editor), `Phase_K/` (variance decomposition)

### Pattern stability data (SNR from Phase I2)

| Pattern | SNR | Notes |
|---------|-----|-------|
| participation_management | 56.0 | Excellent |
| communication_clarity | 22.4 | Good |
| trust_and_credibility | 14.0 | Good SNR but #1 misalignment source |
| purposeful_framing | 13.4 | Good |
| disagreement_navigation | 9.7 | Moderate -- overlaps FM, TC |
| question_quality | 8.0 | Moderate -- overlaps FM, PM |
| assignment_clarity | 5.8 | Weak -- overlaps RA |
| resolution_and_alignment | 5.6 | Weak -- overlaps AC |
| feedback_quality | 5.0 | Weak (2 meetings evaluable) |
| focus_management | 3.0 | Weakest -- most overlap |

### What Phases G-I2 taught about LLM capabilities

**Reliably follows:** Rubric-level scoring, materiality/distinctiveness tests, meeting-type-aware filtering.

**Ignores:** Cross-pattern reclassification, coaching-note distinctiveness on overlapping patterns, cross-pattern reasoning, system prompt suppression rules.

## Suggested execution approach

1. **Decide Q1** (Stage 1 coaching text: yes or no)
2. **Simplify the taxonomy** for Stage 1 (remove cross-pattern rules, keep scoring rubrics)
3. **Redesign the Stage 2 prompt** (from delta-editor to coaching synthesizer)
4. **Run eval** on all 7 transcripts, compare against Phase I2 baseline
5. **Update the judge** if needed for synthesized coaching evaluation
6. **Iterate** based on results
