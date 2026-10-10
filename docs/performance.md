# Performance and capacity baseline

Run `workpilot-benchmark` to reproduce `benchmarks/reports/api-baseline-v1`. The default
profile executes 300 task-create/list requests at concurrency 20 against the in-process ASGI
application with the deterministic planner and no paid model calls. It reports throughput,
error rate and per-operation mean/P50/P95/P99 latency.

This baseline isolates framework and application overhead. It does **not** make claims about
PostgreSQL connection-pool saturation, Temporal queue lag, workers, network ingress or SaaS
latency. The Helm autoscaler therefore uses a queue-lag metric, while a future staging run
must add PostgreSQL/Temporal and configurable connector latency before setting an SLO or a
production capacity number.
