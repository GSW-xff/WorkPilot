# WorkPilot 专业技能项目映射与源码解析

本报告以当前仓库源码、测试、迁移、部署文件和可复现评测报告为依据，逐项核验简历中五类专业技能在 WorkPilot 项目中的实际使用情况。每个技能点都回答四个问题：它是什么意思、解决什么问题、项目怎样实现、目前能够证明到什么程度。

本次核验的结论是：WorkPilot 对后端工程、Plan and Execute、任务编排、结构化输出、状态持久化、MCP、RAG 基础管线、Agent 评测和可靠性控制有较完整的代码证据；对 ReAct、Embedding 选型、Rerank 和 Function Calling 只有部分关联或自研等价实现；Redis、MySQL、LangChain、LangGraph、Multi Agent、Handoff、BM25、Query Rewriting、HyDE、Few shot、SFT、LoRA QLoRA 和 LLM as a Judge 没有在当前项目中落地。

报告中的“使用”不等于“精通”。只有在能够解释设计、独立修改实现、补充测试并处理故障时，才适合在简历中使用“熟练”或“具备经验”等强表述。

## 1 项目概览与核验方法

### 1.1 WorkPilot 是什么

WorkPilot 是一个面向企业跨系统办公流程的安全执行 Agent。用户提交自然语言目标后，系统先判断请求是否属于支持域，再生成结构化任务计划，将计划校验为有向无环图，按依赖顺序调用企业工具，并在高风险写操作前等待人工审批。执行结果还会经过远端状态验证、幂等账本、检查点和审计事件持久化。

它不是聊天机器人，也不是通用开放域 Agent。当前支持周报、会议跟进、Issue 汇总和故障恢复等受限流程。真实云模型、真实 GitHub 沙箱和生产环境效果需要外部凭证或生产运行数据，仓库没有把模拟结果包装成真实结果。

### 1.2 核验状态如何理解

| 状态 | 判定标准 | 简历表达建议 |
| --- | --- | --- |
| 已直接使用 | 依赖、业务源码和测试中都有明确实现 | 可以说明具体设计与代码，但仍应按个人掌握程度选择“熟悉”或“具备经验” |
| 部分关联 | 项目实现了相近机制，但没有使用该标准工具或完整方法 | 必须写成“理解并实现了类似机制”，不能直接写“使用了该框架” |
| 未使用 | 依赖和源码中没有落地证据 | 只能写“了解原理”，或者在补充项目后再升级表述 |

### 1.3 总体映射结论

按本报告拆分的 55 个技能点统计，36 项已直接使用，5 项部分关联，14 项未使用。强项集中在 Python 后端、可靠执行、结构化 Agent、可观测性、安全和评测；主要缺口集中在主流 Agent 框架、生产级向量模型、检索增强策略、多 Agent 和模型训练优化。

| 类别 | 已直接使用 | 部分关联 | 未使用 | 核心判断 |
| --- | ---: | ---: | ---: | --- |
| 编程与工程 | 11 | 0 | 2 | 后端工程证据完整，MySQL 和 Redis 无落地 |
| Agent 开发 | 7 | 1 | 4 | 自研 Plan and Execute 与 Temporal 编排较强，未用 LangChain LangGraph 和 Multi Agent |
| RAG 与知识检索 | 6 | 2 | 3 | 有完整基础管线和评测，但词法检索不是 BM25，也没有独立精排模型 |
| Agent 评测与稳定性 | 11 | 1 | 0 | 是项目最强部分，覆盖指标、Trace、恢复、安全和回归门禁 |
| LLM 基础与优化 | 1 | 1 | 5 | 有 Prompt 与结构化输出工程，没有训练和 LLM Judge |

### 1.4 项目主链路

用户请求进入 FastAPI 后，身份与租户信息先经过认证依赖。IntentGate 在模型调用之前过滤越权请求或要求澄清。StructuredPlanner 构造分层上下文，通过 ModelGateway 请求符合 TaskPlan JSON Schema 的候选计划，再用 Pydantic 和 DAG 规则做确定性校验。WorkPilotService 按拓扑顺序执行步骤，通过 PolicyEngine 判断风险，并在 R2 写操作前生成参数预览和哈希审批。执行器通过 CapabilityRegistry 找到对应 Adapter，先查询远端状态，再执行、验证并把结果写入 Action Ledger、Artifact、Timeline 和 Checkpoint。SQLAlchemy Repository 将完整状态写入 PostgreSQL，Temporal 负责跨等待点和进程重启的长任务控制流。

## 2 编程与工程

### 2.1 Python

**状态  已直接使用**

Python 是项目的主要实现语言。它适合构建 Agent 后端，因为异步网络库、数据校验、Web 框架、数据库 ORM、工作流 SDK 和 AI 生态都比较成熟。项目要求 Python 3.12，并使用类型注解、Protocol、dataclass、枚举、上下文管理器、异步函数和 Pydantic 模型组织代码。

项目不是把所有逻辑写在一个脚本里，而是按 API、Planner、Runtime、Policy、Connector、Repository、Workflow 和 Evaluation 分层。`workpilot/models.py` 定义领域模型和状态枚举，`workpilot/runtime.py` 实现核心执行循环，`workpilot/connectors/base.py` 用 Protocol 抽象工具适配器，`workpilot/model_gateway.py` 用 Protocol 隔离模型供应商。这些做法体现的是 Python 工程化，而不只是语法使用。

**代码证据**  `pyproject.toml`、`workpilot/models.py`、`workpilot/runtime.py`、`workpilot/connectors/base.py`。

### 2.2 FastAPI

**状态  已直接使用**

FastAPI 是基于 ASGI 的 Python Web 框架，核心价值是异步请求处理、类型驱动的参数校验、依赖注入和自动 OpenAPI 文档。它负责把 Agent 能力暴露为可调用、可鉴权、可观察的服务接口。

`workpilot/api.py` 中的 `create_app` 创建 FastAPI 应用，Pydantic 请求模型负责字段长度和类型约束，`Depends(tenant_context)` 注入租户与用户身份。应用实现任务创建、运行、审批、暂停、恢复、取消、知识文件、Memory、MCP、健康检查和 Prometheus 指标等接口，并通过 lifespan 管理 Temporal Client 与数据库资源。HTTP 中间件还为每次请求生成 request id、传播 Trace 上下文并记录延迟指标。

**代码证据**  `workpilot/api.py:50` 至 `workpilot/api.py:988`，入口为 `apps/api/main.py`。

### 2.3 异步任务

**状态  已直接使用**

异步编程用于避免网络等待阻塞线程；持久化异步任务系统则用于跨分钟、跨小时甚至跨进程保存执行状态。两者不是同一个概念。本项目同时使用 `async def` 处理 HTTP、模型和连接器 I O，并使用 Temporal 保存长任务控制流。

API 调用 `await service.create_task_async`，ModelGateway 使用 `httpx.AsyncClient`，Connector 的 `execute`、`lookup` 和 `verify` 都是异步接口。`workpilot/workflows/temporal.py` 定义持久 Workflow：任务等待审批时不会占住 Web 请求；Activity 配置超时、心跳和指数退避重试；Update 处理审批，Signal 处理暂停、恢复和取消。这里没有使用 Celery，异步任务的核心工具是 Temporal。

**代码证据**  `workpilot/api.py:374`、`workpilot/model_gateway.py:79`、`workpilot/workflows/temporal.py:40`、`workpilot/workflows/activities.py:9`。

