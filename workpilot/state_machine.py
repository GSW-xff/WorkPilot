from __future__ import annotations

from workpilot.models import TaskStatus

TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {
        TaskStatus.PLAN_READY,
        TaskStatus.NEEDS_CLARIFICATION,
        TaskStatus.REJECTED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.NEEDS_CLARIFICATION: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.REJECTED: set(),
    TaskStatus.PLAN_READY: {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.REPLANNING,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.SUCCEEDED,
    },
    TaskStatus.WAITING_APPROVAL: {
        TaskStatus.RUNNING,
        TaskStatus.REPLANNING,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REPLANNING: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PAUSED: {
        TaskStatus.PLAN_READY,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.CANCELLED,
    },
    TaskStatus.CANCELLED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.SUCCEEDED: set(),
}


def ensure_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise ValueError(f"illegal task transition: {current.value} -> {target.value}")
