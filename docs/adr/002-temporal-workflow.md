# ADR-002：使用 Temporal 管理长任务控制流

- 状态：已接受，基础实现完成
- 日期：2026-10-10

## 背景

WorkPilot 的任务会等待人工审批、调用不稳定的外部系统，并可能运行数分钟或更久。V2 第一阶段已经把业务事实保存到 PostgreSQL，但 API 进程仍直接运行整个执行循环；进程退出后，系统知道任务停在哪里，却不会自动恢复控制流。

## 决策

使用 Temporal Workflow 管理任务推进：

- `TaskWorkflow` 只保存确定性控制状态；
- 数据库、连接器和策略访问全部放在 Activity；
- 审批使用同步且可返回错误的 Workflow Update；
- Pause、Resume、Cancel 使用 Signal；
- 状态通过 Query 暴露；
- Activity 使用有限指数退避；
- 每个租户内的任务使用稳定 Workflow ID，重复启动不会创建第二条控制流，跨租户任务不会共享句柄；
- API 未配置 Temporal 时保留本地直连模式，方便单元测试和轻量开发。

## 可靠副作用

Temporal Activity 是 at-least-once 语义。仅依赖 Activity 重试会在“远端已提交、响应丢失”时产生重复写入。因此执行器在调用工具前先持久化 `RESERVED` Ledger：

```text
RESERVED → DISPATCHED → CONFIRMED
     └────────→ UNKNOWN → lookup → CONFIRMED / retry with same key
```

若调用抛出异常，动作进入 `UNKNOWN`。下一次执行先调用 Adapter `lookup`；只有远端确认未执行时才使用相同幂等键重试。步骤成功与 `CONFIRMED` Ledger、Verification 和 Checkpoint 一起保存。

## 取舍

优点：

- Worker 崩溃后 Workflow History 可以重放；
- 审批等待不占用 API 进程；
- 重试、超时、Signal 和 Update 语义明确；
- Temporal UI 可用于观察控制流。

代价：

- 本地开发多一个服务；
- Workflow 代码必须保持确定性；
- 部署升级需要兼容历史 Workflow；
- Temporal 不能替代业务数据库、Action Ledger 或远端验证。

## 当前验证范围

自动化测试已经覆盖 Activity 推进、审批 Update 客户端、控制 Signal，以及远端提交后超时再 lookup 的不重复副作用行为。Docker Compose 已加入 Temporal Server 和独立 Worker。

尚未完成真实 Worker kill/restart 的容器级集成测试，因此不能宣称已经通过最终恢复验收。下一步应增加 Temporal 测试环境或 Docker E2E：在 `WAITING_APPROVAL` 和 Activity 执行期间分别终止 Worker，重启后核对 Workflow、Ledger 和远端对象。