### 2.4 RESTful API

**状态  已直接使用**

RESTful API 用资源、HTTP 方法、状态码和稳定数据结构表达系统能力。它的作用是让前端、脚本和外部系统以统一协议操作任务，而不是直接调用内部 Python 函数。

项目把任务设计为 `/v1/tasks` 资源，使用 POST 创建与触发动作，GET 查询，PATCH 更新 Memory，DELETE 删除知识文件。创建任务返回 201；不存在的任务返回 404；冲突和非法状态返回 409；认证失败返回 401 或 403。错误响应采用 Problem Details 风格，列表接口支持分页和状态过滤，SSE 使用 `Last-Event-ID` 续传时间线，创建接口支持 `Idempotency-Key`。

**代码证据**  `workpilot/api.py:323` 至 `workpilot/api.py:950`，API 回归见 `tests/test_api.py`。

### 2.5 SQLAlchemy

**状态  已直接使用**

SQLAlchemy 是 Python 的数据库 Toolkit 和 ORM。它把 Python 领域对象与关系数据库表连接起来，同时保留显式事务、查询和并发控制能力。它在本项目中的作用是让任务、步骤、审批、账本、验证、产物、事件和检查点能够跨进程重启恢复。

`workpilot/db/models.py` 使用 SQLAlchemy 2 的 `DeclarativeBase`、`Mapped` 和 `mapped_column` 定义规范化表结构。`SQLAlchemyTaskRepository` 使用 Session 事务保存聚合，读取时通过 `selectinload` 批量加载子表。保存任务时使用版本号作为更新条件；如果受影响行数不是 1，就抛出 `ConcurrentUpdateError`，这就是乐观锁。业务事件与 Outbox 在同一事务中写入，减少数据库状态已提交但事件丢失的风险。

**代码证据**  `workpilot/db/models.py`、`workpilot/db/repository.py:46` 至 `workpilot/db/repository.py:466`。

### 2.6 Alembic

**状态  已直接使用**

Alembic 是 SQLAlchemy 生态的数据库迁移工具。它用版本脚本记录 Schema 变化，使开发、测试和部署环境能够按同样顺序升级数据库，而不是依靠手工建表。

项目在 `alembic/versions` 中维护迁移。初始迁移创建任务、步骤、审批、账本、验证、产物、时间线、检查点和 Outbox 表；在 PostgreSQL 中为租户表启用并强制 Row Level Security。后续迁移增加账本恢复字段和 Planning Disposition。Docker Compose 启动 API 前执行 `alembic upgrade head`，CI 也在 SQLite 上执行迁移检查。

**代码证据**  `alembic/env.py`、`alembic/versions/20261009_0001_initial_v2_schema.py`、`deploy/docker-compose.yml:32` 至 `deploy/docker-compose.yml:37`。

### 2.7 MySQL

**状态  未使用**

MySQL 是常见关系数据库，适合事务型业务系统，但当前项目依赖和部署文件中没有 MySQL 驱动、连接串或兼容性测试。不能因为使用 SQLAlchemy 就推断项目支持 MySQL；不同数据库在 JSON、并发锁、迁移和行级安全能力上存在差异。

当前可诚实表述为“理解关系数据库与 ORM，项目落地 PostgreSQL 和 SQLite 开发回退”。如果要补齐 MySQL，需要加入驱动、迁移兼容测试、事务与隔离级别测试，并处理 PostgreSQL RLS 在 MySQL 中没有直接等价能力的问题。

### 2.8 PostgreSQL

**状态  已直接使用**

PostgreSQL 是本项目的生产向关系数据库。它除了保存事务数据，还通过 RLS 在数据库层隔离租户，即使应用查询漏写租户条件，数据库也会默认拒绝跨租户访问。

Repository 在每个 Session 中调用 `set_config('app.tenant_id', ...)` 设置事务级租户上下文；Alembic 为父表和子表创建 `USING` 与 `WITH CHECK` 策略，并使用 `FORCE ROW LEVEL SECURITY`。Docker Compose 使用 `pgvector/pgvector:pg16` 镜像，但当前知识向量仍保存在内存对象中，没有写入 pgvector。CI 中的真实 PostgreSQL 集成测试验证默认拒绝、跨租户读写阻断和所有租户表强制 RLS。

**代码证据**  `workpilot/db/repository.py:196`、`alembic/versions/20261009_0001_initial_v2_schema.py:30`、`tests/test_postgres_rls_integration.py`。

### 2.9 Redis

**状态  未使用**

Redis 常用于缓存、分布式锁、限流、会话、任务队列和短期状态。本项目的 `pyproject.toml` 没有 Redis 依赖，Compose 也没有 Redis 服务。API 的创建幂等缓存和 Memory 服务目前使用进程内字典，跨进程不会共享；持久任务和工作流状态分别由 PostgreSQL 与 Temporal 负责。

因此简历不能用 WorkPilot 证明 Redis 实战。若要补齐，可以优先实现跨实例的 Idempotency Key 缓存、速率限制或短期检索缓存，并为 TTL、缓存击穿和一致性补测试。

### 2.10 Linux

**状态  已直接使用**

Linux 能力在项目中主要体现在运行和交付环境，而不是某个 Python 类。Docker 镜像基于 `python:3.12-slim`，GitHub Actions 在 Ubuntu 上执行质量门禁，备份和恢复脚本使用 shell，Compose 和 Helm 也面向 Linux 容器运行时。

需要注意，拥有 Linux 部署文件不等于熟练系统运维。能够解释进程、权限、网络、端口、环境变量、文件挂载、健康检查、日志和资源限制，并能独立排障，才能支撑“掌握 Linux”的表述。

**代码证据**  `Dockerfile`、`.github/workflows/ci.yml`、`scripts/backup-postgres.sh`、`scripts/restore-drill-postgres.sh`。

### 2.11 Git

**状态  已直接使用**

Git 为代码版本、变更审查和回滚提供基础。项目包含提交历史、贡献规范、Pull Request 模板、Issue 模板和 GitHub Actions。每次文档或代码改动都要求配套测试并创建 commit，这让实现、验证和原因可以追踪。

项目中的 Git 证据属于工程流程，不是 Agent 运行时依赖。面试中应能演示分支、提交、差异审查、冲突解决和回滚，而不只是说“会用 Git”。

**代码证据**  `.git` 历史、`CONTRIBUTING.md`、`.github/pull_request_template.md`、`.github/workflows`。

### 2.12 Docker

**状态  已直接使用**

Docker 把应用及依赖封装为可复现镜像，Compose 用于编排本地多服务环境。`Dockerfile` 以 Python 3.12 slim 为基础，安装 WorkPilot 并启动模块入口。`deploy/docker-compose.yml` 同时编排 PostgreSQL、Temporal、API、Worker、OpenTelemetry Collector、Tempo、Prometheus、Alertmanager 和 Grafana，并用健康检查控制依赖顺序。

供应链工作流还构建镜像、运行 Trivy 高危漏洞扫描、生成 SPDX SBOM 并在主分支生成证明。Helm Chart 为 Kubernetes 部署提供 API、Worker、ServiceAccount、Pod 安全配置和基于队列积压的扩缩容模板。

**代码证据**  `Dockerfile`、`deploy/docker-compose.yml`、`deploy/helm/workpilot`、`.github/workflows/supply-chain.yml`。

### 2.13 Pytest

