# WorkPilot 可观测性与 Runbook

WorkPilot 使用 OpenTelemetry API/SDK 和 OTLP gRPC 串联 API、Planner、Policy、Tool 与
Verifier Span，使用内建的 Prometheus exposition 提供低基数度运行指标。

## 本地观测栈

```bash
docker compose -f deploy/docker-compose.yml up --build
```

- WorkPilot：<http://127.0.0.1:8000>
- Prometheus：<http://127.0.0.1:9090>
- Grafana：<http://127.0.0.1:3000>
- Tempo HTTP API：<http://127.0.0.1:3200>

Collector 配置位于 `deploy/observability/otel-collector.yml`，Grafana 会自动加载
Prometheus/Tempo 数据源和 `WorkPilot Reliability and Cost` Dashboard。

## Trace 层级

```text
http.request
└── task.run
    ├── model.plan
    ├── policy.evaluate
    ├── tool.lookup
    ├── tool.execute
    └── tool.verify
```

Span 只保存 ID、类型、版本、Token 计数、能力名和重试次数等安全属性。
Prompt、文档正文、连接器 Token、动作参数和收件人不进入 Trace。`traceparent`
会从 HTTP 请求中提取，`X-Request-ID` 会原样返回；未提供时由服务生成。

## 指标

- `api_request_duration_seconds`：API 时延，按 method/status 聚合；
- `task_duration_seconds`、`task_success_total`、`task_error_total`；
- `tool_call_total`、`tool_error_total`、`tool_duplicate_total`；
- `model_token_usage_total`、`model_cost_usd_total`、`model_latency_seconds`。

这些指标不使用 tenant/task/request ID 作为 label，避免 Prometheus 时序基数爆炸。

## 首版告警和 Runbook

### Tool 错误率升高

1. 在 Grafana 按 `capability` 查看 `tool_error_total`；
2. 用 Tempo 定位对应 `tool.execute` 的 `error.type` 和 retry count；
3. 区分 rate limit、deadline、provider 5xx 和不可重试契约错误；
4. `UNKNOWN` 动作进入 `/v1/recovery`，人工重试前必须先查询远端状态。

### 模型成本异常

1. 按 model/provider 比较 `model_token_usage_total` 与 `model_cost_usd_total`；
2. 检查 Context Snapshot 的 included/omitted source 和 Token 预算；
3. 降低 `WORKPILOT_MODEL_INPUT_BUDGET`/`OUTPUT_BUDGET` 或切回 `demo` Planner；
4. 不在 Trace 中寻找 Prompt 正文，受控正文应从 Artifact 保留策略查询。

### Task 失败或延迟升高

1. 先查 `task.run` 的子 Span 是模型、审批、工具还是验证阶段；
2. 对照 Timeline/Checkpoint 与 Temporal History；
3. 查看 `/v1/recovery` 是否有 `UNKNOWN/RETRYABLE`；
4. 不得直接重放写动作，必须经过 Ledger lookup-before-retry。

## 边界

Dashboard 是本地验证配置，不等同于已达成 99.9% 月可用性。当前仓库没有生产
告警通知渠道，也没有经过持续负载压测；SLO 仍是目标，不是实测成绩。
