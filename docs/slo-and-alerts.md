# SLO、误差预算与告警

本页定义可运维目标和计算口径，不把本地单次验证写成生产成绩。Prometheus 规则位于
`deploy/observability/alerts.yml`，本地 Alertmanager 只展示告警，不配置外部通知目标。

| 信号 | 目标 | 当前可计算口径 | 告警 |
| --- | --- | --- | --- |
| API 可用性 | 月度 >= 99.9% | 5 分钟 2xx/3xx 请求数 / 全部请求数 | 连续 10 分钟低于目标 |
| 非评测 API 时延 | P95 <= 300 ms | Histogram，排除 `/metrics` 与评测运行端点 | 连续 10 分钟超标 |
| 终态任务可靠性 | >= 99.5% | 成功 /（成功 + 失败/取消 + 运行异常） | 30 分钟窗口、连续 15 分钟超标 |
| Trace 完整度 | >= 99% | 有 WorkPilot 请求 Span 的 API 请求 / API 请求 | 连续 10 分钟低于目标 |
| Tool 错误率 | < 1% | 工具错误 /（成功调用 + 工具错误） | 连续 10 分钟超标 |
| 未授权成功写入 | 0 | 由 OIDC/RBAC 对抗测试和审计核验 | 不以“被拒绝请求数”冒充成功越权数 |
| 重复业务副作用 | 0 | 故障注入后核验远端对象数和 Ledger | `tool_duplicate_total` 仅是去重命中，不代表重复副作用 |
| 队列启动时延 | P95 <= 5 s | 尚缺 Temporal schedule-to-start Histogram | 尚不启用告警，避免伪精度 |

## 为什么使用 Histogram

`api_request_duration_seconds`、`task_duration_seconds` 和模型延迟使用固定桶
Histogram。P95 通过 `histogram_quantile` 聚合计算；请求标签使用 FastAPI 路由模板，
不会把 task id 放进 label 造成高基数。

## 告警分级

- `page`：API 可用性或任务终态可靠性持续燃烧误差预算；
- `ticket`：P95、Trace 完整度或工具错误率持续异常；
- `info`：策略拒绝动作，作为安全信号检查，不表示策略故障。

这些阈值需要在真实 staging 流量和外部依赖延迟下重新校准。当前仓库提供了可执行
计算和规则校验，但没有月度生产窗口，因此不能声称已经达到 99.9% SLO。
