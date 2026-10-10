# WorkPilot

WorkPilot 是一个面向企业跨系统办公流程的安全执行 Agent。它把自然语言目标转换为结构化任务 DAG，在确定性策略、人工审批、幂等账本和远端验证的约束下执行。当前已有可替换的 ModelGateway、结构化 Planner、上下文信任标签与预算、PostgreSQL 持久化和 Temporal 长任务控制流。

详细产品与技术方案见 [MVP 完整实现方案](docs/mvp-implementation-plan.md)，本次实现边界见 [初版架构与状态](docs/initial-architecture.md)，持久化与可靠执行路线见 [V2 修改设计方案](docs/v2-design-plan.md)，面向 Agent 岗位的能力盘点、证据标准和后续实施顺序见 [V3 面试竞争力与产品完整性方案](docs/v3-interview-advantage-plan.md)。

## 已实现

- FastAPI 任务、审批、暂停、恢复、取消、Artifact 与回放接口；
- 确定性周报 Demo Planner，以及 DAG 无环、能力、步骤数和风险校验；
- ModelGateway Protocol、OpenAI-compatible 云模型 Provider 和可重现 Fake Provider；
- 结构化 Planner：JSON Schema 输出、一次修复、确定性校验与 DemoPlanner 安全回退；
- ContextBuilder：分层来源、trust label、Prompt Injection 标记、Tool Search 和 Token 预算裁剪；
- 模型请求记录 provider/model/request id、Prompt/Schema 版本、Token、延迟、重试、成本和 trace id，默认不持久化 Prompt 正文；
- 重规划 Plan Diff，并禁止删除或篡改已成功步骤；
- GitHub Issues OAuth/HTTP Adapter：Secret 引用隔离、限流/熔断/超时、远端幂等查询、Webhook 签名与防重放；
- OpenTelemetry/OTLP Trace、Prometheus 指标、Tempo 与 Grafana 本地观测栈；
- API Idempotency-Key、RFC Problem Details、任务分页/过滤和 SSE Last-Event-ID 断线续传；
- Outbox Relay、失败计数/死信与消费端按 event id 去重；
- MCP Server/Client 的只读工具闭环、server identity 和 Schema 指纹防投毒；
- R0–R3 策略、R2 参数预览/哈希绑定、R3 拒绝；
- 邮件、知识、项目更新、报告和任务的 Fake Adapter；
- tenant 范围内的任务与知识数据访问；
- SQLAlchemy 2 持久仓储、Alembic 初始迁移、乐观锁和 PostgreSQL RLS；
- 与业务事务一起写入的事件 Outbox；
- Temporal Workflow/Activity、审批 Update、控制 Signal 和独立 Worker；
- 动作预占、UNKNOWN 状态与远端 lookup-before-retry；
- Action Ledger、稳定幂等键、独立远端状态验证；
- 每个安全边界和副作用后的检查点、完整时间线及 SSE 事件；
- 无构建步骤的三栏任务工作台；
- DAG、状态机、策略、审批、幂等、租户隔离和 API 自动化测试。
- Ruff、mypy、pytest/coverage 和 GitHub Actions 工程门禁。

## 本地启动

