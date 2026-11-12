from __future__ import annotations

from datetime import datetime, timedelta
from threading import RLock
from typing import Protocol

from workpilot.lease import TaskLease
from workpilot.models import TaskRun, utc_now


class TaskNotFoundError(KeyError):
    pass


class ConcurrentUpdateError(RuntimeError):
    pass


class TaskRepository(Protocol):
    def add(self, task: TaskRun) -> TaskRun: ...

    def get(self, tenant_id: str, task_id: str) -> TaskRun: ...

    def save(self, task: TaskRun, expected_version: int | None = None) -> TaskRun: ...

    def list(self, tenant_id: str) -> list[TaskRun]: ...

    def claim_lease(
        self, tenant_id: str, task_id: str, owner: str, lease_seconds: float
    ) -> TaskLease | None: ...

    def renew_lease(
        self,
        tenant_id: str,
        task_id: str,
        owner: str,
        fence_token: int,
        lease_seconds: float,
    ) -> bool: ...

    def release_lease(
        self, tenant_id: str, task_id: str, owner: str, fence_token: int
    ) -> bool: ...

    def owns_lease(
        self, tenant_id: str, task_id: str, owner: str, fence_token: int
    ) -> bool: ...

    def close(self) -> None: ...


class InMemoryTaskRepository(TaskRepository):
    """Tenant-aware repository with copy-on-read semantics for the local MVP."""

    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], TaskRun] = {}
        self._leases: dict[tuple[str, str], tuple[str | None, datetime | None, int]] = {}
        self._lock = RLock()

    def add(self, task: TaskRun) -> TaskRun:
        key = (task.tenant_id, task.id)
        with self._lock:
            if key in self._tasks:
                raise ValueError(f"task already exists: {task.id}")
            self._tasks[key] = task.model_copy(deep=True)
            return task.model_copy(deep=True)

    def get(self, tenant_id: str, task_id: str) -> TaskRun:
        with self._lock:
            try:
                return self._tasks[(tenant_id, task_id)].model_copy(deep=True)
            except KeyError as exc:
                raise TaskNotFoundError(task_id) from exc

    def save(self, task: TaskRun, expected_version: int | None = None) -> TaskRun:
        key = (task.tenant_id, task.id)
        with self._lock:
            current = self._tasks.get(key)
            if current is None:
                raise TaskNotFoundError(task.id)
            if expected_version is not None and current.version != expected_version:
                raise ConcurrentUpdateError("task was updated concurrently")
            stored = task.model_copy(
                deep=True,
                update={"version": current.version + 1, "updated_at": utc_now()},
            )
            self._tasks[key] = stored
            return stored.model_copy(deep=True)

    def list(self, tenant_id: str) -> list[TaskRun]:
        with self._lock:
            return [
                task.model_copy(deep=True)
                for (stored_tenant, _), task in self._tasks.items()
                if stored_tenant == tenant_id
            ]

    def claim_lease(
        self, tenant_id: str, task_id: str, owner: str, lease_seconds: float
    ) -> TaskLease | None:
        key = (tenant_id, task_id)
        now = utc_now()
        with self._lock:
            if key not in self._tasks:
                raise TaskNotFoundError(task_id)
            current = self._leases.get(key)
            if (
                current is not None
                and current[0] is not None
                and current[0] != owner
                and current[1] is not None
                and current[1] > now
            ):
                return None
            fence = (current[2] if current is not None else 0) + 1
            expires_at = now + timedelta(seconds=lease_seconds)
            self._leases[key] = (owner, expires_at, fence)
            return TaskLease(tenant_id, task_id, owner, fence, expires_at)

    def renew_lease(
        self,
        tenant_id: str,
        task_id: str,
        owner: str,
        fence_token: int,
        lease_seconds: float,
    ) -> bool:
        key = (tenant_id, task_id)
        with self._lock:
            current = self._leases.get(key)
            if current is None or current[0] != owner or current[2] != fence_token:
                return False
            self._leases[key] = (
                owner,
                utc_now() + timedelta(seconds=lease_seconds),
                fence_token,
            )
            return True

    def release_lease(
        self, tenant_id: str, task_id: str, owner: str, fence_token: int
    ) -> bool:
        key = (tenant_id, task_id)
        with self._lock:
            current = self._leases.get(key)
            if current is None or current[0] != owner or current[2] != fence_token:
                return False
            # Keep the fence counter: it must stay monotonic across releases, exactly
            # like the persisted column, or a stale token could look current again.
            self._leases[key] = (None, None, fence_token)
            return True

    def owns_lease(
        self, tenant_id: str, task_id: str, owner: str, fence_token: int
    ) -> bool:
        key = (tenant_id, task_id)
        with self._lock:
            current = self._leases.get(key)
            return (
                current is not None
                and current[0] == owner
                and current[2] == fence_token
                and current[1] is not None
                and current[1] > utc_now()
            )

    def close(self) -> None:
        return None