**状态  已直接使用**

Pytest 是项目的主要测试框架。它支持简洁断言、fixture、参数化、异步测试和测试发现。当前仓库有 27 个测试文件、143 个测试函数，覆盖 API、规划、DAG、策略、运行时、数据库、Temporal、MCP、知识检索、认证、安全、可观测性和部署资产。

测试分为快速单元和契约测试，以及需要外部本地服务的 PostgreSQL、Temporal、Playwright 集成测试。CI 使用 pytest coverage 并要求 `workpilot` 包覆盖率至少 85%。这比“写过几个单元测试”更接近工程化质量门禁。

**代码证据**  `tests`、`pyproject.toml` 的 pytest 与 coverage 配置、`.github/workflows/ci.yml:19` 至 `.github/workflows/ci.yml:30`。

### 2.14 编程与工程如何串联

FastAPI 接收 REST 请求，Pydantic 校验输入，异步函数调用 Planner、连接器和 Temporal；SQLAlchemy 在事务中保存状态，Alembic 演进 Schema，PostgreSQL RLS 守住租户边界；Docker 和 Linux 提供运行环境，Git 与 Pytest 把变更变成可审查、可回归的交付物。Redis 和 MySQL 不在这条真实链路中，应从当前项目技能证明中删除。

## 3 Agent 开发

### 3.1 ReAct

**状态  部分关联**

ReAct 的核心是让模型在推理、行动和观察之间循环：模型根据当前观察决定下一步工具，再把工具结果加入上下文继续推理。它适合环境不确定、必须边执行边探索的任务。

WorkPilot 有“执行工具后观察并验证”的循环，但计划在执行前已经生成，步骤顺序由 DAG 决定，模型不会在每一步读取观察后自由产生下一段 Thought 或 Action。因此它更接近 Planner Executor Verifier，而不是标准 ReAct。`runtime.py` 中的 `lookup`、`execute`、`verify` 可以视为行动和观察，但没有 ReAct Prompt 与逐步模型决策。

简历可写“理解 ReAct，并在项目中实现 Planner Executor Verifier 的受控工具执行闭环”，不应写“项目基于 ReAct 实现”。

### 3.2 Plan and Execute

**状态  已直接使用**

Plan and Execute 先把目标拆成计划，再由执行器按计划调用工具。它适合步骤较多、需要审批、依赖和恢复的企业任务，因为完整计划可以先接受安全校验。

`DemoPlanner` 为受支持意图生成确定性 TaskPlan；`StructuredPlanner` 通过模型生成候选计划。每个 `PlanStep` 包含 id、依赖、capability、风险、参数、审批要求和验证规则。`validate_plan` 检查循环依赖、缺失工具、风险篡改、步骤上限和审批规则。Runtime 使用 `topological_order` 按依赖执行，并在步骤成功后保存检查点。

**代码证据**  `workpilot/planner.py`、`workpilot/models.py:77`、`workpilot/dag.py`、`workpilot/runtime.py:324`。

### 3.3 LangGraph

**状态  未使用**

LangGraph 是用于构建有状态 Agent 图的框架，提供节点、边、状态、检查点和人工中断。WorkPilot 确实有 DAG、状态机、检查点和人工审批，但这些能力由自研领域模型、Runtime、SQLAlchemy 和 Temporal 实现，依赖中没有 LangGraph。

两者概念相似不能等同。简历可以说明“理解 LangGraph 的状态图思想，项目采用自研 DAG 加 Temporal 实现”，但不能把 WorkPilot 写成 LangGraph 项目。

### 3.4 LangChain

**状态  未使用**

LangChain 提供模型、Prompt、Retriever、Tool、Agent 和 Chain 等抽象。WorkPilot 没有安装 LangChain，模型网关、工具注册、上下文构建和 Retriever 都是自研边界。

自研实现的优势是安全约束和执行语义可控，代价是生态复用较少。若面试岗位明确要求 LangChain，需要另外做一个小型集成或适配器，而不是从现有代码推断已有经验。

### 3.5 任务编排

**状态  已直接使用**

任务编排解决步骤依赖、长时间等待、失败重试、暂停恢复和跨进程状态延续。项目有两层编排：DAG 负责业务步骤依赖，Temporal 负责持久控制流。

Runtime 在单次推进中按拓扑顺序执行可运行步骤；遇到审批会保存状态并返回。Temporal Workflow 反复调用 `advance_task` Activity，在 `WAITING_APPROVAL` 或 `PAUSED` 状态等待 Update 或 Signal。Activity 设置开始到关闭超时、心跳超时、指数退避和最大尝试次数。稳定 Workflow ID 避免同一租户任务被重复启动。

**代码证据**  `workpilot/dag.py`、`workpilot/workflows/temporal.py`、`workpilot/workflows/client.py`。

### 3.6 Tool Calling

**状态  已直接使用**

Tool Calling 是 Agent 选择并调用外部能力的机制。工具通常需要名称、参数 Schema、风险、可用通道和执行接口。WorkPilot 的工具不是模型供应商原生 tools 数组，而是内部 Capability Registry 与 Adapter 体系。

Planner 只能从 `registry.planning_tools()` 暴露的候选能力中选择。确定性校验拒绝不存在的工具和被模型降低的风险。Runtime 根据 capability 找 Adapter，生成 `ActionRequest`，依次调用 `preview`、`lookup`、`execute` 和 `verify`。Fake、GitHub 和 MCP Adapter 都遵循同一接口，因此工具实现可以替换，审批与账本规则保持不变。

**代码证据**  `workpilot/connectors/base.py`、`workpilot/runtime.py:342` 至 `workpilot/runtime.py:540`。

### 3.7 结构化输出

**状态  已直接使用**

结构化输出要求模型返回符合固定 Schema 的 JSON，而不是自由文本。它让程序能够验证字段、依赖、风险和参数，是 Agent 从 Demo 走向工程系统的关键边界。

`OpenAICompatibleModelGateway` 把 `TaskPlan.model_json_schema()` 作为严格 `json_schema` response format 发送。返回值先由 `TaskPlan.model_validate` 验证，再由 `validate_plan` 做语义校验。首次失败时，Planner 把验证错误加入 repair 消息并只允许修复一次；第二次仍失败或模型网关异常时，回退到确定性 DemoPlanner。Prompt 版本、Schema 版本、验证错误和模型调用记录都会保存。

**代码证据**  `workpilot/model_gateway.py:171` 至 `workpilot/model_gateway.py:250`、`workpilot/planner.py:336` 至 `workpilot/planner.py:415`。

### 3.8 上下文管理

**状态  已直接使用**

上下文管理决定哪些信息进入模型、信任级别是什么、超出 Token 预算时保留什么。它的目标不是把所有历史都塞进 Prompt，而是在安全、相关性和成本之间做选择。

`ContextBuilder` 将系统不变量、用户目标、组织策略、候选工具、历史摘要和检索内容分层。每个 ContextItem 带 source、trust、priority、ACL、时间和过期字段。构建时按优先级选择内容，超出预算的来源记录在 omitted 列表；不可信内容被包在 `external_data` 标签中，检测到 Prompt Injection 时记录来源。`select_candidate_tools` 还会先缩小工具集合。

**代码证据**  `workpilot/context.py`、`workpilot/planner.py:344` 至 `workpilot/planner.py:352`。

### 3.9 状态持久化

**状态  已直接使用**

