"""
services/vector_store.py — ChromaDB mock ile unit testler.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.vector_store import _table_to_text, save_schema_chunks


class TestTableToText:
    """_table_to_text() her iki kolon formatını desteklemeli."""

    def test_string_columns(self):
        table = {"table_name": "orders", "columns": ["id INTEGER", "total NUMERIC"]}
        text = _table_to_text(table)
        assert "TABLE: orders" in text
        assert "id INTEGER" in text
        assert "total NUMERIC" in text

    def test_dict_columns(self):
        table = {
            "table_name": "users",
            "columns": [{"name": "id", "type": "INTEGER"}, {"name": "email", "type": "VARCHAR"}],
        }
        text = _table_to_text(table)
        assert "TABLE: users" in text
        assert "id INTEGER" in text
        assert "email VARCHAR" in text

    def test_legacy_name_key(self):
        """Eski 'name' anahtarı da çalışmalı (geriye dönük uyum)."""
        table = {"name": "products", "columns": ["sku VARCHAR"]}
        text = _table_to_text(table)
        assert "TABLE: products" in text

    def test_human_description_included(self):
        table = {
            "table_name": "orders",
            "columns": [],
            "human_description": "Sipariş ana tablosu",
        }
        text = _table_to_text(table)
        assert "Sipariş ana tablosu" in text

    def test_business_rules_included(self):
        table = {
            "table_name": "orders",
            "columns": [],
            "business_rules": "Sadece aktif siparişler",
        }
        text = _table_to_text(table)
        assert "Sadece aktif siparişler" in text

    def test_empty_columns(self):
        table = {"table_name": "empty_table", "columns": []}
        text = _table_to_text(table)
        assert "TABLE: empty_table" in text


class TestSaveSchemaChunks:
    """save_schema_chunks() doğru metrics dict döndürmeli."""

    def _make_mock_collection(self) -> MagicMock:
        col = MagicMock()
        col.upsert = MagicMock()
        return col

    @patch("services.vector_store._get_collection")
    def test_returns_metrics_dict(self, mock_get_collection):
        mock_get_collection.return_value = self._make_mock_collection()

        tables = [
            {"table_name": "orders", "columns": [{"name": "id", "type": "INT"}]},
            {"table_name": "users", "columns": [{"name": "id", "type": "INT"}]},
        ]
        few_shots = [{"question": "Test?", "sql": "SELECT 1"}]

        result = save_schema_chunks("db1", tables, few_shots)

        assert result["indexed_tables"] == 2
        assert result["indexed_few_shots"] == 1
        assert result["vector_chunks_created"] == 3

    @patch("services.vector_store._get_collection")
    def test_no_few_shots(self, mock_get_collection):
        mock_get_collection.return_value = self._make_mock_collection()

        tables = [{"table_name": "products", "columns": []}]
        result = save_schema_chunks("db1", tables)

        assert result["indexed_tables"] == 1
        assert result["indexed_few_shots"] == 0
        assert result["vector_chunks_created"] == 1

    @patch("services.vector_store._get_collection")
    def test_upsert_called(self, mock_get_collection):
        col = self._make_mock_collection()
        mock_get_collection.return_value = col

        save_schema_chunks("db1", [{"table_name": "t", "columns": []}])
        col.upsert.assert_called_once()

    @patch("services.vector_store._get_collection")
    def test_upsert_failure_raises_runtime_error(self, mock_get_collection):
        col = self._make_mock_collection()
        col.upsert.side_effect = Exception("ChromaDB bağlantı hatası")
        mock_get_collection.return_value = col

        with pytest.raises(RuntimeError, match="Vector store upsert failed"):
            save_schema_chunks("db1", [{"table_name": "t", "columns": []}])
