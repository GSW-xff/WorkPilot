# WorkPilot 补充方案 4：最新版完成情况与后续完善路线

- 文档版本：4.0
- 基线日期：2026-10-10
- 代码基线：与本方案所在 Git 提交一致，以仓库内可复现代码、测试和报告为准
- 目标：明确当前项目能证明什么、还缺什么，以及如何从“可写简历”推进到“强面试证据与准生产验收”

## 0. 结论

WorkPilot 当前已经达到**可以写入简历并进行现场演示的工程版本**。它不再只是 Prompt Demo，
而是一套具备结构化规划、确定性安全策略、人工审批、持久工作流、多租户数据边界、外部工具
适配、故障恢复、可观测性和版本化评测的企业执行 Agent。

当前最有竞争力的部分是“可证明的安全执行闭环”：计划必须通过 Schema/DAG/风险校验，R2
动作绑定审批参数，副作用通过 Ledger 与 lookup-before-retry 恢复，执行后再独立读取验证，
并由 Timeline、Checkpoint、Artifact、Trace 和评测报告形成证据链。

但项目还不能描述为生产就绪。最关键的剩余工作不是继续堆框架，而是闭合四类外部证据：

1. 真实云模型在固定任务集上的质量、成本和方差；
2. GitHub OAuth 沙箱的真实写入、Webhook 和响应丢失恢复；
3. staging 环境的端到端 SLO、容量、PITR 和告警通知；
4. 5 名真实目标用户的可用性研究与正式 Demo 视频。

## 1. 最新版完成情况

状态定义：**已实测**表示有真实进程/容器/浏览器或可重复报告；**已实现**表示代码和自动化测试
完整，但仍缺外部账号或生产环境；**部分完成**表示已有安全边界和本地闭环，但后端或运行环境
仍是本地实现；**待完成**表示只有方案或模板。

| 维度 | 状态 | 当前成果 | 证据边界 |
| --- | --- | --- | --- |
| Agent Runtime | 已实测 | Planner–Executor–Verifier、强类型 DAG、支持域门、澄清/拒绝、重规划 Diff、工具路由、独立验证 | 单 Planner；没有多 Agent 优势证据 |
| Model/Context | 已实现 | ModelGateway、OpenAI-compatible Provider、结构化输出、一次修复、安全回退、信任标签、Token/成本预算 | 未用真实付费模型跑固定集 |
| 安全执行 | 已实测 | R0–R3、R2 参数哈希审批、R3 拒绝、域名白名单、Secret 引用隔离 | 不是渗透测试或生产红队 |
| 可靠工作流 | 已实测 | Temporal Workflow/Activity、Update/Signal、Worker 重启、History replay | 本地 Temporal 开发服务，非 HA 集群 |
| 副作用一致性 | 已实测 | 稳定幂等键、RESERVED/UNKNOWN、远端查询后恢复、独立 verify | Fake Adapter 失败模型已验；真实 SaaS 尚缺 |
| 数据持久化 | 已实测 | SQLAlchemy/Alembic、乐观锁、事务 Outbox、PostgreSQL FORCE RLS | 知识、Memory 和部分运行服务仍非统一生产持久层 |
| 企业连接器 | 已实现 | GitHub Issues OAuth/HTTP Adapter、限流、熔断、Scope、Webhook 签名/防重放、幂等 marker | MockTransport 契约通过；无真实 GitHub 沙箱 E2E |
| MCP | 已实现 | 只读工具桥、身份校验、Schema 指纹、参数约束 | 未验证多个第三方 MCP Server 的兼容性 |
| Browser | 已实测 | Playwright 白名单、稳定 selector、前后截图/DOM 证据、页面注入标记 | 本地受控页面；不是公网网站兼容矩阵 |
| Knowledge/RAG | 部分完成 | PDF/DOCX/XLSX/Markdown/TXT 解析、安全门、ACL、混合检索、精确引用和原文预览 | 本地对象存储与 hash embedding；非 S3/MinIO + pgvector 生产链路 |
| Memory | 部分完成 | working/episodic/semantic 分层、来源、TTL、owner、confidence、确认后写入 | 尚未统一落入 PostgreSQL 并验证长期迁移/删除 |
| 身份权限 | 已实现 | OIDC/JWKS、issuer/audience、tenant claim、RBAC、职责分离 | 尚缺真实 IdP 登录端到端和生产 Token 生命周期 |
| 产品工作台 | 已实测 | 任务、DAG、审批 Inbox、Artifact、恢复中心、连接器、知识、Memory、Eval 面板 | 无构建静态前端；生产登录、无障碍和大规模交互待验证 |
| 评测 | 已实测 | 60 条任务集 x 3、失败分类、Wilson 区间、安全零容忍 CI 门禁、报告对比 | 确定性基线已收口；没有真实模型与人工 judge 校准 |
| 可观测性 | 已实测 | OTel/OTLP、Tempo、Prometheus Histogram、Grafana、6 条 SLO/安全告警、Runbook | 无生产通知渠道和月度 SLO 窗口；队列启动 P95 未采集 |
| 部署供应链 | 已实测 | Docker、Compose、Helm、KEDA、PDB、NetworkPolicy、非 root/只读 FS、CodeQL/Trivy/SBOM/attestation 定义 | GitHub 远程工作流和真实 K8s staging 尚未作为通过证据 |
| 备份恢复 | 已实测 | FORCE RLS 下专用备份身份、vector 扩展恢复顺序、隔离恢复与自动清理 | 31 KB 本地逻辑备份；不是生产 RTO/RPO 或 PITR |
| 用户证据 | 待完成 | 已有 8 分钟 Demo 脚本和 5 人研究协议 | 没有视频、参与者数据或 SUS 结果 |

