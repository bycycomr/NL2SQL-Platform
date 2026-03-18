"""
LangGraph node functions for the NL2SQL agent.

Each node receives the full ``AgentState`` and returns a *partial* dict
of state updates that LangGraph merges back into the state.
"""
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompts import SQL_EXPLAIN_PROMPT, SQL_GENERATION_PROMPT
from agent.state import AgentState
from core.security import validate_sql
from services.db_inspector import DBInspector
from services.llm import ainvoke_with_retry
from services.vector_store import retrieve_relevant_schema

logger = logging.getLogger(__name__)


def _build_execution_error_hint(exc: Exception, sql: str) -> str:
    """Ham DB hatasını LLM'in anlayıp düzeltebileceği net bir mesaja çevirir."""
    raw = str(exc)

    # SQL Server: Invalid column name 'X'
    bad_cols = re.findall(r"Invalid column name '(\w+)'", raw)
    if bad_cols:
        unique_cols = list(dict.fromkeys(bad_cols))
        # Hangi tabloda kullanıldığını SQL'den bul
        alias_table: dict[str, str] = {}
        for m in re.finditer(r"(\w+\.\w+|\w+)\s+(?:AS\s+)?(\w+)\b", sql, re.IGNORECASE):
            alias_table[m.group(2).lower()] = m.group(1)
        hints = []
        for col in unique_cols:
            # Hangi alias/tablo bu kolonu kullandı?
            col_aliases = re.findall(rf"\b(\w+)\.{col}\b", sql, re.IGNORECASE)
            for alias in col_aliases:
                tbl = alias_table.get(alias.lower(), alias)
                hints.append(f"'{col}' kolonu '{tbl}' tablosunda YOKTUR")
        hint_str = "; ".join(hints) if hints else f"{unique_cols} kolonları kullandığın tabloda yok"
        return (
            f"Execution hatası: {hint_str}. "
            f"Şemayı tekrar incele — bu kolonlar başka bir tabloda olabilir. "
            f"Her tablo için yalnızca şemada listelenen kolonları kullan."
        )

    # SQL Server: Invalid object name 'X' (tablo yok)
    bad_objs = re.findall(r"Invalid object name '([^']+)'", raw)
    if bad_objs:
        return (
            f"Execution hatası: {bad_objs} tablosu/nesnesi mevcut değil. "
            f"Şemada yalnızca listelenen tablo adlarını kullan, isim uydurmak yasaktır."
        )

    return raw.splitlines()[0][:300]


# ---------------------------------------------------------------------------
# Node 1 – Retrieve relevant schema DDL from ChromaDB
# ---------------------------------------------------------------------------
async def retrieve_schema_node(state: AgentState) -> dict:
    """Fetch DDL / schema context from the vector store, filtered by db_id."""

    db_id: str = state["db_id"]
    question: str = state["question"]
    logger.info("retrieve_schema_node | db_id=%s | question=%s", db_id, question[:80])

    schema = retrieve_relevant_schema(db_id=db_id, question=question)

    return {"relevant_schema": schema}


# ---------------------------------------------------------------------------
# Node 2 – Generate SQL via LLM
# ---------------------------------------------------------------------------
def _detect_dialect(connection_string: str) -> str:
    """Derive a human-readable SQL dialect name from the SQLAlchemy connection string."""
    cs = (connection_string or "").lower()
    if "mssql" in cs or "pyodbc" in cs or "sqlserver" in cs:
        return "mssql (T-SQL)"
    if "postgresql" in cs or "postgres" in cs:
        return "postgresql"
    if "mysql" in cs or "mariadb" in cs:
        return "mysql"
    if "sqlite" in cs:
        return "sqlite"
    return "postgresql"  # güvenli varsayılan


async def generate_sql_node(state: AgentState) -> dict:
    """Call the configured LLM to generate SQL, fallback to heuristic SQL on failure."""

    dialect = _detect_dialect(state.get("connection_string", ""))
    prompt_text = SQL_GENERATION_PROMPT.format(
        schema=state["relevant_schema"],
        dialect=dialect,
        validation_error=state.get("validation_error") or "Yok",
        question=state["question"],
    )

    logger.info(
        "generate_sql_node | retry_count=%s | has_prev_error=%s",
        state.get("retry_count", 0),
        state.get("validation_error") is not None,
    )

    try:
        response = await ainvoke_with_retry(
            [
                SystemMessage(content="Sen sadece SQL üreten bir asistansın. Sadece ham SQL döndür, başka hiçbir şey yazma."),
                HumanMessage(content=prompt_text),
            ]
        )
        raw_sql = _clean_sql(response.content)
        logger.debug("generate_sql_node | raw LLM output: %s", raw_sql)
    except Exception as exc:
        logger.error(
            "generate_sql_node | llm unavailable, fallback SQL is used | error=%s",
            exc,
            exc_info=True,
        )
        raw_sql = _fallback_sql(state["question"], state.get("relevant_schema", ""))
        logger.info("generate_sql_node | fallback_sql=%s", raw_sql)

    return {"generated_sql": raw_sql}


