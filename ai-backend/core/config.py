"""
Core configuration – loads settings from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Application-wide settings, populated from environment variables."""

    # --- LLM ---
    LLM_PROVIDER: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "auto")
    )
    LLM_MODEL: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "llama3.1:8b-instruct-q4_K_M")
    )
    LLM_BASE_URL: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434")
    )
    LLM_TEMPERATURE: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.0"))
    )
    LLM_REQUEST_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("LLM_REQUEST_TIMEOUT", "180"))
    )
    LLM_MAX_RETRIES: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "4"))
    )
    OPENAI_MODEL: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    OPENAI_BASE_URL: str = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )

    # --- Agent ---
    MAX_RETRY_COUNT: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRY_COUNT", "3"))
    )

    # --- ChromaDB ---
    CHROMA_PERSIST_DIR: str = field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", ".chroma_data")
    )
    CHROMA_EMBEDDING_MODE: str = field(
        default_factory=lambda: os.getenv("CHROMA_EMBEDDING_MODE", "local_hash")
    )
    CHROMA_HTTP_VERIFY_SSL: bool = field(
        default_factory=lambda: os.getenv("CHROMA_HTTP_VERIFY_SSL", "true").lower() == "true"
    )
    CHROMA_HTTP_TRUST_ENV: bool = field(
        default_factory=lambda: os.getenv("CHROMA_HTTP_TRUST_ENV", "true").lower() == "true"
    )

    # --- API ---
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )


# Singleton – importable from anywhere
settings = Settings()
