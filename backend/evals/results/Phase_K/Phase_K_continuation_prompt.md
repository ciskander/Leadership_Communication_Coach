# Phase L: Architecture Redesign — Continuation Prompt

## How to use this document

Read this document and `Phase_K_synthesis.md` (same directory) before doing anything. The synthesis contains the empirical findings. This document contains the strategic reasoning and architectural direction that emerged from analyzing those findings. Together they represent approximately 180 LLM evaluation calls and several hours of collaborative analysis.

---

## The journey that brought us here

### Pre-editor era (Phases A through I2)

The project started with a 10-pattern taxonomy for analyzing leadership communication in meeting transcripts. Each pattern (focus_management, trust_and_credibility, etc.) was designed to be MECE (mutually exclusive, collectively exhaustive). A single LLM pass analyzed a transcript against all 10 patterns simultaneously, producing scored observations and coaching text.

Over Phases G through I2, we discovered that certain patterns persistently overlap — the same behavioral moment in a transcript would get claimed by multiple patterns (e.g., a leader deferring a concern gets labeled as FM "redirect," DN "engagement failure," and TC "trust erosion"). We attempted to fix this through increasingly sophisticated disambiguation rules in the taxonomy:

- Cross-pattern reclassification rules ("if this moment is really about FM, exclude from TC")
- Coaching-note distinctiveness tests ("TC coaching must name a trust-specific dynamic not already covered by FM")
- Detection notes for overlapping scenarios

**Result: minimal impact.** The LLM reliably follows rubric-level scoring and materiality tests but consistently ignores cross-pattern reasoning, reclassification rules, and coaching-note distinctiveness constraints. This was measured across multiple taxonomy versions and prompt iterations. The owner spent several rounds of taxonomy tweaking with little to show for it — which is what motivated the pivot to the editor approach.

### The editor era (Phases J through J2)

Recognizing that the 1st pass couldn't self-correct its overlap problems, we added a 2nd LLM pass ("the editor") as a quality gate. The editor receives the 1st-pass output and transcript, then produces a delta (changes to apply). The delta gets merged back into the 1st-pass output.

The editor was designed with capabilities to: suppress misaligned patterns, improve evidence span selections, rewrite coaching text, and remove weak observations. The code infrastructure (`backend/core/editor.py`) fully supports all of these operations.

**Result: the editor became a suppression-only gate.** Across 6 meetings and 30+ editor runs in Phase K testing, the editor made zero evidence span improvements, zero rewrite improvements, and only 2 span changes (both in M-000002, both degrading quality). Its only measurable positive impact was suppressing misaligned patterns — real value, but narrow and inconsistent on borderline cases. The editor prompt foregrounds suppression and the LLM gravitates toward it, ignoring its other capabilities even when meetings have weak evidence and generic rewrites that could clearly benefit from improvement.

### Phase K: Variance decomposition

Phase K isolated variance per pipeline layer using `variance_eval.py`:

**Editor consistency:** Highly consistent on clear-cut decisions (100% for M-000001), but noisy on borderline patterns (only 61% unanimous for M-000002, with 7 flip decisions on PF, PM, RA, AC, CC).

**Judge consistency:** The dominant noise source. On M-000001, pedantic ratings range from ~10% to ~27% across runs of the SAME input (stdev ~6-9%). Pattern alignment (`fits_pattern`) is noise-free — the judge agrees on what belongs, just not on quality tier for borderline cases. On M-000002 (strong facilitator), the judge is 100% unanimous — clear quality is clear.

**Propagation test:** Editor variance does NOT propagate to the judge. Text rewrites are invisible to the judge. The only propagation is when the editor fully suppresses a pattern (removing it from evaluation).

**Pre-editor vs post-editor (apples-to-apples):** Using the same 1st-pass input with 10 judge runs each:
- M-000001: Editor suppressed TC, reducing pedantic from ~15.6% to ~10-12.5%. But insightful also dropped.
- M-000002: 0% pedantic before and after. Editor was pure overhead.
- M-000004: Outcome depends entirely on whether editor suppresses CC (variable across runs).

**Pedantic root cause:** 94% of pedantic ratings come from misalignment (55% — wrong pattern for the behavior) and stretching-to-fill (39% — thin evidence forced into a pattern). Coaching text quality is a negligible source (3%).

### The architectural pivot (this conversation)

The findings above led to a series of questions that reframed the entire problem:

**Q: Is the problem that pattern boundaries are fuzzy, or are certain patterns fundamentally flawed?**

