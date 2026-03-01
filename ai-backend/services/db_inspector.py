"""
Database inspector service – SQLAlchemy-based schema introspection and read-only execution.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DBInspector:
    """Wraps SQLAlchemy to introspect schemas and execute read-only queries."""

    def __init__(self, connection_string: str) -> None:
        self._engine: Engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
        )

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------
    def get_schema(self) -> list[dict[str, Any]]:
        """Return a list of tables with their column definitions across all schemas (Multi-DBMS Support).

        Each element: ``{"name": "schema.table_name", "columns": ["col1 TYPE", ...]}``
        """
        inspector = inspect(self._engine)
        tables: list[dict[str, Any]] = []

        # Evrensel (PostgreSQL, MySQL, MSSQL, Oracle, SQLite) Sistem Şemaları Karalistesi
        # AI'ın kafasını karıştırmamak için bu şemalardaki binlerce log/ayar tablosunu yoksayıyoruz.
        UNIVERSAL_IGNORED_SCHEMAS = {
            # MSSQL
            'sys', 'information_schema', 'guest', 'db_owner', 'db_accessadmin', 'db_securityadmin',
            'db_ddladmin', 'db_backupoperator', 'db_datareader', 'db_datawriter', 'db_denydatareader', 'db_denydatawriter',
            # PostgreSQL
            'pg_catalog', 'pg_toast', 
            # MySQL
            'mysql', 'performance_schema', 
            # Oracle
            'ctxsys', 'dbsnmp', 'exfsys', 'mdsys', 'olapsys', 'orddata', 'ordsys', 'outln', 'system', 'wmsys', 'xdb',
            # SQLite (SQLite'ta şema yoktur, tablolar doğrudan gelir, onları da aşağıda filtreleyeceğiz)
            'sqlite_master', 'sqlite_sequence', 'sqlite_stat1'
        }

        try:
            # 1. SQLAlchemy ile veritabanının şemalarını iste
            all_schemas = inspector.get_schema_names()
        except Exception as e:
            logger.warning("get_schema_names failed, falling back to default schema. Details: %s", e)
            all_schemas = [None]  # SQLite gibi şema desteklemeyen yapılar için varsayılanı kullan

        for schema in all_schemas:
            # Şema adını küçük harfe çevirip karalistede var mı diye kontrol et
            if schema and schema.lower() in UNIVERSAL_IGNORED_SCHEMAS:
                continue

            try:
                # 2. İlgili şemadaki tabloları çek
                table_names = inspector.get_table_names(schema=schema)
                
                for table_name in table_names:
                    # Bazı sistemler (SQLite gibi) sistem dosyalarını tablo olarak tutar
                    if table_name.lower() in UNIVERSAL_IGNORED_SCHEMAS:
                        continue

                    columns: list[str] = []
                    
                    # 3. Tablonun kolonlarını çek
                    for col in inspector.get_columns(table_name, schema=schema):
                        col_str = f"{col['name']} {col['type']}"
                        if not col.get("nullable", True):
                            col_str += " NOT NULL"
                        columns.append(col_str)
                    
                    # Evrensel isimlendirme: Şema destekleyen DB'ler için 'sema.tablo', desteklemeyenler için 'tablo'
                    full_table_name = f"{schema}.{table_name}" if schema else table_name
                    
                    tables.append({"name": full_table_name, "columns": columns, "human_description": "", "business_rules": ""})
            except Exception as e:
                logger.error("Error reading schema '%s': %s", schema, e)
                continue

        logger.info(
            "get_schema | extracted %d tables from %s",
            len(tables),
            self._engine.url.database or self._engine.url,
        )
        return tables

    # ------------------------------------------------------------------
    # Read-only query execution
    # ------------------------------------------------------------------
    def execute_read_only(self, sql: str) -> list[dict[str, Any]]:
        """Execute a **validated, read-only** SQL statement and return rows as dicts.

        Important: The SQL MUST have already been validated by ``core.security.validate_sql``
        before calling this method.  This function sets the connection to read-only
        mode where supported.
        """
        rows: list[dict[str, Any]] = []

        with self._engine.connect() as conn:
            # Attempt to set read-only at session level (Postgres-specific;
            # harmless no-op on other dialects)
            try:
                conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            except Exception:
                pass  # Not all engines support this; the security layer is the real guard

            result = conn.execute(text(sql))
            column_names = list(result.keys())
            for row in result.fetchall():
                rows.append(dict(zip(column_names, row)))

        logger.info("execute_read_only | returned %d rows", len(rows))
        return rows

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def dispose(self) -> None:
        """Dispose the engine connection pool."""
        self._engine.dispose()