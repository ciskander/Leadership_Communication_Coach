"""
quote_cleanup.py — Post-processing cleanup of evidence span quotes.

Runs a lightweight LLM call to clean up ASR transcript artifacts in evidence
quotes before they are displayed to the user. This is separate from the main
analysis prompt to keep concerns cleanly separated.

Supports both OpenAI and Anthropic providers — the provider is chosen
automatically based on the QUOTE_CLEANUP_MODEL name.

Cleanup operations:
- Insert punctuation for clarity (periods, commas, question marks)
- Remove filler words (um, uh, you know, like) and obvious duplicate words
- Insert single quotes around phrases that should be quoted for clarity
- Abbreviate lengthy non-target-speaker quotes in multi-speaker spans
- Do NOT paraphrase, substitute words, or change phrasing
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

import openai

from .config import OPENAI_API_KEY, ANTHROPIC_API_KEY
from .llm_client import is_anthropic_model

logger = logging.getLogger(__name__)

# Use a smaller/cheaper model for cleanup by default.
CLEANUP_MODEL: str = os.getenv("QUOTE_CLEANUP_MODEL", "gpt-4o-mini")

# Max quotes per LLM batch.  gpt-4o-mini needs to generate a JSON response
# containing each cleaned quote.  With 25-50 quotes in a single batch the
# output generation regularly exceeds 15s.  Smaller batches (≤15) complete
# reliably within the timeout and can be retried individually on failure.
_BATCH_SIZE: int = 15

# Timeout for each cleanup LLM call (seconds).
# With _BATCH_SIZE=15, gpt-4o-mini typically completes in 5-10s.
_CLEANUP_TIMEOUT: float = 20.0

# Total wall-clock budget for the entire cleanup operation (seconds).
# This runs inside the Celery worker (not the HTTP handler), so we are not
# constrained by Railway's proxy timeout.  60s comfortably handles 3-4
# batches of _BATCH_SIZE=15 with gpt-4o-mini (~10-15s per batch).
_TOTAL_BUDGET: float = 60.0

# How many times to retry a single batch on timeout before giving up.
_MAX_RETRIES: int = 1

# ── Persistent cache (PostgreSQL-backed, survives deploys) ────────────────────
# Falls back to in-memory dict if DB is unavailable.
_mem_cache: dict[str, str] = {}
_db_cache_ready = False


def _init_cache_table() -> None:
    """Create the quote_cleanup_cache table if it doesn't exist."""
    global _db_cache_ready
    if _db_cache_ready:
        return
    try:
        from ..auth.sqlite_db import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS quote_cleanup_cache (
                        cache_key   TEXT PRIMARY KEY,
                        cleaned     TEXT NOT NULL,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
            conn.commit()
        _db_cache_ready = True
    except Exception:
        logger.debug("Could not init quote_cleanup_cache table; using in-memory only", exc_info=True)


def _cache_get(key: str) -> Optional[str]:
    """Look up a cached cleanup result. Checks in-memory first, then DB."""
    if key in _mem_cache:
        return _mem_cache[key]
    _init_cache_table()
    if not _db_cache_ready:
        return None
    try:
        from ..auth.sqlite_db import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT cleaned FROM quote_cleanup_cache WHERE cache_key = %s", (key,))
                row = cur.fetchone()
                if row:
                    val = row["cleaned"]
                    _mem_cache[key] = val  # warm in-memory layer
                    return val
    except Exception:
        pass
    return None


def _cache_put_batch(items: list[tuple[str, str]]) -> None:
    """Persist multiple cache entries. Best-effort — failures are non-fatal."""
    for key, val in items:
        _mem_cache[key] = val
    _init_cache_table()
    if not _db_cache_ready or not items:
        return
    try:
        from ..auth.sqlite_db import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Use INSERT ... ON CONFLICT for upsert
                for key, val in items:
                    cur.execute(
                        """INSERT INTO quote_cleanup_cache (cache_key, cleaned)
                           VALUES (%s, %s)
                           ON CONFLICT (cache_key) DO UPDATE SET cleaned = EXCLUDED.cleaned""",
                        (key, val),
                    )
            conn.commit()
    except Exception:
        logger.debug("Failed to persist cleanup cache entries", exc_info=True)

_CLEANUP_SYSTEM_PROMPT = """You are a transcript quote cleanup assistant. You will receive a JSON array of objects, each with "id", "text", and a "category" field. Apply cleanup rules based on the category.

CATEGORY: "transcript_quote"
These are raw quotes from automatic speech recognition (ASR) transcripts. Apply ONLY these operations:
1. PUNCTUATION: Insert periods, commas, question marks, and other punctuation where clearly needed for readability. Capitalize the first word of sentences.
2. FILLER REMOVAL: Remove filler words (um, uh, er, ah, you know, I mean, like when used as filler) ONLY when they add no meaning.
3. DUPLICATE REMOVAL: Remove obviously duplicated words or phrases caused by speech disfluency (e.g., "from the from the" → "from the").
4. SINGLE QUOTES: Where a word or phrase is clearly being referenced as a title, label, or named concept, wrap it in single quotes for clarity (e.g., Engine 17 → 'Engine 17' when it is being named as a specific thing, but NOT when it is part of natural speech like "I drove Engine 17").

Strict rules for transcript_quote:
- Do NOT paraphrase, reword, or substitute any words.
- Do NOT add words that were not in the original (except punctuation marks and single quotes).
- Do NOT remove words that carry meaning — only remove clear filler and exact duplicates.
- Do NOT change the speaker's phrasing, vocabulary, or sentence structure.
- Do NOT correct grammar (e.g., do not fix subject-verb agreement or tense).
- If a quote is too short or garbled to meaningfully clean up, return it unchanged.

For NON-TARGET speaker quotes in multi-speaker spans (marked with "abbreviate": true):
- Keep the first ~1-2 sentences and the last ~1-2 sentences of the quote.
- Replace the removed middle portion with " [...] " (space, brackets, ellipsis, space).
- Keep enough text at the start and end to preserve clear context for what the target speaker was responding to.
- If the quote is already short (under ~40 words), do not abbreviate — return it with only the standard cleanup.

CATEGORY: "coaching_blurb"
These are AI-generated coaching observations that may reference what the speaker said in the meeting. Apply ONLY these operations:
1. INLINE QUOTES: When the text references something the speaker said (e.g., phrases like "such as do we split EP-118" or "your statement I think we should move on"), wrap the referenced speech in single quotes and add appropriate terminal punctuation inside the quotes (e.g., 'do we split EP-118?' or 'I think we should move on.').
2. PUNCTUATION: Insert or fix punctuation for clarity where clearly needed.
3. GRAMMAR: Fix minor grammar issues only if they are clearly errors (e.g., missing articles, broken sentence structure). Do NOT rephrase or rewrite.

Strict rules for coaching_blurb:
- Do NOT change the meaning or substantive content of the coaching observation.
- Do NOT rewrite sentences or change vocabulary — only add quotes and punctuation.
- Do NOT add coaching advice that was not in the original text.
- If no inline speech references are present, return the text with only minor punctuation fixes or unchanged.

GLOBAL RULES:
- Preserve the exact JSON structure. Return a JSON array with the same number of objects.
- Use only single quotes (') around referenced speech — never double quotes.
- Return ONLY a JSON array wrapped in a {"quotes": [...]} object. No prose, no explanation."""

_CLEANUP_USER_TEMPLATE = """Clean up the following transcript quotes. Return a JSON object with a "quotes" key containing the cleaned array.

{quotes_json}"""


def _cache_key(text: str, abbreviate: bool) -> str:
    """Deterministic cache key for a quote."""
    raw = f"{text}|{abbreviate}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_cleanup_response(raw: str) -> list[dict]:
    """Parse the LLM response, handling JSON wrapped in markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            cleaned = inner.strip()

    parsed = json.loads(cleaned)

    # Handle both {"quotes": [...]} and bare [...] formats
    if isinstance(parsed, dict):
        result_list = parsed.get("quotes", parsed.get("results", []))
    elif isinstance(parsed, list):
        result_list = parsed
    else:
        return []

    return result_list


def _call_cleanup_batch_openai(
    batch: list[dict],
    effective_model: str,
    api_key: Optional[str] = None,
) -> dict[str, str]:
    """Send a single batch of quotes to OpenAI and return {id: cleaned_text}."""
    payload = [
        {
            "id": q["id"],
            "text": q["text"],
            "abbreviate": q.get("abbreviate", False),
            "category": q.get("category", "transcript_quote"),
        }
        for q in batch
    ]

    client = openai.OpenAI(
        api_key=api_key or OPENAI_API_KEY,
        timeout=openai.Timeout(timeout=_CLEANUP_TIMEOUT, connect=5.0),
        max_retries=0,  # No SDK-internal retries — we handle failure at batch level
    )

    response = client.chat.completions.create(
        model=effective_model,
        messages=[
            {"role": "system", "content": _CLEANUP_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _CLEANUP_USER_TEMPLATE.format(
                    quotes_json=json.dumps(payload, ensure_ascii=False, indent=2)
                ),
            },
        ],
        max_completion_tokens=16384,
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    raw = response.choices[0].message.content or ""
    result_list = _parse_cleanup_response(raw)

    return {
        item["id"]: item["text"]
        for item in result_list
        if item.get("id") and item.get("text")
    }


def _call_cleanup_batch_anthropic(
    batch: list[dict],
    effective_model: str,
    api_key: Optional[str] = None,
) -> dict[str, str]:
    """Send a single batch of quotes to Anthropic and return {id: cleaned_text}."""
    import anthropic

    payload = [
        {
            "id": q["id"],
            "text": q["text"],
            "abbreviate": q.get("abbreviate", False),
            "category": q.get("category", "transcript_quote"),
        }
        for q in batch
    ]

    client = anthropic.Anthropic(
        api_key=api_key or ANTHROPIC_API_KEY,
        timeout=anthropic.Timeout(timeout=_CLEANUP_TIMEOUT, connect=5.0),
        max_retries=0,
    )

    response = client.messages.create(
        model=effective_model,
        system=_CLEANUP_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _CLEANUP_USER_TEMPLATE.format(
                    quotes_json=json.dumps(payload, ensure_ascii=False, indent=2)
                ),
            },
        ],
        max_tokens=16384,
    )

    raw = ""
    for block in response.content:
        if block.type == "text":
            raw = block.text
            break

    result_list = _parse_cleanup_response(raw)

    return {
        item["id"]: item["text"]
        for item in result_list
        if item.get("id") and item.get("text")
    }


def cleanup_quotes(
    quotes: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict[str, str]:
    """Clean up a batch of quote texts via lightweight LLM calls.

    Splits into batches of _BATCH_SIZE, uses a persistent DB cache (with
    in-memory warm layer) to skip previously cleaned quotes, and applies a
    per-batch timeout.

    Automatically routes to OpenAI or Anthropic based on the model name.

    Args:
        quotes: List of dicts with "id", "text", and optionally "abbreviate" keys.
        model: Override model name (defaults to CLEANUP_MODEL).
        api_key: Override API key.

    Returns:
        Dict mapping quote id -> cleaned text. If cleanup fails for any reason,
        returns the original texts unchanged.
    """
    if not quotes:
        return {}

    originals = {q["id"]: q["text"] for q in quotes}
    cleaned: dict[str, str] = {}

    # Check persistent cache first, build list of uncached quotes
    uncached: list[dict] = []
    for q in quotes:
        ck = _cache_key(q["text"], q.get("abbreviate", False))
        cached_val = _cache_get(ck)
        if cached_val is not None:
            cleaned[q["id"]] = cached_val
        else:
            uncached.append(q)

    if not uncached:
        logger.info("Quote cleanup: all %d quotes served from cache", len(quotes))
        for qid in originals:
            cleaned.setdefault(qid, originals[qid])
        return cleaned

    try:
        import time as _time

        effective_model = model or CLEANUP_MODEL
        use_anthropic = is_anthropic_model(effective_model)
        t0 = _time.monotonic()

        # Process in batches, respecting the total time budget
        new_cache_entries: list[tuple[str, str]] = []
        for i in range(0, len(uncached), _BATCH_SIZE):
            elapsed = _time.monotonic() - t0
            if elapsed > _TOTAL_BUDGET:
                logger.warning(
                    "Quote cleanup: total budget %.1fs exceeded (%.1fs elapsed); "
                    "skipping remaining %d quotes",
                    _TOTAL_BUDGET, elapsed, len(uncached) - i,
                )
                break

            batch = uncached[i : i + _BATCH_SIZE]
            batch_result: dict[str, str] = {}
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    if use_anthropic:
                        batch_result = _call_cleanup_batch_anthropic(batch, effective_model, api_key)
                    else:
                        batch_result = _call_cleanup_batch_openai(batch, effective_model, api_key)
                    break  # success
                except Exception:
                    if attempt < _MAX_RETRIES:
                        logger.info(
                            "Quote cleanup batch %d-%d attempt %d failed; retrying",
                            i, i + len(batch), attempt + 1,
                        )
                    else:
                        logger.warning(
                            "Quote cleanup batch %d-%d failed after %d attempts; skipping",
                            i, i + len(batch), _MAX_RETRIES + 1,
                            exc_info=True,
                        )
            # Write results and collect cache entries
            for q in batch:
                qid = q["id"]
                if qid in batch_result:
                    cleaned[qid] = batch_result[qid]
                    ck = _cache_key(q["text"], q.get("abbreviate", False))
                    new_cache_entries.append((ck, batch_result[qid]))

        # Persist all new cache entries in one batch
        if new_cache_entries:
            _cache_put_batch(new_cache_entries)

        # Fill in any missing IDs with originals
        for qid in originals:
            cleaned.setdefault(qid, originals[qid])

        logger.info(
            "Quote cleanup completed: %d/%d quotes cleaned, model=%s provider=%s",
            sum(1 for qid in cleaned if cleaned[qid] != originals.get(qid)),
            len(originals),
            effective_model,
            "anthropic" if use_anthropic else "openai",
        )
        return cleaned

    except Exception:
        logger.exception("Quote cleanup failed; returning original texts")
        for qid in originals:
            cleaned.setdefault(qid, originals[qid])
        return cleaned


# ── Worker-side cleanup: operates on Parsed JSON dict directly ────────────────


def cleanup_parsed_json(parsed: dict, model: Optional[str] = None) -> None:
    """Clean evidence_span excerpts and coaching blurbs in a Parsed JSON dict.

    Mutates *parsed* in-place so the cleaned text is persisted to Airtable.
    Called from the Celery worker after LLM analysis completes.

    This handles all text that lives in the Parsed JSON:
    - evidence_spans[].excerpt  (transcript quotes)
    - coaching_output.strengths[].message
    - coaching_output.focus[].message / .suggested_rewrite
    - pattern_snapshot[].notes / .coaching_note / .suggested_rewrite
    - experiment_tracking.detection_in_this_meeting.coaching_note / .suggested_rewrite
    """
    cleanup_input: list[dict] = []

    # 1. Collect evidence_span excerpts
    spans = parsed.get("evidence_spans", [])
    for i, span in enumerate(spans):
        excerpt = span.get("excerpt")
        if excerpt:
            cleanup_input.append({
                "id": f"span:{i}",
                "text": excerpt,
                "category": "transcript_quote",
            })

    # 2. Collect coaching blurbs
    coaching = parsed.get("coaching_output", {})
    for i, s in enumerate(coaching.get("strengths", [])):
        if s.get("message"):
            cleanup_input.append({"id": f"str:{i}:msg", "text": s["message"], "category": "coaching_blurb"})

    for i, f in enumerate(coaching.get("focus", [])):
        if f.get("message"):
            cleanup_input.append({"id": f"foc:{i}:msg", "text": f["message"], "category": "coaching_blurb"})
        if f.get("suggested_rewrite"):
            cleanup_input.append({"id": f"foc:{i}:rw", "text": f["suggested_rewrite"], "category": "coaching_blurb"})

    snapshot = parsed.get("pattern_snapshot", [])
    for i, ps in enumerate(snapshot):
        if ps.get("notes"):
            cleanup_input.append({"id": f"snap:{i}:notes", "text": ps["notes"], "category": "coaching_blurb"})
        if ps.get("coaching_note"):
            cleanup_input.append({"id": f"snap:{i}:cn", "text": ps["coaching_note"], "category": "coaching_blurb"})
        if ps.get("suggested_rewrite"):
            cleanup_input.append({"id": f"snap:{i}:rw", "text": ps["suggested_rewrite"], "category": "coaching_blurb"})

    exp_track = parsed.get("experiment_tracking", {})
    detection = exp_track.get("detection_in_this_meeting")
    if isinstance(detection, dict):
        if detection.get("coaching_note"):
            cleanup_input.append({"id": "det:cn", "text": detection["coaching_note"], "category": "coaching_blurb"})
        if detection.get("suggested_rewrite"):
            cleanup_input.append({"id": "det:rw", "text": detection["suggested_rewrite"], "category": "coaching_blurb"})

    if not cleanup_input:
        return

    logger.info("Worker cleanup: %d items to clean", len(cleanup_input))
    cleanup_input_by_id = {q["id"]: q["text"] for q in cleanup_input}
    result = cleanup_quotes(cleanup_input, model=model)

    # 3. Write cleaned text back into the parsed dict
    for i, span in enumerate(spans):
        key = f"span:{i}"
        if key in result:
            span["excerpt"] = result[key]

    for i, s in enumerate(coaching.get("strengths", [])):
        key = f"str:{i}:msg"
        if key in result:
            s["message"] = result[key]

    for i, f in enumerate(coaching.get("focus", [])):
        msg_key = f"foc:{i}:msg"
        if msg_key in result:
            f["message"] = result[msg_key]
        rw_key = f"foc:{i}:rw"
        if rw_key in result:
            f["suggested_rewrite"] = result[rw_key]

    for i, ps in enumerate(snapshot):
        notes_key = f"snap:{i}:notes"
        if notes_key in result:
            ps["notes"] = result[notes_key]
        cn_key = f"snap:{i}:cn"
        if cn_key in result:
            ps["coaching_note"] = result[cn_key]
        rw_key = f"snap:{i}:rw"
        if rw_key in result:
            ps["suggested_rewrite"] = result[rw_key]

    if isinstance(detection, dict):
        if "det:cn" in result:
            detection["coaching_note"] = result["det:cn"]
        if "det:rw" in result:
            detection["suggested_rewrite"] = result["det:rw"]

    actually_cleaned = sum(1 for qid, text in result.items() if text != cleanup_input_by_id.get(qid))
    logger.info("Worker cleanup: done, %d/%d items cleaned", actually_cleaned, len(result))
