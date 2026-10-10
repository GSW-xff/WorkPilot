# WorkPilot

WorkPilot 是一个面向企业跨系统办公流程的任务执行 Agent。当前仓库提供一套可直接运行的纵向 MVP，并已完成 V2 的持久化与 Temporal 基础控制流：它把自然语言目标转换为任务 DAG，在 Fake 企业系统中执行，遇到外部写入时展示真实参数并等待审批，最后通过远端状态查询验证结果并生成审计回放。任务、审批、账本、验证、Artifact、事件与检查点可以保存到 PostgreSQL，并由独立 Worker 推进。

详细产品与技术方案见 [MVP 完整实现方案](docs/mvp-implementation-plan.md)，本次实现边界见 [初版架构与状态](docs/initial-architecture.md)，从当前版本走向可持久运行与面试级工程项目的路线见 [V2 修改设计方案](docs/v2-design-plan.md)。

## 已实现

- FastAPI 任务、审批、暂停、恢复、取消、Artifact 与回放接口；
- 确定性周报 Demo Planner，以及 DAG 无环、能力、步骤数和风险校验；
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

运行测试：

```bash
uv run pytest
```

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
alembic/                  数据库迁移与 PostgreSQL RLS
deploy/                   PostgreSQL、Temporal、API 与 Worker 本地部署
tests/                    单元、运行时、安全与 API 测试
```

## 当前边界

当前版本用于验证安全执行闭环，不宣称已经达到 V2 最终验收目标。PostgreSQL/Alembic 持久层和 Temporal 基础控制流已经实现；未设置 `WORKPILOT_DATABASE_URL` 与 `WORKPILOT_TEMPORAL_TARGET` 时仍使用进程内直连模式。真实 SaaS/MCP、Playwright 多模态观察、PDF/DOCX/XLSX 解析、对象存储、OpenTelemetry 后端、固定评测集和 Next.js 前端仍属于后续迭代。
