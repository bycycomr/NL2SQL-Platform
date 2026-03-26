"""
LangGraph StateGraph definition – wires nodes, edges, and conditional routing.

Graph topology (V2 – with execution)
====================================

    START
      │
      ▼
  retrieve_schema
      │
      ▼
  generate_sql
      │
      ▼
  validate_sql ──┐
      │          │  validation_error AND retry < 3
      │          └──► generate_sql  (loop back)
      ▼
  execute_sql
      │
      ▼
  explain_sql
      │
      ▼
    END
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph


from agent.nodes import (
    execute_sql_node,
    explain_sql_node,
    generate_sql_node,
    retrieve_schema_node,
    validate_sql_node,
)
from agent.state import AgentState
from core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional edge: decide what happens after schema retrieval
# ---------------------------------------------------------------------------
def _after_retrieve(state: AgentState) -> Literal["generate_sql", "__end__"]:
    """Route after ``retrieve_schema_node``.

    * If schema exists → proceed to ``generate_sql``
    * If schema missing (validation_error set) → END
    """
    error = state.get("validation_error")
    schema = (state.get("relevant_schema") or "").strip()

    if error and not schema:
        logger.warning("_after_retrieve | missing schema – ending early")
        return END

    return "generate_sql"


# ---------------------------------------------------------------------------
# Conditional edge: decide what happens after validation
# ---------------------------------------------------------------------------
def _after_validation(state: AgentState) -> Literal["generate_sql", "execute_sql", "__end__"]:
    """Route after ``validate_sql_node``.

    * If valid  → proceed to ``execute_sql``
    * If invalid AND retries left → loop back to ``generate_sql``
    * If invalid AND retries exhausted → END (return error in response)
    """
    error = state.get("validation_error")
    retries = state.get("retry_count", 0)

    if error is None:
        return "execute_sql"

    if retries < settings.MAX_RETRY_COUNT:
        logger.info(
            "_after_validation | retrying (%d/%d)",
            retries,
            settings.MAX_RETRY_COUNT,
        )
        return "generate_sql"

    logger.warning("_after_validation | retries exhausted – ending with error")
    return END


def _after_execution(state: AgentState) -> Literal["generate_sql", "explain_sql", "__end__"]:
    """Route after ``execute_sql_node``.

    * Execution OK  → explain_sql
    * Execution failed AND retries left → generate_sql (model görüsün, hatasını düzeltsin)
    * Retries exhausted → END
    """
    error = state.get("validation_error")
    retries = state.get("retry_count", 0)

    if error is None:
        return "explain_sql"

    if retries < settings.MAX_RETRY_COUNT:
        logger.info(
            "_after_execution | execution failed, retrying (%d/%d)",
            retries,
            settings.MAX_RETRY_COUNT,
        )
        return "generate_sql"

    logger.warning("_after_execution | retries exhausted – ending with error")
    return END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    """Build, compile, and return the NL2SQL LangGraph agent."""

    builder = StateGraph(AgentState)

    # -- Nodes --
    builder.add_node("retrieve_schema", retrieve_schema_node)
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("validate_sql", validate_sql_node)
    builder.add_node("execute_sql", execute_sql_node)
    builder.add_node("explain_sql", explain_sql_node)

    # -- Edges --
    builder.add_edge(START, "retrieve_schema")

    # Conditional: if schema missing, stop early with explicit error
    builder.add_conditional_edges(
        "retrieve_schema",
        _after_retrieve,
        {
            "generate_sql": "generate_sql",
            END: END,
        },
    )

    builder.add_edge("generate_sql", "validate_sql")

    # Conditional: after validation either loop, execute, or end
    builder.add_conditional_edges(
        "validate_sql",
        _after_validation,
        {
            "generate_sql": "generate_sql",
            "execute_sql": "execute_sql",
            END: END,
        },
    )

    # Conditional: after execution either retry, explain, or end
    builder.add_conditional_edges(
        "execute_sql",
        _after_execution,
        {
            "generate_sql": "generate_sql",
            "explain_sql": "explain_sql",
            END: END,
        },
    )
    builder.add_edge("explain_sql", END)

    graph = builder.compile()
    logger.info("NL2SQL LangGraph agent compiled successfully")
    return graph


# Module-level compiled graph – import and invoke directly
agent = build_graph()
