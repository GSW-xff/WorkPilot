# WorkPilot V2 修改设计方案

> 文档状态：提案  
> 编写日期：2026-10-09  
> 基线版本：Git commit `ea3259b`  
> 目标：将当前“可验证的安全纵向原型”升级为“可持久运行、可接真实系统、可量化评测、可用于面试深挖”的产品型项目。

## 1. 结论先行

当前 WorkPilot 已经证明了最关键的产品假设：一个办公 Agent 可以先规划、再执行，在外部写入前绑定真实参数审批，并通过独立证据确认结果。它不是只有聊天界面的 Demo，而是已经具备 DAG、状态机、风险策略、幂等账本、Verifier、租户边界和审计回放的纵向闭环。

但当前版本仍是“单进程、Fake 数据、确定性 Planner”的工程原型，尚不能证明以下能力：

1. 进程重启、并发请求和网络超时下仍能正确恢复；
2. 模型能够稳定生成受约束的计划，并在真实系统中安全执行；
3. 用户可以上传真实材料、理解计划、控制任务并获得有用结果；
4. 项目有可复现的成功率、延迟、成本和安全指标；
5. 系统能以标准部署方式运行，并被定位、调试和演进。

因此 V2 不应立即扩展大量连接器或做通用多 Agent。V2 的核心是把一条真实办公流程做深：

> 用户上传项目材料，系统结合知识库与真实项目数据生成周报；为缺失信息创建跟进任务；展示邮件真实收件人、标题和正文；审批后发送；进程重启后仍能继续，并能回放每一步证据。

V2 建议集中完成六件事：

- PostgreSQL 持久化、迁移、事务、租户隔离；
- Temporal 持久工作流与可靠审批/暂停/恢复；
- `ModelGateway`、结构化 Planner 与受约束局部 Replanner；
- 一组真实连接器加 Fake 合同测试；
- 文件解析、混合检索、来源引用；
- Next.js 工作台、OpenTelemetry 和固定任务集评测。

## 2. 当前项目功能总结

### 2.1 当前可用能力

| 领域 | 当前实现 | 用户价值 |
| --- | --- | --- |
| 任务入口 | 创建、查询、运行、暂停、恢复、取消任务 | 用户能控制任务生命周期 |
| 计划 | 确定性周报 Planner，生成 5 步 DAG | 能直观看到任务依赖和执行顺序 |
| 计划校验 | 节点唯一、依赖存在、无环、能力存在、步骤数和风险检查 | 模型或代码不能提交明显非法计划 |
| 风险策略 | R0–R3；R2 必须审批；R3 禁止 | 外部写入不会静默发生 |
| 审批 | 参数预览、规范化哈希、计划版本绑定 | 防止“审批后换参数” |
| 执行 | 顺序执行，每次运行到完成、失败或审批点 | 降低副作用和恢复复杂度 |
| 连接器 | 项目更新、知识检索、报告、任务、邮件、日历 Fake 能力 | 可确定性演示跨系统流程 |
| 幂等 | tenant/task/step/action/parameters 生成幂等键 | 相同动作不会重复产生副作用 |
| 验证 | Adapter 执行后重新读取远端 Fake 状态 | 不把工具返回的 success 当成最终成功 |
| 审计 | Action Ledger、Artifact、Checkpoint、Timeline、SSE | 用户能查看发生过什么 |
| 租户边界 | tenant-aware Repository 和知识文档过滤 | 不同租户不能直接读取同一任务 |
| 工作台 | 三栏静态 Web Console | 可创建、执行、审批和查看证据 |
| 工程质量 | 22 项自动化测试、依赖锁定、启动文档 | 基础行为可重复验证 |

### 2.2 当前默认流程

```text
收集项目更新（R0）
        ├────────────┐
读取周报模板（R0）   │
        └──────┬─────┘
             生成周报草稿（R1）
                     ↓
          审批并创建跟进任务（R2）
                     ↓
            审批并发送邮件（R2）
                     ↓
             重新查询并验证结果
```

### 2.3 当前限制

| 限制 | 直接影响 | V2 处理 |
| --- | --- | --- |
| 内存仓储 | 重启丢数据，无法多副本 | PostgreSQL + SQLAlchemy + Alembic |
| 同进程执行 | 长任务占用 API，崩溃无法继续 | Temporal Workflow/Activity |
| Fake Adapter | 不能证明真实集成与 OAuth 能力 | 接入一套真实 SaaS，Fake 继续做回归 |
| 确定性 Planner | 不能证明自然语言泛化 | 结构化模型输出 + 规则校验 + fallback |
| 无局部 Replanner | 页面或参数变化后只能失败 | 失败分类和只修改未完成节点的 Replanner |
| 知识检索为内存匹配 | 无文件解析、向量检索和 ACL 生命周期 | 文件管线 + PostgreSQL FTS/pgvector |
| 仅 API 通道 | 尚未证明 Computer Use | Playwright Browser Adapter，限制单一站点 |
| 静态单页 | 缺少登录、任务列表和易用的错误恢复 | Next.js 工作台和统一设计系统 |
| 无真实遥测后端 | 无法量化性能、成本和失败模式 | OpenTelemetry + Prometheus/Grafana |
| 无固定评测集 | 无可复现的成功率与安全数据 | 24 条 V2 固定任务与报告生成器 |
| 客户端自报身份 | 不可用于真实环境 | OIDC/JWT + 网关注入租户上下文 |

