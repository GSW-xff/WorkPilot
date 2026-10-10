# API load baseline

Profile: in-process ASGI, memory, deterministic demo
Load: 300 operations at concurrency 20

- Throughput: **813.90 req/s**
- Error rate: **0.00%**
- Elapsed: **0.3686s**

| Operation | Count | Mean ms | P50 ms | P95 ms | P99 ms |
|---|---:|---:|---:|---:|---:|
| create_task | 100 | 31.670 | 30.878 | 51.253 | 53.819 |
| list_tasks | 200 | 15.263 | 15.028 | 25.862 | 27.812 |

> This isolates API/framework overhead. PostgreSQL pool, Temporal queue lag, worker saturation and external SaaS latency require the Compose/staging profile.
