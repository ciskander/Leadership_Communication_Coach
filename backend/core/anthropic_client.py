"""
anthropic_client.py — Anthropic SDK wrapper with retry logic.

Mirrors the call_openai() interface so it can be used as a drop-in alternative.

Key difference from OpenAI: Anthropic has no "developer" role. The developer
message (taxonomy/rubrics) is prepended to the system prompt, separated by a
clear delimiter.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import anthropic

from .config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_JSON_REPAIR_MODEL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_READ_TIMEOUT,
    ANTHROPIC_READ_TIMEOUT_OPUS,
    ANTHROPIC_RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)
from .models import OpenAIResponse  # reused as provider-agnostic response type

logger = logging.getLogger(__name__)


def _timeout_for_model(model: str) -> float:
    """Return the appropriate read timeout for the given model."""
    if "opus" in model.lower():
        return ANTHROPIC_READ_TIMEOUT_OPUS
    return ANTHROPIC_READ_TIMEOUT


def _make_client(api_key: Optional[str] = None, model: str = "") -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=api_key or ANTHROPIC_API_KEY,
        timeout=anthropic.Timeout(timeout=_timeout_for_model(model), connect=10.0),
        max_retries=0,  # we handle retries ourselves for consistency with OpenAI path
    )


def _backoff(attempt: int) -> float:
    """Exponential backoff with ±25% jitter."""
    import random
    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
    jitter = delay * 0.25 * (2 * random.random() - 1)
    return delay + jitter


def _build_system_message(system_prompt: str, developer_message: str) -> list[dict]:
    """Combine system prompt and developer message into cached content blocks.

    Anthropic has no "developer" role. The developer message (taxonomy, rubrics)
    is appended after the system prompt with a clear delimiter so the model treats
    it with high priority.

    Both blocks are marked with cache_control={"type": "ephemeral"} so that
    Anthropic's prompt caching keeps them in cache across consecutive calls
    (5-minute TTL). Only the user message (transcript) changes per call,
    so subsequent calls pay ~90% less for input tokens.
    """
    blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    if developer_message:
        blocks.append({
            "type": "text",
            "text": (
                "─── TAXONOMY & EVALUATION RUBRICS (apply these strictly) ───\n\n"
                f"{developer_message}"
            ),
            "cache_control": {"type": "ephemeral"},
        })

    return blocks


def _extract_json(raw_text: str) -> dict:
    """Try progressively harder strategies to extract JSON from raw model output.

    Strategy order:
      1. Direct parse (model returned clean JSON)
      2. Strip markdown fences (```json ... ```)
      3. Find outermost { ... } braces (handles prose preamble/postamble)

    Raises json.JSONDecodeError if all strategies fail.
    """
    text = raw_text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            inner = part.strip()
            if inner.lower().startswith("json"):
                inner = inner[4:].strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                continue

    # Strategy 3: find outermost braces
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # All strategies failed — raise with the original text
    raise json.JSONDecodeError(
        "No valid JSON found after all extraction strategies",
        text[:200],
        0,
    )


def _repair_json_via_llm(raw_text: str, api_key: Optional[str] = None) -> dict:
    """Send malformed output to a fast model for JSON extraction.

    Uses ANTHROPIC_JSON_REPAIR_MODEL (default: claude-sonnet-4-6) with a short
    timeout. This is a reformatting task, not a reasoning task.

    Raises ValueError if repair also fails.
    """
    repair_model = ANTHROPIC_JSON_REPAIR_MODEL
    logger.info("Attempting JSON repair via %s", repair_model)

    repair_client = anthropic.Anthropic(
        api_key=api_key or ANTHROPIC_API_KEY,
        timeout=anthropic.Timeout(timeout=60.0, connect=10.0),
        max_retries=0,
    )

    repair_response = repair_client.messages.create(
        model=repair_model,
        system=(
            "You are a JSON extraction tool. The user will provide text that "
            "contains a JSON object. Extract ONLY the JSON object and return it "
            "with no other text, no markdown fences, no explanation. "
            "Do not modify any values — only fix structural issues "
            "(missing commas, trailing commas, unescaped quotes)."
        ),
        messages=[{"role": "user", "content": raw_text}],
        max_tokens=ANTHROPIC_MAX_TOKENS,
    )

    repair_text = ""
    for block in repair_response.content:
        if block.type == "text":
            repair_text = block.text
            break

    try:
        parsed = _extract_json(repair_text)
        logger.info("JSON repair succeeded via %s", repair_model)
        return parsed
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON repair via {repair_model} also failed: {repair_text[:200]}"
        ) from exc


def call_anthropic(
    *,
    system_prompt: str,
    developer_message: str,
    user_message: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
) -> OpenAIResponse:
    """
    Call the Anthropic API with the same three-layer message structure as call_openai.

    The system_prompt and developer_message are combined into the system parameter.
    The user_message is sent as the user role.

    Returns:
        OpenAIResponse (provider-agnostic) with parsed JSON dict and metadata.

    Raises:
        anthropic.APIError: After all retries exhausted.
    """
    effective_model = model or "claude-sonnet-4-6"
    client = _make_client(api_key, model=effective_model)
    effective_max_tokens = max_tokens or ANTHROPIC_MAX_TOKENS

    combined_system = _build_system_message(system_prompt, developer_message)

    messages = [{"role": "user", "content": user_message}]

    last_exc: Optional[Exception] = None
    for attempt in range(ANTHROPIC_RETRY_ATTEMPTS):
        try:
            logger.info(
                "Anthropic call attempt %d/%d model=%s",
                attempt + 1, ANTHROPIC_RETRY_ATTEMPTS, effective_model,
            )
            response = client.messages.create(
                model=effective_model,
                system=combined_system,
                messages=messages,
                max_tokens=effective_max_tokens,
                thinking={"type": "adaptive"},
            )

            # Extract text content from response blocks
            raw_text = ""
            for block in response.content:
                if block.type == "text":
                    raw_text = block.text
                    break

            if not raw_text.strip():
                raise ValueError(
                    f"Anthropic returned empty response content (stop_reason={response.stop_reason})"
                )

            # Extract JSON — tries direct parse, fence stripping, brace matching
            try:
                parsed = _extract_json(raw_text)
            except json.JSONDecodeError:
                # Layer 2: one repair call via a fast model
                logger.warning(
                    "JSON extraction failed on attempt %d; raw_text[:200]=%s",
                    attempt + 1, raw_text[:200],
                )
                parsed = _repair_json_via_llm(raw_text, api_key)

            usage = response.usage
            cache_created = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            if cache_read > 0:
                logger.info(
                    "Anthropic cache HIT: %d tokens read from cache, %d created",
                    cache_read, cache_created,
                )
            elif cache_created > 0:
                logger.info(
                    "Anthropic cache MISS (warming): %d tokens written to cache",
                    cache_created,
                )

            return OpenAIResponse(
                parsed=parsed,
                raw_text=raw_text,
                model=effective_model,
                prompt_tokens=usage.input_tokens if usage else 0,
                completion_tokens=usage.output_tokens if usage else 0,
                total_tokens=(
                    (usage.input_tokens + usage.output_tokens) if usage else 0
                ),
                cache_creation_input_tokens=cache_created,
                cache_read_input_tokens=cache_read,
            )

        except anthropic.RateLimitError as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning(
                "Anthropic 429 RateLimitError on attempt %d; sleeping %.1fs",
                attempt + 1, wait,
            )
            time.sleep(wait)
        except anthropic.APIStatusError as exc:
            if exc.status_code in {429, 500, 502, 503, 504, 529}:
                last_exc = exc
                wait = _backoff(attempt)
                logger.warning(
                    "Anthropic status %d on attempt %d; sleeping %.1fs",
                    exc.status_code, attempt + 1, wait,
                )
                time.sleep(wait)
            else:
                raise
        except anthropic.APITimeoutError as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning(
                "Anthropic timeout on attempt %d; sleeping %.1fs",
                attempt + 1, wait,
            )
            time.sleep(wait)
        except anthropic.APIConnectionError as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning(
                "Anthropic connection error on attempt %d; sleeping %.1fs",
                attempt + 1, wait,
            )
            time.sleep(wait)
        except (json.JSONDecodeError, ValueError) as exc:
            # Extraction + repair both failed — not retryable
            logger.error(
                "Anthropic JSON extraction and repair failed on attempt %d: %s; raw_text[:500]=%s",
                attempt + 1, exc, raw_text[:500],
            )
            raise
        except Exception:
            raise

    raise last_exc or RuntimeError("Anthropic call failed after all retries.")
