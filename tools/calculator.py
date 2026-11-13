"""Tool 3 - Calculator: exact arithmetic on numbers returned by the database.

Small models make arithmetic mistakes, so differences, percentages, ratios and
growth are computed here. Only numbers, + - * / // % ** and round/abs/min/max
are allowed (parsed with `ast`, never `eval`).
"""

import ast
import operator
import re
from typing import Any, Dict

OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
             ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCTIONS = {"round": round, "abs": abs, "min": min, "max": max}
MAX_EXPONENT = 100


class CalculatorTool:
    """Safely evaluates an arithmetic expression."""

    name = "calculator"

    def _eval(self, node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return self._eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = self._eval(node.left), self._eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise ValueError("exponent too large")
            return OPERATORS[type(node.op)](left, right)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in FUNCTIONS and not node.keywords):
            return FUNCTIONS[node.func.id](*(self._eval(a) for a in node.args))
        raise ValueError(f"unsupported element '{ast.dump(node)[:40]}'")

    def calculate(self, expression: str) -> Dict[str, Any]:
        """Return {"status": "success", "result"} or {"status": "error", "error"}. Never raises."""
        expr = (expression or "").strip()
        # accept thousands separators like 1,250,000.50 (but keep commas between function arguments)
        expr = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", expr)
        if not expr:
            return {"status": "error", "error": "Empty expression.", "expression": expression}
        try:
            value = self._eval(ast.parse(expr, mode="eval"))
        except ZeroDivisionError:
            return {"status": "error", "error": "Division by zero.", "expression": expression}
        except (SyntaxError, ValueError, TypeError, OverflowError) as err:
            return {"status": "error", "error": f"Invalid expression: {err}", "expression": expression}
        return {"status": "success", "result": round(float(value), 6), "expression": expression}
