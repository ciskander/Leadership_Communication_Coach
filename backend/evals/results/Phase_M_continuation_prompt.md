# Phase N: Stage 1/Stage 2 Architecture — Continuation Prompt

## How to use this document

Read this document and `Phase_L_continuation_prompt.md` (same parent directory) for full historical context. This document covers what Phase M accomplished and the architectural direction for Phase N.

---

## What Phase M accomplished

### PM removal (committed to main)

Removed participation_management (pattern 3) from the entire codebase:
- Taxonomy v3.0 → v3.1: deleted PM pattern block, renamed Cluster B to "Conflict & Trust" (DN + TC only), renumbered patterns 3-9
- Schema mvp.v0.4.0 → v0.5.0: removed PM from enum, removed balance_assessment field
- All prompts: system_prompt, baseline_pack, editor, editor_pattern_definitions — PM references removed
- Backend: config.py PATTERN_ORDER, gate1_validator, prompt_builder, workers, dto, quote_helpers, routes_coachee
- Frontend: types.ts, strings.ts, PatternSnapshot.tsx (removed BalanceBadge component)
- Tests: conftest.py, test_gate1_validator.py, test_prompt_builder.py
- Deleted superseded scripts: scripts/view_analysis.py, scripts/pattern_scoring_diagnostics.py
- Fixed Dockerfile.backend to reference v3.1 taxonomy filename

### Editor improvements (committed to main)

- Added Step 1.5 "Coaching Value Check" to the editor prompt: asks whether each pattern's coaching would be independently raised by an experienced coach, or exists because the taxonomy demanded it
- Expanded the stretching-to-fill suppression criterion with 4 specific indicators
- Removed PM from editor failure modes list

### RA tightening (committed to main)

- Added coaching materiality gate to RA detection notes in taxonomy: score alignment based on whether shared understanding was ACHIEVED, not whether a specific verbal ritual was performed
- Added RA-specific overcounting guard in system prompt

### Eval results (Phase M, 5 meetings x 5 runs = 25 runs)

**Pre-editor aggregate:**

| Metric | Phase L (N=800) | Phase M (N=175) | Delta |
|--------|:-:|:-:|:-:|
| Insightful | 44.9% | 44.6% | -0.3pp |
| Pedantic | 8.5% | 6.3% | **-2.2pp** |
| Wrong | 0.0% | 0.0% | — |

**Post-editor aggregate:**

| Metric | Phase L (N=698) | Phase M (N=160) |
|--------|:-:|:-:|
| Insightful | 47.0% | 47.5% |
| Pedantic | 7.6% | 8.1% |
| Wrong | 0.0% | 0.0% |

Post-editor pedantic is HIGHER than pre-editor (8.1% vs 6.3%) — this is analyzed in detail below.

**Per-pattern health (pre-editor):**

| Tier | Pattern | Ins% | Ped% | SNR | Status |
|------|---------|:----:|:----:|:---:|--------|
| 1 | feedback_quality | 100% | 0% | 8.05 | Excellent |
| 1 | focus_management | 100% | 0% | — | Excellent (small N) |
| 1 | disagreement_navigation | 85.7% | 0% | 3.16 | Excellent |
| 2 | trust_and_credibility | 63.2% | 0% | 3.75 | Strong |
| 2 | resolution_and_alignment | 48.0% | 0% | 5.61 | Major improvement (was 10.1% ped) |
| 3 | question_quality | 43.5% | 4.3% | 1.48 | Solid coaching, weak tracking |
| 3 | assignment_clarity | 24.0% | 0% | 2.04 | Boring but harmless |
| 4 | communication_clarity | 24.0% | 24.0% | 8.13 | Great tracker, bad coach |
| 4 | purposeful_framing | 4.0% | 16.0% | 0.40 | Weak on both axes |

**Meetings tested:** M-000003 (contentious), M-000004 (avoider), M-000005 (weak feedback), M-000006 (stress test), M-000009 (team retro)

**Results kept in:** `backend/evals/results/Phase_M/`

---

## Key findings from Phase M analysis

### 1. Editor regression: a structural problem, not a prompt problem

Post-editor pedantic went UP (6.3% → 8.1%). Root cause analysis on individual judge files revealed:

**The incoherent state:** In M-000005, AC scored 0.5 (weak — half opportunities missed). The pre-editor had a coaching_note explaining what to improve. The editor correctly identified the coaching_note as misaligned ("this is really feedback_quality, not AC") and suppressed it. But the editor left the score at 0.5 and the positive `notes` field intact. Result: user would see "you did well at this" (notes) with a weak score (0.5) and no explanation of what went wrong. The post-editor judge correctly called this pedantic.

