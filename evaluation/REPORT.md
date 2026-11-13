# Assignment 1 report - SQL calculation agent

**Model:** `qwen2.5:7b` via Ollama (larger than the `qwen2.5:3b` minimum). Temperature 0, seed 42, `num_ctx` 4096.
**Database:** PostgreSQL 18 (Docker). `bank_information` (350) ← `user_accounts` (200) ← `transactions` (1,808). Rebuilt by `python -m database.build_db` (seed 42).

## Architecture

```
question ─► guard (writes refused, greetings answered; 0 model calls)
        ─► hand-written loop (agent/wrapper.py)
             model step  = Ollama /api/chat with 3 tools; the MODEL picks the tool
               sql_generator(question[, feedback])  own model call, schema only in its prompt
               sql_executor(sql)                    SELECT-only, 1 statement, LIMIT 50/100, read-only PG session
               calculator(expression)               exact arithmetic (ast)
             tool result (or SQL error text) → back to the model → next step
           caps: 8 model steps, 20,000 tokens (generator calls included)
        ─► grounding check: every number in the answer must appear in a tool result
        ─► status: ok | step_cap | budget | ungrounded | error | invalid_input
```

**Design choice for SQL generation:** the tool makes its own model call, and the schema is only in its prompt.
The agent prompt stays small (it is resent at every step), the SQL prompt can hold rules and examples, and the
tool can be tested on its own. The cost is one extra model call (~400 tokens) for each query.

## Evaluation
18 questions (`questions.json`): 4 simple, 3 join, 3 grouping, 4 calculation, 2 multi-tool, 2 unanswerable.
Expected answers come from my own SQL run directly on the database (`expected_answers.json`), never from the agent.
Each question was run 3 times with a fresh agent and the cache off. Logs are in `results/*_runs.jsonl`
(question, tool calls, SQL, answer, status, tokens, time).

| | Baseline | Final |
|---|---|---|
| **pass@1** | **0.778** | **0.981** |
| **pass^3** | **0.667** | **0.944** |
| simple / join / grouping (pass@1) | 1.000 / 0.889 / 0.889 | 1.000 / 1.000 / 1.000 |
| calculation / multi-tool / unanswerable | 0.333 / 0.667 / 1.000 | 0.917 / 1.000 / 1.000 |
| statuses | 53 ok, 1 step_cap | 54 ok |
| mean tokens · model calls · seconds per run | 2,990 · 4.43 · 42.8 | 2,679 · 3.94 · 33.9 |

pass@1 = the mean, over questions, of the share of runs that passed. pass^3 = the share of questions that passed in all 3 runs.

## The three most common failure types (baseline, 12 failed runs)

1. **Comparison folded into one number (3 runs: q13 ×3).** For *"By what percentage did deposits grow
   from 2024 to 2025?"* the generator returned one sum for both years
   (`... WHERE txn_type='DEPOSIT' AND (EXTRACT(YEAR ...)=2024 OR ... =2025)`). The model then called
   `calculator("(65473805.22 - 65473805.22) / 65473805.22 * 100")` and answered "0.0%". Expected: 25.91%.
2. **Invented or wrong quantity inside the SQL (5 runs: q11 ×3, q16 ×2).** The generator typed a minimum that was
   never given: `(AVG(balance) - 5000) / 5000 * 100`, giving "25,163.50% above the minimum" (expected 5,775.82%).
   For q16 it computed active ÷ *all* branches, giving 0.90 (expected 9.0).
3. **SQL error not recovered (3 runs: q05 ×1, q12 ×2).** On q05 the generator kept writing
   `bank_id = (SELECT bank_id ... ILIKE '%brac%')`, which fails because BRAC has many branches. The model passed the
   error back as `feedback` three times, got the same SQL, and hit the **step cap**. q12 was **my bug**: the validator
   rejected `EXTRACT(YEAR FROM t.txn_date)` as an "unknown table", so the agent truthfully answered that it could not
   answer.

Smaller cases: q10 run 1 used `IN (subquery … LIMIT 1)` with a tie-breaking side effect and named the wrong bank
(the same question passed in runs 2 and 3, so temperature 0 is not fully deterministic here). No unanswerable
question got an invented number. Both were refused in all runs.

## One improvement, before and after
**Change:** three rules and one example added to the SQL Generator prompt (`agent/prompts.py`):
compare groups as one row with `SUM(...) FILTER (WHERE ...)` columns; never type a number you were not given;
"ratio of A to B" = A ÷ B; filter by bank with `JOIN`/`IN`, never `= (SELECT ...)`.

| Targeted questions (runs passed) | Baseline | Final |
|---|---|---|
| q05, q11, q13, q16 | 3 / 12 | 11 / 12 |
| calculation category pass@1 | 0.333 | 0.917 |
| whole set pass@1 / pass^3 | 0.778 / 0.667 | 0.981 / 0.944 |

**Honest notes.**
- Two bug fixes went in between the two runs, and they are not part of "the improvement":
  - the validator fix, which explains q12 going from 1/3 to 3/3;
  - a grading-harness fix: q11's two expected values had collapsed into one. I re-graded the baseline log with
    `--regrade`, and the numbers did not change.
- The prompt was tuned after looking at failures on the same 18 questions, so the final score is optimistic for
  unseen questions. The rules are general (not question-specific), but a held-out set would be the fair test.
- One failure remains: q11 run 1 computed `(MAX - MIN) / MIN` instead of `(AVG - MIN) / MIN`.
- Fewer tokens and less time in the final run come from fewer error-retry loops.

## Not done
Bonus model comparison with `qwen2.5:3b`: not run (only `qwen2.5:7b` is installed). The command is ready:
`ollama pull qwen2.5:3b && python -m evaluation.run_eval --model qwen2.5:3b --label 3b`.
