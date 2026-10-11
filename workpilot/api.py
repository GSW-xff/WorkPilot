from __future__ import annotations

import hashlib
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from pydantic import BaseModel, Field

from workpilot.auth import AuthenticationError, OIDCVerifier, Principal
from workpilot.config import Settings
from workpilot.connectors.base import CapabilityRegistry, ConnectorError
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.connectors.github import GitHubOAuthManager, GitHubWebhookVerifier
from workpilot.credentials import InMemorySecretStore
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.knowledge import KnowledgeError, KnowledgeService, LocalObjectStore
from workpilot.mcp import MCPServer
from workpilot.memory import MemoryPolicyError, MemoryService
from workpilot.model_gateway import (
    DeterministicModelGateway,
    ModelGateway,
    ModelPolicy,
    OpenAICompatibleModelGateway,
    RunBudget,
)
from workpilot.models import TaskPlan
from workpilot.planner import DemoPlanner, StructuredPlanner
from workpilot.repository import InMemoryTaskRepository, TaskNotFoundError, TaskRepository
from workpilot.runtime import WorkPilotService
from workpilot.telemetry import TELEMETRY, configure_otlp
from workpilot.workflows.client import TemporalTaskClient
from workpilot.workflows.temporal import ApprovalCommand


class CreateTaskRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=4_000)
    recipient: str = "team@example.com"


class ClarifyTaskRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=4_000)
    recipient: str = "team@example.com"


class ApprovalRequest(BaseModel):
    step_id: str
    parameter_hash: str


class RejectionRequest(BaseModel):
    step_id: str
    reason: str = Field(min_length=1, max_length=1_000)


class KnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["lexical", "vector", "hybrid_rrf"] = "hybrid_rrf"


class FeedbackRequest(BaseModel):
    task_id: str | None = None
    category: Literal["correct", "incorrect", "confusing", "recovery"]
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2_000)


class MemoryCreateRequest(BaseModel):
    kind: Literal["episodic", "semantic"]
    title: str = Field(min_length=1, max_length=200)
    content: dict[str, object]
    source_refs: list[str] = Field(min_length=1, max_length=20)
    source_trust: Literal["system", "trusted", "untrusted"]
    confidence: float = Field(ge=0, le=1)
    ttl_days: int = Field(default=30, ge=1, le=365)
    user_confirmed: bool = False


class MemoryUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: dict[str, object]
    confidence: float = Field(ge=0, le=1)


async def tenant_context(
    request: Request,
    x_tenant_id: Annotated[str, Header(min_length=1)] = "demo",
    x_user_id: Annotated[str, Header(min_length=1)] = "local-user",
    authorization: Annotated[str | None, Header()] = None,
) -> tuple[str, str]:
    verifier: OIDCVerifier | None = request.app.state.auth_verifier
    if verifier is None:
        request.state.principal = Principal(
            subject=x_user_id,
            tenant_id=x_tenant_id,
            roles=frozenset({"owner", "approver", "admin"}),
            scopes=frozenset({"*"}),
        )
        return x_tenant_id, x_user_id
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="a bearer token is required")
    try:
        principal = await verifier.verify(authorization.removeprefix("Bearer ").strip())
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    request.state.principal = principal
    return principal.tenant_id, principal.subject


def build_service(
    repository: TaskRepository | None = None,
    settings: Settings | None = None,
) -> tuple[WorkPilotService, FakeEnterpriseAdapter]:
    settings = settings or Settings.from_env()
    adapter = FakeEnterpriseAdapter()
    registry = CapabilityRegistry([adapter])
    planner = _build_planner(settings, registry)
    service = WorkPilotService(
        repository=repository or build_repository(settings),
        registry=registry,
        planner=planner,
        max_steps=settings.max_steps,
        allowed_recipient_domains=set(settings.allowed_recipient_domains),
    )
    return service, adapter


