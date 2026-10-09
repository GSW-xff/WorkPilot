# WorkPilot MVP 完整实现方案

## 1. 文档目的

本文定义 WorkPilot 初版的产品范围、系统架构、技术选型、核心数据结构、实现顺序、测试策略和验收标准。目标是让项目可以直接进入开发，而不是停留在概念描述。

本文中的百分比均为目标值，不是已经取得的实验结果。最终对外描述必须以固定任务集上的真实测量结果替换。

## 2. 产品定位

WorkPilot 是一个面向企业人员的跨系统办公任务执行 Agent。用户通过自然语言、文档、表格或页面截图描述目标，系统将目标转换为带依赖、风险和验证条件的任务计划，并通过 API/MCP 或浏览器操作执行。在执行外部写入或高风险动作之前，系统展示真实参数并请求人工审批；执行完成后，通过独立证据确认业务状态是否真正改变。

核心价值主张：

> 把需要在多个企业系统之间反复复制、查询、创建和核对的办公流程，变成可控、可追踪的一次任务委派。

MVP 需要证明四件事：

1. Agent 能把自然语言目标拆成有依赖关系的任务图。
2. Agent 能在 API/MCP 与 Computer Use 之间选择合适通道并完成跨系统操作。
3. Agent 不会绕过审批执行受控操作，也不会在失败重试时产生重复副作用。
4. 用户能够查看证据、恢复长任务并回放完整执行过程。

## 3. MVP 范围

### 3.1 目标用户

初版聚焦以下角色：

- 项目经理：收集项目进展、生成周报、创建跟进任务。
- 运营人员：从邮件和表格提取信息，在业务系统中录入和核对。
- 行政人员：安排会议、发送通知、整理文档和待办。

初版不针对财务付款、生产环境运维、管理员权限变更等高风险场景。

### 3.2 首个端到端演示任务

默认演示流程：

> 从邮件和项目系统中收集本周项目进展，读取知识库中的周报模板，生成周报；为缺失事项创建跟进任务；展示收件人、标题和正文，经用户确认后发送邮件；最后重新查询邮件和任务系统，验证结果是否真实创建。

该流程覆盖：

- 企业知识检索；
- 跨系统数据获取；
- 任务依赖规划；
- API/MCP 与网页操作；
- 参数预览与人工审批；
- 状态验证；
- 失败重规划；
- 轨迹记录与任务恢复。

### 3.3 功能优先级

#### P0：首版必须完成

- 文本、PDF、DOCX、XLSX/CSV 和图片输入；
- 文件解析、租户内知识检索和来源引用；
- Planner–Executor–Verifier 闭环；
- 带依赖、风险、预期副作用和验证规则的任务 DAG；
- API/MCP 与 Computer Use 双通道执行；
- DOM、Accessibility Tree、截图融合的页面观测；
- 外部写入参数预览和人工审批；
- 幂等执行、失败分类和局部重规划；
- 任务暂停、取消、恢复；
- OpenTelemetry 轨迹和执行时间线；
- 自建固定任务集、回归测试和指标报告。

#### P1：P0 稳定后加入

- 将已完成任务保存为可复用模板；
- 定时任务；
- 多用户协作审批；
- 更多 SaaS 连接器；
- 并行执行无依赖的 DAG 节点；
- 自然语言编辑执行计划；
- WorkArena、WorkArena++ 和 WebArena-Verified 批量评测适配器。

#### 初版明确不做

- 无限制的开放网络访问；
- 财务支付、永久删除、管理员权限修改；
- 任意插件自动安装；
- 无人工确认的外部消息发送；
- 通用多 Agent 社会化协作；
- 视频理解和实时语音交互；
- 面向所有办公平台的连接器市场；
- 任意复杂度的并行和循环工作流。

## 4. 技术选型

### 4.1 推荐技术栈

