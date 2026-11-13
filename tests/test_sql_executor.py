"""Tests for SQL Executor Tool: Query Execution, Safety, and SQL Injection Prevention."""

import pytest
from tools.sql_executor import SQLExecutorTool


@pytest.fixture
def executor():
    return SQLExecutorTool()


# ---------------------------------------------------------------------------
# 1. Retrieve all banks
# ---------------------------------------------------------------------------
def test_retrieve_all_banks(executor):
    """Verify executing query to retrieve all banks."""
    query = "SELECT bank_id, bank_name, district, status FROM bank_information;"
    result = executor.execute_query(query)
    assert result["status"] == "success"
    assert result["row_count"] >= 20
    assert len(result["rows"]) == result["row_count"]
    assert "bank_name" in result["columns"]


# ---------------------------------------------------------------------------
# 2. Retrieve banks by district
# ---------------------------------------------------------------------------
def test_retrieve_banks_by_district(executor):
    """Verify executing query to retrieve banks filtered by district."""
    query = "SELECT bank_name, district FROM bank_information WHERE LOWER(district) = 'chittagong';"
    result = executor.execute_query(query)
    assert result["status"] == "success"
    assert result["row_count"] > 0
    for row in result["rows"]:
        assert row["district"].lower() == "chittagong"


# ---------------------------------------------------------------------------
# 3. Retrieve active banks
# ---------------------------------------------------------------------------
def test_retrieve_active_banks(executor):
    """Verify executing query to retrieve active banks."""
    query = "SELECT bank_name, status FROM bank_information WHERE status = 'ACTIVE';"
    result = executor.execute_query(query)
    assert result["status"] == "success"
    assert result["row_count"] > 0
    for row in result["rows"]:
        assert row["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# 4. Search by bank name
# ---------------------------------------------------------------------------
def test_search_by_bank_name(executor):
    """Verify executing search by bank name using ILIKE."""
    query = "SELECT bank_name, routing_number, district FROM bank_information WHERE bank_name ILIKE '%Sonali Bank%';"
    result = executor.execute_query(query)
    assert result["status"] == "success"
    assert result["row_count"] > 0
    for row in result["rows"]:
        assert "sonali bank" in row["bank_name"].lower()


# ---------------------------------------------------------------------------
# 5. Search by routing number
# ---------------------------------------------------------------------------
def test_search_by_routing_number(executor):
    """Verify search by specific routing number returns exact branch."""
    query = "SELECT bank_name, routing_number, district FROM bank_information WHERE routing_number = '200260123';"
    result = executor.execute_query(query)
    assert result["status"] == "success"
    assert result["row_count"] == 1
    assert result["rows"][0]["routing_number"] == "200260123"
    assert "Sonali Bank" in result["rows"][0]["bank_name"]


# ---------------------------------------------------------------------------
# 8. SQL Injection Attempts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("malicious_sql", [
    "SELECT * FROM bank_information; DROP TABLE bank_information; --",
    "SELECT * FROM bank_information; DELETE FROM bank_information;",
    "SELECT * FROM bank_information; TRUNCATE TABLE user_accounts;",
    "SELECT * FROM bank_information WHERE 1=1; ALTER TABLE bank_information DROP COLUMN status;",
    "SELECT * FROM bank_information; pg_sleep(10);",
])
def test_sql_injection_attempts_blocked(executor, malicious_sql):
    """Verify SQL injection attempts (chaining, multi-statement, destructive calls) are blocked."""
    result = executor.execute_query(malicious_sql)
    assert result["status"] == "error"
    assert "SQL Validation Blocked" in result["error"]
    assert result["row_count"] == 0


