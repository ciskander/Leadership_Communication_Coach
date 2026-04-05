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

After reviewing, summarize:
1. Does longitudinal context improve coaching quality? (A/B results)
2. Is the coaching arc coherent across meetings? (Series judge)
3. Are there systematic issues to fix? (Theme repetition, experiment stalling, detection failures)

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
