# Plan: 5-Tier Tiered Rubric + Remove "Prefer 0.5"

## Goal
Widen score discrimination for the 4 tiered_rubric patterns by:
1. Expanding from 3-tier `{0, 0.5, 1.0}` to 5-tier `{0, 0.25, 0.5, 0.75, 1.0}`
2. Removing the "prefer 0.5" instruction from communication_clarity

## Affected Patterns
- `focus_management` (tiered_rubric)
- `participation_management` (tiered_rubric)
- `disagreement_navigation` (tiered_rubric)
- `communication_clarity` (tiered_rubric)

## Changes

### 1. Taxonomy (`clearvoice_pattern_taxonomy_v3.0.txt`)

**a) Scoring type definition (lines 31-33):** Update the tiered rubric description from 3 values to 5:
```
Before: Each opportunity scored 0.0, 0.5, or 1.0 based on rubric level defined per pattern.
After:  Each opportunity scored 0.0, 0.25, 0.5, 0.75, or 1.0 based on rubric level defined per pattern.
```

**b) Per-pattern rubrics — add 0.25 and 0.75 tiers for each of the 4 patterns:**

- **focus_management** (lines 185-188): Insert 0.75 between 1.0 and 0.5, and 0.25 between 0.5 and 0.0.
  - 0.75: Names the drift but only partially redirects (e.g., acknowledges tangent, suggests returning but doesn't firmly steer back)
  - 0.25: Minimal acknowledgment — makes a vague attempt to intervene but doesn't name the drift or redirect meaningfully

- **participation_management** (lines 248-251): Insert 0.75 and 0.25.
  - 0.75: Named invitation to someone who hasn't spoken on this *specific sub-point* but has contributed to the broader topic
  - 0.25: Directed but generic — turns to a specific side of the room or subgroup without naming an individual ("engineering team, any thoughts?")

- **disagreement_navigation** (lines 316-331): Insert 0.75 and 0.25.
  - 0.75: Engages substantively with the disagreement and acknowledges the other perspective, but doesn't drive toward resolution or park it with a next step
  - 0.25: Acknowledges the disagreement exists but doesn't engage with the substance — de-escalates procedurally without addressing the point

- **communication_clarity** (lines 611-629): Insert 0.75 and 0.25.
  - 0.75: The turn has a clear main point stated early but falls short on one dimension — e.g., slightly disproportionate length, or mostly concrete with minor patches of vagueness
  - 0.25: A discernible point exists but is significantly buried, or the response partially addresses the question asked but mostly drifts to adjacent concerns

**c) Remove "prefer 0.5" instruction** (line 651):
```
Delete: "When in doubt about whether a turn is 0.5 or 1.0, prefer 0.5. When in doubt about whether it's 0.0 or 0.5, prefer 0.5. Center of the rubric is the safe zone."
```

**d) participation_management detection note** (line 284): Update the "default to 0.5" fallback for ambiguous attribution — keep the conservative default but clarify the 5-tier context.

### 2. System Prompt (`system_prompt_v0_3_0.txt`)

**a) Line 232:** The success enum `success(0|0.25|0.5|0.75|0.8|1.0)` already includes 0.25 and 0.75 (these were added for complexity_tiered and multi_element). No change needed.

**b) Line 241:** The anti-holistic instruction references `{0.0, 0.5, 1.0}` — update to `{0.0, 0.25, 0.5, 0.75, 1.0}` to reflect the new tier set.

### 3. Baseline Pack Prompt (`system_prompt_baseline_pack_v0_3_0.txt`)

Check for any parallel references to 3-tier scoring or "prefer 0.5" that need the same update.

### 4. Gate1 Validator (`backend/core/gate1_validator.py`)

**Line 475:** Update `_ALLOWED_SUCCESS` for `tiered_rubric`:
```python
Before: "tiered_rubric": {0, 0.5, 1.0},
After:  "tiered_rubric": {0, 0.25, 0.5, 0.75, 1.0},
```

### 5. Test Fixtures (`backend/tests/conftest.py`)

The test fixture uses `score: 1.0` for all tiered_rubric patterns (all-perfect scores). These remain valid under 5-tier scoring, so no fixture changes are strictly needed. However, should consider adding a test case that uses 0.25 or 0.75 values to verify they pass validation.

### 6. JSON Schema (`backend/schemas/mvp_v0_3_0.json`)

The schema defines success as `"type": "number", "minimum": 0, "maximum": 1`. This already permits 0.25 and 0.75. No change needed.

## Files Changed (summary)
1. `clearvoice_pattern_taxonomy_v3.0.txt` — rubric definitions + remove "prefer 0.5"
2. `system_prompt_v0_3_0.txt` — update anti-holistic instruction reference
3. `system_prompt_baseline_pack_v0_3_0.txt` — check/update if parallel references exist
4. `backend/core/gate1_validator.py` — `_ALLOWED_SUCCESS` update (1 line)
5. `backend/tests/conftest.py` — optionally add 0.25/0.75 test coverage

## Not Changed
- JSON schema (already permissive)
- `score_range_analysis.py` / `pattern_scoring_diagnostics.py` (analysis tools, not production)
- dual_element, binary, complexity_tiered, multi_element patterns (out of scope)
