# Plan: Consolidate Pattern Taxonomy to Single Source of Truth

## Current State Analysis

### Where taxonomy content lives today

| Location | What it contains | How it's loaded |
|---|---|---|
| `clearvoice_pattern_taxonomy_v2.1.txt` | Full canonical taxonomy (385 lines): 10 patterns with scoring rules, denominators, exclusions, role notes, thresholds | **Not loaded by any code** — purely a reference doc |
| Airtable "Taxonomy Compact Block" | Compact taxonomy (content unknown — loaded at runtime) | `_load_developer_message_from_config()` in workers.py; passed as `developer_message` to single_meeting and baseline_pack LLM calls |
| `system_prompt_next_experiment_v0_2_1.txt` lines 21-84 | Experiment-focused taxonomy: 10 patterns with "What it measures / What good looks like / Common failure mode / Experiment focus" | `load_next_experiment_system_prompt()` in openai_client.py; embedded inline in the system prompt |
| `_VALID_PATTERNS` set (workers.py:1191-1196) | Hardcoded set of 10 pattern ID strings | Used for validation of LLM experiment outputs |
| `system_prompt_v0_2_1.txt` line 28 | **References** the taxonomy ("The developer message contains the full pattern taxonomy...") but does NOT embed it | Loaded as system prompt; expects taxonomy via separate developer_message |
| `system_prompt_baseline_pack_v0_2_1.txt` | Same as above — references developer message taxonomy | Same loading pattern |

### Key observations

1. **The single_meeting and baseline_pack prompts already use the right architecture** — they reference the taxonomy via `developer_message` rather than embedding it. The problem is that `developer_message` comes from Airtable, not from the canonical file.

2. **The next_experiment prompt is the only one that embeds taxonomy content inline** (lines 21-84), and it passes an **empty string** as `developer_message` (workers.py:1495).

3. **The canonical taxonomy file is never loaded by any code.** It exists purely as a reference document.

4. **`_VALID_PATTERNS` is a hardcoded set** that duplicates the pattern ID list from the taxonomy.

---

## Proposed Plan

### 1. Add section delimiters to `clearvoice_pattern_taxonomy_v2.1.txt`

Add machine-parseable section markers so extraction functions can locate content reliably. Use a simple delimiter convention that's already close to the current format:

```
<!-- SECTION:CORE_RULES -->
... existing core rules ...
<!-- /SECTION:CORE_RULES -->

<!-- SECTION:PATTERN:agenda_clarity -->
... existing pattern block ...
<!-- /SECTION:PATTERN:agenda_clarity -->

<!-- SECTION:PATTERN:objective_signaling -->
...
```

**Why HTML comments?** They're invisible if the file is rendered as plain text in most contexts, they're easy to parse with simple string operations (no regex needed), and they don't interfere with the existing content that uses `────` line decorators.

**Alternative considered:** Using the existing `PATTERN N: pattern_id` headers with `────` dividers. This works but is fragile — the divider lines are also used within the core rules section. Explicit open/close tags are safer.

### 2. Create taxonomy loader in `prompt_builder.py`

Add a new module-level function and supporting utilities:

```python
# --- Taxonomy loading ---

_TAXONOMY_FILE = Path(__file__).resolve().parent.parent.parent / "clearvoice_pattern_taxonomy_v2.1.txt"

def _load_taxonomy_raw() -> str:
    """Read the canonical taxonomy file. Cached after first call."""
    ...

def _extract_section(raw: str, section_name: str) -> str:
    """Extract content between <!-- SECTION:name --> and <!-- /SECTION:name --> markers."""
    ...

def extract_pattern_ids() -> list[str]:
    """Return ordered list of pattern IDs from the taxonomy file."""
    # Finds all SECTION:PATTERN:xxx markers, returns the xxx values in order
    ...

def build_developer_message() -> str:
    """Build the full developer message (replaces Airtable Taxonomy Compact Block).

    Returns the full taxonomy content: CORE_RULES + all PATTERN sections.
    This is used as the developer_message for single_meeting and baseline_pack calls.
    """
    ...

def build_experiment_taxonomy_block() -> str:
    """Build the experiment-design-focused taxonomy summary.

    For each pattern, extracts:
    - What it measures (first line of pattern's "What it measures" field)
    - What good looks like (derived from "Counts as success" criteria)
    - Common failure mode (derived from "Excluded from numerator only")
    - Experiment focus (a coaching-oriented summary)

    These four fields per pattern are the ones currently embedded in
    system_prompt_next_experiment_v0_2_1.txt lines 21-84.
    """
    ...
```

**Extraction modes:**

