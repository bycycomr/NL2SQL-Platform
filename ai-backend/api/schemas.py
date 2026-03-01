"""
Pydantic request / response models for the NL2SQL API.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Onboarding flow
# ---------------------------------------------------------------------------
class ExtractSchemaRequest(BaseModel):
    """Step 1 – auto-extract schema from a live database."""

    db_id: str
    connection_string: str


class TableSchema(BaseModel):
    """One table's metadata (auto-extracted + human-enriched)."""

    name: str
    columns: list[str]
    human_description: str = ""
    business_rules: str = ""


class ExtractSchemaResponse(BaseModel):
    """Returned after auto-extraction so the user can enrich before registering."""

    db_id: str
    tables: list[TableSchema]
    few_shot_examples: list[dict] = []


class RegisterSchemaRequest(BaseModel):
    """Step 2 – register enriched schema into the vector store."""

    db_id: str
    tables: list[TableSchema]
    few_shot_examples: list[dict]


# ---------------------------------------------------------------------------
# Query flow
# ---------------------------------------------------------------------------
class NL2SQLRequest(BaseModel):
    """Incoming natural-language query (multi-tenant)."""

    db_id: str = Field(..., description="Target database ID")
    connection_string: str = Field(
        ..., description="DB connection string for execution"
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        examples=["Hangi departmanda en çok çalışan var?"],
    )
    user_id: str | None = Field(
        default=None,
        description="Optional caller identifier for auditing.",
    )


class NL2SQLResponse(BaseModel):
    """Response containing the generated SQL, explanation, data, or error."""

    sql_query: str | None = Field(
        default=None,
        description="The generated SQL query (SELECT only).",
    )
    explanation: str | None = Field(
        default=None,
        description="Plain-language explanation of the SQL logic.",
    )
    data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Actual data returned from the DB.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the pipeline failed.",
    )
    status: str = Field(
        ...,
        examples=["success", "failed"],
        description="Overall request status.",
    )
