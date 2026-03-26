"""
API route tanımları — NL2SQL AI Backend (Contract v2.0)

Hibrit Mimari:
  AI Backend SQL üretir ve dry-run ile doğrular.
  Gerçek veri çekimi Core Backend tarafından yapılır.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agent.graph import agent
from api.schemas import (
    ColumnSchema,
    ExtractSchemaRequest,
    ExtractSchemaResponse,
    NL2SQLRequest,
    NL2SQLResponse,
    RegisterSchemaMetrics,
    RegisterSchemaRequest,
    RegisterSchemaResponse,
    TableSchema,
)
from pydantic import BaseModel


class CacheStatsResponse(BaseModel):
    """SQL cache istatistikleri."""
    total_entries: int = 0
    active_entries: int = 0
from services.db_inspector import DBInspector
from services.vector_store import save_schema_chunks
from services import sql_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["NL2SQL"])


def _parse_column_string(col_str: str) -> ColumnSchema:
    """'col_name TYPE [NOT NULL]' formatındaki string'i ColumnSchema'ya çevirir."""
    parts = col_str.split(" ", 1)
    return ColumnSchema(name=parts[0], type=parts[1] if len(parts) > 1 else "")


# ---------------------------------------------------------------------------
# Onboarding — Step 1: Otomatik Şema Çıkarma
# ---------------------------------------------------------------------------

@router.post(
    "/onboard/extract",
    response_model=ExtractSchemaResponse,
    summary="Adım 1 — Canlı veritabanından şemayı otomatik çıkar.",
    description=(
        "Hedef veritabanına bağlanır, tabloları ve kolonları introspect eder. "
        "Sistem şemaları (pg_catalog, information_schema vb.) otomatik filtrelenir. "
        "Dönen şema insan uzmanlar tarafından zenginleştirilip /onboard/register'a gönderilir."
    ),
)
async def extract_schema(request: ExtractSchemaRequest) -> ExtractSchemaResponse:
    logger.info("extract_schema | db_id=%s | db_type=%s", request.db_id, request.db_type)

    try:
        inspector = DBInspector(request.connection_string)
        raw_tables = inspector.get_schema()
        inspector.dispose()
    except Exception as exc:
        logger.exception("extract_schema | introspection failed | db_id=%s", request.db_id)
        raise HTTPException(status_code=400, detail=f"Veritabanına bağlanılamadı veya şema okunamadı: {exc}")

    tables = [
        TableSchema(
            table_name=t["name"],
            columns=[_parse_column_string(c) for c in t["columns"]],
        )
        for t in raw_tables
    ]

    return ExtractSchemaResponse(
        status="success",
        db_id=request.db_id,
        message=f"{len(tables)} tablo başarıyla okundu.",
        tables=tables,
    )


# ---------------------------------------------------------------------------
# Onboarding — Step 2: Zenginleştirilmiş Şema Kaydı
# ---------------------------------------------------------------------------

@router.post(
    "/onboard/register",
    response_model=RegisterSchemaResponse,
    summary="Adım 2 — Zenginleştirilmiş şemayı ve few-shot örneklerini ChromaDB'ye kaydet.",
    description=(
        "İnsan uzmanlar tarafından zenginleştirilmiş (açıklama, iş kuralları, few-shot eklenmiş) "
        "şemayı alır. mode='upsert' ile eski şema kalıntılarının üzerine yazar."
    ),
)
async def register_schema(request: RegisterSchemaRequest) -> RegisterSchemaResponse:
    logger.info(
        "register_schema | db_id=%s | mode=%s | tables=%d | few_shots=%d",
        request.db_id, request.mode, len(request.tables), len(request.few_shot_examples),
    )

    # Contract 'query' anahtarını kullanıyor, vector_store 'sql' bekliyor — normalize et
    normalized_few_shots = [
        {
            "question": ex.get("question", ""),
            "sql": ex.get("query") or ex.get("sql", ""),
        }
        for ex in request.few_shot_examples
    ]

    table_dicts = [
        {
            "table_name": t.table_name,
            "columns": [{"name": c.name, "type": c.type} for c in t.columns],
            "human_description": t.human_description,
            "business_rules": t.business_rules,
        }
        for t in request.tables
    ]

    try:
        metrics = save_schema_chunks(
            db_id=request.db_id,
            tables=table_dicts,
            few_shot_examples=normalized_few_shots,
        )
    except Exception as exc:
        logger.error("register_schema failed | db_id=%s | error=%s", request.db_id, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Şema kaydı başarısız: {exc}",
        )

    return RegisterSchemaResponse(
        status="success",
        db_id=request.db_id,
        message=f"'{request.db_id}' için zenginleştirilmiş şema ve örnek sorgular ChromaDB'ye başarıyla indekslendi.",
        metrics=RegisterSchemaMetrics(**metrics),
    )


# ---------------------------------------------------------------------------
# SQL Üretme ve Dry-Run Doğrulama
# ---------------------------------------------------------------------------

@router.post(
    "/generate-sql",
    response_model=NL2SQLResponse,
    summary="Doğal dil sorusunu güvenli SQL'e çevir ve dry-run ile doğrula.",
    description=(
        "Kullanıcının doğal dil girdisini LangGraph ajan döngüsüyle SQL'e çevirir. "
        "dry_run_limit verilmişse SQL dahili olarak sınırlı satırla test edilir; "
        "döndürülen sql_query temizdir (LIMIT içermez). "
        "Gerçek veri çekimi Core Backend tarafından yapılır.\n\n"
        "**Önemli:** Bu endpoint her zaman HTTP 200 döndürür. "
        "Hata durumu body'deki `status` ('error') ve `error_code` alanlarıyla belirlenir. "
        "Olası hata kodları: `SCHEMA_NOT_FOUND`, `SQL_VALIDATION_FAILED`, `AGENT_ERROR`."
    ),
)
async def generate_sql(request: NL2SQLRequest) -> NL2SQLResponse:
    logger.info(
        "generate_sql | db_id=%s | user_id=%s | dry_run_limit=%s | question=%s",
        request.db_id,
        request.user_id,
        request.dry_run_limit,
        request.query[:80],
    )

    # --- Cache kontrolü ---
    cached = sql_cache.get(request.db_id, request.query)
    if cached is not None:
        return NL2SQLResponse(**cached)

    initial_state = {
        "db_id": request.db_id,
        "connection_string": request.connection_string,
        "question": request.query,
        "relevant_schema": "",
        "generated_sql": "",
        "validation_error": None,
        "explanation": "",
        "execution_data": None,
        "retry_count": 0,
        "dry_run_limit": request.dry_run_limit,
        "is_validated": False,
    }

    try:
        result = await agent.ainvoke(initial_state)
    except Exception as exc:
        logger.error(
            "Agent pipeline failed | db_id=%s | error=%s",
            request.db_id, exc, exc_info=True,
        )
        return NL2SQLResponse(
            status="error",
            error_code="AGENT_ERROR",
            error="Ajan pipeline hatası. Lütfen tekrar deneyin.",
            is_validated=False,
            impact_rows=0,
        )

    if result.get("validation_error"):
        error_msg = result["validation_error"]
        # Şema bulunamadı mı yoksa SQL doğrulama mı başarısız?
        error_code = (
            "SCHEMA_NOT_FOUND"
            if "onboarding" in error_msg.lower() or "sema bulunamadi" in error_msg.lower()
            else "SQL_VALIDATION_FAILED"
        )
        logger.warning("generate_sql | failed | error_code=%s | db_id=%s", error_code, request.db_id)
        return NL2SQLResponse(
            status="error",
            error_code=error_code,
            error=error_msg,
            is_validated=False,
            impact_rows=0,
        )

    response = NL2SQLResponse(
        status="success",
        sql_query=result["generated_sql"],
        explanation=result.get("explanation") or None,
        is_validated=result.get("is_validated", False),
        impact_rows=0,
    )

    # Başarılı sonucu cache'e yaz
    sql_cache.set(request.db_id, request.query, response.model_dump())

    return response


# ---------------------------------------------------------------------------
# SQL Üretme — Streaming (Server-Sent Events)
# ---------------------------------------------------------------------------

# Node adından kullanıcı dostu mesaja
_NODE_MESSAGES = {
    "retrieve_schema": "Şema aranıyor...",
    "generate_sql":    "SQL üretiliyor...",
    "validate_sql":    "SQL dogrulanıyor...",
    "execute_sql":     "SQL test ediliyor (dry-run)...",
    "explain_sql":     "Acıklama haazırlanıyor...",
}


async def _sse_stream(initial_state: dict, db_id: str, question: str) -> AsyncIterator[str]:
    """LangGraph node güncellemelerini SSE formatında yayınlar."""

    def _emit(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    final_state: dict = {}

    try:
        async for chunk in agent.astream(initial_state, stream_mode="updates"):
            for node_name, updates in chunk.items():
                final_state.update(updates)
                msg = _NODE_MESSAGES.get(node_name, node_name)

                # SQL üretildi → SQL'i de gönder
                if node_name == "generate_sql" and updates.get("generated_sql"):
                    yield _emit({
                        "event": "progress",
                        "node": node_name,
                        "message": msg,
                        "sql_preview": updates["generated_sql"][:120],
                    })
                else:
                    yield _emit({"event": "progress", "node": node_name, "message": msg})

    except Exception as exc:
        logger.error("SSE stream error | db_id=%s | error=%s", db_id, exc, exc_info=True)
        yield _emit({"event": "error", "error_code": "AGENT_ERROR", "error": str(exc)})
        return

    # Son durum → "done" eventi
    if final_state.get("validation_error"):
        err = final_state["validation_error"]
        error_code = (
            "SCHEMA_NOT_FOUND"
            if "onboarding" in err.lower() or "sema bulunamadi" in err.lower()
            else "SQL_VALIDATION_FAILED"
        )
        yield _emit({"event": "done", "status": "error", "error_code": error_code, "error": err,
                     "is_validated": False, "impact_rows": 0})
        return

    result_payload = {
        "event": "done",
        "status": "success",
        "sql_query": final_state.get("generated_sql"),
        "explanation": final_state.get("explanation") or None,
        "is_validated": final_state.get("is_validated", False),
        "impact_rows": 0,
    }
    yield _emit(result_payload)

    # Cache'e yaz
    cache_payload = {k: v for k, v in result_payload.items() if k != "event"}
    sql_cache.set(db_id, question, cache_payload)


@router.post(
    "/generate-sql/stream",
    summary="SQL üret ve her adımı SSE ile gerçek zamanlı yayınla.",
    description=(
        "generate-sql ile aynı istek formatı; fark olarak her LangGraph node'u "
        "tamamlandıkça `text/event-stream` formatında event yollanır.\n\n"
        "**Event tipleri:**\n"
        "- `progress` — node ilerlemesi: `{\"event\": \"progress\", \"node\": \"generate_sql\", \"message\": \"SQL üretiliyor...\", \"sql_preview\": \"SELECT...\"}`\n"
        "- `error` — pipeline hatası: `{\"event\": \"error\", \"error_code\": \"AGENT_ERROR\", \"error\": \"...\"}`\n"
        "- `done` — son sonuç (her zaman): `{\"event\": \"done\", \"status\": \"success\", \"sql_query\": \"...\", \"explanation\": \"...\", \"is_validated\": true, \"impact_rows\": 0}`\n\n"
        "Cache HIT durumunda yalnızca tek `done` eventi yollanır: `{\"event\": \"done\", \"cached\": true, ...}`"
    ),
    response_class=StreamingResponse,
)
async def generate_sql_stream(request: NL2SQLRequest) -> StreamingResponse:
    logger.info("generate_sql_stream | db_id=%s | question=%s", request.db_id, request.query[:80])

    # Cache hit → tek seferlik "done" eventi
    cached = sql_cache.get(request.db_id, request.query)
    if cached is not None:
        async def _cached():
            yield f"data: {json.dumps({'event': 'done', 'cached': True, **cached}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_cached(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    initial_state = {
        "db_id": request.db_id,
        "connection_string": request.connection_string,
        "question": request.query,
        "relevant_schema": "",
        "generated_sql": "",
        "validation_error": None,
        "explanation": "",
        "execution_data": None,
        "retry_count": 0,
        "dry_run_limit": request.dry_run_limit,
        "is_validated": False,
    }

    return StreamingResponse(
        _sse_stream(initial_state, request.db_id, request.query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Cache İstatistikleri
# ---------------------------------------------------------------------------

@router.get("/cache/stats", tags=["Ops"], summary="SQL cache istatistikleri.", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    return CacheStatsResponse(**sql_cache.stats())
