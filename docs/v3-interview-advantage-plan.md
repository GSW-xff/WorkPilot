# WorkPilot V3 后续修改补充方案：面试竞争力与产品完整性

- 文档版本：1.0
- 基线日期：2026-10-10
- 代码基线：`471a3cf feat: add durable Temporal task orchestration`
- 适用目标：Agent 应用工程、Agent Harness、AI 平台后端、LLM 应用全栈、AI 基础设施岗位

## 0. 阅读说明

本文只把仓库中已经存在并且有代码或测试支撑的能力写为“已实现”。所有成功率、延迟、成本和安全数字，如果尚未跑出结果，一律标记为“目标值”或“验收门槛”，不能直接写进简历。

本文的核心判断是：互联网大厂不会因为项目安装了很多框架就认可项目。真正能形成面试优势的是下面这条证据链：

```text
真实用户问题
    → 可解释的 Agent 架构
    → 对失败、安全和成本有明确约束
    → 有真实集成和故障场景
    → 有可重复的评测、Trace 和实测数据
    → 能说明取舍，并能被面试官现场验证
```

## 1. 结论先行

### 1.1 当前项目已经有价值的部分

WorkPilot 已经不是一个只有 Prompt 和聊天框的 Demo。它具备：

- 确定性的 Planner–Executor–Verifier 执行闭环；
- DAG 校验、风险分级、人工审批、参数哈希绑定和高危动作拒绝；
- Action Ledger、稳定幂等键、UNKNOWN 动作恢复和远端状态验证；
- PostgreSQL 持久化、Alembic、乐观锁、RLS 和事务 Outbox；
- Temporal Workflow/Activity、审批 Update、控制 Signal 和独立 Worker；
- Timeline、Checkpoint、Artifact、SSE 和可回放任务事实；
- Docker Compose、GitHub Actions、Ruff、mypy、pytest 和覆盖率门禁。

这些能力能够支撑“安全、可恢复的企业办公 Agent”这一项目叙事，也是当前仓库最有区别度的部分。

### 1.2 当前项目不能夸大的部分

以下能力目前没有完成，不能在简历中写成已经实现：

- Planner 仍然是固定模板，没有真实 LLM、结构化生成、上下文压缩和模型降级；
- 连接器全部是 Fake，没有真实 OAuth、限流、Webhook 和 SaaS 契约测试；
- Temporal 只有单元级验证，没有真实测试服务、Worker kill/restart 和历史回放验收；
- PostgreSQL RLS 已有迁移，但自动化测试主要运行在 SQLite，没有真实 PostgreSQL 对抗测试；
- Outbox 有表和读取接口，没有独立发布器、消费端去重和积压监控；
- 没有固定 Agent 任务集、基线对比、模型评测报告和统计置信度；
- 没有 OpenTelemetry、Prometheus/Grafana、Token/成本和队列延迟指标；
- 没有真实文件知识库、引用定位、检索评测、MCP 或 Browser Agent；
- 身份仍来自请求头，没有 OIDC、RBAC/ABAC、Secret Store 和生产级审计保留；
- 前端仍是静态单页，没有登录、连接器管理、任务列表、恢复中心和评测面板。

### 1.3 最值得优先投入的五项成果

按照“面试区分度 ÷ 实现成本”排序，建议优先完成：

1. **真实 ModelGateway + 结构化 Planner + Context Engineering**；
2. **固定评测集 + Trace grading + 回归报告**；
3. **Temporal 真实故障恢复 + 幂等副作用故障注入**；
4. **一个真实企业连接器 + OAuth + Secret 隔离**；
5. **OpenTelemetry 全链路观测 + 成本/延迟/SLO 仪表盘**。

完成这五项后，项目才能从“工程化 MVP”进入“有生产思维和实验依据的 Agent 项目”。

## 2. 当前功能完整盘点

### 2.1 用户可见功能

| 功能 | 当前状态 | 已有证据 | 当前限制 |
| --- | --- | --- | --- |
| 自然语言创建任务 | 已实现 | `POST /v1/tasks` | 只进入固定周报模板 |
| 查看任务 DAG | 已实现 | Web Console、TaskPlan | 不支持用户修改计划和 Plan Diff |
| 执行任务 | 已实现 | Runtime、Temporal Worker | 真实外部系统尚未接入 |
| 审批/拒绝 | 已实现 | 参数预览、哈希、Workflow Update | 没有审批 Inbox、超时和代理审批 |
| 暂停/恢复/取消 | 已实现 | 状态机、Temporal Signal | 缺取消传播和长 Activity heartbeat 实测 |
| 时间线和回放 | 已实现 | Timeline、Replay API | 缺 Trace 跨服务关联和搜索 |
| Artifact 查看 | 基础实现 | Artifact API | 只有 JSON 元数据，没有对象存储和文件预览 |
| 知识文档写入 | 基础实现 | Fake Adapter API | 没有解析、切块、向量检索和引用 |
| 自动刷新状态 | 已实现 | Web Console 轮询 | 没有 WebSocket/SSE 断线续传体验 |
| 多租户 | 基础实现 | tenant Repository、RLS 迁移 | 没有真实身份、组织和连接器 ACL |

### 2.2 Agent 执行内核

| 能力 | 当前实现 | 专业价值 |
| --- | --- | --- |
| 计划表示 | Pydantic TaskPlan + PlanStep | 强类型、可审计、可持久化 |
| DAG 校验 | 唯一节点、依赖存在、拓扑排序、无环、步骤上限 | 阻止模型产生不可执行计划 |
| 能力路由 | CapabilityRegistry + ToolAdapter Protocol | 连接器可替换，可做合同测试 |
| 风险控制 | R0–R3，能力固定风险与计划风险取高值 | 风险不交给模型自行决定 |
| 审批绑定 | 参数规范化 SHA-256 + plan version | 防止审批后偷换参数 |
| 幂等 | tenant/task/step/action/parameters 生成稳定键 | 支撑 Activity 至少一次投递 |
| 副作用恢复 | RESERVED、UNKNOWN、lookup-before-retry | 处理“远端成功但响应丢失” |
| 结果验证 | Execute 后由 Adapter 独立读取状态 | 不把工具返回 success 当作事实 |
| 检查点 | 每个安全边界和成功节点记录 | 支撑恢复、审计和故障解释 |