## 3. 面向互联网大厂面试的项目差距

### 3.1 当前项目已经具备的亮点

1. **问题不是“再做一个聊天机器人”**：项目解决跨系统办公操作、审批与验证，业务问题清楚。
2. **有显式状态和不变量**：DAG、状态机、风险等级、审批哈希、幂等键都能展开讲设计取舍。
3. **关注失败而非 Happy Path**：超时、重复副作用、参数替换、跨租户和验证失败都有设计入口。
4. **可测试**：Fake Adapter 让流程确定性运行，比依赖真实 SaaS 的脆弱 Demo 更适合作为回归基线。
5. **范围意识较好**：没有在首版堆叠多 Agent、无限插件或高危动作。

### 3.2 面试官最可能追问而当前证据不足的问题

| 追问 | 当前不足 | V2 应给出的证据 |
| --- | --- | --- |
| 服务挂了以后任务怎么办？ | Checkpoint 只在内存 | Worker kill/restart 集成测试，任务从最近安全点恢复 |
| API 超时但邮件可能发出怎么办？ | 只有 Fake 幂等 | 远端查询优先、Outbox/Inbox、故障注入测试 |
| 多租户如何保证不串数据？ | 应用层 key 隔离 | PostgreSQL RLS、ACL、跨租户安全测试 |
| LLM 输出非法计划怎么办？ | 尚未接模型 | JSON Schema、重试、规则校验、fallback、非法样本集 |
| 为什么需要 Temporal？ | 只有文档取舍 | 与数据库轮询方案的 ADR、故障恢复实测 |
| 怎么知道 Agent 真的变好了？ | 只有目标，没有结果 | 固定任务集、基线、均值/标准差、失败分类 |
| 如何控制成本和延迟？ | 无真实 Token 数据 | Token、成本、P50/P95、每成功任务成本 |
| 如何排查一次失败？ | Timeline 有限 | trace_id 串联模型、工具、数据库、验证与截图 |
| 用户为什么愿意使用？ | 只有技术流程 | 用户研究、可解释预览、可撤销/补偿、模板与反馈闭环 |
| 如何上线？ | 无容器和 CI | Docker Compose、CI、迁移、健康检查、SLO 与运行手册 |

### 3.3 与当前岗位要求的对应关系

腾讯当前 Agent 工程岗位明确强调 Python 异步与并发、模型/工具调用、上下文管理、任务执行、Trace、结果评估、Kubernetes、性能和稳定性；办公 Agent 岗位还强调需求分析、全栈开发、模型集成、任务调度、沙箱和高可用。Google 当前基础设施岗位也强调分布式系统、可观测性、可靠性、容器化与减少人工运维。V2 应让仓库中每项能力都有代码、测试和测量结果，而不仅是架构图。

项目对面试能力的目标映射如下：

| 能力维度 | V2 项目证据 |
| --- | --- |
| 数据结构与算法 | DAG 拓扑排序、循环检测、调度、Diff、检索与 rerank |
| Python 工程 | asyncio、类型模型、协议接口、依赖注入、错误边界 |
| 后端系统设计 | API、PostgreSQL、缓存、工作流、对象存储、事件与幂等 |
| 分布式系统 | at-least-once、重试、去重、乐观锁、Outbox、故障恢复 |
| AI Agent | Structured Output、tool calling、context budget、Verifier、Replanner |
| 安全 | 租户隔离、最小权限、Prompt Injection、审批绑定、审计 |
| 可观测性 | Trace、Metric、Log 关联，Token/成本/质量指标 |
| 测试 | 单元、契约、集成、E2E、安全、故障注入、评测集 |
| 前端与产品 | 清晰状态、审批体验、证据、错误恢复、无障碍与反馈 |
| DevOps | Docker Compose、CI、迁移、健康检查、运行手册 |

## 4. V2 产品定位

### 4.1 一句话定位

WorkPilot V2 是一个“先展示计划和影响、经审批后跨系统执行、用证据证明结果”的企业办公任务执行助手。

### 4.2 首要用户

- 项目经理：从邮件、项目系统和材料中生成周报并跟进缺失事项；
- 运营人员：从附件提取数据并录入任务系统；
- 行政人员：基于参与人空闲时间创建日程并发送通知。

