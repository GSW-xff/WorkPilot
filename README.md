# WorkPilot

WorkPilot 是一个面向企业跨系统办公流程的任务执行 Agent。当前仓库提供一套可直接运行的纵向 MVP：它把自然语言目标转换为任务 DAG，在 Fake 企业系统中执行，遇到外部写入时展示真实参数并等待审批，最后通过远端状态查询验证结果并生成审计回放。

详细产品与技术方案见 [MVP 完整实现方案](docs/mvp-implementation-plan.md)，本次实现边界见 [初版架构与状态](docs/initial-architecture.md)，从当前版本走向可持久运行与面试级工程项目的路线见 [V2 修改设计方案](docs/v2-design-plan.md)。

## 已实现

- FastAPI 任务、审批、暂停、恢复、取消、Artifact 与回放接口；
- 确定性周报 Demo Planner，以及 DAG 无环、能力、步骤数和风险校验；
- R0–R3 策略、R2 参数预览/哈希绑定、R3 拒绝；
- 邮件、知识、项目更新、报告和任务的 Fake Adapter；
- tenant 范围内的任务与知识数据访问；
- Action Ledger、稳定幂等键、独立远端状态验证；
- 每个安全边界和副作用后的检查点、完整时间线及 SSE 事件；
- 无构建步骤的三栏任务工作台；
- DAG、状态机、策略、审批、幂等、租户隔离和 API 自动化测试。

## 本地启动

需要 Python 3.12 或更高版本以及 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra dev
uv run workpilot
```

打开 <http://127.0.0.1:8000> 使用工作台，接口文档位于 <http://127.0.0.1:8000/docs>。

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

从第二个响应的 `approvals` 中取得 `step_id` 和 `parameter_hash` 后审批。审批不会隐式执行动作，客户端应再调用一次 `/run`：

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/<task-id>/approve \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -H 'X-User-ID: approver' \
  -d '{"step_id":"create_followup","parameter_hash":"<hash>"}'
```

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
tests/                    单元、运行时、安全与 API 测试
```

## 当前边界

当前版本用于验证安全执行闭环，不宣称已经达到方案文档中的八周最终验收目标。它使用进程内仓储和 Fake Adapter；进程重启会清空业务数据。PostgreSQL/Alembic、Temporal、真实 SaaS/MCP、Playwright 多模态观察、PDF/DOCX/XLSX 解析、对象存储、OpenTelemetry 后端、40 条固定评测集和 Next.js 前端仍属于后续迭代。
