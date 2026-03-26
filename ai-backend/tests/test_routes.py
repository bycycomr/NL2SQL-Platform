"""
api/routes.py — FastAPI endpoint'leri için integration testler (TestClient).

Tüm harici servisler (DB, ChromaDB, LLM agent) mock'lanır.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_VALID_CS = "postgresql://user:pass@localhost:5432/testdb"


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root_ok(self):
        resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/onboard/extract
# ---------------------------------------------------------------------------
class TestExtractSchema:

    @patch("api.routes.DBInspector")
    def test_success(self, mock_inspector_cls):
        mock_inspector = MagicMock()
        mock_inspector.get_schema.return_value = [
            {"name": "orders", "columns": ["id INTEGER", "total NUMERIC NOT NULL"], "human_description": "", "business_rules": ""},
        ]
        mock_inspector_cls.return_value = mock_inspector

        resp = client.post("/api/v1/onboard/extract", json={
            "db_id": "tenant_1",
            "db_type": "PostgreSQL",
            "connection_string": _VALID_CS,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["db_id"] == "tenant_1"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["table_name"] == "orders"
        assert data["tables"][0]["columns"][0]["name"] == "id"

    @patch("api.routes.DBInspector")
    def test_db_connection_failure_returns_400(self, mock_inspector_cls):
        mock_inspector_cls.side_effect = Exception("Connection refused")

        resp = client.post("/api/v1/onboard/extract", json={
            "db_id": "x",
            "db_type": "PostgreSQL",
            "connection_string": _VALID_CS,
        })

        assert resp.status_code == 400

    @patch("api.routes.DBInspector")
    def test_db_type_is_optional(self, mock_inspector_cls):
        """db_type opsiyonel — gönderilmeden de kabul edilmeli."""
        mock_inspector = MagicMock()
        mock_inspector.get_schema.return_value = []
        mock_inspector_cls.return_value = mock_inspector

        resp = client.post("/api/v1/onboard/extract", json={
            "db_id": "x",
            "connection_string": _VALID_CS,
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/onboard/register
# ---------------------------------------------------------------------------
class TestRegisterSchema:

    @patch("api.routes.save_schema_chunks")
    def test_success_with_metrics(self, mock_save):
        mock_save.return_value = {
            "indexed_tables": 1,
            "indexed_few_shots": 1,
            "vector_chunks_created": 2,
        }

        resp = client.post("/api/v1/onboard/register", json={
            "db_id": "tenant_1",
            "mode": "upsert",
            "tables": [{
                "table_name": "orders",
                "columns": [{"name": "id", "type": "INTEGER"}],
                "human_description": "Sipariş tablosu",
                "business_rules": "",
            }],
            "few_shot_examples": [
                {"question": "Bugünkü siparişler?", "query": "SELECT * FROM orders WHERE DATE(created_at) = CURRENT_DATE"}
            ],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["metrics"]["indexed_tables"] == 1
        assert data["metrics"]["indexed_few_shots"] == 1
        assert data["metrics"]["vector_chunks_created"] == 2

    @patch("api.routes.save_schema_chunks")
    def test_few_shot_query_key_normalized(self, mock_save):
        """Contract 'query' anahtarını kullanır; vector_store 'sql' bekler — normalize edilmeli."""
        mock_save.return_value = {"indexed_tables": 0, "indexed_few_shots": 1, "vector_chunks_created": 1}

        client.post("/api/v1/onboard/register", json={
            "db_id": "x", "mode": "upsert", "tables": [],
            "few_shot_examples": [{"question": "test?", "query": "SELECT 1"}],
        })

        _, kwargs = mock_save.call_args
        few_shots = kwargs.get("few_shot_examples") or mock_save.call_args[0][2]
        assert few_shots[0].get("sql") == "SELECT 1"
        assert "query" not in few_shots[0]

    @patch("api.routes.save_schema_chunks")
    def test_save_failure_returns_500(self, mock_save):
        mock_save.side_effect = RuntimeError("ChromaDB hatası")

        resp = client.post("/api/v1/onboard/register", json={
            "db_id": "x", "mode": "upsert", "tables": [],
        })
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/v1/generate-sql
# ---------------------------------------------------------------------------
class TestGenerateSql:

    _BASE_PAYLOAD = {
        "db_id": "tenant_1",
        "connection_string": _VALID_CS,
        "query": "En çok sipariş veren müşterileri getir",
    }

    @patch("api.routes.agent")
    def test_success_response_has_contract_fields(self, mock_agent):
        mock_agent.ainvoke = AsyncMock(return_value={
            "generated_sql": "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id",
            "explanation": "Siparişleri müşteriye göre grupladım.",
            "is_validated": True,
            "validation_error": None,
        })

        resp = client.post("/api/v1/generate-sql", json=self._BASE_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_validated"] is True
        assert data["impact_rows"] == 0
        assert "LIMIT" not in data["sql_query"]
        assert "data" not in data  # hibrit mimari — veri döndürülmez

    @patch("api.routes.agent")
    def test_validation_error_returns_error_response(self, mock_agent):
        mock_agent.ainvoke = AsyncMock(return_value={
            "generated_sql": "",
            "explanation": "",
            "is_validated": False,
            "validation_error": "Blocked: DML keyword detected.",
        })

        resp = client.post("/api/v1/generate-sql", json=self._BASE_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["is_validated"] is False
        assert data["error_code"] in ("SQL_VALIDATION_FAILED", "SCHEMA_NOT_FOUND")

    @patch("api.routes.agent")
    def test_with_dry_run_limit(self, mock_agent):
        mock_agent.ainvoke = AsyncMock(return_value={
            "generated_sql": "SELECT * FROM orders",
            "explanation": "Tüm siparişler.",
            "is_validated": True,
            "validation_error": None,
        })

        resp = client.post("/api/v1/generate-sql", json={
            **self._BASE_PAYLOAD,
            "dry_run_limit": 5,
        })

        assert resp.status_code == 200
        # Agent'a gönderilen state'de dry_run_limit olmalı
        call_args = mock_agent.ainvoke.call_args[0][0]
        assert call_args["dry_run_limit"] == 5

    @patch("api.routes.agent")
    def test_agent_exception_returns_error(self, mock_agent):
        mock_agent.ainvoke = AsyncMock(side_effect=Exception("Pipeline crash"))

        resp = client.post("/api/v1/generate-sql", json=self._BASE_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["error_code"] == "AGENT_ERROR"

    def test_invalid_connection_string_returns_422(self):
        resp = client.post("/api/v1/generate-sql", json={
            **self._BASE_PAYLOAD,
            "connection_string": "invalid-url",
        })
        assert resp.status_code == 422