V2 的主用户仍聚焦项目经理，其他角色只通过固定评测任务验证可扩展性，不扩张为通用办公平台。

### 4.3 用户价值原则

1. **先让用户理解，再让系统行动**：计划、参数、影响和验证方式必须可读。
2. **用证据代替“我完成了”**：远端对象 ID、状态查询、来源和截图应可点击。
3. **失败可继续，而非重新开始**：保存检查点，明确哪些步骤已完成、哪些需要处理。
4. **自动化程度与风险成反比**：风险越高，权限越窄、审批越明确、验证越独立。
5. **不让用户理解内部框架**：错误信息给出原因、影响和下一步，而非暴露堆栈。

## 5. V2 目标与非目标

### 5.1 必须达成的目标

- 单机 Docker Compose 可启动 API、Worker、Web、PostgreSQL、Temporal、MinIO 和观测组件；
- 用户能上传 PDF、DOCX、XLSX/CSV 和图片，解析结果带来源位置；
- 模型 Planner 能生成合法 DAG，失败时降级为模板计划；
- 至少一套真实 SaaS 连接器完成读、预览、写、验证闭环；
- 至少一个固定网页任务通过 Playwright Browser Adapter 完成；
- 所有 R2 动作在有效审批前成功执行数为 0，R3 动作成功数为 0；
- Worker 重启后任务可以恢复，已完成副作用不重复执行；
- 24 条固定任务可一键运行并生成 JSON/HTML 报告；
- 用户可在工作台完成创建、计划确认、审批、暂停、恢复和证据回放；
- README、ADR、API 文档、数据模型、演示脚本和运行手册齐全。

### 5.2 明确不做

- 通用多 Agent 自主协作；
- 动态安装未知 MCP Server 或插件；
- 财务支付、删除、管理员权限和生产运维；
- 支持十几个 SaaS 的连接器市场；
- 移动端 App；
- 大规模模型训练或 Agent 强化学习；
- 以模型判断代替授权、审批、幂等和租户隔离。

## 6. V2 功能范围

### 6.1 P0：可用与可讲的核心版本

#### 持久化与工作流

- SQLAlchemy 2 异步 Repository；
- Alembic 初始化和迁移测试；
- PostgreSQL RLS 和 tenant session context；
- Temporal Workflow/Activity；
- Approval 使用同步可校验的 Workflow Update；
- Pause/Cancel 使用 Signal，状态读取使用 Query；
- Activity timeout、retry policy、heartbeat 和非重试错误；
- 数据库 Action Ledger 与唯一索引保证去重；
- Transactional Outbox 发布任务事件。

#### 模型与计划

- `ModelGateway.generate_structured()`；
- provider、模型、Prompt 版本、temperature、timeout 和 token usage 统一记录；
- Planner 使用 JSON Schema/Pydantic 校验；
- 最多两次 schema repair，仍失败则回退模板 Planner；
- Plan Validator 保留当前全部确定性安全规则；
- Replanner 只能修改未完成节点；
- 已审批参数或执行通道变化时使原审批失效。

#### 知识与附件

- MIME sniffing、大小和扩展名双重校验；
- PDF、DOCX、XLSX/CSV 和图片 OCR 解析；
- Chunk 保存页码、Sheet、单元格范围、文档版本和 ACL；
- PostgreSQL Full Text Search + pgvector 混合检索；
- 引用必须指向原文片段；
- 删除或撤销权限后 Chunk 立即不可检索；
- 文档内容作为不可信数据，不能覆盖系统策略。

#### 连接器

- 保留所有 Fake Adapter 和统一合同测试；
- 真实连接器只选一套生态，建议优先 Google Workspace：Gmail + Calendar；
- 任务/知识系统建议选择 Notion 沙箱，若 OAuth 成本过高则先用自建 Fake 服务；
- OAuth scope 最小化，刷新令牌只保存于 Secret Store；
- API 不可用时不得使用已登录浏览器绕过权限；
- 真实连接器必须实现 preview、execute、verify、lookup-before-retry。

#### Browser Adapter

- Playwright 只允许配置的域名白名单；
- 采集 URL、DOM、Accessibility Tree、截图和网络摘要；
- 元素统一为稳定 element graph；
- 先 role/name/test-id，最后才使用视觉坐标；
- 两次定位失败或大范围导航后回退完整观测；
- 浏览器动作与 API 动作使用同一 Action Ledger 和审批规则；
- V2 仅支持一个固定测试站点，不追求开放网页泛化。

#### 工作台

- 登录页和开发环境身份选择；
- 新建任务：目标、附件、系统权限和预计预算；
- 任务详情：DAG、执行时间线、当前步骤、耗时和错误；
- 审批抽屉：影响、参数 Diff、风险、过期时间、验证方式；
- Artifact 查看器：报告、来源、远端对象、截图；
- 恢复中心：显示失败分类和推荐操作；
- 回放页：按时间展示观察、决策、动作、审批和证据；
- 用户反馈：结果有用/无用、失败原因分类和自由文本。