### 2.3 数据与一致性

- SQLAlchemy 2 Repository 同时支持内存、SQLite 和 PostgreSQL；
- Alembic 创建 Task、Step、Approval、Ledger、Verification、Artifact、Timeline、Checkpoint 和 Outbox 表；
- Repository 用版本号进行 compare-and-swap，拒绝 stale writer；
- PostgreSQL 迁移启用并强制 RLS，应用事务设置 tenant context；
- 任务事实和新增 Timeline Event 在同一事务写入 Outbox；
- API、Worker 和持久层共享相同领域模型。

### 2.4 长任务与恢复

- Temporal Workflow 保存控制状态，Activity 承载数据库和连接器 I/O；
- 审批使用 Workflow Update，暂停、恢复和取消使用 Signal；
- Workflow ID 包含租户和任务，避免跨租户共享句柄；
- Activity 设置超时和有限指数退避；
- 未配置 Temporal 时保留直连模式，方便快速开发；
- Docker Compose 已编排 PostgreSQL、Temporal、API 和 Worker。

### 2.5 工程质量基线

- Python 3.12+、uv 锁定依赖；
- Ruff 静态规范检查；
- mypy 类型检查；
- pytest 自动化测试和 85% 覆盖率门禁；
- GitHub Actions 在 push 和 pull request 上执行质量门禁；
- Dockerfile 与 Compose 支持可复现本地环境；
- ADR 记录 Temporal 选型与当前验证边界。

当前基线为 44 项自动化测试；覆盖率应以最新 CI 报告为准，不在简历中手写长期不更新的数字。

## 3. 当前使用的主流工具和技术

### 3.1 已经使用且有实际代码的技术

| 工具/技术 | 仓库中的用途 | 能证明什么 | 面试时应讲的取舍 |
| --- | --- | --- | --- |
| FastAPI | REST、SSE、生命周期管理 | Python API 工程能力 | 当前 Repository 为同步 I/O，后续需处理事件循环阻塞 |
| Pydantic 2 | 请求、计划、动作、审批和结果模型 | Schema-first 和边界校验 | Schema 校验不能替代业务策略 |
| SQLAlchemy 2 | Repository 和领域模型持久化 | 数据建模、事务和抽象能力 | 当前保存子表采用整体替换，规模化前要改增量写 |
| PostgreSQL | 任务事实、RLS、Outbox | 事务、一致性和租户隔离 | 必须补真实 PostgreSQL 集成测试 |
| Alembic | 数据库迁移 | 可演进 Schema | 必须演练 upgrade/downgrade 和兼容发布 |
| Temporal | 长任务、审批等待、重试和控制流 | 分布式状态机、可靠执行 | Temporal 不等于 exactly-once，仍需 Ledger 和远端查询 |
| Docker/Compose | 本地多服务环境 | 容器化和环境复现 | Compose 不是生产级调度和高可用证明 |
| GitHub Actions | CI 质量门禁 | 自动化交付习惯 | 还缺安全扫描、镜像构建和部署门禁 |
| Ruff/mypy/pytest | 规范、类型和测试 | 工程质量和可维护性 | 覆盖率不是效果评测，也不能替代故障测试 |
| SSE | 任务事件推送 | 长任务交互基础 | 还缺 Last-Event-ID、断线续传和背压 |

### 3.2 为什么这些技术与岗位方向匹配

当前官方岗位信号表明，Agent 岗位同时要求模型链路与传统工程能力：

- 腾讯 WorkBuddy Agent Harness 岗位强调 Context Engineering、Programmatic Tool Calling、MCP、Memory、Long-Horizon 和 Evaluation；
- 腾讯混元 Agent 框架岗位强调 Python asyncio、并发、模型/工具调用、上下文管理、Trace、评估、Kubernetes、性能和稳定性；
- 腾讯 AI 数据工程岗位明确涉及 API、MCP、CLI、Skill、Workflow、异步任务、服务治理和可观测性；
- OpenAI Agent Infrastructure 岗位列出 FastAPI、gRPC、Terraform、容器编排、沙箱和大规模可靠系统；
- Apple Agentic Evaluation 岗位强调评测平台、LLM-as-judge、人类一致性、系统测试、调试和监控。

因此，WorkPilot 当前的 FastAPI、PostgreSQL、Temporal、容器化和安全执行方向是正确的；真正缺少的不是再装一个 Agent 框架，而是把模型、评测、可观测性、真实集成和故障证据补齐。

## 4. 当前面试竞争力评估

以下评分只用于安排优先级，不是招聘结果预测。

| 维度 | 证据成熟度（5 分） | 当前优势 | 最大缺口 |
| --- | ---: | --- | --- |
| 产品问题与边界 | 4.0 | 办公 Agent 场景、风险和闭环明确 | 无真实用户访谈与留存数据 |
| Agent 架构 | 3.0 | Planner/Executor/Verifier、DAG、工具抽象 | 没有真实模型和 Context Engineering |
| 后端工程 | 4.0 | API、事务、持久化、Outbox、乐观锁 | 同步 DB、整体子表替换、无背压限流 |
| 分布式可靠性 | 3.5 | Temporal、Ledger、UNKNOWN 恢复 | 无真实 Worker 故障和历史回放测试 |
| 安全 | 4.0 | 风险策略、审批绑定、RLS、脱敏 | 无 OIDC、Secret Store、Agent 红队 |
| 评测 | 1.0 | 有确定性单元测试 | 无 Agent 数据集、基线、grader 和报告 |
| 可观测性 | 1.5 | Timeline、Checkpoint、Artifact | 无 OTel、Token/成本、SLO 和告警 |
| 真实系统集成 | 1.0 | Adapter Protocol | 全部为 Fake |
| RAG/数据 | 1.0 | tenant-aware Fake 文档 | 无解析、检索、引用和评测 |
| Browser/MCP | 0.5 | Channel 抽象已预留 | 没有真实实现 |
| 前端与用户体验 | 2.5 | 可运行工作台和审批 | 缺登录、任务列表、连接器和恢复中心 |
| 部署与运维 | 2.5 | Docker Compose、CI | 无 K8s、IaC、SLO、备份恢复和安全供应链 |
| 技术表达 | 4.0 | README、设计文档、ADR | 无 Benchmark、故障报告和 Demo 视频 |

