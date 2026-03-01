"""
SQL security validation – blocks DML/DDL operations via regex + sqlglot AST parsing.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError


# Blacklisted SQL statement types (DML / DDL that mutate data)
_BLOCKED_STATEMENT_TYPES: set[type] = {
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
}

# Quick regex pre-check (case-insensitive) for obviously dangerous keywords
_DML_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|MERGE|REPLACE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> str | None:
    """Validates SQL using regex and AST parsing.

    Returns ``None`` if valid, else returns the error string.
    """

    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return "Empty SQL query."

    # ---- Layer 1: Regex ----
    match = _DML_PATTERN.search(cleaned)
    if match:
        keyword = match.group(0).upper()
        return f"Blocked: DML/DDL keyword '{keyword}' detected."

    # ---- Layer 2: AST parsing via sqlglot ----
    try:
        # sqlglot'a T-SQL (MS SQL Server) şivesini kullanmasını söylüyoruz
        parsed = sqlglot.parse(cleaned, read="tsql")

        for statement in parsed:
            if statement is None:
                continue
            for node in statement.walk():
                if type(node) in _BLOCKED_STATEMENT_TYPES:
                    return f"Blocked: {type(node).__name__} statement is not allowed."

    except (ParseError, TokenError) as e:
        return (
            f"Blocked: Could not parse SQL or invalid format. "
            f"Model might have returned raw text instead of SQL. Details: {e}"
        )
    except Exception as e:
        return f"Blocked: Unexpected validation error: {e}"

    return None