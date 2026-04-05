# Longitudinal Eval — Scale Test Continuation Prompt

## How to use this document

This is an **execution** continuation prompt. The longitudinal eval suite is fully implemented and smoke-tested. Your job is to run the scale test, review results, and document findings. Read this document for context, then execute the steps below.

Refer to `CLAUDE.md` in the project root for tech stack and conventions.

**IMPORTANT: All commands must be run from the main project root**, not from a worktree:
```
C:\Users\chris\Documents\Persollaneous\Business\Communication Coaching Tool\LLM Prompt to Build Python\Combined Project Files
```
The `.env` file with API keys is in this directory. The eval modules resolve paths relative to the project structure.

---

## What this eval tests

The core question: **Does giving the coaching LLM access to a coachee's prior meeting history improve coaching quality?**

The eval generates synthetic coachees (personas), runs them through multiple meetings where coaching feedback accumulates over time, then compares the coaching output with longitudinal context vs without. Three judge types assess different aspects:

- **Series judge** — evaluates the full coaching arc across all meetings for one persona. Does the coaching evolve, or does it repeat itself? Are experiment transitions logical? Does the executive summary track growth?
- **A/B comparative judge** — per follow-up meeting, compares coaching WITH history vs WITHOUT history (blind, randomized). Which is more specific, fresher, more useful to a leader?
- **Standard per-meeting judge** — evaluates the with-history coaching output on its own merits (insight quality, evidence grounding, rewrite quality, etc.)

If the system is working well: the series judge should rate arcs as "evolving" with "high" value, the A/B judge should prefer with-history, and the advantage should grow as more history accumulates.

---

## What's been completed

### Longitudinal eval suite (4 modules)

| Module | File | Purpose |
|--------|------|---------|
| 1 | `backend/evals/longitudinal_transcript_gen.py` | Persona gen, baseline/follow-up transcript gen via Claude Sonnet, coaching context formatting, quality heuristics, condensed history builder |
| 2 | `backend/evals/longitudinal_eval.py` | Main orchestrator: sequential per-persona pipeline (baselines → synthesis → follow-ups with memory), A/B comparison, crash recovery |
| 3 | `backend/evals/longitudinal_judge.py` | Series judge (full-arc), A/B comparative judge (randomized), standard per-meeting judge (reuses `judge_eval.py`) |
| 4 | `backend/evals/longitudinal_report.py` | Per-persona markdown reports + aggregate report with coherence rate, A/B win rate, detection accuracy, score trajectories |

### Pipeline architecture

The orchestrator mirrors the production two-stage pipeline exactly:
- **Stage 1**: `load_scoring_system_prompt()` + `build_developer_message()` (taxonomy) → `call_llm()` → `patch_analysis_output(scoring_only=True)` → `gate1_validate(mode="scoring_only")`
- **Stage 2**: `build_stage2_system_prompt(memory)` + `build_stage2_user_message(stage1, turns)` → `call_llm()` → `merge_stage2_output()` → `patch_analysis_output(scoring_only=False)` → `gate1_validate(mode="full")`
- **Baseline synthesis**: After 3 baseline sub-runs, a 4th LLM call uses `build_baseline_pack_prompt()` + `load_baseline_system_prompt()` to synthesize coaching across all 3 meetings. Only the synthesis coaching enters the longitudinal history.

### Models used

- **Transcript generation**: Claude Sonnet (`claude-sonnet-4-6`) — hardcoded in `longitudinal_transcript_gen.py` as `_DEFAULT_TRANSCRIPT_MODEL`. Creative writing task, uses `json_mode=False` (plain-text output, no JSON parsing). Override with `--transcript-model`.
- **Analysis (Stage 1 + Stage 2 + synthesis)**: GPT-5.4 — uses the default from `config.py:OPENAI_MODEL_DEFAULT`. Override with `--model`.
- **Judges**: GPT-5.4 — same default. Override with `--model` on the judge command.

Note: `--model` controls analysis and judge models. `--transcript-model` controls transcript generation. If neither is specified, the defaults above are used. These are independent — you can use Claude for transcripts and GPT for analysis simultaneously.

### Per-persona lifecycle

For each persona, the pipeline runs these steps sequentially:

1. **Generate persona** — Claude Sonnet creates a detailed professional profile (role, colleagues, communication strengths/weaknesses)
2. **Generate 3 baseline transcripts** — one LLM call produces all 3 meeting transcripts + initial `story_so_far`
3. **Analyze each baseline** — Stage 1 (scoring) + Stage 2 (coaching) per meeting, all with empty memory (baselines are stateless)
4. **Run baseline synthesis** — 4th LLM call combines 3 sub-run analyses into one coaching output. This is the coaching the coachee "sees." Its themes and executive summary enter `coaching_history` as the single baseline coaching event. The first experiment is adopted from the synthesis `micro_experiment`.
5. **For each follow-up meeting** (meeting 4, 5, ... N):
   - Generate follow-up transcript using coaching context from the most recent analysis + `story_so_far`
   - Run Stage 1 + Stage 2 with populated memory (coaching_history, experiment_history, experiment_progress, active_experiment)
   - Process `graduation_recommendation` (graduate/park/continue the active experiment)
   - If experiment graduated/parked: clear active experiment; the NEXT meeting's Stage 2 will propose a new one
   - Update `state.json`
