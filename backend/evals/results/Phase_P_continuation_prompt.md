# Phase P: Two-Stage Architecture Integration + Experiment-Pattern Decoupling

## How to use this document

This is a **planning** continuation prompt. Your job is to produce a detailed implementation plan for user approval before writing any code. Use plan mode. The plan should cover all changes described below, organized into implementation phases that can be reviewed and executed incrementally.

Read this document thoroughly before starting. It captures extensive context from prior eval work and architectural discussions. The user has been deeply involved in these decisions and will review your plan carefully.

---

## Project root

```
C:\Users\chris\Documents\Persollaneous\Business\Communication Coaching Tool\LLM Prompt to Build Python\Combined Project Files
```

Refer to `CLAUDE.md` in the project root for tech stack, project structure, and conventions.

---

## Background: What we learned from the eval cycle (Phases M through O)

### The eval infrastructure

We built a comprehensive eval pipeline across Phases M–O:
- **10 synthetic test transcripts** covering different meeting types, target roles, and coaching scenarios
- **50 runs per system** (10 meetings × 5 runs each) for statistical stability
- **Automated judge** (LLM-based) that evaluates coaching quality on multiple dimensions
- **Three systems compared**: Post-Editor (PE), Stage 2 v0.1 (S2v1), Stage 2 v0.2 (S2v2)

### Key findings

**Scoring is solid.** Pattern scores are stable across runs (median IQR < 0.05 for most patterns), discriminant across meetings (SNR > 5 for most patterns), and OE removals behave sensibly. Scoring is not the bottleneck.

**Coaching quality is decent but flat across all three prompt variants:**

| Metric | PE | S2v1 | S2v2 |
|---|---|---|---|
| Exec summary insightful | 56% | 64% | 62% |
| Coaching theme insightful | 49% | 54% | 54% |
| Themes add value (vs restate patterns) | 88% | 92% | 94% |
| Overall coaching value "high" | ~10% | ~10% | ~10% |
| Approve for delivery | 100% | 100% | 100% |
| Pattern-first detected (per-run) | 100% | 100% | 100% |

**The coaching is 100% approvable and never misleading, but only ~10% "high value."** Three different prompt arrangements produced essentially the same quality. This tells us prompt restructuring has hit diminishing returns for single-meeting coaching. All three systems are two-pass architectures (PE uses an editor 2nd call; S2v1/v2 use a dedicated coaching 2nd call), so the ceiling applies to two-pass as well as single-pass approaches.

**The LLM already exercises selectivity.** It skips coaching for 60–67% of pattern slots per run. Focus Management is skipped ~95% of the time, Question Quality ~85%. The LLM concentrates on the 3–4 patterns that matter for each meeting. The system is not blindly filling every slot.

**Coaching themes are the strongest part of the output.** They're where cross-pattern behavioral insights live. Per-pattern coaching notes are where pedantic ratings concentrate (especially QQ and RA). The sharpest coaching tends to touch multiple patterns.

**The most likely path to higher coaching value is longitudinal context** — giving the LLM awareness of the coachee's history across meetings, not just the current transcript. Single-meeting analysis has hit its ceiling.

### Decision: Start from Stage 2 v0.2 (S2v2) architecture

The two-stage architecture (scoring call → coaching call) is the right foundation because:
- **Separation of concerns**: Scoring (measurement) and coaching (interpretation) are distinct tasks with different input needs
- **The coaching call is where longitudinal context belongs** — the coachee's history, experiment progress, prior themes. Keeping this separate from scoring means the scoring call stays lean and stable.
- **Both calls change purpose.** Call 1 (currently scoring + coaching via `system_prompt_v0_4_0.txt`) gets pruned to scoring-only. Call 2 (currently the editor via `system_prompt_editor_v1.0.txt`) gets replaced by the Stage 2 coaching call. Both are 2-call architectures; this changes what both calls do.

