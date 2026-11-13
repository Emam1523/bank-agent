"""Send all 50 English and 50 Bangla prompts with identical settings; record every call.

    python -m token_cost.runner                 # qwen2.5:7b (or OLLAMA_MODEL)
    python -m token_cost.runner --model qwen2.5:3b --out results_3b

Same model, system prompt, temperature, seed and max tokens for both languages.
The system prompt does NOT ask the model to answer in the question's language.
"""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from token_cost.analyze import main as analyze_main
from token_cost.counter import PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M, OllamaBackend, TokenCounter, record_dict

HERE = Path(__file__).resolve().parent
SYSTEM_PROMPT = "You are a helpful assistant. Answer briefly."
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 200, "num_ctx": 4096, "top_p": 0.9, "top_k": 20}
FIELDS = ["id", "category", "language", "prompt", "output", "input_tokens", "output_tokens",
          "net_input_tokens", "cost_usd", "latency_s", "truncated"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=None)
    p.add_argument("--out", default="results", help="output folder inside token_cost/")
    a = p.parse_args()

    backend = OllamaBackend(model=a.model)
    counter = TokenCounter(backend, SYSTEM_PROMPT, OPTIONS)
    with (HERE / "dataset.tsv").open(encoding="utf-8") as f:
        pairs = list(csv.DictReader(f, delimiter="\t"))

    counter.count("Hello")                       # warm-up: load the model (not recorded)
    overhead = counter.measure_overhead()        # template + system prompt tokens
    cache_checks = [counter.check_cache(pairs[0]["english"]), counter.check_cache(pairs[0]["bangla"])]
    print(f"overhead={overhead} tokens; cache checks={cache_checks}", flush=True)

    out = HERE / a.out
    out.mkdir(exist_ok=True)
    start = time.perf_counter()
    with (out / "results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for pair in pairs:  # interleave EN and BN so both languages see the same conditions
            for lang, col in (("en", "english"), ("bn", "bangla")):
                rec = counter.count(pair[col])
                w.writerow({"id": pair["id"], "category": pair["category"], "language": lang,
                            **record_dict(rec)})
                f.flush()
                print(f"{pair['id']:>2} {lang} in={rec.input_tokens:>4} out={rec.output_tokens:>4} "
                      f"{rec.latency_s:>6.2f}s{' TRUNCATED' if rec.truncated else ''}", flush=True)

    meta = {"model": backend.model, "system_prompt": SYSTEM_PROMPT, "options": OPTIONS,
            "template_overhead_tokens": overhead, "cache_checks": cache_checks,
            "prices_usd_per_million": {"input": PRICE_INPUT_PER_M, "output": PRICE_OUTPUT_PER_M},
            "run_seconds": round(time.perf_counter() - start, 1),
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    analyze_main(out)


if __name__ == "__main__":
    main()