## 5. V3 产品定位

### 5.1 一句话定位

> WorkPilot 是一个面向企业办公流程的安全执行 Agent：把自然语言目标转为可验证 DAG，通过持久工作流、安全策略和人工审批调用真实企业工具，并用 Trace、评测和 Artifact 证明结果。

### 5.2 目标用户

- 需要跨邮件、日历、任务和文档系统完成重复流程的知识工作者；
- 需要审批高风险 Agent 动作的团队负责人；
- 需要审计、恢复和评估 Agent 运行质量的平台管理员；
- 希望接入自有工具的企业开发者。

### 5.3 V3 非目标

- 不做无边界的“万能自主 Agent”；
- 不为了关键词堆砌多 Agent；
- 不在缺少评测数据时做微调；
- 不一次接入十个浅层连接器；
- 不允许模型直接决定权限、风险等级或 Secret；
- 不宣称 exactly-once，只证明在定义的失败模型下没有重复业务副作用。

## 6. V3 目标架构

```text
┌─────────────────────────────────────────────────────────────┐
│ Next.js/React Console                                       │
│ 任务列表 | 计划 Diff | 审批 Inbox | 恢复中心 | Trace | Eval │
└──────────────────────────┬──────────────────────────────────┘
                           │ OIDC / REST / SSE
┌──────────────────────────▼──────────────────────────────────┐
│ FastAPI Control Plane                                      │
│ AuthN/AuthZ | Rate Limit | Task API | Connector API         │
└────────────┬──────────────────────────────┬──────────────────┘
             │                              │
┌────────────▼──────────────┐  ┌────────────▼─────────────────┐
│ Temporal                  │  │ Evaluation Service           │
│ Workflow/Activity/Worker  │  │ Dataset/Runner/Grader/Report │
└────────────┬──────────────┘  └────────────┬─────────────────┘
             │                              │
┌────────────▼────────────────────────────────────────────────┐
│ Agent Runtime                                               │
│ ModelGateway | ContextBuilder | Planner | Policy | Verifier  │
│ Budget | Prompt Version | Memory Policy | Adapter Router     │
└───────┬──────────────────┬───────────────────┬───────────────┘
        │                  │                   │
┌───────▼──────┐  ┌────────▼────────┐  ┌──────▼──────────────┐
│ API Adapter  │  │ MCP Adapter     │  │ Browser Adapter     │
│ OAuth/Webhook│  │ OAuth/Tool ACL  │  │ Playwright/Sandbox  │
└───────┬──────┘  └────────┬────────┘  └──────┬──────────────┘
        └──────────────────┴───────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ PostgreSQL + pgvector | Object Storage | Secret Store       │
│ Task Facts | Documents | Citations | Eval Runs | Audit      │
└──────────────────────────┬──────────────────────────────────┘
                           │ OTLP
┌──────────────────────────▼──────────────────────────────────┐
│ OTel Collector | Tempo/Jaeger | Prometheus | Grafana        │
└─────────────────────────────────────────────────────────────┘
```

原则：先保持模块化单体和独立 Worker，不提前拆微服务。只有在独立扩缩容、隔离故障或团队边界确实存在时再拆服务。

## 7. P0：真实模型、结构化规划与上下文工程

### 7.1 ModelGateway

新增统一的 `ModelGateway` Protocol，至少提供：

```python
async def generate_structured(
    *,
    messages: list[Message],
    output_schema: type[BaseModel],
    model_policy: ModelPolicy,
    budget: RunBudget,
    metadata: dict[str, str],
) -> ModelResponse: ...
```

必须记录：

- provider、model、request id；
- prompt version 和 schema version；
- 输入/输出 Token；
- 首 Token 与总延迟；
- 重试、错误类型、fallback 原因；
- 缓存命中；
- 估算成本；
- trace_id、tenant_id、task_id，但默认不记录敏感正文。

实现一个真实云模型 Provider 和一个 Deterministic Fake Provider。业务层不得直接 import 厂商 SDK，避免模型切换污染 Planner。

### 7.2 结构化 Planner

- 模型只产生 `TaskPlan` 候选，不直接执行工具；
- Pydantic JSON Schema 校验失败后最多进行一次结构修复；
- DAG、能力、风险、收件人和预算仍由确定性代码校验；
- 模型失败、超时或超预算时回退到 `DemoPlanner`；
- 每次计划保存 prompt/model/schema 版本与原始验证错误；
- 重规划必须产生 Plan Diff，已经成功的步骤不可删除或篡改；
- 对每种 Tool 维护少量高质量示例，而不是把全部工具文档塞进上下文。

### 7.3 ContextBuilder

建立显式上下文分层：

1. 系统不变量：安全边界、输出 Schema、预算；
2. 用户目标与组织策略；
3. 可用工具的最小 Schema；
4. 检索得到的可信业务上下文；
5. 外部不可信内容，必须带来源和 trust label；
6. 运行摘要，不把完整历史无限回填。

需要实现：

- Token 预算和优先级裁剪；
- 长历史压缩与可追溯摘要；
- 上下文来源、ACL、时间和可信等级；
- Prompt Injection 标记，不可信文档不能提升权限；
- Tool Search，只把候选工具暴露给模型；
- Prompt 和 Context Snapshot 可重放，但敏感数据受保留策略控制。

### 7.4 为什么暂不直接引入大型 Agent 框架

当前自研 Runtime 的状态、策略和幂等边界已经清晰。V3 可以参考 Agents SDK、LangGraph 等框架的思想，但不应为获得一个依赖名而替换核心 Runtime。只有当框架在评测中明确改善开发效率、恢复能力或工具编排时再引入，并保留对比 ADR。

