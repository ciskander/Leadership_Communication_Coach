# Airtable Migration Diff

## Summary

All changes are **additive only**. No existing fields or tables are removed.

---

## New Fields

### `runs` table
| Field Name | Type | Notes |
|---|---|---|
| `Coachee ID` | Single line text | Denormalized user ID for idempotency key; avoids cross-table lookup in hot path |
| `Idempotency Key` | Single line text | SHA-256 of (transcript_id, analysis_type, coachee_id, target_speaker_label, target_role, config_version). Unique index. |

### `experiments` table
| Field Name | Type | Notes |
|---|---|---|
| `Created From Run ID` | Single line text | The run_id that instantiated this experiment. Used for idempotency. |
| `Instruction` | Long text | The micro-experiment instruction text from run coaching_output |
| `Success Marker` | Long text | success_marker from micro_experiment |

### `experiment_events` table
| Field Name | Type | Notes |
|---|---|---|
| `Idempotency Key` | Single line text | Composite of (run_id + experiment_id). Prevents duplicate events. |
| `Attempt Count` | Number | count_attempts from detection_in_this_meeting |
| `Attempt Enum` | Single select | no / partial / yes (from detection_in_this_meeting.attempt) |

### `baseline_packs` table
| Field Name | Type | Notes |
|---|---|---|
| `Role Consistency` | Single line text | null / consistent / mixed |
| `Meeting Type Consistency` | Single line text | null / consistent / mixed |
| `Target Speaker Name` | Single line text | (may already exist as Speaker Label — confirm) |
| `Pack Build Idempotency Key` | Single line text | Equals baseline_pack_id. Ensures one build run per pack. |

---

## No Table Additions Required

All required tables already exist: `transcripts`, `run_requests`, `runs`, `validation_issues`, `baseline_packs`, `baseline_pack_items`, `experiments`, `users`, `experiment_events`, `config`.

---

## Notes

- The `transcripts` table has legacy baseline-related fields (`Baseline Pack ID`, `Pack Size`, `Meetings JSON`). Per spec these are Make-workflow artifacts; they are **not read or written** by the new engine.
- `config` table fields (`System Prompt`, `Taxonomy Compact Block`, `Schema JSON`) are read at runtime to assemble OpenAI calls.
- `gate2_reports` table is out of scope for this prompt.
