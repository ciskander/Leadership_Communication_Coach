# Assumptions

1. **OpenAI SDK message structure** — The example calls show a three-part structure
   (system / developer / user). The `developer` role is used for the taxonomy compact
   block. This matches the Responses API style; if you are on the Chat Completions
   endpoint without developer-role support, swap `developer` → `system` (append after
   the first system message).

2. **Transcript text storage** — The engine reads transcript text from the Airtable
   `Transcript (extracted)` field first, falling back to `Raw Transcript Text`. Actual
   file bytes (from `Transcript File` attachment) are handled by the HTTP layer (Prompt
   2) which should write the extracted text into `Transcript (extracted)` before
   enqueueing the job.

3. **Baseline pack items have pre-completed single-meeting runs** — `process_baseline_pack_build`
   validates that each `baseline_pack_item` already has a Gate1-passing run linked.
   Orchestrating those upstream runs is the responsibility of the queue/workflow layer
   (Prompt 2), not this engine.

4. **Config table is the source of model / prompt overrides** — If no Config record is
   linked, the engine falls back to `System_Prompt.txt` on disk and `OPENAI_MODEL_DEFAULT`
   from config.py. All secrets are environment variables only.

5. **`Idempotency Key` and `Created From Run ID` fields must be added to Airtable** — See
   `airtable_migration_diff.md`. The engine will fail gracefully on first run without them
   (Airtable will return a 422 on create), but will not corrupt data.
