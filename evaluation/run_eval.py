"""Run the question set N times through the agent and report pass@1 and pass^k.

Expected answers are computed by our own SQL (evaluation/questions.json),
directly against the database - never by the agent.

    python -m evaluation.run_eval --runs 3 --label final
    python -m evaluation.run_eval --runs 1 --ids q01,q13          # quick check
    python -m evaluation.run_eval --model qwen2.5:3b --label 3b   # another model

Writes evaluation/results/<label>_runs.jsonl (one record per run) and
<label>_summary.md / .json.
"""

import argparse
import json
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

from agent.llm import OllamaClient
from agent.wrapper import BankQueryAgent
from database.connection import get_db_connection
from evaluation.grade import grade, pass_at_1, pass_hat_k

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load_questions() -> List[Dict[str, Any]]:
    return json.loads((HERE / "questions.json").read_text(encoding="utf-8"))


def _alternatives(text: str) -> str:
    """'FIXED_DEPOSIT' also matches 'fixed deposit'; 'Eastern Bank PLC' also 'Eastern Bank'."""
    alts = {text, text.replace("_", " "), text.removesuffix(" PLC")}
    return "|".join(sorted(alts))


def compute_expected(questions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Run each question's expected_sql (read-only) and turn the first row into a grading spec.

    Tuple rows on purpose: dict rows would merge columns that share a name (e.g. two ROUND(...)).
    """
    expected = {}
    conn = get_db_connection(read_only=True)
    try:
        with conn.cursor() as cur:
            for q in questions:
                if q["type"] == "none":
                    expected[q["id"]] = {"type": "none"}
                    continue
                cur.execute(q["expected_sql"])
                row = cur.fetchone()
                if q["type"] == "number":
                    values = [float(v) if isinstance(v, Decimal) else v for v in row]
                else:
                    values = [_alternatives(str(v)) for v in row]
                expected[q["id"]] = {"type": q["type"], "values": values}
    finally:
        conn.close()
    return expected


def save_expected(expected: Dict[str, Dict[str, Any]]) -> None:
    (HERE / "expected_answers.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")


def classify_failure(record: Dict[str, Any], expected_type: str) -> str:
    """Rough automatic failure label; the report groups and explains them by hand."""
    if record["status"] != "ok":
        return record["status"]
    if expected_type == "none":
        return "invented_answer"
    executed = [c for c in record["tool_calls"] if c["tool"] == "sql_executor"]
    if not executed:
        return "no_tool_used"
    if executed[-1]["status"] != "success":
        return "sql_error_not_recovered"
    return "wrong_result"


def run(runs: int, label: str, model: str, ids: List[str]) -> Dict[str, Any]:
    questions = [q for q in load_questions() if not ids or q["id"] in ids]
    expected = compute_expected(questions)
    save_expected(expected)
    llm = OllamaClient(model=model)
    llm.warm_up()
    RESULTS.mkdir(exist_ok=True)
    log_path = RESULTS / f"{label}_runs.jsonl"
    records: List[Dict[str, Any]] = []

    with log_path.open("w", encoding="utf-8") as log:
        for q in questions:
            for trial in range(1, runs + 1):
                agent = BankQueryAgent(llm_client=llm, use_cache=False)  # fresh agent, no cache
                res = agent.run(q["question"])
                calls = [{"tool": s["tool"], "args": s["input"], "status": s["output"].get("status"),
                          "error": s["output"].get("error")} for s in res["steps"]]
                rec = {
                    "label": label, "model": llm.model, "id": q["id"], "category": q["category"], "run": trial,
                    "question": q["question"], "tool_calls": calls,
                    "sql_written": [s["output"]["sql"] for s in res["steps"]
                                    if s["tool"] == "sql_generator" and s["output"].get("sql")],
                    "final_answer": res["response"], "status": res["status"],
                    "tokens": res["tokens"], "llm_calls": res["llm_calls"], "time_s": res["elapsed_s"],
                    "expected": expected[q["id"]],
                    "passed": res["status"] == "ok" and grade(res["response"], expected[q["id"]]),
                }
                rec["failure"] = None if rec["passed"] else classify_failure(rec, q["type"])
                records.append(rec)
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                print(f"{q['id']} run {trial}: {'PASS' if rec['passed'] else 'FAIL'} "
                      f"[{rec['status']}] {rec['time_s']}s {rec['tokens']['total']} tok - {res['response'][:90]!r}",
                      flush=True)

    return summarize(records, label, llm.model, runs)


def regrade(label: str) -> Dict[str, Any]:
    """Grade an existing run log again with the current expected answers (answers are not re-run)."""
    path = RESULTS / f"{label}_runs.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = {q["id"]: q for q in load_questions()}
    expected = compute_expected([questions[i] for i in dict.fromkeys(r["id"] for r in records)])
    for r in records:
        r["expected"] = expected[r["id"]]
        r["passed"] = r["status"] == "ok" and grade(r["final_answer"], r["expected"])
        r["failure"] = None if r["passed"] else classify_failure(r, questions[r["id"]]["type"])
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    runs = max(r["run"] for r in records)
    return summarize(records, label, records[0]["model"], runs)


def summarize(records: List[Dict[str, Any]], label: str, model: str, runs: int) -> Dict[str, Any]:
    by_q: Dict[str, List[bool]] = defaultdict(list)
    by_cat: Dict[str, Dict[str, List[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_q[r["id"]].append(r["passed"])
        by_cat[r["category"]][r["id"]].append(r["passed"])
    summary = {
        "label": label, "model": model, "runs_per_question": runs, "questions": len(by_q),
        "total_runs": len(records),
        "pass_at_1": round(pass_at_1(by_q), 3), f"pass_hat_{runs}": round(pass_hat_k(by_q), 3),
        "by_category": {c: {"pass_at_1": round(pass_at_1(v), 3), f"pass_hat_{runs}": round(pass_hat_k(v), 3)}
                        for c, v in by_cat.items()},
        "per_question": {q: f"{sum(v)}/{len(v)}" for q, v in by_q.items()},
        "status_counts": dict(Counter(r["status"] for r in records)),
        "failure_counts": dict(Counter(r["failure"] for r in records if r["failure"])),
        "tokens_mean": round(mean(r["tokens"]["total"] for r in records)),
        "tokens_median": median(r["tokens"]["total"] for r in records),
        "llm_calls_mean": round(mean(r["llm_calls"] for r in records), 2),
        "time_s_mean": round(mean(r["time_s"] for r in records), 1),
        "time_s_median": median(r["time_s"] for r in records),
    }
    (RESULTS / f"{label}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    k = f"pass_hat_{runs}"
    lines = [f"# Evaluation `{label}` - model `{model}`", "",
             f"{summary['questions']} questions x {runs} runs = {summary['total_runs']} runs", "",
             f"| Metric | Value |", "|---|---|",
             f"| pass@1 | {summary['pass_at_1']:.3f} |", f"| pass^{runs} | {summary[k]:.3f} |",
             f"| mean tokens / run | {summary['tokens_mean']} |", f"| mean model calls / run | {summary['llm_calls_mean']} |",
             f"| mean time / run (s) | {summary['time_s_mean']} |", "",
             "| Category | pass@1 | pass^k |", "|---|---|---|"]
    lines += [f"| {c} | {v['pass_at_1']:.3f} | {v[k]:.3f} |" for c, v in summary["by_category"].items()]
    lines += ["", "Per question (passes/runs): " + ", ".join(f"{q} {v}" for q, v in summary["per_question"].items()),
              "", f"Statuses: {summary['status_counts']}", f"Failures: {summary['failure_counts']}"]
    (RESULTS / f"{label}_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--label", default="final")
    p.add_argument("--model", default=None, help="Ollama model tag (default: OLLAMA_MODEL or qwen2.5:7b)")
    p.add_argument("--ids", default="", help="comma-separated question ids (default: all)")
    p.add_argument("--regrade", action="store_true", help="re-grade results/<label>_runs.jsonl, no model calls")
    a = p.parse_args()
    start = time.perf_counter()
    if a.regrade:
        regrade(a.label)
    else:
        run(a.runs, a.label, a.model, [i for i in a.ids.split(",") if i])
    print(f"\nTotal time: {time.perf_counter() - start:.0f}s")


if __name__ == "__main__":
    main()
