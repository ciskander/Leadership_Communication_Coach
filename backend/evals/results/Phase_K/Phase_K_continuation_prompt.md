# Phase L: Taxonomy Redesign — Continuation Prompt

## What this is

You are redesigning the pattern taxonomy from first principles. The full analysis motivating this is in `Phase_K_synthesis.md` (same directory). Read it first.

## Current state

### Codebase
- **Branch**: `main`
- **Current taxonomy**: `clearvoice_pattern_taxonomy_v3.0.txt` (project root)
- **System prompt**: `system_prompt_v0_4_0.txt` (project root)
- **Editor prompt**: `system_prompt_editor_v1.0.txt` (project root)
- **Editor pattern defs**: `editor_pattern_definitions_v1.0.txt` (project root)
- **Pattern order constant**: `backend/core/config.py` line 63 (`PATTERN_ORDER`)
- **Eval scripts**: `backend/evals/replay_eval.py`, `backend/evals/judge_eval.py`, `backend/evals/variance_eval.py`
- **7 test transcripts**: `backend/evals/transcripts/`

### Results directory
- `backend/evals/results/Phase_K/` -- variance decomposition results + synthesis report
- `backend/evals/results/Phase_I2/` -- pre-editor baseline (5 runs x 7 meetings)
- `backend/evals/results/Phase_J2/` -- post-editor results (5 runs x 7 meetings)

## The problem

The current 10-pattern taxonomy is not MECE (mutually exclusive, collectively exhaustive). Several patterns measure the same observable behavior through different interpretive lenses:

1. **FM/DN/TC cluster**: Same conflict-handling moments detected by all three, classified by inferred "primary" lens. LLM cannot reliably distinguish.
2. **QQ/FM/PM cluster**: Same speech acts classified by inferred functional purpose. Inherently subjective.
3. **AC/RA overlap**: Decisions and assignments blur when woven together.

This produces:
- 55% of pedantic ratings caused by misalignment (coaching assigned to wrong pattern)
- 39% caused by stretching to fill (thin evidence forced into a category)
- ~10% pedantic floor that 5 phases of taxonomy tweaking (G-I2) could not break

## Design constraints for the new taxonomy

1. **MECE at the behavioral level**: Each pattern should be triggered by a distinct observable behavior, not by inferring intent or purpose from the same behavior.
2. **Stable detection**: The LLM should assign a given transcript moment to exactly one pattern with high consistency across runs.
3. **Coaching value**: Each pattern should produce actionable, non-obvious coaching that a senior leader would find useful.
4. **Reasonable count**: Aim for 6-8 patterns (fewer = cleaner boundaries, but must still be collectively exhaustive).
5. **Backward compatibility consideration**: The existing eval transcripts and judge should still work. The judge prompt may need updates but the evaluation methodology should be preserved.

## What the Phase G-I2 experiments taught us about LLM capabilities

**Rules the LLM follows reliably:**
- Rubric-level scoring disqualifiers (e.g., "this scores 0.0")
- Materiality/distinctiveness tests for coaching_notes
- Meeting-type-aware OE filtering

**Rules the LLM ignores or misapplies:**
- Cross-pattern reclassification ("exclude from X, reclassify to Y")
- Coaching-note distinctiveness on overlapping patterns
- Cross-pattern reasoning (evaluating one pattern based on another's results)
- System prompt quality gates / suppression rules

## Pattern stability data (SNR from Phase I2)

| Pattern | SNR | Notes |
|---------|-----|-------|
| participation_management | 56.0 | Excellent (5 meetings) |
| communication_clarity | 22.4 | Good -- measures HOW you say it |
| trust_and_credibility | 14.0 | Good SNR but 4/17 misalignment source |
| purposeful_framing | 13.4 | Good -- proactive direction-setting |
| disagreement_navigation | 9.7 | Moderate -- overlaps with FM and TC |
| question_quality | 8.0 | Moderate -- overlaps with FM and PM |
| assignment_clarity | 5.8 | Weak -- overlaps with RA |
| resolution_and_alignment | 5.6 | Weak -- overlaps with AC |
| feedback_quality | 5.0 | Weak but only 2 meetings evaluable |
| focus_management | 3.0 | Weakest -- most overlap with DN and TC |

## Approach suggestions

Consider organizing patterns around one of these axes:

**Option A: Behavioral mechanics** -- What did the speaker observably do?
- Structure/frame (opening, transitioning, closing)
- Direct the floor (invite, redirect, yield)
- Probe/question (diagnostic, clarifying, challenging)
- Respond to friction (engage, deflect, escalate)
- Specify action (who, what, when)
- Deliver feedback (SBI-RC framework)
- Communicate clearly (structure, conciseness, BLUF)

**Option B: Meeting lifecycle phases** -- When in the meeting flow?
- Opening/framing
- Discussion management (floor, questions, friction)
- Decision closure
- Action specification
- Feedback delivery (when applicable)

**Option C: Hybrid** -- Clean behavioral mechanics for communication patterns, lifecycle-based for meeting management.

The key test for any new taxonomy: can you take a single transcript moment and assign it to exactly one pattern without knowing what other moments exist? If yes, the taxonomy is MECE at the behavioral level.

## Files that need updating for a taxonomy change

| File | What changes |
|------|-------------|
| `clearvoice_pattern_taxonomy_v3.0.txt` | Complete rewrite |
| `system_prompt_v0_4_0.txt` | Pattern references in system prompt |
| `editor_pattern_definitions_v1.0.txt` | Pattern definitions for editor |
| `system_prompt_editor_v1.0.txt` | May need pattern reference updates |
| `backend/core/config.py` | `PATTERN_ORDER` list |
| `backend/core/gate1_validator.py` | Pattern validation |
| `backend/schemas/mvp_v0_4_0.json` | JSON schema for output |
| `backend/evals/judge_eval.py` | Judge prompt may need updating |
| Frontend components | Pattern display, colors, labels |

## Execution sequence

1. Design the new taxonomy (pattern definitions, scoring rubrics, detection rules)
2. Update the taxonomy file and system prompt
3. Run replay_eval in repeat mode on all 7 transcripts (5 runs each)
4. Run judge on all outputs
5. Compare against Phase I2 baseline: insightful%, pedantic%, wrong%, SNR per pattern
6. Iterate based on results
