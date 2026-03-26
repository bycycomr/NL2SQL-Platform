"""
Paylaşılan test fixture'ları.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
import services.sql_cache as _sql_cache_module


@pytest.fixture(autouse=True)
def clear_sql_cache():
    """Her test öncesi SQL cache'i temizle — testler arası state sızıntısını önler."""
    _sql_cache_module._cache.clear()
    yield
    _sql_cache_module._cache.clear()


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_agent_state() -> dict:
    """Geçerli bir AgentState taslağı."""
    return {
        "db_id": "test_db",
        "connection_string": "sqlite:///test.db",
        "question": "Tüm kullanıcıları getir",
        "relevant_schema": "TABLE: users\nCOLUMNS: id INTEGER, name VARCHAR",
        "generated_sql": "SELECT * FROM users",
        "validation_error": None,
        "explanation": "",
        "execution_data": None,
        "retry_count": 0,
        "dry_run_limit": None,
        "is_validated": False,
    }


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """LangChain LLM yanıtı mock'u."""
    response = MagicMock()
    response.content = "SELECT * FROM users LIMIT 10"
    return response


@pytest.fixture
def mock_async_llm(mock_llm_response, monkeypatch) -> AsyncMock:
    """ainvoke_with_retry'ı mock'la."""
    mock = AsyncMock(return_value=mock_llm_response)
    monkeypatch.setattr("agent.nodes.ainvoke_with_retry", mock)
    return mock
