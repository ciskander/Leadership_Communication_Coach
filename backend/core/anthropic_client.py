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
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_READ_TIMEOUT,
    ANTHROPIC_READ_TIMEOUT_OPUS,
    RETRY_ATTEMPTS,
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


def _build_system_message(system_prompt: str, developer_message: str) -> str:
    """Combine system prompt and developer message into a single system parameter.

    Anthropic has no "developer" role. The developer message (taxonomy, rubrics)
    is appended after the system prompt with a clear delimiter so the model treats
    it with high priority.
    """
    if not developer_message:
        return system_prompt

    return (
        f"{system_prompt}\n\n"
        "─── TAXONOMY & EVALUATION RUBRICS (apply these strictly) ───\n\n"
        f"{developer_message}"
    )


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
    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info(
                "Anthropic call attempt %d/%d model=%s",
                attempt + 1, RETRY_ATTEMPTS, effective_model,
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

            # Strip markdown fences if present (Claude sometimes wraps JSON)
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                parts = cleaned.split("```")
                # Take the first code block content
                if len(parts) >= 3:
                    inner = parts[1]
                    # Remove optional language tag (e.g., "json\n")
                    if inner.startswith("json"):
                        inner = inner[4:]
                    cleaned = inner.strip()

            parsed = json.loads(cleaned)

            usage = response.usage
            return OpenAIResponse(
                parsed=parsed,
                raw_text=raw_text,
                model=effective_model,
                prompt_tokens=usage.input_tokens if usage else 0,
                completion_tokens=usage.output_tokens if usage else 0,
                total_tokens=(
                    (usage.input_tokens + usage.output_tokens) if usage else 0
                ),
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
        except json.JSONDecodeError as exc:
            # JSON parse failure is not retryable — the model returned bad output
            raise ValueError(
                f"Anthropic returned non-JSON response: {raw_text[:200]}"
            ) from exc
        except Exception:
            raise

    raise last_exc or RuntimeError("Anthropic call failed after all retries.")
