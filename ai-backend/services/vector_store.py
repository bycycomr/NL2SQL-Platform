"""
Vector store service – ChromaDB integration for multi-tenant RAG.

Each database's schema chunks are stored with ``db_id`` metadata so they can
be filtered at query time.
"""
from __future__ import annotations

import hashlib
import logging
import math
from contextlib import contextmanager
from typing import Any

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_client: chromadb.ClientAPI | None = None
_COLLECTION_NAME = "nl2sql_schemas"
_HASH_EMBEDDING_DIM = 256


class LocalHashEmbeddingFunction:
    """Network-free embedding function for offline and constrained environments."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in input]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * _HASH_EMBEDDING_DIM
        tokens = text.lower().split()

        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % _HASH_EMBEDDING_DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]


_local_hash_embedding = LocalHashEmbeddingFunction()


@contextmanager
def _embedding_network_context():
    """Patch HTTPX stream defaults for SSL/proxy constrained environments."""
    use_patch = (
        settings.CHROMA_EMBEDDING_MODE.lower() != "local_hash"
        and (not settings.CHROMA_HTTP_VERIFY_SSL or not settings.CHROMA_HTTP_TRUST_ENV)
    )

    if not use_patch:
        yield
        return

    original_stream = httpx.stream

    def patched_stream(method: str, url: str, *args, **kwargs):
        kwargs.setdefault("verify", settings.CHROMA_HTTP_VERIFY_SSL)
        kwargs.setdefault("trust_env", settings.CHROMA_HTTP_TRUST_ENV)
        return original_stream(method, url, *args, **kwargs)

    httpx.stream = patched_stream
    logger.warning(
        "Chroma embedding download workaround active | verify_ssl=%s | trust_env=%s",
        settings.CHROMA_HTTP_VERIFY_SSL,
        settings.CHROMA_HTTP_TRUST_ENV,
    )
    try:
        yield
    finally:
        httpx.stream = original_stream


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
    if settings.CHROMA_EMBEDDING_MODE.lower() == "local_hash":
        return _get_client().get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=_local_hash_embedding,
        )

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

    try:
        with _embedding_network_context():
            collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    except Exception as exc:
        logger.exception("save_schema_chunks failed | db_id=%s", db_id)
        raise RuntimeError(f"Vector store upsert failed: {exc}") from exc

    logger.info("save_schema_chunks | db_id=%s | saved %d docs", db_id, len(documents))
    return len(documents)


def retrieve_relevant_schema(db_id: str, question: str, top_k: int = 10) -> str:
    """Semantic search over stored schema chunks filtered by *db_id*.

    Returns a single string of concatenated schema text suitable for injection
    into the LLM prompt.
    """
    collection = _get_collection()

    try:
        with _embedding_network_context():
            results = collection.query(
                query_texts=[question],
                n_results=top_k,
                where={"db_id": db_id},
            )
    except Exception as exc:
        logger.exception("retrieve_relevant_schema failed | db_id=%s", db_id)
        raise RuntimeError(f"Vector store query failed: {exc}") from exc

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
