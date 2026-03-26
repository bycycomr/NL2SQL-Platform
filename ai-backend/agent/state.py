"""
AgentState TypedDict — LangGraph pipeline'ı boyunca akan paylaşılan durum.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    # Kiracı ve bağlantı bilgileri
    db_id: str
    connection_string: str

    # Kullanıcı sorusu
    question: str

    # Pipeline ara değerleri
    relevant_schema: str          # ChromaDB'den çekilen şema metni
    generated_sql: str            # LLM'in ürettiği temiz SQL (LIMIT içermez)
    validation_error: str | None  # Doğrulama / çalıştırma hatası (varsa)
    explanation: str              # Türkçe açıklama
    execution_data: list[dict[str, Any]] | None  # Dry-run satırları (iç kullanım)
    retry_count: int              # Yeniden deneme sayacı

    # Contract v2.0 alanları
    dry_run_limit: int | None     # Dahili dry-run için satır limiti (opsiyonel)
    is_validated: bool            # SQL güvenlik + sözdizimi kontrolünden geçti mi
