# Phase P3: Coachee Context Document — Continuation Prompt

## How to use this document

This is a **planning** continuation prompt. Your job is to produce a detailed implementation plan for user approval before writing any code. Use plan mode. The plan should cover all changes described below, organized into implementation phases that can be reviewed and executed incrementally.

Read this document thoroughly before starting. It captures extensive context from prior work and architectural decisions. The user has been deeply involved in these decisions and will review your plan carefully.

---

## Project root

```
C:\Users\chris\Documents\Persollaneous\Business\Communication Coaching Tool\LLM Prompt to Build Python\Combined Project Files
```

Refer to `CLAUDE.md` in the project root for tech stack, project structure, and conventions.

---

## What's been completed

### Phase P1: Two-stage pipeline (COMPLETE — merged to main)

The production pipeline now uses two LLM calls:
1. **Stage 1 (scoring)**: `system_prompt_scoring_v1.0.txt` — extracts evidence, scores patterns. Stateless.
2. **Stage 2 (coaching)**: `system_prompt_coaching_v1.0.txt` — generates coaching themes, executive summary, strengths, micro_experiment, pattern coaching, experiment tracking/detection.

Key files: `workers.py` (pipeline orchestration), `prompt_builder.py` (prompt construction), `stage2_merge.py` (merges scoring + coaching), `gate1_validator.py` (validation with `scoring_only` mode for Stage 1), `output_patches.py` (post-LLM deterministic fixes).

### Phase P2: Decouple experiments from patterns + deprecate focus_area (COMPLETE — merged to main)

Work was done on `claude/practical-ptolemy` branch and merged to `main`.

Experiments are now behavioral-change-first objects. Key changes:

**Schema (v0.6.0):**
- `coaching.focus` removed entirely — coaching themes replace it as the "what to work on" signal
- `micro_experiment.pattern_id` replaced with `related_patterns: string[]` (0-N patterns)
- Evidence span IDs accept both `ES-T` (pattern scoring) and `EXD-T` (experiment detection) prefixes

**Backend:**
- `process_next_experiment_suggestion` fully rewritten: uses coaching theme history + executive summaries instead of pattern scores. New prompt: `system_prompt_next_experiment_v1.0.txt`. Outputs `related_patterns` and optional `journey_summary`.
- `instantiate_experiment_from_run`: takes first micro_experiment (no focus matching). Writes `Related Patterns` field, `Pattern ID` left empty.
- `_build_memory_for_user`: reads `Related Patterns` from Airtable with fallback to legacy `Pattern ID`. Passes `related_patterns` array in experiment context. No longer reads/passes `focus_pattern`.
- `output_patches`: runs twice — once on Stage 1 (scoring_only=True, no cleanup), once on merged output (scoring_only=False, no cleanup). Quote cleanup runs separately after merge.
- `stage2_merge`: appends experiment detection evidence spans (EXD- prefix) from Stage 2 to the merged `evidence_spans` array.
- Gate1 sanitiser: strips leftover scoring fields from insufficient_signal/not_evaluable patterns (safety net for OE removal demotion).

**Frontend:**
- `CoachingCard`: focus section conditionally renders for backward compat with old runs
- Coaching themes: rendered above CoachingCard with rose styling (eye icon, primary/secondary badges)
- All experiment displays use `related_patterns` with `pattern_id` fallback
- Progress page: "Experiment Patterns" view replaces "Focus Pattern Only", supports multiple patterns, caps at 5 total
- `RunStatusPoller`: accepts proposed experiments and transitions to ExperimentSection with amber styling; no flash on refresh (gated by `expCheckDone`)

**Airtable fields (already applied by user):**
- Experiment table: `Related Patterns` (Long text — JSON array), `Journey Summary` (Long text)
- Run table: `Stage 2 Raw Output`, `Scoring Valid`, renamed editor fields to Stage 2

**Bugs fixed during P2:**
- Dockerfile must include all new prompt .txt files (missed twice — P1 and P2)
- Schema version in scoring prompt must match schema file version
- OE removal demotion must pop `score` key (not set to None) and clear `evidence_span_ids`/`success_evidence_span_ids` for schema compliance
- `output_patches` coaching steps (2-6) weren't running on merged output
- Quote cleanup moved from Stage 1 to after merge (runs once on final output including experiment detection spans)
- Experiment display flash on refresh eliminated via `expCheckDone` gate

---

## What needs to be done: Phase P3 — Coachee Context Document

### Goal

Give the Stage 2 coaching call awareness of the coachee's history across meetings. Currently, each meeting is analyzed in isolation — the coaching LLM sees only the current transcript and scores. The most likely path to higher coaching value is longitudinal context.

### What the coaching call (Stage 2) should receive

The coachee context document provides:
1. **Active experiment** (already implemented): title, instruction, success criteria, related_patterns, attempt history
2. **Prior coaching themes** (2-3 recent meetings): so the LLM avoids repeating itself and can build on prior observations
3. **Prior executive summaries** (2-3 recent meetings): so it can reference growth or persistent issues
4. **Experiment history** (completed/parked experiments with journey summaries): so it understands the coachee's coaching journey

