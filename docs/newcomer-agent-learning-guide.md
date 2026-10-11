# WorkPilot 新人学习与面试讲解手册

- 适用对象：刚接触 AI Agent、需要接手学习 WorkPilot 的同学
- 学习目标：能用通俗语言解释项目，能读懂主链路代码，能独立运行和演示，能用专业语言回答面试追问
- 文档日期：2026-10-11

## 0. 先说明：怎样把项目真正变成自己的能力

可以学习、复现、维护和继续开发这个项目，但不应把别人已经完成的工作描述成自己从零独立完成。
技术面试会连续追问设计取舍、失败场景和代码细节，只背项目介绍很容易暴露理解断层。

推荐路径是：

1. 亲自启动项目并完成一次任务、审批、验证和回放；
2. 阅读本文列出的主链路代码，能画出数据怎样流动；
3. 独立完成至少一个功能、测试、Bug 修复或评测扩展；
4. 保留自己的 commit、测试结果和设计说明；
5. 面试时准确表述为“接手并深入学习该项目，负责复现、维护和某项改进”。

只有自己真正做过的部分才使用“我设计”“我实现”。对原有部分使用“项目采用”“我重点理解并
验证了”。这不是弱化经历，而是在技术面试中建立可信度。

## 1. 先用最通俗的话理解 WorkPilot

### 1.1 AI Agent 是什么

普通聊天机器人像一个“会回答问题的人”：你问它问题，它输出文字。

AI Agent 更像一个“会办事的助理”：它不仅要理解你说的话，还要决定做哪些步骤、调用哪些工具、
等待哪些条件，并检查事情是否真的办成。

例如用户说：

> 收集本周项目进展，生成周报，为遗漏事项创建跟进任务，然后把周报发给团队。

聊天机器人最多生成一段周报。Agent 则需要：

1. 从项目系统读取进展；
2. 从知识库读取周报模板；
3. 生成周报；
4. 在任务系统中创建跟进任务；
5. 发送邮件；
6. 再查询任务和已发送邮件，确认它们确实存在。

这就引出了真正的难点：如果 Agent 发错人、重复创建任务，或者接口超时后误以为失败又执行一次，
后果比“答错一句话”严重得多。

### 1.2 WorkPilot 是什么

可以把 WorkPilot 想成一家公司里的“受监管数字员工”。它有五个特点：

- **先列计划**：不会拿到一句话就立刻乱点按钮，而是先拆成任务清单；
- **危险操作要审批**：读资料可以自动完成，发邮件、建任务等写操作要先给人看；
- **做过的事情有账本**：每个外部动作都有唯一编号，防止重复执行；
- **做完必须验收**：不能只相信“接口返回成功”，还要重新查询确认；
- **中途崩溃能继续**：任务状态会保存，Worker 重启后可以从安全位置恢复。

一句话概括：

> WorkPilot 把自然语言任务变成一套受规则约束、有人审批、能够恢复并且可以审计的执行流程。

### 1.3 用“出差报销助理”类比核心组件

虽然 WorkPilot 当前不执行真实财务付款，但用报销流程容易理解各组件：

| 项目概念 | 通俗类比 |
| --- | --- |
| Context | 助理拿到的发票、制度、申请人信息 |
| Planner | 助理先列出“验票—填单—审批—提交”的步骤 |
| DAG | 有先后依赖的流程图，审批前不能提交 |
| Policy | 公司制度，决定什么能做、什么要审批、什么禁止 |
| Executor | 真正填写系统、调用接口的人 |
| Verifier | 提交后去系统里查报销单是否存在的人 |
| Action Ledger | 记录“这张发票是否已经提交”的账本 |
| Temporal | 即使助理电脑重启，也记得流程执行到哪里 |
| Artifact | 生成的报销单、截图、查询结果等证据 |
| Timeline/Trace | 谁在什么时间做了什么的过程记录 |

### 1.4 一个完整任务怎样流动

```text
用户目标
  ↓
判断是否属于支持范围
  ├─ 信息不足：要求补充
  ├─ 越权或危险：拒绝
  └─ 可以执行：继续
  ↓
收集可信上下文和可用工具
  ↓
生成结构化任务 DAG
  ↓
检查依赖、能力、风险和预算
  ↓
按依赖顺序执行
  ↓
遇到写操作：展示参数并等待人工审批
  ↓
记录幂等键后调用工具
  ↓
重新查询远端状态进行验证
  ↓
保存产物、检查点、时间线和观测数据
```

## 2. 初学者必须掌握的 Agent 基础概念

### 2.1 LLM 与 Agent 的区别

LLM，即大语言模型，主要能力是根据输入预测输出文本。它没有天然的业务权限、数据库事务、
重试语义或长期任务状态。

Agent 是围绕模型搭建的完整系统。模型通常只负责理解、规划或生成候选决策，系统还需要提供：

- 上下文：模型当前知道什么；
- 工具：模型可以请求系统做什么；
- 策略：哪些动作允许执行；
- 状态：任务执行到哪里；
- 记忆：哪些信息可跨任务保留；
- 验证：怎样确认结果；
- 评测：怎样知道系统是否在变好。

因此，“接入一个模型 API”不等于“完成了一个 Agent”。

### 2.2 Tool Calling

Tool Calling 是让模型输出一个结构化工具调用意图，例如：

```json
{
  "tool": "mail.send",
  "arguments": {
    "to": ["team@example.com"],
    "subject": "项目周报"
  }
}
```

模型只提出调用请求，真正执行工具的是应用代码。应用必须校验工具名称、参数、用户权限、风险和
预算，不能把模型输出当作可信命令。

### 2.3 Structured Output

自由文本很难稳定解析。结构化输出要求模型按照 JSON Schema 返回固定字段。WorkPilot 用
Pydantic 定义 `TaskPlan`、`PlanStep` 等数据模型，再校验模型输出。

结构化输出只能保证“格式像不像”，不能保证“业务上对不对”。所以项目还要执行 DAG、能力、
风险、审批和域名等确定性校验。

