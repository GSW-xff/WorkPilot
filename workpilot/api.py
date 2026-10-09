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
from workpilot.repository import InMemoryTaskRepository, TaskNotFoundError, TaskRepository
from workpilot.runtime import WorkPilotService


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
    service = WorkPilotService(
        repository=repository or build_repository(settings),
        registry=CapabilityRegistry([adapter]),
        max_steps=settings.max_steps,
        allowed_recipient_domains=set(settings.allowed_recipient_domains),
    )
    return service, adapter


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

    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(_request, _exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": "task not found"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        storage = (
            "sqlalchemy"
            if isinstance(service.repository, SQLAlchemyTaskRepository)
            else "memory"
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
        return service.create_task(tenant_id, user_id, body.goal, body.recipient)

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
        return await _translate_value_error(service.run(tenant_id, task_id))

    @app.post("/v1/tasks/{task_id}/approve")
    async def approve_task(
        task_id: str,
        body: ApprovalRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
        try:
            return service.approve(
                tenant_id, task_id, body.step_id, body.parameter_hash, user_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/reject")
    async def reject_task(
        task_id: str,
        body: RejectionRequest,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, user_id = context
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
        return _call_or_conflict(service.pause, tenant_id, task_id)

    @app.post("/v1/tasks/{task_id}/resume")
    async def resume_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
        return _call_or_conflict(service.resume, tenant_id, task_id)

    @app.post("/v1/tasks/{task_id}/cancel")
    async def cancel_task(
        task_id: str,
        context: Annotated[tuple[str, str], Depends(tenant_context)],
    ):
        tenant_id, _ = context
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