#### 可观测性与评测

- OpenTelemetry 串联 API、Workflow、Activity、模型、工具和数据库；
- Span 默认不记录 Prompt、邮件正文、凭证或附件内容；
- Prometheus 指标与 Grafana 面板；
- 24 条固定任务：5 只读、5 生成、6 跨系统写入、4 恢复、4 安全对抗；
- 每条任务有初始状态、最终状态检查器、失败注入点和重置脚本；
- 报告至少运行三次，输出均值、标准差和失败类型。

### 6.2 P1：P0 稳定后的产品增强

- 已完成任务保存为模板；
- 无依赖 R0/R1 节点的有限并行；
- 计划自然语言修改和变更 Diff；
- 多人审批与审批策略组；
- 定时任务；
- 连接器健康度、限流和熔断；
- 每租户预算、配额和并发公平调度；
- WorkArena/WebArena-Verified 小规模适配；
- 国际化和基础无障碍支持。

## 7. V2 总体架构

```text
┌────────────────────────────────────────────────────────────┐
│ Next.js Web                                                │
│ Create │ Plan │ Approval │ Live Timeline │ Evidence │ Replay│
└────────────────────────────┬───────────────────────────────┘
                             │ REST + SSE
┌────────────────────────────▼───────────────────────────────┐
│ FastAPI Gateway                                            │
│ OIDC │ Tenant Context │ Task API │ Upload │ Signed Artifact │
└───────────────┬───────────────────────────┬────────────────┘
                │                           │
┌───────────────▼──────────────┐ ┌──────────▼────────────────┐
│ Temporal Workflow            │ │ Knowledge Service         │
│ plan → execute → verify      │ │ parse → chunk → retrieve  │
│ wait approval / replan       │ │ ACL filter → cite         │
└───────────────┬──────────────┘ └──────────┬────────────────┘
                │                           │
┌───────────────▼───────────────────────────▼────────────────┐
│ Tool Runtime                                               │
│ Policy │ Router │ Credential Proxy │ API/MCP │ Browser      │
│ Idempotency │ Outbox │ Verifier │ Redactor                 │
└───────────────┬────────────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────┐
│ PostgreSQL/pgvector │ MinIO │ Temporal │ OTel │ Prometheus  │
└────────────────────────────────────────────────────────────┘
```

### 7.1 服务边界

V2 保持模块化单体，不拆微服务。API、Worker 和 Web 是独立进程，但 Python 业务模块仍在同一仓库和版本中。只有出现独立扩缩容、权限隔离或团队边界时，才拆 Knowledge 或 Browser Runtime。

这样既能展示清晰边界，也避免为面试项目制造无收益的分布式复杂度。

## 8. 核心模块修改设计

### 8.1 数据持久化

新增主要表：

| 表 | 关键约束 |
| --- | --- |
| `task_runs` | `(tenant_id, id)`；状态与乐观锁版本 |
| `task_steps` | `(task_id, step_id)` 唯一；保存不可变计划快照 |
| `approvals` | 参数哈希、计划版本、过期时间、决策人 |
| `action_ledger` | `idempotency_key` 全局唯一；远端对象 ID |
| `verifications` | 一次执行可有多次验证尝试 |
| `artifacts` | 只存元数据、哈希、对象存储 URI |
| `checkpoints` | Workflow run、计划版本和已完成节点 |
| `documents` | tenant、ACL、版本、删除标记 |
| `document_chunks` | 来源位置、全文索引、向量与 ACL |
| `outbox_events` | 与业务事务同时写入，异步发布 |
| `model_calls` | 模型、Prompt 版本、Token、成本、延迟 |

事务边界：

- 审批决策与任务状态变更同一事务；
- Action Ledger 预占与动作状态变更使用唯一幂等键；
- 远端成功后写入 Ledger、Verification 和 Checkpoint；
- Event 通过 Outbox 与业务事实同事务落库；
- Repository 每个查询都显式接收 `TenantContext`，RLS 作为第二道防线。

### 8.2 Temporal 工作流

```text
TaskWorkflow
  1. plan_activity
  2. validate_plan_activity
  3. for each ready step
     a. policy_activity
     b. preview_activity
     c. wait approval update when required
     d. reserve_action_activity
     e. execute_activity
     f. verify_activity
     g. checkpoint_activity
  4. replan_activity when retryable and within budget
  5. finalize_activity
```

约束：

