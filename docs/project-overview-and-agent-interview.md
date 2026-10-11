# WorkPilot 项目全景与 Agent 岗位面试指南

- 文档日期：2026-10-11
- 项目版本：0.2.0
- 结论：**项目已经达到可写入简历、可用于互联网大厂 Agent 岗位面试和现场演示的成熟度。**

本文只描述仓库中已有实现和可复现证据。按照当前成熟度，不再单列“后续补充和完善”章节；
真实云模型、真实 GitHub 沙箱、生产环境和用户研究等尚未完成的内容，只作为简历表达边界说明，
不能包装成既有成果。

## 1. 一句话介绍

WorkPilot 是一个面向企业跨系统办公流程的安全执行 Agent：它把用户的自然语言目标转换为
带依赖关系、风险等级和验证规则的结构化任务 DAG，经确定性策略和人工审批后调用企业工具，
再通过独立查询确认副作用，并用持久工作流、动作账本、审计时间线和评测体系保证任务可恢复、
可追踪、可解释。

它解决的不是“模型能不能回答”，而是“Agent 能不能安全、可靠地替用户完成真实业务动作”。

## 2. 项目面向的用户

### 2.1 直接用户

| 用户角色 | 典型任务 | WorkPilot 提供的价值 |
| --- | --- | --- |
| 项目经理 | 汇总项目进展、生成周报、创建跟进任务、发送通知 | 把跨知识库、项目系统和邮件的重复工作变成一次可审批委派 |
| 运营人员 | 从文档和表格提取信息、录入业务系统、核对结果 | 降低人工复制粘贴和漏录、重复录入风险 |
| 行政与协作人员 | 整理会议结论、分发待办、生成规范文档 | 自动完成信息整理，同时保留来源与执行证据 |
| 企业知识工作者 | 检索 PDF、DOCX、XLSX、Markdown、TXT 并生成有引用的产物 | 在租户和用户权限范围内获得可核验答案 |

项目明确不面向财务付款、永久删除、管理员权限变更等高风险自动执行场景。R3 动作在当前
MVP 中直接拒绝，而不是依赖模型“自觉”规避。

### 2.2 管理与运维用户

- 审批人：查看外部写入的真实参数、参数哈希和风险级别，执行批准或拒绝；OIDC 模式下支持
  职责分离，任务创建者不能审批自己的动作。
- 平台管理员：查看任务时间线、Checkpoint、Artifact、Action Ledger、恢复队列、Trace、指标
  和评测报告，定位失败并导出审计记录。
- Agent 工程团队：通过固定数据集、模型对比 Runner、安全回归和失败分类持续迭代 Planner、
  Context、Policy 与 Connector。

## 3. 项目作用与业务价值

传统办公自动化通常在两个极端之间：规则工作流稳定但不理解自然语言，通用 Agent 灵活但
难以约束真实副作用。WorkPilot 将两者组合：模型负责理解和生成候选计划，确定性系统负责
风险、权限、预算、审批、幂等和验证。

核心作用包括：

1. **目标到执行计划**：把自然语言任务拆成有向无环图，每个步骤显式声明能力、依赖、风险、
   参数、预期副作用和验证规则。
2. **安全执行外部动作**：写操作不能仅凭模型输出发生；系统会校验能力、风险和收件人域名，
   R2 动作必须经参数预览与哈希绑定审批，R3 动作被拒绝。
3. **避免失败重试产生重复业务结果**：先在 Action Ledger 预占稳定幂等键；遇到“远端已成功、
   本地响应丢失”时进入 `UNKNOWN`，恢复后先远端查询，再决定是否重试。
4. **证明任务真的完成**：执行成功不等于业务成功。每一步还会通过独立读取执行验证，并保存
   observed state、evidence reference、confidence 和原因。
5. **让长任务可恢复和可审计**：Temporal 保存工作流历史，PostgreSQL 保存业务事实；时间线、
   Checkpoint、Artifact、Outbox 和 Trace 共同形成证据链。
