from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from pydantic import BaseModel, Field

from workpilot.config import Settings
from workpilot.connectors.base import CapabilityRegistry, ConnectorError
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.connectors.github import GitHubOAuthManager, GitHubWebhookVerifier
from workpilot.credentials import InMemorySecretStore
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.mcp import MCPServer
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


class ApprovalRequest(BaseModel):
    step_id: str
    parameter_hash: str


class RejectionRequest(BaseModel):
    step_id: str
    reason: str = Field(min_length=1, max_length=1_000)


class KnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)


def tenant_context(
    x_tenant_id: Annotated[str, Header(min_length=1)] = "demo",
    x_user_id: Annotated[str, Header(min_length=1)] = "local-user",
) -> tuple[str, str]:
    return x_tenant_id, x_user_id


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
        allow_methods=["DELETE", "GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "traceparent",
            "X-Request-ID",
            "X-Tenant-ID",
            "X-User-ID",
        ],
    )
    app.state.service = service
    app.state.fake_adapter = adapter
    app.state.temporal = None
    app.state.github_oauth = github_oauth
    app.state.github_webhook = github_webhook
    app.state.mcp_server = mcp_server
    app.state.idempotent_creates = {}

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
        TELEMETRY.metrics.observe(
            "api_request_duration_seconds",
            time.perf_counter() - started,
            method=request.method,
            status=str(response.status_code),
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
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        if app.state.temporal is not None:
            service.repository.get(tenant_id, task_id)
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
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
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
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        if github_oauth is None:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        tenant_id, _ = context
        try:
            return github_oauth.revoke(tenant_id, account_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="connector account not found") from exc

    @app.post("/v1/connectors/github/webhook")
    async def github_webhook_event(request: Request):
        if github_webhook is None:
            raise HTTPException(status_code=503, detail="GitHub webhook is not configured")
        try:
            payload = github_webhook.verify(
                await request.body(),
                request.headers.get("X-Hub-Signature-256", ""),
                request.headers.get("X-GitHub-Delivery", ""),
            )
            return {"accepted": True, "action": payload.get("action")}
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
