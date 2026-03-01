"""
AgentState TypedDict – the shared state flowing through the LangGraph pipeline.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    db_id: str
    connection_string: str
    question: str
    relevant_schema: str
    generated_sql: str
    validation_error: str | None
    explanation: str
    execution_data: list[dict[str, Any]] | None
    retry_count: int
