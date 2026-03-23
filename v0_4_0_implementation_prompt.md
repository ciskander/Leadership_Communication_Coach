# Implementation Task: Reasoning-Aligned Schema & Prompt Restructure (v0.3.0 → v0.4.0)

## What you are doing

You are restructuring the LLM output schema and system prompts for a leadership communication coaching app. The current v0.3.0 schema causes span-ID bookkeeping errors because the JSON output order doesn't match how the LLM naturally reasons. You are creating v0.4.0 which aligns the serialization order with the reasoning sequence.

**Primary LLM provider is GPT-5.4** (OpenAI), secondary is Claude (Anthropic). Both providers use the same system prompt content. GPT-5.4 has no extended thinking — the JSON output order IS the only mechanism guiding its reasoning. This restructure is most impactful for GPT-5.4.

**No backwards compatibility needed** — this is development mode. Airtable can be wiped. No version dispatch.

## The Core Change

**Before (v0.3.0)**: `pattern_snapshot` contains EVERYTHING per pattern (OEs, scores, coaching notes, rewrites, evidence_span_ids), and `evidence_spans` (the actual excerpts) comes LAST. The LLM writes rewrites + span ID references thousands of tokens before it serializes the evidence. Span IDs are arbitrary (ES-001, ES-002).

**After (v0.4.0)**: Output order follows reasoning order:
1. `opportunity_events` (top-level, all patterns) — identify transcript moments
2. `evidence_spans` (with turn-anchored IDs like ES-T051) — quote the turns
3. `pattern_snapshot` (scoring only, no coaching fields) — compute scores
4. `experiment_tracking` (detection only, no coaching) — did they attempt it?
5. `coaching` (all coaching in one section) — notes, rewrites, strengths, focus, experiment coaching

By the time the LLM writes coaching/rewrites, all evidence and scoring is already serialized.

## New v0.4.0 Schema Structure

```json
{
  "schema_version": "mvp.v0.4.0",
  "meta": { "analysis_id", "analysis_type", "generated_at", "taxonomy_version", "output_mode", "schema_hash" },
  "context": { "meeting_id", "meeting_type", "target_role", "meeting_date", "target_speaker_name", "target_speaker_label" },

  "opportunity_events": [
    {
      "event_id": "OE-001",
      "pattern_id": "purposeful_framing",
      "turn_start_id": 1,
      "turn_end_id": 3,
      "target_control": "yes|no|unclear",
      "count_decision": "counted|excluded",
      "success": 0.0|0.25|0.5|0.75|0.8|1.0,
      "reason_code": "snake_case_string",
      "notes": "optional string"
    }
  ],

  "evidence_spans": [
    {
      "evidence_span_id": "ES-T001-003",
      "turn_start_id": 1,
      "turn_end_id": 3,
      "excerpt": "verbatim transcript excerpt",
      "event_ids": ["OE-001"],
      "meeting_id": "optional, required for baseline_pack",
      "speaker_role": "chair|presenter|participant|manager_1to1|report_1to1|null"
    }
  ],

  "evaluation_summary": {
    "patterns_evaluated": ["purposeful_framing", ...],
    "patterns_insufficient_signal": [],
    "patterns_not_evaluable": []
  },

  "pattern_snapshot": [
    {
      "pattern_id": "purposeful_framing",
      "cluster_id": "meeting_structure",
      "scoring_type": "dual_element",
      "evaluable_status": "evaluable|insufficient_signal|not_evaluable",
      "denominator_rule_id": "string",
      "min_required_threshold": 1,
      "score": 0.75,
      "opportunity_count": 4,
      "element_a_count": 3,
      "element_b_count": 2,
      "evidence_span_ids": ["ES-T001-003", "ES-T010-011", "ES-T038"],
      "success_evidence_span_ids": ["ES-T001-003", "ES-T010-011"],
      "balance_assessment": "only for participation_management: over_indexed|balanced|under_indexed|unclear"
    }
  ],

  "experiment_tracking": {
    "active_experiment": { "experiment_id": "EXP-000001", "status": "none|proposed|active|completed|abandoned" },
    "detection_in_this_meeting": {
      "experiment_id": "EXP-000001",
      "attempt": "yes|partial|no",
      "count_attempts": 1,
      "evidence_span_ids": ["ES-T094"]
    } | null
  },

  "coaching": {
    "executive_summary": "string",
    "strengths": [{ "pattern_id": "string", "message": "string" }],
    "focus": [{ "pattern_id": "string", "message": "string" }],
    "micro_experiment": [{
      "experiment_id": "string",
      "title": "string",
      "instruction": "string",
      "success_marker": "string",
      "pattern_id": "string",
      "evidence_span_ids": ["ES-T025"]
    }],
    "pattern_coaching": [
      {
        "pattern_id": "purposeful_framing",
        "notes": "observational notes about this pattern",
        "coaching_note": "what was missed and why it matters",
        "suggested_rewrite": "concrete reworded version",
        "rewrite_for_span_id": "ES-T038"
      }
    ],
    "experiment_coaching": {
      "coaching_note": "for partial attempts only",
      "suggested_rewrite": "concrete reworded version",
      "rewrite_for_span_id": "ES-T094"
    } | null
  }
}
```

