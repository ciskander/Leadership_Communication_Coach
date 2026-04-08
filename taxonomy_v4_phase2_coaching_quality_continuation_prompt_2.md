# Taxonomy v4.0 — Phase 2 Coaching Quality: Continuation Prompt 2

## Context

We completed a major round of coaching quality improvements across the taxonomy, coaching prompt, baseline pack prompt, judge eval, and eval pipeline. This continuation prompt captures what was done, what worked, what didn't, and what remains.

IMPORTANT NOTE FOR THE SESSION: Never make assumptions. If anything is ambiguous, inconsistent, underspecified, or otherwise unclear, always stop and ask questions before proceeding. Precision and correctness are 10x more important than development speed.

### Stage architecture (read this first)

- **Stage 1** (scoring): System prompt is `system_prompt_scoring_v1.0.txt`. Developer message is the **full taxonomy** (`clearvoice_pattern_taxonomy_v4.0.txt`). Generates scores, OEs, evidence spans. Does NOT generate coaching fields (`notes`, `coaching_note`).
- **Stage 2** (coaching): System prompt is `system_prompt_coaching_v1.0.txt` with `__PATTERN_DEFINITIONS__` replaced by a **condensed extraction** from the taxonomy (only "What it measures", "NOT this pattern", "Disambiguation", "Coaching materiality" — see `extract_stage2_pattern_definitions()` in `backend/core/prompt_builder.py`). Stage 2 does NOT see GENERAL_DETECTION_GUIDANCE, full detection notes, or taxonomy coaching instructions.
- **Baseline pack**: System prompt is `system_prompt_baseline_pack_v0_6_0.txt`. Generates both scoring and coaching in one pass.

This means: taxonomy changes affect Stage 1 scoring only (indirect effect on coaching via better scores). Coaching prompt changes directly affect Stage 2 coaching output.

### Key terms

- **Card-mode model**: Each pattern_coaching entry is either a "substantive card" (one or both of notes/coaching_note contain real coaching, other can be null) or a "status card" (one field contains a no-empty-cards option, other is null, all supporting fields null). Modes are never mixed on the same card.
- **No-empty-cards options**: Valid status-card content — a brief positive acknowledgment, a cross-reference to where the real coaching lives, or a neutral status statement like "Consistently strong here; no developmental notes."
- **Stage 2 changelog**: The `changes` array in Stage 2 output, saved as `changelog_NNN_timestamp.json` by the eval pipeline. Logs Step 4 card-mode decisions, notes null decisions, and self-audit downgrades.

### Eval commands

Run from the main branch root directory:
```
# Full eval with judge (3 target transcripts):
python -m backend.evals.run_pipeline --phase <phase_name> --transcripts-dir backend/evals/transcripts_v4_test --runs 5 --judge

# Full eval with judge (all 10 transcripts):
python -m backend.evals.run_pipeline --phase <phase_name> --transcripts-dir backend/evals/transcripts --runs 5 --judge

# Changelog-only (no judge, cheaper):
python -m backend.evals.run_pipeline --phase <phase_name> --transcripts-dir backend/evals/transcripts --runs 2
```

## What Was Done

### Taxonomy Changes (`clearvoice_pattern_taxonomy_v4.0.txt`)
- Added **behavioral context override** to GENERAL_DETECTION_GUIDANCE — helps Stage 1 recognize when surface-level pattern "successes" primarily served a dominant interpersonal failure (avoidance, coercion, dismissiveness)
- Added **R&A coerced alignment** detection note — procedural closure via authority override scores low on alignment confirmation
- Added **AL selective hearing** detection note — performative acknowledgment followed by ignoring substance scores 0.25 at best
- **Cleaned up 6 coaching_note instructions** that Stage 1 cannot act on (AC, QQ, CC, Recognition, BI, BI+DN) — removed coaching directives, kept detection/scoring guidance. These were vestigial — see Stage architecture above.

### Coaching Prompt Changes (`system_prompt_coaching_v1.0.txt`)
Major restructuring of the reasoning sequence:

