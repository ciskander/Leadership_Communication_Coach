# Phase C Eval — Continuation Prompt

Use this prompt to continue the Phase C eval cycle in a fresh chat window.

---

## Where We Are

**Branch**: `claude/wonderful-montalcini` (push this to main when Phase C is validated)

**Commit history**:
- `92c6410` — **Phase C**: taxonomy & prompt quality improvements from Phase B eval (CURRENT)
- `42cd475` — Phase B: add trust_and_credibility as 10th scored pattern
- `e283842` — Phase A: coaching quality improvements — conditional coaching + synthesis layer

**What Phase C changed** (commit `92c6410`):

Taxonomy (`clearvoice_pattern_taxonomy_v3.0.txt`):
1. Added focus_management vs trust_and_credibility disambiguation rule (EXCLUSIVE single-pattern)
2. Added question_quality functional classification — questions whose primary function is non-inquiry (steamrolling, avoidance, redirection) classified under DN/T&C/FM, not QQ
3. Tightened participation_management with decision-meeting filter and criteria-based "meaningful alternative" test
4. Added T&C success evidence litmus test (coaching output only, not scoring)
5. Added T&C materiality test for opportunity detection ("would an executive coach notice?")
6. Added focus_management 1:1 feedback conversation guidance
7. Added concrete "quick test" decision anchors to DN vs T&C and FM vs T&C disambiguation heuristics
8. Clarified T&C observable-behavior rule: target speaker intent inference forbidden, impact-on-others inference legitimate
9. Clarified T&C stated-values opportunity type: both sides of contradiction must be observable
10. Fixed communication_clarity 0.75 tier: "MOST of" → "at least 4 of 5 criteria"
11. Removed unused "binary" scoring type
12. Updated header to 10 patterns, Cluster B description, cluster coaching guidance, meeting type expectations

System prompt (`system_prompt_v0_4_0.txt`):
1. Added T&C overcounting warning
2. Fixed "8 patterns" → "9 patterns" in quality-over-coverage
3. Removed binary scoring type references

**New tooling**: `backend/evals/judge_synthesis.py` — aggregates judge_eval outputs into structured synthesis report with phase comparison.

## Phase B Eval Baselines (the numbers Phase C needs to beat)

### Judge Quality (Layer 2)
- **Aggregate**: 39.0% insightful, 49.2% adequate, 11.9% pedantic, 0% wrong (295 ratings)
- **Phase A aggregate**: 41.2% insightful, 45.4% adequate, 13.4% pedantic, 0% wrong (262 ratings)

### Pedantic Hot Spots (3+ of 5 runs pedantic)
- `question_quality` on M-004: **5/5 pedantic** — praised questions used to steamroll
- `focus_management` on M-005: **4/4 pedantic** — forced in 1:1 feedback conversation
- `participation_management` on M-003: **3/5 pedantic** — basic facilitation, not coaching-worthy
- `participation_management` on M-004: **3/5 pedantic** — same issue
- `trust_and_credibility` on M-001: **2/5 pedantic** — overlap with focus_management

### Score Stability (Layer 1)
- `participation_management`: mean dropped 0.067 vs Phase A, IQR nearly tripled, OE count stdev 3.90 on M-001 (range 2-12)
- `communication_clarity`: OE count stdev 4.51 on M-055 (range 7-18), 4.16 on M-005 (range 6-17)
- `focus_management` on M-005: IQR went from 0.0 to 1.0 (threshold effect, 0-1 OEs)

### T&C Pattern
- M-001 (strong facilitator): evaluable with 0.85 score — user is OK with this being a strength, but 2/5 pedantic and 4/5 success evidence "doesn't demonstrate pattern"
- M-002, M-004, M-005: 100% insightful (5/5 each) — the pattern's core value
- anything_important_ignored trust/credibility mentions: 4/35 (11.4%) vs Phase A 9/35 (25.7%)

### Overall Coaching Value
- 34/35 rated "medium", 1/35 "high"

## What Needs to Happen Next

