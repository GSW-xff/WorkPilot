# WorkPilot Deterministic Evaluation Report

Generated: 2026-10-10T01:45:42.603782+00:00

Dataset: `evals/datasets/workpilot-v1.jsonl` (`03f02c2dc6c1d8e3946a96adbbaabc737d9440745200cc4ed55e782f95ddff03`), 60 cases x 3 repetitions.

| Metric | Mean | Stddev | 95% Wilson interval for perfect outcomes |
| --- | ---: | ---: | ---: |
| approval_recall | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| dag_valid | 0.9167 | 0.2764 | [0.8671, 0.9489] |
| r3_block | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| safety_pass | 0.6667 | 0.4714 | [0.5950, 0.7314] |
| schema_valid | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| tool_precision | 0.8667 | 0.1886 | [0.5950, 0.7314] |
| tool_recall | 1.0000 | 0.0000 | [0.9791, 1.0000] |
| unauthorized_write | 0.3333 | 0.4714 | [0.2686, 0.4050] |

## Failure taxonomy

- `dag_valid`: 15
- `invalid_plan`: 15
- `safety_pass`: 60
- `tool_precision`: 60

This report covers the offline deterministic planner and rule graders only. It does not claim cloud-model, SaaS, latency, cost, or human-judge results.
