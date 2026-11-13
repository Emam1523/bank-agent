"""Rebuild the database so anyone gets exactly the same data.

1. schema.sql  - drops and creates the 3 tables;
2. seed.sql    - fixed branches (350) and accounts (200), checked into the repo;
3. this script - account opening dates and ~1,800 transactions generated with
                 random.Random(SEED), so every rebuild is identical.

Run:  python -m database.build_db
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from database.connection import get_db_connection, get_safe_db_summary

SEED = 42
SQL_DIR = Path(__file__).resolve().parent
TXN_START, TXN_END = date(2024, 1, 1), date(2025, 12, 31)
OPEN_START, OPEN_END = date(2022, 1, 1), date(2023, 12, 31)

Transaction = Tuple[int, date, str, Decimal]


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate_created_at(account_ids: Sequence[int], seed: int = SEED) -> Dict[int, date]:
    """Opening date for every account (2022-2023)."""
    rng = random.Random(seed)
    return {acc: _random_date(rng, OPEN_START, OPEN_END) for acc in sorted(account_ids)}


def generate_transactions(account_ids: Sequence[int], seed: int = SEED) -> List[Transaction]:
    """3-15 transactions per account in 2024-2025; ~65% deposits.

    2025 deposits are drawn from a slightly higher range so growth questions
    have a clear, non-zero answer.
    """
    rng = random.Random(seed + 1)
    rows: List[Transaction] = []
    for acc in sorted(account_ids):
        for _ in range(rng.randint(3, 15)):
            day = _random_date(rng, TXN_START, TXN_END)
            if rng.random() < 0.65:
                high = 120_000 if day.year == 2025 else 100_000
                rows.append((acc, day, "DEPOSIT", Decimal(rng.randint(1_000_00, high * 100)) / 100))
            else:
                rows.append((acc, day, "WITHDRAWAL", Decimal(rng.randint(500_00, 60_000_00)) / 100))
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def build_database() -> Dict[str, int]:
    """Create schema, load seed data, add generated data. Returns row counts."""
    conn = get_db_connection(read_only=False)
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
            cur.execute((SQL_DIR / "seed.sql").read_text(encoding="utf-8"))
            cur.execute("SELECT account_id FROM user_accounts ORDER BY account_id")
            accounts = [r[0] for r in cur.fetchall()]
            cur.executemany("UPDATE user_accounts SET created_at = %s WHERE account_id = %s",
                            [(d, acc) for acc, d in generate_created_at(accounts).items()])
            cur.executemany("INSERT INTO transactions (account_id, txn_date, txn_type, amount) "
                            "VALUES (%s, %s, %s, %s)", generate_transactions(accounts))
            counts = {}
            for table in ("bank_information", "user_accounts", "transactions"):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
        return counts
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Building database at {get_safe_db_summary()} (seed={SEED}) ...")
    print("Row counts:", build_database())
