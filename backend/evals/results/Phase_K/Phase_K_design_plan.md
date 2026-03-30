# Phase J: Coaching Editor — Implementation Plan

## Context

After 5 phases of taxonomy optimization (G→I2), pedantic coaching rate plateaued at ~10.5%. The remaining pedantic falls into categories taxonomy rules can't fix: pattern overlap, context-blind evaluation, and judge variance. The editor is a 2nd LLM call that reviews the 1st call's coaching output from an executive coach's perspective — without the taxonomy — and can suppress, rewrite, or improve coaching before delivery.

**Baseline to beat (Phase I2):** 40.2% insightful, 10.5% pedantic, 0.3% wrong (296 ratings, 7 meetings)

**Target:** Pedantic → ~5-7%, Insightful holds ≥ 40%, Wrong stays 0%

---

## Key Design Decisions (all confirmed)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Output format | **Delta-based** — editor returns only what it changed; null = unchanged |
| 2 | Editor scope | Pattern coaching + executive_summary + coaching_themes + strengths messages + focus message + micro_experiment text + experiment_coaching text |
| 3 | Focus/experiment text | **Text rewording only** — editor can sharpen wording of `focus.message`, `micro_experiment.title/instruction/success_marker`, but CANNOT change pattern_ids, the continue/transition decision, or experiment structure |
| 4 | OE removal cascade | If removals demote a pattern to `insufficient_signal`, **discard all coaching** for that pattern |
| 5 | Eval parity | **Extract shared post-processing function** from workers.py so replay_eval applies same patches before editor |
| 6 | Changelog storage | **Separate Airtable field** on Run record (`F_RUN_EDITOR_CHANGELOG`) |
| 7 | Pipeline position | After all post-processing + ASR cleanup (line ~696), before Gate1 (line ~705) |
| 8 | Model | Same model as 1st call (no cost-saving downgrade) |
| 9 | No taxonomy | Editor does NOT receive the pattern taxonomy |

---

## Editor Output Format (Delta-Based)

```json
{
  "executive_summary": "<new text, or null if unchanged>",
  "coaching_themes": ["<new array>", "or null if unchanged"],
  "strengths_edits": {
    "<pattern_id>": { "message": "<new text>" }
  },
  "focus_message": "<new text, or null if unchanged>",
  "micro_experiment_edits": {
    "title": "<new or null>",
    "instruction": "<new or null>",
    "success_marker": "<new or null>"
  },
  "pattern_coaching_edits": {
    "<pattern_id>": {
      "notes": "<new positive observation, or null if unchanged>",
      "coaching_note": "<new, or null to SUPPRESS>",
      "suggested_rewrite": "<new or null>",
      "rewrite_for_span_id": "<changed span or null>",
      "best_success_span_id": "<changed span or null>"
    }
  },
  "experiment_coaching_edits": {
    "coaching_note": "<new or null>",
    "suggested_rewrite": "<new or null>",
    "rewrite_for_span_id": "<new or null>"
  },
  "oe_removals": [
    { "pattern_id": "<str>", "oe_index": "<0-based int>", "reason": "<str>" }
  ],
  "changes": [
    { "field": "<str>", "action": "suppressed|rewritten|changed|removed|unchanged", "reason": "<str>" }
  ]
}
```

**Suppression convention**: When editor sets `coaching_note` to the string `"SUPPRESS"`, the merge step nulls out `coaching_note`, `suggested_rewrite`, and `rewrite_for_span_id` for that pattern. Omitted patterns (not in `pattern_coaching_edits`) are left unchanged.

---

## Implementation Steps

### Step 1: Extract shared post-processing → `backend/core/output_patches.py` (NEW)

Extract the post-LLM-call patching logic from `workers.py` lines 590-696 into a reusable function so both workers.py and replay_eval.py apply identical patches.

**Function:**
```python
def patch_analysis_output(
    parsed_output: dict,
    prompt_meta: dict,               # from prompt_payload.meta
    active_experiment: dict | None,   # from memory.active_experiment
    has_active_experiment: bool,       # whether active_exp_record_id exists
    cleanup_enabled: bool = False,
) -> dict:
```