需要 Python 3.12 或更高版本以及 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra dev
uv run workpilot
```

打开 <http://127.0.0.1:8000> 使用工作台，接口文档位于 <http://127.0.0.1:8000/docs>。

默认使用确定性 Demo Planner。离线验证结构化链路可设置
`WORKPILOT_PLANNER_MODE=fake`；调用 OpenAI-compatible 云模型时设置
`WORKPILOT_PLANNER_MODE=openai`、`WORKPILOT_MODEL_API_KEY`、`WORKPILOT_MODEL_BASE_URL`
和 `WORKPILOT_MODEL_NAME`。可同时设置 Token/成本硬上限，密钥只在 Provider 边界使用。

GitHub OAuth App 配置、Scope、Secret 边界和契约测试说明见
[GitHub Issues 连接器](docs/github-connector.md)。
本地 Trace/Metrics 启动方式、敏感字段边界和故障 Runbook 见
[可观测性与 Runbook](docs/observability.md)。
MCP 只读授权、Schema 固定与写操作边界见 [MCP 安全边界](docs/mcp.md)。

未配置数据库时使用内存仓储。需要跨重启保存任务时，可以先使用 SQLite：

```bash
export WORKPILOT_DATABASE_URL='sqlite:///./workpilot.db'
uv run alembic upgrade head
uv run workpilot
```

PostgreSQL、独立迁移角色和 RLS 的启动方式见 [V2 持久化说明](docs/persistence.md)，也可以使用：

```bash
docker compose -f deploy/docker-compose.yml up --build
```

该 Compose 会同时启动 PostgreSQL、Temporal、API 和独立 Worker。Temporal 的设计取舍与当前验证边界见 [ADR-002](docs/adr/002-temporal-workflow.md)。
真实 Temporal 测试服务的 Worker 重启、Update 继续、幂等投递与 History replay
证据见 [故障注入报告](docs/reports/temporal-fault-injection.md)。

运行测试：

```bash
uv run pytest
```

执行需要本地 Temporal 开发服务二进制的真实 Workflow/Worker 集成测试：

```bash
make test-temporal
```

运行 60 条版本化任务集的离线确定性评测（默认每条重复 3 次）：

```bash
uv run workpilot-eval --output evals/reports/local
```

评测会生成机器可读 `eval-report.json`、人可读 `eval-report.md` 和
`baseline-comparison.md`。仓库内的 `evals/reports/baseline-v1/` 保留了 DemoPlanner
基线的完整失败分类；该报告不代表真实模型或 SaaS 实测结果。

## API 演示

创建任务并执行到第一个审批点：

```bash
curl -s http://127.0.0.1:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -H 'X-User-ID: local-user' \
  -d '{"goal":"收集项目进展，生成并发送周报","recipient":"team@example.com"}'

curl -s -X POST http://127.0.0.1:8000/v1/tasks/<task-id>/run \
  -H 'X-Tenant-ID: demo'
```

从任务响应的 `approvals` 中取得 `step_id` 和 `parameter_hash` 后审批：

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/<task-id>/approve \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -H 'X-User-ID: approver' \
  -d '{"step_id":"create_followup","parameter_hash":"<hash>"}'
```

未配置 Temporal 的直连模式需要在审批后再次调用 `/run`；配置 Temporal 后，Workflow 会自动从审批点继续，客户端只需轮询任务查询接口（内置工作台已自动刷新）。

## 项目结构

```text
apps/api/                 FastAPI 入口
apps/web/                 本地任务工作台
workpilot/api.py          HTTP/SSE API
workpilot/runtime.py      Planner–Executor–Verifier 主循环
workpilot/dag.py          DAG 与计划确定性校验
workpilot/policy.py       风险和审批策略
workpilot/connectors/     统一接口、能力注册与 Fake Adapter
workpilot/repository.py   tenant-aware 乐观锁仓储
workpilot/db/             SQLAlchemy 数据模型和持久 Repository
workpilot/workflows/      Temporal Workflow、Activity 与客户端
workpilot/outbox.py       At-least-once Outbox Relay 与消费去重
workpilot/knowledge.py    文件解析、ACL、混合检索与可核验引用
alembic/                  数据库迁移与 PostgreSQL RLS
deploy/                   PostgreSQL、Temporal、API 与 Worker 本地部署
tests/                    单元、运行时、安全与 API 测试
evals/                    60 条版本化数据集与可重复基准报告
```

## 当前边界

当前已完成 V3 阶段 A 的模型/上下文核心链路、60 条固定任务集和确定性基准报告，并完成 GitHub OAuth/Adapter 契约、真实 Temporal 本地服务恢复测试、真实 PostgreSQL RLS 对抗测试、本地可观测栈、MCP 只读安全闭环、OIDC/RBAC 鉴权、带 ACL 和引用的文件检索管线，以及任务/审批/恢复/评测产品控制台，但不宣称真实模型、GitHub 沙箱 E2E、生产 SLO、5 人可用性研究或 V3 最终验收已完成。真实云模型、GitHub OAuth 沙箱和用户研究需要外部账号或真实参与者。认证部署说明见 [docs/authentication.md](docs/authentication.md)，文件管线说明见 [docs/knowledge-pipeline.md](docs/knowledge-pipeline.md)，控制台说明见 [docs/product-console.md](docs/product-console.md)，数据库实测证据见 [docs/reports/postgres-rls.md](docs/reports/postgres-rls.md)。