## 2. 当前可复现数据

### 2.1 自动化与真实集成

- 108 项测试已被收集；默认离线套件通过，5 项 gated 测试按环境显式启用；
- 真实 PostgreSQL RLS 对抗测试：3 项通过；
- 真实 Temporal Worker 重启、Update 和 History replay：1 项通过，既有报告记录 19.78 秒；
- 真实 Playwright Chromium：2 项通过；
- Prometheus：配置有效，加载 1 个规则文件、6 条规则；Alertmanager 配置有效；
- Helm 3.17.3：1 个 Chart lint 通过；受限容器以 UID/GID 10001、只读 root filesystem 运行；
- PostgreSQL 备份恢复：31,418 bytes，备份 0.44 秒，恢复/校验 0.99 秒，10/10 表，清理残留 0。

### 2.2 Agent、检索、安全和容量数据

| 报告 | 已取得结果 | 正确解释 |
| --- | --- | --- |
| 历史 Agent baseline-v1 | 60 cases x 3；Schema 1.0、审批召回 1.0、DAG 0.9167、safety_pass=0.6667、unauthorized_write=0.3333 | 修复前失败基线，保留用于证明评测发现了真实设计缺口 |
| 当前 intent-gated-v2 | 60 cases x 3，180/180 通过；Schema、DAG、Disposition、Safety、R3 block 均 1.0；unauthorized_write 0 | fail-closed 确定性 Planner 回归；不是云模型、SaaS 或生产红队结果 |
| Agentic security | 20/20 | 确定性策略门回归，不替代渗透测试 |
| Retrieval | 10 cases；lexical/vector/hybrid 的 Recall@5、MRR、nDCG@5、Citation P@1 均 1.0 | hash embedding 的精确事实离线集，不代表真实企业语料泛化 |
| API baseline | 300 ops、并发 20、0% 错误、813.90 req/s；create P95 51.253 ms、list P95 25.862 ms | in-process ASGI + 内存仓储，不是 PostgreSQL/Temporal/SaaS 生产容量 |
| 幂等故障注入 | 同键 100 次投递，实际执行 1 次，远端对象 1，重复业务副作用 0 | Fake Enterprise Adapter 已定义失败模型 |

### 2.3 当前简历可写范围

可以写：结构化 Agent Runtime、安全审批与副作用恢复、Temporal/PostgreSQL RLS、真实浏览器
证据、固定评测集、OTel/Prometheus、Helm/供应链配置和本地故障演练。数字必须带环境限定。

不能写：真实模型达到某成功率、GitHub 沙箱 E2E、月度 99.9% 可用性、生产 Kubernetes、
5 人研究、SUS、PITR、多区域恢复、第三方 MCP 兼容矩阵或“多 Agent 提升了效果”。

## 3. 仍需补充和完善的内容

### 3.1 P0：先闭合 Agent 质量与真实连接器证据

#### P0-1 固定任务集安全基线收口（已完成）

历史 DemoPlanner 对不支持或应拒绝的意图仍会套用固定周报写动作，导致 `baseline-v1` 中
`safety_pass=0.6667` 和 `unauthorized_write=0.3333`。该缺口现已完成代码、产品、持久化和
评测闭环。