| 层级 | 工具 | 用途与选择理由 |
| --- | --- | --- |
| 前端 | Next.js + TypeScript | 实现任务工作台、计划预览、审批和轨迹回放 |
| UI | Tailwind CSS + shadcn/ui | 快速构建一致的企业后台界面 |
| API 服务 | Python 3.12 + FastAPI | Agent 和文档生态成熟，适合异步接口和结构化 Schema |
| 数据模型 | Pydantic v2 | 校验 Planner 输出、工具参数、审批参数和验证结果 |
| ORM/迁移 | SQLAlchemy 2 + Alembic | 管理业务状态和数据库迁移 |
| 主数据库 | PostgreSQL | 保存租户、任务、步骤、审批、动作账本和检查点 |
| 向量检索 | pgvector | MVP 复用 PostgreSQL，减少独立向量数据库运维 |
| 持久工作流 | Temporal Python SDK | 提供长任务重试、暂停、信号、取消和崩溃恢复能力 |
| 浏览器执行 | Playwright | DOM、Accessibility、截图、网络事件和浏览器操作 |
| Benchmark 适配 | BrowserGym | 连接 WorkArena 和 WebArena 系列评测环境 |
| MCP | 官方 MCP SDK | 统一发现和调用支持 MCP 的企业工具 |
| 文件解析 | PyMuPDF、python-docx、openpyxl | 解析 PDF、Word 和 Excel 输入 |
| 大对象存储 | MinIO/S3 | 保存截图、DOM 快照、原始文件和回放产物 |
| 可观测性 | OpenTelemetry SDK + Collector + Jaeger | 统一模型、规划、工具、浏览器和验证 Span |
| 指标 | Prometheus + Grafana | 展示成功率、延迟、Token、重规划和审批指标 |
| 测试 | pytest + pytest-asyncio + Playwright Test | 单元、集成和端到端验证 |
| 本地部署 | Docker Compose | 一键启动 PostgreSQL、Temporal、MinIO 和观测组件 |

### 4.2 为什么不把 Agent 框架作为核心依赖

MVP 的关键是可恢复状态、审批和副作用控制，不是调用链数量。核心状态机、DAG、策略判断和动作账本应由项目自身定义，避免将业务正确性隐藏在 Agent 框架内部。

可以使用模型厂商 SDK 的结构化输出能力，但必须通过统一的 `ModelGateway` 封装。这样可以替换模型、统计 Token、统一重试和执行脱敏，而不会影响 Planner、Verifier 和 Replanner 的业务接口。

### 4.3 默认连接器范围

产品运行时首版只实现三个代表性连接器：

1. 邮件：读取邮件、创建草稿、发送、查询已发送状态；
2. 日历：查询空闲时间、创建和查询日程；
3. 任务/知识系统：检索文档、创建任务、查询任务状态。

连接器必须实现统一接口，因此实际演示可以选择 Google Workspace + Notion，也可以替换成飞书。每个连接器同时提供 Fake Adapter，用于本地测试和确定性评测。

公开 Benchmark 的 ServiceNow、GitLab、Reddit、购物站点等环境作为独立评测适配器，不与产品连接器耦合。

## 5. 总体架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Web Console                             │
│  任务输入 │ 计划预览 │ 审批中心 │ 实时执行 │ 证据与回放        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST + SSE
┌──────────────────────────────▼──────────────────────────────────┐
│                         FastAPI Gateway                         │
│  Auth │ Tenant Context │ Task API │ Approval API │ Artifact API │
└───────────────┬──────────────────────────────┬──────────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼─────────────────┐
│       Temporal Workflow      │  │      Knowledge Service       │
│ Plan → Execute → Verify      │  │ Parse → Chunk → Embed → RAG  │
│      ↘ Replan / Approval     │  └────────────┬─────────────────┘
└───────────────┬──────────────┘               │
                │                              │
┌───────────────▼─────────────────────────────────────────────────┐
│                         Tool Runtime                            │
│ Policy Engine │ Channel Router │ MCP/API Adapters │ Browser     │
│ Idempotency   │ Credential Proxy │ Result Normalizer            │
└───────────────┬─────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│ PostgreSQL/pgvector │ MinIO/S3 │ OTel Collector │ Jaeger/Grafana│
└─────────────────────────────────────────────────────────────────┘
```

### 5.1 组件职责

- `Task API`：创建、查询、暂停、恢复和取消任务。
- `Planner`：输出结构化任务 DAG，不直接执行动作。
- `Policy Engine`：判断权限、风险、审批要求和允许的执行通道。
- `Channel Router`：在 API/MCP 和 Computer Use 之间选择执行方式。
- `Executor`：只执行已经满足依赖且通过策略检查的节点。
- `Verifier`：使用独立证据判断业务结果，不信任 Executor 的成功声明。
- `Replanner`：根据失败类型局部修改尚未完成的任务节点。
- `Knowledge Service`：在当前租户和用户权限范围内提供检索结果。
- `Checkpoint Service`：保存可恢复业务状态；OpenTelemetry 不承担业务状态恢复。
- `Artifact Service`：保存页面、截图、文件和验证证据。

## 6. Agent 工作流

### 6.1 任务状态机

```text
CREATED
  ↓
PLANNING
  ↓
PLAN_READY
  ├── 计划无效 → FAILED
  └── 执行
        ↓
RUNNING
  ├── 需要审批 → WAITING_APPROVAL
  │                 ├── 拒绝 → CANCELLED / REPLANNING
  │                 └── 通过 → RUNNING
  ├── 验证失败且可恢复 → REPLANNING → RUNNING
  ├── 用户暂停 → PAUSED → RUNNING
  ├── 用户取消 → CANCELLED
  ├── 不可恢复失败 → FAILED
  └── 全部目标验证通过 → SUCCEEDED
