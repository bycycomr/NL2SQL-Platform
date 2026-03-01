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
        default_factory=lambda: float(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
    )

    # --- Agent ---
    MAX_RETRY_COUNT: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRY_COUNT", "3"))
    )

    # --- ChromaDB ---
    CHROMA_PERSIST_DIR: str = field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", ".chroma_data")
    )

    # --- API ---
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )


# Singleton – importable from anywhere
settings = Settings()
