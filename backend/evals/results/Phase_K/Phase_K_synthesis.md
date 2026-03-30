# Phase K: Variance Decomposition — Synthesis Report

## Objective

Isolate variance contributed by each pipeline layer (1st pass, editor, judge) before investing further in taxonomy or prompt changes.

## Methodology

Created `backend/evals/variance_eval.py` with three modes:
- `--mode editor`: Run editor N times on fixed pre-editor input
- `--mode judge`: Run judge N times on fixed input
- `--mode propagation`: Merge N editor variants, judge each once

Tested on 3 meetings (M-000001 strong facilitator, M-000002 weak facilitator, M-000004 avoider) plus 3 additional meetings (M-000006, M-000055, M-000001 repeated). Model: gpt-5.4 exclusively.

Total LLM calls: ~180 (editor variance: 30, judge variance on post-editor: 30, propagation: 30, judge on pre-editor: 30, clean pre-vs-post comparison: 90).

---

## Key Findings

### 1. Editor Consistency

| Meeting | Unanimous Rate | Changes/Run |
|---------|---------------|-------------|
| M-000001 (strong) | 100% | 1-2 |
| M-000004 (avoider) | 92.9% | 2-10 |
| M-000002 (weak) | 61.1% | 3-11 |

The editor is highly consistent on clear-cut cases but shows significant variance on borderline patterns in M-000002 (7 flip decisions across PF, PM, RA, AC, CC). OE removal decisions are noisy across all meetings (0% full agreement on any OE).

### 2. Judge Consistency

| Meeting | Unanimous Rate | Dominant Noise |
|---------|---------------|---------------|
| M-000002 (post-editor) | 100% | None |
| M-000004 (post-editor) | 85.7% | RA insightful/adequate |
| M-000001 (post-editor) | 16.7% | Adjacent-tier flips on 5/6 patterns |

Judge self-variance is the dominant noise source in the measurement system. On M-000001, pedantic ranges from ~10% to ~27% across runs of the same input (stdev ~6-9%). Pattern alignment (`fits_pattern`) is essentially noise-free (100% agreement) -- the judge agrees on what belongs, just not how good borderline cases are.

### 3. Editor Variance Does NOT Propagate to the Judge

Tested across all 3 meetings with 10 editor variants each. In M-000001 and M-000004, the judge gave identical ratings regardless of editor variant. In M-000002, the only propagation was when the editor fully suppressed a pattern (removing it from evaluation). Text rewrites and minor editorial changes were invisible to the judge.

### 4. Editor's Value is Exclusively Pattern Suppression

Across 6 meetings and 30+ editor runs:
- Zero evidence span improvements attempted
- Zero rewrite improvements attempted
- 2 span changes (both M-000002) that degraded judge assessment
- Text rewrites don't move judge ratings

The editor's only measurable positive impact is suppressing misaligned patterns (e.g., TC in M-000001). This value is real but inconsistent on borderline cases.

### 5. Editor Does NOT Use Its Span/Rewrite Capabilities

The editor code supports changing `best_success_span_id`, `rewrite_for_span_id`, and `suggested_rewrite`. But the editor prompt foregrounds suppression and the LLM gravitates toward it. Even on meetings with weak evidence and generic rewrites (M-000001 AC: 2 weak, 2 generic; M-000055 FQ: 4 weak, 3 generic), the editor only suppressed.

### 6. Pre-Editor vs Post-Editor Quality (Apples-to-Apples)

Using the same 1st-pass input, 3 editor variants x 10 judge runs:

**M-000001**: Pedantic dropped from ~15.6% (pre) to ~10-12.5% (post) by suppressing TC. Insightful also dropped from ~33% to ~23%. Judge unanimity improved dramatically (11% -> 62-88%).

**M-000002**: 0% pedantic before and after. Editor was overhead on already-good output.

**M-000004**: Pedantic outcome depends entirely on whether editor suppresses CC (variable across editor runs). When it does: 0% pedantic. When it doesn't: worse than pre-editor.

---

## Pedantic Root Cause Analysis

Cross-referenced judge's alignment and evidence fields with pedantic ratings across Phase I2 (pre-editor, 35 judge runs) and Phase J2 (post-editor, 35 judge runs).

### Phase I2: 31 pedantic ratings

