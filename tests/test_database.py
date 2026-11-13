"""Tests for Database Connection and Schema Integrity."""

import pytest
from database.connection import (
    get_db_connection,
    get_safe_db_summary,
    check_db_health,
    DatabaseConnectionError,
    get_db_config,
)


def test_database_connection():
    """Verify that PostgreSQL connection succeeds and version can be queried."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version();")
        res = cur.fetchone()
        assert res is not None
        assert "PostgreSQL" in res[0]
    finally:
        conn.close()


def test_database_health():
    """Verify check_db_health returns True on active database."""
    assert check_db_health() is True


def test_safe_db_summary_never_exposes_password():
    """Verify get_safe_db_summary masks/excludes database password key and value."""
    summary = get_safe_db_summary()
    assert "password=" not in summary.lower()
    assert "password:" not in summary.lower()
    assert "5434" in summary
    assert "dbname=" in summary


def test_database_connection_failure(monkeypatch):
    """Verify DatabaseConnectionError is raised when host/port is unreachable."""
    monkeypatch.setenv("DB_PORT", "9999")
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    with pytest.raises(DatabaseConnectionError) as exc_info:
        get_db_connection()
    # Confirm error message explains connection failure without leaking sensitive info
    assert "Failed to connect to PostgreSQL" in str(exc_info.value)
    assert "password" not in str(exc_info.value).lower()


def test_tables_and_seed_data_exist():
    """Verify required tables and realistic Bangladeshi seed records are populated."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Verify bank_information table has rows
        cur.execute("SELECT COUNT(*) FROM bank_information;")
        bank_count = cur.fetchone()[0]
        assert bank_count >= 20, f"Expected at least 20 banks, got {bank_count}"

        # Verify user_accounts table has rows
        cur.execute("SELECT COUNT(*) FROM user_accounts;")
        user_count = cur.fetchone()[0]
        assert user_count >= 5, f"Expected at least 5 user accounts, got {user_count}"

        # Verify specific Bangladeshi bank exists
        cur.execute("SELECT bank_name, district, status FROM bank_information WHERE bank_name ILIKE '%BRAC Bank%' AND district = 'Dhaka';")
        brac = cur.fetchone()
        assert brac is not None
        assert brac[2] == "ACTIVE"
    finally:
        conn.close()


def test_agent_connection_is_read_only_at_database_level():
    """Even if validation were bypassed, PostgreSQL itself must reject writes."""
    import psycopg
    conn = get_db_connection()  # read_only=True by default
    try:
        cur = conn.cursor()
        cur.execute("SHOW default_transaction_read_only;")
        assert cur.fetchone()[0] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            cur.execute("UPDATE bank_information SET status = status WHERE bank_id = 1;")
    finally:
        conn.close()


def test_three_related_tables_and_biggest_table_over_100_rows():
    """Assignment rule: >= 3 related tables and >= 100 rows in the biggest one."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions t JOIN user_accounts u ON u.account_id = t.account_id "
                    "JOIN bank_information b ON b.bank_id = u.bank_id")
        assert cur.fetchone()[0] >= 100
    finally:
        conn.close()