6. **把 Agent 迭代变成可测量工程**：版本化任务集、重复运行、失败分类、安全零容忍门禁、
   模型成本/时延统计和人工盲审包，使优化不依赖主观 Demo 观感。

## 4. 端到端工作方式

```text
自然语言目标
  → 支持域门：EXECUTABLE / NEEDS_CLARIFICATION / REJECTED
  → ContextBuilder：来源信任标签、注入标记、工具筛选、Token 预算
  → Planner：结构化输出、Schema 校验、一次修复、安全回退
  → DAG / 能力 / 风险 / 预算确定性校验
  → Temporal 调度步骤
  → Policy Engine 判定 R0–R3
  → R2 参数预览与人工审批；R3 拒绝
  → Action Ledger 预占幂等键
  → API / MCP / Browser Adapter 执行
  → 独立远端读取验证
  → 持久化 Artifact、Checkpoint、Timeline、Outbox 与 Trace
```

当远端写入已经发生但响应丢失时，流程不会盲目重放：Ledger 将动作标为 `UNKNOWN`，恢复后用
同一稳定键执行 `lookup-before-retry`。发现远端对象后直接确认，不再执行第二次写入。这是项目
可靠性设计中最能体现工程深度的部分之一。

## 5. 已具备的功能

### 5.1 Agent 规划与上下文

- 支持周报、会议跟进、Issue 汇总和故障恢复场景的确定性 Planner；
- 模型调用前的 fail-closed 支持域门，输出 `EXECUTABLE`、`NEEDS_CLARIFICATION`、`REJECTED`；
- 可替换 `ModelGateway`，支持 OpenAI-compatible Provider 与可复现 Fake Provider；
- 基于 Pydantic JSON Schema 的结构化计划输出、一次自动修复和确定性安全回退；
- DAG 无环、依赖存在、步骤数量、能力注册、风险与审批一致性检查；
- 重规划 Plan Diff，禁止删除或篡改已成功步骤；
- ContextBuilder 的来源分层、trust label、Prompt Injection 标记、候选工具筛选与 Token 裁剪；
- 模型调用记录 provider、model、request id、Prompt/Schema 版本、Token、成本、时延、重试和
  trace id，默认不持久化 Prompt 正文。

### 5.2 安全与权限

- R0–R3 风险分级：读操作、内部产物、外部可逆写入和禁止动作采用不同策略；
- R2 审批展示真实参数，并将审批绑定到 `parameter_hash` 和 plan version，防止“批的是 A，
  执行的是 B”；
- 域名白名单、步骤预算、工具能力白名单和外部写入限制；
- OIDC/JWKS 验签、issuer/audience 校验、tenant claim、RBAC 和审批职责分离；
- Secret 只以引用形式存在于计划和模型上下文中，在 Connector 边界注入；
- MCP 只开放 R0 读工具，校验 server identity、工具描述和 Schema 指纹，阻断工具投毒与
  运行期 Schema 漂移；
- Browser 通道限制 origin、稳定 selector、动作预算、上传下载和弹窗，并把网页内容视为
  untrusted context。

### 5.3 执行可靠性

- Planner–Executor–Verifier 主循环与显式任务/步骤状态机；
- Temporal Workflow/Activity、审批 Update、Pause/Resume/Cancel Signal 和独立 Worker；
- PostgreSQL/SQLAlchemy 持久仓储、Alembic 迁移、乐观锁和 FORCE RLS 租户隔离；
- 稳定幂等键、Action Ledger、`RESERVED/UNKNOWN/CONFIRMED` 状态和远端核验；
- 与业务事务一起提交的 Outbox、失败计数、死信和消费端 event id 去重；
- 每个安全边界和副作用后的 Checkpoint，可用于恢复和审计；
- API `Idempotency-Key`、RFC Problem Details、分页/过滤和 SSE `Last-Event-ID` 续传。