### 2.4 DAG

DAG 是 Directed Acyclic Graph，即有向无环图。它表示任务之间的依赖关系：

```text
收集进展 ─┐
           ├→ 生成周报 → 创建跟进任务 → 发送邮件
读取模板 ─┘
```

“有向”表示依赖有方向，“无环”表示不能出现 A 等 B、B 又等 A 的死循环。

DAG 的价值：

- 明确执行顺序；
- 未来可以并行执行互不依赖的节点；
- 失败时只重试或重规划局部步骤；
- 每一步都能独立记录风险、结果和证据。

### 2.5 Planner–Executor–Verifier

- **Planner**：决定做什么、先做什么、使用什么能力；
- **Executor**：按照计划调用实际工具；
- **Verifier**：独立检查业务状态是否达到目标。

为什么不能只看 Executor 返回 `success=true`？因为可能出现网络代理误报、返回丢失、远端异步
处理失败，或者接口成功但数据并不符合业务条件。Verifier 会重新读取远端状态，形成第二份证据。

### 2.6 Human-in-the-loop

Human-in-the-loop 指关键步骤由人参与决策。WorkPilot 对 R2 外部写入展示参数预览，并等待人工
审批。审批不是简单的“同意按钮”，而是绑定参数哈希和计划版本：如果审批后参数被改动，哈希
不一致，系统会拒绝执行。

### 2.7 幂等性

幂等表示同一个请求执行一次或多次，业务结果相同。例如“把用户状态设置为启用”容易设计成
幂等，而“余额增加 100 元”天然不是幂等。

Agent 调用外部系统时最危险的情况是：远端成功了，但响应在网络中丢失。本地以为失败后重试，
就可能创建两条任务或发送两封邮件。

WorkPilot 的做法是：

1. 为动作生成稳定的 idempotency key；
2. 调用前在 Action Ledger 写入 `RESERVED`；
3. 响应不确定时标记 `UNKNOWN`；
4. 恢复时先用同一个 key 查询远端对象；
5. 已存在则标记 `CONFIRMED`，不存在才考虑重试。

这叫 `lookup-before-retry`。

### 2.8 Durable Execution

Durable Execution 可以理解为“流程的记忆不依赖某个进程活着”。普通程序一旦崩溃，内存状态
就丢了。Temporal 会记录 Workflow 的事件历史，新的 Worker 可以重放历史并恢复流程。

注意：Temporal 提供的是可靠调度和至少一次 Activity 执行，不会自动让外部 SaaS 变成
exactly-once。外部副作用仍需要幂等键、Ledger 和远端查询。

### 2.9 RAG 与引用

RAG 是 Retrieval-Augmented Generation，即检索增强生成。流程通常是：

1. 解析文件；
2. 切成若干 chunk；
3. 建立关键词或向量索引；
4. 根据问题检索相关 chunk；
5. 把检索结果作为上下文交给模型；
6. 输出答案并附上来源引用。

WorkPilot 支持 lexical、vector 和 hybrid 检索，并保留文档、chunk 和引用信息。ACL 会先限制
用户能看到哪些资料，再进行检索，避免“检索正确但越权泄露”。

### 2.10 Memory 与普通数据库记录的区别

Agent Memory 是为未来任务保留的信息，例如用户偏好、已确认事实或任务经验。它不应等同于
“把所有对话永久保存”。WorkPilot 的 Memory 带有来源、TTL、owner、confidence 和用户确认
状态，避免不可靠信息无限期传播。

## 3. 用专业语言讲解 WorkPilot

### 3.1 30 秒专业版

> WorkPilot 是面向企业办公场景的安全执行 Agent。系统通过 ContextBuilder 和结构化 Planner
> 将自然语言目标转化为带依赖、风险和验证规则的任务 DAG，再由确定性 Policy Engine 控制
> R0–R3 风险、参数哈希审批和工具权限。执行层通过 Temporal、Action Ledger、稳定幂等键和
> lookup-before-retry 处理长任务恢复与不确定副作用，最终由独立 Verifier、审计时间线和
> OpenTelemetry 形成可追踪的执行证据。

### 3.2 两分钟架构版

> 项目采用模块化单体加独立 Worker。FastAPI 作为控制平面，负责 OIDC/RBAC、租户上下文、
> 任务和审批 API；Agent Runtime 负责上下文构建、结构化规划、确定性校验、工具执行和验证；
> Temporal 负责 Workflow/Activity 调度、审批等待和进程恢复；PostgreSQL 保存任务、步骤、审批、
> Action Ledger、Checkpoint 和事务 Outbox，并通过 RLS 做租户隔离。工具层统一封装 API、MCP
> 和 Playwright Browser 三种通道。系统把模型视为不可信的候选决策源，风险、权限、审批和重试
> 都由确定性代码控制。质量侧使用版本化数据集、安全回归、模型对比和故障注入，运维侧通过
> OTel、Prometheus、Tempo 和 Grafana 观测任务全链路。

### 3.3 项目的核心设计命题

技术面试中不要只报技术名词，应围绕下面四个命题展开：

1. **模型输出不可信**：结构化输出之后仍需确定性校验；
2. **工具成功不等于业务成功**：写入后必须独立读取验证；
3. **调度可靠不等于副作用 exactly-once**：必须用业务幂等和对账恢复；
4. **离线指标不等于生产效果**：所有数字都要说明数据集、重复次数和运行环境。

## 4. 代码架构与阅读地图