6. **A/B comparison** — re-run Stage 2 on each follow-up with empty memory (parallel, independent)

### Experiment lifecycle

The orchestrator handles the full experiment lifecycle from Stage 2's `graduation_recommendation`:
- `graduate` → experiment moves to history as "completed", `story_so_far` updated, next meeting proposes new experiment
- `park` (pivot/stale) → experiment moves to history as "parked" with reason, pivot rationale carried forward in `story_so_far`
- `continue` → experiment stays active, safety cap nudge after 5 meetings
- `experiment_progress` tracks per-meeting detection (attempt, count, coaching_note) and feeds into MemoryBlock for Stage 2 attempt history

### A/B comparison design

After all persona series complete, each follow-up meeting (meeting_04+) gets a second Stage 2 run with an **empty MemoryBlock** — no coaching history, no experiment context, no experiment progress. The same Stage 1 scoring output is reused. This produces `analysis_no_history.json` alongside the original `analysis.json` (which had full longitudinal context). The A/B judge then compares the two coaching outputs blind (randomized to System A/B positions to avoid position bias).

### Memory accumulation

- `state.json` stores full coaching_history, experiment_history, active_experiment, experiment_progress, story_so_far
- `MemoryBlock` at build time applies windowing: last 3 coaching_history, last 5 experiment_history
- Baseline = one coaching event (from synthesis, not individual sub-runs)
- Each follow-up = one coaching event appended to history

### Output structure

```
backend/evals/results/Long_YYYYMMDD/
├── manifest.json
├── persona_01/
│   ├── persona.json
│   ├── state.json
│   ├── quality.json
│   ├── baseline_synthesis.json
│   ├── meeting_01/ ... meeting_03/        (baseline)
│   │   ├── transcript.txt
│   │   ├── metadata.json
│   │   ├── stage1.json                    (Stage 1 parsed analysis dict — NOT a wrapper)
│   │   ├── stage2_raw.json                (Stage 2 coaching delta before merge)
│   │   └── analysis.json                  (final merged + patched + validated)
│   ├── meeting_04/ ... meeting_NN/        (follow-up)
│   │   ├── transcript.txt
│   │   ├── metadata.json
│   │   ├── design_note.json
│   │   ├── stage1.json
│   │   ├── stage2_raw.json
│   │   ├── analysis.json
│   │   └── analysis_no_history.json       (A/B)
├── judges/
│   └── persona_01/
│       ├── longitudinal_series.json
│       ├── meeting_04_ab_comparison.json
│       └── meeting_04_standard.json
└── reports/
    ├── persona_01_longitudinal.md
    ├── aggregate_report.md
    └── aggregate_stats.json
```

### Smoke test results (1 persona, 4 meetings)

- Pipeline completed end-to-end with no errors
- Series judge: overall_longitudinal_value = **high**, theme_evolution = **evolving**
- A/B judge: preferred **with_history** (high confidence, all 4 dimensions)
- Standard judge: coaching_value = medium, would_approve = True
- All transcripts passed quality checks
- Coaching themes have `nature` classification (strength/developmental/mixed) in follow-up meetings and baseline synthesis

---

## Known issues

1. **Experiment ID sanitization**: Gate1 renames eval-format IDs like `EXP-EVAL-P01-001` to `EXP-001001` to match the production `EXP-NNNNNN` pattern. Harmless — the ID still works, just gets silently renamed.

2. **Detection accuracy metric**: Design note `intended_attempt_level` vs actual `detection.attempt` often disagrees (e.g., intended="yes", detected="partial"). This is by design — the transcript generator's intent and the analysis system's judgment are independent. The metric is still useful for tracking gross mismatches.

3. **Smoke test output exists**: `backend/evals/results/Long_20260404/` contains the 1-persona smoke test output. This is a reference for the expected directory structure but uses old output (pre-baseline-prompt-update). Don't use it for quality assessment — run a fresh test instead.

---

## What to do now: Scale test

### Step 1: Run the scale test

```bash
python -m backend.evals.longitudinal_eval \
  --num-personas 3 \
  --meetings-per-persona 6 \
  --no-pause \
  --phase Long_Scale_01
```

This runs 3 personas × 6 meetings (3 baseline + 3 follow-up). Estimated cost: ~$15-25 in API tokens. Expected duration: 15-30 minutes.