### Key design decisions

- **Turn-anchored evidence span IDs**: `ES-T{start}` for single turn, `ES-T{start}-{end}` for multi-turn. Regex: `^ES-T[0-9]+-?[0-9]*$`. Self-documenting, eliminates arbitrary ID tracking.
- **Shared spans**: If two patterns reference the same turns, they share ONE evidence span. The span's `event_ids` lists both OEs. No duplicate excerpts, no ID collisions.
- **OEs at top level**: All OEs across all patterns in one array (with `pattern_id` on each). Moved out of pattern_snapshot.
- **pattern_snapshot is scoring only**: No `notes`, `coaching_note`, `suggested_rewrite`, `rewrite_for_span_id`, or `opportunity_events` nested inside. Just scoring fields.
- **Coaching unified**: `coaching_output` renamed to `coaching`. All coaching text — pattern coaching, experiment coaching, strengths, focus, micro_experiment, executive_summary — lives here.
- **Experiment detection split from experiment coaching**: `experiment_tracking.detection_in_this_meeting` has observational fields only (attempt, count, evidence). Coaching fields (coaching_note, suggested_rewrite, rewrite_for_span_id) moved to `coaching.experiment_coaching`.
- **9 patterns** in required order: purposeful_framing, focus_management, participation_management, disagreement_navigation, resolution_and_alignment, assignment_clarity, question_quality, communication_clarity, feedback_quality
- **5 scoring types**: dual_element, tiered_rubric, binary, complexity_tiered, multi_element

## Files to Modify (in order)

### Phase 1: Schema
1. **CREATE** `backend/schemas/mvp_v0_4_0.json` — Full JSON Schema definition for the structure above. Base it on `backend/schemas/mvp_v0_3_0.json` but restructured. This is the ground truth.
2. **EDIT** `backend/core/config.py` — Update `MVP_SCHEMA_PATH` (or equivalent) to point to v0.4.0.

### Phase 2: System Prompts (3 files)
3. **CREATE** `system_prompt_v0_4_0.txt` — Based on `system_prompt_v0_3_0.txt`. Major changes:
   - Reorder prompt sections to match output sequence (OEs → evidence spans → pattern scoring → experiment detection → coaching)
   - Add new REASONING SEQUENCE section (see below)
   - Update all schema references from v0.3.0 to v0.4.0
   - Split the current "2-LAYER SCORING TRACE" section — OE definition becomes its own top-level section
   - Simplify PATTERN SNAPSHOT section (scoring only)
   - Create new COACHING section combining what was in coaching_output + pattern_snapshot coaching fields + experiment_tracking coaching fields
   - Update EVIDENCE SPANS section with turn-anchored ID format and `event_ids` field
   - Use provider-neutral language: "Before generating JSON output" not "In your thinking"