- **Merged old Steps 4+5 into Step 4 (Pattern-level coaching decisions)** — clean two-mode decision: substantive card vs status card, with value test, behavioral context test, and tiebreaker criteria
- **Rewrote old Step 6 as Step 5 (Pattern-level coaching generation)** — handles only substantive cards, with quality gates for both notes and coaching_note, theme overlap check with downgrade path
- **Renumbered all steps** — old 7/7b/8/9 became 6/6b/7/8
- **Restructured PATTERN COACHING field rules around card-mode model** — SUBSTANTIVE CARDS section with field definitions, STATUS CARDS section with no-empty-cards rule
- **No-empty-cards rule** — three problems (pedantic, empty, tone-deaf), two guiding principles (no silent cards, no forced coaching), three example options (not exhaustive)
- **Card-mode model** — substantive and status content never mixed on the same card. Substantive: one or both fields have real coaching, other can be null. Status: one field has a no-empty-cards option, other is null, all supporting fields null.
- **Tightened Step 8 self-audit** — merged overlapping checks, added incoherent status card check, removed active experiment coaching_note requirement (experiments now link to 0..N patterns)
- **Expanded `changes` field** — now logs Step 4 card-mode decisions with reasons, notes null decisions, and self-audit downgrades. Schema: `{"field": "pattern_coaching.<pattern_id>", "action": "substantive_card|status_card|downgraded_to_status|noted", "reason": "<why>"}`

### Baseline Pack Changes (`system_prompt_baseline_pack_v0_6_0.txt`)
- Replaced mechanical score-based pattern coaching (score > 0 = notes, score < 1.0 = coaching_note) with judgment-based quality guidance matching the single-meeting philosophy
- Same card-mode model, no-empty-cards rule, and behavioral context override as coaching prompt
- Updated self-checks to match card-mode model

### Eval Pipeline Changes (`backend/evals/replay_eval.py`)
- Stage 2 changelog now captured and saved as `changelog_NNN_timestamp.json` alongside each run output file
- Previously the changelog was discarded (`_changelog`); now it's available for analysis

## Eval Results Summary

### Aggregate comparison (baseline vs iter3, same 3 meetings x 5 runs)

| Metric | Baseline (v4p2_recognition_fix) | Iter3 (v4p2_coaching_quality_iter3) |
|--------|--------------------------------|-------------------------------------|
| Insightful | 34.9% (38 of 109) | 34.1% (46 of 135) |
| Adequate | 52.3% | 54.1% |
| Pedantic | 12.8% | 11.9% |
| N | 109 | 135 |

**The aggregate coaching quality is essentially unchanged.** Insightful rate held steady (absolute count increased from 38 to 46), pedantic rate slightly improved. The N increased from 109 to 135 because more patterns are evaluable per run (9.0 vs 7.3) — the card-mode model keeps status cards visible to the judge, whereas the old prompt would leave both fields null and the judge formatting code would skip them entirely. Empty cards remaining: 6 of 141 total pattern_coaching entries across all runs (4.3%; the 141 count differs from the 135 judge N because the judge skips both-null cards).

### Per-pattern pedantic rates

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

### Per-pattern insightful rates

Absolute insightful count increased from 38 to 46 (+8). Per-pattern:

| Pattern | Baseline ins (N) | Iter3 ins (N) | Delta |
|---------|-----------------|---------------|-------|
| purposeful_framing | 2 (13) | 1 (15) | -1 |
| focus_management | 2 (5) | 2 (7) | 0 |
| resolution_and_alignment | 6 (10) | 6 (13) | 0 |
| assignment_clarity | 0 (15) | 3 (15) | +3 |
| question_quality | 7 (12) | 4 (13) | -3 |
| communication_clarity | 0 (12) | 3 (13) | +3 |
| active_listening | 2 (10) | 6 (15) | +4 |
| recognition | 1 (10) | 0 (11) | -1 |
| behavioral_integrity | 6 (6) | 8 (13) | +2 |
| disagreement_navigation | 6 (9) | 8 (15) | +2 |
| feedback_quality | 1 (1) | 5 (5) | +4 |

Per-pattern percentage drops (e.g., QQ 58%->31%, BI 100%->62%) are largely denominator effects from more patterns being evaluable. The only genuine absolute drop is QQ (-3), which appears to be judge variance — the LLM writes essentially the same QQ insight across both versions, but the judge rates it insightful in some runs and adequate in others.

### Remaining Pedantic Problem: CC and Recognition