**What moves into this function:**
- Meta field injection (lines 590-593)
- Experiment tracking detection coercion (lines 595-620)
- Micro-experiment evidence_span_ids backfill (lines 622-626)
- Coaching defaults (lines 628-630)
- Focus override safety gate (lines 632-656) — needs `has_active_experiment` + `active_experiment`
- Rewrite span migration (lines 658-675)
- `_patch_parsed_output()` call (line 677) — move this function too, or call it from here
- ASR quote cleanup (lines 682-686, conditional on `cleanup_enabled`)

**workers.py changes:** Replace lines 590-696 with a single call to `patch_analysis_output()`, then reconstruct `openai_resp`.

**replay_eval.py changes:** Call `patch_analysis_output()` after `call_llm()`, before editor/Gate1.

**Files:**
- `backend/core/output_patches.py` — **CREATE**
- `backend/core/workers.py` lines 590-696 — **MODIFY** (replace with function call)
- `backend/evals/replay_eval.py` `run_single_analysis()` — **MODIFY** (add patch call)

---

### Step 2: Create `backend/core/editor.py` (NEW)

**Constants:**
- `EDITOR_SYSTEM_PROMPT` — the editor system prompt with `{experiment_context}` placeholder

**Functions:**

1. `build_experiment_context(memory: MemoryBlock, parsed_output: dict) -> str`
   - Returns the read-only experiment context string based on active experiment state
   - Three cases: no experiment, active+continue, active+transition

2. `build_editor_user_message(parsed_output: dict, transcript_turns: list[dict]) -> str`
   - Assembles: transcript turns JSON + full analysis JSON
   - Format: clear section headers so the editor can reference both

3. `run_editor(parsed_output: dict, transcript_turns: list[dict], experiment_context: str, model: str | None = None) -> tuple[dict, int, int]`
   - Formats system prompt with experiment context
   - Calls `call_llm()` with editor system prompt (no developer_message / no taxonomy)
   - Returns `(editor_output_dict, prompt_tokens, completion_tokens)`

4. `merge_editor_output(original: dict, editor_output: dict) -> tuple[dict, list[dict]]`
   - Returns `(merged_output, changelog)`
   - **Processing order** (critical):
     1. **OE removals** — remove flagged OEs from `opportunity_events`, recalculate pattern scores (`sum(success_value of remaining counted OEs) / count`), update `opportunity_count` in `pattern_snapshot`
     2. **Status check** — if remaining counted OEs < `min_required_threshold`, set `evaluable_status` to `insufficient_signal`, null out `score`
     3. **Coaching discard for demoted patterns** — if pattern became `insufficient_signal`, null out `coaching_note`, `suggested_rewrite`, `rewrite_for_span_id`, `best_success_span_id`, `notes` for that pattern; skip any editor edits for it
     4. **Apply coaching text edits** — for each pattern in `pattern_coaching_edits`, apply non-null fields; handle `"SUPPRESS"` convention for coaching_note
     5. **Apply span reference changes** — validate `best_success_span_id` exists in `success_evidence_span_ids`; validate `rewrite_for_span_id` exists in `evidence_span_ids` (non-success). If `rewrite_for_span_id` changed but `suggested_rewrite` didn't change → revert both to original
     6. **Apply top-level text edits** — `executive_summary`, `coaching_themes`, `strengths_edits`, `focus_message`, `micro_experiment_edits`, `experiment_coaching_edits` (non-null fields only)
   - All edits are applied to a deep copy of `original`

**Editor system prompt:** Based on the draft in Phase_J_editor_design_plan.md, with these adjustments:
- Updated "YOUR EDITORIAL TOOLS" section to describe delta-based output format
- Added scope for focus_message, micro_experiment text, experiment_coaching text (text rewording only)
- Added explicit instruction: omit patterns from `pattern_coaching_edits` if no changes needed
- Added JSON schema specification at the end for the delta output format

---

### Step 3: Add config flag

**`backend/core/workers.py`** (following `_CLEANUP_ENABLED` pattern at line 99-101):
```python
_EDITOR_ENABLED = _os.getenv("EDITOR_ENABLED", "0") == "1"
```

**`backend/core/airtable_client.py`** — add field constants:
```python
F_RUN_EDITOR_CHANGELOG = "Editor Changelog"
F_RUN_EDITOR_TOKENS = "Editor Tokens"
```

