"""
SQL sorgu cache servisi — in-memory LRU cache.

Aynı (db_id, question) çifti için LLM'e gitmeden önce cache'e bak.
Başarılı SQL'ler cache'e alınır; hatalı sonuçlar alınmaz.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------
_cache: OrderedDict[str, dict] = OrderedDict()


def _make_key(db_id: str, question: str) -> str:
    normalized = question.lower().strip()
    h = hashlib.sha256(f"{db_id}::{normalized}".encode("utf-8")).hexdigest()[:16]
    return h


def get(db_id: str, question: str) -> dict | None:
    """Cache'te eşleşme varsa döndür, yoksa None."""
    key = _make_key(db_id, question)
    entry = _cache.get(key)
    if entry is None:
        return None

    # TTL kontrolü
    if time.time() > entry["_expires_at"]:
        _cache.pop(key, None)
        logger.debug("sql_cache | expired | key=%s", key)
        return None

    # LRU: son kullanılanı sona taşı
    _cache.move_to_end(key)
    logger.info("sql_cache | HIT | db_id=%s | question=%s", db_id, question[:60])
    return entry["payload"]


def set(db_id: str, question: str, payload: dict) -> None:
    """Başarılı SQL sonucunu cache'e yaz."""
    if len(_cache) >= settings.SQL_CACHE_MAX_SIZE:
        # En eski girdiyi sil (LRU)
        evicted_key, _ = _cache.popitem(last=False)
        logger.debug("sql_cache | evict | key=%s", evicted_key)

    key = _make_key(db_id, question)
    _cache[key] = {
        "payload": payload,
        "_expires_at": time.time() + settings.SQL_CACHE_TTL_SECONDS,
    }
    logger.info(
        "sql_cache | SET | db_id=%s | question=%s | cache_size=%d",
        db_id, question[:60], len(_cache),
    )


def invalidate(db_id: str) -> int:
    """Belirli bir db_id'ye ait tüm cache girdilerini sil."""
    # Key'ler hash'lendiği için db_id'yi payload'dan kontrol etmemiz gerekir
    to_delete = [k for k, v in _cache.items() if v["payload"].get("_db_id") == db_id]
    for k in to_delete:
        _cache.pop(k, None)
    if to_delete:
        logger.info("sql_cache | invalidate | db_id=%s | removed=%d", db_id, len(to_delete))
    return len(to_delete)


def stats() -> dict:
    """Cache istatistikleri."""
    now = time.time()
    active = sum(1 for v in _cache.values() if v["_expires_at"] > now)
    return {"total_entries": len(_cache), "active_entries": active}
