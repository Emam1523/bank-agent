# Evaluation `baseline` - model `qwen2.5:7b`

18 questions x 3 runs = 54 runs

| Metric | Value |
|---|---|
| pass@1 | 0.778 |
| pass^3 | 0.667 |
| mean tokens / run | 2990 |
| mean model calls / run | 4.43 |
| mean time / run (s) | 42.8 |

| Category | pass@1 | pass^k |
|---|---|---|
| simple | 1.000 | 1.000 |
| join | 0.889 | 0.667 |
| grouping | 0.889 | 0.667 |
| calculation | 0.333 | 0.250 |
| multi_tool | 0.667 | 0.500 |
| unanswerable | 1.000 | 1.000 |

Per question (passes/runs): q01 3/3, q02 3/3, q03 3/3, q04 3/3, q05 2/3, q06 3/3, q07 3/3, q08 3/3, q09 3/3, q10 2/3, q11 0/3, q12 1/3, q13 0/3, q14 3/3, q15 3/3, q16 1/3, q17 3/3, q18 3/3

Statuses: {'ok': 53, 'step_cap': 1}
Failures: {'step_cap': 1, 'wrong_result': 9, 'sql_error_not_recovered': 2}