已实施：

1. 在确定性与结构化 Planner 的模型调用前增加支持域门，输出 `EXECUTABLE`、
   `NEEDS_CLARIFICATION` 或 `REJECTED`；
2. 把信息不足、越权/注入、未知工具和无界计划作为一等结果，不创建 Plan 或动作；
3. 新增 owner-only 澄清 API、原任务重新规划、数据库字段/Alembic 迁移及控制台交互；
4. 评测增加 disposition、unauthorized write、R3 block 等门禁，CI 使用 `--enforce-safety`；
5. 生成 `intent-gated-v2` 报告：180/180 通过，未授权写入 0，无失败分类。

当前边界：支持域识别是窄域确定性规则，目的是在模型前 fail closed；它不代表开放域意图识别
已经解决，也不替代真实模型对比、对抗红队或 GitHub 沙箱 E2E。

#### P0-2 运行真实模型对比评测

用同一数据集、Prompt/Schema 版本和预算，至少对比“确定性基线、一个主模型、一个低成本
模型”，每条至少重复 3 次。记录成功率、Tool precision/recall、安全违规、修复率、P50/P95、
输入/输出 Token、成本和方差。对失败样本做盲审，不能只使用 LLM-as-judge 自证。

交付物：版本化 JSON/Markdown 报告、逐 case trace id、成本清单、失败分类和回归阈值。

#### P0-3 完成 GitHub OAuth 沙箱 E2E

在专用组织/仓库验收授权、最小 Scope、创建 Issue、评论、读取验证、撤销、Webhook 防重放、
429/5xx 和“远端成功但响应丢失”。最后用 GitHub 远端对象 id 证明重复副作用为 0。

交付物：可清理的 sandbox fixture、脱敏 HTTP/Trace 证据、故障矩阵和 connector runbook。

### 3.2 P1：把本地工程闭环推进到 staging 运维闭环

#### P1-1 持久化知识、Memory 与评测事实

- 原文件迁移到 S3/MinIO adapter，启用加密、保留和删除策略；
- chunk/embedding/ACL/citation 落 PostgreSQL + pgvector，重启后结果一致；
- Memory 与 Eval Run 进入 tenant-scoped schema、RLS 和迁移；
- 文件解析进入资源受限 Worker，接入真实防病毒服务并加入 zip bomb/PDF bomb 回归。

#### P1-2 补齐队列、Outbox 与多进程指标

- 从 Temporal 采集 schedule-to-start latency Histogram 和 task queue backlog；
- 暴露 Outbox oldest-age、pending/dead-letter、UNKNOWN recovery backlog；
- 将当前进程内指标交给标准 OTel/Prometheus SDK，验证多副本聚合与重启语义；
- 为队列 P95、Outbox age 和恢复积压加入告警与 Runbook。

#### P1-3 建立真实 staging

先确定云和责任边界，再创建 Terraform，不提交空壳 IaC。部署 API/Worker、托管 PostgreSQL、
Temporal、对象存储、OIDC、Secret Manager 和监控；镜像只允许 digest，迁移使用独立 Job，
配置受限 egress、NetworkPolicy、Pod Security 和回滚门禁。

#### P1-4 端到端容量与恢复

- 压测 Compose/staging：PostgreSQL 连接池、Temporal backlog、Worker 饱和和 SaaS 延迟；
- 做长 Activity heartbeat/cancel 传播、Worker SIGKILL、DB 短暂不可用、Collector 不可用；
- 使用接近目标数据量的加密备份完成恢复，增加 WAL/PITR、对象存储和 Secret 恢复；
- 在持续窗口内计算 SLO，再决定告警阈值与副本容量。

### 3.3 P2：补齐产品与用户证据

1. 使用真实 IdP 完成 Authorization Code + PKCE 登录、登出、Token 刷新/失效和职责分离 E2E；
2. 对 Console 做键盘操作、屏幕阅读器、焦点、错误提示、移动端和慢网测试；
3. 用既有协议完成 5 人研究，保留匿名原始数据、任务完成率、中位时长、错误数和 SUS；
4. 修复研究中最严重的三项问题，再做同任务复测；
5. 按 8 分钟脚本录制无剪辑核心流程，所有数字链接到证据索引；
6. 只有 GitHub 深度闭环稳定后，再新增第二个连接器，避免“十个浅连接器”。

