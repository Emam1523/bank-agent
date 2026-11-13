"""Tool 2 - SQL Executor: validate, then run read-only SQL on PostgreSQL (never generates SQL)."""

import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

from agent.prompts import SCHEMA
from database.connection import DatabaseConnectionError, get_db_connection

ALLOWED_TABLES = set(SCHEMA)
KNOWN_COLUMNS = {col for cols in SCHEMA.values() for col in cols}

# Write/admin keywords and dangerous functions. Matched after string literals are removed.
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"EXEC|EXECUTE|CALL|DO|COPY|VACUUM|ANALYZE|CLUSTER|REINDEX|COMMENT|LOCK|DISCARD|"
    r"PREPARE|DEALLOCATE|LISTEN|NOTIFY|SET|RESET|SECURITY|INTO|"
    r"pg_\w+|information_schema|current_setting|set_config|dblink\w*|lo_\w+)\b",
    re.IGNORECASE,
)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
TABLE_REF = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
CTE_NAME = re.compile(r"(?:\bWITH|,)\s*([A-Za-z_]\w*)\s+AS\s*\(", re.IGNORECASE)
TRAILING_LIMIT = re.compile(r"\bLIMIT\s+(\d+|ALL)(\s+OFFSET\s+\d+)?\s*$", re.IGNORECASE)


class SQLExecutorTool:
    """Validates SQL against safety rules and executes it in a read-only session."""

    name = "sql_executor"
    MAX_ROWS = 100      # hard cap on rows returned
    DEFAULT_LIMIT = 50  # appended when a query has no LIMIT

    def validate_sql(self, sql: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Return (is_valid, safe_sql, error).

        Rules: one statement; starts with SELECT/WITH; no comments; no write/admin
        keywords or system catalogs; only known tables; LIMIT added or capped.
        """
        if not sql or not sql.strip():
            return False, None, "SQL query cannot be empty."

        stmt = sql.strip().rstrip(";").strip()
        code = STRING_LITERAL.sub("''", stmt)  # inspect code only, not data inside quotes

        if ";" in code:
            return False, None, "Multiple SQL statements are not allowed."
        if "--" in code or "/*" in code:
            return False, None, "SQL comments are not allowed."
        first = code.split()[0].upper() if code else ""
        if first not in ("SELECT", "WITH"):
            return False, None, f"Only read-only SELECT queries are permitted (got '{first}')."

        bad = FORBIDDEN.search(code)
        if bad:
            return False, None, f"Forbidden keyword '{bad.group(0)}' detected."

        allowed = ALLOWED_TABLES | {n.lower() for n in CTE_NAME.findall(code)}
        for name in TABLE_REF.findall(code):
            n = name.lower()
            # FROM can also be part of EXTRACT(x FROM column) / TRIM(... FROM column),
            # where the column may be qualified: EXTRACT(YEAR FROM t.txn_date)
            if n not in allowed and n.split(".")[-1] not in KNOWN_COLUMNS:
                return False, None, f"Unknown or disallowed table '{name}'."

        limit = TRAILING_LIMIT.search(stmt)
        if not limit:
            stmt = f"{stmt} LIMIT {self.DEFAULT_LIMIT}"
        elif limit.group(1).upper() == "ALL" or int(limit.group(1)) > self.MAX_ROWS:
            stmt = stmt[:limit.start()] + f"LIMIT {self.MAX_ROWS}" + (limit.group(2) or "")
        return True, f"{stmt};", None

    @staticmethod
    def _serialize(value: Any) -> Any:
        """Make DB values JSON-friendly (Decimal -> float, dates -> ISO text)."""
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def execute_query(self, sql: str) -> Dict[str, Any]:
        """Validate and run `sql`. Never raises.

        Returns:
            {"status": "success"|"error", "error_type": None|"validation"|"database"|"connection",
             "row_count", "columns", "rows", "sql", "error", "elapsed_ms"}
        """
        result: Dict[str, Any] = {"status": "error", "error_type": None, "row_count": 0,
                                  "columns": [], "rows": [], "sql": sql, "error": None, "elapsed_ms": 0}

        ok, safe_sql, err = self.validate_sql(sql)
        if not ok:
            return {**result, "error_type": "validation", "error": f"SQL Validation Blocked: {err}"}
        result["sql"] = safe_sql

        start = time.perf_counter()
        try:
            conn = get_db_connection(read_only=True)
        except DatabaseConnectionError as e:
            return {**result, "error_type": "connection", "error": f"Database Connection Error: {e}"}
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(safe_sql)
                rows = cur.fetchmany(self.MAX_ROWS)
                columns = [d.name for d in cur.description] if cur.description else []
        except psycopg.Error as e:
            msg = e.diag.message_primary or str(e)
            return {**result, "error_type": "database", "error": f"PostgreSQL Execution Error: {msg}"}
        finally:
            conn.close()

        rows = [{k: self._serialize(v) for k, v in r.items()} for r in rows]
        return {**result, "status": "success", "row_count": len(rows), "columns": columns, "rows": rows,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)}