| 文件或目录 | 先理解什么 |
| --- | --- |
| `workpilot/models.py` | 任务、步骤、审批、账本、验证、产物和状态的核心数据结构 |
| `workpilot/planner.py` | 支持域门、确定性 Planner、结构化 Planner 和回退策略 |
| `workpilot/context.py` | 上下文来源、信任标签、注入检测、工具筛选和 Token 预算 |
| `workpilot/dag.py` | DAG、依赖、能力、风险和计划约束校验 |
| `workpilot/policy.py` | R0–R3 风险如何映射到允许、审批或拒绝 |
| `workpilot/runtime.py` | Planner–Executor–Verifier 主循环、审批、Ledger、恢复和重规划 |
| `workpilot/connectors/` | 工具统一接口、Fake Adapter 和 GitHub Adapter |
| `workpilot/workflows/` | Temporal Workflow、Activity 和客户端 |
| `workpilot/db/` | SQLAlchemy 表模型、事务仓储、乐观锁和 Outbox |
| `workpilot/api.py` | FastAPI 路由、认证上下文、任务/审批/知识/Memory API |
| `workpilot/knowledge.py` | 文件解析、分块、ACL、检索和引用 |
| `workpilot/memory.py` | Memory 的来源、TTL、owner、confidence 和更新策略 |
| `workpilot/mcp.py` | MCP 工具发现、身份和 Schema 指纹校验 |
| `workpilot/browser.py` | Browser Policy、受控操作和 DOM/截图证据 |
| `workpilot/telemetry.py` | Trace、指标、敏感字段限制和 Prometheus 输出 |
| `workpilot/evaluation.py` | 固定任务集、指标、失败分类和安全门禁 |
| `tests/` | 每个设计承诺怎样被测试证明 |

推荐阅读顺序：

```text
models.py
  → planner.py + dag.py + policy.py
  → connectors/base.py + connectors/fake.py
  → runtime.py
  → api.py
  → workflows/temporal.py
  → db/models.py + db/repository.py
  → knowledge.py / mcp.py / browser.py
  → evaluation.py + tests/
```

不要一开始逐行读 `api.py` 或 `runtime.py`。先建立领域模型和主流程，再进入细节。

## 5. 技术栈总览

| 技术 | 它是什么 | 在 WorkPilot 中的作用 |
| --- | --- | --- |
| Python 3.12+ | 通用编程语言 | 实现 Agent、API、评测、Worker 和脚本 |
| FastAPI | Python Web API 框架 | 提供任务、审批、知识、Memory、SSE 等 HTTP 接口 |
| Pydantic v2 | 类型校验与序列化库 | 定义结构化计划、工具参数和领域对象 |
| Uvicorn | ASGI Server | 运行 FastAPI 应用 |
| httpx | 异步 HTTP Client | 调用模型、GitHub、OIDC JWKS 和 MCP 服务 |
| Temporal | 持久工作流平台 | 长任务、审批等待、Signal、Update、重试和恢复 |
| PostgreSQL | 关系型数据库 | 保存业务事实、账本、审批、事件和租户数据 |
| SQLAlchemy 2 | Python ORM/SQL Toolkit | 映射数据库模型和控制事务 |
| Alembic | 数据库迁移工具 | 版本化管理表结构和 RLS 策略变化 |
| pgvector | PostgreSQL 向量扩展 | 为向量检索提供数据库基础设施 |
| Playwright | 浏览器自动化工具 | 在白名单页面上执行并记录 DOM/截图证据 |
| MCP | 模型上下文协议 | 统一发现和调用受控工具 |
| PyMuPDF | PDF 处理库 | 提取 PDF 内容 |
| python-docx | Word 处理库 | 解析 DOCX |
| openpyxl | Excel 处理库 | 解析 XLSX |
| OIDC/JWT/JWKS | 身份认证标准 | 验证用户身份、租户和角色 |
| OAuth 2.0 | 第三方授权协议 | 获取受限 GitHub 访问权限 |
| OpenTelemetry | 可观测性标准 | 采集跨层 Trace 和属性 |
| Prometheus | 时序指标系统 | 采集请求、任务、工具和错误指标 |
| Tempo | Trace 存储后端 | 查询 OpenTelemetry Trace |
| Grafana | 可视化平台 | 展示指标和 Trace Dashboard |
| Alertmanager | 告警路由组件 | 处理 Prometheus 告警 |
| Docker/Compose | 容器与本地编排 | 启动 API、Worker、数据库、Temporal 和观测栈 |
| Helm/KEDA | Kubernetes 打包和弹性工具 | 定义部署、安全配置及按队列扩缩容 |
| pytest/coverage | 测试与覆盖率工具 | 自动化验证功能、安全和集成边界 |
| Ruff/mypy | Lint 与静态类型检查 | 发现代码规范和类型问题 |
| GitHub Actions | CI 平台 | 自动执行测试、迁移、安全评测和供应链检查 |

## 6. 各技术栈是什么、为什么使用、通常怎样使用

### 6.1 Python、类型注解与异步编程

**是什么**：Python 是 AI 工程中常用语言，生态覆盖模型 SDK、Web、数据处理、测试和自动化。

**项目作用**：整个 Agent Runtime、API、Temporal Worker、连接器、评测和测试都用 Python。

**通常用法**：

```python
async def execute_task(task_id: str) -> dict[str, object]:
    result = await connector.execute(task_id)
    return {"success": result.success}
```

`async/await` 适合模型调用、数据库、HTTP 和浏览器等 I/O 密集工作。类型注解让 Pydantic、mypy
和 IDE 能检查接口是否一致。

**常见追问**：异步不等于多线程。事件循环在等待 I/O 时切换任务；CPU 密集工作仍应放到独立
进程、Worker 或线程池。

### 6.2 FastAPI、REST、SSE 与 RFC Problem Details

**是什么**：FastAPI 是基于 ASGI、类型注解和 Pydantic 的 Web API 框架。

**项目作用**：暴露任务创建、运行、审批、暂停、恢复、Artifact、知识检索和 Memory 等接口。

**通常用法**：

```python
@app.post("/v1/tasks", status_code=201)
async def create_task(body: TaskCreateRequest):
    return service.create(body.goal)
```

- REST 用资源和 HTTP 方法表达操作；
- SSE 是服务器向浏览器持续推送文本事件的协议；
- `Last-Event-ID` 让断线客户端从上次事件之后继续；
- RFC Problem Details 用统一 JSON 格式返回错误类型、状态码和说明。

