# 能力边界策略与动作影响面

本文对应四项能力的实现位置与边界，便于面试追问时定位到代码。

## 一、动作影响面（三级）

`workpilot/models.py` 定义 `ImpactClass`，与 `RiskLevel`（R0–R3，处置强度）**正交**：

| 影响面 | 含义 | 默认对应风险 |
|---|---|---|
| `read_only` | 只读，不改远端状态 | R0 |
| `reversible_write` | 写，但产物在系统内可删可改 | R1 |
| `irreversible_write` | 写，且一旦发出不可收回（对外发送、建远端对象） | R2 / R3 |

- 能力在注册表里声明（`connectors/fake.py`、`connectors/github.py` 显式传入，未声明时按风险推导）。
- 计划里的 `PlanStep.impact` 可声明，但**只能比推导值更严**，低于推导值直接被 `dag.validate_plan` 拒绝。
- `irreversible_write` 的步骤必须 `requires_approval=True`，否则校验失败。
- `PolicyEngine.evaluate` 取「步骤声明、能力声明、风险推导」三者的最大值作为有效影响面。

## 二、能力边界可配置（`config/policy.json`）

`workpilot/policy_profile.py` 的 `PolicyProfile` 是可配置项：

| 字段 | 作用 |
|---|---|
| `risk_floor` | 逐能力抬高风险等级下限（只能抬高，传更低值会被 `max_risk` 吸收） |
| `denied_capabilities` | 直接不下发该能力，规划器看不到 |
| `require_approval_for` | 哪些影响面必须先人工确认 |
| `allowed_recipient_domains` | 允许的外部收件域名 |
| `max_steps` / `lease_seconds` | 单任务步数上限、任务租约时长 |

**加载即校验（`validate_hard_limits`）**，越界直接抛 `PolicyViolation`：

- `irreversible_write` 不能被移出审批（硬底线）；
- 域名不允许通配符 `*`，也不允许空列表；
- `max_steps ≤ 50`，租约 `3–300s`；
- 引用未注册的能力名 → 注册表构造失败。

因此"边界可配置"成立，但**配置只能收紧、不能放松**；改硬底线必须改代码，会进 code review。

通过 `WORKPILOT_POLICY_PATH` 指定文件；未指定时沿用环境变量的默认值（行为与之前一致）。

## 三、校验失败回退重规划

`StructuredPlanner.plan` 只负责"候选 + 一次格式修复"，失败时抛 `PlanRejected`（带候选计划与错误清单），不再内部兜底。`WorkPilotService._structured_plan` 分三段：

1. `plan()` 未通过六项校验 → 记 `plan.replan_requested`，调用 `StructuredPlanner.replan()`：
   带上"上一版计划 + 具体错误"，要求在保持步骤 id 稳定的前提下只修补不合格部分；
2. 重规划通过 → 记 `plan.replanned`，指标 `plan_replan_total{outcome=succeeded}`；
3. 仍不通过 → 记 `plan.replan_failed`，降级到 `DemoPlanner` 的确定性模板（`fallback_outcome`），
   仍要过同一套校验，并标记 `used_fallback=True`。

三段都留事件与指标，`PlanningMetadata.replanned` 与 `used_fallback` 分别记录"是否重规划过""是否降级"。

## 四、人工审批的两条通道

| 通道 | 方法 | 语义 | 用途 |
|---|---|---|---|
| Update | `TaskWorkflow.decide_approval` | 同步应答，校验失败当场抛错返回 | 审批界面（需要回执） |
| Signal | `TaskWorkflow.submit_approval` | 单向投递，送达即落库并唤醒 `wait_condition` | 异步入队、批量审批、外部系统回调 |

Signal 通道没有回执，因此校验失败不抛错，而是写入 `last_approval_error`，由
`TaskWorkflow.last_approval_error`（Query）读取；API 侧 `POST /v1/tasks/{id}/approve?transport=signal`
会在响应里带回该字段。

挂起仍然由 `wait_condition` 完成（审批最长 7 天，暂停无超时），两条通道只是把结果送进来的两种方式。

## 五、边界与已知限制

- 影响面是**声明 + 推导**得到的静态分类，不做运行时语义判定；模型把危险动作描述成只读也不会被识别，
  防线仍在能力注册表与固定风险表。
- 策略文件目前是进程级加载，不支持按租户差异化；多租户差异化需要把 profile 挂到租户上下文。
- 重规划的"只修补不合格部分"是提示词约束，不是强制；真正的强制在于新计划必须整体重新过校验。
- Signal 通道的失败原因只保留最近一次，没有逐条审计；需要审计时用 Update 通道。
