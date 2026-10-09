from __future__ import annotations

from threading import RLock

from workpilot.models import TaskRun, utc_now


class TaskNotFoundError(KeyError):
    pass


class InMemoryTaskRepository:
    """Tenant-aware repository with copy-on-read semantics for the local MVP."""

    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], TaskRun] = {}
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
                raise RuntimeError("task was updated concurrently")
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

