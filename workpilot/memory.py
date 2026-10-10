from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from workpilot.models import TaskRun, TaskStatus


class MemoryPolicyError(ValueError):
    pass


class MemoryRecord(BaseModel):
    id: str
    tenant_id: str
    owner_id: str
    kind: Literal["episodic", "semantic"]
    title: str
    content: dict[str, object]
    source_refs: list[str]
    source_trust: Literal["system", "trusted", "untrusted"]
    confidence: float = Field(ge=0, le=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    user_confirmed: bool = False

    @property
    def expired(self) -> bool:
        return self.expires_at <= datetime.now(UTC)


class MemoryService:
    """Tenant-scoped memory with provenance, expiry, and explicit trust gates."""

    def __init__(self, *, default_ttl_days: int = 30, max_ttl_days: int = 365) -> None:
        self.default_ttl_days = default_ttl_days
        self.max_ttl_days = max_ttl_days
        self._records: dict[str, MemoryRecord] = {}

    def create(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        kind: Literal["episodic", "semantic"],
        title: str,
        content: dict[str, object],
        source_refs: list[str],
        source_trust: Literal["system", "trusted", "untrusted"],
        confidence: float,
        ttl_days: int | None = None,
        user_confirmed: bool = False,
    ) -> MemoryRecord:
        if source_trust == "untrusted" and not user_confirmed:
            raise MemoryPolicyError("untrusted content requires explicit user confirmation")
        if not source_refs:
            raise MemoryPolicyError("memory requires at least one source reference")
        ttl = self.default_ttl_days if ttl_days is None else ttl_days
        if ttl < 1 or ttl > self.max_ttl_days:
            raise MemoryPolicyError(f"ttl_days must be between 1 and {self.max_ttl_days}")
        now = datetime.now(UTC)
        record = MemoryRecord(
            id=f"memory-{uuid4().hex[:16]}",
            tenant_id=tenant_id,
            owner_id=owner_id,
            kind=kind,
            title=title,
            content=content,
            source_refs=source_refs,
            source_trust=source_trust,
            confidence=confidence,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=ttl),
            user_confirmed=user_confirmed,
        )
        self._records[record.id] = record
        return record

    def remember_task(self, task: TaskRun, owner_id: str, ttl_days: int = 90) -> MemoryRecord:
        if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise MemoryPolicyError("only terminal tasks can become episodic memory")
        completed = [
            step_id for step_id, step in task.steps.items() if step.status.value == "SUCCEEDED"
        ]
        return self.create(
            tenant_id=task.tenant_id,
            owner_id=owner_id,
            kind="episodic",
            title=f"Task outcome: {task.goal[:120]}",
            content={
                "task_id": task.id,
                "goal": task.goal,
                "status": task.status.value,
                "completed_steps": completed,
                "event_count": len(task.events),
                "artifact_refs": [f"artifact://{item.id}" for item in task.artifacts],
            },
            source_refs=[
                f"task://{task.id}",
                *[f"artifact://{item.id}" for item in task.artifacts],
            ],
            source_trust="system",
            confidence=1.0 if task.status is TaskStatus.SUCCEEDED else 0.7,
            ttl_days=ttl_days,
        )

    def list(self, tenant_id: str, user_id: str, *, is_admin: bool = False) -> list[MemoryRecord]:
        self.purge_expired()
        return [
            record
            for record in self._records.values()
            if record.tenant_id == tenant_id and (record.owner_id == user_id or is_admin)
        ]

    def get(
        self, tenant_id: str, user_id: str, memory_id: str, *, is_admin: bool = False
    ) -> MemoryRecord:
        self.purge_expired()
        try:
            record = self._records[memory_id]
        except KeyError as exc:
            raise KeyError("memory not found") from exc
        if record.tenant_id != tenant_id or (record.owner_id != user_id and not is_admin):
            raise KeyError("memory not found")
        return record

    def update(
        self,
        tenant_id: str,
        user_id: str,
        memory_id: str,
        *,
        title: str,
        content: dict[str, object],
        confidence: float,
        is_admin: bool = False,
    ) -> MemoryRecord:
        record = self.get(tenant_id, user_id, memory_id, is_admin=is_admin)
        record.title = title
        record.content = content
        record.confidence = confidence
        record.updated_at = datetime.now(UTC)
        record.user_confirmed = True
        return record

    def delete(
        self, tenant_id: str, user_id: str, memory_id: str, *, is_admin: bool = False
    ) -> None:
        self.get(tenant_id, user_id, memory_id, is_admin=is_admin)
        del self._records[memory_id]

    def purge_expired(self) -> int:
        expired = [record_id for record_id, record in self._records.items() if record.expired]
        for record_id in expired:
            del self._records[record_id]
        return len(expired)