For the Stage 1 (scoring) prompt, build from the existing `system_prompt_v0_4_0.txt` by stripping coaching instructions. Rename the result to `system_prompt_scoring_v1.0.txt`. For the Stage 2 (coaching) prompt, build from `system_prompt_stage2_v0.1.txt` (which contains the v0.2 "coaching-first" content despite the filename) — this is the most polished coaching prompt version. Rename the result to `system_prompt_coaching_v1.0.txt`. Keep the original files intact for reference; create new files with the new names.

---

## What needs to change

### 1. Integrate two-stage pipeline into the production app

**Current production pipeline** (in `backend/core/workers.py`, function `process_single_meeting_analysis`):
1. Build memory block + prompt → LLM Call 1 (scoring + coaching + experiment tracking, using `system_prompt_v0_4_0.txt` + `clearvoice_pattern_taxonomy_v3.1.txt`)
2. Post-LLM patches (`patch_analysis_output`)
3. Optional: Editor LLM Call 2 (`run_editor` in `editor.py`, using `system_prompt_editor_v1.0.txt`) → merge via `merge_editor_output`
4. Gate1 validation
5. Persist run + post-pass actions (experiment events, next-experiment suggestion)

**Target pipeline:**
1. Build prompt → **LLM Call 1: Scoring only** (no coaching fields in output)
2. Post-LLM patches (adapted for scoring-only output)
3. **Gate 1 validation** on scoring output (adapted schema — no coaching fields required)
4. Build coaching prompt with scoring output + transcript + coachee context → **LLM Call 2: Coaching** (using adapted S2v2 prompt)
5. **Merge** scoring + coaching into final output
6. **Gate 2 validation** on merged output (coaching fields validated)
7. Persist run + post-pass actions

**Key files to modify:**
- `backend/core/workers.py` — `process_single_meeting_analysis` function (~lines 463–741)
- `system_prompt_v0_4_0.txt` → create `system_prompt_scoring_v1.0.txt` by stripping coaching instructions, keeping scoring + evidence extraction.
- `system_prompt_stage2_v0.1.txt` → create `system_prompt_coaching_v1.0.txt` by adapting for production use. Needs to handle memory block, active experiment context, experiment tracking. This is the Stage 2 coaching prompt.
- `backend/core/editor.py` — `run_editor` and `merge_editor_output` become deprecated. The Stage 2 call replaces the editor. The OE removal logic in `merge_editor_output` (`_process_oe_removals`, `_recalculate_pattern_score`) may need to be preserved if OE removal stays in the pipeline.
- `backend/schemas/mvp_v0_5_0.json` — JSON schema needs updating for the new output structure
- `backend/core/gate1_validator.py` — Validation logic needs to handle the two-stage output (Gate 1 for scoring, Gate 2 for coaching)

**OE removal consideration:** In the current S2v2 eval pipeline, the Stage 2 LLM outputs an `oe_removals` array identifying over-extracted observations. The **merge code** (not the LLM) then processes these removals: deleting the flagged evidence spans, recalculating pattern scores, and updating evaluable status. This merge logic lives in `backend/evals/run_stage2.py` (which reuses `_process_oe_removals` and `_recalculate_pattern_score` from `editor.py`). The same merge logic needs to be replicated in the production pipeline.

**What the S2v2 eval pipeline does** (in `backend/evals/run_stage2.py`):
1. Takes a Stage 1 `run_*.json` file
2. Strips coaching fields via `strip_to_stage1.py` (keeps scoring + evidence)
3. Calls LLM with the stripped output + transcript + Stage 2 prompt
4. Merges: takes Stage 1 scoring, applies S2's OE removals and score recalculations, adds S2's coaching fields
5. Outputs `stage2_merged_*.json`

### 2. Decouple experiments from patterns

