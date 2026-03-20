# ClearVoice Taxonomy v2.1 → v3.0 Migration Plan

## Decision Log (from user)
- **Backward compatibility**: Clean break — new schema only; old v2.1 runs stay in Airtable but aren't consumed
- **Baseline pack aggregation**: Weighted average of sub-run scores: `sum(score × denominator) / sum(denominators)`
- **Tier field**: Replace with `cluster_id`
- **OpportunityReasonCode**: Free-text with snake_case naming convention

## Taxonomy file fix
- Fix header typo on line 3: "Three scoring types" → "Five scoring types: dual-element, tiered rubric, binary, complexity-tiered, multi-element"
- Fix CORE_RULES binary scoring description (line 37) to say `Score = purposeful_count / opportunity_count` instead of `Score = numerator / denominator`

---

## Phase 1: JSON Schema (`backend/schemas/mvp_v0_3_0.json`)

This is the contract between the LLM output and everything downstream. Create a new schema file (keep old one for reference).

### 1.1 PatternId enum
Replace:
```
agenda_clarity, objective_signaling, turn_allocation, facilitative_inclusion,
decision_closure, owner_timeframe_specification, summary_checkback,
question_quality, listener_response_quality, conversational_balance
```
With:
```
purposeful_framing, focus_management, participation_management,
disagreement_navigation, resolution_and_alignment, assignment_clarity,
question_quality, communication_clarity, feedback_quality
```

### 1.2 ClusterId enum (new)
Add enum: `meeting_structure`, `participation_dynamics`, `decisions_accountability`, `communication_quality`

### 1.3 ScoringType enum (new)
Add enum: `dual_element`, `tiered_rubric`, `binary`, `complexity_tiered`, `multi_element`

### 1.4 PatternMeasurementBase — field changes
- **Remove**: `tier` (integer 1|2)
- **Add**: `cluster_id` (ClusterId enum, required)
- **Add**: `scoring_type` (ScoringType enum, required)
- **Rename**: `ratio` → `score` (number in [0, 1])
- **Remove**: `numerator`, `denominator` (replaced by scoring-type-specific fields)
- **Keep**: `evaluable_status`, `denominator_rule_id`, `min_required_threshold`, `evidence_span_ids`, `notes`, `coaching_note`, `suggested_rewrite`, `rewrite_for_span_id`, `success_evidence_span_ids`
- **Add optional**: `balance_assessment` (enum: over_indexed|balanced|under_indexed|unclear) — only used with participation_management
- **Add**: `opportunity_count` (integer ≥ 0, required when evaluable)
- **Add optional**: `element_a_count`, `element_b_count` (for dual_element scoring)
- **Add optional**: `simple_count`, `complex_count` (for complexity_tiered scoring)

### 1.5 Remove ConversationalBalanceMeasurement
The standalone measurement type is removed. `balance_assessment` is now an optional field on the base.

### 1.6 PatternMeasurement discriminated union
Replace the current union (EvaluableNumeric, EvaluableMedian, ConversationalBalance, InsufficientSignal, NotEvaluable) with a simpler structure:
- **Evaluable**: requires `score`, `opportunity_count`, `scoring_type`, `cluster_id`; type-specific fields per scoring_type
- **EvaluableMedian** (baseline pack): requires `score`, `scoring_type`, `cluster_id`; `opportunity_count` optional; `denominator_rule_id` = `weighted_average_of_meeting_level_scores`
- **InsufficientSignal**: requires `scoring_type`, `cluster_id`; forbids `score`, `opportunity_count`
- **NotEvaluable**: requires `scoring_type`, `cluster_id`; forbids `score`, `opportunity_count`