## 8. P0：Agent 评测与质量飞轮

### 8.1 固定任务集

在仓库新增版本化 `evals/datasets/*.jsonl`，第一版不少于 60 条：

- 20 条正常办公任务；
- 10 条信息缺失或歧义任务；
- 10 条非法计划和未知工具任务；
- 10 条 Prompt Injection/工具误用任务；
- 5 条超预算、超步骤和循环任务；
- 5 条远端超时、限流和部分成功任务。

每条样本应包含：输入、租户策略、可用工具、期望约束、允许的多个正确结果、禁止动作和评分规则。

### 8.2 分层评测指标

| 层级 | 指标 | 说明 |
| --- | --- | --- |
| Planner | schema valid、DAG valid、tool precision/recall | 判断计划是否可执行 |
| Policy | unauthorized write、approval recall、R3 block | 安全指标必须独立于模型评分 |
| Executor | task success、step success、retry recovery | 判断真实完成，而非文本看起来正确 |
| Verifier | false positive/negative、evidence completeness | 防止错误 success |
| Retrieval | Recall@K、nDCG、citation precision | 判断知识依据是否可靠 |
| Product | time-to-value、approval latency、recovery rate | 判断用户是否真正受益 |
| Efficiency | token、cost、P50/P95 latency、tool calls | 判断成本与性能 |

### 8.3 Grader 设计

- 规则可以判断的内容优先使用确定性 grader；
- LLM-as-judge 只评价语言质量、计划合理性等难以编码的维度；
- Judge 使用结构化 rubric，保存模型和 Prompt 版本；
- 至少抽样 20% 结果做人评，报告 Cohen's kappa 或其他一致性指标；
- 每个模型配置至少重复运行 3 次，报告均值、标准差和失败分类；
- 评测集划分开发集和保留集，避免对公开样本过拟合；
- CI 只跑离线确定性 smoke eval；真实模型 eval 采用手动或定时 workflow，设置预算上限。

OpenAI 官方 Agent 评测指南建议先用 Trace 定位工具调用、策略和路由问题，再把稳定标准沉淀为 dataset 与重复 eval run。WorkPilot 应采用同样的“Trace → failure taxonomy → dataset → regression”闭环，但保持 Provider 可替换。

### 8.4 报告产物

每次重要版本生成：

- `eval-report.json`：机器可读结果；
- `eval-report.md`：总体指标、置信区间、失败分类；
- `baseline-comparison.md`：模板 Planner 与模型 Planner 对比；
- 失败样本 Artifact 与 trace 链接；
- 模型、Prompt、代码 commit 和数据集版本。

## 9. P0：Temporal 可靠性与故障证明

### 9.1 必须补齐的测试

- 使用 `temporalio.testing.WorkflowEnvironment` 运行真实 Workflow/Worker 测试；
- 使用 time-skipping 测试审批超时、重试退避和 Timer；
- 在 WAITING_APPROVAL 时杀死 Worker，重启后继续；
- 在 Activity 执行前、远端提交后响应前、验证前分别注入崩溃；
- 重复投递同一 Activity 100 次，确认业务副作用只出现一次；
- 测试 Signal/Update 并发、取消传播和 handler 完成策略；
- 测试 Workflow 版本升级、历史 replay 和不兼容变更检测；
- PostgreSQL 与 Temporal 同时短暂不可用时验证恢复顺序。

### 9.2 Runtime 需要修改的部分

- 长 Activity 增加 heartbeat 和 heartbeat details；
- 为重试异常建立明确分类：retryable、non-retryable、unknown；
- 连接器遵守 deadline 和 cancellation；
- Action Ledger 增加 attempt、last_error、next_retry_at 和 reconciliation 状态；
- 为 UNKNOWN 动作提供人工恢复队列；
- 终止任务前处理正在进行的副作用，明确 cancel 与 compensate 的区别；
- 使用 Temporal versioning 或 patch 机制保证历史兼容；
- 为同租户和连接器增加并发限制，防止突发请求打爆外部 API。

### 9.3 验收证据

输出一份故障注入报告：故障点、预期、不变量、实际恢复时间、Ledger 变化、重复副作用数、Trace 和截图。仅写“Temporal 可恢复”不算完成。

## 10. P0：真实企业连接器与 MCP

### 10.1 连接器策略

先选择一个生态完成深度闭环，而不是同时接入多个浅层 Demo。可按求职方向选择：

- 国内办公场景：飞书/企业微信中的任务、文档或消息；
- 国际企业场景：Microsoft Graph 或 Google Workspace；
- 开发协作场景：GitHub Issues/Projects，最容易搭建可公开演示的沙箱。

第一条真实链路建议为：读取项目 Issue → 生成周报 → 创建跟进 Issue → 审批后发送通知。

### 10.2 真实 Adapter 完成标准

- OAuth 2.0/OIDC，最小 Scope；
- Token 只保存 Secret 引用，模型、Timeline 和日志不可见；
- refresh、撤销、过期和重新授权；
- rate limit、Retry-After、指数退避和 jitter；
- timeout、circuit breaker 和连接池；
- request/response schema 校验和敏感字段脱敏；
- provider idempotency key 或 lookup/reconciliation；
- Webhook 签名验证、重放防护和去重；
- Fake 与真实实现运行同一套合同测试；
- Sandbox 账号 E2E，禁止测试触达真实用户。

### 10.3 MCP 实现

- 实现一个独立 MCP Server，把经过 Policy 包装的只读能力暴露为工具；
- 实现 MCP Client Adapter，支持 tools/list、tools/call、超时和结构化错误；
- 工具 Schema 版本化并固定来源，防止 tool poisoning 和 rug pull；
- 对读写工具分别授权，写操作仍进入 WorkPilot 审批；
- 记录 MCP server identity、tool version 和调用证据；
- 使用 OAuth discovery 和短期凭证，不在配置中放长期 Token；
- 增加恶意工具描述、Schema 变化、上下文过度共享的安全测试。

MCP 是协议能力证明，不应绕过现有 Adapter、Policy、Ledger 和 Verification。