### Step 1: Run replay_eval (Layer 1) — ~7 min
```bash
cd "<project_root>"
python -m backend.evals.replay_eval \
  --mode compare \
  --transcripts-dir backend/evals/transcripts \
  --runs 5 \
  --model gpt-5.4 \
  --detail
```
- All 5 runs per transcript happen in parallel (OpenAI model)
- Expect Gate1 failures — ignore them, run JSONs save regardless
- Results save to `backend/evals/results/<meeting_id>/run_NNN_<timestamp>.json`
- Compare report saves to `backend/evals/results/compare_report_<timestamp>.json` + `.md`

### Step 2: Run judge_eval (Layer 2) — ~7 min
Launch all 7 meetings in parallel:
```bash
TRANSCRIPTS="backend/evals/transcripts"
RESULTS="backend/evals/results"

for meeting in M-000001_strong_facilitator M-000002_weak_facilitator M-000003_contentious_meeting M-000004_avoider M-000005_weak_feedback M-000006_stress_test M-000055_feedback; do
  python -m backend.evals.judge_eval \
    --transcript "$TRANSCRIPTS/${meeting}.txt" \
    --output-dir "$RESULTS/$meeting" \
    --all &
done
wait
```

### Step 3: Run judge_synthesis (new tool)
```bash
python -m backend.evals.judge_synthesis \
  --results-dir backend/evals/results \
  --baseline-dir backend/evals/results/Phase_A
```
This produces `judge_synthesis_<timestamp>.json` + `.md` with all aggregate metrics, heat maps, and phase comparison.

### Step 4: Compare Phase C vs Phase B

Load the Phase C compare report and the Phase B compare report (`compare_report_20260328T185145.json`) to diff:
- Per-pattern score means and IQRs for existing 9 patterns (should be stable or improved)
- OE count variation (participation_management and communication_clarity should decrease)
- T&C scores across meetings

For judge comparison, use the Phase B synthesis numbers above as baseline (or save the Phase B judge synthesis JSON to `backend/evals/results/Phase_B/` first).

**IMPORTANT**: Before running Step 3, move the Phase B judge synthesis and judge files to `backend/evals/results/Phase_B/` so they don't get mixed with Phase C results. The judge_synthesis script uses most-recent-timestamp-batch detection, but keeping phases in separate directories is cleaner.

### Key Tests (what Phase C should fix)
1. `question_quality` pedantic on M-004 should decrease from 5/5 (functional classification → moments reclassified to DN/T&C)
2. `focus_management` pedantic on M-005 should decrease from 4/4 (1:1 guidance → insufficient_signal)
3. `participation_management` pedantic on M-003/M-004 should decrease (decision-meeting filter)
4. `participation_management` OE count stdev should decrease (meaningful-alternative test)
5. `communication_clarity` OE count stdev should decrease (per-turn confidence test)
6. `trust_and_credibility` on M-001: pedantic should drop from 2/5 (FM disambiguation)
7. T&C success evidence quality should improve (litmus test)
8. Aggregate insightful% should hold or improve from 39.0%
9. Zero wrong maintained

## Key Files

| File | Purpose |
|------|---------|
| `clearvoice_pattern_taxonomy_v3.0.txt` | Pattern definitions, scoring rubrics, disambiguation rules |
| `system_prompt_v0_4_0.txt` | LLM system prompt for analysis |
| `backend/evals/replay_eval.py` | Layer 1: score stability & discriminant validity |
| `backend/evals/judge_eval.py` | Layer 2: LLM-as-judge coaching quality |
| `backend/evals/judge_synthesis.py` | Judge result aggregation & phase comparison |
| `backend/evals/report.py` | Shared stats/formatting utilities |
| `backend/evals/transcripts/` | 7 eval transcripts + eval_config.json |
| `backend/evals/results/Phase_A/` | Phase A baseline results (runs + judges) |
| `backend/evals/results/Phase_A/compare_report_20260328T165630.json` | Phase A score stats |
| `backend/evals/results/compare_report_20260328T185145.json` | Phase B score stats |
| `backend/evals/results/judge_synthesis_20260328T202117.json` | Phase B judge synthesis |

## Eval Workflow Summary

```
replay_eval (Layer 1)     judge_eval (Layer 2)
    |                          |
    v                          v
compare_report.json       judge_*.json (per meeting)
    |                          |
    v                          v
Score stability            judge_synthesis.py
IQR, OE count, means          |
                               v
                          judge_synthesis.json/.md
                          Aggregate metrics, heat maps, phase comparison
```

Both layers run independently. Compare results against Phase B baselines documented above.
