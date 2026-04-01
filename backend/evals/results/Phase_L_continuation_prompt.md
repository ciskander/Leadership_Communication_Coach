# Phase L2: Big Eval + Next Steps — Continuation Prompt

## How to use this document

Read this document and `Phase_K/Phase_K_synthesis.md` (same parent directory) for historical context. This document covers what Phase L accomplished and what needs to happen next. The Phase K synthesis has the empirical findings that motivated Phase L.

---

## What Phase L accomplished

### Taxonomy changes (all committed to main)

Three targeted changes to address patterns with measurable detection and scoring problems:

1. **CC (communication_clarity) — Mechanical denominator.** Replaced elastic "3+ sentence" threshold with "40+ words of target speaker's speech, cap of 8 turns per meeting." Detection CV dropped from ~32% to ~16%. SNR dropped from 19.8 to 7.78 (trade-off: cap makes each OE weigh more).

2. **FM (focus_management) — Raised minimum threshold from 1 to 2.** Single-event FM scores swung 33-100% on a 3-level rubric. With threshold=2, pedantic dropped from 23.1% to 9.1%. SNR improved from 3.6 to 7.0.

3. **AC (assignment_clarity) — Replaced complexity-tiered rubric with single tiered rubric.** The old rubric required two sequential judgments (classify simple/complex, then count elements) which amplified noise. New rubric: one holistic judgment per OE ("could the assignee execute without follow-up questions?") scaled proportionately to task complexity. Pre-editor pedantic dropped from 11.4% to 5.1%. SNR still worst (1.20), either because AC doesn't discriminate well across leaders (assignment clarity is a baseline professional skill, not a leadership differentiator) OR because the rubric scoring makes it hard to score lower. This could be revisited to encourage a wider scoring range in practice.

### Infrastructure built

- **`backend/evals/run_pipeline.py`** — Single-command eval pipeline orchestrator. Chains replay -> compare -> editor -> judge -> synthesis with auto-calculated concurrency, skip logic for resume, and phase-isolated output directories. See docstring for usage.
- **`backend/evals/run_editor_on_outputs.py`** — Standalone editor runner with auto-discovery of meetings from directory.
- **Fixed `replay_eval.py`** — Offline compare now filters to `run_*.json` only (was picking up editor/judge/post_editor files and contaminating stats).

### Eval results (Phase L, N=5 on 7 original meetings + N=5 on 3 new feedback meetings)

**Pre-editor (vs I2 baseline):** Insightful 44.9% (+4.7pp), Pedantic 8.5% (-2.0pp), Wrong 0.0%
**Post-editor (vs J2 baseline):** Insightful 47.0% (+4.3pp), Pedantic 7.6% (-1.1pp), Wrong 0.0%

### Big eval (Phase L2, N=10 on all 10 meetings) — partially complete

100 replay runs + 100 editor runs + 200 judge runs completed successfully. Results are in `backend/evals/results/Phase_L` and `backend/evals/results/Phase_L/Phase_L_post_editor` (the per-meeting M-* directories). The compare reports and judge synthesis reports were generated. 

**Phase L2 aggregate (N=10, 10 meetings):**

| Config | Ins% | Ped% | Wrong% | N |
|--------|:----:|:----:|:------:|:-:|
| L2 pre-editor | 44.9% | 8.5% | 0.0% | 800 |
| L2 post-editor | 47.0% | 7.6% | 0.0% | 698 |

---

## What needs to happen next

### Immediate: Move Phase L2 results and retest pipeline

**Test the pipeline end-to-end** with a small run (2 meetings x 2 runs). The pipeline (`run_pipeline.py`) was built but hit API quota before it could be tested. Run:
   ```
   python -m backend.evals.run_pipeline \
     --phase Phase_test \
     --transcripts-dir backend/evals/transcripts \
     --runs 2 --editor --judge \
     --baseline-dir backend/evals/results/Phase_I2 \
     --post-editor-baseline-dir backend/evals/results/Phase_J2
   ```
   Then delete `Phase_test/` after verifying it worked.

### Key findings to carry forward

#### Pattern health assessment (two lenses: coaching quality + progress tracking)

| Pattern | Coaching | Tracking | Status |
|---------|:-------:|:-------:|:-------|
| FQ | Excellent (84% ins, 0% ped) | Weak SNR (2.87) | Keep — high coaching value |
| DN | Strong (79.5% ins, 1.3% ped) | Good SNR (6.23) | Keep as-is |
| TC | Strong w/ editor (82% ins, 1.5% ped) | Moderate SNR (4.11) | Keep — editor-dependent |
| FM | Good (70.5% ins, 9.1% ped) | Moderate SNR (7.0) | Keep — threshold change helped |
| CC | Weak coaching (23% ins, 13% ped) | Best SNR (7.78) | Better as metric than coaching topic |
| PF | Reliable/boring (17% ins, 5% ped) | Moderate SNR (3.03) | Keep — rarely wrong, rarely insightful |
| QQ | Moderate (39.7% ins, 6.4% ped) | Poor SNR (2.04) | Needs work — M-000004 avoider problem |
| AC | Improved (41.4% ins, 5.1% ped) | Worst SNR (1.20) | Keep for coaching, try to improve tracking |
| RA | Weak (39.4% ins, 10.1% ped) | Poor SNR (1.87) | Candidate for redesign |
| PM | Worst (19.3% ins, 33.3% ped) | Poor SNR (2.68) | **Candidate for removal** |