**The principle this reveals:** When the editor suppresses a coaching_note, the resulting state must be coherent:
- Score ≥ 0.70 + notes only → coherent (genuine strength, no developmental edge)
- Score < 0.70 + notes only → **incoherent** (weak score with only praise and no guidance)
- Focus pattern or active experiment → coaching_note should be rewritten, not suppressed

**But the deeper issue:** The editor is fundamentally limited to suppression. Phase K showed it can't reliably generate better coaching through rewriting. This means it can remove bad coaching but can't replace it with good coaching — it can only create hollowed-out states. The fused architecture (detection + scoring + coaching in one pass) is the root cause.

### 2. "decision_quality" is a real gap in the taxonomy

Surveyed all pattern alignment misfits across Phase L (800 judge ratings) and Phase M (175 ratings):

| Suggested construct | Occurrences | Where |
|---|:-:|:-:|
| decision_quality / decision_quality_under_pressure | 29 | M-000004, M-000006, M-000002, M-000009 |
| stakeholder orchestration/alignment | 60 | Heavily from now-removed PM; will drop |
| executive_presence / structured_summarization | 8 | M-000003, M-000001, M-000006 |

The judges consistently describe a gap: **no pattern captures whether a leader synthesized diverse inputs into a defensible decision, held tension long enough to surface real risks, or optimized for pace over judgment.** Existing patterns cover closure mechanics (RA), assignment mechanics (AC), and communication quality (CC/QQ) — but not decision robustness.

Specific judge quotes:
- M-000004 (avoider): "He converted substantive dissent into an obstacle to pace rather than an input to decision quality"
- M-000006 (stress test): "Clear assignments are less impressive when the underlying decision quality is shaky"
- M-000002 (weak facilitator): "The core failure is one integrated leadership problem: Jordan did not run a decision meeting"

### 3. PF and CC have structural limitations

**PF (purposeful_framing):** SNR 0.40, 4% insightful, 16% pedantic. Four of five meetings cluster at scores 0.75-0.89 (cross-IQR = 0.04). It measures a hygiene skill most leaders clear. Coaching is "you could have stated the outcome more explicitly" — generic and not insightful.

**CC (communication_clarity):** SNR 8.13 (excellent tracking), 24% insightful, 24% pedantic. Pedantic is concentrated in M-000006 (4/5) where judges say CC coaching is "redundant with purposeful_framing and resolution_and_alignment." Great metric, boring/misaligned coach.

Both patterns work well for scoring/tracking but fail at generating valuable coaching. This is symptomatic of the fused architecture — the system must generate coaching for every evaluable pattern, even when the coaching isn't worth delivering.

---

## Architectural direction: Stage 1 / Stage 2 separation

### The problem

The current architecture fuses detection, scoring, and coaching into one LLM pass, then applies an editor as quality filter. This creates fundamental tensions:
1. Every evaluable pattern must generate coaching text, even when the coaching isn't valuable
2. The editor can remove bad coaching but can't replace it with good coaching
3. Suppressing coaching_note for low-scoring patterns creates incoherent states
4. The editor's only reliable function is pattern suppression — text rewrites don't improve judge ratings

### The proposed solution

**Stage 1: Detection + Scoring (replaces current 1st pass)**
- Input: transcript + taxonomy + memory/experiment context
- Output: opportunity events, evidence spans, pattern scores, evaluable status
- NO coaching text, NO executive summary, NO coaching themes
- Strict per-pattern tunnel vision — apply rubrics rigorously
- This is what the current system already does well

**Stage 2: Coaching Synthesis (replaces current editor)**
- Input: transcript + Stage 1 output (scores, evidence, OEs) + memory/experiment context
- Output: executive summary, coaching themes, strengths, focus area, per-pattern coaching, micro-experiment
- Holistic judgment — synthesize what matters for THIS leader in THIS meeting
- Free to skip patterns that don't add coaching value (CC scores in sparkline, no coaching card)
- Can generate coaching that crosses pattern boundaries ("your clarity is a strength, but in this meeting it was used to shut down valid input")
- Addresses the "coach the person, not the rubric" principle directly

### Why this is cost-neutral

The current system already makes 2 transcript-aware LLM calls:
- 1st pass: ~48K tokens (detection + scoring + coaching)
- Editor: ~18K tokens (transcript + 1st pass output + editorial judgment)
- Total: ~66K tokens

Proposed:
- Stage 1: ~35-40K tokens (detection + scoring only — less output to generate)
- Stage 2: ~25-30K tokens (transcript + Stage 1 output + coaching synthesis)
- Total: ~60-70K tokens