## 11. P1：文件知识管线与可验证 RAG

### 11.1 用户能力

- 上传 PDF、DOCX、XLSX、Markdown 和文本；
- 显示解析、切块、索引进度与失败原因；
- 文档、文件夹和 Chunk 继承 tenant/user ACL；
- 回答或报告中的结论必须带文档、页码/工作表和片段引用；
- 用户可以打开原文并核对引用；
- 支持删除文档及其派生 Chunk、Embedding 和缓存。

### 11.2 推荐技术

- MinIO/S3：原始文件和 Artifact；
- PyMuPDF、python-docx、openpyxl：显式可控的文件解析；
- PostgreSQL full-text search + pgvector：混合检索；
- RRF 或可解释的加权融合，不在首版引入复杂学习排序；
- EmbeddingGateway：与 ModelGateway 相同的 Provider 隔离、成本和 Trace；
- 防病毒扫描、文件类型探测、大小限制和解析沙箱。

### 11.3 检索质量证明

- 建立查询、相关 Chunk 和标准引用数据集；
- 报告 Recall@5、MRR/nDCG、citation precision；
- 对比向量、全文和混合检索；
- 验证 tenant ACL 过滤发生在检索层，而不是生成后过滤；
- 注入隐藏指令和恶意文档，确认它们不能改变系统策略或触发写工具。

## 12. P1：安全、身份与治理

### 12.1 身份和权限

- 使用 OIDC 登录，开发环境可用 Keycloak，部署环境可替换企业 IdP；
- 建立 organization、user、role、connector_account 和 service_account；
- RBAC 管理页面权限，ABAC/Policy 管理任务、文档和工具 Scope；
- tenant_id 必须来自已验证 Token，不再信任任意请求头；
- 审批人必须满足角色、任务归属和 separation-of-duties；
- 管理员可撤销连接器、任务和长期授权。

### 12.2 Secret 和网络边界

- 本地使用 SOPS 或 Docker Secret，生产使用 Vault/云 Secret Manager；
- 凭证按需在 Adapter 边界注入，模型上下文永远不可见；
- 出站域名/IP allowlist，阻止 SSRF 和 metadata endpoint；
- Browser/文件解析运行在受限容器，设置 CPU、内存、时间和文件系统限制；
- 日志、Trace、Artifact 分级保留，并支持按租户删除。

### 12.3 Agent 安全测试

以 OWASP Agentic Top 10 和 MCP Top 10 建立映射测试，至少覆盖：

- Goal hijacking 与间接 Prompt Injection；
- Tool misuse、越权参数和额外收件人；
- Identity/privilege abuse；
- Tool/MCP supply-chain poisoning；
- Unexpected code execution、路径穿越和 SSRF；
- Memory/context poisoning；
- Loop amplification、资源耗尽和级联失败；
- 错误审批暗示、过度信任和不可撤销动作。

所有红队样本进入版本化数据集，修复后必须成为回归测试。

## 13. P1：OpenTelemetry、SLO 与成本治理

### 13.1 Trace 结构

使用 OpenTelemetry，并统一以下层级：

```text
task.run
├── model.plan
├── context.retrieve
├── policy.evaluate
├── approval.wait
├── tool.execute
│   ├── provider.http
│   └── tool.verify
└── artifact.persist
```

每个 Span 关联 trace_id、tenant、task、workflow、step、capability、model、prompt version 和 retry count。敏感 Prompt/文档正文默认不进入 Trace，只记录 hash、长度、分类和受控 Artifact 引用。

OpenTelemetry GenAI semantic conventions 可统一模型、Token、工具和检索信号；但这些约定仍在演进，字段需要封装在项目自己的 telemetry 模块内，避免业务代码直接依赖实验属性。

### 13.2 指标

- `task_success_total`、`task_duration_seconds`；
- `workflow_queue_latency_seconds`、`activity_retry_total`；
- `approval_wait_seconds`、`approval_reject_total`；
- `tool_call_total`、`tool_error_total`、`tool_duplicate_total`；
- `unknown_action_age_seconds`；
- `model_token_usage`、`model_cost`、`model_latency_seconds`；
- `retrieval_latency_seconds`、`citation_missing_total`；
- `outbox_lag_seconds`、`outbox_pending_total`。

### 13.3 首版 SLO 目标

以下均为目标，不是当前结果：

- API 读取接口月可用性 ≥ 99.9%；
- 非模型 API P95 延迟 ≤ 300 ms；
- Worker 可用后，排队任务 P95 在 5 秒内开始；
- 已接受任务最终进入成功、失败、取消或人工恢复队列的比例 ≥ 99.5%；
- 未授权 R2/R3 写入数为 0；
- 故障注入任务中的重复业务副作用数为 0；
- 失败 Trace 完整率 ≥ 99%；
- 每个真实模型任务均有 Token 和成本记录。

使用 OTel Collector、Prometheus、Grafana 和 Tempo/Jaeger 构建本地观测栈。告警必须关联 Runbook，而不是只展示漂亮图表。

## 14. P1：API、数据与事件架构修改

### 14.1 API

- OIDC Bearer Token 和 Scope；
- RFC Problem Details 统一错误；
- `X-Request-ID`/traceparent；
- 创建和运行接口支持客户端 Idempotency-Key；
- 异步动作返回 202、Location 和 operation status；
- 列表分页、过滤、排序；
- SSE 支持 Last-Event-ID、断线续传和 heartbeat；
- OpenAPI 契约测试和向后兼容检查；
- 租户、用户和连接器级 rate limit。

### 14.2 数据模型

建议新增：

- `model_runs`、`prompt_versions`；
- `connector_accounts`、`credential_refs`、`webhook_events`；
- `documents`、`document_chunks`、`citations`；
- `eval_datasets`、`eval_runs`、`eval_results`；
- `feedback`、`recovery_cases`、`compensation_runs`；
- `audit_exports`、`retention_policies`。

现有 Repository 每次保存会删除并重建多张子表，数据增长后写放大明显。应改为按 Aggregate 变化增量更新，Timeline/Checkpoint/Artifact 使用 append-only 写入。

