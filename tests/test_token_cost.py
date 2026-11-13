"""Assignment 2 tests: token counting, cost and comparison maths with a fake backend.

Written before token_cost/ was implemented (test-first).
"""

import csv
from pathlib import Path

import pytest

from token_cost.analyze import bootstrap_ci, compare_pairs, describe
from token_cost.counter import TokenCounter, cost_usd

DATASET = Path(__file__).resolve().parent.parent / "token_cost" / "dataset.tsv"


class FakeBackend:
    """Mimics Ollama /api/generate: 10 template tokens + 1 token per character of the prompt."""

    def __init__(self, cached_second_time=False):
        self.calls = []
        self.cached_second_time = cached_second_time

    def generate(self, system, prompt, options):
        self.calls.append((system, prompt, options))
        n = 10 + len(prompt)
        if self.cached_second_time and sum(p == prompt for _, p, _ in self.calls) > 1:
            n = 3  # prompt reused from the KV cache
        return {"response": "ok " * 4, "prompt_eval_count": n, "eval_count": 5,
                "done_reason": "length" if "long" in prompt else "stop"}


def test_cost_uses_the_course_prices():
    assert cost_usd(1_000_000, 0) == pytest.approx(0.15)
    assert cost_usd(0, 1_000_000) == pytest.approx(0.60)
    assert cost_usd(200, 100) == pytest.approx(200 * 0.15e-6 + 100 * 0.60e-6)


def test_counter_reads_ollama_counts_and_settings():
    backend = FakeBackend()
    counter = TokenCounter(backend, system="SYS", options={"temperature": 0, "seed": 42, "num_predict": 64})
    rec = counter.count("hello")
    assert (rec.input_tokens, rec.output_tokens) == (15, 5)
    assert rec.cost_usd == pytest.approx(cost_usd(15, 5))
    assert rec.latency_s >= 0 and rec.truncated is False
    assert backend.calls[0] == ("SYS", "hello", {"temperature": 0, "seed": 42, "num_predict": 64})


def test_truncation_is_flagged():
    rec = TokenCounter(FakeBackend(), system="S", options={}).count("a long prompt")
    assert rec.truncated is True


def test_template_overhead_is_measured_with_a_one_token_prompt():
    counter = TokenCounter(FakeBackend(), system="S", options={})
    assert counter.measure_overhead() == 10          # (10 + 1) - 1
    rec = counter.count("hello")
    assert rec.net_input_tokens == 5                  # 15 - 10


def test_cache_check_detects_reused_prompts():
    assert TokenCounter(FakeBackend(), "S", {}).check_cache("same prompt")["cached"] is False
    res = TokenCounter(FakeBackend(cached_second_time=True), "S", {}).check_cache("same prompt")
    assert res["cached"] is True and res["first"] > res["second"]


def test_compare_pairs_ratios():
    rows = [
        {"id": "1", "category": "q", "language": "en", "input_tokens": 20, "output_tokens": 10, "net_input_tokens": 10, "cost_usd": cost_usd(20, 10), "latency_s": 1.0},
        {"id": "1", "category": "q", "language": "bn", "input_tokens": 40, "output_tokens": 30, "net_input_tokens": 30, "cost_usd": cost_usd(40, 30), "latency_s": 2.0},
    ]
    (pair,) = compare_pairs(rows)
    assert pair["input_ratio"] == pytest.approx(2.0)
    assert pair["net_input_ratio"] == pytest.approx(3.0)
    assert pair["output_ratio"] == pytest.approx(3.0)
    assert pair["total_cost_ratio"] == pytest.approx(cost_usd(40, 30) / cost_usd(20, 10))


def test_describe_and_bootstrap():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    d = describe(values)
    assert (d["mean"], d["median"], d["min"], d["max"]) == (3.0, 3.0, 1.0, 5.0)
    lo, hi = bootstrap_ci(values, n=2000, seed=0)
    assert 1.0 <= lo < 3.0 < hi <= 5.0
    assert bootstrap_ci(values, n=2000, seed=0) == (lo, hi)  # reproducible


def test_dataset_has_50_aligned_pairs_with_varied_categories():
    with DATASET.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert len(rows) == 50
    assert list(rows[0]) == ["id", "category", "english", "bangla"]
    assert [r["id"] for r in rows] == [str(i) for i in range(1, 51)]
    assert all(r["english"].strip() and r["bangla"].strip() for r in rows)
    assert all(any("ঀ" <= ch <= "৿" for ch in r["bangla"]) for r in rows)  # Bengali script
    assert len({r["category"] for r in rows}) >= 6
    lengths = sorted(len(r["english"].split()) for r in rows)
    assert lengths[0] <= 6 and lengths[-1] >= 40  # short and long prompts


def _row(pid, lang, n_in, n_out, lat=1.0):
    return {"id": pid, "category": "q", "language": lang, "input_tokens": n_in, "output_tokens": n_out,
            "net_input_tokens": n_in - 10, "cost_usd": cost_usd(n_in, n_out), "latency_s": lat, "truncated": "False"}


def test_compare_models_reports_same_tokenizer_and_differences():
    from token_cost.compare_models import compare_models
    a = [_row("1", "en", 20, 10, 1.0), _row("1", "bn", 40, 30, 2.0)]
    b = [_row("1", "en", 20, 5, 0.5), _row("1", "bn", 40, 60, 1.0)]
    res = compare_models(a, b)
    assert res["identical_input_counts"] == 1.0          # same tokenizer -> same prompt counts
    assert res["by_language"]["bn"]["output_tokens"] == {"a": 30, "b": 60}
    assert res["by_language"]["en"]["latency_mean"] == {"a": 1.0, "b": 0.5}
    assert res["bn_en_input_ratio"] == {"a": 2.0, "b": 2.0}
    assert res["bn_en_total_cost_ratio"]["b"] == pytest.approx(cost_usd(40, 60) / cost_usd(20, 5))
