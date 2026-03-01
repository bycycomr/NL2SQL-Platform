"""
API route definitions for the NL2SQL microservice.

Multi-tenant with onboarding + query execution.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from agent.graph import agent
from api.schemas import (
    ExtractSchemaRequest,
    ExtractSchemaResponse,
    NL2SQLRequest,
    NL2SQLResponse,
    RegisterSchemaRequest,
    TableSchema,
)
from services.db_inspector import DBInspector
from services.vector_store import save_schema_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["NL2SQL"])


# ---------------------------------------------------------------------------
# Onboarding endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/onboard/extract",
    response_model=ExtractSchemaResponse,
    summary="Step 1 – Auto-extract schema from a live database.",
    tags=["Onboarding"],
)
async def extract_schema(request: ExtractSchemaRequest) -> ExtractSchemaResponse:
    """Connect to the target database, introspect tables & columns,
    and return the raw schema for human enrichment.
    """
    logger.info("extract_schema | db_id=%s", request.db_id)

    try:
        inspector = DBInspector(request.connection_string)
        raw_tables = inspector.get_schema()
        inspector.dispose()
    except Exception as exc:
        logger.exception("extract_schema | introspection failed")
        raise HTTPException(status_code=400, detail=f"Could not connect / introspect: {exc}")

    tables = [
        TableSchema(name=t["name"], columns=t["columns"])
        for t in raw_tables
    ]

    return ExtractSchemaResponse(
        db_id=request.db_id,
        tables=tables,
        few_shot_examples=[],
    )


@router.post(
    "/onboard/register",
    summary="Step 2 – Register enriched schema into the vector store.",
    tags=["Onboarding"],
)
async def register_schema(request: RegisterSchemaRequest) -> dict:
    """Receive the human-enriched schema and persist it into ChromaDB."""
    logger.info("register_schema | db_id=%s | tables=%d", request.db_id, len(request.tables))

    table_dicts = [
        {
            "name": t.name,
            "columns": t.columns,
            "human_description": t.human_description,
            "business_rules": t.business_rules,
        }
        for t in request.tables
    ]

    count = save_schema_chunks(
        db_id=request.db_id,
        tables=table_dicts,
        few_shot_examples=request.few_shot_examples,
    )

    return {"status": "registered", "db_id": request.db_id, "chunks_saved": count}


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/generate-sql",
    response_model=NL2SQLResponse,
    summary="Translate a natural-language question into a validated SQL query and execute it.",
)
async def generate_sql(request: NL2SQLRequest) -> NL2SQLResponse:
    """Accept a natural-language question, run the LangGraph NL2SQL agent,
    execute the query, and return results with explanation.
    """
    logger.info(
        "generate-sql called | db_id=%s | user_id=%s | question=%s",
        request.db_id,
        request.user_id,
        request.query[:80],
    )

    # Seed the initial agent state
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
    }

    try:
        result = await agent.ainvoke(initial_state)
    except Exception:
        logger.exception("Agent pipeline failed")
        return NL2SQLResponse(
            sql_query=None,
            explanation=None,
            data=None,
            error="Internal agent error. Please try again later.",
            status="failed",
        )

    # If the agent exhausted retries, validation_error will still be set
    if result.get("validation_error"):
        return NL2SQLResponse(
            sql_query=None,
            explanation=None,
            data=None,
            error=f"SQL validation failed after retries: {result['validation_error']}",
            status="failed",
        )

    return NL2SQLResponse(
        sql_query=result["generated_sql"],
        explanation=result.get("explanation", ""),
        data=result.get("execution_data"),
        error=None,
        status="success",
    )