The editor is eliminated — Stage 2 IS the editorial judgment layer, but it generates coaching from scratch rather than editing existing text.

### What this solves

1. **Incoherent states** — Stage 2 only generates coaching for patterns it decides are worth coaching. No hollow shells.
2. **Coach the person** — Stage 2 can synthesize across patterns, identify the real leadership issue, and generate coaching that addresses it holistically.
3. **decision_quality gap** — Can be added as a Stage 1 pattern (detection + scoring) without worrying about whether the coaching is valuable — Stage 2 makes that call.
4. **PF/CC limitations** — Stage 1 scores them (good for tracking). Stage 2 decides whether to generate coaching (often won't for PF; might for CC in specific meetings).
5. **Editor obsolescence** — The fundamental limitation of the editor (can suppress but can't create) is resolved by having Stage 2 generate coaching from scratch.

### Open design questions

1. **Stage 1 output schema:** How much of the current output structure stays in Stage 1? Opportunity events, evidence spans, scores — yes. But what about `coaching.focus`, `coaching.strengths`, `coaching.micro_experiment`? Those are coaching decisions that should move to Stage 2.

2. **Stage 2 transcript access:** Stage 2 needs the transcript to ground coaching in specific moments. This doubles input tokens across the two stages. The cost analysis above accounts for this, but it means Stage 2 prompts need to be efficient about what they ask for.

3. **Experiment continuity:** The current system tracks active experiments and maintains continuity. Stage 2 needs the same experiment context. The memory/experiment payload that currently goes to the 1st pass should also go to Stage 2.

4. **decision_quality pattern design:** What's the denominator? What's the rubric? How does it avoid overlapping with RA (closure mechanics) and DN (conflict handling)? The judges suggest it's about "synthesizing inputs into defensible decisions under uncertainty/pressure" — but that needs to be operationalized into a scoreable rubric.

5. **Eval strategy:** Can we test Stage 2 on existing Stage 1 outputs? The current run_*.json files contain all the scoring data Stage 2 would need. We could prototype Stage 2 by feeding it existing Phase M outputs and comparing the coaching quality.

6. **Migration path:** Can Stage 1 and Stage 2 be deployed incrementally? Stage 1 could be the current 1st pass with coaching fields stripped. Stage 2 could be prototyped on a few meetings before replacing the editor in the pipeline.

---

## Key codebase references

- **Taxonomy**: `clearvoice_pattern_taxonomy_v3.1.txt` (project root) — 9 patterns, PM removed
- **System prompt**: `system_prompt_v0_4_0.txt` — current with PM removed, RA guard added
- **Editor prompt**: `system_prompt_editor_v1.0.txt` — current with Step 1.5 coaching value check
- **Pipeline orchestrator**: `backend/evals/run_pipeline.py` — verified working
- **Editor merge logic**: `backend/core/editor.py` — has `_cleanup_fully_suppressed` step
- **Config**: `backend/core/config.py` — PATTERN_ORDER (9 patterns), SCHEMA_VERSION mvp.v0.5.0, TAXONOMY_VERSION v3.1
- **Schema**: `backend/schemas/mvp_v0_5_0.json`
- **Phase M results**: `backend/evals/results/Phase_M/` (5 meetings x 5 runs, kept as baseline)
- **Phase L results**: `backend/evals/results/Phase_L/` (10 meetings, N=5 on originals + N=5 on feedback meetings)
- **Baselines**: `backend/evals/results/Phase_I2/` (pre-editor), `Phase_J2/` (post-editor)

### 10 test transcripts (unchanged)

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

---

## Recommended next steps (Phase N)

### 1. Design and prototype Stage 2 coaching synthesis

Start by writing the Stage 2 prompt — it takes Stage 1 output + transcript and generates coaching. Test it on existing Phase M run_*.json files (which already contain the scoring data Stage 2 needs). Compare the coaching quality against the current system's coaching + editor.

### 2. Design decision_quality pattern for Stage 1

Draft the pattern definition: denominator, rubric, detection notes, experiment guidance. Test on M-000004 (avoider), M-000006 (stress test), M-000002 (weak facilitator) — the meetings where judges most strongly flagged the gap.

### 3. Strip Stage 1 of coaching fields

Once Stage 2 is prototyped, modify the 1st pass to produce scoring-only output. This simplifies the Stage 1 prompt, reduces output tokens, and may improve scoring consistency (the LLM isn't distracted by coaching generation).

### 4. Run a comparative eval

Stage 1 + Stage 2 vs current system (1st pass + editor). Compare:
- Insightful/pedantic/wrong rates
- Coaching coherence (no more incoherent states?)
- Decision_quality coaching value
- Whether PF/CC coaching improves or is appropriately suppressed