### 14.3 异步 I/O

当前 FastAPI 和 Temporal Activity 中调用同步 SQLAlchemy。V3 需要二选一：

1. 迁移到 SQLAlchemy `AsyncSession` + asyncpg；或
2. 把数据库 Activity 定义为同步 Activity，避免阻塞 asyncio 事件循环。

两种方案都要用负载测试证明吞吐和连接池行为，而不是仅因为“async 更先进”就迁移。

### 14.4 Outbox 完整闭环

- 独立 Outbox Relay 使用 `FOR UPDATE SKIP LOCKED` 抢占事件；
- 消费者按 event id 去重；
- 发布失败退避、死信和人工重放；
- 监控 pending 数量和 oldest age；
- 如果只有 SSE 一个消费者，先使用 PostgreSQL 轮询即可；只有多个独立消费者出现后再引入 NATS/Redis Streams/Kafka。

## 15. P1：用户体验与前端产品化

建议使用 TypeScript + React/Next.js，但重点是产品闭环而不是框架名称。

### 15.1 必备页面

- 登录与组织切换；
- 连接器授权和 Scope 展示；
- 任务列表、筛选和模板；
- 任务详情、DAG、实时 Timeline；
- Plan Diff 和重新规划确认；
- 审批 Inbox、参数 Diff、风险原因和证据；
- Artifact/引用预览；
- UNKNOWN/FAILED 恢复中心；
- Eval Dashboard 和版本对比；
- 管理员审计和连接器撤销。

### 15.2 服务用户的关键功能

- 周报、会议跟进、Issue 汇总等可复用模板；
- 草稿模式：先生成报告，审批后再产生外部写入；
- 可解释预览：明确“将修改什么、为什么、如何验证”；
- 补偿动作：可撤销时提供 undo，不可撤销时给出明确警告；
- 失败后给用户具体恢复选项，而不是只有 Retry；
- 邮件/站内审批通知；
- 用户反馈和纠正进入评测数据闭环；
- 导出审计包，包含计划、审批、动作、验证和 Artifact 清单。

### 15.3 可用性验证

至少邀请 5 名目标用户完成固定任务，记录：完成率、首次价值时间、审批理解错误、失败恢复成功率和主观信任度。真实用户观察比前端截图更有说服力。

## 16. P2：Browser Agent、Memory 与多 Agent

### 16.1 Browser Adapter

- 使用 Playwright；
- 首版只允许一个自建固定测试站点；
- Observation 包含 URL、标题、可访问性树、关键 DOM 和截图；
- Action 只允许有限点击、输入、选择和滚动；
- 域名、下载、文件上传和弹窗有策略限制；
- 每个动作前后保存截图和 DOM 证据；
- 页面文本全部视为不可信数据，不能改变系统策略；
- E2E 验证 UI 变化，而不是只看 Playwright 命令成功。

### 16.2 Memory

先实现有治理的记忆，而不是无限聊天历史：

- Working memory：当前任务状态，由 Temporal/数据库负责；
- Episodic memory：已完成任务的结构化摘要；
- Semantic memory：经过 ACL 和来源验证的知识；
- 每次写 Memory 都记录来源、TTL、owner 和 confidence；
- 用户可查看、编辑和删除；
- 不可信内容不能自动写入长期记忆。

### 16.3 多 Agent 的引入条件

只有当单 Agent 基线显示某类任务确实需要角色分离时，再实现 Planner/Executor/Reviewer 三角色。必须通过消融实验回答：

- 成功率是否显著提高；
- Token、延迟和失败面增加多少；
- Reviewer 是否真的发现错误，还是只增加调用；
- Handoff 和共享上下文如何审计；
- 子 Agent 是否遵循同一 Policy 和预算。

没有这些数据，多 Agent 只会增加复杂度，不构成专业优势。

## 17. P2：部署、性能与软件供应链

### 17.1 Kubernetes 与 IaC

- API 和 Worker 分别使用 Deployment；
- Worker 按 Temporal task queue lag 或自定义指标扩缩容；
- readiness/liveness/startup probe；
- resource request/limit、PodDisruptionBudget；
- NetworkPolicy、non-root、read-only root filesystem；
- Helm Chart 管理环境差异；
- Terraform 只覆盖真实使用的云资源，不为展示创建空壳代码；
- kind/k3d 中执行部署 smoke test。

Kubernetes HPA 支持基于资源或自定义指标调整副本，因此 Worker 的合理扩缩容信号应优先使用队列积压和处理延迟，而不是只看 CPU。

### 17.2 CI/CD 与 DevSecOps

在现有 CI 上增加：

- PostgreSQL service container 集成测试；
- Temporal test server 或 Compose E2E；
- OpenAPI breaking-change 检查；
- CodeQL、dependency review、secret scanning；
- Trivy 或 Grype 镜像扫描；
- Syft SBOM；
- 镜像签名和 artifact attestation；
- migration smoke、upgrade/downgrade 检查；
- build once、promote same image；
- staging 自动部署，production 保留人工批准。

GitHub Artifact Attestations 可把构建产物关联到源代码、工作流和 commit，并可附带 SBOM；它证明来源和完整性，不代表产物本身没有漏洞。

### 17.3 性能测试

- 使用 k6 或 Locust；
- 测任务创建、查询、SSE 连接和审批，不用真实付费模型压测 API；
- 模型和 SaaS 使用可配置延迟/限流的 simulator；
- 报告吞吐、P50/P95/P99、错误率、DB 连接池、队列积压和 Worker 饱和度；
- 至少做一次容量估算和瓶颈分析。

## 18. 分阶段实施路线

### 阶段 A：建立可测的真实 Agent（第 1–2 周）

交付：

- ModelGateway、Fake/真实 Provider；
- 结构化 Planner、fallback、预算和 Prompt version；
- ContextBuilder 和信任标签；
- 60 条固定任务集；
- 模板 Planner 与模型 Planner 基线报告。

