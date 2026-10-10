from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
ACTIVITY_TIMEOUT = timedelta(seconds=60)
HEARTBEAT_TIMEOUT = timedelta(seconds=15)
APPROVAL_TIMEOUT = timedelta(days=7)
WORKFLOW_PATCH_ID = "workpilot-v3-heartbeat-recovery-v1"
ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


@dataclass(frozen=True)
class TaskRef:
    tenant_id: str
    task_id: str


@dataclass(frozen=True)
class ApprovalCommand:
    tenant_id: str
    task_id: str
    step_id: str
    parameter_hash: str
    approver: str
    approved: bool = True
    reason: str = ""


@workflow.defn(name="workpilot.task")
class TaskWorkflow:
    def __init__(self) -> None:
        self._ref: TaskRef | None = None
        self._status = "CREATED"

    @workflow.run
    async def run(self, task: TaskRef) -> str:
        self._ref = task
        self._status = "PLAN_READY"
        workflow.patched(WORKFLOW_PATCH_ID)
        while self._status not in TERMINAL:
            if self._status in {"WAITING_APPROVAL", "PAUSED"}:
                previous = self._status
                try:
                    await self._wait_until_status_changes(previous)
                except TimeoutError:
                    if previous == "WAITING_APPROVAL":
                        self._status = await workflow.execute_activity(
                            "cancel_task",
                            task,
                            start_to_close_timeout=ACTIVITY_TIMEOUT,
                            heartbeat_timeout=HEARTBEAT_TIMEOUT,
                            retry_policy=ACTIVITY_RETRY,
                            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                        )
                continue
            self._status = await workflow.execute_activity(
                "advance_task",
                task,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                heartbeat_timeout=HEARTBEAT_TIMEOUT,
                retry_policy=ACTIVITY_RETRY,
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
        return self._status

    async def _wait_until_status_changes(self, previous: str) -> None:
        timeout = APPROVAL_TIMEOUT if previous == "WAITING_APPROVAL" else None
        await workflow.wait_condition(lambda: self._status != previous, timeout=timeout)

    @workflow.update
    async def decide_approval(self, command: ApprovalCommand) -> str:
        if (
            self._ref is None
            or command.tenant_id != self._ref.tenant_id
            or command.task_id != self._ref.task_id
        ):
            raise ApplicationError("approval targets a different task", non_retryable=True)
        if self._status != "WAITING_APPROVAL":
            raise ApplicationError("task is not waiting for approval", non_retryable=True)
        activity_name = "approve_task" if command.approved else "reject_task"
        self._status = await workflow.execute_activity(
            activity_name,
            command,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )
        return self._status

    @workflow.signal
    async def pause(self) -> None:
        if self._ref is None or self._status in TERMINAL or self._status == "PAUSED":
            return
        self._status = await workflow.execute_activity(
            "pause_task",
            self._ref,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    @workflow.signal
    async def resume(self) -> None:
        if self._ref is None or self._status != "PAUSED":
            return
        self._status = await workflow.execute_activity(
            "resume_task",
            self._ref,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    @workflow.signal
    async def cancel(self) -> None:
        if self._ref is None or self._status in TERMINAL:
            return
        self._status = await workflow.execute_activity(
            "cancel_task",
            self._ref,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )

    @workflow.query
    def status(self) -> str:
        return self._status
