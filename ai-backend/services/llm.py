"""LLM service – provider-aware Chat model factory with retries."""
from __future__ import annotations

import asyncio
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

# Module-level singletons (lazy-initialised on first call)
_llm_instance: Any | None = None
_fast_llm_instance: Any | None = None  # hafif model — basit sorgular için

# Ollama tek thread'de çalışır; aynı anda yalnızca 1 LLM çağrısına izin ver.
# Eş zamanlı istekler kuyrukta bekler, "Remote end closed" almaz.
_ollama_semaphore = asyncio.Semaphore(1)

# Basit sorgu tespiti için anahtar kelimeler
_SIMPLE_KEYWORDS = frozenset([
    "kaç", "kac", "count", "toplam", "sayı", "say", "how many", "total",
    "liste", "listele", "göster", "var mi", "var mı", "en yüksek", "en dusuk",
    "minimum", "maximum", "avg", "ortalama",
])
_COMPLEX_KEYWORDS = frozenset([
    "join", "birleştir", "grupla", "group", "subquery", "alt sorgu",
    "pivot", "having", "window", "rank", "partition",
])


def estimate_complexity(question: str, schema_text: str = "") -> str:
    """Sorunun karmaşıklığını tahmin et: 'simple' veya 'complex'.

    Basit: tek tablo, COUNT/SUM, filtreleme yok veya tek koşul.
    Karmaşık: birden fazla tablo, JOIN, GROUP BY, alt sorgu.
    """
    q = question.lower()
    s = schema_text.lower()

    # Karmaşık işaret varsa hemen complex
    if any(kw in q for kw in _COMPLEX_KEYWORDS):
        return "complex"

    # Şemada birden fazla tablo geçiyor ve sorgu ilişkisel görünüyorsa complex
    table_count = s.count("table:")
    if table_count > 2 and len(q.split()) > 8:
        return "complex"

    # Basit anahtar kelime varsa simple
    if any(kw in q for kw in _SIMPLE_KEYWORDS) and table_count <= 2:
        return "simple"

    # Kısa soru genellikle basittir
    if len(q.split()) <= 6:
        return "simple"

    return "complex"


def _create_ollama_client(model_name: str) -> ChatOllama:
    """Create a ChatOllama client with shared runtime settings."""
    return ChatOllama(
        model=model_name,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_REQUEST_TIMEOUT,
        num_predict=1024,
    )


def _is_ollama_memory_error(exc: Exception) -> bool:
    """Detect Ollama memory pressure errors from exception text."""
    msg = str(exc).lower()
    return "model requires more system memory" in msg or "insufficient memory" in msg


def _fallback_model_candidates(current_model: str) -> list[str]:
    """Return fallback model candidates ordered by preference.

    Override with env: OLLAMA_FALLBACK_MODELS=model1,model2,...
    """
    raw = os.getenv("OLLAMA_FALLBACK_MODELS", "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        models = [
            "qwen3.5:4b",
            "llama3.2:3b",
            "deepseek-r1:1.5b",
        ]
    return [m for m in models if m != current_model]


def _try_switch_ollama_model(exc: Exception) -> bool:
    """Switch to a smaller Ollama model when memory error is detected.

    Returns True if model switch succeeded, otherwise False.
    """
    global _llm_instance

    if not _is_ollama_memory_error(exc):
        return False

    if not isinstance(_llm_instance, ChatOllama):
        return False

    current_model = getattr(_llm_instance, "model", settings.LLM_MODEL)
    for candidate in _fallback_model_candidates(current_model):
        try:
            _llm_instance = _create_ollama_client(candidate)
            logger.warning(
                "LLM memory fallback activated | from=%s | to=%s",
                current_model,
                candidate,
            )
            return True
        except Exception:
            logger.exception("Failed to create fallback Ollama client | model=%s", candidate)

    logger.error("No usable fallback Ollama model found after memory error")
    return False


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


def get_fast_llm() -> Any:
    """Basit sorgular için hafif/hızlı Ollama modeli döndür."""
    global _fast_llm_instance
    if _fast_llm_instance is None:
        fast_model = settings.LLM_FAST_MODEL
        if fast_model and fast_model != settings.LLM_MODEL:
            _fast_llm_instance = _create_ollama_client(fast_model)
            logger.info("Fast LLM initialized | model=%s", fast_model)
        else:
            # Fast model tanımlı değilse ana modeli kullan
            _fast_llm_instance = get_llm()
    return _fast_llm_instance


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
            _llm_instance = _create_ollama_client(settings.LLM_MODEL)
            logger.info(
                "LLM initialized | provider=ollama | model=%s | base_url=%s | timeout=%s | retries=%s",
                settings.LLM_MODEL,
                settings.LLM_BASE_URL,
                settings.LLM_REQUEST_TIMEOUT,
                settings.LLM_MAX_RETRIES,
            )

    return _llm_instance


async def ainvoke_with_retry(messages: list[BaseMessage], complexity: str = "complex"):
    """Invoke LLM with exponential backoff retries.

    Concurrent requests are serialised via ``_ollama_semaphore`` so that
    Ollama (single-threaded) is never overwhelmed and callers queue cleanly
    instead of receiving connection-reset errors.

    complexity='simple' → hafif/hızlı model (LLM_FAST_MODEL)
    complexity='complex' → ana model (LLM_MODEL)
    """
    async with _ollama_semaphore:
        llm = get_fast_llm() if complexity == "simple" else get_llm()
        logger.info("ainvoke_with_retry | complexity=%s | model=%s", complexity, getattr(llm, "model", "?"))

        retryer = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(max(1, settings.LLM_MAX_RETRIES)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(Exception),
        )

        async for attempt in retryer:
            with attempt:
                try:
                    return await llm.ainvoke(messages)
                except Exception as exc:
                    switched = _try_switch_ollama_model(exc)
                    if switched:
                        llm = get_llm()
                        return await llm.ainvoke(messages)
                    raise

    raise RuntimeError("LLM invocation failed after retries")