**Current state:**
- `Experiment` has a `pattern_id` field — each experiment targets exactly one pattern
- `Run.focus_pattern` — the LLM selects one pattern as the "focus area"
- `Run.micro_experiment_pattern` — the pattern for the proposed experiment
- `coaching.focus` in the output — a single-item array with `{pattern_id, message}`
- `coaching.micro_experiment` — includes `pattern_id`
- The LLM is biased to select a focus pattern consistent with the active experiment's pattern
- `process_next_experiment_suggestion` selects the next experiment by finding the lowest-scoring pattern (excluding parked/recently completed pattern IDs)

**Target state:**
- Experiments are **behavioral-change-first** objects: title, instruction, success criteria describe the behavioral change in coaching language, not pattern language
- Experiments may optionally list `related_patterns` (for measurement convenience), but this is informational, not a constraint
- `focus_area` concept is **deprecated** — coaching themes take over the per-meeting "what to work on" role
- The experiment is the **continuity anchor** across meetings, not a pattern

**Specific changes needed:**

#### Backend data model (Airtable fields — user makes these changes manually):
- `Experiment` table: `Pattern ID` field becomes optional or is replaced by `Related Patterns` (comma-separated list or JSON array)
- `Run` table: `Focus Pattern` field may become deprecated. `Micro Experiment Pattern` field becomes optional.
- New fields may be needed for coaching theme history

#### Backend code:
- `workers.py` — `instantiate_experiment_from_run`: Currently reads `micro_experiment[0].pattern_id`. Needs to handle experiments without a single pattern_id.
- `workers.py` — `process_next_experiment_suggestion` (~line 1373): Currently ranks patterns by average score and proposes experiments for the lowest-scoring ones. This needs fundamental redesign — experiments should be proposed based on **coaching theme history only**, not pattern scores. See constraint #7 below.
- `workers.py` — `_build_memory_for_user` (~line 1840): Currently passes `active_experiment.pattern_id` to the prompt. This needs to pass the experiment without pattern constraint.
- `workers.py` — `_build_memory_for_user`: Currently `recent_snapshots` is always empty (`[]`) with a comment "Populated via future enhancement". This is where coachee history context would be built.
- `prompt_builder.py` — `build_single_meeting_prompt`: The memory block structure needs updating to remove pattern-linked experiment/focus fields.

#### System prompts:
- Stage 1 (scoring) prompt: Remove all coaching-related instructions, focus/experiment selection logic, and experiment tracking. This call just scores patterns and extracts evidence. It should be **stateless** — same transcript produces the same scores regardless of who the coachee is or what experiment they're running.
- Stage 2 (coaching) prompt: This is where all coaching lives: `executive_summary`, `coaching_themes`, `strengths`, `pattern_coaching`, `micro_experiment`, `experiment_coaching`, and `experiment_tracking`. It also produces the `experiment_status_model` and `attempt_model` enum fields on the Run record (these are LLM-generated classifications related to experiment detection). It receives scores + transcript + coachee context (memory block with active experiment, baseline profile, and eventually coaching history).
- `system_prompt_next_experiment_v0_4_0.txt`: Needs redesign. Currently receives pattern scores and selects the lowest-scoring pattern to design an experiment around. Should instead receive **coaching theme history only** from recent meetings and design experiments based on recurring behavioral themes. Pattern scores should not be included — see constraint #7 below.

#### Frontend:
- `CoachingCard.tsx`: Currently shows `focus` section (rose-colored, single pattern). This needs to be removed or replaced with coaching themes display.
- `ExperimentTracker.tsx`: Currently displays experiment linked to a pattern. Needs to work with pattern-independent experiments.
- `RunStatusPoller.tsx`: Orchestrates the coaching display. Needs to handle the new output structure.
- `frontend/src/lib/types.ts`: Type definitions need updating (`RunStatus.focus`, `MicroExperiment.pattern_id`, etc.)
- `frontend/src/config/strings.ts`: UI strings for any new/changed sections
- Progress page (`client/progress/page.tsx`): May need updates if experiment tracking changes

**Coach role pages are NOT a priority** for this work.

