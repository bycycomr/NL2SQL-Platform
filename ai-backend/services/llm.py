"""LLM service – provider-aware Chat model factory with retries."""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional dependency fallback
    ChatOpenAI = None

from core.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton (lazy-initialised on first call)
_llm_instance: Any | None = None


def _has_real_openai_key() -> bool:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return False
    placeholders = (
        "sk-your-openai-api-key-here",
        "your-openai-api-key",
        "changeme",
    )
    lowered = api_key.lower()
    return not any(placeholder in lowered for placeholder in placeholders)


def _resolve_provider() -> str:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider in {"openai", "ollama"}:
        return provider

    if _has_real_openai_key():
        return "openai"

    return "ollama"


def get_llm() -> Any:
    """Return configured LLM client based on provider settings."""
    global _llm_instance

    if _llm_instance is None:
        provider = _resolve_provider()

        if provider == "openai":
            if ChatOpenAI is None:
                raise RuntimeError(
                    "LLM provider is openai but langchain-openai is not installed."
                )
            if not _has_real_openai_key():
                raise RuntimeError(
                    "OPENAI_API_KEY is missing/placeholder. Set a valid key in .env."
                )

            _llm_instance = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                timeout=settings.LLM_REQUEST_TIMEOUT,
                max_retries=settings.LLM_MAX_RETRIES,
                api_key=os.getenv("OPENAI_API_KEY", "").strip(),
                base_url=settings.OPENAI_BASE_URL,
            )
            logger.info(
                "LLM initialized | provider=openai | model=%s | timeout=%s | retries=%s",
                settings.OPENAI_MODEL,
                settings.LLM_REQUEST_TIMEOUT,
                settings.LLM_MAX_RETRIES,
            )
        else:
            _llm_instance = ChatOllama(
                model=settings.LLM_MODEL,
                base_url=settings.LLM_BASE_URL,
                temperature=settings.LLM_TEMPERATURE,
                timeout=settings.LLM_REQUEST_TIMEOUT,
                num_predict=1024,
            )
            logger.info(
                "LLM initialized | provider=ollama | model=%s | base_url=%s | timeout=%s | retries=%s",
                settings.LLM_MODEL,
                settings.LLM_BASE_URL,
                settings.LLM_REQUEST_TIMEOUT,
                settings.LLM_MAX_RETRIES,
            )

    return _llm_instance


async def ainvoke_with_retry(messages: list[BaseMessage]):
    """Invoke LLM with exponential backoff retries."""
    llm = get_llm()

    retryer = AsyncRetrying(
        reraise=True,
        stop=stop_after_attempt(max(1, settings.LLM_MAX_RETRIES)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
    )

    async for attempt in retryer:
        with attempt:
            return await llm.ainvoke(messages)

    raise RuntimeError("LLM invocation failed after retries")
