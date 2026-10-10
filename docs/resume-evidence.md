# 简历证据索引

本页只收录仓库中可复现的结果。目标值、外部账号未完成项和人工研究不写成成果。

## 可使用的项目描述

> 设计并实现面向企业办公流程的安全执行 Agent：以结构化 DAG、R0–R3 策略、参数哈希审批、
> Action Ledger 和远端核验约束副作用；基于 Temporal 与 PostgreSQL RLS 构建可恢复多租户
> 执行链路，并用版本化评测、OpenTelemetry 和故障注入建立回归证据。

## 可量化证据

| 结果 | 可复现证据 | 简历表达边界 |
| --- | --- | --- |
| 60 条版本化 Agent 任务集，默认每条 3 次 | `evals/` 与 `workpilot-eval` | 必须同时给失败分类；不是云模型结果 |
| 20 条 Agentic 安全回归全部通过 | `evals/reports/security-v1/` | 确定性策略回归，不是渗透测试 |
| 10 条检索集三种模式均为 1.0 | `evals/reports/retrieval-v1/` | 离线 hash embedding 精确事实基线 |
| 真实 Temporal 测试 1 passed / 19.78s | `docs/reports/temporal-fault-injection.md` | 本地开发服务，不代表生产集群 |
| 同动作 100 次投递、远端对象 1、重复副作用 0 | 故障注入测试与复盘 | Fake Enterprise Adapter 失败模型 |
| PostgreSQL RLS 对抗测试 3 passed | `docs/reports/postgres-rls.md` | 本地 pgvector/pg16 容器 |
| Playwright Chromium 真实浏览器测试 2 passed | `tests/test_browser_adapter.py` | 本地页面，不是第三方站点兼容矩阵 |
| 300 ops、并发 20、0% 错误、813.90 req/s | `benchmarks/reports/api-baseline-v1/` | 内存仓储/in-process ASGI，非生产容量 |
| Helm lint 与受限容器运行通过 | `docs/deployment-and-supply-chain.md` | 本地验证；远程供应链 CI 需看 GitHub 记录 |

## 尚不能写成已完成

- 真实云模型质量/成本、GitHub OAuth 沙箱端到端；
- 月度 99.9% SLO、生产告警通知和多区域恢复；
- 5 人可用性研究、SUS 分数和 Demo 视频；
- 多 Agent 优于单 Agent（参见 ADR-003）。
