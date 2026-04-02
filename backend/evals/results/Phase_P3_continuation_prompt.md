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
4. **Experiment history** (completed/parked experiments): so it understands the coachee's coaching journey

### What NOT to include

**Pattern score trendlines** were deliberately excluded. There is no evidence that experiment completion correlates with pattern score movement, and including scores could create artificial tension — pulling the LLM toward pattern-score-driven recommendations that conflict with theme-based coaching insights. Coaching themes should be the primary longitudinal signal.

### Current state of `_build_memory_for_user` (~line 1954 in workers.py)

Currently builds a `MemoryBlock` with:
- `baseline_profile`: `{ strengths: [...], baseline_pack_id: "..." }` (focus removed in P2)
- `active_experiment`: full experiment dict with related_patterns (or null)
- `recent_pattern_snapshots`: always `[]` — placeholder marked "Populated via future enhancement"

The `recent_pattern_snapshots` field was designed for this purpose but was never populated. This is the designated place for coachee history context.

### Design constraints

1. **Schema stability**: Whatever schema is chosen for the coachee context must be stable before coaching themes start accumulating in production, since those themes will be read back as historical context in future meetings.

2. **Data source**: Coaching themes and executive summaries live in each run's `Parsed JSON` field in Airtable. The context builder needs to fetch recent runs and extract these fields.

3. **Token budget**: The context document competes for tokens in the Stage 2 prompt. Keep it concise — summaries of themes, not full theme objects. Consider what the minimum viable context is that would meaningfully improve coaching quality.

4. **Experiment attempt history**: The active experiment's attempt events are already fetchable via `client.get_experiment_events()`. Consider including a compact summary (e.g., "3 meetings analyzed, 2 partial attempts, 1 full attempt").

5. **Prompt integration**: The Stage 2 prompt has `__EXPERIMENT_CONTEXT__` substitution already. The coachee context could extend this or use a new `__COACHEE_HISTORY__` substitution point.

### Key files to modify

| File | Purpose | What changes |
|---|---|---|
| `backend/core/workers.py` | `_build_memory_for_user` (~L1954) | Populate `recent_pattern_snapshots` (or richer equivalent) from recent runs |
| `backend/core/prompt_builder.py` | `build_memory_block`, `build_stage2_system_prompt` | Add coachee history to the memory block; inject into Stage 2 prompt |
| `backend/core/models.py` | `MemoryBlock` dataclass | May need new fields for coaching history |
| `system_prompt_coaching_v1.0.txt` | Stage 2 coaching prompt | Add substitution point for coachee history; add instructions for using longitudinal context |
| `system_prompt_next_experiment_v1.0.txt` | Next-experiment prompt | Already uses coaching themes; may benefit from experiment history context |

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