**Airtable**: Create `Editor Changelog` (long text) and `Editor Tokens` (number) fields on the Runs table. Create `Editor Enabled` (checkbox) field on the Config table.

---

### Step 4: Modify `backend/core/workers.py` — insert editor call

**Location:** After line 696 (post openai_resp reconstruction), before line 704 (Gate1).

```python
# ── Editor pass (optional) ──
editor_changelog = None
if _EDITOR_ENABLED:
    from backend.core.editor import (
        build_experiment_context, run_editor, merge_editor_output,
    )
    exp_context = build_experiment_context(memory, _parsed_output)
    transcript_turns = prompt_payload.transcript_payload["turns"]
    editor_result, ed_prompt_tokens, ed_completion_tokens = run_editor(
        _parsed_output, transcript_turns, exp_context, model=openai_resp.model,
    )
    _parsed_output, editor_changelog = merge_editor_output(
        _parsed_output, editor_result,
    )
    # Reconstruct openai_resp with editor-merged output
    patched_raw = _json.dumps(_parsed_output, ensure_ascii=False, indent=2)
    openai_resp = OpenAIResponse(
        parsed=_parsed_output, raw_text=patched_raw,
        model=openai_resp.model,
        prompt_tokens=openai_resp.prompt_tokens,
        completion_tokens=openai_resp.completion_tokens,
        total_tokens=openai_resp.total_tokens,
    )
    logger.info("Editor: %d prompt tokens, %d completion tokens, %d changes",
                ed_prompt_tokens, ed_completion_tokens, len(editor_changelog))
```

**In `_persist_run_fields()`** — add optional `editor_changelog` parameter:
```python
if editor_changelog:
    fields[F_RUN_EDITOR_CHANGELOG] = _safe_json_dumps(editor_changelog)
    fields[F_RUN_EDITOR_TOKENS] = ed_prompt_tokens + ed_completion_tokens
```

---

### Step 5: Modify `backend/evals/replay_eval.py`

In `run_single_analysis()` (line 205), after `call_llm()` (line 238) and before `gate1_validate()` (line 241):

1. Call `patch_analysis_output()` on `response.parsed` (the new shared function from Step 1)
2. Check `EDITOR_ENABLED` env var
3. If enabled, call `run_editor()` → `merge_editor_output()`
4. Serialize merged output as raw_text for Gate1
5. Track editor token usage in the returned dict (add `editor_prompt_tokens`, `editor_completion_tokens`, `editor_changes_count` fields)

---

### Step 6: Create `backend/tests/test_editor.py` (NEW)

**Test categories:**

1. **Delta merge basics**
   - Null field in editor output → original preserved
   - Non-null field → original replaced
   - Pattern not in `pattern_coaching_edits` → completely unchanged
   - `"SUPPRESS"` coaching_note → nulls coaching_note + suggested_rewrite + rewrite_for_span_id

2. **OE removal + score recalculation**
   - Remove 1 of 3 OEs → score = sum(remaining) / 2
   - Remove all OEs → pattern becomes `insufficient_signal`, score = null
   - Remove enough to drop below min_required_threshold → `insufficient_signal`
   - Only `counted` OEs factor into recalculation

3. **Coaching discard for demoted patterns**
   - Pattern demoted to `insufficient_signal` → all coaching fields nulled
   - Editor's coaching edits for demoted patterns are discarded

4. **Span reference validation**
   - `best_success_span_id` must be in `success_evidence_span_ids` → revert if invalid
   - `rewrite_for_span_id` must be in `evidence_span_ids` (non-success) → revert if invalid
   - Changed `rewrite_for_span_id` without changed `suggested_rewrite` → revert both

5. **Top-level text edits**
   - `executive_summary` replacement
   - `coaching_themes` replacement
   - `strengths_edits` — message text only, pattern_id preserved
   - `focus_message` — text only, structure preserved
   - `micro_experiment_edits` — text fields only
   - `experiment_coaching_edits` — text fields only

6. **Edge cases**
   - Editor returns empty dict → original unchanged
   - Editor returns unknown pattern_id in edits → ignored
   - Editor returns invalid JSON → graceful failure, original preserved

---

## File Summary