### 1.7 OpportunityEvent changes
- **`success`**: Change from string enum `["yes", "no", "na"]` to number in [0, 1] — supports 0.0, 0.25, 0.5, 0.75, 1.0 and any value (for feedback_quality's 0.2 increments)
- **`reason_code`**: Change from fixed enum to `type: "string"` with `pattern: "^[a-z][a-z0-9_]*$"` (free-text snake_case convention)
- Keep `event_id`, `turn_start_id`, `turn_end_id`, `target_control`, `count_decision`, `notes`

### 1.8 Version constants
- `schema_version`: `"mvp.v0.3.0"`
- `taxonomy_version`: update to match new taxonomy version

### 1.9 Pattern count
- Change from 10 to 9 wherever the schema constrains it (e.g., `minItems`/`maxItems` on `pattern_snapshot`)

---

## Phase 2: System Prompts

### 2.1 `system_prompt_v0_3_0.txt` (new file, based on v0_2_1)

Changes from v0_2_1:
- **PATTERN_ID ENUM**: Update to 9 new patterns in fixed order
- **schema_version**: `"mvp.v0.3.0"`
- **taxonomy_version**: update
- **Pattern snapshot section**:
  - Replace `numerator/denominator/ratio` with `score + opportunity_count + scoring_type + cluster_id`
  - Remove all conversational_balance special-case text
  - Add scoring-type-specific field requirements per type
  - Add cluster_id requirements
  - Remove `tier` references
- **Pattern-level coaching section**:
  - Replace `numerator > 0` / `numerator < denominator` / `numerator == denominator` with score-based conditions
  - When score > 0: notes required
  - When score < 1.0: coaching_note, suggested_rewrite, rewrite_for_span_id required
  - When score == 1.0: omit coaching fields
  - Replace conversational_balance coaching rules with participation_management + balance_assessment rules
- **Coaching output section**:
  - Replace `ratio >= 0.5` with `score >= 0.5`
  - Replace conversational_balance strength exception with participation_management balance_assessment logic
  - Focus pattern_id: no longer needs "not conversational_balance" exclusion
- **2-layer scoring trace**: Update for numeric `success` field instead of yes/no/na enum; update invariant checks
- **Self-check section**: Update all references (10→9, ratio→score, numerator→opportunity_count, conversational_balance→participation_management, tier→cluster_id)
- **Forbidden keys**: Add old field names (`numerator`, `denominator`, `ratio`, `tier`) to forbidden list

### 2.2 `system_prompt_baseline_pack_v0_3_0.txt` (new file)

Changes from v0_2_1:
- All changes from 2.1 above
- **Aggregation rules**:
  - Replace "ratio = MEDIAN of meeting-level ratios" with "score = weighted average: sum(score × opportunity_count) / sum(opportunity_counts)"
  - Replace "numerator = sum, denominator = sum" with scoring-type-specific aggregation (sum element_a_count across meetings, etc.)
  - Remove conversational_balance aggregation section
  - Add: participation_management balance_assessment aggregation (most common across meetings, same as old conversational_balance rule)
- **Pattern count**: 10 → 9

### 2.3 `system_prompt_next_experiment_v0_3_0.txt` (new file)

- Minimal changes — this prompt uses `{{EXPERIMENT_TAXONOMY}}` placeholder which auto-populates from taxonomy
- Update any references to old pattern names
- Update any references to old scoring fields

---

## Phase 3: Backend Config & Infrastructure

### 3.1 `backend/core/config.py`
- `SCHEMA_VERSION`: `"mvp.v0.3.0"`
- `TAXONOMY_VERSION`: update (e.g., `"v3.0"`)
- `MVP_SCHEMA_PATH`: point to `mvp_v0_3_0.json`
- `PATTERN_ORDER`: replace with 9 new pattern IDs:
  ```python
  PATTERN_ORDER = [
      "purposeful_framing",
      "focus_management",
      "participation_management",
      "disagreement_navigation",
      "resolution_and_alignment",
      "assignment_clarity",
      "question_quality",
      "communication_clarity",
      "feedback_quality",
  ]
  ```

### 3.2 `backend/core/prompt_builder.py`
- `extract_pattern_ids()`: Should work dynamically from taxonomy file markers — verify with new taxonomy
- `build_developer_message()`: Should work — reads full taxonomy file content
- `build_experiment_taxonomy_block()`: Should work — extracts experiment guidance per pattern using field names that are preserved in v3.0
- **Hard reminders** (lines ~186-200): Remove conversational_balance references; update numeric field constraints to use `score` instead of `numerator/denominator/ratio`
- **Baseline pack hard reminders** (lines ~286-301): Replace aggregation description with weighted average formula; remove conversational_balance rules; update field names

### 3.3 `backend/core/openai_client.py`
- `load_system_prompt()`: Update filename to `system_prompt_v0_3_0.txt`
- `load_baseline_system_prompt()`: Update filename to `system_prompt_baseline_pack_v0_3_0.txt`
- `load_next_experiment_system_prompt()`: Update filename to `system_prompt_next_experiment_v0_3_0.txt`

---

## Phase 4: Backend Validation (`backend/core/gate1_validator.py`)

### 4.1 Pattern set updates
- `_PATTERN_ID_ENUM`: derived from PATTERN_ORDER — will auto-update
- Remove `_NUMERIC_PATTERNS` (was `PATTERN_ORDER - {conversational_balance}`) — no longer needed since all patterns now have score
- Remove `_VALID_SUCCESS = {"yes", "no", "na"}` — success is now numeric

### 4.2 Business rule 3a: pattern count
- Change `10` → `9` in pattern_snapshot count check

### 4.3 Business rule 3c: pattern validation
- Remove all `conversational_balance` special-case logic (lines 372-386)
- For evaluable patterns:
  - Validate `score` in [0, 1]
  - Validate `opportunity_count` ≥ 1 (for non-median patterns)
  - Validate `scoring_type` matches pattern_id (add mapping)
  - Validate `cluster_id` matches pattern_id (add mapping)
  - Validate scoring-type-specific fields:
    - dual_element: `element_a_count` ≥ 0, `element_b_count` ≥ 0, both ≤ `opportunity_count`
    - complexity_tiered: `simple_count` ≥ 0, `complex_count` ≥ 0, `simple_count + complex_count == opportunity_count`
    - participation_management: if `balance_assessment` present, validate enum
- For baseline median patterns:
  - Change `denominator_rule_id` check to `weighted_average_of_meeting_level_scores`
  - Validate `score` in [0, 1]
- For insufficient_signal/not_evaluable: forbid `score`, `opportunity_count` (was `numerator`, `denominator`, `ratio`)

### 4.4 Opportunity events validation
- Remove `numerator = count(success=="yes")` check
- Add: validate `success` is numeric in [0, 1]
- Update: `denominator = opportunity_events_counted` → `opportunity_count = opportunity_events_counted`
- Add: sum of (success values for counted events) / counted_events ≈ score (approximate due to rounding)

### 4.5 Coaching output validation
- Remove `conversational_balance` exception for micro_experiment evidence_span_ids (line 552)
- Update any `ratio` references to `score`

### 4.6 Sanitizer updates
- `_VALID_SUCCESS`: remove (was string enum, now numeric)
- Add numeric success sanitization: coerce string values to float
- Update key-stripping to handle new field names

---

## Phase 5: Backend Workers (`backend/core/workers.py`)

### 5.1 `_patch_parsed_output()` (lines ~237-285)
- Remove conversational_balance field stripping (lines 252-258)
- Remove zero-denominator coercion to insufficient_signal for conversational_balance exception (lines 263-272)
- Update zero-denominator → zero-opportunity_count coercion: if evaluable pattern has `opportunity_count == 0`, coerce to `insufficient_signal`

### 5.2 Hardcoded fallback pattern IDs (line ~1231)
- Replace with new 9 pattern IDs

### 5.3 Pattern scoring collection (lines ~1350-1406)
- Replace `ratio` reads with `score`
- Remove `conversational_balance` exclusion from "no data yet" messages
- Update aggregate scoring: `avg_scores[pid] = sum(vals) / len(vals)`

### 5.4 Baseline pack numerics (lines ~896-900)
- Remove numerator/denominator float→int coercion (no longer needed)
- Add any score-specific coercion if needed

### 5.5 `_build_slim_meeting_summary()` (lines ~150-234)
- Replace `numerator`, `denominator`, `ratio` with `score`, `opportunity_count`, `scoring_type`
- Include `balance_assessment` where applicable
- Include scoring-type-specific fields

### 5.6 Experiment instantiation
- Verify pattern_id validation works with new IDs (should use PATTERN_ORDER dynamically)

---

## Phase 6: Backend Routes

### 6.1 `routes_coachee.py`
- `client_progress()`: Replace `ratio` with `score` in PatternDataPoint construction; replace `opportunity_count` from `denominator` field
- `client_summary()`: Update `ratio_by_pattern` → `score_by_pattern` for strength filtering
- `get_experiment_options()`: Update pattern weakness scoring from `ratio` to `score`

### 6.2 `routes_coach.py`
- Mirror all changes from routes_coachee.py

### 6.3 `routes_runs.py` — `_build_run_response()`
- Update PatternSnapshotItem construction: replace `numerator`, `denominator`, `ratio` with `score`, `opportunity_count`, `scoring_type`, `cluster_id`
- Include scoring-type-specific fields in response
- Update balance_assessment handling

### 6.4 `backend/api/quote_helpers.py`
- Verify no pattern-specific logic needs updating (should be pattern-agnostic)

---

## Phase 7: Frontend Types (`frontend/src/lib/types.ts`)

### 7.1 `PatternSnapshotItem`
```typescript
// Remove: numerator, denominator, ratio, tier
// Add:
score?: number;
opportunity_count?: number;
scoring_type?: string;  // 'dual_element' | 'tiered_rubric' | 'binary' | 'complexity_tiered' | 'multi_element'
cluster_id?: string;    // 'meeting_structure' | 'participation_dynamics' | 'decisions_accountability' | 'communication_quality'
element_a_count?: number;  // dual_element
element_b_count?: number;  // dual_element
simple_count?: number;     // complexity_tiered
complex_count?: number;    // complexity_tiered
// Keep: balance_assessment (now for participation_management)
```

### 7.2 `PatternDataPoint`
```typescript
// Change: ratio → score
pattern_id: string;
score: number;          // was: ratio
opportunity_count: number;
```

---

## Phase 8: Frontend Strings (`frontend/src/config/strings.ts`)

### 8.1 `patternLabels`
```typescript
purposeful_framing: 'Purposeful Framing',
focus_management: 'Focus Management',
participation_management: 'Participation Management',
disagreement_navigation: 'Disagreement Navigation',
resolution_and_alignment: 'Resolution & Alignment',
assignment_clarity: 'Assignment Clarity',
question_quality: 'Question Quality',
communication_clarity: 'Communication Clarity',
feedback_quality: 'Feedback Quality',
```

### 8.2 `patternExplanations`
Write new explanations for each pattern based on taxonomy v3.0 definitions.

### 8.3 `patternIcons`
Update to new pattern IDs. Design new emoji/icon mappings.

### 8.4 `balanceLabels`
Keep as-is (still used for participation_management's balance_assessment annotation).

### 8.5 Add `clusterLabels`
```typescript
clusterLabels: {
  meeting_structure: 'Meeting Structure & Direction',
  participation_dynamics: 'Participation & Interpersonal Dynamics',
  decisions_accountability: 'Decisions & Accountability',
  communication_quality: 'Communication Quality',
}
```

---

## Phase 9: Frontend Components

### 9.1 `PatternSnapshot.tsx`
- **PATTERN_ICONS**: Update to 9 new pattern IDs with new SVG icons
- **Score display**: Replace `numerator/denominator` fraction display with score percentage; show opportunity_count as context
- **hasMissedOpportunities**: `score < 1.0` instead of `numerator < denominator`
- **isPerfectScore**: `score === 1.0` instead of `numerator === denominator`
- **isMixedScore**: `score > 0 && score < 1.0`
- **BalanceBadge**: Now renders for `participation_management` when `balance_assessment` is present (not for a separate `conversational_balance` pattern)
- **buildTrendData**: Use `score` instead of `ratio`; use `opportunity_count` directly (no longer from `denominator`)
- **Conversational balance rendering logic**: Remove special-case rendering for conversational_balance; add balance_assessment display to participation_management card
- **Cluster grouping**: Deferred — keep flat list for now

### 9.2 Progress page (`frontend/src/app/client/progress/page.tsx`)
- **buildChartData**: Replace `ratio` with `score`, `denominator` with `opportunity_count`
- **Top 5 Patterns**: Keep logic but now selects from 9 patterns
- **CHART_COLORS**: 10 colors → 9 (or keep 10 for safety)
- **Pattern labels in legend/tooltip**: Use new STRINGS.patternLabels

### 9.3 Coach coachee detail (`frontend/src/app/coach/coachees/[id]/page.tsx`)
- Mirror progress page changes

### 9.4 Baseline detail page (`frontend/src/app/client/baseline/[id]/page.tsx`)
- Update pattern snapshot rendering: `score` instead of `ratio`
- Update ratio_by_pattern → score_by_pattern for strength filtering

### 9.5 RunStatusPoller
- Should work via PatternSnapshot component — verify no direct pattern ID references

---

## Phase 10: Backend Tests

### 10.1 `test_gate1_validator.py`
- Update test fixtures with new pattern IDs and scoring fields
- Add tests for each scoring type validation
- Remove conversational_balance test cases
- Add participation_management with balance_assessment tests

### 10.2 `test_workers_unit.py`
- Update _patch_parsed_output tests
- Update scoring collection tests

### 10.3 `test_prompt_builder.py`
- Update expected pattern IDs from taxonomy parsing

---

## Implementation Order

| Step | Phase | Est. scope | Risk |
|------|-------|-----------|------|
| 1 | Fix taxonomy file header typo | trivial | none |
| 2 | Create `mvp_v0_3_0.json` schema | large | high — contract for everything |
| 3 | Create new system prompt files (3) | large | high — LLM instruction quality |
| 4 | Update `config.py` | small | low |
| 5 | Update `openai_client.py` | small | low |
| 6 | Update `prompt_builder.py` | medium | medium |
| 7 | Update `gate1_validator.py` | large | high — validation correctness |
| 8 | Update `workers.py` | large | high — data pipeline |
| 9 | Update route files | medium | medium |
| 10 | Update frontend types | small | low |
| 11 | Update frontend strings | small | low |
| 12 | Update frontend components | large | medium |
| 13 | Update backend tests | medium | medium |

---

## Open Questions (resolved)

1. ~~Backward compatibility~~ → Clean break
2. ~~Baseline aggregation~~ → Weighted average: sum(score × opportunity_count) / sum(opportunity_counts)
3. ~~Tier field~~ → Replace with cluster_id
4. ~~OpportunityReasonCode~~ → Free-text with snake_case convention

## Additional Decisions (resolved)

5. ~~Binary scoring fields~~ → Just `score` + `opportunity_count` (no numerator/denominator), consistent with all other types
6. ~~OpportunityEvent.success range~~ → Any numeric value in [0, 1] (unconstrained)
7. ~~Frontend cluster grouping~~ → Flat list for now; defer visual cluster grouping post-migration

## Minor Items (will handle during implementation)

- **Baseline pack `denominator_rule_id`**: Old value `median_of_meeting_level_ratios` → new value `weighted_average_of_meeting_level_scores`
- **SVG icons for new patterns**: Will create appropriate icons for the 4 new patterns and update renamed patterns during Phase 9
- **Taxonomy file typos**: Will fix header ("Three" → "Five" scoring types) and CORE_RULES binary scoring description