状态持久化使任务在 API 或 Worker 重启后仍能继续。需要保存的不只是最终结果，还包括计划版本、每步状态、审批、账本、验证、产物、时间线和检查点。

`TaskRun` 聚合这些领域状态，`SQLAlchemyTaskRepository` 把它们拆入规范化表。每次关键状态变化都在乐观锁保护下保存；事件同时写入 Outbox。Temporal 保存 Workflow 控制状态，数据库保存业务事实，两者通过稳定 task id 关联。`tests/test_persistence.py` 验证 Repository 与 Worker 重启后的任务恢复和陈旧写入拒绝。

**代码证据**  `workpilot/models.py:188`、`workpilot/db/models.py`、`workpilot/db/repository.py`。

### 3.10 MCP 协议

**状态  已直接使用**

MCP 用标准方式让客户端发现和调用工具。项目实现最小 JSON RPC MCP Server 和 Client Adapter，覆盖 `tools/list` 与 `tools/call`，并把 MCP 工具接入统一 Connector 接口。

Server 只暴露 R0 只读能力，写工具不会出现在发现结果中。Client 固定预期 server id，校验风险和工具描述，对完整 Tool Schema 计算指纹；后续发现若发生变化就拒绝，防止工具定义被替换。调用响应还校验 server identity，网络超时和错误转换为可重试 ConnectorError。当前是本地 HTTP JSON RPC，没有外部 MCP OAuth discovery 和短期凭证验收。

**代码证据**  `workpilot/mcp.py`、`workpilot/api.py:232`、`tests/test_mcp.py`。

### 3.11 Multi Agent 路由

**状态  未使用**

Multi Agent 路由是根据任务类型、权限或模型专长，把子任务分配给不同 Agent。当前项目只有一个 Structured Planner 和一个确定性 Executor Verifier，步骤不是独立 Agent，也没有 Supervisor Worker 对话。

`docs/adr/003-single-agent-before-multi-agent.md` 明确决定先保留单 Agent DAG。原因是现有评测没有证明 Multi Agent 能改善质量、成本或恢复能力，而它会增加上下文复制、Token、Trace、授权和故障处理复杂度。并行度由 DAG 和 Temporal Activity 表达，不应写成 Multi Agent 路由。

### 3.12 Handoff

**状态  未使用**

Handoff 是一个 Agent 把任务、上下文和控制权交给另一个 Agent，通常还要定义交接 Schema、权限委托、回收条件和 Trace 关联。WorkPilot 没有 Agent 间 Handoff。

当前存在的 Planner 到 Executor、API 到 Temporal、Runtime 到 Adapter 都是组件调用或工作流调度，不是 Agent Handoff。只有未来引入独立权限域或不同模型专长，并完成相同数据集上的消融实验后，才适合增加该能力。

### 3.13 Agent 开发如何串联

WorkPilot 先由 IntentGate 控制支持域，再由 StructuredPlanner 生成结构化 TaskPlan，用 DAG 校验固定计划边界；ContextBuilder 控制模型输入，Capability Registry 提供工具，Runtime 执行和验证，Temporal 管理长任务等待，SQLAlchemy 保存状态，MCP 提供受限工具互操作。它是自研的单 Agent Plan and Execute 系统，不是 LangChain、LangGraph、ReAct 或 Multi Agent 项目。

## 4 RAG 与知识检索

### 4.1 文档解析

**状态  已直接使用**

文档解析把 PDF、Word、Excel 和文本转成可检索内容，同时保留页码、工作表等引用定位信息。项目支持 PDF、DOCX、XLSX、Markdown 和 UTF 8 文本。

PDF 使用 PyMuPDF 按页提取；DOCX 使用 python docx 提取段落和表格；XLSX 使用 openpyxl 逐工作表读取。上传前还检查扩展名、文件签名、大小、PDF 页数、Excel 行数、OOXML 解压后体积、宏文件和 EICAR 测试签名。原始文件保存到 ObjectStore，引用可以重新打开原文核验。

**代码证据**  `workpilot/knowledge.py:24`、`workpilot/knowledge.py:154`、`workpilot/knowledge.py:305` 至 `workpilot/knowledge.py:404`。

### 4.2 分块

**状态  已直接使用**

分块把长文档切成适合 Embedding 和召回的小单元。块过大容易混入无关内容，块过小会丢失上下文，重叠用于保留边界信息。

`_split_text` 先归一化空格，再按 900 个字符切分，每块重叠 120 个字符。每个 KnowledgeChunk 保存 document id、tenant、owner、visibility、ordinal、文本、页码或工作表、Prompt Injection 标记和向量。当前是固定字符分块，没有按标题层级、句子或 Token 自适应，也没有分块策略对比实验。

**代码证据**  `workpilot/knowledge.py:321` 至 `workpilot/knowledge.py:345`、`workpilot/knowledge.py:407` 至 `workpilot/knowledge.py:419`。

### 4.3 Embedding 选型

**状态  部分关联**

Embedding 把文本映射为向量，语义相近的文本在向量空间中距离更近。选型通常需要比较语言覆盖、维度、领域效果、延迟、成本和部署方式。

项目实现 `HashEmbeddingGateway` 作为可复现离线基线：对 Token 做 SHA 256 哈希，将正负计数写入 128 维向量并归一化。它能验证向量检索接口、余弦相似度和评测流程，但不是真实语义 Embedding，也没有比较 BGE、E5 或云模型。因此可以证明“理解 Embedding 接口和评测方法”，不能证明“完成生产 Embedding 选型”。

**代码证据**  `workpilot/knowledge.py:124` 至 `workpilot/knowledge.py:150`。

### 4.4 BM25

**状态  未使用**

BM25 是基于词频、逆文档频率和文档长度归一化的经典概率检索算法。它对关键词、专有名词和编号检索很有效。

WorkPilot 的 `_lexical_score` 只计算查询 Token 与文档 Token 的重合次数，并用文档 Token 总数平方根做归一化。代码没有语料级文档频率、IDF、BM25 的 k1 或 b 参数，所以不能称为 BM25。当前准确表述应为“自定义词法召回”。

**代码证据**  `workpilot/knowledge.py:422` 至 `workpilot/knowledge.py:430`。

### 4.5 向量与混合召回

**状态  已直接使用**

向量召回按语义相似度排序，词法召回按关键词匹配排序。混合召回结合两者，降低单一路径漏召回的风险。

`KnowledgeService.search` 先在 ACL 过滤后的 Chunk 上分别计算词法排名和余弦向量排名。`hybrid_rrf` 使用 Reciprocal Rank Fusion，将两路名次转换为 `1 / (60 + rank)` 后相加。返回 Citation 时同时保存 lexical rank、vector rank、融合分数、原文预览、页码或工作表和注入标记。

当前向量是离线 Hash Embedding，索引在进程内存中，不是 pgvector、Milvus 或 Elasticsearch 生产索引。

**代码证据**  `workpilot/knowledge.py:237` 至 `workpilot/knowledge.py:303`。

### 4.6 Rerank 精排

**状态  部分关联**

Rerank 通常在初步召回后，用 Cross Encoder 或 LLM 对较小候选集重新打分，提高前几名相关性。它比召回模型慢，但能看到 Query 与文档的联合表示。

项目没有独立 Reranker，也没有两阶段的 top N 召回再精排。RRF 只是把词法和向量名次融合为最终排序，可以视为轻量排序融合，但不能称为 Cross Encoder 精排。简历应写“实现词法与向量 RRF 融合”，不要写“实现 Rerank 模型”。