| File | Action | What |
|------|--------|------|
| `backend/core/output_patches.py` | **CREATE** | Shared post-processing patches (extracted from workers.py) |
| `backend/core/editor.py` | **CREATE** | Editor prompt, LLM call, delta merge logic |
| `backend/tests/test_editor.py` | **CREATE** | Unit tests for merge logic and edge cases |
| `backend/core/workers.py` | **MODIFY** | Replace inline patches with shared function call; insert editor step before Gate1; add changelog to persist |
| `backend/core/airtable_client.py` | **MODIFY** | Add `F_RUN_EDITOR_CHANGELOG`, `F_RUN_EDITOR_TOKENS` constants |
| `backend/evals/replay_eval.py` | **MODIFY** | Add shared patches + editor call in `run_single_analysis()` |

---

## Bug Fix: Airtable "Editor Enabled" flag not wired up

**Problem**: Line 622 in `workers.py` only checks the `_EDITOR_ENABLED` env var (line 105). The Airtable `Editor Enabled` checkbox is never read, so the editor never runs in production even when the flag is checked in Airtable.

**Root cause**: The env var pattern (`_EDITOR_ENABLED = _os.getenv(...)`) was added for eval scripts. The Airtable config read was mentioned in the plan but not implemented.

**Fix** (`backend/core/workers.py`):
1. Initialize `cfg_fields = {}` before the `if config_links:` block (around line 507) so it's always in scope
2. Change line 622 from:
   ```python
   if _EDITOR_ENABLED:
   ```
   to:
   ```python
   if _EDITOR_ENABLED or cfg_fields.get("Editor Enabled"):
   ```

This follows the existing pattern where env vars provide eval/dev overrides and Airtable config controls production behavior.

---

## Phase J1 Eval Results & Analysis

### Results vs Phase I2 baseline

| Metric | I2 Baseline | Phase J | Delta |
|--------|----------:|--------:|------:|
| Insightful | 40.2% | 42.0% | +1.8pp |
| **Pedantic** | **10.5%** | **12.3%** | **+1.8pp** |
| Wrong | 0.3% | 0.3% | +0.0pp |

**Pedantic went UP, not down.** The editor is not achieving its goal.

### Root cause analysis

**Problem 1: Editor rewrites when it should suppress (the big one)**

The editor made 0-1 suppressions per analysis and 10-17 rewrites. It's acting as a copy editor, not a quality gate. The pedantic patterns it should be killing are:

| Pattern × Meeting | Ped rate | Judge says | Editor did |
|-------------------|---------|------------|------------|
| TC in M-000001 | 4/5 | "Repackages FM moment under second label" | Suppressed coaching_note but `notes` field survived |
| PM in M-000004 | 4/5 | "Taxonomy-filling — too thin to count" | **Rewrote** instead of suppressing |
| TC in M-000006 | 4/4 | Similar pattern overlap | Likely rewrote |
| PM in M-000003 | 3/5 | "Stretching to fill a category" | Likely rewrote |
| AC in M-000005 | 4/5 | Thin coaching on feedback meeting | Likely rewrote |

**Problem 2: `notes` field survives suppression**

When the editor suppresses `coaching_note` (sets to null), the `notes` field (positive observation) still exists. In M-000001, the TC `notes` says "You built credibility at the end by not pretending you could do justice to the Vantage issue..." — the judge sees this and rates the TC coaching as pedantic because the observation is really about focus management, not trust.

The editor can suppress coaching_note but has no mechanism to suppress the `notes` field independently.

**Problem 3: Editor prompt lacks pattern-overlap detection guidance**

The editor prompt says to suppress when coaching is "redundant — another pattern's coaching already makes the same point more specifically." But it doesn't give the editor enough guidance to detect when a pattern's entire coaching (notes + coaching_note) is really about a different pattern. The judge can detect this ("repackages FM under TC label") but the editor misses it.

### Root cause: editor lacks the judge's pattern-alignment lens

Comparing the two prompts reveals the core gap:

**The judge** has a dedicated `coaching_pattern_alignment` evaluation section that asks per-pattern:
- `fits_pattern`: Does this coaching genuinely fit this behavioral pattern?
- `better_pattern`: If not, which pattern would be more natural?
- `stretching_to_fill`: Is the system stretching to populate a category?

This structured alignment check is exactly what catches "TC is really FM" (M-000001) and "PM is taxonomy-filling" (M-000004). It forces the judge to reason about *whether each pattern belongs* before rating quality.