#### Score compression analysis

Low SNR in some patterns (AC, PF, FQ) is partly because the bottom tiers (0.0, 0.25) are rarely used. Competent professionals rarely fail completely on these dimensions and/or scoring rubric requires extreme incompetence to score low:
- AC: nobody makes assignments with zero specification
- PF: nobody starts a topic without any framing at all
- CC: nobody talks at length with no discernible point

This may be the transcripts reflecting reality, or a rubric problem. These patterns have structural floor effects that limit their discrimination. Patterns like DN, TC, FM discriminate better because total failure IS common (avoiding disagreement, eroding trust, ignoring drift).

**Implication:** Some patterns are better for coaching (the insights are valuable even if scores don't vary much), others are better for progress tracking (scores differentiate leaders meaningfully). Perhaps the product should present these differently.

#### Remaining problem spots

1. **PM is the weakest pattern** — 33% pedantic, highest intra IQR (0.202), 18 misfits. The judge consistently says PM coaching is taxonomy-filling. Candidate for removal.

2. **Editor blind spot** — The editor catches misalignment (wrong pattern for behavior) but not stretching-to-fill (technically correct but low coaching value). Demonstrated in M-000009 where it suppressed clean patterns (TC, CC) but left PF (80% pedantic) untouched. Review editor prompt to see if this can be improved.

3. **QQ in M-000004 (avoider)** — Persistently pedantic because questions in certain contexts get misclassified as "question quality" when they're really being used as a tool for some other purpose in context (e.g. decision-forcing, disagreement surfacing, or avoidance of tough conversations).

4. **Missing constructs** — The judge keeps suggesting categories that don't exist in the taxonomy: "decision_quality," "stakeholder_sequencing," "executive_presence," "commitment_checking." This may indicate real gaps. Could survey judge_eval reports to look for recurring themes. However: be conservative about introducing new patterns.

### Potential next interventions (not yet started)

1. **Remove or redesign PM** — Highest priority. 33% pedantic is not acceptable.
2. **Editor prompt for stretching-to-fill** — Teach the editor to detect low-value coaching, not just misaligned patterns.
3. **RA redesign** — Weak on both coaching and tracking dimensions.
4. **Stage 2 coaching synthesis** — The original Phase K proposal for separating detection from coaching. Still potentially valuable but the bottom-up pattern fixes should come first.

---

## Key codebase references

- **Taxonomy**: `clearvoice_pattern_taxonomy_v3.0.txt` (project root) — current version with CC/FM/AC changes
- **System prompt**: `system_prompt_v0_4_0.txt` (project root) — updated to remove complexity_tiered references
- **Pipeline orchestrator**: `backend/evals/run_pipeline.py` — single-command eval pipeline
- **Editor standalone**: `backend/evals/run_editor_on_outputs.py` — run editor on existing outputs
- **Eval results**: `backend/evals/results/Phase_I2/` (pre-editor baseline), `Phase_J2/` (post-editor baseline), `Phase_L/` (N=5 initial results), Phase_L2 results in `M-*` dirs (need to be moved)
- **Test transcripts**: `backend/evals/transcripts/` (10 transcripts: 7 original + 3 new feedback meetings M-000007/8/9)
- **Config**: `backend/core/config.py` (`PATTERN_ORDER` at line 63)

### 10 test transcripts

| ID | Type | Target | Role | Key characteristic |
|----|------|--------|------|-------------------|
| M-000001 | project_review | Jordan | Chair | Strong facilitator |
| M-000002 | project_review | Jordan | Chair | Weak facilitator |
| M-000003 | project_review | Alex | Chair | Contentious meeting |
| M-000004 | project_review | Alex | Chair | Conflict avoider |
| M-000005 | project_review | Jordan | 1:1 Manager | Weak feedback |
| M-000006 | cross_functional | Robin | Chair | Stress test |
| M-000007 | one_on_one | Morgan | 1:1 Manager | Mixed feedback quality |
| M-000008 | one_on_one | Taylor | 1:1 Manager | Mostly poor feedback |
| M-000009 | team_meeting | Sasha | Chair | Team retro with feedback |
| M-000055 | project_review | Jordan | 1:1 Manager | Feedback-focused |

### Code references for backward compatibility

The gate1 validator (`backend/core/gate1_validator.py`) and workers (`backend/core/workers.py`) still contain references to `complexity_tiered`, `simple_count`, and `complex_count`. These are harmless — they handle optional fields that the LLM will no longer output. Clean up when convenient but not blocking.
