"""Calculator tool tests (written first)."""

import pytest

from tools.calculator import CalculatorTool

calc = CalculatorTool()


@pytest.mark.parametrize("expr,value", [
    ("2 + 3 * 4", 14),
    ("(500 - 400) / 400 * 100", 25.0),
    ("-5 + 2", -3),
    ("2 ** 10", 1024),
    ("round(1307879.1934, 2)", 1307879.19),
    ("abs(-3.5)", 3.5),
    ("max(3, 9, 4) - min(3, 9, 4)", 6),
    ("1,250,000.50 - 250,000.50", 1000000.0),  # thousands separators are accepted
])
def test_valid_expressions(expr, value):
    res = calc.calculate(expr)
    assert res["status"] == "success" and res["result"] == pytest.approx(value)


@pytest.mark.parametrize("expr", [
    "__import__('os').system('dir')",
    "open('x')",
    "1 / 0",
    "",
    "2 +",
    "9 ** 9999",
])
def test_rejected_expressions(expr):
    res = calc.calculate(expr)
    assert res["status"] == "error" and res["error"]