### 4.7 Query Rewriting

**状态  未使用**

Query Rewriting 使用规则或模型把模糊问题改写成更适合搜索的查询，例如补全指代、拆分多问题或生成同义表达。当前 `KnowledgeService.search` 直接对原始 query 分词和向量化，没有改写阶段、多个候选查询或改写质量评测。

项目中的 `select_candidate_tools` 是工具候选筛选，不是 RAG Query Rewriting，不能混为一谈。

### 4.8 HyDE

**状态  未使用**

HyDE 先让 LLM 生成一段假设答案，再对假设答案做 Embedding，用它去召回真实文档。它可能改善短问题的语义召回，但会增加模型调用成本，并可能引入错误方向。

当前代码没有生成假设文档，也没有 HyDE 与原始 Query 的对照评测，因此只能写“了解原理”，不能写“项目应用 HyDE”。

### 4.9 Recall at K

**状态  已直接使用**

Recall at K 衡量前 K 个结果是否覆盖相关文档。当前数据集每个 Case 只有一个相关文件，所以实现把相关文件出现在前 5 名记为 1，否则为 0，再对所有 Case 求平均。

`workpilot/retrieval_evaluation.py` 对 lexical、vector 和 hybrid rrf 三种模式计算 `recall_at_5`。这能比较召回路径，但数据集只有 10 条离线事实 Case，不能代表真实企业语料泛化效果。

### 4.10 MRR

**状态  已直接使用**

MRR 即 Mean Reciprocal Rank，关注第一个相关结果的位置。相关结果排第 1 得 1，排第 2 得 0.5，未召回得 0。它适合每个问题只有一个主要正确结果的检索任务。

项目计算每个 Case 的 `1 / rank` 并求平均，报告三种检索模式的 MRR。实现简单明确，与当前单相关文档数据集匹配。

**代码证据**  `workpilot/retrieval_evaluation.py:31` 至 `workpilot/retrieval_evaluation.py:56`。

### 4.11 NDCG

**状态  已直接使用**

NDCG 衡量排序质量，并对靠前的相关结果给予更高权重。完整 NDCG 可以支持多级相关性；本项目每个 Case 只有一个二元相关文档，因此计算 `1 / log2(rank + 1)`，未命中为 0。

报告字段为 `ndcg_at_5`。它是当前数据集条件下的简化且正确的形式，但不能证明项目已经处理多文档、多级相关性标注。

### 4.12 证据引用

**状态  已直接使用的扩展能力**

虽然原简历没有单列 Citation，WorkPilot 的 RAG 管线会返回文件名、Chunk、页码或工作表、预览、两路排名和融合分数。评测还计算 `citation_precision_at_1`，判断第一个引用是否来自相关文档。原始文件接口允许用户重新打开来源。

这使 RAG 结果具有可核验性，但项目还没有评测最终生成答案中的每个主张是否被引用支持。

### 4.13 RAG 如何串联

文件先通过安全校验和类型解析，再按固定窗口分块，生成离线 Hash Embedding；查询先做 ACL 过滤，再分别进行自定义词法召回和向量召回，使用 RRF 融合名次，最后返回可打开原文的 Citation。离线评测计算 Recall at 5、MRR、NDCG at 5 和 Citation Precision at 1。BM25、真实 Embedding 选型、Cross Encoder Rerank、Query Rewriting 和 HyDE 不在当前链路中。

## 5 Agent 评测与稳定性

### 5.1 Trace

**状态  已直接使用**

Trace 把一次请求中的 HTTP、规划、策略、工具查找、执行、验证和模型调用串起来，帮助定位错误发生在哪一层。项目使用 OpenTelemetry Span，并在内存中保留可测试的 SpanRecord。

HTTP 中间件提取 `traceparent`，记录 `http.request`；Runtime 记录 `task.run`、`policy.evaluate`、`tool.lookup`、`tool.execute` 和 `tool.verify`；ModelGateway 记录 `model.plan`、Token、模型、Prompt 版本和 Schema 版本。OTLP 可以把 Trace 发给 Collector 和 Tempo，Grafana 用于查看。

**代码证据**  `workpilot/telemetry.py`、`workpilot/api.py:280`、`workpilot/runtime.py:344`、`deploy/observability`。

### 5.2 Bad Case 分析

**状态  已直接使用**

Bad Case 分析不是只看总分，而是保留失败样本、失败阶段和分类，再把修复后的结果与基线比较。项目的评测结果记录 case id、repetition、metrics、failures 和 trace，并汇总 failure taxonomy。

`evals/reports/baseline-v1` 保存修复前跨域误规划基线，`intent-gated-v2` 保存加入支持域门后的结果。Model Comparison 还输出逐 Case 候选、验证错误、是否修复、是否回退和匿名盲审包。这样可以从失败类型回到具体计划与模型调用，而不是只展示最好的一次结果。

### 5.3 评测集

**状态  已直接使用**

评测集把输入、期望工具、禁止动作、审批要求、允许结果和评分权重版本化，使 Agent 修改能够回归。主任务集有 60 条 Case，默认每条重复 3 次；安全集有 20 条策略 Case；检索集有 10 条固定事实 Case。

加载主评测集时计算 SHA 256，并检查 Case id 唯一。报告保存数据集摘要、Planner、重复次数、分类结果和 Wilson 区间。固定数据集能发现回归，但仍需要真实模型、真实业务数据和人工标注扩展外部有效性。

**代码证据**  `evals/datasets/workpilot-v1.jsonl`、`evals/security_cases.jsonl`、`evals/retrieval_cases.jsonl`、`workpilot/evaluation.py`。

### 5.4 任务成功率

**状态  已直接使用**

任务成功率表示满足所有任务条件的运行比例。项目的离线评测只有在要求的工具、审批、安全、DAG 和 Disposition 指标都通过时才把 Case 标为 passed，并按整体和类别计算 pass rate。

在线运行时，只有所有步骤状态都为 SUCCEEDED 且远端验证通过，任务才进入 SUCCEEDED。Telemetry 记录 `task_success_total`、终态失败和任务延迟。离线 180 次确定性回归不能表述成生产任务成功率。

### 5.5 工具调用准确率

**状态  已直接使用**

工具调用准确率需要同时看召回和精度。漏选必需工具会降低 tool recall，选择禁止工具会降低 tool precision，并可能触发 unauthorized write。

`grade_plan` 比较计划 capability 与 Case 的 required、forbidden 集合，计算 `tool_recall`、`tool_precision`、`approval_recall`、`r3_block`、`unauthorized_write` 和 `safety_pass`。安全门禁要求 Schema、DAG、Disposition、Safety 和 R3 阻断为 1，未授权写入为 0。

**代码证据**  `workpilot/evaluation.py:232` 至 `workpilot/evaluation.py:279`。

### 5.6 证据有效率

**状态  部分关联**

证据有效率通常衡量回答中的证据是否真实存在、能否打开、是否支持对应主张。WorkPilot 已实现两个相邻指标：工具步骤验证必须带 Artifact Evidence Ref；检索评测计算 Citation Precision at 1。

但项目没有对最终自然语言回答做 Claim Citation 对齐，也没有统计完整的“有效证据数除以引用证据数”。因此可以说“实现可核验引用和引用准确率基线”，不应声称已有完整证据有效率体系。

