---
name: bank-agent
description: Maintain, debug, evaluate or extend this repo - the Ollama tool-calling SQL agent (sql_generator, sql_executor, calculator over a read-only 3-table PostgreSQL DB, with step/token caps and an eval harness) and the English-vs-Bangla token-cost study in token_cost/. Use for any change to agent/, tools/, database/, evaluation/, token_cost/, main.py or tests/.
---

# Bank Query Agent + token-cost study

Course "Agentic Software Engineering, Part 1". Model: `qwen2.5:7b` via Ollama (`.env` `OLLAMA_MODEL`). No agent framework. Read the referenced file before editing; this skill only records what the code does not make obvious.

## Map
| Concern | File | Key symbols |
|---|---|---|
| Agent loop, caps, status, grounding | `agent/wrapper.py` | `BankQueryAgent.run`, `_loop`, `_call_tool`, `_for_model`, `ungrounded_numbers`, `extract_numbers`, `MAX_STEPS`, `TOKEN_BUDGET` |
| Ollama client | `agent/llm.py` | `chat` (/api/chat + tools), `generate` (/api/generate), `LLMResult`, `parse_tool_calls`, `BASE/SQL/CHAT_OPTIONS` |
| Prompts, tool schemas, schema | `agent/prompts.py` | `AGENT_SYSTEM_PROMPT`, `AGENT_TOOLS`, `SQL_SYSTEM_PROMPT`, `SCHEMA`, `NO_SQL` |
| Tools | `tools/sql_generator.py`, `tools/sql_executor.py`, `tools/calculator.py` | `generate_sql(question, feedback)`, `validate_sql`/`execute_query`, `calculate` |
| DB | `database/build_db.py`, `schema.sql`, `seed.sql`, `connection.py` | `build_database`, `SEED=42`, `get_db_connection(read_only=True)` |
| Eval (A1) | `evaluation/run_eval.py`, `grade.py`, `questions.json` | `compute_expected`, `grade`, `pass_at_1`, `pass_hat_k` |
| Token cost (A2) | `token_cost/counter.py`, `runner.py`, `analyze.py`, `compare_models.py`, `dataset.tsv` | `TokenCounter`, `cost_usd`, `compare_pairs`, `bootstrap_ci`, `compare_models`; 2nd model in `results_3b/` |

## Invariants (marked by the course rubric - keep)
- **The model chooses tools** (Ollama native tool calling). Don't replace the loop with fixed orchestration. `plan()` is only a guard (writes refused, greetings answered, 0 model calls).
- Loop stops with a status: `ok | step_cap | budget | ungrounded | error | invalid_input`. A step = one `chat` call. The budget counts all tokens, including the generator's own calls.
- Tool errors are returned to the model as tool messages (that is how SQL retries happen). Tools never raise, except `LLMConnectionError`.
- Grounding: numbers in the final answer must appear in the question or in a successful tool output (0.5% / 0.01 tolerance). One correction message, then status `ungrounded`.
- Executor safety: SELECT/WITH only, single statement, no comments, `FORBIDDEN` keywords, `SCHEMA` table allow-list, LIMIT 50/100, read-only PG session + 5 s timeout. Only `build_db` writes. Every new rule gets a test.
- `BASE_OPTIONS["num_ctx"]` is shared by chat and generate (and A2 uses 4096 too). A different num_ctx makes Ollama reload the model.
- Expected answers come from `questions.json` `expected_sql`, never from the agent. Use a fresh agent with `use_cache=False` per eval run.
- `agent/__init__.py`, `tools/__init__.py` stay import-free (circular import otherwise).
- Test-first, as the course requires: write the test, see it fail, then implement. Log assistant work in `AI_ASSISTANT_LOG.md`.

## Changing things
- Schema: `schema.sql` + `SCHEMA` + `SQL_SYSTEM_PROMPT` + `build_db.py` + `questions.json` expected SQL. Then rebuild: `python -m database.build_db`.
- New tool: add a class (dict result, never raises), its schema to `AGENT_TOOLS`, a branch in `_call_tool` and `_for_model`/`_log_tool`, a line in `AGENT_SYSTEM_PROMPT`, and tests with a scripted fake `chat` (see `tests/test_agent_loop.py::reply`).
- Prompt edits change the measured numbers. Re-run `python -m evaluation.run_eval --runs 3 --label <new>` and compare `*_summary.md`.

## Run / test
`docker compose up -d` · `python -m database.build_db` · `pytest -m "not integration"` (fast) · `pytest -m integration` (live model) · `python -m evaluation.run_eval --runs 1 --ids q01,q13` (quick live check, ~1 min per question) · `python -m token_cost.runner` (~100 calls).
On Windows, call Ollama from PowerShell or the venv Python; Git-Bash curl can hang.

## Triage
| Symptom | Look at |
|---|---|
| status `step_cap` | model repeating a tool. Check `steps` in `evaluation/results/*_runs.jsonl` |
| wrong number, status ok | `sql_written`. Usually a generator prompt rule (GROUP BY per year, JOIN) |
| `ungrounded` | the model did its own arithmetic. Check whether `calculator` was offered/used |
| "cannot connect to the local LLM runtime" | `ollama serve`, model pulled |
| "SQL Validation Blocked" | the model broke a rule. Fix the prompt, not the validator |