- Workflow 代码只做确定性编排，不直接访问网络、数据库或模型；
- 所有 I/O 放在 Activity；
- Activity 采用 at-least-once 语义设计，外部写入必须幂等；
- 超时后优先 `verify/lookup`，不能直接切换通道重试；
- 审批使用 Update 验证参数哈希后才接收；
- Worker 版本升级使用兼容的 Workflow 版本策略；
- Event History 过大时 Continue-As-New，并保存业务检查点引用。

### 8.3 ModelGateway 与 Planner

统一请求：

```python
class ModelGateway(Protocol):
    async def generate_structured(
        self,
        *,
        operation: str,
        messages: list[Message],
        output_schema: type[BaseModel],
        budget: ModelBudget,
        trace_context: TraceContext,
    ) -> StructuredModelResult: ...
```

必须实现：

- provider 超时、429、5xx 和 schema failure 分类；
- 请求级 deadline 与最大重试；
- Token 和费用预算硬限制；
- Prompt 模板版本化；
- 内容与指令分区，检索内容使用不可信数据标签；
- 可配置禁用原始 Prompt/Completion 的遥测记录；
- 模型不可直接决定风险、审批、权限和域名白名单。

Planner 质量通过以下方式保证：

1. Capability Registry 只暴露当前用户已授权能力；
2. 模型输出严格 Pydantic Schema；
3. 规则层校验 DAG、预算、风险、验证和能力；
4. 相同输入保存计划快照，便于回归；
5. 失败时优先修复 Schema，不能绕过规则；
6. 周报主流程保留确定性模板作为降级。

### 8.4 Executor 与幂等

动作状态：

```text
RESERVED → DISPATCHED → CONFIRMED
                 ├── FAILED
                 └── UNKNOWN → VERIFYING → CONFIRMED / MANUAL_REVIEW
```

执行前在数据库以幂等键预占。远端支持原生幂等键时直接透传；不支持时使用业务唯一字段、发送前查询和发送后远端 ID 共同去重。`UNKNOWN` 不得被当作失败直接重试。

对于邮件，建议在发送内容中加入不可见的任务关联头或 provider 支持的 client request ID；若 provider 不支持，则使用受控时间窗口内的收件人、主题和正文哈希查询。查询仍不确定时进入人工处理。

### 8.5 Verifier

Verifier 与 Executor 解耦，优先级如下：

1. 本地确定性结果和文件哈希；
2. 远端 API 重新查询；
3. 网络响应或事件回执；
4. DOM/Accessibility 状态；
5. 截图；
6. 模型语义判断。

每条证据包含：来源、采集时间、对象 ID、内容哈希、Artifact URI、验证规则版本和脱敏状态。模型判断只能产生 `INCONCLUSIVE` 或建议，不能单独确认高风险副作用成功。

### 8.6 Replanner

失败分类：

| 类型 | 是否自动处理 | 策略 |
| --- | --- | --- |
| 429/网络抖动 | 是 | 指数退避，不改变参数 |
| 页面元素漂移 | 是 | 重建观察，最多两次 |
| 参数格式错误 | 是 | 只修改当前未完成节点 |
| 权限不足 | 否 | 停止并提示重新授权 |
| 结果未知 | 否直接重试 | 先远端核对，再人工处理 |
| 目标已变化 | 条件处理 | 局部重规划，参数变化则重新审批 |
| Prompt Injection | 否 | 阻断、记录安全事件 |
| 不可恢复业务错误 | 否 | 失败并生成诊断 |

Replanner 输入只包含失败节点、必要依赖、最近证据和预算，不重新生成整个计划。已成功节点不可修改或删除。

## 9. 安全设计

### 9.1 威胁模型

V2 安全测试映射 OWASP Agentic Top 10 中与本项目最相关的风险：目标劫持、工具滥用、身份与权限滥用、Agent 供应链、意外代码执行、记忆/上下文投毒、级联失败和对人类信任的利用。

重点控制：

- 网页、邮件、文档和工具结果永远是数据，不能申请权限或改写策略；
- 工具参数使用 allowlist Schema，拒绝额外字段；
- Credential Proxy 在工具边界注入凭证，模型不可见；
- OAuth scope 与连接器 capability 一一映射；
- 浏览器网络出口和文件目录白名单；
- Artifact 使用 tenant 前缀、内容哈希和短期签名 URL；
- Prompt、日志、Span、错误统一脱敏；
- 审批展示参数 Diff，防止通过冗长文本隐藏影响；
- 批量动作设置数量上限和二次确认策略；
- 依赖锁定、SBOM、漏洞扫描和第三方许可证检查。

### 9.2 身份与授权

- 开发环境提供固定测试身份；
- V2 演示环境接入 OIDC；
- API 只接受网关签发的 JWT，不接受任意客户端租户头；
- RBAC 至少包含 `member`、`approver`、`tenant_admin`；
- 审批人不能审批超出自身权限的工具；
- PostgreSQL RLS 默认拒绝，没有匹配 policy 时不可见；
- 每次授权和拒绝都写审计事件。