**The editor** has no equivalent. It evaluates coaching text quality (vague? generic? actionable?) but never asks "does this pattern's coaching actually describe behavior that belongs to this pattern, or is it describing another pattern's domain?" Without this lens, the editor sees TC coaching about "deferring the Vantage issue" and thinks "this is decent coaching text, let me rewrite it sharper" — missing that the entire observation is FM relabeled as TC.

**Additionally**: The `notes` field (positive observation) and `coaching_note` are independent — a pattern can have great notes but weak coaching_note, or vice versa. The editor should evaluate each field on its own merits, including whether the `notes` content genuinely demonstrates that specific pattern or is stretching.

### Proposed fixes for Phase J1

**1. Add pattern-alignment reasoning to the editor prompt**

Add a structured pre-editing step that mirrors the judge's alignment check. Before deciding to rewrite or suppress, the editor should ask per-pattern:
- "Does this pattern's coaching (both notes AND coaching_note) describe behavior that genuinely belongs to this specific behavioral domain?"
- "Or is it describing behavior that's really about a different pattern (e.g., TC observation that's really FM behavior)?"
- "Is the system stretching to populate this category with thin evidence?"

If the answer is "doesn't belong" or "stretching to fill", the editor should suppress the specific field(s) that don't belong — `notes` if the positive observation is misaligned, `coaching_note` if the developmental feedback is misaligned, or both if the whole pattern is off-base.

**2. Allow independent suppression of `notes`**

Currently the editor can only suppress `coaching_note` (via "SUPPRESS"). Add the ability to independently suppress `notes` by setting it to `"SUPPRESS"` as well. The merge step should handle:
- `coaching_note: "SUPPRESS"` → nulls coaching_note + suggested_rewrite + rewrite_for_span_id (existing behavior)
- `notes: "SUPPRESS"` → nulls notes (new)
- Both can be set independently

**3. Strengthen the suppression examples in the prompt**

Add concrete examples that match the judge's findings:
- "A trust_and_credibility observation about deferring a topic to a future meeting — that's really focus_management, not trust-building. Suppress the notes."
- "A participation_management observation about calling on someone by name once — if that's the only evidence and the rest of the meeting showed poor participation, the category is being filled. Suppress."

**4. Add explicit "this is your most impactful tool" framing for suppression**

The editor prompt currently lists suppression first but most guidance is about rewriting. Rebalance: "Your highest-impact editorial decision is whether each pattern's coaching *belongs*. A leader with 6 well-targeted coaching points learns more than one with 9 where 3 are about the wrong thing."

**5. Provide pattern descriptions to both editor and judge**

Neither the editor nor the judge receives any taxonomy definitions — they evaluate based purely on pattern names and intuition. This is why the judge sometimes gets alignment right and sometimes doesn't, and why the editor almost never catches it.

**What to include** (from the taxonomy, per pattern):
- "What it measures" (1-2 sentence purpose statement)
- "Excluded from numerator AND denominator" (what this pattern is NOT about)
- The disambiguation notes where patterns overlap (e.g., TC vs DN, PM vs QQ)

**What NOT to include**:
- Scoring rubric tiers (0.0-1.0 definitions) — these drive pattern-filling behavior
- Detection notes and opportunity counting rules — these are for the 1st call only
- Role notes and denominator rules — irrelevant to coaching quality assessment

This gives both the editor and judge a grounded understanding of what each pattern *means* so they can identify when coaching is about the wrong pattern, without teaching them how to score.

**Implementation**: Create a `pattern_definitions_for_review.txt` extracted from the taxonomy (or build it dynamically in `editor.py`). Provide it to the editor as a "PATTERN DEFINITIONS" section in the system prompt. Optionally update the judge prompt too.

### Files to modify

| File | Change |
|------|--------|
| `backend/core/editor.py` | EDITOR_SYSTEM_PROMPT: add pattern-alignment reasoning step, pattern definitions reference, independent notes suppression, stronger suppression guidance with examples |
| `backend/core/editor.py` | Add `PATTERN_DEFINITIONS` constant extracted from taxonomy (what-it-measures + exclusions + disambiguation) |
| `backend/core/editor.py` | `_apply_pattern_coaching_edits()`: handle `notes: "SUPPRESS"` → null out notes |
| `backend/core/editor.py` | Output format: document that `notes` can also be set to `"SUPPRESS"` |
| `backend/evals/judge_eval.py` | **Deferred** — judge prompt unchanged for now to preserve Phase I2 baseline comparison validity |

