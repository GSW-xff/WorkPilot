# WorkPilot V3 架构与关键时序

## C4：容器视图

```mermaid
C4Container
  title WorkPilot V3 container view
  Person(user, "Knowledge worker", "Creates and approves governed tasks")
  Person(admin, "Platform operator", "Reviews recovery, traces and evaluations")
  System_Boundary(workpilot, "WorkPilot") {
    Container(console, "Operations console", "HTML/CSS/JavaScript", "Task, approval, recovery and evaluation views")
    Container(api, "Control plane", "FastAPI", "OIDC/RBAC, REST/SSE, policy entry points")
    Container(worker, "Durable worker", "Temporal Python SDK", "Workflow and Activity execution")
    Container(runtime, "Agent runtime", "Python", "Context, structured planning, policy, execution and verification")
    Container(eval, "Evaluation runner", "Python", "Versioned datasets, graders and regression reports")
    ContainerDb(postgres, "Task database", "PostgreSQL/pgvector", "Tenant facts, RLS, ledger and outbox")
    ContainerDb(objects, "Evidence store", "Object storage adapter", "Uploaded files and browser evidence")
    Container(observe, "Observability", "OTel/Tempo/Prometheus/Grafana", "Traces, metrics, SLO rules and dashboards")
  }
  System_Ext(temporal, "Temporal service", "Durable event history and scheduling")
  System_Ext(github, "GitHub", "OAuth, issues and webhooks")
  System_Ext(mcp, "MCP server", "Pinned read-only tool schemas")
  Rel(user, console, "Uses")
  Rel(admin, console, "Operates")
  Rel(console, api, "REST/SSE with OIDC")
  Rel(api, temporal, "Starts, updates and signals workflows")
  Rel(temporal, worker, "Dispatches workflow/activity tasks")
  Rel(worker, runtime, "Runs deterministic boundaries")
  Rel(runtime, postgres, "Tenant-scoped transactions")
  Rel(runtime, objects, "Stores and reads evidence")
  Rel(runtime, github, "OAuth tool calls with idempotency")
  Rel(runtime, mcp, "Schema-pinned read calls")
  Rel(api, observe, "OTLP and Prometheus")
  Rel(worker, observe, "OTLP")
  Rel(eval, runtime, "Executes versioned cases")
```

实现保持“模块化单体 + 独立 Worker”。评测、API 和 Worker 是独立运行入口，但共享领域模型；
没有为了简历关键词提前拆微服务。

## 创建、审批与验证时序

```mermaid
sequenceDiagram
  actor U as User
  participant A as FastAPI
  participant T as Temporal
  participant R as Agent Runtime
  participant P as Policy
  participant L as Ledger/DB
  participant X as Tool Adapter

  U->>A: POST /v1/tasks (Idempotency-Key)
  A->>R: build context + structured plan
  R->>P: validate DAG, capability, risk and budget
  R->>L: task + plan + timeline + outbox (one transaction)
  U->>A: POST /run
  A->>T: start tenant-scoped workflow
  T->>R: run activity
  R->>P: evaluate step
  alt R2 approval required
    R->>L: approval preview + parameter hash + checkpoint
    R-->>T: WAITING_APPROVAL
    U->>A: approve(step, parameter_hash)
    A->>T: Workflow Update
    T->>R: continue activity
  end
  R->>L: reserve stable idempotency key
  R->>X: lookup before execute
  alt remote effect absent
    R->>X: execute(idempotency key)
  end
  R->>X: verify by independent read
  R->>L: confirmed ledger + artifact + checkpoint + outbox
  R-->>U: SSE timeline and terminal result
```

## 响应丢失后的恢复时序

```mermaid
sequenceDiagram
  participant R as Runtime
  participant L as Ledger
  participant X as Tool Adapter
  R->>L: RESERVED, attempt=1
  R->>X: execute(stable key)
  X--xR: remote committed, response lost
  R->>L: UNKNOWN + reconciliation REQUIRED
  Note over R,L: Worker may restart here
  R->>X: lookup(stable key)
  X-->>R: existing remote object
  R->>L: CONFIRMED without re-executing
```

边界：Temporal 提供 at-least-once 调度，不提供外部 SaaS exactly-once。业务无重复的证据来自
稳定键、Ledger、lookup-before-retry 和独立远端核验的组合。