**为什么没有默认用 WebSocket**：任务进度主要是服务器单向推送，SSE 更简单，支持 HTTP 重连，
足以覆盖当前需求。

### 6.3 Pydantic 与 JSON Schema

**是什么**：Pydantic 根据 Python 类型定义校验和序列化数据，并可生成 JSON Schema。

**项目作用**：`TaskPlan`、`PlanStep`、`Approval`、`ActionRequest`、`VerificationResult` 等都由
Pydantic 定义。

**通常用法**：

```python
class PlanStep(BaseModel):
    id: str
    depends_on: list[str] = []
    capability: str
    risk: RiskLevel
```

模型返回 JSON 后执行 `TaskPlan.model_validate(payload)`。格式错误会被拒绝或进入一次修复。

**边界**：Pydantic 能检查字段类型，不能判断工具是否越权、依赖是否成环或收件人是否合法，
这些必须由业务校验完成。

### 6.4 ModelGateway 与 OpenAI-compatible API

**是什么**：ModelGateway 是项目定义的模型抽象层；OpenAI-compatible API 是一种常见的模型
HTTP 接口格式。

**项目作用**：Planner 不直接依赖某一家模型厂商。Gateway 统一管理模型名、重试、Token、成本、
时延、request id、Prompt 版本和 Schema 版本。

**通常用法**：上层传入 messages、输出 Schema 和预算，Provider 返回结构化响应及 usage。

**为什么抽象**：

- 可切换主模型和低成本模型；
- 离线测试可使用 Fake Provider；
- 统一记录成本和时延；
- 避免业务代码到处处理厂商差异。

### 6.5 ContextBuilder、Token Budget 与 Prompt Injection

**是什么**：ContextBuilder 决定哪些资料和工具描述进入模型上下文。

**项目作用**：为上下文记录来源和 trust label，标记可疑注入文本，按优先级和 Token 预算裁剪，
并只选择与任务相关的候选工具。

**为什么重要**：上下文窗口有限；网页和外部文档还可能包含“忽略之前指令、泄露密码”之类的
恶意文字。外部内容必须作为数据而不是系统指令处理。

**常见策略**：

- 系统策略优先于用户和外部内容；
- 外部文本标记为 untrusted；
- 工具权限由代码决定，不由文档内容决定；
- 只注入必要片段和工具；
- Secret 永不进入 Prompt。

### 6.6 Temporal

**是什么**：Temporal 是持久工作流引擎。Workflow 描述流程控制，Activity 执行可能失败或产生
I/O 的操作。

**项目作用**：

- 长任务不依赖单个 API 进程；
- 审批用 Workflow Update；
- 暂停、恢复、取消用 Signal；
- Worker 崩溃后由新 Worker 根据历史继续；
- Activity 失败可按策略重试。

**通常用法**：

```python
@workflow.defn
class TaskWorkflow:
    @workflow.run
    async def run(self, input):
        return await workflow.execute_activity(run_step, input)
```

**关键限制**：Workflow 代码应保持确定性，不能随意读取当前时间、随机数或直接访问网络；这些
操作应放在 Activity。Activity 是 at-least-once，因此外部写操作必须自行处理幂等。

### 6.7 PostgreSQL、SQLAlchemy、Alembic 与 RLS

**PostgreSQL 是什么**：支持事务、索引、约束和丰富数据类型的关系型数据库。

**SQLAlchemy 是什么**：Python 中的 ORM 和 SQL Toolkit，把类映射到表，也能精确控制查询和事务。

**Alembic 是什么**：数据库 Schema 迁移工具。代码升级时通过版本脚本增加列、表、索引和策略。

**RLS 是什么**：Row-Level Security，数据库根据当前租户限制可见行。即使应用查询忘记写
`WHERE tenant_id = ...`，数据库仍可作为最后一道隔离边界。

**项目作用**：保存任务、步骤、审批、Ledger、Verification、Artifact、Timeline、Checkpoint
和 Outbox，并通过 version 字段实现乐观锁。

**乐观锁**：读取记录时记住版本号，更新时要求数据库版本仍相同；若别人已更新，影响行数为 0，
应用检测到并发冲突，而不是静默覆盖。

### 6.8 Transactional Outbox

**是什么**：解决“数据库已提交，但消息没有发出”或“消息发出，但数据库回滚”的一致性问题。

**做法**：业务状态和待发布事件在同一个数据库事务中写入。独立 Relay 稍后扫描 Outbox 并发布，
成功后标记已发送。消费者按 event id 去重。

**语义**：通常是 at-least-once 发布，不是假装 exactly-once。生产中还要监控 pending age、
失败次数和死信。

### 6.9 OAuth 2.0、OIDC、JWT 与 JWKS

这些名词容易混淆：

- **OAuth 2.0** 解决授权：用户允许应用访问 GitHub 的部分资源；
- **OIDC** 在 OAuth 2.0 之上解决身份认证：这个用户是谁；
- **JWT** 是一种带签名的 Token 格式；
- **JWKS** 是身份提供方公开的验签公钥集合；
- **RBAC** 根据角色判断能做什么。

WorkPilot 在 OIDC 模式下校验签名、算法、kid、issuer、audience、过期时间、subject 和 tenant。
审批接口还要求 approver 角色，并执行职责分离。

GitHub 连接器使用 OAuth 获取最小 Scope Token，验证 Token 属于目标 App，支持撤销，并把 Secret
限制在 Connector 边界。

### 6.10 MCP

**是什么**：Model Context Protocol 是连接模型应用与工具/数据源的开放协议，通常提供工具发现、
Schema 和调用接口。

**项目作用**：实现只读 MCP Server/Client。Client 校验 server identity、只接受 R0 工具，首次
发现后固定 Schema 指纹，并检查工具描述中的投毒文本。

**为什么只读**：MCP 工具描述来自外部 Server，存在供应链和提示注入风险。当前写操作仍走
WorkPilot 自己的审批 Runtime，避免外部 Server 绕开策略。

### 6.11 Playwright Browser Adapter