**How it runs**: Within each persona, meetings are strictly sequential (each meeting's coaching feeds the next transcript). Across personas, the pipeline runs in parallel using `ThreadPoolExecutor`. The number of parallel workers is calculated from `--tpm-limit` (default 4M tokens/min): `min(num_personas, tpm_limit * 0.8 / 95_000)`.

**What each meeting costs**: ~95K tokens total — transcript generation (~12K via Sonnet) + Stage 1 scoring (~48K via GPT-5.4) + Stage 2 coaching (~35K via GPT-5.4). Baseline synthesis adds one extra ~50K call after the 3 baselines. A/B comparison adds one ~35K Stage 2 call per follow-up meeting.

For a larger test (if the first passes cleanly):

```bash
python -m backend.evals.longitudinal_eval \
  --num-personas 5 \
  --meetings-per-persona 8 \
  --no-pause \
  --phase Long_Scale_02
```

### Step 2: Run judges

```bash
python -m backend.evals.longitudinal_judge \
  --phase-dir backend/evals/results/Long_Scale_01
```

### Step 3: Generate reports

```bash
python -m backend.evals.longitudinal_report \
  --phase-dir backend/evals/results/Long_Scale_01
```

### Step 4: Review results

Key metrics to check in `reports/aggregate_report.md`:
- **Coaching arc coherence rate**: % of personas with evolving themes + medium/high value. Target: >60%
- **A/B win rate**: with_history should win overall. Check if advantage grows with meeting number.
- **Detection accuracy**: Expect 40-60% exact match (design intent vs detection). Look for systematic biases.
- **Score trajectories**: Experiment-targeted patterns should show some improvement over time.

Per-persona reports (`reports/persona_NN_longitudinal.md`):
- Read the series judge explanations — they're the most informative single artifact
- Check theme evolution: are themes evolving or repeating?
- Check experiment journey: are transitions logical?

### Step 5: Crash recovery (if needed)

The pipeline is fully resumable. Before each step, it checks if the output file already exists and skips if so:
- `transcript.txt` exists → skip transcript generation
- `stage1.json` exists → skip Stage 1
- `analysis.json` exists → skip Stage 2 + merge
- `baseline_synthesis.json` exists → skip synthesis
- `analysis_no_history.json` exists → skip A/B for that meeting

Per-persona state is tracked in `state.json` (last completed meeting, coaching history, experiment state). On restart, it loads state from this file and resumes from the next incomplete meeting.

```bash
# Re-run with the same --phase flag — picks up where it left off
python -m backend.evals.longitudinal_eval \
  --num-personas 3 \
  --meetings-per-persona 6 \
  --no-pause \
  --phase Long_Scale_01
```

To re-run just judges or reports on existing output:
```bash
# Judges only (skips generation + analysis)
python -m backend.evals.longitudinal_judge --phase-dir backend/evals/results/Long_Scale_01

# Reports only
python -m backend.evals.longitudinal_report --phase-dir backend/evals/results/Long_Scale_01
```

To start completely fresh (discard a previous run):
```bash
rm -rf backend/evals/results/Long_Scale_01
# Then re-run the command
```

**Useful skip flags**:
- `--skip-generation`: Use existing transcripts, only run analysis. Useful when transcripts are fine but you changed the analysis pipeline.
- `--skip-analysis`: Use existing analysis, only run A/B comparison. Useful when analysis is fine but you want to add/redo A/B.
- `--skip-ab`: Skip the A/B comparison entirely (saves ~35K tokens per follow-up meeting).
- `--skip-judge`: Skip judge evaluation (run judges separately via `longitudinal_judge.py`).

### Step 6: Document findings

Write a summary in `backend/evals/results/Long_Scale_01/findings.md` covering:
1. **Does longitudinal context improve coaching quality?** — A/B win rate overall + by meeting number + by dimension. Does the advantage grow with more history?
2. **Is the coaching arc coherent across meetings?** — Series judge coherence rate. Read the series judge explanations for the best qualitative signal.
3. **Are there systematic issues?** — Theme repetition (freshness ratings), experiment stalling (same experiment >5 meetings), detection failures (systematic bias in intended vs detected). Flag specific personas where things went wrong.
4. **Recommendations** — Should the coaching prompt be adjusted? Is the memory window (3 meetings) too small or too large? Are experiments transitioning at sensible times?

---

## Judge dimensions reference

### Series judge dimensions
| Dimension | Ratings | What it checks |
|---|---|---|
| `coaching_theme_evolution` | evolving / stagnant / contradictory | Do themes evolve, resolve, introduce new ones? |
| `executive_summary_arc` | coherent_arc / disconnected / generic | Does the summary narrative build across meetings? |
| `experiment_coaching_quality` | strong_progression / adequate / illogical | Detection accuracy, logical experiment sequencing |
| `score_narrative_coherence` | coherent / minor_inconsistencies / contradictory | Do scores and coaching narrative agree? |
| `coaching_freshness` | fresh_and_deepening / some_repetition / stale | Avoids verbatim repetition, progressively nuanced? |
| `overall_longitudinal_value` | high / medium / low | Would a real coach find this series useful? |

### A/B judge dimensions
| Dimension | What it checks |
|---|---|
| `specificity` | Which system's coaching is more specific to THIS leader in THIS meeting? |
| `context_use` | Which system better uses knowledge of the coachee's history? |
| `freshness` | Which system avoids repeating what the coachee has already heard? |
| `leader_value` | Which output would a senior leader find more useful? |

Each returns `preferred: "with_history" | "no_history" | "tie"` with `confidence: "high" | "medium" | "low"`.

### Standard judge key fields
| Field | What it checks |
|---|---|
| `overall_coaching_value` | high / medium / low — overall coaching quality |
| `would_approve_for_delivery` | true / false — would a coach send this to a client? |
| `coaching_themes_quality.nature_accurate` | Is the strength/developmental/mixed classification correct? |
| `coaching_themes_quality.evidence_grounding` | Do the evidence quotes support the theme's claims? |

---

## Troubleshooting

**A persona fails mid-run**: Check the log for the specific error. Common causes: LLM rate limits (retry automatically), Gate1 validation failure (check `stage1.json` for issues), transcript parsing failure (check `transcript.txt` format). The pipeline continues to the next meeting — check `state.json` for `last_completed_meeting` and the `MeetingResult` error field.

**Judges return unexpected results**: Inspect the raw judge JSON in `judges/persona_NN/`. The `_meta` field shows token counts and model used. For A/B judges, `_meta.randomization` shows which system was A and which was B. If the judge seems confused, check that the condensed history (`build_condensed_history` output) is well-formed.

**Transcripts are unrealistic**: Check `persona.json` — is the persona detailed enough? Check `quality.json` for heuristic failures (too few turns, speaker domination). The transcript gen model (Claude Sonnet) can be overridden with `--transcript-model`.

**All A/B results are ties**: The coaching history might not be substantive enough. Check `state.json` — does `coaching_history` have meaningful themes and executive summaries? If the baseline synthesis produced generic coaching, the follow-up memory won't add much value.

**Experiment never transitions**: Check `state.json` for `experiment_progress` — is the LLM detecting attempts? Check `graduation_recommendation` in the follow-up `analysis.json` files. If the recommendation is always "continue", the experiment may need more meetings or the transcript generator may not be creating enough variation.

---

## Key files reference

| File | Purpose |
|------|---------|
| `backend/evals/longitudinal_eval.py` | Main orchestrator — run this for the full pipeline |
| `backend/evals/longitudinal_judge.py` | Judge evaluation — run this after analysis completes |
| `backend/evals/longitudinal_report.py` | Report generation — run this after judges complete |
| `backend/evals/longitudinal_transcript_gen.py` | Transcript generation (called by orchestrator, not directly) |
| `backend/evals/judge_eval.py` | Standard per-meeting judge (called by longitudinal_judge) |
| `backend/core/prompt_builder.py` | Prompt construction for both stages |
| `backend/core/workers.py` | Production pipeline (reference for how the eval mirrors it) |
| `system_prompt_scoring_v1.0.txt` | Stage 1 scoring prompt |
| `system_prompt_coaching_v1.0.txt` | Stage 2 coaching prompt |
| `system_prompt_baseline_pack_v0_6_0.txt` | Baseline synthesis prompt |
| `clearvoice_pattern_taxonomy_v3.1.txt` | Pattern taxonomy (developer_message for Stage 1 + synthesis) |

---

## Important constraints

1. **Do NOT modify the eval infrastructure** (`backend/evals/judge_eval.py`, `backend/evals/report.py`, `backend/evals/replay_eval.py`) without explicit approval.
2. **Do NOT modify production prompts** (`system_prompt_*.txt`) or production backend code (`backend/core/`) without explicit approval.
3. **Transcript generation uses Claude Sonnet** with `json_mode=False`. Analysis uses GPT-5.4 with standard JSON mode. Do not change these models without discussing with the user.
4. **The `.env` file** must be in the project root with `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. `config.py` uses `load_dotenv(override=True)`. If API calls fail with auth errors, check that these keys are present and non-empty.
5. **Results directories** (`backend/evals/results/Long_*`) are gitignored. Don't commit test output.
6. **The baseline synthesis** uses `build_developer_message()` (loads the canonical pattern taxonomy file) as the `developer_message` parameter. This mirrors production, where the taxonomy is loaded from Airtable config — the eval loads from the file directly.