### 5.7 延迟指标

**状态  已直接使用**

延迟决定 Agent 是否可用，也能暴露模型、工具和数据库瓶颈。项目记录 API、任务、模型、知识索引等延迟直方图；模型对比报告计算运行延迟 P50 和 P95，并结合 Token 与成本分析。

`MetricsRegistry` 提供 Prometheus counter 和 histogram，默认桶覆盖毫秒到分钟级。基准脚本还生成 API 吞吐和延迟报告，但 in process ASGI 基准不能当作生产容量。

**代码证据**  `workpilot/telemetry.py`、`workpilot/model_evaluation.py:361` 至 `workpilot/model_evaluation.py:447`、`benchmarks/api_load.py`。

### 5.8 超时与重试

**状态  已直接使用**

超时防止外部调用无限等待，重试用于处理短暂网络错误和限流。安全重试必须区分“确定失败”和“结果未知”，否则可能重复产生副作用。

模型调用取 Provider 超时与总预算的较小值，对 429、5xx、网络错误和超时进行有限重试并指数退避。Connector Action 带 60 秒 deadline；Runtime 对 retryable 错误计算下一次重试时间。Temporal Activity 有开始到关闭超时、心跳超时、指数退避和最多 5 次尝试。

**代码证据**  `workpilot/model_gateway.py:203` 至 `workpilot/model_gateway.py:269`、`workpilot/runtime.py:430` 至 `workpilot/runtime.py:494`、`workpilot/workflows/temporal.py:11` 至 `workpilot/workflows/temporal.py:20`。

### 5.9 幂等

**状态  已直接使用**

幂等意味着同一操作重复提交不会产生重复业务副作用。WorkPilot 在 API、Workflow、Action 和事件消费四层处理幂等。

创建任务接受 `Idempotency-Key`；Temporal 使用稳定 Workflow ID 并忽略 Already Started；Runtime 根据 tenant、task、step、capability 和参数生成稳定 Action Key，在调用前预占 Ledger；Adapter 支持远端幂等与 `lookup`；Outbox Consumer 按 event id 去重。测试包含同一动作 100 次投递只产生一个远端对象的场景。

**代码证据**  `workpilot/security.py`、`workpilot/runtime.py:394`、`workpilot/workflows/client.py:18`、`workpilot/outbox.py:63`。

### 5.10 断点恢复

**状态  已直接使用**

断点恢复要求系统在进程中断后知道哪些步骤已完成、哪些动作可能已执行、从哪里继续。项目每个安全边界和副作用后保存 Checkpoint，其中包含任务状态、计划版本、已完成步骤和 Ledger Keys。

动作执行前先把 RESERVED Ledger 持久化。如果调用后连接中断，状态标记 UNKNOWN 和 REQUIRED；下次运行先调用 Adapter `lookup` 查询远端，而不是直接重试写操作。Temporal History 保存控制流，Activity 心跳暴露推进阶段。真实 Temporal 本地服务的故障注入报告验证 Worker 重启后的继续执行。

**代码证据**  `workpilot/runtime.py:394` 至 `workpilot/runtime.py:541`、`workpilot/runtime.py:699`、`workpilot/workflows/temporal.py`。

### 5.11 权限隔离

**状态  已直接使用**

权限隔离防止用户、租户、工具或凭证越界。项目同时使用 API 认证、RBAC、Repository 租户条件、PostgreSQL RLS、知识 ACL、工具风险和 Secret 边界。

OIDC Verifier 校验 Token 并生成 Principal；接口检查 owner、approver 和 admin 角色。Repository 查询显式带 tenant id，PostgreSQL 再用 RLS 做第二层保护。知识文件按 tenant、owner 和 private 或 tenant visibility 在排序前过滤。高风险能力进入审批，R3 被拒绝，GitHub Token 保存在 SecretStore 并只在 Adapter 边界读取。

**代码证据**  `workpilot/auth.py`、`workpilot/api.py:105`、`workpilot/db/repository.py:76`、`workpilot/knowledge.py:246`、`workpilot/policy.py`。

### 5.12 Prompt Injection 防护

**状态  已直接使用**

Prompt Injection 是不可信内容试图改变系统指令、绕过审批或窃取秘密。项目采用分层防护，而不是只依靠一句 Prompt。

IntentGate 在模型调用前拒绝越权和绕过审批请求；ContextBuilder 为来源标注 trust，把外部内容包入 `external_data`，并记录注入模式；Knowledge Chunk 保存注入标记；MCP Client 检查工具描述中的投毒词并固定 Schema 指纹；模型只生成候选计划，风险、DAG、收件人域、审批和权限由确定性代码重新校验。

当前检测主要基于规则，对变体和语义攻击覆盖有限，因此报告将其称为安全基线，不等同于完整红队或渗透测试。

**代码证据**  `workpilot/planner.py:63`、`workpilot/context.py:40`、`workpilot/mcp.py:109`、`workpilot/security_evaluation.py`。

### 5.13 评测与稳定性如何串联

每次运行产生 Trace、指标、Timeline、Artifact 和 Checkpoint；固定评测集把目标工具、安全边界和成功条件转成可重复指标；Bad Case 与 Failure Taxonomy 反馈给 IntentGate、Prompt、Schema 和确定性校验；超时重试、幂等账本、lookup before retry、Temporal 和 PostgreSQL 共同保证故障后恢复；认证、RLS、ACL、审批和 Prompt Injection 防护限制错误影响范围。这一类是 WorkPilot 最完整、最适合面试深入讲解的能力。

## 6 LLM 基础与优化

### 6.1 Transformer

**状态  未在代码中实现**

Transformer 通过自注意力和前馈网络处理 Token 序列，是主流大模型的基础架构。应用项目通常调用已有模型，不会自己实现 Transformer。WorkPilot 没有训练代码、模型权重、Tokenizer 或 Attention 实现。

项目可以证明你理解如何使用模型边界，但不能用来证明 Transformer 底层实现经验。面试中应从 Attention、位置编码、上下文窗口和生成过程解释原理，再说明它们如何影响 Token 预算、延迟和上下文管理。

### 6.2 Prompt Engineering

**状态  已直接使用**

Prompt Engineering 是用系统约束、任务上下文、工具描述、输出 Schema 和示例组织模型输入。有效 Prompt 必须与程序校验结合，不能把权限和安全完全交给模型。

ContextBuilder 的系统不变量要求只生成 TaskPlan、不执行工具、不泄露秘密、不改变授权和风险；用户目标、组织策略和工具 Schema 分层进入消息。StructuredPlanner 在候选校验失败时追加包含错误原因的修复指令，并限制一次修复。Prompt version 和 Schema version 写入 ModelCallRecord，便于回归比较。

**代码证据**  `workpilot/context.py:72` 至 `workpilot/context.py:142`、`workpilot/planner.py:381` 至 `workpilot/planner.py:395`。

### 6.3 Few shot

**状态  未使用**

Few shot 是在 Prompt 中提供少量输入输出示例，让模型学习格式或决策模式。当前 Planner Context 只有规则、目标、策略和工具列表，没有示例计划，也没有 zero shot 与 few shot 对照实验。

如果未来增加 Few shot，应从评测集选择不泄漏测试答案的训练示例，控制 Token 成本，并比较 Schema 通过率、工具准确率、安全和延迟。

### 6.4 Function Calling

**状态  部分关联**