### 3. Experiment tracking, detection, and continuity

(Note: focus_area deprecation is part of section 2 above — `coaching.focus` is removed from the schema, `Run.focus_pattern` is deprecated, and the focus section in `CoachingCard.tsx` is removed. Coaching themes replace focus_area for the per-meeting "what to work on" role; the active experiment replaces it for cross-meeting continuity.)

**Current behavior when a coachee submits a new meeting with an active experiment:**
- The LLM receives the active experiment (title, instruction, success_marker, pattern_id) via the memory block
- It checks whether the coachee attempted the experiment in this meeting
- It identifies evidence spans where attempts occurred (or were missed), classifies the attempt (yes/partial/no), counts attempts, and generates coaching feedback including `notes`, `coaching_note`, `suggested_rewrite`, and `rewrite_for_span_id`
- It outputs `experiment_tracking.detection_in_this_meeting` with the attempt classification, count, and evidence span references
- The system creates an `ExperimentEvent` record
- The coachee can confirm/deny the detection via the UI

**All experiment detection and coaching moves to Stage 2.** In the current `system_prompt_v0_4_0.txt`, there is logic for identifying experiment attempt moments in the transcript, creating OE-type entities that represent those attempts, counting them, and generating coaching on them. All of this logic needs to be ported to `system_prompt_coaching_v1.0.txt`.

**How this works in the two-stage architecture:**
- **Stage 1 (scoring)** extracts evidence spans for *pattern scoring* — these are observations of communication behaviors mapped to the 9 patterns. Stage 1 has no awareness of the active experiment.
- **Stage 2 (coaching)** receives Stage 1's scored output + transcript + the active experiment definition. It identifies which moments in the transcript relate to the experiment — these are **separate OE-type entities** from Stage 1's pattern evidence spans. They may reference the same transcript turns, but the interpretation is different ("this moment is an instance of pattern X" vs. "this moment is where the coachee tried their experiment"). Stage 2 counts these experiment-attempt entities, classifies the overall attempt (yes/partial/no), and generates coaching feedback on them (notes, coaching_note, suggested_rewrite, rewrite_for_span_id).

**Target behavior (beyond porting):**
- Same detection flow as above, but experiment is not pattern-constrained
- After each meeting, the coaching output should surface how the meeting relates to the active experiment AND whether new coaching themes suggest the coachee might benefit from a new experiment
- The coachee should be able to: **continue** the current experiment, **complete** it (mark as done), **park** it (save for later), or **abandon** it
- Complete, park, and abandon are all already implemented in the backend with UI support

**Experiment lifecycle with new themes:**
When the LLM's coaching themes surface insights that diverge from the active experiment's focus, the output should flag this for the coachee. The UI should present this as a choice, not an automatic switch. Something like: "Your current experiment is X. In this meeting, you showed improvement in [areas]. However, new coaching themes suggest [Y]. Would you like to continue with your current experiment, or explore a new direction?"

The exact UX for this is a design question that can be deferred to a later phase, but the coaching output schema needs to support it (e.g., a field that indicates whether the LLM sees a potential new experiment direction).

### 4. Coachee context document (future — design sketch only)

This is the biggest lever for improving coaching quality, but implementation is deferred to a later phase. The plan should **sketch the target design** so that the changes in phases 1–4 are compatible with it.

**What the coaching call (Stage 2) should eventually receive:**
- Active experiment (title, instruction, success criteria, attempt history)
- Prior 2–3 coaching themes (so the LLM avoids repeating itself and can build on prior observations)
- Prior executive summaries (so it can reference growth or persistent issues)

**Note on pattern scores:** Pattern score trendlines were considered as an input but deliberately excluded. There is no evidence that experiment completion correlates with pattern score movement, and including scores could create artificial tension — pulling the LLM toward pattern-score-driven recommendations that conflict with theme-based coaching insights. Coaching themes should be the primary longitudinal signal. Pattern scores can be added later if evidence emerges that they correlate with coaching progress.