### 9.3 风险治理

参考 NIST AI RMF 的 Govern、Map、Measure、Manage：

- Govern：定义所有者、策略版本、审批责任和数据保留；
- Map：为每类任务记录用户、数据、工具、影响与失败模式；
- Measure：运行评测、安全测试、红队任务和用户反馈分析；
- Manage：按风险接受、降低、转移或禁止能力，并记录决策。

## 10. 用户体验修改

### 10.1 首次使用

首次进入不展示空白聊天框，而是展示三个可理解的任务模板：生成周报、创建会议、从材料创建跟进任务。模板显示会访问哪些系统、是否包含外部写入和预计用时。

### 10.2 计划确认

计划用业务语言呈现，技术 capability 放在详情中。用户能看到：

- 将读取哪些来源；
- 将创建或发送什么；
- 哪些步骤需要审批；
- 每步如何验证；
- 预计 Token、费用和最长执行时间；
- 系统没有权限完成的部分。

### 10.3 审批体验

审批面板不能只显示 JSON。邮件要以邮件预览呈现，日程要以日历卡片呈现，任务要展示负责人、截止时间和可见范围。参数变更以 Diff 标出。审批过期、计划版本变化或通道变化时明确解释为什么需要重新审批。

### 10.4 失败与恢复

错误页回答三个问题：

1. 哪一步失败；
2. 已经产生了什么影响；
3. 用户现在可以安全地做什么。

提供“重试只读检查”“重新授权”“修改参数后重新审批”“导出诊断”四类受控操作，不提供含义模糊的“重新运行全部”。

### 10.5 结果页

结果页首先显示业务结果，其次显示技术轨迹：周报可下载、已创建任务可打开、已发送邮件可查看远端 ID。每个结论都能跳转到来源片段。

## 11. API V2 设计

