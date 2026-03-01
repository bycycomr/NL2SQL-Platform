"""
Vector store service – ChromaDB integration for multi-tenant RAG.

Each database's schema chunks are stored with ``db_id`` metadata so they can
be filtered at query time.
"""
from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_client: chromadb.ClientAPI | None = None
_COLLECTION_NAME = "nl2sql_schemas"


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.Client(
            ChromaSettings(
                anonymized_telemetry=False,
                persist_directory=settings.CHROMA_PERSIST_DIR,
            )
        )
    return _client


def _get_collection() -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def save_schema_chunks(
    db_id: str,
    tables: list[dict[str, Any]],
    few_shot_examples: list[dict] | None = None,
) -> int:
    """Upsert table DDL chunks (and optional few-shot examples) into ChromaDB.

    Each table becomes one document.  ``db_id`` is stored as metadata for
    filtering.  Returns the number of documents saved.
    """
    collection = _get_collection()

    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for table in tables:
        doc = _table_to_text(table)
        documents.append(doc)
        metadatas.append({"db_id": db_id, "type": "table_schema"})
        ids.append(f"{db_id}_{table['name']}")

    # Optional few-shot examples as extra documents
    if few_shot_examples:
        for idx, example in enumerate(few_shot_examples):
            doc = f"Question: {example.get('question', '')}\nSQL: {example.get('sql', '')}"
            documents.append(doc)
            metadatas.append({"db_id": db_id, "type": "few_shot"})
            ids.append(f"{db_id}_fewshot_{idx}")

    collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    logger.info("save_schema_chunks | db_id=%s | saved %d docs", db_id, len(documents))
    return len(documents)


def retrieve_relevant_schema(db_id: str, question: str, top_k: int = 10) -> str:
    """Semantic search over stored schema chunks filtered by *db_id*.

    Returns a single string of concatenated schema text suitable for injection
    into the LLM prompt.
    """
    collection = _get_collection()

    results = collection.query(
        query_texts=[question],
        n_results=top_k,
        where={"db_id": db_id},
    )

    if not results or not results["documents"] or not results["documents"][0]:
        logger.warning("retrieve_relevant_schema | no results for db_id=%s", db_id)
        return ""

    combined = "\n\n".join(results["documents"][0])
    logger.info(
        "retrieve_relevant_schema | db_id=%s | returned %d chunks",
        db_id,
        len(results["documents"][0]),
    )
    return combined


def delete_schema(db_id: str) -> None:
    """Remove all schema chunks for a given *db_id*."""
    collection = _get_collection()
    # ChromaDB requires IDs for deletion; query first
    results = collection.get(where={"db_id": db_id})
    if results and results["ids"]:
        collection.delete(ids=results["ids"])
        logger.info("delete_schema | db_id=%s | removed %d docs", db_id, len(results["ids"]))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _table_to_text(table: dict[str, Any]) -> str:
    """Convert a table dict to a DDL-like text chunk."""
    lines = [f"TABLE: {table['name']}"]
    lines.append(f"COLUMNS: {', '.join(table.get('columns', []))}")
    if table.get("human_description"):
        lines.append(f"DESCRIPTION: {table['human_description']}")
    if table.get("business_rules"):
        lines.append(f"BUSINESS RULES: {table['business_rules']}")
    return "\n".join(lines)
