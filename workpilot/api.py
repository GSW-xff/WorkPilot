from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from workpilot.config import Settings
from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
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
    service, adapter = build_service(repository, settings)

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
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Tenant-ID", "X-User-ID"],
    )
    app.state.service = service
    app.state.fake_adapter = adapter
    app.state.temporal = None

    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(_request, _exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": "task not found"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        storage = (
            "sqlalchemy" if isinstance(service.repository, SQLAlchemyTaskRepository) else "memory"
        )
        return {"status": "ok", "runtime": "fake-enterprise", "storage": storage}

    @app.get("/")
    async def console() -> FileResponse:
        return FileResponse(Path(__file__).parents[1] / "apps" / "web" / "index.html")

    @app.post("/v1/tasks", status_code=201)
    async def create_task(
        body: CreateTaskRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        return await service.create_task_async(tenant_id, user_id, body.goal, body.recipient)

    @app.get("/v1/tasks")
    async def list_tasks(
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return service.repository.list(tenant_id)

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
    ):
        tenant_id, _ = context
        task = service.repository.get(tenant_id, task_id)

        async def stream():
            for event in task.events:
                payload = event.model_dump(mode="json")
                data = json.dumps(payload, ensure_ascii=False)
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {data}\n\n"

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


app = create_app()