**Current state of `_build_memory_for_user`** (~line 1840 in workers.py):
- Builds a `MemoryBlock` with baseline profile, active experiment, and `recent_snapshots=[]` (placeholder)
- The `recent_snapshots` field was designed for this purpose but never populated

**Design constraint:** Whatever schema is chosen for the coachee context document must be stable before coaching themes start accumulating in production, since those themes will be read back as historical context in future meetings.

### 5. Baseline pack considerations

The baseline pack currently works as:
- 3 separate LLM calls (one per transcript), each using `system_prompt_baseline_pack_v0_4_0.txt`
- A 4th LLM call for synthesis across the 3 analyses

In the new architecture, the baseline pack is a **cross-sectional multi-meeting view** — same fundamental challenge as the longitudinal context document, just at a single point in time. The baseline pack prompt and synthesis step may need similar updates (decoupling from pattern-centric focus selection, producing coaching themes instead of/in addition to per-pattern focus).

**For this planning phase:** Note the baseline pack as a downstream dependency but don't redesign it yet. Focus on the single-meeting pipeline first. The baseline pack can be updated in a subsequent phase once the single-meeting architecture is stable.

---

## Implementation phasing (suggested)

The user wants a plan organized into phases that can be reviewed and executed incrementally. Here's a suggested ordering, but refine this based on your codebase exploration:

**Phase P1: Integrate two-stage pipeline (backend only) — COMPLETE**

Merged to `main`. The two-stage pipeline is live in production. Key files created/modified:

- `system_prompt_scoring_v1.0.txt` — Stage 1 scoring-only prompt
- `system_prompt_coaching_v1.0.txt` — Stage 2 coaching prompt
- `backend/core/stage2_merge.py` — Merges Stage 1 scoring + Stage 2 coaching output (includes OE removal processing)
- `backend/core/workers.py` — `process_single_meeting_analysis` rewritten as two-call pipeline
- `backend/core/prompt_builder.py` — Added `build_stage2_system_prompt()`, `build_stage2_user_message()`, experiment context builder
- `backend/core/gate1_validator.py` — Added `scoring_only` validation mode for Stage 1; business rules skip coaching checks in scoring mode; auto-corrects `opportunity_count` and `score` when OE `count_decision` changes
- `backend/core/output_patches.py` — Added `scoring_only` flag to skip coaching-related patches
- `backend/core/config.py` — `EDITOR_ENABLED=False`
- `backend/schemas/mvp_v0_5_0.json` — Removed `maxLength` on evidence span `excerpt` (long excerpts are allowed; validator warns at 2500 chars)

Airtable field changes already applied by user:
- Run table: Added "Stage 2 Raw Output" (Long text), "Scoring Valid" (Checkbox)
- Run table: Renamed "Editor Changelog" → "Stage 2 Changelog", "Editor Tokens" → "Stage 2 Tokens"

Bugs fixed during smoke testing:
- Dockerfile needed new prompt files added to COPY
- Scoring-only validation was still running coaching business rule checks against empty dicts
- `micro_experiment` variable unbound in scoring-only path
- Airtable field constants needed updating for renamed fields
- Missing `count_decision` on OEs now defaults to `"counted"` in sanitiser, with arithmetic auto-correction
- Strengths with score < 0.70 now flagged as `STRENGTH_LOW_SCORE` warning; self-audit check added to coaching prompt

**Phase P2: Decouple experiments from patterns + deprecate focus_area**
- Update experiment data model (Airtable field changes → user does manually, code changes → Claude)
- Update coaching output schema (drop `focus`, make experiment `pattern_id` optional)
- Update frontend components (remove focus section, update experiment display)
- Update `process_next_experiment_suggestion` to use coaching themes instead of pattern scores
- **Test:** End-to-end flow works with pattern-independent experiments