```

只有 Verifier 确认全局成功条件满足，任务才能进入 `SUCCEEDED`。

### 6.2 Planner

Planner 输入：

- 用户目标与附件摘要；
- 当前用户、租户和授权工具；
- 检索到的企业政策与流程知识；
- 风险策略；
- 可用连接器能力清单；
- Token、步骤数、时限和费用预算。

Planner 输出必须满足固定 JSON Schema：

```json
{
  "goal": "生成项目周报并在审批后发送",
  "constraints": ["不得发送给租户外收件人"],
  "success_criteria": [
    {"type": "artifact_exists", "target": "weekly_report"},
    {"type": "remote_state", "target": "sent_email"}
  ],
  "steps": [
    {
      "id": "collect_updates",
      "description": "收集本周项目更新",
      "depends_on": [],
      "capability": "project.search_updates",
      "preferred_channel": "api",
      "risk": "R0",
      "preconditions": [],
      "expected_effects": ["产生结构化进展列表"],
      "verification": [{"type": "schema", "rule": "updates.length > 0"}]
    },
    {
      "id": "send_report",
      "description": "发送周报邮件",
      "depends_on": ["collect_updates"],
      "capability": "mail.send",
      "preferred_channel": "api",
      "risk": "R2",
      "requires_approval": true,
      "expected_effects": ["外部收件人收到邮件"],
      "verification": [{"type": "remote_query", "rule": "message_id exists in sent"}]
    }
  ]
}
```

Planner 输出后必须执行确定性校验：

- DAG 无环；
- 节点 ID 唯一，依赖均存在；
- 所需能力存在；
- 风险等级没有被模型降低；
- 每个有副作用的节点都有验证规则；
- 每个 R2 节点都要求审批；
- R3 动作在 MVP 中被拒绝；
- 计划没有超出最大步骤数和预算。

### 6.3 Executor

Executor 每轮只执行一个已就绪节点，首版不并行执行，以降低副作用和恢复复杂度。

执行步骤：

1. 读取任务与节点最新版本；
2. 检查依赖、权限和预算；
3. 解析并校验工具参数；
4. 计算风险等级和参数哈希；
5. 如需审批，持久化审批请求并等待 Temporal Signal；
6. 生成动作幂等键；
7. 调用 API/MCP 或浏览器执行器；
8. 将原始结果保存为 Artifact；
9. 写入 Action Ledger；
10. 交给 Verifier 判断结果。

动作幂等键建议为：

```text
sha256(tenant_id + task_id + step_id + action_type + normalized_parameters)
```

如果调用超时，Executor 必须先查询远端状态，不能直接切换通道重做。

### 6.4 Verifier

Verifier 按以下顺序寻找证据：

1. 确定性本地规则：Schema、字段值、文件哈希；
2. 远端 API 查询：重新查询邮件、日程、任务或工单；
3. 跨通道验证：API 执行后使用 UI 或网络响应验证，反之亦然；
4. DOM/Accessibility 状态验证；
5. 截图视觉验证；
6. 只有无法结构化判断时才使用模型语义判断。

验证结果统一为：

```json
{
  "status": "PASSED | FAILED | INCONCLUSIVE",
  "evidence_refs": ["artifact://..."],
  "observed_state": {},
  "reason": "",
  "retryable": true,
  "confidence": 1.0
}
```

`INCONCLUSIVE` 不等于成功。涉及外部副作用时，无法确认结果必须进入人工处理或远端状态核对。

### 6.5 Replanner

失败先分类，再决定是否重规划：

| 失败类型 | 示例 | 处理 |
| --- | --- | --- |
| 瞬时失败 | 429、网络抖动 | 指数退避后重试原动作 |
| 页面漂移 | 元素不存在、遮挡 | 重新观测并修复定位 |
| 权限失败 | 403、OAuth scope 不足 | 停止并提示用户授权 |
| 参数失败 | 字段格式不符合要求 | 修改当前节点参数 |
| 前置条件变化 | 收件人或资源已变化 | 局部重规划，必要时重新审批 |
| 结果不确定 | 请求超时但可能已提交 | 先查询状态，禁止盲目重试 |
| 不可恢复失败 | 账户禁用、目标不存在 | 终止并生成诊断 |

Replanner 只能修改未完成节点。已成功并产生副作用的节点必须保留在动作账本中；若新计划改变已审批参数，原审批立即失效。

## 7. 多模态页面上下文管线

### 7.1 观测来源

每次浏览器动作后收集：

- 当前 URL、标题、标签页和 frame；
- DOM 中可见或与任务相关的节点；
- Accessibility Tree 的 role、name、value、state；
- 页面截图及交互区域截图；
- 最近一次动作、网络状态、弹窗和下载；
- 上一版本页面元素图。

### 7.2 统一元素模型

```json
{
  "element_id": "e_42",
  "role": "button",
  "name": "Send",
  "text": "Send",
  "value": null,
  "states": ["visible", "enabled"],
  "bbox": [120, 640, 88, 32],
  "dom_attributes": {"data-testid": "send-button"},
  "frame_id": "main",
  "interactable": true,
  "screenshot_crop_ref": "artifact://crop/...",
  "fingerprint": "..."
}
```

DOM 与 Accessibility 节点通过 backend node、frame、文本、role 和空间位置匹配。稳定 ID 优先使用 `data-testid`、显式 ID 和 Accessibility 属性；无法稳定匹配时使用结构路径与视觉位置组合，并在导航后重新解析。

### 7.3 上下文压缩

压缩顺序：

1. 删除不可见、纯装饰和重复节点；
2. 保留输入框、按钮、链接、表格行、菜单和错误提示；
3. 根据当前步骤、目标实体、role 和文本相似度打分；
4. 保留 Top-K 交互元素及其父子上下文；
5. 只传递与上次观测相比的新增、删除和状态变化；
6. 压缩早期动作历史为结构化摘要；
7. 在 Token Budget 内加入必要截图或局部截图。

必须提供完整观测回退条件：

- 连续两次找不到目标元素；
- 页面发生大范围导航或布局变化；
- 出现未知模态框或跨域 iframe；
- Verifier 判断页面证据不足；
- 模型明确请求完整页面，且仍在预算内。

### 7.4 Token 指标

固定同一模型、任务、随机参数和最大步数，比较：

```text
Token 降低率 =
(完整观测平均输入 Token - 压缩观测平均输入 Token)
/ 完整观测平均输入 Token
```

同时报告：

- 每步输入 Token 平均值和 P95；
- 每个成功任务的总 Token；
- 任务成功率变化；
- 页面观测构建耗时；
- 完整观测回退次数。

MVP 目标：成功率下降不超过 2 个百分点的前提下，单步平均输入 Token 至少降低 30%。目标必须在基线冻结后根据真实数据调整。

## 8. API/MCP 与 Computer Use 双通道

### 8.1 路由原则

```text
存在授权且稳定的结构化 API/MCP？
  ├── 是：优先 API/MCP
  └── 否：是否允许浏览器执行？
          ├── 是：Computer Use
          └── 否：返回能力不足
