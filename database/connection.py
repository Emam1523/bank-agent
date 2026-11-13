"""PostgreSQL connection management.

Settings come from environment variables (.env). Agent queries use read-only
sessions enforced by PostgreSQL itself; only `build_db` opens a writable one.
The password is never included in logs or error messages.
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

STATEMENT_TIMEOUT_MS = 5000  # kill runaway queries server-side


class DatabaseConnectionError(Exception):
    """Raised when a PostgreSQL connection cannot be established."""


def get_db_config() -> Dict[str, Any]:
    """Read connection settings from the environment (re-read on every call)."""
    return {
        "host": os.getenv("DB_HOST", "localhost").strip(),
        "port": int(os.getenv("DB_PORT", "5434")),
        "dbname": os.getenv("DB_NAME", "postgres").strip(),
        "user": os.getenv("DB_USER", "postgres").strip(),
        "password": os.getenv("DB_PASSWORD", "postgres").strip(),
    }


def get_safe_db_summary() -> str:
    """Connection summary that never contains the password."""
    c = get_db_config()
    return f"host={c['host']}:{c['port']} dbname={c['dbname']} user={c['user']}"


def get_db_connection(read_only: bool = True) -> psycopg.Connection:
    """Open a new autocommit connection.

    With ``read_only=True`` every transaction of the session is read-only
    (``default_transaction_read_only=on``), so PostgreSQL rejects any write even
    if SQL validation were bypassed. A statement timeout is always applied.

    Raises:
        DatabaseConnectionError: if PostgreSQL is unreachable.
    """
    c = get_db_config()
    options = f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"
    if read_only:
        options += " -c default_transaction_read_only=on"
    try:
        return psycopg.connect(**c, connect_timeout=5, autocommit=True, options=options)
    except psycopg.Error as err:
        raise DatabaseConnectionError(
            f"Failed to connect to PostgreSQL at {c['host']}:{c['port']} "
            f"(database '{c['dbname']}', user '{c['user']}'): {err}"
        ) from None


@contextmanager
def get_db_cursor() -> Iterator[psycopg.Cursor]:
    """Yield a read-only dict-row cursor; the connection is closed on exit."""
    conn = get_db_connection()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
    finally:
        conn.close()


def check_db_health() -> bool:
    """Return True if `SELECT 1` succeeds."""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    except Exception:
        return False
