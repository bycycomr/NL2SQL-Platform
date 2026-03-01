"""
LLM service – configures the ChatOllama binding for local Llama 3.1 inference.
"""
from __future__ import annotations

from langchain_ollama import ChatOllama

from core.config import settings

# Module-level singleton (lazy-initialised on first call)
_llm_instance: ChatOllama | None = None


def get_llm() -> ChatOllama:
    """Return a configured ChatOllama instance pointed at the local Ollama server.

    The instance is cached as a module-level singleton so every call
    shares the same HTTP session / connection pool.
    """
    global _llm_instance

    if _llm_instance is None:
        _llm_instance = ChatOllama(
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            timeout=settings.LLM_REQUEST_TIMEOUT,
            # Encourage deterministic, non-chatty output
            num_predict=1024,
        )

    return _llm_instance
