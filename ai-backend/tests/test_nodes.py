"""
agent/nodes.py — LangGraph node fonksiyonları için unit testler.

Tüm harici bağımlılıklar (LLM, DBInspector) mock'lanır.
async fonksiyonlar asyncio.run() ile çalıştırılır (pytest-asyncio gerektirmez).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    """Async coroutine'i senkron olarak çalıştır."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# validate_sql_node testleri
# ---------------------------------------------------------------------------
class TestValidateSqlNode:

    def test_valid_sql_sets_is_validated_true(self, sample_agent_state):
        from agent.nodes import validate_sql_node
        state = {**sample_agent_state, "generated_sql": "SELECT * FROM users"}
        result = _run(validate_sql_node(state))
        assert result["validation_error"] is None
        assert result["is_validated"] is True

    def test_invalid_sql_sets_is_validated_false(self, sample_agent_state):
        from agent.nodes import validate_sql_node
        state = {**sample_agent_state, "generated_sql": "DROP TABLE users"}
        result = _run(validate_sql_node(state))
        assert result["validation_error"] is not None
        assert result["is_validated"] is False

    def test_invalid_sql_increments_retry_count(self, sample_agent_state):
        from agent.nodes import validate_sql_node
        state = {**sample_agent_state, "generated_sql": "DELETE FROM users", "retry_count": 1}
        result = _run(validate_sql_node(state))
        assert result["retry_count"] == 2

    def test_empty_sql_is_invalid(self, sample_agent_state):
        from agent.nodes import validate_sql_node
        state = {**sample_agent_state, "generated_sql": ""}
        result = _run(validate_sql_node(state))
        assert result["is_validated"] is False

    def test_dml_insert_blocked(self, sample_agent_state):
        from agent.nodes import validate_sql_node
        state = {**sample_agent_state, "generated_sql": "INSERT INTO users VALUES (1)"}
        result = _run(validate_sql_node(state))
        assert result["is_validated"] is False
        assert result["validation_error"] is not None