4. **CREATE** `system_prompt_baseline_pack_v0_4_0.txt` — Based on `system_prompt_baseline_pack_v0_3_0.txt`. Lighter changes: no OEs in baseline output, but same structural reorder. Check what it references and update accordingly.

5. **CREATE** `system_prompt_next_experiment_v0_4_0.txt` — Based on `system_prompt_next_experiment_v0_3_0.txt`. Check if it references the analysis schema structure; update if so.

### Phase 3: Prompt Builder & LLM Clients
6. **EDIT** `backend/core/prompt_builder.py`:
   - Update `_HARD_REMINDERS` for v0.4.0 structure
   - Update `_BASELINE_HARD_REMINDERS` for v0.4.0
   - Update user message text: `mvp.v0.3.0` → `mvp.v0.4.0` in both `build_single_meeting_prompt` and `build_baseline_pack_prompt`

7. **EDIT** `backend/core/openai_client.py`:
   - `load_system_prompt()` line 146: `system_prompt_v0_3_0.txt` → `system_prompt_v0_4_0.txt`
   - `load_baseline_system_prompt()` line 156: `system_prompt_baseline_pack_v0_3_0.txt` → `system_prompt_baseline_pack_v0_4_0.txt`
   - `load_next_experiment_system_prompt()` line 170: `system_prompt_next_experiment_v0_3_0.txt` → `system_prompt_next_experiment_v0_4_0.txt`

### Phase 4: Test Fixtures
8. **EDIT** `backend/tests/conftest.py` — Update `VALID_SINGLE_MEETING_OUTPUT` fixture to v0.4.0 structure. This is critical — all validator and worker tests depend on it.

### Phase 5: Validator
9. **EDIT** `backend/core/gate1_validator.py`:
   - OE validation moves from inside pattern_snapshot loop to top-level `opportunity_events` array
   - Pattern_snapshot validation simplified — no coaching fields to check
   - New `coaching` section validation: pattern_coaching array, experiment_coaching, rewrite_for_span_id checks
   - Update ES ID regex from `^ES-[0-9]{3}$` to `^ES-T[0-9]+-?[0-9]*$`
   - Retain all existing auto-corrections: score arithmetic, success list rebuild, content mismatch detection
   - Update success_evidence_span_ids rebuild to work with new structure (OEs are now top-level, not nested)
   - Rewrite validation moves from pattern_snapshot context to coaching.pattern_coaching context

### Phase 6: Workers
10. **EDIT** `backend/core/workers.py`:
    - `_patch_parsed_output()`: update for new field locations (coaching fields now in `coaching.pattern_coaching`, not `pattern_snapshot`)
    - `_enriched_output()`: update evidence span enrichment, coaching extraction for new structure
    - Rewrite fixups: update to work with `coaching.pattern_coaching[].rewrite_for_span_id` and `coaching.experiment_coaching.rewrite_for_span_id`
    - `_extract_coaching_from_run()`: extract from `coaching` not `coaching_output`
    - Airtable field mappings: update field extraction paths

### Phase 7: API Layer
11. **EDIT** `backend/api/dto.py` — Update Pydantic response models:
    - Add `PatternCoaching` model (pattern_id, notes, coaching_note, suggested_rewrite, rewrite_for_span_id)
    - Add `ExperimentCoaching` model
    - Update `RunStatusResponse` to use new `coaching` structure instead of `coaching_output`
    - PatternSnapshotItem loses coaching fields (notes, coaching_note, suggested_rewrite, rewrite_for_span_id)

