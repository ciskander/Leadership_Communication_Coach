"""
openai_client.py — OpenAI SDK wrapper with retry logic.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

import openai
from openai import OpenAI

from .config import (
    OPENAI_API_KEY,
    OPENAI_CONNECT_TIMEOUT,
    OPENAI_MAX_CONCURRENCY,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL_DEFAULT,
    OPENAI_READ_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)
from .models import OpenAIResponse

logger = logging.getLogger(__name__)

# Concurrency semaphore (shared per process)
_semaphore = asyncio.Semaphore(OPENAI_MAX_CONCURRENCY)

# Retryable status codes / exception types
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _make_client(api_key: Optional[str] = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or OPENAI_API_KEY,
        timeout=openai.Timeout(connect=OPENAI_CONNECT_TIMEOUT, read=OPENAI_READ_TIMEOUT),
    )


def _backoff(attempt: int) -> float:
    """Exponential backoff with ±25% jitter."""
    import random
    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
    jitter = delay * 0.25 * (2 * random.random() - 1)
    return delay + jitter


def call_openai(
    *,
    system_prompt: str,
    developer_message: str,
    user_message: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
) -> OpenAIResponse:
    """
    Call the OpenAI API with the three-layer message structure.
    
    Returns:
        OpenAIResponse with parsed JSON dict and metadata.
        
    Raises:
        openai.OpenAIError: After all retries exhausted.
    """
    client = _make_client(api_key)
    effective_model = model or OPENAI_MODEL_DEFAULT
    effective_max_tokens = max_tokens or OPENAI_MAX_TOKENS

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "developer", "content": developer_message},
        {"role": "user", "content": user_message},
    ]

    last_exc: Optional[Exception] = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info("OpenAI call attempt %d/%d model=%s", attempt + 1, RETRY_ATTEMPTS, effective_model)
            response = client.chat.completions.create(
                model=effective_model,
                messages=messages,
                max_tokens=effective_max_tokens,
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content or ""
            usage = response.usage

            import json
            parsed = json.loads(raw_text)

            return OpenAIResponse(
                parsed=parsed,
                raw_text=raw_text,
                model=response.model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            )

        except openai.RateLimitError as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning("OpenAI 429 RateLimitError on attempt %d; sleeping %.1fs", attempt + 1, wait)
            time.sleep(wait)
        except openai.APIStatusError as exc:
            if exc.status_code in _RETRYABLE_STATUS:
                last_exc = exc
                wait = _backoff(attempt)
                logger.warning(
                    "OpenAI status %d on attempt %d; sleeping %.1fs",
                    exc.status_code, attempt + 1, wait,
                )
                time.sleep(wait)
            else:
                raise
        except openai.APITimeoutError as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning("OpenAI timeout on attempt %d; sleeping %.1fs", attempt + 1, wait)
            time.sleep(wait)
        except (openai.APIConnectionError,) as exc:
            last_exc = exc
            wait = _backoff(attempt)
            logger.warning("OpenAI connection error on attempt %d; sleeping %.1fs", attempt + 1, wait)
            time.sleep(wait)
        except Exception:
            raise

    raise last_exc or RuntimeError("OpenAI call failed after all retries.")


def load_system_prompt(path: Optional[str] = None) -> str:
    """Load the system prompt from file or use the built-in path."""
    from pathlib import Path as P
    default_path = P(__file__).parent.parent.parent / "System_Prompt.txt"
    p = P(path) if path else default_path
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"System prompt not found at {p}")
