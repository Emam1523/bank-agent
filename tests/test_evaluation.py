"""Evaluation grader and metric tests (written first)."""

import pytest

from evaluation.grade import extract_numbers, grade, pass_at_1, pass_hat_k


def test_extract_numbers_handles_commas_currency_and_percent():
    assert extract_numbers("Total is BDT 1,234,567.89 (12.5%) in 2025") == [1234567.89, 12.5, 2025.0]
    assert extract_numbers("No numbers here") == []


@pytest.mark.parametrize("answer,expected,ok", [
    ("There are 350 branches.", {"type": "number", "values": [350]}, True),
    ("There are 351 branches.", {"type": "number", "values": [350]}, False),
    ("Average is 1,256,201.40 BDT, 25.1% above the minimum.", {"type": "number", "values": [1256201.4, 25.13]}, True),
    ("Average is 1,256,201.40 BDT.", {"type": "number", "values": [1256201.4, 25.13]}, False),
    ("Growth was 4.4%.", {"type": "number", "values": [4.378]}, True),          # rounded to 1 decimal
    ("Dhaka has the most branches.", {"type": "text", "values": ["Dhaka"]}, True),
    ("Chittagong has the most.", {"type": "text", "values": ["Dhaka"]}, False),
    ("Fixed deposit accounts hold the most.", {"type": "text", "values": ["FIXED_DEPOSIT|fixed deposit"]}, True),
    ("Savings accounts hold the most.", {"type": "text", "values": ["FIXED_DEPOSIT|fixed deposit"]}, False),
    ("The database does not contain interest rates.", {"type": "none"}, True),
    ("The interest rate is 7%.", {"type": "none"}, False),
    ("I cannot answer that from this database.", {"type": "none"}, True),
])
def test_grade(answer, expected, ok):
    assert grade(answer, expected) is ok


def test_pass_metrics():
    runs = {"q1": [True, True, True], "q2": [True, False, True], "q3": [False, False, False]}
    assert pass_at_1(runs) == pytest.approx((1 + 2 / 3 + 0) / 3)
    assert pass_hat_k(runs) == pytest.approx(1 / 3)


def test_expected_answers_keep_columns_with_duplicate_names():
    """Regression: two unnamed ROUND(...) columns used to collapse into one expected value."""
    from evaluation.run_eval import compute_expected
    spec = compute_expected([{"id": "x", "type": "number", "expected_sql": "SELECT ROUND(1.234, 2), ROUND(5.678, 2)"},
                             {"id": "y", "type": "none", "expected_sql": None}])
    assert spec == {"x": {"type": "number", "values": [1.23, 5.68]}, "y": {"type": "none"}}
