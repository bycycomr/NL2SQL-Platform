"""
core/security.py — validate_sql() fonksiyonu için unit testler.
"""
import pytest

from core.security import validate_sql


class TestValidSQLPassThrough:
    """Geçerli SELECT sorguları geçmeli."""

    def test_simple_select(self):
        assert validate_sql("SELECT * FROM users") is None

    def test_select_with_where(self):
        assert validate_sql("SELECT id, name FROM users WHERE active = 1") is None

    def test_select_with_join(self):
        sql = "SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        assert validate_sql(sql) is None

    def test_select_with_group_by(self):
        sql = "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id ORDER BY 2 DESC"
        assert validate_sql(sql) is None

    def test_select_top_mssql(self):
        assert validate_sql("SELECT TOP 10 * FROM products") is None

    def test_select_with_limit(self):
        assert validate_sql("SELECT * FROM products LIMIT 5") is None

    def test_cte_select(self):
        sql = "WITH ranked AS (SELECT *, ROW_NUMBER() OVER (ORDER BY id) rn FROM users) SELECT * FROM ranked"
        assert validate_sql(sql) is None

    def test_trailing_semicolon(self):
        assert validate_sql("SELECT 1;") is None


class TestBlockedDML:
    """DML / DDL sorguları engellenmeli."""

    @pytest.mark.parametrize("sql", [
        "INSERT INTO users VALUES (1, 'test')",
        "UPDATE users SET name = 'x' WHERE id = 1",
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE users",
        "TRUNCATE TABLE orders",
        "ALTER TABLE users ADD COLUMN email TEXT",
        "CREATE TABLE new_table (id INT)",
        "MERGE INTO target USING source ON ...",
        "EXEC sp_executesql N'SELECT 1'",
    ])
    def test_blocked(self, sql: str):
        result = validate_sql(sql)
        assert result is not None
        assert "Blocked" in result


class TestEdgeCases:
    """Sınır durumları."""

    def test_empty_string(self):
        result = validate_sql("")
        assert result is not None

    def test_whitespace_only(self):
        result = validate_sql("   ")
        assert result is not None

    def test_non_sql_text(self):
        result = validate_sql("Bana kullanıcıları getir")
        assert result is not None  # AST parse edilemez → engellenir

    def test_case_insensitive_block(self):
        assert validate_sql("insert into t values (1)") is not None
        assert validate_sql("DROP table x") is not None
