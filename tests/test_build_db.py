"""Database builder tests (written first): fixed seed -> identical data."""

from datetime import date

from database.build_db import SEED, generate_created_at, generate_transactions

ACCOUNTS = list(range(1, 201))


def test_transactions_are_reproducible_with_the_fixed_seed():
    assert generate_transactions(ACCOUNTS, SEED) == generate_transactions(ACCOUNTS, SEED)
    assert generate_transactions(ACCOUNTS, SEED) != generate_transactions(ACCOUNTS, SEED + 1)


def test_transactions_are_the_biggest_table_and_valid():
    rows = generate_transactions(ACCOUNTS, SEED)
    assert len(rows) >= 1000
    for account_id, txn_date, txn_type, amount in rows:
        assert account_id in ACCOUNTS
        assert date(2024, 1, 1) <= txn_date <= date(2025, 12, 31)
        assert txn_type in ("DEPOSIT", "WITHDRAWAL")
        assert amount > 0 and round(amount, 2) == amount


def test_created_at_is_reproducible():
    a = generate_created_at(ACCOUNTS, SEED)
    assert a == generate_created_at(ACCOUNTS, SEED)
    assert set(a) == set(ACCOUNTS)
    assert all(date(2022, 1, 1) <= d <= date(2023, 12, 31) for d in a.values())