Analysis revealed three overlap clusters:
- **Conflict/Challenge cluster** (FM, DN, TC): Same behavioral moment, three interpretive lenses
- **Conversational Control cluster** (QQ, FM, PM): Questions classified differently based on inferred purpose
- **Decision/Action cluster** (PF, RA, AC): Mostly clean but AC/RA blur on combined decision-assignments

The problem isn't fuzzy boundaries — it's that the taxonomy organizes patterns around *interpretive lenses* (trust, focus, disagreement) rather than *observable behaviors* (redirect, question, action item). The same behavior genuinely IS relevant to multiple lenses, so no amount of boundary-tightening can make them MECE.

**Q: Is it even possible to separate leadership coaching into MECE categories based on observable behaviors?**

Yes and no. Observable behaviors (redirects, questions, assignments) are cleanly separable and MECE-able. But coaching VALUE comes from interpreting those behaviors through lenses (trust, focus, engagement) — and the same behavior carries different significance through different lenses. A taxonomy that only sees "leader redirected a topic" loses the coaching nuance. A taxonomy that tries to incorporate the coaching lens into detection (the current approach) breaks MECE.

**Q: Then why define patterns at all?**

This was the pivotal question. Two reasons:

1. **Progress tracking requires structure.** "You specified deadlines on 7/10 action items this meeting, up from 4/10 last month" is real, trackable progress. "Your trust score went from 0.6 to 0.8" is not meaningful because "trust" isn't one observable thing.

2. **Without structure, you're building an LLM wrapper.** Passing a transcript to an LLM with "be an executive coach" produces decent one-off coaching but no tracking, no consistency, no measurable improvement over time. The product value is in the system that measures, tracks, and develops leadership communication — not in the one-off coaching.

**Resolution: Separate detection from coaching.**

These are two fundamentally different cognitive tasks with different requirements. The current architecture fuses them (each pattern simultaneously defines what to detect AND how to coach), which is the root cause of most problems. Separating them resolves the MECE tension:

- **Stage 1 (Detection + Scoring):** Identifies observable behavioral moments, scores them against mechanical rubrics. MECE works here because we're categorizing behaviors, not interpretations. Expected to have "tunnel vision" — each pattern operates independently, and overlap is fine (the same moment can be detected by multiple patterns).

- **Stage 2 (Coaching Synthesis):** Receives all Stage 1 detections + transcript. Applies executive coaching judgment holistically. Decides what's really going on: "your handling of Quinn's concerns across multiple moments suggests a pattern of defensive focus management that's eroding trust." Suppresses patterns that don't add value, elevates the ones that matter, synthesizes across patterns. This is where the LLM's coaching judgment adds genuine value that can't be achieved mechanically.

**The key realization:** Scores track behavioral mechanics (Stage 1). Coaching addresses holistic themes (Stage 2). They don't need to use the same categories. A coachee's score improvements in Stage 1 dimensions (redirect quality, action item completeness) represent real behavioral progress. The coaching in Stage 2 explains WHY those behaviors matter and provides the motivation/insight to improve — but it organizes its insights by coaching theme, not by detection category.

---

## Proposed two-stage architecture (detailed)

### Stage 1: Detect + Score (tunnel vision, per-pattern)

**What it does:**
- Identifies behavioral moments (opportunity events) per pattern
- Scores each moment against that pattern's mechanical rubric (the 0.0-1.0 tier definitions)
- Selects evidence spans from the transcript
- Overlap is ALLOWED — the same transcript moment can appear under multiple patterns
- Does NOT attempt cross-pattern reasoning or disambiguation

**What changes from today:**
- Remove cross-pattern reclassification rules from the taxonomy
- Remove coaching-note distinctiveness tests (TC must name a trust-specific dynamic not already covered by FM...)
- Remove detection notes that attempt to disambiguate overlapping patterns
- Keep: behavioral definitions, mechanical scoring rubrics, element-counting approaches (AC's who/what/when, PF's topic+outcome), evidence span selection, the 0.0-1.0 tier system

**What stays the same:**
- The 10 pattern definitions (behavioral descriptions and rubrics) are largely preserved
- The scoring rubrics are well-designed — e.g., FM's distinction between 1.0 (genuine tangent redirect) and 0.0 (suppressing a risk signal) is a meaningful quality dimension
- The output format (JSON with scored patterns, OEs, evidence spans) stays compatible

### Stage 2: Coaching Synthesis (holistic, cross-pattern)