### 5.4 企业工具与数据

- GitHub Issues OAuth/HTTP Adapter：授权状态、Scope、Token 归属/撤销、限流、熔断、远端
  幂等 marker、Webhook 签名与防重放；
- GitHub 沙箱 E2E Runner：创建/验证/清理 Issue 与评论，注入 429、5xx 和提交后响应丢失；
- 邮件、知识、项目更新、报告和任务的 Fake Adapter，用于离线确定性验证；
- MCP Server/Client 的只读工具发现与调用闭环；
- Playwright 浏览器证据通道，保存操作前后 DOM、截图、SHA-256 和验证结果；
- PDF、DOCX、XLSX、Markdown、TXT 文件解析，ACL、分块、lexical/vector/hybrid 检索、引用
  和原文预览；
- working、episodic、semantic Memory，带来源、TTL、owner、confidence 和确认后写入策略。

### 5.5 产品、观测和部署

- FastAPI 提供任务创建、澄清、执行、重规划、审批、拒绝、暂停、恢复、取消、Artifact、
  Replay、审计导出、知识库、Memory、连接器和评测接口；
- 无构建步骤的三栏 Web 工作台，覆盖任务、DAG、审批 Inbox、恢复中心、连接器、知识、Memory
  与 Eval 面板；
- OpenTelemetry/OTLP Trace、Prometheus 指标、Tempo、Grafana Dashboard、Alertmanager 和
  6 条 SLO/安全告警；
- Docker、Docker Compose、Helm、KEDA、PDB、NetworkPolicy、非 root 和只读文件系统；
- GitHub Actions 中的 Ruff、mypy、pytest/coverage、安全评测、Alembic、PostgreSQL RLS、
  CodeQL、Trivy、SBOM、attestation 和 Helm 契约检查。

## 6. 技术架构

项目采用“模块化单体 + 独立 Worker”，避免为了简历关键词提前拆分微服务。

| 层次 | 主要模块 | 职责 |
| --- | --- | --- |
| 交互层 | `apps/web`、FastAPI、REST、SSE | 任务输入、审批、进度、证据与恢复操作 |
| 控制平面 | `workpilot/api.py`、`auth.py` | OIDC/RBAC、租户上下文、API 幂等和协议错误 |
| Agent Runtime | `planner.py`、`context.py`、`runtime.py` | 上下文构建、结构化规划、执行、验证与重规划 |
| 安全策略 | `dag.py`、`policy.py`、`security.py` | DAG、能力、风险、审批、域名和秘密边界 |
| 工具层 | `connectors/`、`mcp.py`、`browser.py` | API、MCP 与浏览器三种执行通道 |
| 持久化 | `db/`、Alembic、PostgreSQL | 任务事实、RLS、乐观锁、Ledger、Outbox |
| 工作流 | `workflows/`、Temporal Worker | 长任务调度、审批等待、信号与崩溃恢复 |
| 知识与记忆 | `knowledge.py`、`memory.py` | 文件摄取、检索、引用和受控长期信息 |
| 质量系统 | `evaluation.py`、`model_evaluation.py`、`security_evaluation.py` | 固定集、重复评测、门禁、盲审与失败分类 |
| 运维系统 | `telemetry.py`、`deploy/`、`benchmarks/` | Trace、Metrics、告警、部署、容量和恢复演练 |

关键设计原则是：模型不拥有风险判定、权限判定、审批决策和重试语义。这些决定由可测试、
可审计的确定性代码控制。

## 7. 使用到的工具和技术

