from __future__ import annotations

from temporalio import activity

from workpilot.runtime import WorkPilotService
from workpilot.workflows.temporal import ApprovalCommand, TaskRef


class TaskActivities:
    def __init__(self, service: WorkPilotService) -> None:
        self.service = service

    @activity.defn(name="advance_task")
    async def advance_task(self, task: TaskRef) -> str:
        _heartbeat("advance.started", task)
        result = await self.service.run(task.tenant_id, task.task_id)
        _heartbeat("advance.persisted", task, result.status.value)
        return result.status.value

    @activity.defn(name="approve_task")
    async def approve_task(self, command: ApprovalCommand) -> str:
        _heartbeat("approval.started", TaskRef(command.tenant_id, command.task_id))
        result = self.service.approve(
            command.tenant_id,
            command.task_id,
            command.step_id,
            command.parameter_hash,
            command.approver,
        )
        _heartbeat("approval.persisted", TaskRef(command.tenant_id, command.task_id))
        return result.status.value

    @activity.defn(name="reject_task")
    async def reject_task(self, command: ApprovalCommand) -> str:
        result = self.service.reject(
            command.tenant_id,
            command.task_id,
            command.step_id,
            command.approver,
            command.reason or "approval rejected",
        )
        return result.status.value

    @activity.defn(name="pause_task")
    async def pause_task(self, task: TaskRef) -> str:
        return self.service.pause(task.tenant_id, task.task_id).status.value

    @activity.defn(name="resume_task")
    async def resume_task(self, task: TaskRef) -> str:
        return self.service.resume(task.tenant_id, task.task_id).status.value

    @activity.defn(name="cancel_task")
    async def cancel_task(self, task: TaskRef) -> str:
        return self.service.cancel(task.tenant_id, task.task_id).status.value


def _heartbeat(stage: str, task: TaskRef, status: str | None = None) -> None:
    if activity.in_activity():
        activity.heartbeat(
            {
                "stage": stage,
                "tenant_id": task.tenant_id,
                "task_id": task.task_id,
                "status": status,
            }
        )