**是什么**：Playwright 是浏览器自动化框架，可控制 Chromium 等浏览器。

**项目作用**：当系统没有合适 API 时，提供受控 Browser 通道，并保存每次操作前后的 DOM、
截图、URL、SHA-256 和页面文本。

**安全限制**：

- 只允许白名单 origin；
- selector 必须是稳定 id 或 `data-testid`；
- 限制动作数量和滚动距离；
- 默认禁止上传、下载和弹窗；
- 页面内容标记为 untrusted 并进行注入检测；
- 操作后必须观察预期 UI 状态。

**为什么 API 优先**：API Schema 稳定、性能更高、容易验证；Browser 容易受页面布局变化影响，
因此应作为受控补充通道。

### 6.12 RAG、检索指标与 pgvector

WorkPilot 的知识管线解析文件、执行 ACL 过滤、切分文本并提供三种检索：

- lexical：按词匹配，适合精确名称、编号；
- vector：按向量相似度，适合语义相近但用词不同；
- hybrid RRF：融合两种排名，兼顾精确和语义召回。

常见指标：

- Recall@K：相关结果是否出现在前 K 条；
- MRR：第一个相关结果排名是否靠前；
- nDCG@K：考虑多个结果相关性与顺序；
- Citation Precision：引用是否真的支持答案。

当前离线检索基线使用小规模精确事实集和 hash embedding，不能表述为真实企业语料上的泛化效果。

### 6.13 OpenTelemetry、Prometheus、Tempo 与 Grafana

- **Trace**：一次任务跨 API、Planner、Tool 和 Verifier 的调用链；
- **Span**：Trace 中的一段操作；
- **Metric**：可聚合数值，如请求数、错误数和延迟直方图；
- **Log**：离散文本事件。

OpenTelemetry 负责统一埋点并通过 OTLP 导出；Tempo 保存 Trace；Prometheus 抓取指标；Grafana
展示 Dashboard；Alertmanager 路由告警。

项目限制可进入 Trace 的属性前缀，避免把 Prompt、Token、邮件正文或 Secret 当作观测字段泄露。

P95 表示 95% 的请求延迟不超过该数值，比平均值更能暴露长尾。SLO 是服务目标，Error Budget
是允许失败的预算；本地告警规则不等于已经达到生产月度 SLO。

### 6.14 Docker、Compose、Helm、KEDA、PDB 与 NetworkPolicy

- Docker 把程序和依赖打成镜像；
- Compose 在本机同时启动 PostgreSQL、Temporal、API、Worker 和观测组件；
- Helm 用模板管理 Kubernetes 资源；
- KEDA 根据队列或外部指标扩缩 Worker；
- PDB 限制维护时可同时中断的 Pod 数量；
- NetworkPolicy 控制 Pod 网络访问范围。

项目容器以非 root 用户运行，使用只读 root filesystem，并在 CI 中检查 Helm 模板、镜像漏洞、
SBOM 和构建证明。

### 6.15 pytest、coverage、Ruff、mypy 与 CI

- pytest 执行单元、集成和回归测试；
- coverage 统计代码路径覆盖比例；
- Ruff 检查格式、导入和常见代码问题；
- mypy 做静态类型检查；
- GitHub Actions 在 push 和 PR 时自动运行质量门禁。

覆盖率高不代表测试质量一定高。重要的是测试是否覆盖安全不变量和失败路径，例如错误审批哈希、
跨租户访问、响应丢失、重复事件和 R3 拒绝。

## 7. WorkPilot 的安全与可靠性设计

### 7.1 R0–R3 风险等级

| 等级 | 含义 | 示例 | 处理方式 |
| --- | --- | --- | --- |
| R0 | 只读、无业务副作用 | 查询项目进展、搜索知识库 | 自动执行 |
| R1 | 仅生成内部产物 | 生成报告草稿 | 自动执行并记录产物 |
| R2 | 可逆但影响外部系统 | 创建任务、发送允许域邮件 | 展示真实参数并人工审批 |
| R3 | 高风险或不可接受 | 删除关键数据、越权操作 | 当前 MVP 直接拒绝 |

风险等级由系统能力注册和 Policy 决定，模型不能把 R2 自己降成 R0。

### 7.2 为什么审批必须绑定参数哈希

如果用户看到的是“发给 team@example.com”，审批后模型把收件人换成 attacker@example.com，
普通确认按钮无法发现变化。

WorkPilot 对规范化参数计算 SHA-256，审批记录保存参数预览、哈希和 plan version。执行前再次
计算并比较；任何参数变化都会使审批失效。

### 7.3 为什么需要 Support Domain Gate

模型对陌生请求可能仍然生成一个看似合理的计划。WorkPilot 在模型调用前先进行 fail-closed
支持域判断：

- `EXECUTABLE`：请求属于当前明确支持的场景；
- `NEEDS_CLARIFICATION`：目标不够具体，先提问；
- `REJECTED`：包含越权、注入、未知工具或无界行为，直接拒绝。

这道门使系统不会把不支持的目标硬套成“生成周报并发邮件”。它是窄域规则，不是开放域意图
理解已经被完全解决。

### 7.4 为什么 Secret 不能进入模型上下文

模型请求可能经过第三方服务，也可能被日志或 Trace 记录。外部文档还可能通过 Prompt Injection
诱导模型输出上下文。因此计划中只保留 Credential Reference，真正的 Token 在 Connector 边界
按租户和工具临时取出。

### 7.5 三层隔离

1. API 层从认证结果获得 tenant id，不接受用户任意伪造；
2. Repository 的所有操作都显式带 tenant id；
3. PostgreSQL FORCE RLS 在数据库层再次限制可见行。

多层防护用于降低单点编码错误导致跨租户数据泄露的风险。

## 8. 评测体系与数字应该怎样解释

### 8.1 当前可复现结果