**Phase P3: Coachee context document (design + implement)**
- Populate `recent_snapshots` (or a richer equivalent) in `_build_memory_for_user`
- Include coaching theme history and prior executive summaries
- Update Stage 2 prompt to use the context document
- **Test:** Eval suite comparison — does longitudinal context improve "high value" rate?

**Phase P4: Baseline pack alignment (if needed)**
- Update baseline pack to use the new architecture
- Align with the single-meeting pipeline changes

---

## Key files reference

### Backend — Pipeline & orchestration
| File | Purpose | Key functions |
|---|---|---|
| `backend/core/workers.py` | Main pipeline orchestration | `process_single_meeting_analysis` (~L463), `instantiate_experiment_from_run` (~L1160), `create_attempt_event_from_run` (~L1239), `process_next_experiment_suggestion` (~L1373), `_build_memory_for_user` (~L1840) |
| `backend/core/editor.py` | Editor (2nd LLM call in PE) — to be deprecated | `run_editor` (~L137), `merge_editor_output` (~L175), `_process_oe_removals`, `_recalculate_pattern_score` |
| `backend/core/prompt_builder.py` | Prompt construction | `build_single_meeting_prompt` (~L226), `build_developer_message` |
| `backend/core/openai_client.py` | LLM call interface | `call_llm`, `load_system_prompt` |
| `backend/core/gate1_validator.py` | Output validation | Uses `mvp_v0_5_0.json` schema |
| `backend/core/config.py` | Configuration | `PATTERN_ORDER`, `MVP_SCHEMA_PATH`, `EDITOR_ENABLED` |
| `backend/core/models.py` | Dataclass models | `RunRequest`, `Run`, `Experiment`, `ExperimentEvent`, `MemoryBlock` |

### Backend — API routes
| File | Purpose |
|---|---|
| `backend/api/routes_coachee.py` | Coachee endpoints (submit analysis, get summary) |
| `backend/api/routes_runs.py` | Run detail endpoints |
| `backend/api/routes_experiments.py` | Experiment CRUD + lifecycle (activate, complete, park, abandon) |
| `backend/api/routes_transcripts.py` | Transcript upload |
| `backend/api/dto.py` | API data transfer objects |

### System prompts
| File | Purpose | Status in new architecture |
|---|---|---|
| `system_prompt_v0_4_0.txt` | Main analysis prompt (scoring + coaching) | Source for new `system_prompt_scoring_v1.0.txt` — strip coaching, keep scoring |
| `system_prompt_stage2_v0.1.txt` | Stage 2 coaching prompt (eval-only, contains v0.2 content) | Source for new `system_prompt_coaching_v1.0.txt` — adapt for production |
| `system_prompt_editor_v1.0.txt` | Editor prompt | **Deprecate** — replaced by Stage 2 |
| `system_prompt_next_experiment_v0_4_0.txt` | Next-experiment proposal prompt | **Redesign** — use coaching themes instead of pattern scores |
| `system_prompt_baseline_pack_v0_4_0.txt` | Baseline pack analysis prompt | **Defer** — update in Phase P4 |
| `clearvoice_pattern_taxonomy_v3.1.txt` | Pattern taxonomy — single source of truth | **Keep** — used by Stage 1 scoring (full taxonomy as developer message) and Stage 2 coaching (relevant sections extracted programmatically). The separate `stage2_pattern_definitions_v0.1.txt` should be replaced by programmatic extraction from this canonical file to prevent version drift. |

### Validation & schemas
| File | Purpose |
|---|---|
| `backend/schemas/mvp_v0_5_0.json` | JSON schema for LLM output validation |

### Frontend — Components
| File | Purpose | Impact |
|---|---|---|
| `frontend/src/components/CoachingCard.tsx` | Main coaching display | Remove focus section, update experiment display |
| `frontend/src/components/PatternSnapshot.tsx` | Per-pattern scoring display | Minor or no changes |
| `frontend/src/components/ExperimentTracker.tsx` | Active experiment tracking | Decouple from pattern |
| `frontend/src/components/RunStatusPoller.tsx` | Run detail orchestrator | Handle new output structure |
| `frontend/src/lib/types.ts` | TypeScript type definitions | Update for schema changes |
| `frontend/src/config/strings.ts` | UI strings | Add/update strings |

