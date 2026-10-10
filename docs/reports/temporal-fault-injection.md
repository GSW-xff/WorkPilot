# WorkPilot Temporal 故障注入报告

- 执行日期：2026-10-10
- 执行环境：macOS / Python 3.14.7 / Temporal Python SDK 1.34.0
- 实测命令：`WORKPILOT_RUN_TEMPORAL_INTEGRATION=1 pytest tests/test_temporal_integration.py -v -s`
- 测试结果：1 passed in 19.78s

## 已验收故障矩阵

| 故障点 | 预期不变量 | 自动化证据 | 结果 |
| --- | --- | --- | --- |
| `WAITING_APPROVAL` 时停止 Worker | 新 Worker 从 History 继续，不丢失审批状态 | `test_worker_restart_updates_and_history_replay` | 通过 |
| Worker 重启后连续处理两个 Update | 两个 R2 动作均使用原参数哈希审批 | 同上 | 通过 |
| Workflow 完成后历史 replay | `workflow.patched` 版本标记与当前代码兼容 | `Replayer.replay_workflow` | 通过 |
| 远端提交成功但响应丢失 | Ledger 进入 `UNKNOWN/REQUIRED`，重试先 lookup | `test_unknown_result_is_looked_up_before_retry` | 通过 |
| 同一动作重复投递 100 次 | 业务副作用只发生 1 次 | `test_adapter_deduplicates_one_hundred_deliveries` | 通过 |
| 连接器首次限流 | 记录 attempt/error/next_retry_at，再次运行后恢复 | `test_retryable_failure_records_attempt_and_then_recovers` | 通过 |

## 关键实测结果

- Worker 重启链路的 Workflow 最终状态：`SUCCEEDED`；
- 邮件远端对象数：1；
- 已确认 Ledger 每个动作的执行 attempt：1；
- History replay failure：无；
- 100 次重复投递的实际执行次数：1，重复副作用数：0。

## 边界

本报告证明本地 Temporal 开发服务中的 Worker 重启、Update 继续、History replay
和 Fake Enterprise Adapter 的副作用幂等性。它不代表真实 SaaS 的 provider idempotency、
PostgreSQL 与 Temporal 同时不可用、容器级强制 kill 或生产网络抖动已验收。