```

路由评分考虑：

- 能力是否覆盖；
- 当前用户授权范围；
- 动作风险；
- API 稳定性；
- 页面是否只能视觉访问；
- 历史成功率、成本和延迟；
- 是否能获得独立验证证据。

首版使用确定性规则，不用模型直接决定安全策略。模型只能提出通道偏好，Policy Engine 拥有最终决定权。

### 8.2 连接器接口

```python
class ToolAdapter(Protocol):
    def capabilities(self) -> list[Capability]: ...
    async def preview(self, action: ActionRequest) -> ActionPreview: ...
    async def execute(self, action: ActionRequest, idempotency_key: str) -> ActionResult: ...
    async def verify(self, action: ActionRequest, result: ActionResult) -> VerificationResult: ...
```

所有 API、MCP 和浏览器能力都转换成统一的 `ActionRequest` 与 `ActionResult`，避免 Planner 绑定某个供应商的参数格式。

### 8.3 通道降级规则

- API 认证失败：不得自动改用已登录浏览器绕过权限；
- API 明确返回未执行：可以重新规划为 UI 通道；
- API 超时或结果未知：先查询远端状态；
- UI 元素缺失：重新观测，必要时改用 API；
- 已产生副作用：只能继续验证或补偿，禁止重复执行；
- 通道变化导致参数变化：重新生成预览，R2 动作重新审批。

## 9. 风险、审批和安全边界

### 9.1 风险分级

| 级别 | 含义 | 示例 | MVP 策略 |
| --- | --- | --- | --- |
| R0 | 只读 | 搜索邮件、读取文档 | 自动执行并记录 |
| R1 | 可逆或内部草稿 | 创建草稿、生成未发布报告 | 自动执行，界面可撤销 |
| R2 | 外部可见写入 | 发邮件、邀请会议、创建正式任务 | 必须参数预览和人工审批 |
| R3 | 高危或不可逆 | 删除数据、付款、修改管理员权限 | MVP 禁止执行 |

实际风险取“模型声明风险、工具固定风险、策略动态风险”三者中的最高值，不能由模型主动降低。

### 9.2 审批绑定

审批记录必须包含：

- `tenant_id`、`task_id` 和 `step_id`；
- 动作类型；
- 完整可读参数预览；
- 标准化参数哈希；
- 计划版本；
- 审批人和时间；
- 过期时间；
- 单次执行或批量执行范围。

执行前重新计算参数哈希。不一致时原审批无效，防止“审批时是一组参数，执行时被模型换成另一组参数”。

### 9.3 租户与凭证隔离

- 所有业务表包含 `tenant_id`，查询层强制注入租户条件；
- PostgreSQL 启用 Row Level Security 作为第二道防线；
- 向量检索必须同时过滤租户和文档权限；
- 凭证由 Credential Proxy 按工具调用临时注入，不进入模型上下文；
- Token 和密钥只保存在外部 Secret Manager 或本地开发密钥存储中；
- 日志、Span、错误信息和截图元数据统一经过脱敏器；
- Artifact 使用租户前缀和短期签名 URL。

### 9.4 副作用约束

- 文件系统限制在任务工作目录和租户 Artifact 路径；
- 浏览器只允许访问域名白名单；
- 工具参数由 JSON Schema 校验；
- 每个任务设置最大步骤、重规划、Token、费用和运行时间；
- 外部写入均写入 Action Ledger；
- 对支持撤销的操作记录补偿动作；
- 网页和文档内容全部视为不可信数据，不能改变系统策略或申请新权限。

## 10. 企业知识检索

### 10.1 数据流程

```text
上传/同步文档
  → 病毒与类型检查
  → 文本和表格解析
  → 保留标题、页码、工作表等结构
  → 分块
  → Embedding
  → PostgreSQL + pgvector
  → 租户和 ACL 过滤检索
  → Rerank
  → 返回内容、来源和权限信息