### Frontend — Pages
| File | Purpose |
|---|---|
| `frontend/src/app/client/page.tsx` | Coachee dashboard |
| `frontend/src/app/client/runs/[id]/page.tsx` | Run detail page |
| `frontend/src/app/client/experiment/page.tsx` | Experiment selection |
| `frontend/src/app/client/progress/page.tsx` | Progress tracking |

### Eval infrastructure (DO NOT MODIFY — for reference only)
| File | Purpose |
|---|---|
| `backend/evals/run_stage2.py` | Stage 2 eval runner — reference implementation for production integration |
| `backend/evals/strip_to_stage1.py` | Strips coaching from run files — shows what Stage 1 output looks like |
| `backend/evals/judge_eval.py` | Judge for eval runs |
| `backend/evals/results/Phase_O_stage2/` | S2v2 eval results (50 runs) |
| `backend/evals/results/Phase_O_stage2_batch2/` | S2v2 eval results (50 runs) |

---

## Important constraints and notes

1. **Airtable stays as the data store** for now. The user makes Airtable schema changes manually — your plan should specify what field changes are needed, and the user will execute them.

2. **Production contracts first, then update eval scripts.** Define the input/output contracts for the production scoring and coaching calls first. Then update the eval scripts (`backend/evals/run_stage2.py`, etc.) to match the production input format. The goal is one `system_prompt_coaching_v1.0.txt` that works in both contexts because both contexts format their inputs the same way.

3. **Coach role pages are not a priority.** Focus on the coachee experience.

4. **The baseline pack is a downstream dependency.** Note it in the plan but don't redesign it. Phase P4 can handle it once the single-meeting pipeline is stable.

5. **Experiment lifecycle statuses (complete, park, abandon) are all already implemented** in the backend with UI support.

6. **`recent_snapshots` in `_build_memory_for_user` is currently always `[]`** with a comment "Populated via future enhancement." This is the designated place for coachee history context.

7. **The `process_next_experiment_suggestion` function** currently selects experiments based on lowest-scoring patterns and passes pattern coaching notes as context. In the new architecture, it should use **coaching theme history as the primary input** for experiment design. Pattern scores should not drive experiment selection — there is no evidence that experiment completion correlates with pattern score movement, and including scores could create artificial tension with theme-based insights.

8. **The eval infrastructure (judge, synthesis, compare scripts) should not be modified** as part of this work. It's stable and will be used to test the new architecture once implemented.

9. **Single source of truth for pattern taxonomy.** The canonical taxonomy file is `clearvoice_pattern_taxonomy_v3.1.txt`. The codebase already has logic in several places that parses this file and extracts specific sections for different purposes (e.g., the next-experiment prompt extracts experiment guidance sections). This pattern should be maintained — rather than maintaining separate, thinner taxonomy documents for different stages (like the current `stage2_pattern_definitions_v0.1.txt`), the Stage 2 coaching prompt should extract what it needs from the canonical taxonomy file programmatically. This prevents version drift across multiple taxonomy documents.

10. **The editor should be fully disabled and deprecated.** The `EDITOR_ENABLED` flag in `backend/core/config.py` controls whether the editor runs. The editor (`backend/core/editor.py`'s `run_editor` function and `system_prompt_editor_v1.0.txt`) is replaced by the Stage 2 coaching call. Set `EDITOR_ENABLED = False` and remove the editor call path from `process_single_meeting_analysis`. The OE removal and score recalculation logic in `editor.py` (`_process_oe_removals`, `_recalculate_pattern_score`) may still be needed by the Stage 2 merge step — preserve these utility functions even if the editor itself is deprecated.