# ---------------------------------------------------------------------------
# 9. Blocked Write Operations
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("write_query", [
    "INSERT INTO bank_information (bank_name, district) VALUES ('Fake Bank', 'Dhaka');",
    "UPDATE bank_information SET status = 'INACTIVE' WHERE district = 'Dhaka';",
    "DELETE FROM bank_information WHERE district = 'Dhaka';",
    "DROP TABLE user_accounts;",
    "TRUNCATE TABLE bank_information;",
    "ALTER TABLE bank_information ADD COLUMN test_col VARCHAR(10);",
    "CREATE TABLE test_table (id INT);",
    "GRANT ALL PRIVILEGES ON bank_information TO public;",
])
def test_blocked_write_operations(executor, write_query):
    """Verify that all data/schema modifying statements are strictly rejected."""
    result = executor.execute_query(write_query)
    assert result["status"] == "error"
    assert "SQL Validation Blocked" in result["error"]
    assert result["row_count"] == 0


# ---------------------------------------------------------------------------
# Limit enforcement and capping
# ---------------------------------------------------------------------------
def test_limit_enforcement(executor):
    """Verify default LIMIT is appended when query has no limit."""
    query = "SELECT * FROM bank_information"
    is_valid, safe_sql, _ = executor.validate_sql(query)
    assert is_valid is True
    assert "LIMIT 50" in safe_sql


def test_limit_capping(executor):
    """Verify excessive LIMIT (e.g. 1000) is capped to MAX_ALLOWED_LIMIT (100)."""
    query = "SELECT * FROM bank_information LIMIT 1000;"
    is_valid, safe_sql, _ = executor.validate_sql(query)
    assert is_valid is True
    assert "LIMIT 100" in safe_sql


# ---------------------------------------------------------------------------
# Validator hardening (no database needed)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sql", [
    "SELECT * FROM pg_user",
    "SELECT usename, passwd FROM pg_shadow",
    "SELECT table_name FROM information_schema.tables",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT current_setting('data_directory')",
    "SELECT * FROM secrets",
    "SELECT * INTO backup FROM bank_information",
    "SELECT * FROM bank_information -- comment",
    "SELECT * FROM bank_information /* x */",
    "WITH d AS (DELETE FROM bank_information RETURNING *) SELECT * FROM d",
    "EXPLAIN ANALYZE SELECT * FROM bank_information",
])
def test_dangerous_or_unknown_queries_blocked(executor, sql):
    ok, _, err = executor.validate_sql(sql)
    assert ok is False and err


@pytest.mark.parametrize("sql", [
    "SELECT bank_name FROM bank_information WHERE address ILIKE '%update%'",
    "SELECT bank_name FROM bank_information WHERE bank_name = 'A; B'",
    "SELECT EXTRACT(YEAR FROM created_at) AS y, COUNT(*) FROM user_accounts GROUP BY 1",
    "SELECT SUM(t.amount) FROM transactions t WHERE EXTRACT(YEAR FROM t.txn_date) = 2025",
    "WITH d AS (SELECT district FROM bank_information) SELECT district FROM d",
    "SELECT u.user_name, b.bank_name FROM user_accounts u JOIN bank_information b ON b.bank_id = u.bank_id",
])
def test_legitimate_queries_allowed(executor, sql):
    ok, safe_sql, err = executor.validate_sql(sql)
    assert ok is True, err
    assert safe_sql.endswith(";")


def test_limit_all_and_offset_capped(executor):
    _, sql1, _ = executor.validate_sql("SELECT * FROM bank_information LIMIT ALL")
    assert sql1.endswith("LIMIT 100;")
    _, sql2, _ = executor.validate_sql("SELECT * FROM bank_information LIMIT 500 OFFSET 10;")
    assert sql2 == "SELECT * FROM bank_information LIMIT 100 OFFSET 10;"


def test_subquery_limit_does_not_skip_outer_limit(executor):
    _, sql, _ = executor.validate_sql(
        "SELECT * FROM bank_information WHERE bank_id IN (SELECT bank_id FROM user_accounts LIMIT 5)")
    assert sql.endswith(") LIMIT 50;")


def test_execution_error_reported_with_type(executor):
    result = executor.execute_query("SELECT branch_name FROM bank_information")
    assert result["status"] == "error" and result["error_type"] == "database"
    assert "branch_name" in result["error"]
