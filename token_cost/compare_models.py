"""Bonus: compare two models on the same 100 prompts (tokenizer, output, latency, cost).

    python -m token_cost.compare_models results results_3b
"""

import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent


def _totals(rows: List[Dict[str, Any]], lang: str, key: str) -> float:
    return sum(float(r[key]) for r in rows if r["language"] == lang)


def compare_models(rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`a` and `b` are results.csv rows of two models for the same prompts."""
    key = lambda r: (str(r["id"]), r["language"])
    b_by = {key(r): r for r in rows_b}
    same = [int(float(r["input_tokens"])) == int(float(b_by[key(r)]["input_tokens"])) for r in rows_a]

    def per_model(rows):
        return {
            "bn_en_input": _totals(rows, "bn", "input_tokens") / _totals(rows, "en", "input_tokens"),
            "bn_en_cost": _totals(rows, "bn", "cost_usd") / _totals(rows, "en", "cost_usd"),
        }

    pa, pb = per_model(rows_a), per_model(rows_b)
    return {
        "identical_input_counts": sum(same) / len(same),
        "by_language": {lang: {
            "input_tokens": {"a": int(_totals(rows_a, lang, "input_tokens")), "b": int(_totals(rows_b, lang, "input_tokens"))},
            "output_tokens": {"a": int(_totals(rows_a, lang, "output_tokens")), "b": int(_totals(rows_b, lang, "output_tokens"))},
            "latency_mean": {"a": round(mean(float(r["latency_s"]) for r in rows_a if r["language"] == lang), 2),
                             "b": round(mean(float(r["latency_s"]) for r in rows_b if r["language"] == lang), 2)},
            "truncated": {"a": sum(str(r["truncated"]) == "True" for r in rows_a if r["language"] == lang),
                          "b": sum(str(r["truncated"]) == "True" for r in rows_b if r["language"] == lang)},
        } for lang in ("en", "bn")},
        "bn_en_input_ratio": {"a": round(pa["bn_en_input"], 4), "b": round(pb["bn_en_input"], 4)},
        "bn_en_total_cost_ratio": {"a": round(pa["bn_en_cost"], 4), "b": round(pb["bn_en_cost"], 4)},
    }


def _load(folder: str) -> List[Dict[str, Any]]:
    with (HERE / folder / "results.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    a, b = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("results", "results_3b")
    meta = {f: json.loads((HERE / f / "run_meta.json").read_text(encoding="utf-8")) for f in (a, b)}
    res = {"a": {"folder": a, "model": meta[a]["model"], "overhead": meta[a]["template_overhead_tokens"]},
           "b": {"folder": b, "model": meta[b]["model"], "overhead": meta[b]["template_overhead_tokens"]},
           **compare_models(_load(a), _load(b))}
    (HERE / "model_comparison.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