def _clean_sql(text: str) -> str:
    """Strip markdown fences and extraneous whitespace from model output."""
    text = re.sub(r"```(?:sql)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Node 3 – Validate generated SQL (DML blocking + syntax)
# ---------------------------------------------------------------------------
async def validate_sql_node(state: AgentState) -> dict:
    """Run the two-layer security validation on the generated SQL."""

    sql = state["generated_sql"]
    logger.info("validate_sql_node | sql=%s", sql[:120])

    error = validate_sql(sql)

    if error is None:
        logger.info("validate_sql_node | PASS")
        return {"validation_error": None}

    retry = state.get("retry_count", 0) + 1
    logger.warning(
        "validate_sql_node | FAIL (%s) | retry_count=%s",
        error,
        retry,
    )
    return {
        "validation_error": error,
        "retry_count": retry,
    }


# ---------------------------------------------------------------------------
# Node 4 – Execute validated SQL (read-only)
# ---------------------------------------------------------------------------
async def execute_sql_node(state: AgentState) -> dict:
    """Connect to the target DB and execute the validated SQL."""

    connection_string: str = state["connection_string"]
    sql: str = state["generated_sql"]
    logger.info("execute_sql_node | executing query")

    try:
        inspector = DBInspector(connection_string)
        rows = inspector.execute_read_only(sql)
        inspector.dispose()
        return {"execution_data": rows, "validation_error": None}
    except Exception as exc:
        logger.exception("execute_sql_node | execution failed")
        retry = state.get("retry_count", 0) + 1
        hint = _build_execution_error_hint(exc, sql)
        logger.warning("execute_sql_node | retry_count=%s | error=%s", retry, hint)
        return {
            "execution_data": None,
            "validation_error": hint,
            "retry_count": retry,
        }


# ---------------------------------------------------------------------------
# Node 5 – Explain the validated SQL in plain language (Turkish)
# ---------------------------------------------------------------------------
async def explain_sql_node(state: AgentState) -> dict:
    """Call the LLM to produce a concise Turkish explanation."""

    prompt_text = SQL_EXPLAIN_PROMPT.format(
        sql_query=state["generated_sql"],
        question=state["question"],
    )

    logger.info("explain_sql_node | generating explanation")

    try:
        response = await ainvoke_with_retry(
            [
                SystemMessage(content="Sen kısa ve öz açıklama yapan bir veri çevirmenisin. Her zaman Türkçe yanıt ver."),
                HumanMessage(content=prompt_text),
            ]
        )
        return {"explanation": response.content.strip()}
    except Exception as exc:
        logger.error(
            "explain_sql_node | llm unavailable, fallback explanation is used | error=%s",
            exc,
            exc_info=True,
        )
        return {
            "explanation": "Sorgu, kullanıcı talebine uygun kayıtları getirir ve sonuçları en yüksekten düşüğe sıralar."
        }


def _fallback_sql(question: str, schema_text: str) -> str:
    """Deterministic fallback SQL for common business questions."""
    q = question.lower()
    schema = schema_text.lower()

    has_orders = "table: public.orders" in schema or "public.orders" in schema
    has_users = "table: public.users" in schema or "public.users" in schema

    if "en cok siparis" in q or "en çok sipariş" in q or "en fazla sipariş" in q or "top 3" in q:
        return (
            "SELECT u.id, CONCAT(u.first_name, ' ', u.last_name) AS customer_name, COUNT(o.id) AS order_count "
            "FROM public.orders o "
            "JOIN public.users u ON u.id = o.user_id "
            "GROUP BY u.id, u.first_name, u.last_name "
            "ORDER BY order_count DESC "
            "LIMIT 3"
        )

    if has_users:
        return "SELECT * FROM public.users LIMIT 10"

    if has_orders:
        return "SELECT * FROM public.orders LIMIT 10"

    return "SELECT 1"