模型供应商原生 Function Calling 通常把 tools 或 functions Schema 传给模型，模型返回函数名与参数。WorkPilot 的 Provider 请求只使用 `response_format=json_schema` 生成完整 TaskPlan，没有传原生 tools 数组，也没有接收 tool call 对象。

项目确实有 Tool Calling，但工具选择先写进 TaskPlan，再由自研 Runtime 调用 Capability Adapter。因此准确表述是“使用 JSON Schema 结构化规划并实现内部工具调用框架”，而不是“使用模型原生 Function Calling API”。

### 6.5 SFT

**状态  未使用**

SFT 即监督微调，用输入与理想输出样本更新模型参数，使模型适应特定任务和格式。项目没有训练数据流水线、训练脚本、Checkpoint、训练指标或微调模型部署。评测集用于回归，不等于 SFT 数据集。

当前只能写“了解 SFT 原理与适用场景”。如果未来补充，应明确数据来源、切分、防泄漏、训练配置、基座模型、对照组和离线安全评测。

### 6.6 LoRA 与 QLoRA

**状态  未使用**

LoRA 冻结基座权重，只训练低秩适配矩阵；QLoRA 进一步量化基座模型以降低显存需求。两者属于参数高效微调方法。

WorkPilot 没有 PEFT、bitsandbytes、训练 GPU 配置或 Adapter 权重，因此没有 LoRA QLoRA 落地。调用云模型和配置 ModelGateway 不能视为模型微调。

### 6.7 LLM as a Judge

**状态  未使用**

LLM as a Judge 使用另一个模型按评分 Rubric 评价回答质量。它适合难以完全规则化的帮助度、完整性和事实一致性，但必须处理 Judge 偏差、位置偏差、模型自偏好和成本。

WorkPilot 的主评测是确定性规则打分，Model Comparison 会生成匿名人工盲审包，但没有调用 Judge 模型。人工 blind review 与 LLM Judge 不是同一方法。简历只能写“了解 LLM as a Judge”，不能说项目已实现。

### 6.8 LLM 能力如何串联

当前 LLM 链路重点是应用工程：Prompt 和可信上下文进入 OpenAI Compatible Gateway，模型按 JSON Schema 返回 TaskPlan，Pydantic 与 DAG 规则验证，失败只修复一次，再回退确定性 Planner。Transformer、Few shot、原生 Function Calling、SFT、LoRA QLoRA 和 LLM Judge 都不是这条链路的一部分。

## 7 五类技能在 WorkPilot 中的完整链路

### 7.1 从请求到计划

FastAPI 接收任务请求，Pydantic 校验字段，OIDC 或本地身份依赖生成租户上下文。IntentGate 先判断请求是可执行、需要澄清还是拒绝。对于模型规划模式，ContextBuilder 根据 Token 预算组合系统规则、目标、租户策略和候选工具；ModelGateway 请求严格 TaskPlan Schema；Planner 对结果做 Pydantic 和 DAG 校验。

### 7.2 从计划到安全执行

Runtime 按拓扑序选择依赖已完成的步骤。PolicyEngine 比较模型声明风险与 Registry 固定风险，R2 操作必须生成预览并等待参数哈希审批，R3 直接拒绝。审批通过后，Runtime 计算稳定幂等键并预占 Ledger，先查询远端，再执行 Adapter，最后独立验证远端状态。

### 7.3 从执行到恢复

步骤执行、验证、Artifact、Timeline 和 Checkpoint 通过 SQLAlchemy 事务写入数据库，并使用乐观锁防止并发覆盖。Outbox 与业务事件同事务写入，再由 Relay 至少一次发布。Temporal 保存等待审批、暂停和取消的控制流，Worker 重启后可继续推进。结果未知时必须先 lookup，避免盲目重试产生重复副作用。

### 7.4 从知识到证据

文件经过安全校验、解析、固定窗口分块和离线向量化。检索时先做 ACL 过滤，再执行词法和向量两路召回，以 RRF 融合并返回 Citation。引用包含来源定位和排名，检索评测用 Recall at 5、MRR、NDCG at 5 和 Citation Precision at 1 验证。

### 7.5 从运行到评测闭环

OpenTelemetry 将 HTTP、Planner、Policy、Tool 和 Model 调用串成 Trace；Prometheus 指标记录成功、错误、延迟、Token 和成本；版本化数据集重复运行并输出分类指标和 Failure Taxonomy；历史失败基线与修复后结果共同证明改动效果。安全门禁进入 CI，代码改动必须通过 Ruff、mypy、pytest、覆盖率和 Alembic 迁移检查。

## 8 逐项证据索引

| 技能 | 状态 | 首要代码证据 | 最关键测试或报告 |
| --- | --- | --- | --- |
| Python FastAPI REST | 已直接使用 | `workpilot/api.py` | `tests/test_api.py` |
| 异步任务 Temporal | 已直接使用 | `workpilot/workflows` | `tests/test_temporal_workflow.py` |
| SQLAlchemy Alembic PostgreSQL | 已直接使用 | `workpilot/db` `alembic/versions` | `tests/test_persistence.py` `tests/test_postgres_rls_integration.py` |
| Docker Linux Git | 已直接使用 | `Dockerfile` `deploy` `.github` | `tests/test_deployment_assets.py` |
| Pytest | 已直接使用 | `tests` | CI coverage gate |
| Plan and Execute | 已直接使用 | `workpilot/planner.py` `workpilot/runtime.py` | `tests/test_runtime.py` |
| LangChain LangGraph | 未使用 | 无依赖 | ADR 使用自研 DAG 与 Temporal |
| ReAct | 部分关联 | `workpilot/runtime.py` | 无标准 ReAct 循环测试 |
| Tool Calling | 已直接使用 | `workpilot/connectors/base.py` | `tests/test_runtime.py` |
| 结构化输出 | 已直接使用 | `workpilot/model_gateway.py` | `tests/test_model_planning.py` |
| 上下文管理 | 已直接使用 | `workpilot/context.py` | `tests/test_model_planning.py` |
| 状态持久化 | 已直接使用 | `workpilot/db/repository.py` | `tests/test_persistence.py` |
| MCP | 已直接使用 | `workpilot/mcp.py` | `tests/test_mcp.py` |
| Multi Agent Handoff | 未使用 | `docs/adr/003-single-agent-before-multi-agent.md` | 无 |
| 文档解析与分块 | 已直接使用 | `workpilot/knowledge.py` | `tests/test_knowledge.py` |
| Embedding 选型 | 部分关联 | `HashEmbeddingGateway` | 离线 Hash 基线 |
| BM25 | 未使用 | `_lexical_score` 为自定义词频重合 | 无 BM25 参数或 IDF |
| 混合召回 | 已直接使用 | `KnowledgeService.search` | `tests/test_retrieval_evaluation.py` |
| Rerank | 部分关联 | RRF 排序融合 | 无独立 Reranker |
| Query Rewriting HyDE | 未使用 | 无对应阶段 | 无 |
| Recall MRR NDCG | 已直接使用 | `workpilot/retrieval_evaluation.py` | `evals/reports/retrieval-v1` |
| Trace 与延迟 | 已直接使用 | `workpilot/telemetry.py` | `tests/test_telemetry.py` |
| Bad Case 与评测集 | 已直接使用 | `workpilot/evaluation.py` | `evals/reports` |
| 工具准确率 | 已直接使用 | `grade_plan` | `tests/test_evaluation.py` |
| 证据有效率 | 部分关联 | Citation 与 Verification | `citation_precision_at_1` |
| 超时重试 幂等 恢复 | 已直接使用 | `runtime.py` `temporal.py` | `tests/test_runtime.py` |
| 权限隔离与注入防护 | 已直接使用 | `auth.py` `security.py` `context.py` | 安全和 RLS 测试 |
| Prompt Engineering | 已直接使用 | `context.py` `planner.py` | 结构化规划测试 |
| Transformer Few shot SFT LoRA QLoRA LLM Judge | 未使用 | 无训练或 Judge 代码 | 无 |
| Function Calling | 部分关联 | JSON Schema 加内部 Adapter | 未使用 Provider 原生 tools |

