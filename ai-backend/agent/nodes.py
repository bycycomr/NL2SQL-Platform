"""
LangGraph node functions for the NL2SQL agent.

Each node receives the full ``AgentState`` and returns a *partial* dict
of state updates that LangGraph merges back into the state.
"""
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

# Dry-run LIMIT enjeksiyonu için guard regex'leri
_HAS_LIMIT = re.compile(r"\bLIMIT\s+\d+\s*;?\s*$", re.IGNORECASE)
_HAS_TOP   = re.compile(r"^\s*SELECT\s+TOP\s+\d+", re.IGNORECASE)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from agent.prompts import SQL_EXPLAIN_PROMPT, SQL_GENERATION_PROMPT
from core.config import settings
from agent.state import AgentState
from core.security import validate_sql
from services.db_inspector import DBInspector
from services.llm import ainvoke_with_retry, estimate_complexity
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
    if not schema.strip():
        msg = (
            f"'{db_id}' icin kayitli sema bulunamadi. "
            "Lutfen once /api/v1/onboard/extract ve /api/v1/onboard/register ile onboarding yapin."
        )
        logger.warning("retrieve_schema_node | no schema found | db_id=%s", db_id)
        return {
            "relevant_schema": "",
            "validation_error": msg,
            # schema yoksa tekrar SQL uretmek anlamsiz; akisi erken bitirelim.
            "retry_count": settings.MAX_RETRY_COUNT,
        }

    return {"relevant_schema": schema, "validation_error": None}


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

    retry_count = state.get("retry_count", 0)
    # İlk denemede karmaşıklığa göre model seç; retry'da her zaman güçlü modeli kullan
    if retry_count > 0:
        complexity = "complex"
    else:
        complexity = estimate_complexity(state["question"], state.get("relevant_schema", ""))
    logger.info(
        "generate_sql_node | retry_count=%s | complexity=%s | has_prev_error=%s",
        retry_count,
        complexity,
        state.get("validation_error") is not None,
    )

    try:
        response = await ainvoke_with_retry(
            [
                SystemMessage(content="Sen sadece SQL üreten bir asistansın. Sadece ham SQL döndür, başka hiçbir şey yazma."),
                HumanMessage(content=prompt_text),
            ],
            complexity=complexity,
        )
        raw_sql = _clean_sql(_extract_response_text(response))

        if not _looks_like_sql(raw_sql):
            logger.warning(
                "generate_sql_node | empty/non-sql output from llm, using fallback | output=%s",
                (raw_sql or "<EMPTY>")[:200],
            )
            raw_sql = _fallback_sql(
                question=state["question"],
                schema_text=state.get("relevant_schema", ""),
                dialect=dialect,
            )

        logger.debug("generate_sql_node | raw LLM output: %s", raw_sql)
    except Exception as exc:
        logger.error(
            "generate_sql_node | llm unavailable, fallback SQL is used | error=%s",
            exc,
            exc_info=True,
        )
        raw_sql = _fallback_sql(
            question=state["question"],
            schema_text=state.get("relevant_schema", ""),
            dialect=dialect,
        )
        logger.info("generate_sql_node | fallback_sql=%s", raw_sql)

    return {"generated_sql": raw_sql}