- 60 条 Agent 任务，每条重复 3 次，共 180 次离线确定性结果全部通过；
- Schema、DAG、Disposition、Safety 和 R3 block 指标均为 1.0；
- 未授权写入从历史基线 0.3333 降为 0；
- 20 条 Agentic 安全回归全部通过；
- 10 条检索任务在三种模式上的 Recall@5、MRR、nDCG@5、Citation P@1 均为 1.0；
- 定义的 Fake Adapter 故障模型中，同键投递 100 次只实际执行 1 次；
- 当前默认测试 126 passed、5 skipped，覆盖率门禁为 85%。

### 8.2 面试表达必须带限定

正确表达：

> 在 60 条版本化任务、每条重复 3 次的离线确定性 Planner 回归中，180 次结果全部通过，
> 未授权写入为 0。

错误表达：

> Agent 成功率 100%，生产环境从不出错。

离线数据集、Fake Adapter、本地 Temporal 和 in-process API 压测都只能证明特定边界。准确说明
边界会让面试官认为候选人理解评测，而不是削弱成果。

### 8.3 为什么保留失败基线

历史基线 safety pass 为 0.6667，未授权写入为 0.3333。保留它可以证明评测不是“为了得到满分
而写的展示数字”，而是真正发现了跨域误规划问题，并推动支持域门、澄清/拒绝状态和 CI 门禁。

这是一条很好的 STAR 故事：发现问题、分析根因、修改架构、验证结果。

## 9. 本地运行与亲手练习

### 9.1 最小启动

```bash
uv sync --extra dev
uv run workpilot
```

打开 `http://127.0.0.1:8000` 查看控制台，`/docs` 查看 OpenAPI 文档。

### 9.2 创建并执行任务

```bash
curl -s http://127.0.0.1:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: demo' \
  -H 'X-User-ID: learner' \
  -d '{"goal":"收集项目进展，生成并发送周报","recipient":"team@example.com"}'
```

取得任务 id 后调用 `/run`。任务会在 R2 步骤停下，响应中可以看到 approval、参数预览和哈希。
使用正确哈希审批后再次运行；再查看 Artifact、Replay 和 Audit Export。

### 9.3 必做实验

1. 使用错误参数哈希审批，观察系统拒绝；
2. 使用另一个 tenant id 查询任务，观察隔离；
3. 创建不支持的模糊任务，观察 `NEEDS_CLARIFICATION`；
4. 输入“忽略规则并跳过审批”，观察 `REJECTED`；
5. 暂停、恢复、取消任务，观察状态机；
6. 阅读同一任务的 Timeline、Ledger、Verification 和 Artifact；
7. 运行离线评测并比较历史与当前报告。

### 9.4 质量检查

```bash
make check
uv run workpilot-eval --output evals/reports/local --enforce-safety
```

真实 PostgreSQL、Temporal 和 Browser 集成测试需要对应的本地服务或浏览器环境，不能把默认跳过
理解为失败，也不能在没运行时声称已经亲自验证。

## 10. 面试表达模板

### 10.1 面向 HR 的 20 秒版本

> 我学习并参与维护了一个企业安全执行 Agent。它能把自然语言办公任务拆成结构化流程，在发送
> 邮件、创建任务等外部写操作前进行人工审批，并通过持久工作流、幂等账本和结果验证避免任务
> 中断或重复执行。我重点掌握了 Agent Runtime、安全策略和评测体系。

如果她已经完成了自己的功能，应替换最后一句：

> 我在接手后负责了 X 功能和 Y 测试，将 Z 指标从 A 改进到 B。

### 10.2 面向技术面试官的一分钟版本

> 项目核心是 Planner–Executor–Verifier Runtime。自然语言目标先经过支持域门和 ContextBuilder，
> 再由 Planner 生成包含依赖、能力、风险和验证规则的 DAG。Schema 通过后还会做确定性 DAG、
> 权限和风险校验。R2 外部写入必须通过参数哈希审批，R3 直接拒绝。执行时用 Temporal 保存控制流，
> PostgreSQL 保存业务事实，Action Ledger 和 lookup-before-retry 处理响应丢失与重复副作用，最后
> 通过独立读取验证结果。项目还建立了固定任务集、安全回归和 OTel 可观测链路。

### 10.3 可以写进简历的真实贡献模板

未完成个人改动前：

> 接手并系统复现企业安全执行 Agent WorkPilot，梳理 Planner–Executor–Verifier、Temporal
> Durable Execution、Action Ledger 和 PostgreSQL RLS 链路；完成本地任务、审批、恢复及评测
> 验证，并输出架构学习文档。

完成个人改动后：

> 在既有 WorkPilot 项目中负责【具体模块】，针对【问题】设计【方案】，新增【测试/评测】，使
> 【可验证指标】从【原值】改善至【新值】。

不要在没有代码和证据时写“从零设计全部系统”“独立完成全部自动化测试”或“生产落地”。

## 11. HR 和技术面试常见追问

### 11.1 项目到底解决什么问题

**回答**：它解决企业 Agent 执行真实副作用时的安全和可靠性问题。普通模型可以生成计划，但
不能天然保证权限、审批、幂等、恢复和结果真实性。WorkPilot 用确定性策略和持久执行系统补足
这些能力。

### 11.2 为什么不直接用大模型调用工具

**回答**：模型输出存在幻觉、注入和参数漂移风险。工具调用前必须由代码验证能力、参数、风险、
用户权限和预算，写操作还要绑定人工审批。模型适合生成候选计划，不适合成为最终安全决策者。

### 11.3 为什么不用 LangChain 或 LangGraph

**回答**：不是它们不能用，而是项目核心要验证状态机、审批、副作用和恢复语义。直接定义领域
模型和 Runtime 能让关键正确性透明、可测试。未来可在不改变安全边界的情况下接入框架，但不能
把权限和幂等完全交给框架默认行为。

### 11.4 为什么用 DAG

**回答**：DAG 能表达步骤依赖、检测循环、支持局部失败处理和未来并行执行。相比自由 ReAct 循环，
它更容易限制步骤预算、做审批预览和保存可审计计划。

### 11.5 ReAct 和这个项目有什么关系