### Phase 8: Frontend
12. **EDIT** `frontend/src/lib/types.ts` — Update TypeScript interfaces to match new schema
13. **EDIT** `frontend/src/components/RunStatusPoller.tsx` — Update field access paths
14. **EDIT** `frontend/src/components/PatternSnapshot.tsx` — Pattern data now scoring-only; coaching comes from `coaching.pattern_coaching`
15. **EDIT** `frontend/src/components/CoachingCard.tsx` — Update coaching field paths

### Phase 9: Scripts
16. **EDIT** `scripts/view_analysis.py` — Update JSON field paths
17. **EDIT** `scripts/pattern_scoring_diagnostics.py` — Update field paths

## REASONING SEQUENCE (new prompt section to add)

Add this section to the system prompt:

```
═══════════════════════════════════════════════════════════════
REASONING SEQUENCE
═══════════════════════════════════════════════════════════════

Follow this sequence. Complete each step before starting the next.

Step 1 — Holistic impression (before generating JSON output):
Read the full transcript. Form a clear picture of this speaker as a communicator.
Identify their genuine strengths and the single highest-leverage gap.
If an active experiment exists, note where the speaker attempted it.

Step 2 — Opportunity event identification (output: opportunity_events):
Scan the transcript for moments matching each pattern's denominator definition.
For each moment: record turn range, assess target_control, decide counted/excluded.
Score each counted OE per its pattern's rubric. Work through all 9 patterns.

Step 3 — Cross-pattern overlap resolution (still in opportunity_events):
Check if any turns are counted under multiple patterns.
Apply Pattern Priority Rules from the taxonomy to resolve overlaps.
Remove the weaker-fit OE from the contested turns.

Step 4 — Evidence spans (output: evidence_spans):
For each counted OE, create an evidence span quoting the relevant turns verbatim.
Use turn-anchored IDs: ES-T{start} for single turn, ES-T{start}-{end} for multi-turn.
Link each span to its source OE(s) via the event_ids field.
If two patterns share the same turns, create ONE shared span with both event_ids.

Step 5 — Pattern scoring (output: pattern_snapshot):
For each pattern, compute: score = sum(success for counted OEs) / counted_OE_count.
Classify each evidence span as success or missed opportunity using the threshold for its
scoring type: binary/dual_element ≥ 1.0, tiered_rubric/complexity_tiered ≥ 0.75,
multi_element ≥ 0.8. List success spans in success_evidence_span_ids.

Step 6 — Experiment detection (output: experiment_tracking):
If active experiment exists: evaluate whether the speaker attempted it.
Record attempt (yes/partial/no), count, and evidence_span_ids.

Step 7 — Coaching (output: coaching):
For each evaluable pattern with score < 1.0:
  - Choose rewrite_for_span_id from the pattern's NON-success evidence spans.
  - Re-read that span's excerpt (already serialized above). Write a rewrite that
    addresses the SAME topic and conversational moment.
  - Write notes and coaching_note grounded in the cited evidence.
For partial experiment attempts: write experiment_coaching with rewrite for
the detection span.
Write strengths, focus, micro_experiment, and executive_summary.
```

## What to Keep from v0.3.0

- All warning validations (SUCCESS_SPAN_MISSING/INCORRECT, REWRITE_TARGETS_SUCCESS, REWRITE_CONTENT_MISMATCH)
- Deterministic success_evidence_span_ids rebuild in gate1 validator
- Score arithmetic auto-correction in gate1 validator
- Sanitiser (enum confusion fixes, key stripping)
- workers.py rewrite_for_span_id safety checks (adapt to new field locations)

## What to Drop

- Post-hoc rewrite span reassignment (remapping rewrite to different span) — the reasoning-aligned schema should prevent most errors at the source
- Any backward-compatibility version dispatch — not needed

## Verification

After implementation:
1. Run `cd backend && python -m pytest tests/ -v` — all tests must pass
2. Verify the v0.4.0 JSON schema is valid (`python -c "import json, jsonschema; ..."`)
3. Check that system prompt sections match the output key ordering
4. Verify _HARD_REMINDERS reference the correct field paths for v0.4.0
