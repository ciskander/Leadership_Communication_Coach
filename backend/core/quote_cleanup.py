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

# Max quotes per LLM batch. Set high — individual turn texts are short and
# 50 quotes easily fits within gpt-4o-mini / haiku context.  The previous
# value of 10 caused 5 sequential API calls for ~41 quotes, creating the
# timeout cascade.  A single call with all quotes is faster and more reliable.
_BATCH_SIZE: int = 200

# Timeout for each cleanup LLM call (seconds).
# With max_retries=0 on the client, this is a hard per-request cap.
# 60s accommodates larger batches (150+ items) through Anthropic models.
_CLEANUP_TIMEOUT: float = 60.0

# Total wall-clock budget for the entire cleanup operation (seconds).
# If we exceed this, skip remaining batches rather than blocking the response.
_TOTAL_BUDGET: float = 65.0

# Simple in-memory cache: hash(quote_text + abbreviate) -> cleaned_text.
# Survives for the lifetime of the process, cleared on restart.
_cache: dict[str, str] = {}

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

    Splits into batches of _BATCH_SIZE, uses an in-memory cache to skip
    previously cleaned quotes, and applies a per-batch timeout.

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

    # Check cache first, build list of uncached quotes
    uncached: list[dict] = []
    for q in quotes:
        ck = _cache_key(q["text"], q.get("abbreviate", False))
        if ck in _cache:
            cleaned[q["id"]] = _cache[ck]
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
            try:
                if use_anthropic:
                    batch_result = _call_cleanup_batch_anthropic(batch, effective_model, api_key)
                else:
                    batch_result = _call_cleanup_batch_openai(batch, effective_model, api_key)
                # Write results and populate cache
                for q in batch:
                    qid = q["id"]
                    if qid in batch_result:
                        cleaned[qid] = batch_result[qid]
                        ck = _cache_key(q["text"], q.get("abbreviate", False))
                        _cache[ck] = batch_result[qid]
                    # else: will be filled from originals below
            except Exception:
                logger.warning(
                    "Quote cleanup batch %d-%d failed; skipping",
                    i, i + len(batch),
                    exc_info=True,
                )
                # This batch fails; remaining batches still get attempted.

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
