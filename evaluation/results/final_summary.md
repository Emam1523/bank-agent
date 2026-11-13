# Evaluation `final` - model `qwen2.5:7b`

18 questions x 3 runs = 54 runs

| Metric | Value |
|---|---|
| pass@1 | 0.981 |
| pass^3 | 0.944 |
| mean tokens / run | 2679 |
| mean model calls / run | 3.94 |
| mean time / run (s) | 33.9 |

| Category | pass@1 | pass^k |
|---|---|---|
| simple | 1.000 | 1.000 |
| join | 1.000 | 1.000 |
| grouping | 1.000 | 1.000 |
| calculation | 0.917 | 0.750 |
| multi_tool | 1.000 | 1.000 |
| unanswerable | 1.000 | 1.000 |

Per question (passes/runs): q01 3/3, q02 3/3, q03 3/3, q04 3/3, q05 3/3, q06 3/3, q07 3/3, q08 3/3, q09 3/3, q10 3/3, q11 2/3, q12 3/3, q13 3/3, q14 3/3, q15 3/3, q16 3/3, q17 3/3, q18 3/3

Statuses: {'ok': 54}
Failures: {'wrong_result': 1}