---

## Phase J1 Hotspot Re-run Findings

Targeted re-run on 4 hotspot transcripts (M-000001, M-000003, M-000004, M-000006) with 3 runs each revealed **two distinct causes** for remaining pedantic:

### Issue A: Ghost patterns in judge formatter (mechanical fix)
When both `notes` and `coaching_note` are null after editor suppression, the judge formatter (`_format_pattern_coaching` in `judge_eval.py` line 264) still renders:
- The `#### pattern_id` heading
- Success evidence quotes from `pattern_snapshot.success_evidence_span_ids`

The judge sees an empty pattern with just orphaned quotes and correctly rates it as taxonomy-filling. The `_cleanup_fully_suppressed` fix nulled `best_success_span_id` but the formatter shows ALL success spans, not just the best one.

**Fix**: `backend/evals/judge_eval.py` line 264 — skip patterns where both `notes` and `coaching_note` are null. The judge should evaluate what the user actually sees.

### Issue B: Inconsistent editor suppression of notes (prompt tuning)
In M-000004 run_001, the editor suppressed `coaching_note` for PM but left `notes` ("You made a strong inclusion move when you brought Quinn in"). The judge rated the notes itself as pedantic — calling on one person once isn't meaningful PM. The editor's alignment step should catch this but doesn't always.

This is LLM judgment variance, not a code bug. The prompt already instructs independent evaluation of notes and coaching_note. Further prompt tuning may help but diminishing returns apply.

---

## Phase K: Variance Decomposition — Editor & Judge Consistency Tests

### Context

The pipeline now has 3 layers of LLM calls: 1st pass → editor → judge. We've measured end-to-end variance extensively (replay_eval repeat mode) but never isolated whether the editor or judge introduces their own noise. Before investing in taxonomy changes to fix OE stability or SNR issues, we need to know which layer the noise comes from.

Key motivating observations:
- PM SNR dropped from 18.5 → 3.2 after adding the editor — is this the editor flipping randomly on borderline PM cases, or consistently removing real signal?
- CC has avg OE range 3.9 — is this 1st-pass variance, or does the editor's OE removal add variance on top?
- Our entire measurement system (judge) has never been tested for self-consistency

### Test Design

**Editor variance test**: Take a fixed 1st-pass output (`run_*.json`), run the editor N times on it, compare the N delta outputs for consistency.

**Judge variance test**: Take a fixed post-editor output (`run_*.json`), run the judge N times on it, compare the N judge ratings for consistency.

Both tests hold the input constant and vary only the target layer's LLM call.

### Implementation

**New file: `backend/evals/variance_eval.py`**

Two modes via `--mode editor` and `--mode judge`.

#### Editor variance mode

```
python -m backend.evals.variance_eval --mode editor \
  --input <pre-editor run_*.json> \
  --transcript <transcript file> \
  --runs 10
```

**Input requirement**: The `--input` file must be a **pre-editor** 1st-pass output (generated with `EDITOR_ENABLED=0`).

Steps:
1. Load the fixed `run_*.json` as `parsed_output`
2. Load and parse the transcript to get `transcript_turns`
3. Build experiment context via `build_experiment_context()` (using default no-experiment memory)
4. Call `run_editor()` N times on the same input
5. Save each editor delta output as `editor_var_{i:03d}_{timestamp}.json`
6. Compare the N deltas:
   - Per-pattern: did the editor suppress/rewrite/pass consistently?
   - Field-level agreement rate (what % of decisions are identical across all N runs?)
   - Focus on PM, TC, FM, DN — the patterns where editor decisions matter most
7. Print a consistency report

**Key functions to reuse:**
- `run_editor()` from `backend/core/editor.py`
- `build_experiment_context()` from `backend/core/editor.py`
- `merge_editor_output()` from `backend/core/editor.py` (to see the downstream impact of each delta)
- `load_raw_transcript()` / `load_transcript_for_judge()` for transcript loading
- `save_json()`, `save_report()` from `backend/evals/report.py`

**Consistency metrics to report:**