| Consumer | Function | What it returns |
|---|---|---|
| single_meeting developer_message | `build_developer_message()` | Full taxonomy: core rules + all 10 pattern blocks (equivalent to current Airtable "Taxonomy Compact Block") |
| baseline_pack developer_message | `build_developer_message()` | Same — both use identical developer_message today |
| next_experiment system prompt | `build_experiment_taxonomy_block()` | Experiment-focused summary: 4 fields per pattern (What it measures / What good looks like / Common failure mode / Experiment focus) |
| Pattern ID validation | `extract_pattern_ids()` | Ordered list of pattern ID strings |

**Important design decision: Where do the experiment-focused fields live?**

The experiment taxonomy block (lines 21-84 of `system_prompt_next_experiment_v0_2_1.txt`) contains two fields that do NOT exist in the canonical taxonomy file today:
- **"Common failure mode"** — currently derived from the "Excluded from numerator only" section but rephrased more concisely
- **"Experiment focus"** — a coaching-oriented sentence not present in the canonical file

**Proposed solution:** Add these two fields to each pattern block in `clearvoice_pattern_taxonomy_v2.1.txt`:

```
Experiment guidance:
- Common failure mode: Purpose statement without an outcome frame, or an outcome frame without a purpose statement.
- Experiment focus: Help the coachee build the habit of stating both elements — purpose and desired outcome — in their opening.
```

This keeps the canonical file as the true single source. The `build_experiment_taxonomy_block()` function extracts just these fields plus "What it measures" and the success criteria summary.

### 3. Update system prompt files with `{{PATTERN_TAXONOMY}}` placeholder

**`system_prompt_v0_2_1.txt`** — No changes needed. This file already delegates taxonomy to the developer_message ("The developer message contains the full pattern taxonomy..."). It does not embed taxonomy content.

**`system_prompt_baseline_pack_v0_2_1.txt`** — Same as above. No changes needed.

**`system_prompt_next_experiment_v0_2_1.txt`** — Replace lines 20-85 (the inline "PATTERN TAXONOMY — EXPERIMENT DESIGN GUIDE" section) with:

```
{{EXPERIMENT_TAXONOMY}}
```

Then update the loader in `openai_client.py`:

```python
def load_next_experiment_system_prompt(path=None):
    ...
    raw = f.read()
    # Substitute taxonomy placeholder
    from backend.core.prompt_builder import build_experiment_taxonomy_block
    return raw.replace("{{EXPERIMENT_TAXONOMY}}", build_experiment_taxonomy_block())
```

### 4. Replace Airtable developer_message with file-based version

**In `workers.py`:**

```python
# In process_single_meeting_analysis() around line 470:
dev_message = developer_message_override or _load_developer_message()

# In process_baseline_pack_build() around line 842:
dev_message = developer_message_override or _load_developer_message()
```

New function replacing `_load_developer_message_from_config()`:

```python
def _load_developer_message(client=None, config_links=None) -> str:
    """Load taxonomy developer message from canonical file.

    Falls back to Airtable if file is unavailable (backwards compat).
    Logs warning if both sources exist and differ.
    """
    from backend.core.prompt_builder import build_developer_message

    file_based = build_developer_message()

    if file_based:
        # If Airtable is also available, check for drift
        if client and config_links:
            try:
                airtable_based = _load_developer_message_from_config(client, config_links)
                if airtable_based and airtable_based.strip() != file_based.strip():
                    logger.warning(
                        "Taxonomy drift detected: Airtable 'Taxonomy Compact Block' "
                        "differs from canonical file. Using file-based version."
                    )
            except Exception:
                pass
        return file_based

    # Fallback to Airtable if file is missing/empty
    if client:
        logger.warning("Canonical taxonomy file unavailable; falling back to Airtable.")
        return _load_developer_message_from_config(client, config_links)

    return ""
```

**Replace `_VALID_PATTERNS` hardcoded set:**

```python
from backend.core.prompt_builder import extract_pattern_ids

_VALID_PATTERNS = set(extract_pattern_ids())
```

### 5. Migration / Rollback Strategy

**Migration steps (in order):**

1. Add section delimiters + experiment guidance fields to `clearvoice_pattern_taxonomy_v2.1.txt`
2. Add taxonomy loader functions to `prompt_builder.py`
3. Add unit tests that verify:
   - `extract_pattern_ids()` returns exactly 10 IDs in expected order
   - `build_developer_message()` returns non-empty string containing all 10 pattern IDs
   - `build_experiment_taxonomy_block()` returns content structurally matching current inline block