def _build_planner(settings: Settings, registry: CapabilityRegistry):
    if settings.planner_mode == "demo":
        return DemoPlanner()
    policy = ModelPolicy(provider=settings.planner_mode, model=settings.model_name)
    budget = RunBudget(
        max_input_tokens=settings.model_input_budget,
        max_output_tokens=settings.model_output_budget,
        max_cost_usd=settings.model_cost_budget_usd,
    )
    if settings.planner_mode == "fake":

        def response_factory(messages):
            goal = "structured planning task"
            recipient = "team@example.com"
            for message in messages:
                if message.source != "user://goal":
                    continue
                for line in message.content.splitlines():
                    if line.startswith("Goal: "):
                        goal = line.removeprefix("Goal: ")
                    elif line.startswith("Requested recipient: "):
                        recipient = line.removeprefix("Requested recipient: ")
            return DemoPlanner().plan(goal, recipient).model_dump(mode="json")

        gateway: ModelGateway = DeterministicModelGateway(response_factory=response_factory)
    elif settings.planner_mode == "openai":
        if not settings.model_api_key:
            raise ValueError("WORKPILOT_MODEL_API_KEY is required for openai planner mode")
        gateway = OpenAICompatibleModelGateway(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
        )
    else:
        raise ValueError(f"unsupported planner mode: {settings.planner_mode}")
    return StructuredPlanner(
        gateway,
        available_tools=registry.planning_tools(),
        fixed_risks=registry.risks,
        model_policy=policy,
        budget=budget,
        max_steps=settings.max_steps,
    )


def build_repository(settings: Settings) -> TaskRepository:
    if not settings.database_url:
        return InMemoryTaskRepository()
    engine = create_database_engine(settings.database_url)
    return SQLAlchemyTaskRepository(engine, create_schema=settings.auto_create_schema)


