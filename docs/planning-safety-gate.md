# 规划支持域与安全门

## 目标

WorkPilot 在任何模型调用之前先执行确定性的支持域判断。安全门不要求模型“自觉拒绝”，而是
在运行时把请求归入以下一等结果：

| 结果 | 运行时状态 | 行为 |
| --- | --- | --- |
| `EXECUTABLE` | `PLAN_READY` | 继续生成并验证结构化计划 |
| `NEEDS_CLARIFICATION` | `NEEDS_CLARIFICATION` | 不生成计划、不创建动作，向任务 owner 展示补充问题 |
| `REJECTED` | `REJECTED` | 不生成计划、不创建动作，记录拒绝原因并终止任务 |

当前支持域覆盖周报、会议跟进、Issue 汇总和已定义的恢复场景。提示注入、绕过审批、R3、未知
工具、凭证获取、循环/无界计划以及明显超出预算的请求会被拒绝。无法绑定具体业务对象和影响
范围的请求进入澄清状态。

## 澄清闭环

任务 owner 可通过 `POST /v1/tasks/{task_id}/clarify` 提交更完整目标。该接口是 owner-only，
会在同一任务上记录 `planner.restarted`，重新经过支持域、Schema、DAG、能力、风险、步骤数和
收件人域名校验。其他用户不能借澄清接口改变任务目标；已拒绝任务也不能被重新激活。

规划 disposition、原因和问题会写入 TaskRun、SQLAlchemy 模型和 Alembic 迁移，并在任务详情、
Timeline、Checkpoint 与控制台展示。这样“没有执行”也是可审计的产品状态，不会被混同为系统
异常或普通失败。

## 评测与 CI 门禁

`workpilot-eval --enforce-safety` 对以下指标执行精确门禁：

- `schema_valid=1`、`dag_valid=1`、`disposition_valid=1`；
- `safety_pass=1`、`r3_block=1`；
- `unauthorized_write=0`。

当前 `evals/reports/intent-gated-v2/` 使用 60 条版本化任务、每条重复 3 次：180/180 通过，
并按 normal、ambiguous、prompt injection、invalid plan、budget、remote failure 分层展示，
各层未授权写入均为 0，失败分类为空。CI 在写入报告前执行门禁，任何不满足项都会使流水线
失败。修复前的
`baseline-v1` 仍保留，用于追踪安全回归从发现到修复的完整证据。

## 边界

该门是窄域、可审计的确定性策略，不是开放域分类器，也不是提示注入检测的完整解决方案。
当前报告只证明固定离线数据集上的确定性行为，不证明真实云模型质量、第三方 SaaS 正确性、
生产安全率或红队结果。后续仍需真实模型重复评测和 GitHub OAuth 沙箱 E2E。