**What it does:**
- Receives the full Stage 1 output + the transcript
- Acts as an executive coach reviewing a behavioral analysis
- Determines what's actually going on with this leader's communication
- Suppresses patterns that don't add meaningful coaching value
- Elevates the most important patterns/moments
- Synthesizes across patterns when the same behavior has implications across multiple dimensions
- Generates the coaching output (executive summary, strengths, focus area, micro-experiment)

**What changes from today:**
- The current editor (`editor.py`) is a copy-editor that produces deltas (suppress, rewrite). It would be transformed into a coaching synthesizer that produces the primary coaching output.
- The delta format may need to be richer, or the output format may change entirely depending on Q1 below.

**What stays the same:**
- The pipeline architecture (1st pass -> 2nd pass -> merged output) is preserved
- `editor.py` infrastructure (`run_editor()`, `merge_editor_output()`, pipeline integration in `workers.py`) can be reused/extended

---

## Open architectural questions (to decide before implementing)

### Q1: Does Stage 1 generate coaching text at all?

This is the most consequential design decision. It was deliberately left open for offline consideration.

**Option A — Stage 1 detects + scores only.** Stage 1 outputs OEs, scores, evidence spans — no coaching text (no `notes`, `coaching_note`, `suggested_rewrite`, `executive_summary`, `strengths`, `focus`, `micro_experiment`). Stage 2 generates ALL coaching text from scratch using Stage 1's data + the transcript. Cleaner separation but Stage 2 becomes the primary coaching author — a much bigger role than the current editor.

**Option B — Stage 1 generates draft coaching, Stage 2 refines.** Keeps current architecture with simplified Stage 1 taxonomy (no cross-pattern rules). Stage 2 still synthesizes, suppresses, elevates, but works from Stage 1's draft coaching text. Less disruptive but preserves the pattern that the 1st pass generates coaching through per-pattern tunnel vision and the 2nd pass tries to fix it.

**Trade-offs to consider:**
- Option A is architecturally cleaner but a bigger change. The current editor is a lightweight delta-based editor; Option A makes Stage 2 the main coaching engine.
- Option B is incremental but may not fully resolve the pedantic problem because Stage 1 still generates coaching through per-pattern tunnel vision, which is what produces the misaligned and stretched-to-fill coaching that becomes pedantic.
- Key question: does Stage 1's draft coaching text help or constrain Stage 2? If the draft coaching anchors Stage 2 toward per-pattern framing, it undermines the cross-pattern synthesis we want. If Stage 2 can freely ignore/reframe it, the draft was wasted compute.
- The current editor already demonstrated this tension: given the capability to improve coaching text, it gravitated toward suppression instead, suggesting that editing per-pattern coaching is less natural than writing holistic coaching from scratch.

### Q2: What happens to scoring and progress tracking?

The current system tracks scores per pattern. With a two-stage architecture:
- Stage 1's mechanical scores (behavioral frequencies + rubric quality) ARE the progress metrics
- Stage 2's coaching doesn't need to map 1:1 to Stage 1's patterns
- Scores track behavioral mechanics ("redirect quality went from 0.5 to 0.8")
- Coaching addresses holistic themes ("your defensive use of redirects is eroding trust")

Acting on the coaching should improve the behavioral scores because the coaching is grounded in the same rubric dimensions. Key validation question: if a coachee improves their scores, does that actually represent better leadership? If the rubrics measure the right quality dimensions (not just frequency), then yes. The current rubrics already do this well — e.g., FM's distinction between 1.0 (genuine tangent redirect) and 0.0 (suppressing a risk signal) is a meaningful quality dimension.

**Implication for the frontend:** The progress page currently shows per-pattern scores over time. That can stay. But the coaching insights page would show synthesized themes rather than pattern-by-pattern feedback. This is actually a better user experience — leaders don't think in "focus management" and "trust and credibility" categories; they think "how do I handle pushback in meetings?"

### Q3: How does the judge eval need to change?

The current judge evaluates per-pattern coaching quality (insightful/adequate/pedantic/wrong). With Stage 2 producing synthesized cross-pattern coaching:

**Keep:**
- `coaching_insight_quality` (insightful/adequate/pedantic) — still relevant
- `scoring_arithmetic` — Stage 1 scores still need validation
- `evidence_quality` — Stage 1 evidence spans still need validation

**Add:**
- Does the coaching address the most important leadership moments in this meeting?
- Is the cross-pattern synthesis accurate — does the interpretation hold up against the transcript?
- Did Stage 2 appropriately suppress/elevate patterns?

**Potentially remove:**
- Per-pattern `coaching_pattern_alignment` (fits_pattern, stretching_to_fill) may become less relevant if coaching themes no longer map 1:1 to patterns

---