def create_app(
    repository: TaskRepository | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.otlp_endpoint:
        configure_otlp(settings.otlp_endpoint, settings.service_name)
    service, adapter = build_service(repository, settings)
    auth_verifier = _build_auth_verifier(settings)
    knowledge = KnowledgeService(
        LocalObjectStore(Path(settings.knowledge_object_dir)),
        max_file_bytes=settings.knowledge_max_file_bytes,
    )
    memory = MemoryService()
    secret_store = InMemorySecretStore()
    github_oauth = None
    if (
        settings.github_client_id
        and settings.github_client_secret
        and settings.github_oauth_state_secret
    ):
        github_oauth = GitHubOAuthManager(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            redirect_uri=settings.github_redirect_uri,
            state_secret=settings.github_oauth_state_secret,
            secret_store=secret_store,
        )
    github_webhook = (
        GitHubWebhookVerifier(settings.github_webhook_secret)
        if settings.github_webhook_secret
        else None
    )
    mcp_server = MCPServer("workpilot-local-v1", adapter)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.temporal_target:
            _app.state.temporal = await TemporalTaskClient.connect(
                settings.temporal_target, settings.temporal_task_queue
            )
        yield
        service.repository.close()
        if auth_verifier is not None:
            await auth_verifier.close()

    app = FastAPI(
        title="WorkPilot API",
        version="0.2.0",
        description="Safe, approval-bound and auditable cross-system task runtime.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "PATCH", "POST"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "Authorization",
            "traceparent",
            "X-Request-ID",
            "X-Tenant-ID",
            "X-User-ID",
        ],
    )
    app.state.service = service
    app.state.auth_verifier = auth_verifier
    app.state.auth_mode = settings.auth_mode
    app.state.knowledge = knowledge
    app.state.memory = memory
    app.state.fake_adapter = adapter
    app.state.temporal = None
    app.state.github_oauth = github_oauth
    app.state.github_webhook = github_webhook
    app.state.mcp_server = mcp_server
    app.state.idempotent_creates = {}
    app.state.feedback = []

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or __import__("uuid").uuid4().hex
        token = otel_context.attach(extract(request.headers))
        started = time.perf_counter()
        try:
            with TELEMETRY.span(
                "http.request",
                {
                    "workpilot.request.id": request_id,
                    "workpilot.http.method": request.method,
                    "workpilot.http.path": request.url.path,
                },
            ):
                response = await call_next(request)
        finally:
            otel_context.detach(token)
        response.headers["X-Request-ID"] = request_id
        route = str(getattr(request.scope.get("route"), "path", "unmatched"))
        labels: dict[str, str] = {
            "method": request.method,
            "route": route,
            "status": str(response.status_code),
        }
        TELEMETRY.metrics.counter(
            "api_request_total",
            method=labels["method"],
            route=labels["route"],
            status=labels["status"],
        )
        TELEMETRY.metrics.counter(
            "api_request_trace_total",
            method=labels["method"],
            route=labels["route"],
            status=labels["status"],
        )
        TELEMETRY.metrics.observe(
            "api_request_duration_seconds",
            time.perf_counter() - started,
            **labels,
        )
        return response

    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(request: Request, _exc):
        return _problem(request, 404, "Task not found", "task not found")

    @app.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException):
        return _problem(request, exc.status_code, "Request failed", str(exc.detail))

    @app.get("/health")
    async def health() -> dict[str, str]:
        storage = (
            "sqlalchemy" if isinstance(service.repository, SQLAlchemyTaskRepository) else "memory"
        )
        return {"status": "ok", "runtime": "fake-enterprise", "storage": storage}

    @app.get("/v1/auth/config")
    async def auth_config():
        return {
            "mode": settings.auth_mode,
            "issuer": settings.oidc_issuer if settings.auth_mode == "oidc" else None,
            "audience": settings.oidc_audience if settings.auth_mode == "oidc" else None,
        }

    @app.get("/v1/templates")
    async def task_templates():
        return [
            {
                "id": "weekly-report",
                "name": "项目周报",
                "goal": "收集本周项目进展，生成周报，为缺失事项创建跟进任务，并在审批后发送邮件。",
            },
            {
                "id": "meeting-followup",
                "name": "会议跟进",
                "goal": "整理会议结论、负责人和截止时间，审批后创建跟进任务。",
            },
            {
                "id": "issue-summary",
                "name": "Issue 汇总",
                "goal": "汇总当前高优先级 Issue，生成带来源的风险报告。",
            },
        ]

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        return TELEMETRY.metrics.render_prometheus()

    @app.get("/")
    async def console() -> FileResponse:
        return FileResponse(Path(__file__).parents[1] / "apps" / "web" / "index.html")

    @app.post("/v1/tasks", status_code=201)
    async def create_task(
        body: CreateTaskRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ):
        tenant_id, user_id = context
        key = (tenant_id, idempotency_key) if idempotency_key else None
        if key and key in app.state.idempotent_creates:
            return service.repository.get(tenant_id, app.state.idempotent_creates[key])
        task = await service.create_task_async(tenant_id, user_id, body.goal, body.recipient)
        if key:
            app.state.idempotent_creates[key] = task.id
        return task

    @app.post("/v1/tasks/{task_id}/clarify")
    async def clarify_task(
        task_id: str,
        body: ClarifyTaskRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        try:
            return await service.clarify_task(
                tenant_id,
                task_id,
                user_id,
                body.goal,
                body.recipient,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/tasks")
    async def list_tasks(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: str | None = None,
    ):
        tenant_id, _ = context
        tasks = service.repository.list(tenant_id)
        if status:
            tasks = [task for task in tasks if task.status.value == status.upper()]
        return {
            "items": tasks[offset : offset + limit],
            "limit": limit,
            "offset": offset,
            "total": len(tasks),
        }

    @app.get("/v1/recovery")
    async def recovery_cases(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return service.recovery_cases(tenant_id)

    @app.get("/v1/approvals")
    async def approval_inbox(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return [
            {
                "task_id": task.id,
                "goal": task.goal,
                "task_status": task.status,
                "approval": approval,
            }
            for task in service.repository.list(tenant_id)
            for approval in task.approvals
            if approval.status.value == "PENDING"
        ]

    @app.get("/v1/evaluations/latest")
    async def latest_evaluations(
        _context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        root = Path(__file__).parents[1] / "evals" / "reports"
        reports = {}
        for name, relative in {
            "agent": Path("intent-gated-v2/eval-report.json"),
            "retrieval": Path("retrieval-v1/report.json"),
            "security": Path("security-v1/report.json"),
        }.items():
            path = root / relative
            reports[name] = json.loads(path.read_text()) if path.exists() else None
        return reports

    @app.post("/v1/feedback", status_code=201)
    async def record_feedback(
        body: FeedbackRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        if body.task_id is not None:
            service.repository.get(tenant_id, body.task_id)
        item = {
            "id": f"feedback-{len(app.state.feedback) + 1}",
            "tenant_id": tenant_id,
            "user_id": user_id,
            **body.model_dump(),
        }
        app.state.feedback.append(item)
        return {"id": item["id"], "accepted": True}

    @app.get("/v1/memories")
    async def list_memories(
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        principal: Principal = request.state.principal
        return memory.list(tenant_id, user_id, is_admin=principal.has_role("admin"))

    @app.post("/v1/memories", status_code=201)
    async def create_memory(
        body: MemoryCreateRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        try:
            return memory.create(
                tenant_id=tenant_id,
                owner_id=user_id,
                **body.model_dump(),
            )
        except MemoryPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/memories/from-task/{task_id}", status_code=201)
    async def remember_task(
        task_id: str,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
        ttl_days: Annotated[int, Query(ge=1, le=365)] = 90,
    ):
        tenant_id, user_id = context
        task = service.repository.get(tenant_id, task_id)
        principal: Principal = request.state.principal
        if task.user_id != user_id and not principal.has_role("admin"):
            raise HTTPException(status_code=403, detail="only the task owner can remember it")
        try:
            return memory.remember_task(task, user_id, ttl_days)
        except MemoryPolicyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch("/v1/memories/{memory_id}")
    async def update_memory(
        memory_id: str,
        body: MemoryUpdateRequest,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        principal: Principal = request.state.principal
        try:
            return memory.update(
                tenant_id,
                user_id,
                memory_id,
                is_admin=principal.has_role("admin"),
                **body.model_dump(),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory not found") from exc

    @app.delete("/v1/memories/{memory_id}", status_code=204)
    async def delete_memory(
        memory_id: str,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ) -> Response:
        tenant_id, user_id = context
        principal: Principal = request.state.principal
        try:
            memory.delete(
                tenant_id,
                user_id,
                memory_id,
                is_admin=principal.has_role("admin"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory not found") from exc
        return Response(status_code=204)

    @app.get("/v1/tasks/{task_id}")
    async def get_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return service.repository.get(tenant_id, task_id)

    @app.post("/v1/tasks/{task_id}/run")
    async def run_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        if app.state.temporal is not None:
            task = service.repository.get(tenant_id, task_id)
            await app.state.temporal.start(tenant_id, task_id)
            return task
        return await _translate_value_error(service.run(tenant_id, task_id))

    @app.post("/v1/tasks/{task_id}/replan")
    async def replan_task(
        task_id: str,
        body: TaskPlan,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        try:
            task, plan_diff = service.replan(tenant_id, task_id, body)
            return {"task": task, "diff": plan_diff}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/approve")
    async def approve_task(
        task_id: str,
        body: ApprovalRequest,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        _require_role(request, "approver")
        task = service.repository.get(tenant_id, task_id)
        if settings.auth_mode == "oidc" and task.user_id == user_id:
            raise HTTPException(status_code=403, detail="task creator cannot approve own action")
        if app.state.temporal is not None:
            await app.state.temporal.approve(
                ApprovalCommand(
                    tenant_id=tenant_id,
                    task_id=task_id,
                    step_id=body.step_id,
                    parameter_hash=body.parameter_hash,
                    approver=user_id,
                )
            )
            return service.repository.get(tenant_id, task_id)
        try:
            return service.approve(tenant_id, task_id, body.step_id, body.parameter_hash, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/reject")
    async def reject_task(
        task_id: str,
        body: RejectionRequest,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        _require_role(request, "approver")
        if app.state.temporal is not None:
            task = service.repository.get(tenant_id, task_id)
            approval = next(
                (
                    item
                    for item in reversed(task.approvals)
                    if item.step_id == body.step_id and item.status.value == "PENDING"
                ),
                None,
            )
            if approval is None:
                raise HTTPException(status_code=409, detail="no pending approval")
            await app.state.temporal.approve(
                ApprovalCommand(
                    tenant_id=tenant_id,
                    task_id=task_id,
                    step_id=body.step_id,
                    parameter_hash=approval.parameter_hash,
                    approver=user_id,
                    approved=False,
                    reason=body.reason,
                )
            )
            return service.repository.get(tenant_id, task_id)
        try:
            return service.reject(tenant_id, task_id, body.step_id, user_id, body.reason)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/pause")
    async def pause_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        if app.state.temporal is not None:
            task = service.repository.get(tenant_id, task_id)
            await app.state.temporal.signal(tenant_id, task_id, "pause")
            return task
        return _call_or_conflict(service.pause, tenant_id, task_id)

    @app.post("/v1/tasks/{task_id}/resume")
    async def resume_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        if app.state.temporal is not None:
            task = service.repository.get(tenant_id, task_id)
            await app.state.temporal.signal(tenant_id, task_id, "resume")
            return task
        return _call_or_conflict(service.resume, tenant_id, task_id)

    @app.post("/v1/tasks/{task_id}/cancel")
    async def cancel_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        if app.state.temporal is not None:
            task = service.repository.get(tenant_id, task_id)
            await app.state.temporal.signal(tenant_id, task_id, "cancel")
            return task
        return _call_or_conflict(service.cancel, tenant_id, task_id)

    @app.get("/v1/tasks/{task_id}/artifacts")
    async def task_artifacts(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return service.repository.get(tenant_id, task_id).artifacts

    @app.get("/v1/tasks/{task_id}/replay")
    async def task_replay(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        task = service.repository.get(tenant_id, task_id)
        return {"task_id": task.id, "status": task.status, "events": task.events}

    @app.get("/v1/tasks/{task_id}/audit-export")
    async def export_task_audit(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        task = service.repository.get(tenant_id, task_id)
        payload = {
            "schema": "workpilot.audit.v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "task": task.model_dump(mode="json"),
            "integrity": {
                "event_count": len(task.events),
                "ledger_keys": [item.idempotency_key for item in task.ledger],
                "artifact_ids": [item.id for item in task.artifacts],
            },
        }
        return JSONResponse(
            payload,
            headers={"Content-Disposition": f'attachment; filename="{task.id}-audit.json"'},
        )

    @app.get("/v1/tasks/{task_id}/events")
    async def task_events(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
        last_event_id: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
    ):
        tenant_id, _ = context
        task = service.repository.get(tenant_id, task_id)

        async def stream():
            for event in task.events:
                if last_event_id is not None and event.sequence <= last_event_id:
                    continue
                payload = event.model_dump(mode="json")
                data = json.dumps(payload, ensure_ascii=False)
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {data}\n\n"
            yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/v1/knowledge/documents", status_code=201)
    async def add_document(
        body: KnowledgeDocumentRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        document = {
            "id": f"document-{len(adapter.state.documents) + 1}",
            "tenant_id": tenant_id,
            "title": body.title,
            "content": body.content,
        }
        adapter.add_document(document)
        return {"id": document["id"], "title": document["title"]}

    @app.post("/v1/knowledge/files", status_code=201)
    async def upload_knowledge_file(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
        file: Annotated[UploadFile, File()],
        visibility: Annotated[str, Form()] = "private",
    ):
        tenant_id, user_id = context
        if visibility not in {"private", "tenant"}:
            raise HTTPException(status_code=422, detail="visibility must be private or tenant")
        content = await file.read(settings.knowledge_max_file_bytes + 1)
        try:
            return knowledge.ingest(
                tenant_id=tenant_id,
                owner_id=user_id,
                filename=file.filename or "upload",
                media_type=file.content_type or "application/octet-stream",
                content=content,
                visibility=cast(Literal["private", "tenant"], visibility),
            )
        except KnowledgeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/knowledge/files")
    async def list_knowledge_files(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        return knowledge.list_documents(tenant_id, user_id)

    @app.get("/v1/knowledge/files/{document_id}")
    async def get_knowledge_file(
        document_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        try:
            return knowledge.get(tenant_id, user_id, document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc

    @app.get("/v1/knowledge/files/{document_id}/content")
    async def open_knowledge_file(
        document_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        try:
            document = knowledge.get(tenant_id, user_id, document_id)
            content = knowledge.original(tenant_id, user_id, document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc
        safe_filename = document.filename.replace('"', "")
        return Response(
            content,
            media_type=document.media_type,
            headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
        )

    @app.delete("/v1/knowledge/files/{document_id}", status_code=204)
    async def delete_knowledge_file(
        document_id: str,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ) -> Response:
        tenant_id, user_id = context
        principal: Principal = request.state.principal
        try:
            knowledge.delete(
                tenant_id,
                user_id,
                document_id,
                is_admin=principal.has_role("admin"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="document not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/v1/knowledge/search")
    async def search_knowledge(
        body: KnowledgeSearchRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        return {
            "query": body.query,
            "mode": body.mode,
            "citations": knowledge.search(
                tenant_id=tenant_id,
                user_id=user_id,
                query=body.query,
                top_k=body.top_k,
                mode=body.mode,
            ),
        }

    @app.get("/v1/connectors/github/authorize")
    async def github_authorize(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        if github_oauth is None:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        tenant_id, user_id = context
        return {"authorization_url": github_oauth.authorization_url(tenant_id, user_id)}

    @app.get("/v1/connectors/github/callback")
    async def github_callback(code: str, state: str):
        if github_oauth is None:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        try:
            return await github_oauth.exchange(code, state)
        except ConnectorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/connectors")
    async def connector_accounts(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        if github_oauth is None:
            return []
        return [
            account
            for (stored_tenant, _account_id), account in github_oauth.accounts.items()
            if stored_tenant == tenant_id
        ]

    @app.delete("/v1/connectors/github/{account_id}")
    async def revoke_github(
        account_id: str,
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        _require_role(request, "admin")
        if github_oauth is None:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        tenant_id, _ = context
        try:
            return await github_oauth.revoke_remote(tenant_id, account_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="connector account not found") from exc
        except ConnectorError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/connectors/github/webhook")
    async def github_webhook_event(request: Request):
        if github_webhook is None:
            raise HTTPException(status_code=503, detail="GitHub webhook is not configured")
        try:
            body = await request.body()
            payload = github_webhook.verify(
                body,
                request.headers.get("X-Hub-Signature-256", ""),
                request.headers.get("X-GitHub-Delivery", ""),
            )
            return {
                "accepted": True,
                "action": payload.get("action"),
                "evidence": {
                    "delivery_id": request.headers.get("X-GitHub-Delivery"),
                    "event": request.headers.get("X-GitHub-Event"),
                    "repository": payload.get("repository", {}).get("full_name"),
                    "payload_sha256": hashlib.sha256(body).hexdigest(),
                    "signature_valid": True,
                },
            }
        except (ConnectorError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/mcp")
    async def mcp_endpoint(
        request: Request,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        payload = await request.json()
        return await mcp_server.handle(payload, tenant_id)

    return app


def _build_auth_verifier(settings: Settings) -> OIDCVerifier | None:
    if settings.auth_mode == "headers":
        return None
    if settings.auth_mode != "oidc":
        raise ValueError(f"unsupported auth mode: {settings.auth_mode}")
    if not settings.oidc_issuer or not settings.oidc_audience or not settings.oidc_jwks_url:
        raise ValueError("OIDC issuer, audience and JWKS URL are required in oidc auth mode")
    return OIDCVerifier(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        jwks_url=settings.oidc_jwks_url,
    )


def _require_role(request: Request, role: str) -> None:
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None or not principal.has_role(role):
        raise HTTPException(status_code=403, detail=f"{role} role is required")


async def _translate_value_error(awaitable):
    try:
        return await awaitable
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _call_or_conflict(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _problem(request: Request, status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
        },
    )


app = create_app()
