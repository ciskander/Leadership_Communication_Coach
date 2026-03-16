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

import json
import logging
from typing import Optional

from .config import OPENAI_API_KEY, OPENAI_MODEL_DEFAULT

logger = logging.getLogger(__name__)

# Use a smaller/cheaper model for cleanup by default.
# Can be overridden via environment variable.
import os

CLEANUP_MODEL: str = os.getenv("QUOTE_CLEANUP_MODEL", "gpt-4o-mini")

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


def _build_cleanup_payload(
    quotes: list[dict],
) -> list[dict]:
    """Build the payload for the cleanup LLM call.

    Each dict in quotes should have:
        - "text": the quote text to clean
        - "abbreviate": bool (True for non-target speakers in multi-speaker spans)
        - "id": a unique identifier to match results back
    """
    return [
        {"id": q["id"], "text": q["text"], "abbreviate": q.get("abbreviate", False)}
        for q in quotes
    ]


def cleanup_quotes(
    quotes: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict[str, str]:
    """Clean up a batch of quote texts via a lightweight LLM call.

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

    # Build the original mapping as fallback
    originals = {q["id"]: q["text"] for q in quotes}

    try:
        import openai

        client = openai.OpenAI(api_key=api_key or OPENAI_API_KEY)
        effective_model = model or CLEANUP_MODEL

        payload = _build_cleanup_payload(quotes)

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
            max_completion_tokens=4096,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw = response.choices[0].message.content or ""
        parsed = json.loads(raw)

        # Handle both {"quotes": [...]} and bare [...] formats
        if isinstance(parsed, dict):
            result_list = parsed.get("quotes", parsed.get("results", []))
        elif isinstance(parsed, list):
            result_list = parsed
        else:
            logger.warning("Quote cleanup returned unexpected type: %s", type(parsed))
            return originals

        # Map results back by id
        cleaned = {}
        for item in result_list:
            qid = item.get("id")
            text = item.get("text")
            if qid and text and qid in originals:
                cleaned[qid] = text

        # Fill in any missing IDs with originals
        for qid in originals:
            if qid not in cleaned:
                cleaned[qid] = originals[qid]

        logger.info(
            "Quote cleanup completed: %d quotes processed, model=%s",
            len(cleaned),
            effective_model,
        )
        return cleaned

    except Exception:
        logger.exception("Quote cleanup failed; returning original texts")
        return originals