保留现有路径并增加异步语义：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/v2/tasks` | 创建任务，返回 `202` 和 task ID |
| `GET` | `/v2/tasks/{id}` | 当前计划、状态、预算和摘要 |
| `GET` | `/v2/tasks/{id}/events` | 支持 `Last-Event-ID` 的 SSE |
| `POST` | `/v2/tasks/{id}/approvals/{step}` | 提交参数哈希和审批决定 |
| `POST` | `/v2/tasks/{id}/pause` | 请求安全暂停 |
| `POST` | `/v2/tasks/{id}/resume` | 从检查点恢复 |
| `POST` | `/v2/tasks/{id}/cancel` | 取消未调度动作 |
| `GET` | `/v2/tasks/{id}/artifacts` | 分页获取 Artifact 元数据 |
| `GET` | `/v2/tasks/{id}/replay` | 分页审计回放 |
| `POST` | `/v2/documents/uploads` | 获取上传 URL |
| `POST` | `/v2/documents/{id}/ingest` | 启动解析和索引 |
| `GET` | `/v2/capabilities` | 当前身份可用能力与授权状态 |
| `GET` | `/v2/metrics/tasks/{id}` | 单任务 Token、成本和延迟摘要 |

所有写接口支持 `Idempotency-Key`。错误统一为 RFC 9457 Problem Details 风格，包含可公开的错误码、是否可重试和建议动作，不包含内部凭证或堆栈。

## 12. 可观测性、SLO 与评测

### 12.1 Trace

```text
agent.run
├── knowledge.ingest / knowledge.retrieve
├── planner.generate
├── plan.validate
├── workflow.wait_approval
├── step.execute
│   ├── policy.evaluate
│   ├── tool.preview
│   ├── tool.execute
│   └── verifier.check
├── replanner.generate
└── checkpoint.persist
```

采用 OpenTelemetry 通用和 GenAI 语义约定。工具参数、结果、Prompt 和 Completion 可能包含敏感信息，因此默认只记录哈希、大小、类型、token usage 和脱敏摘要，原文仅在显式调试模式且经过授权时短期保存。

### 12.2 SLO 目标

以下均为 V2 目标，不是当前结果：

| 指标 | 目标 |
| --- | ---: |
| API 非流式请求可用性 | ≥ 99.5%（演示环境按运行窗口统计） |
| `POST /tasks` P95 | < 500 ms，不含异步规划 |
| SSE 事件投递延迟 P95 | < 2 s |
| 非模型内部步骤 P95 | < 1 s |
| Worker 重启恢复成功率 | 100% 固定恢复任务 |
| 未审批 R2/R3 成功动作 | 0 |
| 重复副作用 | 0 |
| Artifact/Trace 敏感凭证泄露 | 0 |

### 12.3 评测指标

- Task Success Rate；
- Step Verification Pass Rate；
- Planner Valid-on-First-Try Rate；
- Recovery Rate；
- Unauthorized Action Count；
- Duplicate Side Effect Count；
- Token/Cost per Success；
- End-to-end P50/P95；
- Approval Precision/Recall；
- 用户完成时间节省；
- 用户对结果和证据的满意度。

评测报告必须同时展示失败样本，不得只选最佳运行。模型、Prompt、任务集、随机参数和环境版本全部固定并记录。

## 13. 测试策略

### 13.1 测试金字塔

- 单元测试：DAG、状态机、策略、哈希、脱敏、Diff、预算；
- 属性测试：随机 DAG、参数顺序、状态转换不变量；
- Adapter 合同测试：Fake 与真实连接器运行同一套行为规范；
- 数据库集成测试：事务、唯一约束、RLS、迁移升级/回滚；
- Temporal 测试：虚拟时间、重试、Signal/Update、Worker 重启；
- API 测试：认证、租户、幂等、SSE 续传、Problem Details；
- E2E：浏览器完成创建、审批、恢复和回放；
- 安全测试：Prompt Injection、路径穿越、SSRF、额外收件人、旧审批重放；
- 故障注入：远端超时但成功、数据库短暂不可用、Worker kill；
- 负载测试：任务创建、事件订阅和 Worker 队列延迟。

### 13.2 CI 门禁

每个 Pull Request 必须通过：

- 格式化、lint、类型检查；
- 单元与集成测试；
- 数据库迁移检查；
- 依赖漏洞与 secret scan；
- Docker build；
- 关键安全不变量测试；
- 测试覆盖率不低于已冻结基线，核心 policy/runtime 分支覆盖率目标 ≥ 90%。

夜间任务运行 24 条固定评测和真实沙箱连接器 smoke test。

## 14. 部署设计

### 14.1 本地

Docker Compose 服务：

- `api`；
- `worker`；
- `web`；
- `postgres` + pgvector；
- `temporal` + UI；
- `minio`；
- `otel-collector`；
- `jaeger`；
- `prometheus` + `grafana`；
- Fake enterprise services。

提供 `make dev`、`make test`、`make eval`、`make reset-demo` 四个稳定入口。

### 14.2 演示环境

V2 面试演示不必上 Kubernetes，但需要提供 Kubernetes manifests 或 Helm chart 作为扩展证明。实际部署可先使用单节点容器平台，重点证明：配置与密钥分离、数据库迁移、滚动升级、健康检查、备份恢复和可观测性。

## 15. 六周实施路线图

### 第 1 周：持久化与工程基线

- SQLAlchemy、Alembic、PostgreSQL Schema；
- Repository 替换与 RLS；
- Ruff、mypy、coverage、CI；
- Docker Compose 基础依赖；
- ADR-001：为何 V2 使用模块化单体。

退出条件：API 重启后任务仍可读取，跨租户测试通过，CI 全绿。

### 第 2 周：Temporal 与可靠执行

- Workflow/Activity 拆分；
- Approval Update、Pause/Cancel Signal、Query；
- Action Ledger 数据库化；
- Worker kill、超时和重复投递测试；
- ADR-002：Temporal 与数据库任务队列的取舍。

退出条件：审批等待期间重启 Worker，恢复后不重复执行已完成动作。

### 第 3 周：模型 Planner 与知识管线

- ModelGateway 与一个模型 provider；
- Structured Planner、repair、fallback；
- PDF/DOCX/XLSX/CSV 解析；
- FTS + pgvector 检索与来源引用；
- Prompt Injection 数据边界测试。

退出条件：给定三类附件可以生成合法计划和带来源的周报。

### 第 4 周：真实连接器与 Browser Adapter

- Gmail/Calendar 沙箱连接器；
- preview/execute/verify/lookup 合同；
- Playwright 固定站点执行；
- 通道路由与降级规则；
- 超时但远端成功的故障注入。

退出条件：真实沙箱发送动作必须审批，重复副作用为 0。

### 第 5 周：工作台与可观测性

- Next.js 任务、审批、恢复、回放页面；
- SSE 续传；
- OpenTelemetry、Prometheus、Grafana；
- 脱敏和 Artifact 签名访问；
- 用户可用性走查。

退出条件：非开发者可独立完成主 Demo 并理解每个审批影响。

### 第 6 周：评测、性能与面试交付

- 24 条固定任务与重置器；
- 运行三轮基线并分类失败；
- 修复主要失败模式；
- 负载测试和 SLO 报告；
- 架构图、ADR、演示视频、运行手册和简历描述。

退出条件：所有 V2 完成定义满足，报告明确区分目标和实测结果。

## 16. V2 完成定义

只有以下条件全部满足才称为 V2：

- 一条真实跨系统办公流程从输入到验证完整可用；
- PostgreSQL 和 Temporal 中的事实与控制流可在重启后恢复；
- 模型 Planner 有结构化校验、fallback 和可复现测试；
- Fake 与真实连接器通过同一套合同测试；
- R2 无审批执行数、R3 执行数、重复副作用数均为 0；
- 文档与知识结果都带可核对来源；
- 工作台完整覆盖创建、审批、恢复、结果和回放；
- 24 条任务运行三次并生成可公开报告；
- Trace 能定位一次失败经过，且不泄露凭证；
- Docker Compose 一条命令启动，CI 全部通过；
- README、API、数据模型、ADR、部署、运行手册和 Demo 齐全。

## 17. 面试展示方案

### 17.1 三分钟演示

1. 上传项目材料并提交“生成并发送周报”；
2. 展示模型生成的 DAG、来源和风险；
3. 执行到创建任务审批点；
4. kill Worker，再启动并展示状态恢复；
5. 审批创建任务和发送邮件；
6. 打开远端对象与验证证据；
7. 打开 Trace 和评测面板。

### 17.2 深挖主题

准备两个可以讲 10 分钟的主题：

- **可靠副作用**：at-least-once、幂等键、Action Ledger、UNKNOWN 状态、远端核对和审批绑定；
- **受控 Agent**：模型负责建议，规则负责权限；Planner/Executor/Verifier/Replanner 如何解耦。

每个主题都应包含：问题、错误方案、最终方案、取舍、测试、真实指标和下一步。

### 17.3 简历表述原则

只写已测量事实，例如：

> 设计并实现可恢复的跨系统办公 Agent，基于 Temporal/PostgreSQL 管理长任务与审批，通过参数哈希和幂等账本将固定安全任务集中的未授权写入与重复副作用降为 0；建立 24 条可复现任务集并报告成功率、P95 延迟和每成功任务成本。

其中数字必须在 V2 完成后替换为真实结果。不要写“支持海量并发”“生产级”“准确率 99%”等未验证描述。

## 18. 风险与取舍

| 风险 | 取舍 |
| --- | --- |
| 六周范围仍大 | 真实连接器只做一套生态，Browser 只做一个站点 |
| Temporal 学习成本 | 第 2 周必须完成最小闭环，否则回退 DB queue，但保留 ADR |
| OAuth 审核耗时 | 只用测试账号和沙箱，不承诺公开多租户授权 |
| pgvector 效果有限 | 先冻结检索基线，再决定 reranker，不盲目堆模型 |
| 模型输出不稳定 | 模板 fallback 保证主 Demo，模型能力用评测单独衡量 |
| UI 工作量影响后端 | 只做四个核心页面，使用成熟组件库 |
| 评测集制作耗时 | 先 12 条黄金任务，再扩展到 24 条，不先做公开 Benchmark |
| 安全功能难以完全覆盖 | 明确威胁模型和禁止能力，不宣传绝对安全 |

## 19. 建议的下一步

第一项实现应是“PostgreSQL 持久化 + CI”，而不是接模型。原因是当前安全闭环已经存在，但所有事实都在内存；先把 Task、Approval、Ledger、Verification 和 Checkpoint 变成可恢复事实，后续 Temporal、真实连接器和模型才有可靠落点。

建议下一次开发任务拆分为：

1. 创建 PostgreSQL Compose、SQLAlchemy 模型和 Alembic 初始迁移；
2. 用 Repository Protocol 替换当前具体内存类型；
3. 保留 InMemory Repository 作为单元测试实现；
4. 增加 PostgreSQL 集成测试、RLS 跨租户测试和重启恢复测试；
5. 更新 README 和架构图，记录迁移前后取舍。

## 20. 参考资料

- [腾讯招聘：混元 Agent 强化学习框架工程师](https://careers.tencent.com/jobdesc.html?postId=2061654749727600640)：Agent 框架、异步并发、上下文、Trace、评估、Kubernetes 与工程稳定性要求。
- [腾讯招聘：AI 协作工具与 WorkBuddy 相关岗位](https://careers.tencent.com/jobdesc.html?postId=2077641607687090176)：办公 Agent、全栈、任务调度、沙箱、高并发和高可靠要求。
- [Google Careers：Software Engineer, IO Experience](https://www.google.com/about/careers/applications/jobs/results/75462689798660806-software-engineer-io-experience)：分布式系统、可观测性、容器化、可靠性和可运维性要求。
- [Temporal Durable AI](https://docs.temporal.io/ai)：长任务、人工审批等待、崩溃恢复和隔离重试模式。
- [Temporal Workflow message passing](https://docs.temporal.io/encyclopedia/workflow-message-passing)：Signal、Query、Update 的语义和选择。
- [OpenTelemetry GenAI attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)：模型与工具调用属性及敏感信息告警。
- [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)：Agent 目标劫持、工具滥用、身份权限、供应链和上下文投毒等风险。
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)：可信 AI 风险治理与 GenAI Profile。
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)：行级安全策略与默认拒绝模型。