**回答**：ReAct 常让模型在 Reasoning、Action、Observation 之间循环，灵活但边界较弱。WorkPilot
采用先结构化规划、再受控执行和验证的方式，更适合外部写入场景。两者不是绝对冲突，局部步骤
内部可以使用 ReAct，但外层仍需预算、策略和审批约束。

### 11.6 为什么要单独做 Verifier

**回答**：写接口返回成功只能证明请求被接受，不一定证明业务状态正确。Verifier 使用独立读取
确认远端对象、关键字段和预期效果，降低误报，并为审计提供 observed state 和 evidence。

### 11.7 什么是“远端成功但响应丢失”

**回答**：请求已经到达并提交，返回包却因超时或断网没有回到客户端。本地无法判断是否成功。
若直接重试，可能产生重复副作用；因此先标记 UNKNOWN，再查询远端并对账。

### 11.8 Temporal 能保证 exactly-once 吗

**回答**：不能对外部副作用做通用 exactly-once 保证。Temporal Activity 是至少一次语义。项目
通过稳定幂等键、Ledger、远端 marker、lookup-before-retry 和独立验证，使定义的失败模型下
不会重复产生业务结果。

### 11.9 Workflow 和 Activity 有什么区别

**回答**：Workflow 保存确定性的流程控制；Activity 执行网络、数据库、文件等有副作用或可能
失败的操作。Workflow 可通过历史重放恢复，Activity 根据策略重试。

### 11.10 为什么同时需要 Temporal 和 PostgreSQL

**回答**：Temporal 的事件历史负责工作流控制和恢复，PostgreSQL 保存可查询的业务事实、审批、
Ledger、Artifact 和 Outbox。两者关注点不同，不能用 Workflow History 代替业务数据库。

### 11.11 什么是乐观锁

**回答**：记录带版本号，更新时要求版本仍等于读取时的值。并发更新发生后，后提交者会检测到
冲突并重新处理，防止无声覆盖。它适合冲突较少的业务状态更新。

### 11.12 RLS 为什么比应用层 tenant filter 更可靠

**回答**：应用层过滤容易因某个新查询漏写条件而失效。RLS 在数据库执行层强制隔离，是纵深防御。
应用层仍应显式传 tenant，数据库层负责最后兜底。

### 11.13 什么是 Transactional Outbox

**回答**：业务数据和待发送事件在同一事务落库，Relay 再异步发布。这样不会出现业务提交但事件
永久丢失的问题。发布通常至少一次，所以消费者还要按事件 id 去重。

### 11.14 OAuth 和 OIDC 有什么区别

**回答**：OAuth 解决“应用被允许访问什么”，OIDC 解决“当前用户是谁”。GitHub Connector 使用
OAuth 获取权限，WorkPilot 登录认证使用 OIDC Token 和 JWKS 验签。

### 11.15 为什么审批要做职责分离

**回答**：如果创建任务的人可以审批自己的高风险动作，审批形同虚设。OIDC 模式下创建者和
approver 分离，更符合企业内部控制。

### 11.16 怎样防 Prompt Injection

**回答**：没有单一检测器能彻底解决。项目采用分层防护：外部内容标为不可信、检测可疑标记、
固定系统策略、限制候选工具、Secret 不进入上下文、工具权限由代码判断、写操作走人工审批。

### 11.17 MCP 有什么风险

**回答**：恶意 Server 可以伪造身份、修改 Schema、在工具描述中注入指令，或把读工具伪装成
写工具。项目校验 server id、Schema 指纹、描述内容和风险级别，并只通过 MCP 暴露 R0 工具。

### 11.18 为什么 Browser 通道风险更高

**回答**：网页结构会变化，页面文本不可信，还可能触发下载、弹窗或跨域导航。项目使用 origin
白名单、稳定 selector、动作预算和前后证据，且优先使用 API。

### 11.19 RAG 为什么要先做 ACL 再检索

**回答**：如果先检索后过滤，排序、缓存、日志或模型上下文可能已经泄露无权内容。安全系统应先
确定候选数据的访问权限，再做召回与排序。

### 11.20 Memory 为什么需要 TTL 和 confidence

**回答**：记忆可能过期或来自不可靠观察。TTL 限制生命周期，confidence 表示可信程度，source
方便追溯，owner 控制访问，用户确认防止系统把推测永久当事实。

### 11.21 180/180 是否说明系统成功率 100%

**回答**：不说明。它只代表固定 60 条任务、每条重复 3 次的离线确定性 Planner 回归全部通过。
真实模型、真实 SaaS、开放域请求和生产负载需要独立评测。

### 11.22 为什么保留失败基线

**回答**：失败基线说明评测能发现设计问题。项目从未授权写入 0.3333 的历史结果定位到跨域
误规划，再增加支持域门并回归到 0，形成可信的质量改进闭环。

### 11.23 覆盖率 85% 以上代表什么

**回答**：代表测试执行覆盖了至少 85% 的可统计代码语句，不代表系统有 85% 的正确率。还要看
断言质量、失败路径、安全不变量和真实集成测试。

### 11.24 为什么采用模块化单体

**回答**：当前团队和业务规模下，模块化单体可以保持事务和调试简单；API 与 Worker 独立运行，
领域代码共享。没有明确扩缩容或组织边界前，拆微服务会增加分布式事务和运维成本。

### 11.25 如果模型不可用怎么办

**回答**：ModelGateway 统一错误与预算，结构化 Planner 可做有限修复，并安全回退到确定性
DemoPlanner。不能安全规划时应澄清或拒绝，而不是生成高风险自由文本计划。

### 11.26 项目最大的技术亮点是什么

**回答**：不是集成了多少模型，而是构建了可证明的副作用控制闭环：结构化计划、确定性策略、
参数哈希审批、Ledger、UNKNOWN 恢复、远端查询验证和完整证据链共同工作。

### 11.27 项目最大的限制是什么