def _clean_sql(text: str) -> str:
    """Strip markdown fences and trailing natural-language text from model output.

    Strategy:
    1. Remove markdown fences.
    2. Split on blank lines — the SQL block is the first paragraph that
       starts with a SQL keyword; everything after is explanation.
    3. Fallback: if no blank-line separator, strip lines that start with
       obvious natural-language patterns (Turkish/English prose).
    """
    text = re.sub(r"```(?:sql)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Split into paragraphs (blank-line separated)
    paragraphs = re.split(r"\n\s*\n", text)
    sql_start = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
    for para in paragraphs:
        if sql_start.match(para.strip()):
            return para.strip()

    # No blank-line separator — strip trailing prose line by line
    # Keep all lines until the first line that looks like natural language
    # (starts with a word char that is NOT a SQL keyword or symbol)
    prose_pattern = re.compile(
        r"^\s*(?!SELECT|WITH|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|FULL|GROUP|ORDER|HAVING|ON|AND|OR|UNION|INSERT|UPDATE|DELETE|CASE|WHEN|THEN|ELSE|END|AS|BY|INTO|SET|NOT|IN|IS|NULL|DISTINCT|TOP|LIMIT|OFFSET|--|\()"
        r"[A-Za-z\u00c0-\uffff]",
        re.IGNORECASE,
    )
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if prose_pattern.match(line):
            break
        kept.append(line)

    return "\n".join(kept).strip()


def _extract_response_text(response: object) -> str:
    """Extract text content from LangChain response object safely."""
    content = getattr(response, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Common content blocks from chat model responses.
                txt = item.get("text") or item.get("content") or ""
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(p for p in parts if p).strip()

    return str(content or "")


def _looks_like_sql(text: str) -> bool:
    """Basic guard to detect SQL-ish output."""
    if not text:
        return False
    return bool(re.match(r"^\s*(SELECT|WITH)\b", text, re.IGNORECASE))


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
        return {"validation_error": None, "is_validated": True}

    retry = state.get("retry_count", 0) + 1
    logger.warning(
        "validate_sql_node | FAIL (%s) | retry_count=%s",
        error,
        retry,
    )
    return {
        "validation_error": error,
        "retry_count": retry,
        "is_validated": False,
    }


# ---------------------------------------------------------------------------
# Node 4 – Execute validated SQL (read-only)
# ---------------------------------------------------------------------------
async def execute_sql_node(state: AgentState) -> dict:
    """Dry-run doğrulaması: SQL'i hedef DB'de sınırlı satırla çalıştırır.

    Hibrit Mimari Notu:
        Bu node yalnızca SQL'in gerçekten çalışıp çalışmadığını doğrular.
        dry_run_limit varsa SQL'e dahili LIMIT enjekte eder; döndürülen
        generated_sql her zaman temiz (LIMIT'siz) kalır.
        Gerçek veri çekimi Core Backend tarafından yapılır.
    """
    connection_string: str = state["connection_string"]
    sql: str = state["generated_sql"]
    dry_run_limit: int | None = state.get("dry_run_limit")

    # Non-retryable config error: invalid SQLAlchemy URL
    try:
        make_url(connection_string)
    except ArgumentError:
        err = (
            "Invalid connection_string: SQLAlchemy URL format geçersiz. "
            "Lütfen geçerli bir bağlantı dizesi gönderin."
        )
        logger.warning("execute_sql_node | non-retryable | error=%s", err)
        return {
            "execution_data": None,
            "validation_error": err,
            "retry_count": settings.MAX_RETRY_COUNT,
        }

    # Dry-run SQL oluştur: generated_sql'i temiz bırak
    if dry_run_limit is not None:
        dialect = _detect_dialect(connection_string)
        is_mssql = "mssql" in dialect
        if is_mssql and not _HAS_TOP.match(sql):
            dry_run_sql = re.sub(
                r"(?i)^\s*SELECT\s+",
                f"SELECT TOP {dry_run_limit} ",
                sql,
                count=1,
            )
        elif not is_mssql and not _HAS_LIMIT.search(sql):
            dry_run_sql = f"{sql.rstrip(';')} LIMIT {dry_run_limit}"
        else:
            dry_run_sql = sql  # zaten LIMIT var, çift enjeksiyon engelle
    else:
        dry_run_sql = sql

    logger.info("execute_sql_node | dry_run_limit=%s | executing", dry_run_limit)

    try:
        inspector = DBInspector(connection_string)
        rows = inspector.execute_read_only(dry_run_sql)
        inspector.dispose()
        # generated_sql dönen dict'te YOK — LangGraph state'deki temiz SQL korunur
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


def _fallback_sql(question: str, schema_text: str, dialect: str) -> str:
    """Deterministic fallback SQL for common business questions."""
    q = question.lower()
    schema = schema_text.lower()

    is_mssql = "mssql" in dialect

    # Schema-aware default table selection for non-public schemas (e.g., SalesLT.Customer)
    m = re.search(r"TABLE:\s*([A-Za-z0-9_]+\.[A-Za-z0-9_]+|[A-Za-z0-9_]+)", schema_text)
    default_table = m.group(1) if m else None

    def _limit_clause(n: int) -> str:
        return "" if is_mssql else f" LIMIT {n}"

    def _top_prefix(n: int) -> str:
        return f"TOP {n} " if is_mssql else ""

    def _quote_table(name: str) -> str:
        if not is_mssql:
            return name
        if "." in name:
            schema_name, table_name = name.split(".", 1)
            return f"[{schema_name}].[{table_name}]"
        return f"[{name}]"

    has_orders = "table: public.orders" in schema or "public.orders" in schema
    has_users = "table: public.users" in schema or "public.users" in schema

    if "en cok siparis" in q or "en çok sipariş" in q or "en fazla sipariş" in q or "top 3" in q:
        if is_mssql:
            return (
                "SELECT TOP 3 u.id, (u.first_name + ' ' + u.last_name) AS customer_name, COUNT(o.id) AS order_count "
                "FROM public.orders o "
                "JOIN public.users u ON u.id = o.user_id "
                "GROUP BY u.id, u.first_name, u.last_name "
                "ORDER BY order_count DESC"
            )
        return (
            "SELECT u.id, CONCAT(u.first_name, ' ', u.last_name) AS customer_name, COUNT(o.id) AS order_count "
            "FROM public.orders o "
            "JOIN public.users u ON u.id = o.user_id "
            "GROUP BY u.id, u.first_name, u.last_name "
            "ORDER BY order_count DESC "
            "LIMIT 3"
        )

    if has_users:
        return f"SELECT {_top_prefix(10)}* FROM public.users{_limit_clause(10)}"

    if has_orders:
        return f"SELECT {_top_prefix(10)}* FROM public.orders{_limit_clause(10)}"

    if default_table:
        return f"SELECT {_top_prefix(10)}* FROM {_quote_table(default_table)}{_limit_clause(10)}"

    return "SELECT 1"
