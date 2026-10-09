# WorkPilot V2 持久化说明

## 设计目标

V2 第一阶段把任务业务事实从进程内存迁移到关系数据库，同时保留 `InMemoryTaskRepository` 作为快速单元测试实现。运行时只依赖 `TaskRepository` Protocol，因此后续 Temporal Worker 与 API 可以共享相同持久层语义。

持久化覆盖：

- Task 与计划快照；
- Step 运行状态与结果；
- Approval 参数哈希和审批决定；
- Action Ledger 和远端对象 ID；
- Verification；
- Artifact 元数据；
- Timeline Event；
- Checkpoint；
- Transactional Outbox Event。

## 一致性边界

每次 `save` 使用任务版本号做 compare-and-swap。版本不匹配时抛出 `ConcurrentUpdateError`，避免审批、取消和执行器同时覆盖状态。

业务状态和新增 Timeline Event 在同一数据库事务写入；新增事件同时进入 `outbox_events`。发布器可以读取未发布事件并在成功发送后标记 `published_at`，从而避免“业务提交成功但实时事件丢失”。

`action_ledger.idempotency_key` 是主键。它包含 tenant、task、step、动作和规范化参数，为后续 at-least-once Activity 投递提供数据库去重基础。

## 租户隔离

Repository 的所有入口都要求 `tenant_id`。PostgreSQL 连接会在事务内设置：

```sql
SELECT set_config('app.tenant_id', :tenant_id, true);
```

初始 Alembic 迁移为所有业务表启用并强制 Row Level Security。包含 `tenant_id` 的表直接比较 session setting；Step、Verification、Timeline 和 Checkpoint 通过所属 Task 验证租户。

Docker Compose 使用三个数据库角色：

- `postgres`：只负责首次初始化；
- `workpilot_owner`：运行迁移并拥有表；
- `workpilot_app`：应用运行身份，不具备超级用户和建表权限。

不要在真实环境继续使用示例密码。

## 本地运行

只启动 PostgreSQL：

```bash
make db-up
```

宿主机运行迁移与 API：

```bash
export WORKPILOT_DATABASE_URL='postgresql+psycopg://workpilot_owner:workpilot_owner@127.0.0.1:5432/workpilot'
uv run alembic upgrade head

export WORKPILOT_DATABASE_URL='postgresql+psycopg://workpilot_app:workpilot_app@127.0.0.1:5432/workpilot'
uv run workpilot
```

也可以启动 API 与数据库：

```bash
docker compose -f deploy/docker-compose.yml up --build
```

未设置 `WORKPILOT_DATABASE_URL` 时继续使用内存仓储，方便开发和测试。SQLite 可以用于本地验证：

```bash
export WORKPILOT_DATABASE_URL='sqlite:///./workpilot.db'
uv run alembic upgrade head
uv run workpilot
```

## 恢复测试

`tests/test_persistence.py` 会执行以下场景：

1. 创建任务并执行到第一个审批点；
2. 销毁 Repository 和 Service；
3. 从同一数据库重新构造运行时；
4. 完成两次审批和剩余动作；
5. 再次重建 Repository 并核对最终任务、账本、验证和 Artifact。

该测试证明业务事实能跨进程对象生命周期恢复。Temporal 控制流恢复仍属于 V2 下一阶段，不能用本测试替代。
