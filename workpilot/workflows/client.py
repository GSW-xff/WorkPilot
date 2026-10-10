from __future__ import annotations

from temporalio.client import Client, WorkflowHandle
from temporalio.exceptions import WorkflowAlreadyStartedError

from workpilot.workflows.temporal import ApprovalCommand, TaskRef, TaskWorkflow


class TemporalTaskClient:
    def __init__(self, client: Client, task_queue: str) -> None:
        self.client = client
        self.task_queue = task_queue

    @classmethod
    async def connect(cls, target: str, task_queue: str) -> TemporalTaskClient:
        return cls(await Client.connect(target), task_queue)

    @staticmethod
    def workflow_id(tenant_id: str, task_id: str) -> str:
        return f"workpilot-task-{tenant_id}-{task_id}"

    async def start(self, tenant_id: str, task_id: str) -> None:
        try:
            await self.client.start_workflow(
                TaskWorkflow.run,
                TaskRef(tenant_id=tenant_id, task_id=task_id),
                id=self.workflow_id(tenant_id, task_id),
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            return

    def handle(self, tenant_id: str, task_id: str) -> WorkflowHandle:
        return self.client.get_workflow_handle(self.workflow_id(tenant_id, task_id))

    async def approve(self, command: ApprovalCommand) -> None:
        await self.handle(command.tenant_id, command.task_id).execute_update(
            TaskWorkflow.decide_approval,
            command,
        )

    async def signal(self, tenant_id: str, task_id: str, signal: str) -> None:
        handle = self.handle(tenant_id, task_id)
        if signal == "pause":
            await handle.signal(TaskWorkflow.pause)
        elif signal == "resume":
            await handle.signal(TaskWorkflow.resume)
        elif signal == "cancel":
            await handle.signal(TaskWorkflow.cancel)
        else:
            raise ValueError(f"unknown workflow signal: {signal}")