### 3.4 P3：有证据才做的实验

- 多 Agent：仅在独立权限域、长上下文隔离或关键路径并行存在时做消融；
- LLM-as-judge：先用人工双标样本校准一致性，再用于规模化辅助评分；
- 模型路由/缓存：必须同时报告质量、安全、成本和陈旧结果风险；
- 微调：只有稳定失败簇和足够高质量训练数据出现后再评估。

这些内容不能因为“岗位关键词”提前加入主链路。ADR-003 已记录单 Agent 优先的决策。

## 4. 推荐实施顺序

| 阶段 | 建议周期 | 关键任务 | 阶段出口 |
| --- | --- | --- | --- |
| A：安全基线收口 | 已完成 | 支持域/拒绝/澄清、重跑 60 条任务集、CI 零容忍门禁 | 180/180 通过，unauthorized write=0 |
| B：真实外部证据 | 5–7 天 | 真实模型对比、GitHub sandbox E2E、真实 IdP | 三套脱敏、可复现报告 |
| C：staging 数据与观测 | 1–2 周 | S3/MinIO、pgvector、Memory/Eval 持久化、队列/Outbox 指标 | 重启不丢数据，关键 SLO 可计算 |
| D：生产化演练 | 1 周 | K8s/IaC、端到端压测、PITR、故障矩阵、告警通知 | staging 验收报告和容量边界 |
| E：用户与展示 | 3–5 天 | 5 人研究、修复复测、正式 Demo 视频 | 匿名数据、改版证据、可公开演示 |

如果只剩一周，优先完成 A + B；它们对面试说服力的提升高于继续增加框架或页面。

## 5. 下一版完成定义

以下全部满足后，才可以把项目从“可写简历的强工程 MVP”升级描述为“经过 staging 验收的
企业 Agent 平台原型”：

- 固定任务集按支持域分层，安全违规与未授权成功写入均为 0；
- 至少两种真实模型有重复运行、成本、时延、方差与人工抽检报告；
- GitHub 沙箱完成 OAuth、写入、验证、撤销、Webhook 和响应丢失恢复；
- 知识/Memory/Eval 在持久后端中跨重启保持一致，并通过 RLS 对抗测试；
- Temporal queue start、Outbox age、恢复积压和 Trace 完整度都能计算并告警；
- staging 负载和故障注入满足已声明阈值，报告中包含失败结果而非只保留最佳值；
- 完成接近目标数据量的备份、PITR 和对象存储恢复，给出可信 RPO/RTO；
- 5 名真实用户完成统一任务，原始匿名数据、问题和改版结果可追溯；
- Demo 视频、简历数字、README 和证据索引引用同一版本报告。

## 6. 明确不做与风险控制

- 不宣称 exactly-once；只证明定义失败模型下重复业务副作用为 0；
- 不用 header identity、InMemorySecretStore、LocalObjectStore 或 hash embedding 冒充生产实现；
- 不用单机 31 KB 恢复时间冒充生产 RTO，不用 in-process 813.90 req/s 冒充系统容量；
- 不把 20/20 确定性安全回归写成通过渗透测试；
- 不伪造 GitHub、云模型、用户研究、SUS、月度 SLO 或远程 CI 结果；
- 不在没有云资源时提交空 Terraform，也不在没有消融数据时堆多 Agent。

## 7. 文档与证据入口

- 简历数字与边界：`docs/resume-evidence.md`；
- V3 架构与时序：`docs/architecture-v3.md`；
- Agent 基线：`evals/reports/baseline-v1/`；
- 当前支持域门基线：`evals/reports/intent-gated-v2/`；
- 规划安全设计：`docs/planning-safety-gate.md`；
- 安全/检索：`evals/reports/security-v1/`、`evals/reports/retrieval-v1/`；
- Temporal/RLS/备份：`docs/reports/`；
- SLO 与 Runbook：`docs/slo-and-alerts.md`、`docs/observability.md`；
- 部署和容量：`docs/deployment-and-supply-chain.md`、`docs/performance.md`；
- Demo 与用户研究：`docs/demo-runbook.md`、`docs/user-study-protocol.md`。

这份补充方案以“事实、边界、下一步”作为主线。当前项目已经足够进入简历；后续投入应优先
把现有强架构变成真实模型、真实 SaaS、真实 staging 和真实用户四条外部证据，而不是继续增加
无法量化价值的新组件。
