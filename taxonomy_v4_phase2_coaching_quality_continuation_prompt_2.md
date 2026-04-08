# Taxonomy v4.0 — Phase 2 Coaching Quality: Continuation Prompt 2

## Context

We completed a major round of coaching quality improvements across the taxonomy, coaching prompt, baseline pack prompt, judge eval, and eval pipeline. This continuation prompt captures what was done, what worked, what didn't, and what remains.

IMPORTANT NOTE FOR THE SESSION: Never make assumptions. If anything is ambiguous, inconsistent, underspecified, or otherwise unclear, always stop and ask questions before proceeding. Precision and correctness are 10x more important than development speed.

## What Was Done (Commits 52f6d23 through 3c7324c)

### Taxonomy Changes (`clearvoice_pattern_taxonomy_v4.0.txt`)
- Added **behavioral context override** to GENERAL_DETECTION_GUIDANCE — helps Stage 1 recognize when surface-level pattern "successes" primarily served a dominant interpersonal failure (avoidance, coercion, dismissiveness)
- Added **R&A coerced alignment** detection note — procedural closure via authority override scores low on alignment confirmation
- Added **AL selective hearing** detection note — performative acknowledgment followed by ignoring substance scores 0.25 at best
- **Cleaned up 6 coaching_note instructions** that Stage 1 cannot act on (AC, QQ, CC, Recognition, BI, BI+DN) — removed coaching directives, kept detection/scoring guidance
- Note: Stage 2 does NOT see the full taxonomy — it gets a condensed extraction via `extract_stage2_pattern_definitions()` in `prompt_builder.py`. Taxonomy coaching instructions were vestigial for Stage 2.

### Coaching Prompt Changes (`system_prompt_coaching_v1.0.txt`)
Major restructuring of the reasoning sequence:

- **Merged old Steps 4+5 into Step 4 (Pattern-level coaching decisions)** — clean two-mode decision: substantive card vs status card, with value test, behavioral context test, and tiebreaker criteria
- **Rewrote old Step 6 as Step 5 (Pattern-level coaching generation)** — handles only substantive cards, with quality gates for both notes and coaching_note, theme overlap check with downgrade path
- **Renumbered all steps** — old 7/7b/8/9 became 6/6b/7/8
- **Restructured PATTERN COACHING field rules around card-mode model** — SUBSTANTIVE CARDS section with field definitions, STATUS CARDS section with no-empty-cards rule
- **No-empty-cards rule** — three problems (pedantic, empty, tone-deaf), two guiding principles (no silent cards, no forced coaching), three example options (not exhaustive)
- **Card-mode model** — substantive and status content never mixed on the same card. Substantive: one or both fields have real coaching, other can be null. Status: one field has a no-empty-cards option, other is null, all supporting fields null.
- **Tightened Step 8 self-audit** — merged overlapping checks, added incoherent status card check, removed active experiment coaching_note requirement (experiments now link to 0..N patterns)
- **Expanded `changes` field** — now logs Step 4 card-mode decisions with reasons, notes null decisions, and self-audit downgrades

### Baseline Pack Changes (`system_prompt_baseline_pack_v0_6_0.txt`)
- Replaced mechanical score-based pattern coaching (score > 0 = notes, score < 1.0 = coaching_note) with judgment-based quality guidance matching the single-meeting philosophy
- Same card-mode model, no-empty-cards rule, and behavioral context override as coaching prompt
- Updated self-checks to match card-mode model

### Judge Eval Changes (`backend/evals/judge_eval.py`, `judge_synthesis.py`)
- Added **"appropriate" rating category** for status-card-style output — cross-references, neutral status statements, brief acknowledgments
- Added **explicit definitions** for all 5 categories (insightful, adequate, appropriate, pedantic, wrong) grounded in judge's own language from prior eval data
- Updated synthesis code to count and display "appropriate" in aggregate and per-pattern tables
- **IMPORTANT FINDING:** The new judge definitions shifted calibration significantly. See "Judge Calibration" section below.

### Eval Pipeline Changes (`backend/evals/replay_eval.py`)
- Stage 2 changelog now captured and saved as `changelog_NNN_timestamp.json` alongside each run output file
- Previously the changelog was discarded (`_changelog`); now it's available for analysis

## Eval Results Summary

### Apples-to-apples comparison (old judge on both baseline and iter3 output)

| Metric | Baseline (v4p2_recognition_fix) | Iter3 (v4p2_coaching_quality_iter3) |
|--------|--------------------------------|-------------------------------------|
| Insightful | 34.9% (38 of 109) | 34.1% (46 of 135) |
| Adequate | 52.3% | 54.1% |
| Pedantic | 12.8% | 11.9% |
| N | 109 | 135 |

**The aggregate coaching quality is essentially unchanged.** Insightful rate held steady (absolute count increased from 38 to 46), pedantic rate slightly improved. The N increased because more patterns are evaluable per run (9.0 vs 7.3 patterns per run).

### Per-pattern pedantic rates (old judge, apples-to-apples)

