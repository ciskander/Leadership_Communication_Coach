"""
quote_cleanup.py — Post-processing cleanup of evidence span quotes.

Runs a lightweight LLM call to clean up ASR transcript artifacts in evidence
quotes before they are displayed to the user. This is separate from the main
analysis prompt to keep concerns cleanly separated.

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

from .config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Use a smaller/cheaper model for cleanup by default.
CLEANUP_MODEL: str = os.getenv("QUOTE_CLEANUP_MODEL", "gpt-4o-mini")

# Max quotes per LLM batch to avoid token truncation.
_BATCH_SIZE: int = 10

# Timeout for each cleanup LLM call (seconds).
_CLEANUP_TIMEOUT: float = 15.0

# Simple in-memory cache: hash(quote_text + abbreviate) -> cleaned_text.
# Survives for the lifetime of the process, cleared on restart.
_cache: dict[str, str] = {}

_CLEANUP_SYSTEM_PROMPT = """You are a transcript quote cleanup assistant. Your job is to lightly clean up quotes from automatic speech recognition (ASR) transcripts to improve readability.

You will receive a JSON array of quote objects. For each quote, apply ONLY these cleanup operations:

1. PUNCTUATION: Insert periods, commas, question marks, and other punctuation where clearly needed for readability. Capitalize the first word of sentences.
2. FILLER REMOVAL: Remove filler words (um, uh, er, ah, you know, I mean, like when used as filler) ONLY when they add no meaning.
3. DUPLICATE REMOVAL: Remove obviously duplicated words or phrases caused by speech disfluency (e.g., "from the from the" → "from the").
4. SINGLE QUOTES: Where a word or phrase is clearly being referenced as a title, label, or named concept, wrap it in single quotes for clarity (e.g., Engine 17 → 'Engine 17' when it is being named as a specific thing, but NOT when it is part of natural speech like "I drove Engine 17").

STRICT RULES — DO NOT VIOLATE:
- Do NOT paraphrase, reword, or substitute any words.
- Do NOT add words that were not in the original (except punctuation marks and single quotes).
- Do NOT remove words that carry meaning — only remove clear filler and exact duplicates.
- Do NOT change the speaker's phrasing, vocabulary, or sentence structure.
- Do NOT correct grammar (e.g., do not fix subject-verb agreement or tense).
- If a quote is too short or garbled to meaningfully clean up, return it unchanged.
- Preserve the exact JSON structure. Return a JSON array with the same number of objects.

For NON-TARGET speaker quotes in multi-speaker spans (marked with "abbreviate": true):
- Keep the first ~1-2 sentences and the last ~1-2 sentences of the quote.
- Replace the removed middle portion with " [...] " (space, brackets, ellipsis, space).
- Keep enough text at the start and end to preserve clear context for what the target speaker was responding to.
- If the quote is already short (under ~40 words), do not abbreviate — return it with only the standard cleanup.

Return ONLY a JSON array. No prose, no explanation."""

_CLEANUP_USER_TEMPLATE = """Clean up the following transcript quotes. Return a JSON array with the same structure.

{quotes_json}"""


def _cache_key(text: str, abbreviate: bool) -> str:
    """Deterministic cache key for a quote."""
    raw = f"{text}|{abbreviate}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _call_cleanup_batch(
    batch: list[dict],
    client: openai.OpenAI,
    effective_model: str,
) -> dict[str, str]:
    """Send a single batch of quotes to the LLM and return {id: cleaned_text}."""
    payload = [
        {"id": q["id"], "text": q["text"], "abbreviate": q.get("abbreviate", False)}
        for q in batch
    ]

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
        max_completion_tokens=8192,
        response_format={"type": "json_object"},
        temperature=0.0,
        timeout=_CLEANUP_TIMEOUT,
    )

    raw = response.choices[0].message.content or ""
    parsed = json.loads(raw)

    # Handle both {"quotes": [...]} and bare [...] formats
    if isinstance(parsed, dict):
        result_list = parsed.get("quotes", parsed.get("results", []))
    elif isinstance(parsed, list):
        result_list = parsed
    else:
        return {}

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
        client = openai.OpenAI(
            api_key=api_key or OPENAI_API_KEY,
            timeout=openai.Timeout(timeout=_CLEANUP_TIMEOUT, connect=5.0),
        )
        effective_model = model or CLEANUP_MODEL

        # Process in batches
        for i in range(0, len(uncached), _BATCH_SIZE):
            batch = uncached[i : i + _BATCH_SIZE]
            try:
                batch_result = _call_cleanup_batch(batch, client, effective_model)
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
            "Quote cleanup completed: %d/%d quotes cleaned, model=%s",
            sum(1 for qid in cleaned if cleaned[qid] != originals.get(qid)),
            len(originals),
            effective_model,
        )
        return cleaned

    except Exception:
        logger.exception("Quote cleanup failed; returning original texts")
        for qid in originals:
            cleaned.setdefault(qid, originals[qid])
        return cleaned