退出条件：计划 Schema 最终合法率 100%，所有失败可分类，真实调用有 Token/成本记录。这里的 100% 指“校验、修复或安全 fallback 后不会把非法计划交给执行器”，不是模型首轮正确率。

### 阶段 B：证明可靠和可观测（第 3–4 周）

交付：

- Temporal WorkflowEnvironment 测试；
- Worker kill/restart 和副作用故障注入；
- heartbeat、取消传播、版本 replay；
- OpenTelemetry、Prometheus、Grafana、Tempo；
- 故障报告和 Runbook。

退出条件：定义的故障矩阵全部通过，未授权写入和重复业务副作用为 0，失败任务能够定位到具体模型/工具/数据库 Span。

### 阶段 C：接入真实系统（第 5–6 周）

交付：

- 一个真实 OAuth 企业连接器；
- Connector Account、Secret 引用、限流和 Webhook；
- MCP Server/Client 最小闭环；
- Fake/真实合同测试；
- PostgreSQL RLS 对抗测试。

退出条件：沙箱账号完成完整周报任务，撤销授权后不能继续调用，跨租户和越 Scope 测试通过。

### 阶段 D：让用户真正可用（第 7–8 周）

交付：

- 文件上传、混合检索、引用与 RAG 评测；
- OIDC、审批 Inbox、任务列表和恢复中心；
- Outbox Relay 和断线续传；
- 5 名用户可用性测试和反馈修复。

退出条件：用户不看开发者说明也能完成创建、审批、核对证据和恢复失败任务。

### 阶段 E：展示生产化能力（第 9–10 周，可选）

交付：

- Kubernetes/Helm、IaC、自动扩缩容；
- 安全扫描、SBOM、attestation；
- 性能报告、SLO Dashboard、备份恢复演练；
- Demo 视频、架构图、Benchmark 和事故复盘。

退出条件：全新环境可按文档部署，回滚和恢复演练有记录，简历中的每个数字都能指向报告。

## 19. V3 完成定义

### 19.1 用户闭环

- 用户能够登录、授权连接器、上传资料、创建任务、查看计划、审批、追踪、恢复和导出审计包；
- 至少一条真实业务流程在沙箱环境端到端完成；
- 结果有可点击引用或远端对象证据；
- 失败有可理解的原因和恢复动作；
- 用户可以撤销授权并删除自己的数据。

### 19.2 Agent 质量

- 固定任务集、版本化 rubric 和可重复 Runner 已提交仓库；
- 模板、模型、不同 Prompt/模型配置有基线对比；
- 报告 task success、tool selection、安全、Token、成本和延迟；
- LLM Judge 与人评一致性经过校准；
- 每个线上 bad case 可以转为回归样本。

### 19.3 工程与可靠性

- PostgreSQL、Temporal 和一个真实连接器有集成/E2E；
- Worker 崩溃、超时、重复投递和响应丢失测试通过；
- RLS、OIDC、Scope、Prompt Injection 和 Secret 泄漏测试通过；
- OTel Trace 能串联 API、Workflow、Model、Tool、Verify 和 DB；
- SLO、告警、Runbook、备份和恢复演练存在；
- CI 包含质量、安全、迁移、集成和构建供应链门禁。

### 19.4 项目表达

- README 五分钟可运行；
- C4/时序图和关键 ADR 完整；
- Benchmark 报告包含失败样本，不只展示最好结果；
- 有 5–8 分钟 Demo 视频；
- 有一次真实故障复盘；
- 简历数字全部来自可复现实验。

## 20. 面试展示设计

### 20.1 八分钟 Demo

1. 登录并连接沙箱企业系统；
2. 上传周报模板，输入自然语言目标；
3. 展示模型计划、DAG 校验、预算和来源；
4. 执行到外部写入，展示参数 Diff 和审批哈希；
5. 审批前杀死 Worker，重启后继续；
6. 注入“远端成功但响应丢失”，展示 UNKNOWN → lookup → CONFIRMED 且无重复对象；
7. 打开 Trace、Artifact、评测报告和成本；
8. 说明一个没有采用的方案及原因，例如为什么没有默认多 Agent。

### 20.2 面试官追问与证据

| 追问 | 应展示的证据 |
| --- | --- |
| LLM 输出非法计划怎么办？ | Schema 错误样本、修复/fallback、DAG validator |
| 如何避免重复发邮件？ | Ledger 状态机、provider key、lookup、故障注入报告 |
| 服务挂了怎么办？ | Temporal History、Worker restart E2E、恢复时间 |
| Prompt Injection 怎么防？ | trust label、Policy、恶意文档回归集 |
| 如何知道 Agent 变好了？ | Dataset、baseline、置信区间、failure taxonomy |
| 如何排查一次失败？ | OTel Trace 从 API 到模型、工具和验证 |
| 为什么不用 LangChain/多 Agent？ | ADR 和消融数据，而不是个人偏好 |
| 多租户如何保证？ | OIDC tenant claim、RLS、真实 PostgreSQL 对抗测试 |
| 如何控制成本？ | Token/cost budget、缓存、模型路由和成本 Dashboard |
| 如何上线？ | 镜像、Helm、IaC、SLO、Runbook 和回滚演练 |

## 21. 简历表达模板

以下数字必须用真实结果替换，不得原样使用占位符：

- 设计并实现面向企业办公流程的安全执行 Agent，使用 FastAPI、PostgreSQL 与 Temporal 管理长任务、人工审批和故障恢复，覆盖 `[N]` 类业务动作。
- 构建参数哈希审批、Action Ledger 和 lookup-before-retry，在 `[N]` 次故障注入中将未授权写入与重复副作用保持为 `0`。
- 建立 `[N]` 条版本化 Agent 评测集和 Trace grading 流程，将任务成功率从 `[A]%` 提升到 `[B]%`，同时把每成功任务成本控制在 `[C]`。
- 基于 OpenTelemetry 串联模型、检索、工具、数据库和 Temporal Span，将失败定位时间从 `[A]` 降至 `[B]`。
- 接入 `[真实系统]` OAuth 沙箱和 MCP 工具，完成限流、Webhook、最小权限、跨租户隔离与合同测试。

