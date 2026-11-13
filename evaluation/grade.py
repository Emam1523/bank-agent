"""Grading of final answers and the pass@1 / pass^k metrics."""

import re
from statistics import mean
from typing import Any, Dict, List

from agent.wrapper import extract_numbers

__all__ = ["extract_numbers", "grade", "pass_at_1", "pass_hat_k"]

REFUSAL = re.compile(
    r"\b(cannot|can't|can not|unable|not available|no (data|information|records?)|"
    r"(does not|doesn't|do not|don't) (contain|have|include|store|track|hold)|"
    r"not (stored|recorded|tracked|included) in)\b", re.IGNORECASE)


def _number_matches(expected: float, found: List[float]) -> bool:
    """Exact for whole numbers; otherwise the answer may round to 0, 1 or 2 decimals."""
    if float(expected).is_integer():
        return any(abs(f - expected) < 1e-9 for f in found)
    targets = {round(expected, d) for d in (0, 1, 2)} | {expected}
    return any(abs(f - t) < 0.006 for f in found for t in targets)


def grade(answer: str, expected: Dict[str, Any]) -> bool:
    """True if `answer` contains the expected result.

    expected = {"type": "number", "values": [...]}  every value must appear (rounding allowed)
             | {"type": "text",   "values": [...]}  every string must appear (case-insensitive, "A|B" = A or B)
             | {"type": "none"}                     the agent must say the database cannot answer
    """
    answer = answer or ""
    kind = expected["type"]
    if kind == "number":
        found = extract_numbers(answer)
        return all(_number_matches(float(v), found) for v in expected["values"])
    if kind == "text":  # "A|B" = either spelling is accepted
        low = answer.lower()
        return all(any(alt.lower() in low for alt in str(v).split("|")) for v in expected["values"])
    if kind == "none":
        return bool(REFUSAL.search(answer))
    raise ValueError(f"unknown expected type {kind!r}")


def pass_at_1(runs: Dict[str, List[bool]]) -> float:
    """Expected success rate of a single try: mean over questions of (passes / trials)."""
    return mean(sum(r) / len(r) for r in runs.values())


def pass_hat_k(runs: Dict[str, List[bool]]) -> float:
    """pass^k: share of questions answered correctly in ALL k trials (reliability)."""
    return mean(1.0 if all(r) else 0.0 for r in runs.values())