| 类别 | 工具/技术 | 在项目中的实际用途 |
| --- | --- | --- |
| 语言与 API | Python 3.12+、FastAPI、Uvicorn | Agent 核心、异步 HTTP API、SSE 事件流 |
| 类型与 Schema | Pydantic v2、JSON Schema | Planner 输出、任务模型、工具参数、审批和验证结果校验 |
| 模型接入 | OpenAI-compatible Chat Completions、ModelGateway | 模型替换、结构化规划、预算、重试和调用记录 |
| 工作流 | Temporal Python SDK | Durable Execution、Activity、Update、Signal、History replay |
| 数据库 | PostgreSQL、SQLAlchemy 2、Alembic、pgvector | 持久化、迁移、乐观锁、RLS、向量数据基础设施 |
| 工具协议 | HTTP/OAuth 2.0、MCP、Playwright | GitHub 连接器、只读工具桥、受控浏览器执行 |
| 文件处理 | PyMuPDF、python-docx、openpyxl | PDF、Word、Excel 等企业文档解析 |
| 身份安全 | OIDC、JWT/JWKS、RBAC、HMAC、SHA-256 | 身份验证、租户与角色、Webhook、参数和证据完整性 |
| 可观测性 | OpenTelemetry、OTLP、Tempo、Prometheus、Grafana、Alertmanager | 分布式追踪、指标、Dashboard、SLO 与告警 |
| 部署 | Docker、Docker Compose、Helm、KEDA、Kubernetes 策略 | 本地全栈、镜像、弹性、可用性和网络边界 |
| 工程质量 | pytest、coverage、Ruff、mypy、uv | 自动化测试、覆盖率门禁、静态检查和依赖锁定 |
| 供应链安全 | GitHub Actions、CodeQL、Trivy、SPDX SBOM、attestation | 代码扫描、镜像漏洞、物料清单和构建证明 |

项目没有把 LangChain、LangGraph 等通用 Agent 框架作为核心依赖。这是有意识的取舍：状态机、
DAG、策略和动作账本是本项目要展示的核心能力，直接实现可以让安全与恢复语义更透明，也能在
面试中清楚解释每个边界，而不是把关键正确性隐藏在框架内部。

## 8. 当前可复现的工程证据

| 证据 | 当前结果 | 正确解释 |
| --- | --- | --- |
| 默认测试收集 | 131 项，其中 5 项依赖本地真实服务/浏览器的 gated 测试；当前默认运行 126 passed、5 skipped | 默认套件与外部集成测试分层 |
| Agent 支持域门评测 | 60 cases × 3 次，180/180 通过；Schema、DAG、Disposition、Safety、R3 block 均为 1.0；未授权写入 0 | 离线确定性 Planner 回归 |
| 历史 Agent 基线 | safety 0.6667、未授权写入 0.3333 | 保留失败基线，证明评测发现问题并驱动修复 |
| Agentic 安全回归 | 20/20 通过 | 策略回归，不等同于渗透测试 |
| 检索评测 | 10 cases；lexical、vector、hybrid 的 Recall@5、MRR、nDCG@5、Citation P@1 均为 1.0 | 小规模精确事实离线集 |
| 幂等故障注入 | 同动作 100 次投递，实际执行 1 次，远端对象 1，重复副作用 0 | Fake Adapter 定义失败模型 |
| Temporal 集成 | 本地真实测试服务 1 passed / 19.78s | 本地 Worker 重启、Update、History replay |
| PostgreSQL RLS | 本地 pgvector/pg16 容器 3 passed | 真实数据库租户隔离对抗测试 |
| Browser | Playwright Chromium 2 passed | 本地受控页面，不是第三方站点兼容矩阵 |
| API 基线 | 300 ops、并发 20、0% 错误、813.90 req/s；create P95 51.253 ms | in-process ASGI + 内存仓储容量基线 |
| 部署与恢复 | Helm lint、受限容器、10/10 表恢复与自动清理通过 | 本地工程验证，不代表生产 SLO |

证据入口集中在 [`resume-evidence.md`](resume-evidence.md)、`evals/reports/`、
`benchmarks/reports/` 和 `docs/reports/`。项目特意保留历史失败结果，并区分“已实现”“已实测”
与“需要外部凭证”，这是可信度而不是短板。