### What NOT to include

**Pattern score trendlines** were deliberately excluded. There is no evidence that experiment completion correlates with pattern score movement, and including scores could create artificial tension — pulling the LLM toward pattern-score-driven recommendations that conflict with theme-based coaching insights. Coaching themes should be the primary longitudinal signal.

### Existing code that already fetches this data

`process_next_experiment_suggestion` (~line 1560 in `workers.py`) already fetches and formats coaching themes, executive summaries, and experiment progress from recent runs. The data-fetching logic extracts from each run's `Parsed JSON` field:
- `coaching.coaching_themes` → list of `{theme, explanation, priority, related_patterns}`
- `coaching.executive_summary` → string
- `experiment_tracking.detection_in_this_meeting` → `{attempt, count_attempts}`
- `coaching.experiment_coaching.coaching_note` → string

This logic should be **extracted into a shared helper** and reused by `_build_memory_for_user`, not duplicated. The formatting (how the context is serialized into prompt text) may differ between the two use cases.

### Current state of `_build_memory_for_user` (~line 1954 in workers.py)

Currently builds a `MemoryBlock` with:
- `baseline_profile`: `{ strengths: [...], baseline_pack_id: "..." }` (focus removed in P2)
- `active_experiment`: full experiment dict with related_patterns (or null)
- `recent_pattern_snapshots`: always `[]` — placeholder marked "Populated via future enhancement"

The `recent_pattern_snapshots` field name is misleading — it suggests pattern data, but the intent was always to hold coaching history context. Either rename it (e.g., `coaching_history`) or add a new field alongside it. The plan should propose a concrete field name and shape.

### Design questions to address in the plan

1. **How many meetings of history?** The prompt says "2-3 recent meetings" but the plan should propose a specific number (or make it configurable). Consider: too few limits context; too many risks the LLM fixating on stale details.

2. **Data shape in the MemoryBlock**: What does the new field look like? Suggestion to consider:
   ```python
   coaching_history: list[dict] = []
   # Each entry: {
   #   "meeting_date": "2026-03-15",
   #   "executive_summary": "...",
   #   "coaching_themes": [{"theme": "...", "explanation": "...", "priority": "..."}],
   # }
   ```

3. **How to serialize into the prompt**: Should the context be formatted as a structured block (like the experiment context), prose summary, or JSON? The experiment context uses a labeled text block with `===` headers. The same approach would be consistent.

4. **Prompt instructions for the LLM**: The Stage 2 prompt needs instructions telling the LLM *how* to use the history. Key behaviors:
   - Build on prior themes, don't repeat them verbatim
   - Reference growth or persistent issues when writing the executive summary
   - Note when a coaching theme from a prior meeting reappears (or resolves)
   - Do NOT let prior context override what's actually observed in this transcript

5. **Prompt integration point**: The Stage 2 prompt has `__EXPERIMENT_CONTEXT__` substitution. The coachee history should use a new `__COACHEE_HISTORY__` substitution — separate concerns, since experiment context is conditional but coachee history is always present (even if empty).

6. **Experiment history shape**: Completed/parked experiments have these fields in Airtable: `Title`, `Instructions`, `Success Criteria`, `Status`, `Journey Summary`, `Related Patterns`, `Started At`, `Ended At`. The `Journey Summary` field (added in P2) is a coach's retrospective generated by the next-experiment prompt. Include title, status, related_patterns, and journey_summary for each past experiment (most recent 3-5).

7. **Active experiment attempt history**: The active experiment's attempt events are fetchable via `client.get_experiment_events()`. Include a compact summary in the context (e.g., "3 meetings analyzed: 1 full attempt, 2 partial attempts"). This data is already available in the experiment context block — consider enriching it rather than duplicating in the history block.

### Curation quality over token-stinginess

The context document should provide enough information for the LLM to see the coaching trajectory and avoid repetition. Include the full coaching themes (theme + explanation + priority) and full executive summaries — these are already concise (themes are 1-3 items per meeting, exec summaries are max 1200 chars). Don't summarize them further; let the LLM see the actual prior output so it can meaningfully build on it.

Think of it as a coach's working notes from the last few sessions — enough to walk into the room prepared, not a database export.

### Key files to modify