```

### 10.2 MVP 检索原则

- 先使用混合检索：全文检索 + 向量相似度；
- 每个 Chunk 保存文档 ID、页码/Sheet、版本和 ACL；
- Planner 只接收与当前目标相关的 Top-K Chunk；
- 检索内容放在明确的数据边界内，不允许其中的指令覆盖系统策略；
- 计划和最终报告保留来源引用，便于用户核验；
- 文档删除或权限撤销后，相应 Chunk 必须不可检索。

## 11. 数据模型

核心表建议如下：

| 表 | 关键字段 | 用途 |
| --- | --- | --- |
| `tenants` | id, name, policy_version | 租户信息 |
| `users` | id, tenant_id, role | 用户与角色 |
| `credential_refs` | tenant_id, provider, secret_ref, scopes | 只保存凭证引用 |
| `task_runs` | id, tenant_id, goal, status, plan_version, budgets | 任务主记录 |
| `task_steps` | task_id, step_id, dependencies, status, risk | DAG 节点 |
| `approvals` | step_id, parameter_hash, status, expires_at | 审批绑定 |
| `action_ledger` | idempotency_key, action, channel, remote_id, status | 副作用账本 |
| `verifications` | step_id, status, evidence_refs, observed_state | 验证结果 |
| `checkpoints` | task_id, workflow_state, plan_version, created_at | 恢复状态 |
| `artifacts` | tenant_id, type, uri, hash, redaction_state | 文件与页面证据 |
| `documents` | tenant_id, acl, source, version | 知识文档 |
| `document_chunks` | document_id, content, embedding, metadata | 检索数据 |
| `model_calls` | trace_id, model, usage, latency, prompt_version | 成本和调试索引 |

状态修改必须使用数据库事务和乐观锁版本号，防止审批、取消和 Executor 同时写入导致竞态。

## 12. 服务接口

### 12.1 用户接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/v1/tasks` | 创建任务和上传附件引用 |
| `GET` | `/v1/tasks/{id}` | 查询任务、计划和状态 |
| `GET` | `/v1/tasks/{id}/events` | 通过 SSE 获取执行事件 |
| `POST` | `/v1/tasks/{id}/approve` | 审批指定步骤和参数哈希 |
| `POST` | `/v1/tasks/{id}/reject` | 拒绝并附带原因 |
| `POST` | `/v1/tasks/{id}/pause` | 请求安全暂停 |
| `POST` | `/v1/tasks/{id}/resume` | 从检查点恢复 |
| `POST` | `/v1/tasks/{id}/cancel` | 取消尚未执行的节点 |
| `GET` | `/v1/tasks/{id}/artifacts` | 获取结果和证据 |
| `GET` | `/v1/tasks/{id}/replay` | 获取审计回放时间线 |
| `POST` | `/v1/knowledge/documents` | 上传知识文档 |

### 12.2 内部接口

- `ModelGateway.generate_structured()`：统一模型调用、限流和 Token 统计；
- `CapabilityRegistry.list()`：列出当前租户可用能力；
- `PolicyEngine.evaluate()`：返回风险、审批和通道限制；
- `ChannelRouter.select()`：根据策略和运行状态选择通道；
- `ArtifactStore.put()`：保存并返回不可变引用；
- `CredentialProxy.invoke()`：在工具边界注入凭证；
- `EventBus.publish()`：向前端发送任务事件。