## 9. 面向互联网大厂 Agent 岗位的优势

### 9.1 不停留在 Prompt 与对话层

很多 Agent 项目只展示模型选工具和生成回答，WorkPilot 展示的是完整的 Agent Runtime：
Context、Planner、DAG、Policy、Executor、Verifier、Replanner、Memory、Evaluation 与
Observability 都有明确边界。它能用于讨论 Agent 系统设计，而不只是提示词技巧。

### 9.2 抓住真实 Agent 最难的副作用问题

项目能清楚回答面试中的关键问题：

- 模型误规划怎么办：支持域门、Schema、DAG 和 Policy 四层约束；
- 写操作怎么控：R2 参数预览、哈希绑定审批、R3 拒绝；
- Worker 崩溃怎么办：Temporal History + PostgreSQL 业务事实 + Checkpoint；
- 请求超时但远端成功怎么办：`UNKNOWN` + lookup-before-retry；
- 怎么知道真的成功：独立读取验证，而不是相信写接口返回；
- 怎么审计：Timeline、Ledger、Artifact、Outbox、Trace 和审计导出。

这套回答覆盖了 Agent 生产化中最具区分度的安全性、一致性和可恢复性。

### 9.3 有企业级多租户与身份意识

OIDC/JWKS、tenant claim、RBAC、职责分离、PostgreSQL FORCE RLS、Secret 隔离、Webhook 防重放、
MCP Schema 固定和浏览器白名单，表明项目从一开始就在考虑企业权限边界，而不是在 Demo 完成后
再补一层登录页面。

### 9.4 有评测闭环，而不是只展示成功案例

版本化数据集、重复运行、Wilson 区间、失败分类、安全零容忍、模型成本与方差、匿名人工盲审包，
构成了较完整的 Agent Evals 思路。尤其是保留 0.6667 的历史失败基线，再用支持域门把未授权写入
从 0.3333 降到 0，能讲出“发现问题—定位根因—设计门禁—回归证明”的完整工程故事。

### 9.5 工程广度与取舍能力兼具

项目覆盖 API、工作流、数据库、浏览器、知识检索、模型网关、观测、部署和供应链，但仍保持
模块化单体和单 Planner，没有为了关键词堆微服务或多 Agent。ADR 和文档明确写出取舍及证据
边界，体现的是架构判断力，而不是技术名词数量。

### 9.6 特别适配的岗位方向

- Agent 平台 / Agent Runtime 工程师；
- 大模型应用工程师、AI Backend Engineer；
- Agent 安全、治理和评测工程师；
- 企业 AI、Copilot、Workflow Automation 方向；
- 偏后端与基础设施的 Applied AI Engineer。

如果岗位更偏纯算法研究，应重点讲结构化规划、检索评测、模型对比与失败分类；如果岗位偏
平台工程，应重点讲 Temporal、Ledger、RLS、Outbox、可观测性和部署供应链。

## 10. 建议写进简历的内容

### 10.1 项目标题

**WorkPilot｜面向企业跨系统办公流程的安全执行 Agent**

### 10.2 项目简介

> 设计并实现企业办公安全执行 Agent，将自然语言目标转换为结构化任务 DAG，在确定性策略、
> 人工审批、幂等账本和独立远端验证约束下执行；基于 Temporal 与 PostgreSQL RLS 构建可恢复、
> 多租户的执行链路，并用版本化评测、OpenTelemetry 和故障注入形成可复现证据。

### 10.3 推荐简历要点

- 自研 Planner–Executor–Verifier Runtime，使用 Pydantic Schema 和确定性 DAG/能力/风险校验
  约束模型输出；增加 fail-closed 支持域门，在 60 条任务、每条 3 次的 180 次离线回归中实现
  Schema、DAG、Disposition、Safety 全部 1.0，未授权写入从 0.3333 降至 0。