Per-pattern:
- Action distribution: how many runs suppressed / rewrote / passed each pattern's `notes` and `coaching_note`
- Unanimous rate: % of patterns where all N runs made the same action decision
- Flip patterns: which patterns had mixed decisions (e.g., suppressed in 3/5, rewrote in 2/5)

Per-field:
- `executive_summary`: changed in N/N runs? (expect high — editor almost always rewrites this)
- `coaching_themes`: changed in N/N?
- `oe_removals`: which OEs flagged in how many runs? Agreement rate.

Overall:
- Total changes per run (min/max/mean) — how variable is the editor's activity level?

#### Judge variance mode

```
python -m backend.evals.variance_eval --mode judge \
  --input <post-editor run_*.json> \
  --transcript <transcript file> \
  --runs 10
```

**Input requirement**: The `--input` file must be a **post-editor** output (the standard `run_*.json` files from a `EDITOR_ENABLED=1` eval run).

Steps:
1. Load the fixed `run_*.json` as `parsed_json`
2. Load transcript via `load_transcript_for_judge()`
3. Call `judge_analysis()` N times on the same input
4. Save each judge output as `judge_var_{i:03d}_{timestamp}.json`
5. Compare the N judge outputs:
   - Per-pattern rating distribution (insightful/adequate/pedantic/wrong)
   - Pattern-level agreement rate
   - Which patterns flip between ratings?
6. Print a consistency report

**Key functions to reuse:**
- `judge_analysis()` from `backend/evals/judge_eval.py`
- `load_transcript_for_judge()` from `backend/evals/judge_eval.py`
- `save_json()`, `save_report()` from `backend/evals/report.py`

**Consistency metrics to report:**

Per-pattern:
- Rating distribution across N runs (e.g., "TC: 3 insightful, 2 adequate, 0 pedantic")
- Unanimous rate: % of patterns where all N runs gave the same rating
- Flip patterns: which patterns had mixed ratings

Aggregate:
- Mean ± stddev of insightful%, adequate%, pedantic% across runs
- Overall coaching value distribution (high/medium/low)
- Would-approve-for-delivery agreement rate

#### Output directory

Results saved to `backend/evals/results/variance_tests/{input_file_stem}/`:
- `editor_var_*.json` or `judge_var_*.json` — raw outputs
- `variance_report_{timestamp}.md` — formatted consistency report
- `variance_report_{timestamp}.json` — machine-readable stats

### Test inputs to use

Selected based on actual editor activity and flip patterns from Phase J2:

**Important**: The `run_*.json` files in the results directory are **post-editor** outputs. The editor variance test needs pre-editor input; the judge variance test needs post-editor input.

**All 3 target meetings get both editor and judge variance tests.**

**Editor variance inputs** (need pre-editor 1st-pass outputs):
- Generate by running `EDITOR_ENABLED=0 python -m backend.evals.replay_eval --mode repeat --runs 1` for each target transcript
- Save the output to `backend/evals/results/variance_tests/pre_editor/`
- The variance_eval script then runs the editor 10 times on this fixed pre-editor output

**Judge variance inputs** (use existing post-editor outputs):
- Use a `run_001_*.json` from the current Phase J2 results — these are already post-editor
- Specific file selection happens at Step 3 (after reviewing editor results)
- The variance_eval script runs the judge 10 times on this fixed post-editor output

**Why these 3 meetings:**
1. **M-000004** (avoider) — 3 editor flip patterns (PF, TC, CC), highest pedantic rate (19.4%), PM SNR degradation hotspot, QQ 4/4 pedantic
2. **M-000002** (weak facilitator) — 2 editor flip patterns (RA, AC), highest editor activity (8.6 avg changes)
3. **M-000001** (strong facilitator) — DN 3/5 pedantic, AC 2/5 — boundary cases for judge consistency

### Files to create/modify

| File | Action |
|------|--------|
| `backend/evals/variance_eval.py` | **CREATE** — new eval script with editor and judge variance modes |

No modifications to existing files needed — this is a new standalone eval tool.

### Running the tests

**Target meetings** (all 3 get both editor and judge variance tests):
1. **M-000004** (avoider) — most editor flips, highest pedantic rate
2. **M-000002** (weak facilitator) — most editor activity, RA/AC flips
3. **M-000001** (strong facilitator) — DN pedantic boundary cases