# ---------------------------------------------------------------------------
# execute_sql_node testleri
# ---------------------------------------------------------------------------
class TestExecuteSqlNode:

    @patch("agent.nodes.DBInspector")
    def test_dry_run_adds_limit_postgresql(self, mock_inspector_cls, sample_agent_state):
        """PostgreSQL: dry_run_limit=5 → 'LIMIT 5' SQL'e eklenmeli."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.return_value = [{"id": 1}]
        mock_inspector_cls.return_value = mock_inspector

        state = {
            **sample_agent_state,
            "connection_string": "postgresql://u:p@host:5432/db",
            "generated_sql": "SELECT * FROM users",
            "dry_run_limit": 5,
        }

        from agent.nodes import execute_sql_node
        result = _run(execute_sql_node(state))

        called_sql = mock_inspector.execute_read_only.call_args[0][0]
        assert "LIMIT 5" in called_sql
        # generated_sql dönen dict'te olmamalı — state'deki temiz SQL korunur
        assert "generated_sql" not in result
        assert result["validation_error"] is None

    @patch("agent.nodes.DBInspector")
    def test_dry_run_adds_top_mssql(self, mock_inspector_cls, sample_agent_state):
        """MSSQL: dry_run_limit=5 → 'SELECT TOP 5' kullanılmalı."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.return_value = []
        mock_inspector_cls.return_value = mock_inspector

        state = {
            **sample_agent_state,
            "connection_string": "mssql+pyodbc://u:p@host/db",
            "generated_sql": "SELECT * FROM dbo.Orders",
            "dry_run_limit": 5,
        }

        from agent.nodes import execute_sql_node
        result = _run(execute_sql_node(state))

        called_sql = mock_inspector.execute_read_only.call_args[0][0]
        assert "TOP 5" in called_sql.upper()
        assert "LIMIT" not in called_sql.upper()

    @patch("agent.nodes.DBInspector")
    def test_no_double_limit_injection(self, mock_inspector_cls, sample_agent_state):
        """SQL zaten LIMIT içeriyorsa çift enjeksiyon yapılmamalı."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.return_value = []
        mock_inspector_cls.return_value = mock_inspector

        state = {
            **sample_agent_state,
            "connection_string": "postgresql://u:p@host/db",
            "generated_sql": "SELECT * FROM users LIMIT 10",
            "dry_run_limit": 5,
        }

        from agent.nodes import execute_sql_node
        _run(execute_sql_node(state))

        called_sql = mock_inspector.execute_read_only.call_args[0][0]
        assert called_sql.upper().count("LIMIT") == 1

    @patch("agent.nodes.DBInspector")
    def test_no_dry_run_limit_uses_original_sql(self, mock_inspector_cls, sample_agent_state):
        """dry_run_limit=None ise orijinal SQL değişmeden kullanılmalı."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.return_value = []
        mock_inspector_cls.return_value = mock_inspector

        state = {**sample_agent_state, "dry_run_limit": None}

        from agent.nodes import execute_sql_node
        _run(execute_sql_node(state))

        called_sql = mock_inspector.execute_read_only.call_args[0][0]
        assert called_sql == "SELECT * FROM users"

    def test_invalid_connection_string_returns_error(self, sample_agent_state):
        """Geçersiz connection_string → non-retryable hata."""
        state = {**sample_agent_state, "connection_string": "not-a-url"}

        from agent.nodes import execute_sql_node
        from core.config import settings
        result = _run(execute_sql_node(state))

        assert result["execution_data"] is None
        assert result["retry_count"] == settings.MAX_RETRY_COUNT

    @patch("agent.nodes.DBInspector")
    def test_execution_failure_increments_retry(self, mock_inspector_cls, sample_agent_state):
        """DB çalıştırma hatası → retry_count artmalı."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.side_effect = Exception("DB bağlantı hatası")
        mock_inspector_cls.return_value = mock_inspector

        state = {**sample_agent_state, "retry_count": 0}

        from agent.nodes import execute_sql_node
        result = _run(execute_sql_node(state))

        assert result["execution_data"] is None
        assert result["retry_count"] == 1
        assert result["validation_error"] is not None

    @patch("agent.nodes.DBInspector")
    def test_mssql_already_has_top_no_double(self, mock_inspector_cls, sample_agent_state):
        """MSSQL SQL'i zaten SELECT TOP içeriyorsa tekrar eklenmemeli."""
        mock_inspector = MagicMock()
        mock_inspector.execute_read_only.return_value = []
        mock_inspector_cls.return_value = mock_inspector

        state = {
            **sample_agent_state,
            "connection_string": "mssql+pyodbc://u:p@host/db",
            "generated_sql": "SELECT TOP 10 * FROM dbo.Orders",
            "dry_run_limit": 5,
        }

        from agent.nodes import execute_sql_node
        _run(execute_sql_node(state))

        called_sql = mock_inspector.execute_read_only.call_args[0][0]
        # TOP sadece bir kez geçmeli
        assert called_sql.upper().count("TOP") == 1


# ---------------------------------------------------------------------------
# generate_sql_node testleri
# ---------------------------------------------------------------------------
class TestGenerateSqlNode:

    def test_llm_sql_returned(self, sample_agent_state, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.content = "SELECT * FROM users LIMIT 10"
        mock = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr("agent.nodes.ainvoke_with_retry", mock)

        from agent.nodes import generate_sql_node
        result = _run(generate_sql_node(sample_agent_state))
        assert "generated_sql" in result
        assert "SELECT" in result["generated_sql"].upper()

    def test_markdown_fences_stripped(self, sample_agent_state, monkeypatch):
        """LLM ```sql ... ``` döndürürse fence'ler temizlenmeli."""
        mock_resp = MagicMock()
        mock_resp.content = "```sql\nSELECT * FROM users\n```"
        mock = AsyncMock(return_value=mock_resp)
        monkeypatch.setattr("agent.nodes.ainvoke_with_retry", mock)

        from agent.nodes import generate_sql_node
        result = _run(generate_sql_node(sample_agent_state))
        assert "```" not in result["generated_sql"]

    def test_llm_failure_uses_fallback(self, sample_agent_state, monkeypatch):
        """LLM hatası durumunda fallback SQL kullanılmalı."""
        mock = AsyncMock(side_effect=Exception("Ollama bağlantı hatası"))
        monkeypatch.setattr("agent.nodes.ainvoke_with_retry", mock)

        from agent.nodes import generate_sql_node
        result = _run(generate_sql_node(sample_agent_state))
        assert "generated_sql" in result
        assert result["generated_sql"]  # boş olmamalı