- 设计 R0–R3 风险策略与参数哈希审批，将审批绑定到真实执行参数；以 Action Ledger、稳定幂等键、
  `UNKNOWN` 状态和 lookup-before-retry 处理提交后响应丢失，在定义的故障模型下实现 100 次
  同键投递仅 1 次实际执行、重复业务副作用 0。
- 基于 Temporal Workflow/Activity 和 PostgreSQL/SQLAlchemy/Alembic 构建持久执行链路，支持
  审批 Update、暂停/恢复/取消 Signal、Worker 重启恢复、乐观锁、事务 Outbox 和 FORCE RLS；
  完成本地真实 Temporal 与 PostgreSQL 租户隔离集成验证。
- 建设 Agent 质量与运维体系：版本化评测集、安全回归、检索指标、双模型成本/时延/方差 Runner、
  OTel/Tempo/Prometheus/Grafana、Docker Compose 与 Helm，并在 CI 中执行覆盖率、类型、迁移、
  安全评测、CodeQL、Trivy、SBOM 和部署契约门禁。

建议根据简历版面保留 3 条，并始终携带“离线确定性”“本地真实服务”或“定义故障模型”等
环境限定，避免把工程证据扩大成生产结果。

## 11. 面试展示顺序

建议用 8 分钟讲完整闭环：

1. 用 30 秒说明问题：企业 Agent 的难点不是聊天，而是安全地执行副作用；
2. 创建周报或会议跟进任务，展示结构化 DAG、风险和成功条件；
3. 运行到 R2 审批点，展示参数预览与参数哈希；
4. 批准后展示执行、独立验证、Artifact 和时间线；
5. 展示一次响应丢失恢复，解释 `UNKNOWN` 与 lookup-before-retry；
6. 展示评测报告中历史失败基线和 180/180 当前基线；
7. 用架构图收束到 Temporal、PostgreSQL RLS、OTel 与部署门禁。

最值得深入准备的追问是：为什么不用通用 Agent 框架、为什么 Temporal 不等于 exactly-once、
为什么审批必须绑定参数、为什么验证要与执行分离、如何防止 Prompt Injection 影响工具调用、
以及离线 100% 指标为什么不能代表生产效果。

## 12. 简历表达边界

项目已经足够进入简历，但以下内容不能写成已完成成果：

- 真实付费云模型达到某个成功率或成本目标；
- GitHub OAuth 沙箱端到端已经通过；
- 生产 Kubernetes、月度 99.9% SLO、多区域容灾或生产级 RTO/RPO；
- 5 人可用性研究、SUS 分数或正式 Demo 视频；
- 多 Agent 相比单 Agent 获得效果提升；
- 20/20 策略回归等同于渗透测试；
- in-process 813.90 req/s 等同于 PostgreSQL、Temporal 和 SaaS 全链路吞吐。

因此，准确定位应是：**具备完整安全执行闭环和强面试证据的企业 Agent 工程 MVP**，而不是
“已经生产落地的大规模 Agent 平台”。这个边界不影响项目写入简历，反而能体现严谨的工程判断。

## 13. 相关入口

- [README](../README.md)：启动方式、API 示例和项目结构；
- [V3 架构图](architecture-v3.md)：C4 容器图与关键时序；
- [简历证据索引](resume-evidence.md)：可复现数字和措辞边界；
- [8 分钟 Demo 脚本](demo-runbook.md)：现场展示流程；
- [规划安全门](planning-safety-gate.md)：支持域、澄清与拒绝；
- [模型对比评测](model-comparison-evaluation.md)：双模型 Runner 与人工盲审；
- [GitHub 沙箱 Runbook](github-sandbox-runbook.md)：真实连接器验收步骤；
- [可观测性](observability.md)：Trace、Metrics、SLO 和故障 Runbook。