| Pattern | Baseline Ped% | Iter3 Ped% |
|---------|--------------|------------|
| purposeful_framing | **15.4%** | **0.0%** |
| focus_management | 0.0% | 0.0% |
| resolution_and_alignment | **10.0%** | **7.7%** |
| assignment_clarity | **20.0%** | **20.0%** |
| question_quality | **16.7%** | **15.4%** |
| communication_clarity | **25.0%** | **53.8%** |
| active_listening | **20.0%** | **0.0%** |
| recognition | **10.0%** | **27.3%** |
| behavioral_integrity | 0.0% | 0.0% |
| disagreement_navigation | 0.0% | 0.0% |
| feedback_quality | 0.0% | 0.0% |

PF, AL improved significantly. CC and Recognition worsened. AC, QQ roughly flat.

### Judge Calibration Finding

Running the **new judge** (with "appropriate" category and explicit definitions) on the same iter3 output produced dramatically different numbers:
- Insightful dropped from 34.1% to 17.0%
- Appropriate appeared at 24.4%
- Pedantic dropped from 11.9% to 8.9%

This is a **calibration artifact**, not a quality change. The new judge definitions made it stricter about "insightful" and caused it to bin many adequate/insightful ratings as "appropriate." The old judge (without definitions) is the correct comparison baseline.

**Decision needed:** The new judge definitions need recalibration before they can be used for future evals. The "appropriate" category concept is sound, but the definitions are too broad — they're absorbing content that should be "adequate" or "insightful." Options:
1. Tighten the "appropriate" definition to only match true status-card content (very brief, no specific behavioral observations)
2. Remove the explicit definitions and let the judge use its own calibration (pre-change behavior) while keeping the "appropriate" category
3. Keep the old judge as the eval baseline and use the new judge only for "appropriate" classification

### Remaining Pedantic Problem: CC and Recognition

The LLM's changelog reveals the root cause. For CC on M-000003 (contentious meeting):
- "substantive_card because Alex's summaries and explanations were unusually strong and worth reinforcing"
- "substantive_card because clarity was a defining strength in key opening and closing moments"

For CC on M-000004 (avoider):
- "substantive_card with notes only; clarity was a real strength, while the bigger issue was not how clearly you spoke but what you did with dissent"

The LLM understands the framework. It makes thoughtful decisions and even acknowledges when CC isn't the central issue. But its threshold for "worth a substantive card" is lower than the judge's threshold for "not pedantic." When the LLM says "real strength worth reinforcing," the judge says "true but obvious, not coaching-rich."

This is a **calibration gap** between the LLM's quality bar and the judge's quality bar. The prompt guidance is clear; the LLM understands it; it's just making borderline calls differently than the judge would.

## What Remains

### Immediate options
1. **Run the full 10-transcript eval** with the old judge to get a larger sample size and confirm the per-pattern trends hold. The 3-transcript comparison has small N per pattern.
2. **Attempt further CC/Recognition calibration** — could try adding specific examples to Step 4 guidance showing when "real strength" is NOT worth a substantive card (e.g., "clarity in a meeting whose central issue is avoidance is not a strength worth coaching — it's background competence"). Risk: over-fitting to these transcripts.
3. **Accept the current quality level** — the 11.9% pedantic rate (down from 12.8%) may be close to the floor for prompt engineering. The remaining pedantic cases are judgment calls that reasonable coaches might disagree on.
4. **Recalibrate the new judge definitions** so future evals have a working "appropriate" category without the insightful drop.

### Files modified in this session
| File | Changes |
|------|---------|
| `clearvoice_pattern_taxonomy_v4.0.txt` | Behavioral context override, R&A coerced alignment, AL selective hearing, 6 coaching_note cleanups, CC cleanup |
| `system_prompt_coaching_v1.0.txt` | Steps 4-6 rewrite, card-mode field rules, no-empty-cards rule, self-audit, changelog expansion |
| `system_prompt_baseline_pack_v0_6_0.txt` | Judgment-based pattern coaching, card-mode model, no-empty-cards rule, self-checks |
| `backend/evals/judge_eval.py` | "appropriate" category, rating definitions |
| `backend/evals/judge_synthesis.py` | "appropriate" in _dist and report tables |
| `backend/evals/replay_eval.py` | Changelog capture and save |

### Eval results directories
| Phase | Contents |
|-------|----------|
| `v4p2_recognition_fix` | Baseline (3 meetings x 5 runs, old judge) |
| `v4p2_coaching_quality` | Initial changes (10 meetings x 5 runs, new judge) |
| `v4p2_coaching_quality_iter1` | Iteration 1 fixes (3 meetings x 5 runs, new judge) |
| `v4p2_coaching_quality_iter3` | Iteration 3 rewrite (3 meetings x 5 runs, both judges). New-judge files in `judge_new/` subdirs; old-judge files in meeting dirs. |
| `v4p2_coaching_quality_iter4` | Iteration 4 with changelog (3 meetings x 2 runs, no judge) |

### Test transcripts
Located at `backend/evals/transcripts_v4_test/`:
- M-000003_contentious_meeting.txt (+ .meta.json)
- M-000004_avoider.txt (+ .meta.json)
- M-000005_weak_feedback.txt (+ .meta.json)

### Active branch
- `claude/lucid-ellis` — current feature branch (worktree at `.claude/worktrees/lucid-ellis`)