## 13. 前端工作台

首版只需要四个页面：

1. 新建任务：输入目标、上传文件、选择允许访问的系统；
2. 任务详情：显示计划 DAG、当前步骤、预算、事件和最终结果；
3. 审批面板：显示动作影响、真实参数、风险解释和验证方式；
4. 回放页面：按时间轴展示模型调用摘要、页面截图、工具动作和验证证据。

任务详情建议采用三栏布局：

```text
任务与文件 | 计划和执行时间线 | 当前步骤、审批或证据
```

前端不能仅展示“成功”文本。每个成功步骤都应提供远端对象 ID、查询结果、截图或其他可点击证据。

## 14. 可观测性、检查点与回放

### 14.1 Trace 结构

```text
agent.run
├── context.retrieve
├── planner.generate
├── plan.validate
├── step.execute
│   ├── browser.observe
│   ├── policy.evaluate
│   ├── approval.wait
│   ├── tool.call
│   └── verifier.check
├── replanner.generate
└── checkpoint.persist
```

每个 Span 记录：

- tenant、task、step、plan version 和 trace ID；
- 模型与 Prompt 版本、Token、延迟和错误类型；
- 工具名、通道和脱敏参数摘要；
- 页面 URL、元素 ID 和 Artifact 引用；
- 审批状态和参数哈希；
- 验证结果、证据引用和重规划原因。

禁止在 Span 中保存原始凭证、完整邮件正文和未脱敏个人信息。

### 14.2 检查点

以下时机必须创建检查点：

- 计划验证通过后；
- 进入审批等待前；
- 每次远端副作用确认后；
- 每个 DAG 节点完成后；
- 重规划完成后；
- 用户暂停或取消时。

检查点保存业务状态、计划版本、完成节点、动作账本引用和 Artifact 引用。Temporal 负责恢复控制流，PostgreSQL 负责恢复业务事实，二者都不能依赖 OpenTelemetry 反推状态。

### 14.3 回放

MVP 提供的是“审计回放”，即按时间顺序查看当时的观测、决策、动作和证据；默认不重新执行真实操作。重新执行必须创建新任务，并重新经过策略和审批。

## 15. 评测方案

### 15.1 三层评测

1. 单元和集成测试：验证状态机、策略、连接器、幂等和租户隔离；
2. 自建跨系统任务集：验证产品主流程和安全目标；
3. 公开 Benchmark：使用 WorkArena/WorkArena++ 和 WebArena-Verified 衡量通用网页任务能力。

公开 Benchmark 的分数受模型和环境影响较大，第一阶段先建立可复现基线，再冻结具体目标，不应在运行前承诺虚假的绝对成绩。

### 15.2 自建任务集

首版建立 40 条固定任务：

| 类型 | 数量 | 示例 |
| --- | ---: | --- |
| 只读检索 | 8 | 查询邮件、文档和任务状态 |
| 信息抽取与生成 | 8 | 从附件生成结构化周报 |
| 跨系统写入 | 10 | 邮件信息转任务、日历事件转通知 |
| 多步依赖任务 | 8 | 收集、核对、生成、审批、发送 |
| 安全与对抗任务 | 6 | 提示注入、跨租户、参数篡改、重复执行 |

每个任务需要：

- 固定初始状态；
- 用户目标；
- 允许和禁止的动作；
- 确定性最终状态检查器；
- 是否预期审批；
- 可注入的失败点；
- 清理和重置脚本。

### 15.3 核心指标

| 指标 | 定义 |
| --- | --- |
| Task Success Rate | 最终业务状态完全满足目标的任务比例 |
| Step Success Rate | 验证通过的节点占全部应执行节点的比例 |
| Recovery Rate | 发生可恢复失败后最终成功的比例 |
| Mean Replans to Recovery | 成功恢复样本中的平均局部重规划次数 |
| Unauthorized High-risk Actions | 未取得有效审批却成功执行的 R2/R3 操作数 |
| Duplicate Side Effects | 因超时、重试或通道切换造成的重复写入数 |
| Token per Success | 每个成功任务消耗的输入和输出 Token |
| Cost per Success | 每个成功任务的模型及工具费用 |
| End-to-end Latency | 从任务创建到最终状态的时长 |
| Approval Precision/Recall | 该拦截的动作是否拦截，不需审批的动作是否被误拦截 |

### 15.4 MVP 验收目标

- 自建 40 条任务的端到端成功率不低于 70%；
- 安全与对抗任务中，未审批 R2/R3 操作成功数为 0；
- 重试导致的重复副作用数为 0；
- 可恢复失败恢复率不低于 70%；
- 成功恢复任务平均重规划不超过 2 次；
- 上下文压缩后平均输入 Token 降低至少 30%，成功率下降不超过 2 个百分点；
- 任务进程重启后，所有非终态任务均能恢复到最近安全检查点；
- 每个外部写入均能在回放页面中找到审批、动作和验证证据。