**Step 1: Generate 3 pre-editor inputs** — 3 LLM calls in parallel (~2 min):
```bash
EDITOR_ENABLED=0 python -m backend.evals.replay_eval --mode repeat \
  --transcript backend/evals/transcripts/M-000001_strong_facilitator.txt --runs 1
EDITOR_ENABLED=0 python -m backend.evals.replay_eval --mode repeat \
  --transcript backend/evals/transcripts/M-000002_weak_facilitator.txt --runs 1
EDITOR_ENABLED=0 python -m backend.evals.replay_eval --mode repeat \
  --transcript backend/evals/transcripts/M-000004_avoider.txt --runs 1
```
Copy the resulting `run_001_*.json` files to `backend/evals/results/variance_tests/pre_editor/`.

**Step 2: Run 3 editor variance tests** — 30 LLM calls (10 per meeting), max 10 concurrent:
```bash
python -m backend.evals.variance_eval --mode editor \
  --input backend/evals/results/variance_tests/pre_editor/M-000001_run_001.json \
  --transcript backend/evals/transcripts/M-000001_strong_facilitator.txt --runs 10

python -m backend.evals.variance_eval --mode editor \
  --input backend/evals/results/variance_tests/pre_editor/M-000002_run_001.json \
  --transcript backend/evals/transcripts/M-000002_weak_facilitator.txt --runs 10

python -m backend.evals.variance_eval --mode editor \
  --input backend/evals/results/variance_tests/pre_editor/M-000004_run_001.json \
  --transcript backend/evals/transcripts/M-000004_avoider.txt --runs 10
```

**Step 3: Pause and review editor results** — inspect the 3 editor variance reports. Based on the findings, strategically select which post-editor `run_*.json` files to use as judge variance inputs.

**Step 4: Run 3 judge variance tests** — 30 LLM calls (10 per meeting), max 10 concurrent:
```bash
python -m backend.evals.variance_eval --mode judge \
  --input backend/evals/results/M-000001_strong_facilitator/run_001_<timestamp>.json \
  --transcript backend/evals/transcripts/M-000001_strong_facilitator.txt --runs 10

python -m backend.evals.variance_eval --mode judge \
  --input backend/evals/results/M-000002_weak_facilitator/run_001_<timestamp>.json \
  --transcript backend/evals/transcripts/M-000002_weak_facilitator.txt --runs 10

python -m backend.evals.variance_eval --mode judge \
  --input backend/evals/results/M-000004_avoider/run_001_<timestamp>.json \
  --transcript backend/evals/transcripts/M-000004_avoider.txt --runs 10
```

**Note on input format**: `variance_eval.py` calls `run_editor()` and `judge_analysis()` directly — it loads the `run_*.json` file and passes its contents to the target function. It does NOT go through `replay_eval.py`'s pipeline. The `--input` flag accepts a path to any analysis output JSON file.

### What we learn from the results

| Finding | Implication |
|---------|------------|
| Editor flips on PM/TC suppression | Editor prompt needs stronger decision criteria for borderline patterns |
| Editor is consistent | PM SNR drop is a real effect of consistent (but possibly wrong) editorial choices — fix the prompt's PM guidance |
| Judge flips between adequate/pedantic | Our pedantic % has an error bar — quote it as a range, and consider judge prompt improvements |
| Judge is consistent | Our measurements are reliable — focus optimization on the pipeline, not the ruler |
| Both are consistent | All variance comes from Layer 1 (1st pass) — focus entirely on taxonomy/prompt changes |

---

## Continuation Prompt for Next Session

See `backend/evals/results/Phase_K_continuation_prompt.md`.

---

## Verification Plan

1. **Smoke test** — run `variance_eval.py` in each mode with `--runs 1` on one meeting to verify it runs end-to-end and produces valid output files
2. **Full run** — execute all 6 variance tests (3 meetings × 2 modes × 10 runs) as described in "Running the tests" above
3. **Report review** — check the consistency reports for:
   - Editor: per-pattern unanimous rate, flip patterns, change count variance
   - Judge: per-pattern rating agreement, insightful/pedantic flip rate
4. **Interpret results** — use the "What we learn from the results" table to determine next steps (taxonomy changes vs prompt tuning vs accepting current variance)
