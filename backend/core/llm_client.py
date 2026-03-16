"""
llm_client.py — Provider-agnostic LLM routing.

Inspects the model name to decide whether to call OpenAI or Anthropic.
The Airtable config "Model Name" field controls which provider is used at runtime.

Usage:
    from .llm_client import call_llm

    resp = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=user_msg,
        model="claude-sonnet-4-6",   # or "gpt-5.2-chat-latest"
    )
"""
from __future__ import annotations

import logging
from typing import Optional

from .models import OpenAIResponse

logger = logging.getLogger(__name__)

# Model name prefixes that route to Anthropic
_ANTHROPIC_PREFIXES = ("claude-",)


def is_anthropic_model(model: Optional[str]) -> bool:
    """Check if a model name should be routed to the Anthropic provider."""
    if not model:
        return False
    return any(model.lower().startswith(p) for p in _ANTHROPIC_PREFIXES)


def call_llm(
    *,
    system_prompt: str,
    developer_message: str,
    user_message: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
) -> OpenAIResponse:
    """Route an LLM call to the appropriate provider based on model name.

    If model starts with "claude-", routes to Anthropic. Otherwise, routes to OpenAI.
    The return type is the same regardless of provider.
    """
    if is_anthropic_model(model):
        from .anthropic_client import call_anthropic

        logger.info("Routing to Anthropic provider (model=%s)", model)
        return call_anthropic(
            system_prompt=system_prompt,
            developer_message=developer_message,
            user_message=user_message,
            model=model,
            max_tokens=max_tokens,
            api_key=api_key,
        )
    else:
        from .openai_client import call_openai

        logger.info("Routing to OpenAI provider (model=%s)", model)
        return call_openai(
            system_prompt=system_prompt,
            developer_message=developer_message,
            user_message=user_message,
            model=model,
            max_tokens=max_tokens,
            api_key=api_key,
        )