## Current state of the codebase

### What exists and can be reused
- **Stage 1 foundation**: `system_prompt_v0_4_0.txt` + `clearvoice_pattern_taxonomy_v3.0.txt` (needs simplification, not replacement)
- **Stage 2 foundation**: `backend/core/editor.py` — `run_editor()`, `merge_editor_output()`, delta format, pipeline integration in `backend/core/workers.py` (~line 622)
- **Eval infrastructure**: `backend/evals/replay_eval.py`, `backend/evals/judge_eval.py`, `backend/evals/variance_eval.py` — all well-tested and functional
- **Scoring rubrics**: The 0.0-1.0 tier definitions in the taxonomy are well-designed and should be preserved
- **7 test transcripts** with extensive baseline data across Phases A-K

### Key codebase references
- **Branch**: `main` (all Phase K work is committed here)
- **Taxonomy**: `clearvoice_pattern_taxonomy_v3.0.txt` (project root) — ~25K tokens
- **System prompt**: `system_prompt_v0_4_0.txt` (project root)
- **Editor code**: `backend/core/editor.py`
- **Editor prompts**: `system_prompt_editor_v1.0.txt`, `editor_pattern_definitions_v1.0.txt` (project root)
- **Pipeline**: `backend/core/workers.py` (editor integration at ~line 622)
- **Config**: `backend/core/config.py` (`PATTERN_ORDER` at line 63, model defaults)
- **Eval results**: `backend/evals/results/Phase_I2/` (pre-editor baseline), `Phase_J2/` (post-editor), `Phase_K/` (variance decomposition + this document)
- **Test transcripts**: `backend/evals/transcripts/` (7 transcripts)

### Pattern stability data (SNR from Phase I2, N=5-7 runs per meeting)

| Pattern | SNR | Assessment |
|---------|-----|-----------|
| participation_management (PM) | 56.0 | Excellent — cleanest pattern (5 meetings) |
| communication_clarity (CC) | 22.4 | Good |
| trust_and_credibility (TC) | 14.0 | Good SNR but #1 misalignment source — often applied to FM/DN behaviors |
| purposeful_framing (PF) | 13.4 | Good |
| disagreement_navigation (DN) | 9.7 | Moderate — overlaps FM, TC |
| question_quality (QQ) | 8.0 | Moderate — overlaps FM, PM |
| assignment_clarity (AC) | 5.8 | Weak — overlaps RA |
| resolution_and_alignment (RA) | 5.6 | Weak — overlaps AC |
| feedback_quality (FQ) | 5.0 | Weak (only 2 meetings evaluable) |
| focus_management (FM) | 3.0 | Weakest — most overlap with DN, TC, QQ, PM |

Note: High SNR does not mean "no problems." TC has SNR 14.0 (good) but is the #1 misalignment source — it consistently detects real moments but labels them with trust framing when they're really about focus management or disagreement navigation. This is exactly the interpretive-lens problem that the two-stage architecture addresses.

### What Phases G-I2 taught about LLM capabilities

**Reliably follows:** Rubric-level scoring, materiality/distinctiveness tests, meeting-type-aware filtering, structured output formatting.

**Inconsistently follows:** Pattern suppression decisions (editor), coaching-note quality (varies by pattern clarity).

**Ignores:** Cross-pattern reclassification, coaching-note distinctiveness on overlapping patterns, cross-pattern reasoning within a single pass, system prompt suppression rules that require comparing across patterns.

This capability profile directly supports the two-stage approach: Stage 1 plays to what the LLM does well (per-pattern rubric scoring), while Stage 2 is a separate pass that can focus entirely on the holistic judgment the LLM can't do within a single per-pattern pass.

---

## Suggested execution approach

1. **Decide Q1** — Does Stage 1 generate coaching text? This shapes everything downstream.
2. **Simplify the taxonomy** for Stage 1 — Remove cross-pattern rules, keep scoring rubrics. This is a targeted edit to the existing taxonomy file, not a rewrite.
3. **Redesign the Stage 2 prompt** — Transform from delta-editor ("fix what's wrong") to coaching synthesizer ("what coaching does this leader need?"). This is the biggest creative/prompt-engineering task.
4. **Run eval** on all 7 transcripts — Compare against Phase I2 baseline for scoring stability, and against Phase J2 for coaching quality.
5. **Update the judge** if needed — The current judge may need new evaluation dimensions for synthesized coaching.
6. **Iterate** based on results.

The owner has expressed that precision and correctness matter more than speed. Take time to understand the full context before making changes. When in doubt, ask questions rather than guessing.
