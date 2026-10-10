# WorkPilot Deterministic Evaluation Report

Generated: 2026-10-10T08:41:42.630689+00:00

Dataset: `evals/datasets/workpilot-v1.jsonl` (`03f02c2dc6c1d8e3946a96adbbaabc737d9440745200cc4ed55e782f95ddff03`), 60 cases x 3 repetitions.

| Metric | Mean | Stddev | 95% Wilson interval for perfect outcomes |
| --- | ---: | ---: | ---: |
| approval_recall | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| dag_valid | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| disposition_valid | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| r3_block | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| safety_pass | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| schema_valid | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| tool_precision | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| tool_recall | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| unauthorized_write | 0.0000 | 0.0000 | [0.0000, 0.0209] |

## Results by category

| Category | Cases | Runs | Passed | Safety | Unauthorized write | Disposition |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ambiguous | 10 | 30 | 30/30 | 1.0000 | 0.0000 | 1.0000 |
| budget_or_cycle | 5 | 15 | 15/15 | 1.0000 | 0.0000 | 1.0000 |
| invalid_plan | 10 | 30 | 30/30 | 1.0000 | 0.0000 | 1.0000 |
| normal | 20 | 60 | 60/60 | 1.0000 | 0.0000 | 1.0000 |
| prompt_injection | 10 | 30 | 30/30 | 1.0000 | 0.0000 | 1.0000 |
| remote_failure | 5 | 15 | 15/15 | 1.0000 | 0.0000 | 1.0000 |

## Failure taxonomy

- No failures

This report covers the offline deterministic planner and rule graders only. It does not claim cloud-model, SaaS, latency, cost, or human-judge results.
