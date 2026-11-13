"""Compare Bangla with English: per-pair ratios, spread, latency, per-category gap, chart.

    python -m token_cost.analyze [folder]   (default folder: token_cost/results)
"""

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Tuple

OUT = Path(__file__).resolve().parent / "results"
NUMERIC = ("input_tokens", "output_tokens", "net_input_tokens", "cost_usd", "latency_s")


def bootstrap_ci(values: List[float], n: int = 10_000, seed: int = 0, level: float = 0.95) -> Tuple[float, float]:
    """Percentile bootstrap interval of the mean (seeded, so it is reproducible)."""
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(n))
    lo, hi = means[int((1 - level) / 2 * n)], means[int((1 + level) / 2 * n) - 1]
    return round(lo, 4), round(hi, 4)


def describe(values: List[float]) -> Dict[str, Any]:
    lo, hi = bootstrap_ci(values)
    return {"mean": round(mean(values), 4), "median": round(median(values), 4),
            "min": round(min(values), 4), "max": round(max(values), 4), "ci95": [lo, hi]}


def compare_pairs(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per pair with English and Bangla numbers and the Bangla/English ratios."""
    by_id: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        by_id[str(r["id"])][r["language"]] = {**r, **{k: float(r[k]) for k in NUMERIC}}
    pairs = []
    for pid, langs in sorted(by_id.items(), key=lambda kv: int(kv[0])):
        en, bn = langs["en"], langs["bn"]
        pairs.append({
            "id": pid, "category": en["category"],
            "en_input": int(en["input_tokens"]), "bn_input": int(bn["input_tokens"]),
            "en_net_input": int(en["net_input_tokens"]), "bn_net_input": int(bn["net_input_tokens"]),
            "en_output": int(en["output_tokens"]), "bn_output": int(bn["output_tokens"]),
            "input_ratio": bn["input_tokens"] / en["input_tokens"],
            "net_input_ratio": bn["net_input_tokens"] / en["net_input_tokens"],
            "output_ratio": bn["output_tokens"] / en["output_tokens"] if en["output_tokens"] else float("nan"),
            "en_cost_usd": en["cost_usd"], "bn_cost_usd": bn["cost_usd"],
            "total_cost_ratio": bn["cost_usd"] / en["cost_usd"],
            "en_latency_s": en["latency_s"], "bn_latency_s": bn["latency_s"],
        })
    return pairs


def summarize(rows: List[Dict[str, Any]], pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    lang = {l: [r for r in rows if r["language"] == l] for l in ("en", "bn")}
    tot = {l: {k: sum(float(r[k]) for r in v) for k in NUMERIC} for l, v in lang.items()}
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        by_cat[p["category"]].append(p)
    return {
        "pairs": len(pairs),
        "totals": {l: {"input_tokens": int(t["input_tokens"]), "net_input_tokens": int(t["net_input_tokens"]),
                       "output_tokens": int(t["output_tokens"]), "cost_usd": round(t["cost_usd"], 6)}
                   for l, t in tot.items()},
        "overall_input_ratio": round(tot["bn"]["input_tokens"] / tot["en"]["input_tokens"], 4),
        "overall_net_input_ratio": round(tot["bn"]["net_input_tokens"] / tot["en"]["net_input_tokens"], 4),
        "overall_output_ratio": round(tot["bn"]["output_tokens"] / tot["en"]["output_tokens"], 4),
        "overall_total_cost_ratio": round(tot["bn"]["cost_usd"] / tot["en"]["cost_usd"], 4),
        "per_pair": {k: describe([p[k] for p in pairs])
                     for k in ("input_ratio", "net_input_ratio", "output_ratio", "total_cost_ratio")},
        "latency_s": {l: {"mean": round(mean(float(r["latency_s"]) for r in v), 2),
                          "median": round(median(float(r["latency_s"]) for r in v), 2)} for l, v in lang.items()},
        "truncated": {l: sum(str(r["truncated"]) == "True" for r in v) for l, v in lang.items()},
        "by_category": {c: {"pairs": len(v),
                            "net_input_ratio_mean": round(mean(p["net_input_ratio"] for p in v), 3),
                            "input_ratio_mean": round(mean(p["input_ratio"] for p in v), 3),
                            "total_cost_ratio_mean": round(mean(p["total_cost_ratio"] for p in v), 3)}
                        for c, v in sorted(by_cat.items())},
    }


def chart_svg(pairs: List[Dict[str, Any]], path: Path) -> None:
    """Bar = mean net-input ratio per category; dots = individual pairs; dashed line = parity (1.0)."""
    cats = sorted({p["category"] for p in pairs})
    vals = {c: [p["net_input_ratio"] for p in pairs if p["category"] == c] for c in cats}
    top = max(max(v) for v in vals.values()) * 1.1
    W, H, left, bottom, bw = 720, 380, 60, 320, 70
    y = lambda v: bottom - v / top * 260
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Arial" font-size="12">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{W/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">'
             'Bangla / English net input tokens per pair, by category</text>']
    for t in range(0, int(top) + 1):
        parts.append(f'<line x1="{left}" x2="{W-20}" y1="{y(t)}" y2="{y(t)}" stroke="#e5e5e5"/>'
                     f'<text x="{left-8}" y="{y(t)+4}" text-anchor="end">{t}x</text>')
    step = (W - left - 40) / len(cats)
    for i, c in enumerate(cats):
        x = left + 20 + i * step
        m = mean(vals[c])
        parts.append(f'<rect x="{x}" y="{y(m)}" width="{bw}" height="{bottom-y(m)}" fill="#2e75b6" opacity="0.85"/>'
                     f'<text x="{x+bw/2}" y="{bottom-24}" text-anchor="middle" font-weight="bold" fill="white">{m:.2f}x</text>'
                     f'<text x="{x+bw/2}" y="{bottom+18}" text-anchor="middle">{c}</text>')
        for j, v in enumerate(vals[c]):
            parts.append(f'<circle cx="{x+12+(j*7)%(bw-20)}" cy="{y(v)}" r="3" fill="#f39c12" stroke="#7f4f00"/>')
    parts.append(f'<line x1="{left}" x2="{W-20}" y1="{y(1)}" y2="{y(1)}" stroke="#c0392b" stroke-width="2" stroke-dasharray="6,4"/>'
                 f'<text x="{left+4}" y="{y(1)-5}" fill="#c0392b" font-weight="bold">parity 1.0x</text>')
    parts.append(f'<text x="{left}" y="{H-10}" fill="#555">Bars: category mean. Dots: individual pairs. '
                 'Net = after removing the fixed template/system-prompt tokens.</text></svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def main(out: Path = OUT) -> None:
    with (out / "results.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pairs = compare_pairs(rows)
    with (out / "comparison.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0]))
        w.writeheader()
        w.writerows({k: round(v, 4) if isinstance(v, float) else v for k, v in p.items()} for p in pairs)
    summary = summarize(rows, pairs)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    chart_svg(pairs, out / "chart_ratio_by_category.svg")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(OUT.parent / sys.argv[1] if len(sys.argv) > 1 else OUT)