4. Update `_VALID_PATTERNS` to use `extract_pattern_ids()`
5. Replace `_load_developer_message_from_config()` calls with `_load_developer_message()` (with drift detection)
6. Update `system_prompt_next_experiment_v0_2_1.txt` with `{{EXPERIMENT_TAXONOMY}}` placeholder
7. Update `load_next_experiment_system_prompt()` to do substitution

**Rollback:** Each step is independently revertable:
- Steps 1-3 are purely additive — no behavior change
- Step 4 can revert to hardcoded set
- Step 5 falls back to Airtable automatically if file is unavailable
- Steps 6-7 can revert by restoring the old prompt file and loader

**Verification:** Before deploying, compare the final assembled prompts (after substitution) against the current prompts character-by-character to confirm equivalence.

---

## 6. Critiques and Pushback

### What's good about this approach
- **Single source of truth** — one file to update when taxonomy changes
- **No content changes** — purely structural refactor, low risk of behavior change
- **Graceful fallback** — Airtable path preserved as backup
- **Simple extraction** — HTML comment delimiters are robust and easy to parse

### Concerns and alternatives

**Concern 1: The "Taxonomy Compact Block" in Airtable may not be identical to the canonical file.**

The Airtable field is called "Compact Block" — it may be an intentionally condensed version optimized for token efficiency. If so, `build_developer_message()` shouldn't return the full 385-line canonical file (which includes verbose detection notes, examples, and counterexamples). Instead, it should produce a compact version that matches what Airtable currently sends.

**Recommendation:** Before implementing, dump the current Airtable "Taxonomy Compact Block" content and diff it against the canonical file. If they differ significantly, `build_developer_message()` should extract a compact subset (core rules + key fields per pattern, omitting detection notes and examples). This compact format should be defined as a new section type in the taxonomy file, or `build_developer_message()` should selectively extract only the fields needed (What it measures, Denominator, Counts as success, Excluded from numerator, Excluded from both, Role notes, Minimum threshold).

**Concern 2: HTML comment delimiters may get stripped by some editors/tools.**

Alternative: Use plain-text delimiters like `### BEGIN:PATTERN:agenda_clarity ###` / `### END:PATTERN:agenda_clarity ###`. These are more visible but equally parseable.

**Recommendation:** Use plain-text delimiters. The taxonomy file is plain text, not HTML/Markdown. Consistency matters.

**Concern 3: The experiment-focused fields ("Common failure mode", "Experiment focus") are human-written coaching content, not mechanical derivations.**

Adding them to the canonical taxonomy file is the right call — they ARE part of the taxonomy's coaching layer. But this means `build_experiment_taxonomy_block()` is a simple extraction, not a transformation. That's actually better — transforms are fragile.

**Concern 4: Token cost of developer_message.**

The full canonical taxonomy is ~385 lines. If the current Airtable compact block is significantly shorter, switching to the full file will increase token usage per call. Consider this when deciding what `build_developer_message()` returns.

**Concern 5: Caching.**

`_load_taxonomy_raw()` should cache the file content (e.g., `@lru_cache` or module-level variable). The file doesn't change at runtime, and reading it for every LLM call is wasteful.

**Concern 6: Is `prompt_builder.py` the right home?**

Currently `prompt_builder.py` builds user messages. Adding taxonomy/developer_message building there expands its scope. An alternative is a new `taxonomy.py` module. However, given the small size of the additions and the existing pattern of prompt-related logic in `prompt_builder.py`, keeping it there avoids unnecessary module proliferation.

**Recommendation:** Keep it in `prompt_builder.py` for now. If the taxonomy logic grows beyond ~100 lines, extract to `taxonomy.py` later.

---

## Summary of File Changes

| File | Change |
|---|---|
| `clearvoice_pattern_taxonomy_v2.1.txt` | Add section delimiters; add "Experiment guidance" fields to each pattern |
| `backend/core/prompt_builder.py` | Add `_load_taxonomy_raw()`, `_extract_section()`, `extract_pattern_ids()`, `build_developer_message()`, `build_experiment_taxonomy_block()` |
| `backend/core/openai_client.py` | Update `load_next_experiment_system_prompt()` to substitute `{{EXPERIMENT_TAXONOMY}}` |
| `backend/core/workers.py` | Replace `_load_developer_message_from_config()` calls with new `_load_developer_message()` wrapper; derive `_VALID_PATTERNS` from `extract_pattern_ids()` |
| `system_prompt_next_experiment_v0_2_1.txt` | Replace inline taxonomy block (lines 20-85) with `{{EXPERIMENT_TAXONOMY}}` placeholder |
| `system_prompt_v0_2_1.txt` | No changes |
| `system_prompt_baseline_pack_v0_2_1.txt` | No changes |
