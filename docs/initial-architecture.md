# WorkPilot 初版架构与实现状态

## 目标

本初版优先打通一个可测试的安全纵向闭环：

```text
目标 → 确定性 Planner → DAG 校验 → 顺序 Executor
                                ↓
Fake 企业系统 ← Verifier ← Action Ledger ← 参数哈希审批
                                ↓
                         Artifact / 回放 / 检查点
```

真实连接器、模型 Planner 和持久工作流可以替换现有边界，而审批、幂等与验证语义保持不变。

## 关键不变量

1. Planner 声明的风险不能低于能力注册表的固定风险。
2. R2 动作没有与当前计划版本和参数哈希匹配的审批时不得调用 Adapter。
3. R3 动作即使带审批也不得进入执行器。
4. 每个动作的幂等键包含 tenant、task、step、动作类型和规范化参数。
5. Adapter 返回成功不等于步骤成功；Verifier 必须再次查询 Fake 远端状态。
6. 只有全部步骤验证通过，任务才能进入 `SUCCEEDED`。
7. 仓储访问始终要求 tenant ID；另一个 tenant 对相同任务 ID 得到未找到。

## 默认演示计划

| 步骤 | 能力 | 风险 | 行为 |
| --- | --- | --- | --- |
| `collect_updates` | `project.search_updates` | R0 | 读取项目进展 |
| `load_template` | `knowledge.search` | R0 | 读取租户内周报模板 |
| `compose_report` | `report.compose` | R1 | 生成内部草稿并保存来源 |
| `create_followup` | `task.create` | R2 | 参数预览、审批后创建任务 |
| `send_report` | `mail.send` | R2 | 参数预览、审批后发送邮件 |

## API 行为

`POST /v1/tasks` 生成并验证计划，任务停在 `PLAN_READY`。`POST /v1/tasks/{id}/run` 顺序运行到完成、失败或下一个审批点。审批接口只记录决策，执行仍由显式 `/run` 触发，因此审批请求本身可安全重试和审计。

所有本地请求可以通过 `X-Tenant-ID` 和 `X-User-ID` 传入上下文；开发默认值分别为 `demo` 与 `local-user`。真实部署必须由认证网关注入并移除客户端自报身份。

## 后续替换点

- `InMemoryTaskRepository` → PostgreSQL、SQLAlchemy、Alembic 与 RLS；
- `DemoPlanner` → 通过 `ModelGateway` 的结构化模型输出；
- `FakeEnterpriseAdapter` → 邮件、日历、任务/知识的 API 或 MCP Adapter；
- 同进程运行循环 → Temporal Workflow/Activity 与 Signal；
- 内存 Artifact → S3/MinIO；
- 工作台静态页 → Next.js 工作台；
- 结构化 API-only 通道 → Playwright 页面观察与 Browser Adapter。
