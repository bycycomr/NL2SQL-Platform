"""
api/schemas.py — Pydantic model doğrulama testleri.
"""
import pytest
from pydantic import ValidationError

from api.schemas import (
    ColumnSchema,
    NL2SQLRequest,
    NL2SQLResponse,
    RegisterSchemaMetrics,
    RegisterSchemaRequest,
    RegisterSchemaResponse,
    TableSchema,
)


class TestColumnSchema:
    def test_valid(self):
        col = ColumnSchema(name="order_id", type="INTEGER")
        assert col.name == "order_id"
        assert col.type == "INTEGER"

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ColumnSchema(type="INTEGER")  # type: ignore


class TestTableSchema:
    def test_valid(self):
        table = TableSchema(
            table_name="orders",
            columns=[ColumnSchema(name="id", type="INTEGER")],
        )
        assert table.table_name == "orders"
        assert len(table.columns) == 1

    def test_defaults(self):
        table = TableSchema(table_name="t", columns=[])
        assert table.human_description == ""
        assert table.business_rules == ""


class TestNL2SQLRequest:
    _VALID_CS = "postgresql://user:pass@host:5432/db"

    def test_valid(self):
        req = NL2SQLRequest(
            db_id="tenant_1",
            connection_string=self._VALID_CS,
            query="Tüm siparişleri getir",
        )
        assert req.db_id == "tenant_1"
        assert req.dry_run_limit is None

    def test_dry_run_limit_valid(self):
        req = NL2SQLRequest(
            db_id="x", connection_string=self._VALID_CS,
            query="test", dry_run_limit=5,
        )
        assert req.dry_run_limit == 5

    def test_dry_run_limit_zero_raises(self):
        with pytest.raises(ValidationError):
            NL2SQLRequest(
                db_id="x", connection_string=self._VALID_CS,
                query="test", dry_run_limit=0,
            )

    def test_invalid_connection_string_raises(self):
        with pytest.raises(ValidationError, match="connection_string"):
            NL2SQLRequest(
                db_id="x",
                connection_string="not-a-valid-url",
                query="test",
            )

    def test_query_max_length_raises(self):
        with pytest.raises(ValidationError):
            NL2SQLRequest(
                db_id="x", connection_string=self._VALID_CS,
                query="a" * 2001,
            )

    def test_query_empty_raises(self):
        with pytest.raises(ValidationError):
            NL2SQLRequest(
                db_id="x", connection_string=self._VALID_CS,
                query="",
            )


class TestNL2SQLResponse:
    def test_success_defaults(self):
        resp = NL2SQLResponse(status="success", sql_query="SELECT 1", is_validated=True)
        assert resp.impact_rows == 0
        assert resp.error is None
        assert resp.error_code is None

    def test_error_response(self):
        resp = NL2SQLResponse(
            status="error",
            error_code="SQL_VALIDATION_FAILED",
            error="Blocked: DML keyword detected.",
            is_validated=False,
        )
        assert resp.sql_query is None
        assert resp.is_validated is False


class TestRegisterSchemaMetrics:
    def test_valid(self):
        m = RegisterSchemaMetrics(indexed_tables=3, indexed_few_shots=2, vector_chunks_created=5)
        assert m.vector_chunks_created == 5

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            RegisterSchemaMetrics(indexed_tables=1, indexed_few_shots=0)  # type: ignore


class TestRegisterSchemaRequest:
    def test_mode_default(self):
        req = RegisterSchemaRequest(db_id="x", tables=[])
        assert req.mode == "upsert"

    def test_few_shot_default_empty(self):
        req = RegisterSchemaRequest(db_id="x", tables=[])
        assert req.few_shot_examples == []