不要写：

- “精通 Kubernetes/Temporal”，除非能够深入回答运行机制和故障案例；
- “准确率 99%”，如果没有数据集、样本数和统计方法；
- “零重复”，如果只测试了 Fake 正常路径；
- “生产级”，如果没有身份、安全、观测、告警和恢复演练；
- “多 Agent 架构”，如果没有证明它比单 Agent 更好。

## 22. 优先级 Backlog

### P0：完成后即可显著增强简历

- [ ] ModelGateway + structured output + fallback
- [ ] ContextBuilder + budget + trust label
- [ ] 60 条评测集 + baseline report
- [ ] Temporal test environment + kill/restart E2E
- [ ] OTel Trace + Token/成本 + Grafana
- [ ] 一个真实 OAuth 连接器 + 合同测试
- [ ] PostgreSQL RLS 真实集成测试
- [ ] 故障注入报告和 Demo 视频

### P1：形成完整可用产品

- [ ] OIDC + RBAC/ABAC + Secret Store
- [ ] 文件解析 + MinIO + pgvector 混合检索
- [ ] 引用 UI 和检索评测
- [ ] Outbox Relay + SSE 断线续传
- [ ] React/Next.js 任务、审批、恢复和 Eval 页面
- [ ] OWASP Agentic/MCP 安全回归集
- [ ] 用户反馈闭环和 5 人可用性测试

### P2：面向平台/基础设施岗位加分

- [ ] MCP Server/Client 完整授权
- [ ] Playwright Browser Adapter 与沙箱
- [ ] Kubernetes/Helm + queue-lag autoscaling
- [ ] Terraform + staging deployment
- [ ] CodeQL/Trivy/SBOM/attestation
- [ ] k6/Locust 容量和性能报告
- [ ] 受控 Memory；评测证明后再引入多 Agent

## 23. 主要风险与控制

| 风险 | 表现 | 控制 |
| --- | --- | --- |
| 技术栈堆砌 | 每项都只有 Hello World | 一个真实连接器和一条流程做深 |
| 模型费用失控 | CI 或循环反复调用模型 | budget、离线 Fake、定时 eval、硬上限 |
| 评测污染 | 针对公开样本调 Prompt | 开发集/保留集、版本冻结、盲测 |
| Prompt/Trace 泄密 | 观测系统保存正文和 Token | 默认不采集正文、脱敏、访问控制、保留策略 |
| Temporal 与 DB 双状态漂移 | Workflow 与 Task 状态不同 | 明确事实源、reconciliation job、恢复中心 |
| OAuth 审核阻塞 | 无法使用生产应用 | 优先 Sandbox/开发者应用，准备 GitHub 备选 |
| RAG 变成演示 | 只有向量库，没有引用质量 | 固定检索集和 citation 指标 |
| Kubernetes 消耗时间 | 集群 YAML 多但产品没提升 | P0 完成后再做，用 kind 自动验收 |
| 多 Agent 放大失败 | Token、上下文和权限面增加 | 先单 Agent baseline，再做消融 |

## 24. 官方参考依据

### 岗位能力信号

- [腾讯 WorkBuddy-Agent Harness 研发工程师](https://careers.tencent.com/jobdesc.html?postId=2098252452842352640)：Context Engineering、MCP、Memory、Long-Horizon、Evaluation 和系统工程。
- [腾讯混元 Agent 强化学习框架工程师](https://careers.tencent.com/jobdesc.html?postId=2061654749727600640)：Python asyncio、并发、模型/工具调用、Trace、评估、Kubernetes 和稳定性。
- [腾讯 AI 数据工程开发](https://careers.tencent.com/jobdesc.html?postId=2097954502169767936)：API、MCP、Workflow、异步任务、服务治理和可观测性。
- [OpenAI Software Engineer, Agent Infrastructure](https://openai.com/careers/software-engineer-agent-infrastructure-san-francisco/)：FastAPI、gRPC、Terraform、容器化、沙箱、可靠性与规模化。
- [Apple AI Evaluation Engineer](https://jobs.apple.com/en-us/details/200686891/aiml-sr-software-engineer-ai-evaluation)：Agentic systems、LLM-as-judge、人评一致性、系统测试、调试和监控。

### 技术与安全依据

- [OpenAI 官方 Agent 评测指南](https://developers.openai.com/api/docs/guides/agent-evals)：Trace、grader、dataset 和重复 eval run。
- [OpenTelemetry GenAI 语义约定](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)：模型、Token、检索和 GenAI 观测字段。
- [Temporal Python WorkflowEnvironment](https://python.temporal.io/temporalio.testing.WorkflowEnvironment.html)：本地测试服务与 time-skipping。
- [OWASP Agentic Top 10](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)：Goal hijacking、工具误用、身份权限和供应链等风险。
- [OWASP MCP Top 10](https://owasp.org/projects/mcp-top-10?tab=top10)：Token、Scope、工具投毒、命令执行和审计风险。
- [MCP Authorization](https://apps.extensions.modelcontextprotocol.io/api/documents/authorization.html)：OAuth discovery 和 per-server/per-tool authorization。
- [Kubernetes HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)：资源和自定义指标扩缩容。
- [GitHub Artifact Attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)：构建来源、完整性与 SBOM 关联。

## 25. 最终建议

后续不要继续平均分配精力。最优路径是：

```text
真实 Model Planner
    → 固定评测和 Trace
    → Temporal 故障证明
    → 一个真实企业连接器
    → OTel/SLO/成本
    → 用户闭环与安全治理
    → 最后再做 K8s、Browser 和多 Agent
```

对求职最有说服力的不是“项目支持很多功能”，而是能够拿出三类硬证据：

1. 一份包含失败样本的 Agent Benchmark；
2. 一份 Worker 崩溃和副作用不重复的故障报告；
3. 一条真实 OAuth 系统上的用户流程和完整 Trace。

当这三项成立时，WorkPilot 才能同时体现 Agent 原理、后端系统设计、可靠性、安全、评测和产品意识，并形成比普通 RAG 聊天项目更明显的面试优势。