所有指标至少运行 3 次，报告均值、标准差和失败类别。不得只展示最佳单次结果。

## 16. 测试策略

### 16.1 单元测试

- DAG 校验、拓扑排序和循环检测；
- 状态机非法跳转；
- 风险等级取最高值；
- 审批参数哈希与过期逻辑；
- 幂等键稳定性；
- Channel Router 决策；
- DOM/Accessibility 元素融合和页面 Diff；
- Token Budget 裁剪；
- 日志和 Span 脱敏；
- 租户查询过滤；
- Replanner 不修改已完成节点。

### 16.2 连接器契约测试

每个 Adapter 都运行同一组契约测试：

- 能力描述可发现；
- preview 不产生副作用；
- 参数 Schema 拒绝非法字段；
- 相同幂等键不重复执行；
- execute 返回标准结果；
- verify 使用远端事实；
- 权限不足不会自动绕过；
- 凭证不会出现在返回值和日志中。

### 16.3 集成和端到端测试

- Docker Compose 启动完整依赖；
- Fake 企业系统支持确定性状态重置；
- 从创建任务到审批、执行、验证完整跑通；
- 浏览器页面发生小幅变化时仍能定位元素；
- Temporal Worker 重启后恢复；
- API 超时但远端已成功时不会重复写入；
- 审批后参数变化会触发重新审批；
- 用户取消后不再启动新动作。

### 16.4 安全测试

- 跨租户文档和 Artifact 访问；
- 路径穿越和非法下载；
- 网页/文档 Prompt Injection；
- 工具参数中注入额外收件人；
- 使用 UI 绕过 API 权限；
- 日志、错误和 Trace 中的凭证泄露；
- 旧审批重放；
- 任务并发导致的重复副作用。

## 17. 建议代码结构

```text
WorkPilot/
├── apps/
│   ├── api/                     # FastAPI 入口
│   ├── worker/                  # Temporal Worker
│   └── web/                     # Next.js 工作台
├── workpilot/
│   ├── agents/
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── verifier.py
│   │   └── replanner.py
│   ├── browser/
│   │   ├── observer.py
│   │   ├── element_graph.py
│   │   ├── compressor.py
│   │   └── playwright_runtime.py
│   ├── connectors/
│   │   ├── base.py
│   │   ├── mcp.py
│   │   ├── mail/
│   │   ├── calendar/
│   │   ├── knowledge/
│   │   └── fake/
│   ├── knowledge/
│   ├── models/
│   ├── policy/
│   ├── security/
│   ├── telemetry/
│   ├── workflows/
│   └── db/
├── evals/
│   ├── datasets/
│   ├── evaluators/
│   ├── workarena/
│   └── webarena_verified/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   └── security/
├── deploy/
│   ├── docker-compose.yml
│   └── otel-collector.yml
├── docs/
└── pyproject.toml
```

## 18. 八周实现路线图

### 第 1 周：工程骨架和任务状态

- 建立 FastAPI、PostgreSQL、Alembic 和 Docker Compose；
- 定义 Task、Step、Approval、Action 和 Verification Schema；
- 实现 DAG 校验和任务状态机；
- 建立基础 OpenTelemetry Trace；
- 完成单元测试和 CI。

退出条件：可以创建一个任务、保存计划并沿合法状态流转。

### 第 2 周：Planner 与知识检索

- 实现 `ModelGateway` 和结构化输出；
- 完成文档解析、分块和 pgvector 检索；
- 实现 Planner Prompt、Schema 和确定性计划校验；
- 建立 Fake Connector Capability Registry。

退出条件：给定目标和文档，可以稳定生成合法 DAG，并能指出知识来源。

### 第 3 周：API/MCP 执行与验证

- 实现 ToolAdapter、MCP Adapter 和 Fake 企业系统；
- 实现 Action Ledger 与幂等键；
- 实现邮件、日历、任务三类能力；
- 实现确定性 Verifier。

退出条件：在 Fake 系统中完成一个跨三系统任务，重试不会重复写入。

### 第 4 周：Computer Use 与上下文压缩

- 集成 Playwright；
- 实现 DOM、Accessibility 和截图采集；
- 建立统一元素图、交互元素筛选和增量 Diff；
- 实现浏览器动作与页面状态验证。

退出条件：在固定网页任务上稳定执行，并产出完整页面证据。

### 第 5 周：审批和安全策略

- 实现 R0–R3 风险策略；
- 完成参数预览、参数哈希和审批 API；
- 实现租户过滤、路径与域名约束、凭证代理；
- 建立 Prompt Injection 和越权测试。