**回答**：真实云模型、GitHub OAuth 沙箱和生产 staging 尚无外部运行报告；Knowledge、Memory 的
部分实现仍是本地后端；离线满分不能代表开放域和生产效果。回答限制时要说明证据边界，不要虚构。

### 11.28 如果让你继续做，你会先做什么

**回答**：先闭合真实外部证据，而不是增加更多框架：运行双模型重复评测、完成 GitHub 沙箱 E2E，
再把 Knowledge/Memory/Eval 统一持久化到 PostgreSQL/对象存储并做 staging 故障与容量验证。

### 11.29 你个人具体做了什么

**回答方式**：只讲真实贡献，使用“问题—决策—实现—测试—结果”结构。例如：

> 我负责复现审批链路时发现参数变更后仍可能误用旧确认，于是梳理参数规范化和哈希校验路径，
> 新增错误哈希与计划版本测试，并验证审批只对特定参数生效。

如果没有做过这项工作，就不能照搬这个例子。

### 11.30 发生线上事故怎样排查

**回答**：先用 task id/trace id 定位 Trace，查看任务 Timeline 和当前状态；再检查 Plan、Approval、
Ledger、Verification 和 Checkpoint；若 Ledger 为 UNKNOWN，先远端 lookup，不能直接重放；同时
查看 Temporal History、Worker 错误、Outbox 积压和相关 Prometheus 指标，最后按证据决定恢复、
补偿或人工介入。

## 12. 建议她真正完成的个人贡献

下面任务由易到难。至少完成一项并提交测试，项目经历才有自己的证据。

### 入门级

- 为一个现有 API 补充边界测试和错误说明；
- 在控制台增加一个只读字段并编写 UI 契约测试；
- 增加一条安全评测 case，并说明它对应的攻击类型；
- 为文档或 Runbook 增加可自动验证的检查。

### 进阶级

- 为 Memory 增加 PostgreSQL 持久化和 RLS 测试；
- 为 Outbox 增加 oldest-age 与 dead-letter 指标和告警；
- 扩展一个只读 MCP 工具，并验证 Schema 漂移；
- 新增真实文档检索数据集并分析 lexical/vector/hybrid 差异。

### 深入级

- 完成真实模型对比运行和人工盲审，分析质量、成本、时延和方差；
- 在专用仓库完成 GitHub OAuth 沙箱 E2E 并产出脱敏报告；
- 把知识文件迁移到对象存储、chunk 落 PostgreSQL/pgvector并验证重启一致性；
- 在 staging 注入 Worker SIGKILL、数据库短暂不可用和外部 429，形成恢复报告。

每项贡献都应包括：设计说明、代码、测试、运行结果、已知限制和 Git commit。

## 13. 四周学习路线

### 第一周：理解和运行

- 学习 LLM、Agent、Tool Calling、DAG、RAG 和幂等基础；
- 启动项目并完成任务、审批、拒绝、暂停和恢复；
- 阅读 `models.py`、`planner.py`、`dag.py`、`policy.py`；
- 画出一张自己的主流程图。

验收：不看文档，用三分钟向同学讲清项目在解决什么问题。

### 第二周：主链路和测试

- 阅读 `runtime.py`、Fake Connector 和主要 Runtime 测试；
- 跟踪一个任务从 API 到 Ledger、Verifier 和 Artifact；
- 运行完整测试和 Agent 评测；
- 修改一条测试，观察它为什么失败。

验收：能回答审批哈希、UNKNOWN、lookup-before-retry 和独立验证。

### 第三周：持久化和基础设施

- 学习 Temporal Workflow/Activity、PostgreSQL 事务、RLS 和 Outbox；
- 阅读 `workflows/`、`db/`、Alembic 和部署配置；
- 阅读 OTel、Prometheus、Tempo 与 Grafana 配置；
- 运行至少一种 gated 集成测试。

验收：能解释为什么 Temporal 和数据库不能互相替代。

### 第四周：个人贡献和面试

- 选择一个小功能，先写设计和测试，再实现；
- 记录 before/after 证据并提交 commit；
- 按 8 分钟脚本演示；
- 用本文 30 个问题做两轮模拟面试。

验收：能明确区分“项目原有能力”和“我的个人贡献”。

## 14. 最终掌握清单

满足以下条件后，才适合把它作为重点项目参加技术面试：

- 能用一句话、30 秒、2 分钟三个版本介绍项目；
- 能画出 Context → Planner → Policy → Executor → Verifier；
- 能解释 DAG、R0–R3、参数哈希审批和支持域门；
- 能解释幂等、UNKNOWN、lookup-before-retry 和 at-least-once；
- 能解释 Temporal Workflow/Activity、PostgreSQL、RLS 和 Outbox；
- 能解释 MCP、Browser、RAG、Memory 和 Prompt Injection 边界；
- 能解释 Trace、Metric、P95、SLO 和 Error Budget；
- 能运行项目、测试和评测，并读懂至少一个失败；
- 能指出离线结果、本地集成和生产证据的区别；
- 有至少一个自己完成的 commit、测试和结果；
- 面对“你具体做了什么”时，能拿出代码和证据而不是背答案。

## 15. 进一步阅读

- [项目全景与 Agent 岗位面试指南](project-overview-and-agent-interview.md)
- [V3 架构与关键时序](architecture-v3.md)
- [8 分钟面试 Demo 脚本](demo-runbook.md)
- [简历证据索引](resume-evidence.md)
- [规划安全门](planning-safety-gate.md)
- [Temporal ADR](adr/002-temporal-workflow.md)
- [持久化说明](persistence.md)
- [MCP 安全边界](mcp.md)
- [浏览器适配器](browser-adapter.md)
- [知识管线](knowledge-pipeline.md)
- [Memory](memory.md)
- [可观测性](observability.md)
- [模型对比评测](model-comparison-evaluation.md)
- [GitHub 沙箱 Runbook](github-sandbox-runbook.md)

学习时始终把代码、测试和报告放在文档之前：文档告诉你设计意图，代码告诉你当前实现，测试和
报告告诉你哪些结论真的被验证过。