| Root Cause | Count | % |
|-----------|-------|---|
| Misaligned (wrong pattern for the behavior) | 17 | 55% |
| Stretching to fill (thin evidence) | 12 | 39% |
| Weak evidence | 1 | 3% |
| Quality judgment (vague coaching text) | 1 | 3% |

**94% of pedantic comes from misalignment (55%) and stretching to fill (39%).** Coaching text quality is a negligible source.

### Top Misalignment Flows

| Pattern rated pedantic | Judge says it's really... | Count |
|----------------------|--------------------------|-------|
| trust_and_credibility | focus_management | 4 |
| focus_management | disagreement_navigation / trust_and_credibility | 3 |
| question_quality | disagreement_navigation / purposeful_framing | 3 |
| participation_management | focus_management / disagreement_navigation | 3 |

### Phase J2: Editor Impact on Root Causes

The editor reduced pedantic from 31 to 22 (29% reduction). It primarily caught stretching-to-fill cases (12 -> 6) but barely touched misalignment (17 -> 16). The editor doesn't reliably detect when a pattern's coaching describes behavior belonging to a different pattern.

---

## Pattern Stability (SNR from Phase I2)

| Pattern | SNR | Assessment |
|---------|-----|-----------|
| participation_management | 56.0 | Excellent (5 meetings) |
| communication_clarity | 22.4 | Good |
| trust_and_credibility | 14.0 | Good |
| purposeful_framing | 13.4 | Good |
| disagreement_navigation | 9.7 | Moderate |
| question_quality | 8.0 | Moderate |
| assignment_clarity | 5.8 | Weak |
| resolution_and_alignment | 5.6 | Weak |
| feedback_quality | 5.0 | Weak (2 meetings) |
| focus_management | 3.0 | Weakest |

---

## Fundamental Diagnosis: Dimensional Overlap

The 10-pattern taxonomy is not sufficiently mutually exclusive. Several patterns measure the same observable behavior through different interpretive lenses:

**Conflict/Challenge Handling cluster** (FM, DN, TC): When a leader defers a concern, FM sees "redirect," DN sees "engagement failure," TC sees "trust erosion." Same moment, three labels. Context rules attempting disambiguation (Phases G-I2) had minimal impact because the LLM cannot reliably infer which lens is "primary."

**Conversational Control cluster** (QQ, FM, PM): A question can be inquiry (QQ), redirect (FM), or floor-direction (PM) depending on inferred purpose -- inherently subjective.

**Decision/Action Clarity cluster** (PF, RA, AC): Mostly clean temporal separation but AC/RA blur when decisions and assignments are woven together.

### Why Previous Taxonomy Tweaking Had Little Impact

Phases G through I2 attempted disambiguation via context rules ("if the moment is really about X, exclude from Y"). These consistently either had no effect, backfired, or were inconsistent across runs. This makes sense: you can't disambiguate patterns that are measuring the same behavior from different angles. The rules ask the LLM to decide which lens is primary for an inherently multi-dimensional moment.

### Implication

The ~10% pedantic floor is structural, not fixable by taxonomy boundary-tightening or editor improvements. A foundational redesign of the pattern taxonomy is needed, organized around observable behavioral mechanics rather than abstract leadership dimensions, to achieve genuine mutual exclusivity.

---

## Artifacts

| File | Description |
|------|-------------|
| `backend/evals/variance_eval.py` | New eval tool (editor, judge, propagation modes) |
| `Phase_K/variance_tests/M-000001_strong_facilitator/` | All M-000001 variance test outputs |
| `Phase_K/variance_tests/M-000002_weak_facilitator/` | All M-000002 variance test outputs |
| `Phase_K/variance_tests/M-000004_avoider/` | All M-000004 variance test outputs |
| `Phase_K/variance_tests/M-000006_stress_test/` | Editor delta + merged post-editor |
| `Phase_K/variance_tests/M-000055_feedback/` | Editor delta + merged post-editor |

## Next Phase

Architecture redesign (Phase L): Separate the pipeline into two stages — behavioral detection/scoring (Stage 1, per-pattern tunnel vision) and coaching synthesis (Stage 2, holistic cross-pattern judgment). This addresses the root cause: the current architecture fuses detection, scoring, and coaching into one pass, but these have fundamentally conflicting requirements. See `Phase_K_continuation_prompt.md` for the full architectural proposal and open design questions.