CC and Recognition are the only patterns where pedantic rates worsened. The Stage 2 changelog (from v4p2_coaching_quality_iter4) reveals the root cause — a **calibration gap** between the LLM's quality bar and the judge's quality bar. The LLM understands the framework and makes thoughtful decisions, but its threshold for "worth a substantive card" is lower than the judge's threshold for "not pedantic."

**CC changelog examples:**

M-000003 (contentious meeting):
- Run 001: "substantive_card because Alex's summaries and explanations were unusually strong and worth reinforcing"
- Run 002: "substantive_card because clarity was a defining strength in key opening and closing moments"

M-000004 (avoider):
- Run 001: "Clear enough to acknowledge as a supporting strength, though not the central coaching issue"
- Run 002: "substantive_card with notes only; clarity was a real strength, while the bigger issue was not how clearly you spoke but what you did with dissent"

Note: Run 002 on M-000004 even acknowledges CC isn't the central issue — but still gives it a substantive card. The LLM sees "real strength" and defaults to substantive even when it knows the pattern is peripheral. The judge calls this pedantic: "clarity is not the issue in this meeting."

**Recognition changelog examples:**

M-000003:
- Run 001: "status_card because recognition was present but not central to the coaching story" (correct — judge would agree)
- Run 002: "substantive_card because this is the clearest developmental edge and ties directly to the meeting's main coaching message" (judge calls this pedantic — recognition is not the developmental edge in this meeting)

## What Remains

### Immediate options

1. **Run the full 10-transcript eval** with judge to get a larger sample size and confirm the per-pattern trends hold. The 3-transcript comparison has small N per pattern (e.g., CC has only 13 ratings — the 25%->54% pedantic jump could be noise).
2. **Attempt further CC/Recognition calibration** — could try adding specific examples to Step 4 guidance showing when "real strength" is NOT worth a substantive card (e.g., "clarity in a meeting whose central issue is avoidance is not a strength worth coaching — it's background competence"). Risk: over-fitting to these transcripts. The changelog shows the LLM already understands the principle but makes borderline calls differently.
3. **Accept the current quality level** — the 11.9% pedantic rate (down from 12.8%) may be close to the floor for prompt engineering. The remaining pedantic cases are judgment calls that reasonable coaches might disagree on.
4. **Analyze changelogs at scale** — run the eval on all 10 transcripts with 2 runs each (cheap — no judge needed; see Eval commands above), then analyze changelog patterns to see if the CC/Recognition calibration gap is consistent or transcript-specific.

### Eval results directories
| Phase | Contents |
|-------|----------|
| `v4p2_recognition_fix` | Baseline (3 meetings x 5 runs, with judge). **Use this as the comparison baseline.** |
| `v4p2_coaching_quality` | Initial changes (10 meetings x 5 runs, run output only — no judge files). |
| `v4p2_coaching_quality_iter1` | Iteration 1 fixes (3 meetings x 5 runs, run output only — no judge files). |
| `v4p2_coaching_quality_iter3` | Iteration 3 rewrite (3 meetings x 5 runs, with judge). **This is the primary comparison to baseline.** |
| `v4p2_coaching_quality_iter4` | Iteration 4 with changelog (3 meetings x 2 runs, no judge). Use for changelog analysis. |

### Test transcripts
Located at `backend/evals/transcripts_v4_test/` (subset of `backend/evals/transcripts/`):
- **M-000003_contentious_meeting** — Cross-functional project review, Alex as chair, multiple substantive disagreements about release scope, QA, and design. Alex is generally strong but over-commits.
- **M-000004_avoider** — Project review, Alex as chair, leader dismisses substantive pushback from experts (Jamie on design, Taylor on QA certification). The central coaching issue is avoidance/coercion.
- **M-000005_weak_feedback** — 1:1 manager meeting, Jordan giving developmental feedback to Avery with vague unnamed sourcing, hedging, and no concrete examples. The central coaching issue is feedback quality.

### Baseline pack note
The baseline pack prompt changes (judgment-based pattern coaching, card-mode model) have NOT been eval-tested. All eval results in this document are for single-meeting coaching (Stage 2). Baseline pack validation is a separate task.

### Branch state
All changes are merged to `main`. The worktree branch `claude/lucid-ellis` is behind main and can be cleaned up.