## 9 简历表述校准

### 9.1 当前项目能够有力支撑的表述

可以写：使用 Python 与 FastAPI 构建异步 REST API；基于 SQLAlchemy、Alembic 和 PostgreSQL RLS 实现多租户状态持久化；使用 Temporal、幂等账本、检查点和 lookup before retry 设计可恢复任务执行；实现结构化 Plan and Execute、Tool Calling、MCP 只读安全边界、上下文信任标签和 Prompt Injection 基线防护；实现文件解析、分块、离线向量与词法混合召回、RRF 融合和 Recall at 5、MRR、NDCG at 5 评测；使用 OpenTelemetry、Prometheus 和版本化评测集建立质量回归。

### 9.2 应降低强度或改写的表述

“熟悉 ReAct”可以保留为理论理解，但项目表述应改成“实现 Planner Executor Verifier 闭环”。“LangGraph LangChain”不应与 WorkPilot 绑定。“掌握 BM25 与 Rerank”应改成“实现自定义词法与向量召回，并使用 RRF 融合；了解 BM25 与 Cross Encoder Rerank”。“Embedding 选型”应改成“实现可替换 Embedding 边界和离线 Hash 基线”。“Function Calling”应说明是内部 Adapter Tool Calling，不是模型原生 Function Calling。

### 9.3 当前项目不能支撑的表述

MySQL、Redis、LangChain、LangGraph、Multi Agent 路由、Handoff、BM25、Query Rewriting、HyDE、Few shot、SFT、LoRA QLoRA 和 LLM as a Judge 都没有实际落地。Transformer 属于基础原理，不应写成项目实现。这些内容如果仍放在专业技能中，建议统一使用“了解原理”，并准备清楚说明没有在 WorkPilot 中使用。

### 9.4 基于当前仓库的推荐专业技能版本

> **编程与工程**  使用 Python 与 FastAPI 开发异步 REST API，基于 SQLAlchemy、Alembic 和 PostgreSQL RLS 实现多租户持久化；使用 Docker Compose、GitHub Actions、Ruff、mypy 与 Pytest 完成交付和质量门禁。
>
> **Agent 开发**  实现结构化 Plan and Execute、DAG 校验、Tool Calling、上下文信任与状态持久化；基于 Temporal 实现审批等待、暂停恢复和故障重试，并实现只读 MCP Server Client 安全闭环。理解 ReAct、LangGraph、LangChain 和 Multi Agent 协作模式。
>
> **RAG 与知识检索**  实现 PDF DOCX XLSX 文档解析、重叠分块、离线向量与词法混合召回、RRF 融合和可核验 Citation；使用 Recall at 5、MRR、NDCG at 5 与 Citation Precision at 1 进行离线评测。了解 BM25、Cross Encoder Rerank、Query Rewriting 和 HyDE。
>
> **Agent 评测与稳定性**  使用 OpenTelemetry Trace、Prometheus 指标、版本化评测集与 Failure Taxonomy 分析 Bad Case；实现超时重试、幂等账本、lookup before retry、检查点恢复、OIDC RBAC、PostgreSQL RLS 与 Prompt Injection 基线防护。
>
> **LLM 基础与优化**  使用版本化 Prompt、Token 成本预算和 JSON Schema 结构化输出构建可替换 ModelGateway；理解 Transformer、Few shot、Function Calling、SFT、LoRA QLoRA 和 LLM as a Judge 的原理与适用边界。

这份推荐版本只描述仓库能够证明的技术。是否使用“熟练”“掌握”仍取决于你能否独立解释、修改和排障，不应只因为项目里出现过某个依赖就使用强表述。

## 10 建议的补强顺序

### 10.1 第一优先级 真实 RAG

接入一个真实中文或多语言 Embedding Provider，把向量持久化到 pgvector；引入标准 BM25 实现；增加 Cross Encoder Reranker；把检索集扩展到多相关文档和困难负例。完成后才能把“Embedding 选型、BM25、Rerank”升级为项目经验。

### 10.2 第二优先级 主流 Agent 框架对照

用 LangGraph 复刻一条现有审批流程，并与自研 Runtime 比较状态表示、检查点、可观测性、恢复和代码复杂度。保留同一数据集做对照，避免只做框架 Demo。LangChain 可作为 Model 或 Retriever Adapter 层接入，不必重写全部安全边界。

### 10.3 第三优先级 Query 增强

增加 Query Rewriting 和 HyDE 的可开关策略，对原始 Query、改写、HyDE 和组合方案进行消融。报告 Recall、MRR、NDCG、延迟和模型成本，只有在固定数据集上有收益才保留。

### 10.4 第四优先级 LLM 评测

在现有确定性指标之外增加 Claim Citation 对齐和成对比较；若使用 LLM as a Judge，要保存 Rubric、Judge 模型、随机化顺序、一致性和人工复核结果。Few shot 也应通过相同评测集验证，而不是凭感觉修改 Prompt。

### 10.5 第五优先级 Multi Agent

只有在任务出现独立权限域、长上下文隔离或不同模型专长时才增加 Router 和 Handoff。先做单 Agent 与 Multi Agent 消融，比较成功率、安全违规、P95、Token、成本和恢复复杂度。没有明确收益就保留当前单 Agent DAG。

## 11 面试讲解顺序

1. 先用一句话说明 WorkPilot 是带审批、幂等和验证的企业办公执行 Agent。
2. 画出 FastAPI 到 Planner、DAG、Policy、Adapter、Verifier、PostgreSQL 和 Temporal 的主链路。
3. 选择一个周报任务，说明计划如何生成、为什么写操作必须审批、参数哈希如何防止审批后篡改。
4. 解释响应丢失时为什么不能直接重试，以及 Ledger 与 lookup before retry 怎样避免重复副作用。
5. 展示 Trace、评测集、Failure Taxonomy 和修复前后基线，说明如何从 Bad Case 推动改进。
6. 诚实说明边界：没有 LangGraph、Multi Agent、Redis、真实语义 Embedding 和模型微调。

## 12 总结

WorkPilot 最能证明的不是某个热门框架，而是把 Agent 变成可控制、可恢复、可评测的后端系统：模型只生成结构化候选计划，确定性代码负责风险和权限；工具调用必须经过审批、幂等、验证和检查点；数据库与工作流保存状态；Trace、指标和固定数据集形成回归证据。

从简历技能分类看，编程与工程、Plan and Execute、任务编排、结构化输出、上下文管理、状态持久化、MCP、RAG 基础管线和 Agent 稳定性都有直接代码证据。ReAct、Embedding 选型、Rerank、证据有效率和 Function Calling 只能算部分关联。其余未落地技能应写成理论了解，或者按补强顺序完成真实实现、测试和评测后再升级。
