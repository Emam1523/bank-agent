# AI-assistant use log

A coding assistant (Claude Code, model Claude Opus) was used. As the course rules require, every
item below lists **what it wrote**, **the test that proves it**, and **what I reviewed**.
Test-first was followed: each test file was written and run red (ImportError / failing
assertion) before the code it tests was written.

> Student: please fill in every "Reviewed" line yourself after checking the item.

| # | What it wrote | Test that proves it | What I reviewed |
|---|---|---|---|
| 1 | Model-driven agent loop with step cap, token budget, final status, grounding check (`agent/wrapper.py`) | `tests/test_agent_loop.py` (16 tests, red first: `ImportError: LLMResult`) | Reviewed: ____ |
| 2 | Ollama client with `chat` (tool calling) and `generate`, token counts per call (`agent/llm.py`) | `tests/test_agent_loop.py`, `tests/test_sql_generator.py` | Reviewed: ____ |
| 3 | SQL Generator tool with its own model call and output parser (`tools/sql_generator.py`) | `tests/test_sql_generator.py` | Reviewed: ____ |
| 4 | Read-only SQL Executor: SELECT-only validation, row limit, read-only DB session (`tools/sql_executor.py`, `database/connection.py`) | `tests/test_sql_executor.py`, `tests/test_database.py::test_agent_connection_is_read_only_at_database_level` | Reviewed: ____ |
| 5 | Calculator tool using `ast`, no `eval` (`tools/calculator.py`) | `tests/test_calculator.py` (red first: `ModuleNotFoundError`) | Reviewed: ____ |
| 6 | Database builder with fixed seed 42 and the `transactions` table (`database/build_db.py`, `schema.sql`) | `tests/test_build_db.py` (red first) | Reviewed: ____ |
| 7 | Question set, expected answers from my own SQL, grader, pass@1 / pass^3 (`evaluation/`) | `tests/test_evaluation.py` (red first; the "fixed deposit" spelling case was added red before the fix) | Reviewed: ____ |
| 8 | Assignment 2 token counter, cost, runner, analysis, chart (`token_cost/`) | `tests/test_token_cost.py` (fake backend; red first: `ModuleNotFoundError`) | Reviewed: ____ |
| 9 | Bangla translations of the 50 prompts (`token_cost/dataset.tsv`) | `tests/test_token_cost.py::test_dataset_has_50_aligned_pairs_with_varied_categories` checks structure only | Reviewed: every pair read and checked for same meaning: ____ |
| 10 | Fix found by the baseline run: validator wrongly blocked `EXTRACT(YEAR FROM t.txn_date)` (qualified column) | `tests/test_sql_executor.py::test_legitimate_queries_allowed[...t.txn_date...]` (red first) | Reviewed: ____ |
| 11 | Fix found by the baseline run: expected answers lost one of two same-named columns (q11); `--regrade` option | `tests/test_evaluation.py::test_expected_answers_keep_columns_with_duplicate_names` (red first) | Reviewed: ____ |
| 12 | The improvement: 3 rules + 1 example in `SQL_SYSTEM_PROMPT` (compare with FILTER, never type numbers, ratio = A/B, no `= (SELECT)`) | before/after: `evaluation/results/baseline_summary.md` vs `final_summary.md` | Reviewed: ____ |
| 13 | Bonus: two-model comparison (`token_cost/compare_models.py`) and the qwen2.5:3b run | `tests/test_token_cost.py::test_compare_models_reports_same_tokenizer_and_differences` (red first) | Reviewed: ____ |
| 14 | Reports (`evaluation/REPORT.md`, `token_cost/REPORT.md`), including the 10-pair quality check | numbers come from `*_summary.json` / `summary.json` produced by the scripts | Reviewed: ____ |