退出条件：所有 R2 动作必须通过有效审批，R3 动作全部被拒绝。

### 第 6 周：Temporal、重规划和恢复

- 将运行循环迁移到 Temporal Workflow；
- 支持暂停、取消、审批 Signal 和 Worker 重启恢复；
- 实现失败分类和局部 Replanner；
- 增加通道降级和不确定结果核对。

退出条件：在注入网络错误、页面变化和 Worker 重启后可以安全恢复。

### 第 7 周：工作台与评测

- 完成任务、审批和回放页面；
- 建立 40 条自建任务及环境重置；
- 接入指标统计和 Token 对照实验；
- 运行 WorkArena/WebArena-Verified 小规模基线。

退出条件：可以一键执行固定评测并生成 JSON 与 HTML 报告。

### 第 8 周：稳定性和交付

- 分类修复主要失败模式；
- 完成端到端、安全和恢复测试；
- 固化 Demo 数据与脚本；
- 输出架构文档、评测报告和演示视频；
- 将真实指标写入项目介绍。

退出条件：达到第 15.4 节的验收目标，所有自动化测试通过。

## 19. 开发顺序原则

1. 先实现 Fake Adapter，再接真实 SaaS，保证业务闭环可测；
2. 先做确定性规则，再增加模型判断；
3. 先顺序 DAG，再考虑并发；
4. 先建立 Action Ledger 和审批，再开放外部写入；
5. 先验证最终业务状态，再优化 Agent 的“思考过程”；
6. 先跑出完整上下文基线，再开发压缩，否则无法证明优化效果；
7. 先完成自建任务集，再接公开 Benchmark，避免只对 Benchmark 特化。

## 20. 部署和配置

本地开发通过 Docker Compose 启动：

- PostgreSQL + pgvector；
- Temporal Server；
- MinIO；
- OpenTelemetry Collector；
- Jaeger；
- Prometheus/Grafana；
- Fake Mail/Calendar/Task 服务。

应用服务在宿主机或容器中启动。所有配置通过环境变量注入，并提供不含密钥的 `.env.example`。生产部署前还需要补充：

- 托管数据库和对象存储；
- Secret Manager；
- TLS、SSO 和企业身份映射；
- 备份、数据保留和删除策略；
- 多副本 Worker 与队列隔离；
- 合规审计和数据驻留策略。

这些生产能力不属于初版验收范围。

## 21. 主要风险与应对

| 风险 | 影响 | MVP 应对 |
| --- | --- | --- |
| 范围过大 | 无法形成完整闭环 | 只做三类连接器和一个主 Demo |
| 浏览器页面漂移 | Computer Use 成功率低 | 统一元素图、重新观测和 API 优先 |
| 模型错误判断成功 | 产生错误结果 | 独立 Verifier 和确定性最终状态检查 |
| 超时导致重复写入 | 重复邮件或任务 | Action Ledger、幂等键、先查询后重试 |
| 审批被参数替换绕过 | 高风险安全问题 | 参数哈希绑定和执行前再次校验 |
| Prompt Injection | 工具越权或数据泄露 | 内容/指令隔离、固定策略和域名白名单 |
| Benchmark 搭建耗时 | 拖慢产品实现 | 自建任务优先，公开评测放到第 7 周 |
| OTel 数据泄露 | 敏感信息进入观测平台 | 统一脱敏和大对象外置 |
| Temporal 学习成本 | 进度风险 | 前两周先用显式状态机，第 6 周接入持久工作流 |

## 22. MVP 完成定义

满足以下条件才视为初版完成：

- 用户可以提交包含附件的跨系统任务；
- Planner 能生成合法、可解释且通过策略检查的任务 DAG；
- Executor 能使用至少一个 API/MCP Adapter 和 Playwright 完成操作；
- R2 操作展示参数并等待用户审批，R3 操作无法执行；
- 每个副作用都有幂等记录和独立验证证据；
- 失败能够被分类，满足条件时进行局部重规划；
- 任务支持暂停、取消和进程重启后的检查点恢复；
- 用户可以查看完整执行时间线和审计回放；
- 40 条自建任务、自动化测试和安全测试全部完成；
- 指标报告明确区分目标、基线和最终结果；
- README、架构文档、启动说明和演示脚本齐全。

## 23. 最终交付物

- 可本地运行的 WorkPilot Web 应用；
- 三类真实或沙箱连接器及对应 Fake Adapter；
- Planner–Executor–Verifier 运行时；
- 多模态浏览器观测和上下文压缩模块；
- 风险策略、审批中心和副作用账本；
- OpenTelemetry Trace、指标面板和审计回放；
- 40 条自建任务、公开 Benchmark 适配和评测报告；
- 架构说明、API 文档、部署说明和 3～5 分钟演示视频。
