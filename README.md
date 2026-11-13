# Agentic Software Engineering - Part 1 assignments

Both assignments use one local model through Ollama: **`qwen2.5:7b`** (Qwen 2.5, 7.6B, Q4_K_M).
This is larger than the required minimum `qwen2.5:3b`, which the assignment allows. No hosted APIs are used.

| Assignment | Folder | Report |
|---|---|---|
| 1. SQL calculation agent | `agent/`, `tools/`, `database/`, `evaluation/`, `main.py` | [evaluation/REPORT.md](evaluation/REPORT.md) |
| 2. English vs Bangla token cost | `token_cost/` | [token_cost/REPORT.md](token_cost/REPORT.md) |

AI-assistant use is logged in [AI_ASSISTANT_LOG.md](AI_ASSISTANT_LOG.md).

## Prerequisites
Python 3.11+, Docker, Ollama. Create `.env` with `POSTGRES_DB/USER/PASSWORD`, `DB_HOST=localhost`,
`DB_PORT=5434`, `DB_NAME/USER/PASSWORD`, `OLLAMA_BASE_URL=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5:7b`.

## Run everything (4 commands)

```bash
docker compose up -d && pip install -r requirements.txt && ollama pull qwen2.5:7b
python -m database.build_db              # rebuild the same data every time (seed 42)
python -m evaluation.run_eval --runs 3   # Assignment 1: 18 questions x 3 runs -> evaluation/results/
python -m token_cost.runner              # Assignment 2: 100 calls -> token_cost/results/
```

Tests (one command): `pytest`. Use `pytest -m "not integration"` to skip the tests that call the live model.

Interactive agent: `python main.py` (commands: `help`, `stats`, `db status`, `db init`, `cache clear`, `exit`).

## Assignment 1 - SQL calculation agent

```
question ─► guard (refuse writes, answer greetings; 0 model calls)
        ─► agent loop (agent/wrapper.py, hand-written)
             model step: Ollama /api/chat with 3 tools ─► the MODEL chooses:
               sql_generator(question[, feedback])  own model call, schema in its prompt  -> SQL
               sql_executor(sql)                    validate SELECT-only, LIMIT, read-only session -> rows | error
               calculator(expression)               exact arithmetic (ast, no eval)       -> number
             tool results go back to the model; SQL errors are returned so it can retry
           stop: answer | step cap (8) | token budget (20,000) | error
        ─► grounding check: every number in the answer must appear in a tool result
        ─► status: ok | step_cap | budget | ungrounded | error | invalid_input
```

- **Database** (PostgreSQL 18 in Docker, port 5434): `bank_information` (350) ← `user_accounts` (200) ← `transactions` (1,808).
  `database/build_db.py` loads `schema.sql` and `seed.sql`, then generates the transactions and account
  opening dates with `random.Random(42)`.
- **Safety**: only `SELECT`/`WITH`; one statement; no comments, write/admin keywords, system catalogs or unknown tables;
  `LIMIT` added (50) or capped (100). The connection itself is read-only: `default_transaction_read_only=on`
  and `statement_timeout=5000`.
- **Evaluation**: `evaluation/questions.json` (18 questions, each with my own `expected_sql`),
  `evaluation/expected_answers.json`, run logs `evaluation/results/*_runs.jsonl`, summaries `*_summary.md`.

## Assignment 2 - English vs Bangla token cost
- `token_cost/dataset.tsv`: 50 aligned pairs (`id, category, english, bangla`) in 6 categories.
- `token_cost/counter.py`: token counter that uses Ollama's `prompt_eval_count` / `eval_count`. It
  measures the template overhead once, checks the prompt cache, and computes notional cost ($0.15 / $0.60 per million tokens).
- `token_cost/runner.py`: same settings for both languages (temperature 0, seed 42, max 200 tokens, one system prompt).
- Outputs in `token_cost/results/`: `results.csv`, `comparison.csv`, `summary.json`, `run_meta.json`, `chart_ratio_by_category.svg`.
- Bonus (second model): `python -m token_cost.runner --model qwen2.5:3b --out results_3b`, then
  `python -m token_cost.compare_models results results_3b`. Outputs go to `token_cost/results_3b/` and `token_cost/model_comparison.json`.

**Bonus summary:** Assignment 1 adds an extra `calculator` tool. Assignment 2 repeats the experiment on `qwen2.5:3b`
and compares the tokenizers.