| File | Purpose | What changes |
|---|---|---|
| `backend/core/workers.py` | `_build_memory_for_user` (~L1954) | Fetch recent runs, extract coaching themes + exec summaries + experiment history; populate new MemoryBlock field. Extract shared data-fetching logic from `process_next_experiment_suggestion` into a reusable helper. |
| `backend/core/prompt_builder.py` | `build_memory_block` (~L631), `build_stage2_system_prompt` (~L270) | Accept new coaching history data in `build_memory_block`; add new `__COACHEE_HISTORY__` substitution builder; inject into Stage 2 prompt |
| `backend/core/models.py` | `MemoryBlock` dataclass | Add new field for coaching history (e.g., `coaching_history: list[dict]`). Consider renaming or deprecating `recent_pattern_snapshots`. |
| `system_prompt_coaching_v1.0.txt` | Stage 2 coaching prompt | Add `__COACHEE_HISTORY__` substitution point; add instructions for using longitudinal context (build on prior themes, reference growth, don't repeat) |

### Testing strategy

1. **Unit tests**: Test the shared data-fetching helper — given mock run records with `Parsed JSON`, verify correct extraction of themes, summaries, and experiment progress. Test the prompt builder's history serialization.
2. **Smoke test in production**: Run a single meeting analysis for a coachee with 3+ prior runs. Inspect the Stage 2 system prompt (logged in worker output) to verify the coachee history block is present and well-formatted. Verify the coaching output references or builds on prior themes.
3. **Eval comparison** (future): Once stable, use the eval suite to compare coaching quality with vs. without longitudinal context. This is a separate effort — don't block P3 on it.

### Important: Eval infrastructure

The eval infrastructure (`backend/evals/`) should NOT be modified. It's stable and will be used to test whether longitudinal context improves coaching quality after implementation.

### Downstream: Baseline pack (Phase P4)

The baseline pack is a cross-sectional multi-meeting view — same fundamental challenge as the longitudinal context document, just at a single point in time. Note it as a dependency but don't redesign it in P3. Phase P4 can handle it once the single-meeting pipeline is stable with longitudinal context.

---

## Key files reference

### Backend — Pipeline & orchestration
| File | Purpose | Key functions |
|---|---|---|
| `backend/core/workers.py` | Main pipeline orchestration | `process_single_meeting_analysis` (~L463), `instantiate_experiment_from_run` (~L1239), `create_attempt_event_from_run` (~L1317), `process_next_experiment_suggestion` (~L1451), `_build_memory_for_user` (~L1954) |
| `backend/core/prompt_builder.py` | Prompt construction | `build_stage2_system_prompt` (~L270), `_build_experiment_context_for_stage2` (~L300), `build_stage2_user_message` (~L352), `build_memory_block` (~L631) |
| `backend/core/stage2_merge.py` | Merges Stage 1 scoring + Stage 2 coaching | `merge_stage2_output` |
| `backend/core/gate1_validator.py` | Output validation | `validate()` with `scoring_only` mode |
| `backend/core/output_patches.py` | Post-LLM deterministic fixes | `patch_analysis_output` — runs on both Stage 1 (scoring_only) and merged output |
| `backend/core/models.py` | Dataclass models | `MemoryBlock`, `Run`, `Experiment` |
| `backend/core/config.py` | Configuration | `SCHEMA_VERSION`, `MVP_SCHEMA_PATH` |

### System prompts
| File | Purpose |
|---|---|
| `system_prompt_scoring_v1.0.txt` | Stage 1 scoring-only prompt |
| `system_prompt_coaching_v1.0.txt` | Stage 2 coaching prompt (has `__PATTERN_DEFINITIONS__` and `__EXPERIMENT_CONTEXT__` substitutions) |
| `system_prompt_next_experiment_v1.0.txt` | Next-experiment proposal prompt (coaching-theme-driven) |
| `system_prompt_baseline_pack_v0_4_0.txt` | Baseline pack analysis prompt (defer to P4) |
| `clearvoice_pattern_taxonomy_v3.1.txt` | Pattern taxonomy — single source of truth |

### Schemas
| File | Purpose |
|---|---|
| `backend/schemas/mvp_v0_6_0.json` | Current JSON schema (v0.6.0) — coaching.focus removed, micro_experiment uses related_patterns, EXD- span IDs supported |

### Frontend (for reference — P3 is primarily backend)
| File | Purpose |
|---|---|
| `frontend/src/components/RunStatusPoller.tsx` | Run detail orchestrator — shows coaching themes, experiment section |
| `frontend/src/components/CoachingCard.tsx` | Coaching display (strengths, micro_experiment) |
| `frontend/src/app/client/progress/page.tsx` | Progress tracking with pattern trends |

### Eval infrastructure (DO NOT MODIFY)
| File | Purpose |
|---|---|
| `backend/evals/run_stage2.py` | Stage 2 eval runner |
| `backend/evals/judge_eval.py` | Judge for eval runs |

---

## Important constraints

1. **Airtable stays as the data store.** The user makes Airtable schema changes manually — specify what field changes are needed.

2. **Coach role pages are not a priority.** Focus on the coachee experience.

3. **The baseline pack is a downstream dependency.** Note it but don't redesign it.

4. **The eval infrastructure should not be modified.**

5. **Single source of truth for pattern taxonomy.** `clearvoice_pattern_taxonomy_v3.1.txt` is canonical.

6. **Any new system prompt .txt files must be added to `Dockerfile.backend` COPY instructions.** This has been missed in prior phases — always verify.

7. **Pattern scores should NOT drive experiment selection or coaching.** Coaching themes are the primary longitudinal signal. This was a deliberate architectural decision — see the background section in the original continuation prompt at `backend/evals/results/Phase_P_continuation_prompt.md` for the full rationale.
