from __future__ import annotations

import hashlib
import time
from datetime import timedelta
from uuid import uuid4

from workpilot.connectors.base import CapabilityRegistry, ConnectorError
from workpilot.dag import topological_order, validate_plan
from workpilot.models import (
    ActionLedgerEntry,
    ActionRequest,
    Approval,
    ApprovalStatus,
    Artifact,
    Checkpoint,
    PlanningDisposition,
    StepRun,
    StepStatus,
    TaskRun,
    TaskStatus,
    TimelineEvent,
    VerificationStatus,
    utc_now,
)
from workpilot.planner import (
    DemoPlanner,
    PlanningDecisionError,
    PlanningOutcome,
    StructuredPlanner,
    diff_plans,
)
from workpilot.policy import PolicyEngine
from workpilot.repository import TaskRepository
from workpilot.security import idempotency_key, parameter_hash, redact
from workpilot.state_machine import ensure_transition
from workpilot.telemetry import TELEMETRY

TERMINAL_STATUSES = {
    TaskStatus.CANCELLED,
    TaskStatus.FAILED,
    TaskStatus.REJECTED,
    TaskStatus.SUCCEEDED,
}


class WorkPilotService:
    def __init__(
        self,
        repository: TaskRepository,
        registry: CapabilityRegistry,
        planner: DemoPlanner | StructuredPlanner | None = None,
        policy: PolicyEngine | None = None,
        max_steps: int = 20,
        allowed_recipient_domains: set[str] | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.planner = planner or DemoPlanner()
        self.policy = policy or PolicyEngine()
        self.max_steps = max_steps
        self.allowed_recipient_domains = allowed_recipient_domains or {"example.com"}

    def create_task(
        self,
        tenant_id: str,
        user_id: str,
        goal: str,
        recipient: str = "team@example.com",
    ) -> TaskRun:
        if isinstance(self.planner, StructuredPlanner):
            raise RuntimeError("structured planner requires create_task_async")
        task = self._new_task(tenant_id, user_id, goal)
        try:
            plan = self.planner.plan(goal, recipient)
            validate_plan(plan, self.registry.names, self.registry.risks, self.max_steps)
            self._validate_recipient_domains(plan)
        except PlanningDecisionError as exc:
            return self._store_planning_decision(task, exc)
        except Exception as exc:
            return self._store_planning_failure(task, exc)
        return self._store_plan(task, plan)

    async def create_task_async(
        self,
        tenant_id: str,
        user_id: str,
        goal: str,
        recipient: str = "team@example.com",
    ) -> TaskRun:
        if not isinstance(self.planner, StructuredPlanner):
            return self.create_task(tenant_id, user_id, goal, recipient)
        task = self._new_task(tenant_id, user_id, goal)
        trace_id = uuid4().hex
        try:
            outcome = await self._structured_plan(task, recipient, trace_id)
        except PlanningDecisionError as exc:
            return self._store_planning_decision(task, exc)
        except Exception as exc:
            return self._store_planning_failure(task, exc)

        self._attach_planning_evidence(task, outcome, trace_id)
        return self._store_plan(task, outcome.plan)

    async def _structured_plan(
        self, task: TaskRun, recipient: str, trace_id: str
    ) -> PlanningOutcome:
        assert isinstance(self.planner, StructuredPlanner)
        outcome = await self.planner.plan(
            task.goal,
            recipient,
            metadata={
                "trace_id": trace_id,
                "tenant_id": task.tenant_id,
                "task_id": task.id,
            },
        )
        self._validate_recipient_domains(outcome.plan)
        return outcome

    def _attach_planning_evidence(
        self, task: TaskRun, outcome: PlanningOutcome, trace_id: str
    ) -> None:
        snapshot_id = f"context-{uuid4().hex[:12]}"
        snapshot = outcome.context_snapshot
        safe_messages = [
            {
                "source": item["source"],
                "trust": item["trust"],
                "content_length": len(item["content"]),
                "content_sha256": hashlib.sha256(item["content"].encode()).hexdigest(),
            }
            for item in snapshot["messages"]
        ]
        task.artifacts.append(
            Artifact(
                id=snapshot_id,
                tenant_id=task.tenant_id,
                task_id=task.id,
                type="context_snapshot",
                content={
                    "messages": safe_messages,
                    "included_sources": snapshot["included_sources"],
                    "omitted_sources": snapshot["omitted_sources"],
                    "injection_markers": snapshot["injection_markers"],
                    "estimated_tokens": snapshot["estimated_tokens"],
                    "trace_id": trace_id,
                    "sensitive_content_recorded": False,
                },
            )
        )
        assert outcome.plan.planning is not None
        outcome.plan.planning.context_snapshot_id = snapshot_id
        self._event(
            task,
            "planner.completed",
            "结构化计划已生成" if not outcome.used_fallback else "模型规划失败，已安全回退",
            details={
                "trace_id": trace_id,
                "used_fallback": outcome.used_fallback,
                "model_calls": len(outcome.model_calls),
                "validation_error_count": len(outcome.validation_errors),
                "context_snapshot_id": snapshot_id,
            },
        )

    async def clarify_task(
        self,
        tenant_id: str,
        task_id: str,
        user_id: str,
        goal: str,
        recipient: str = "team@example.com",
    ) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        expected_version = task.version
        if task.user_id != user_id:
            raise PermissionError("only the task owner can clarify the request")
        if task.status is not TaskStatus.NEEDS_CLARIFICATION:
            raise ValueError("task is not waiting for clarification")

        task.goal = goal
        task.planning_disposition = None
        task.planning_reason = None
        task.clarification_questions = []
        self._transition(
            task,
            TaskStatus.PLANNING,
            "planner.restarted",
            "已收到补充信息，重新规划",
        )
        try:
            if isinstance(self.planner, StructuredPlanner):
                trace_id = uuid4().hex
                outcome = await self._structured_plan(task, recipient, trace_id)
                self._attach_planning_evidence(task, outcome, trace_id)
                plan = outcome.plan
            else:
                plan = self.planner.plan(goal, recipient)
                validate_plan(plan, self.registry.names, self.registry.risks, self.max_steps)
                self._validate_recipient_domains(plan)
        except PlanningDecisionError as exc:
            self._apply_planning_decision(task, exc)
            return self.repository.save(task, expected_version=expected_version)
        except Exception as exc:
            self._apply_planning_failure(task, exc)
            return self.repository.save(task, expected_version=expected_version)

        self._apply_plan(task, plan)
        return self.repository.save(task, expected_version=expected_version)

    async def run(self, tenant_id: str, task_id: str) -> TaskRun:
        started = time.perf_counter()
        try:
            result = await self._run(tenant_id, task_id)
        except Exception as exc:
            duration = time.perf_counter() - started
            TELEMETRY.metrics.counter("task_error_total", error_type=type(exc).__name__)
            TELEMETRY.metrics.observe("task_duration_seconds", duration, status="error")
            TELEMETRY.record_span(
                "task.run",
                duration * 1_000,
                {"task.id": task_id, "workpilot.tenant.id": tenant_id},
                error_type=type(exc).__name__,
            )
            raise
        duration = time.perf_counter() - started
        TELEMETRY.metrics.observe(
            "task_duration_seconds", duration, status=result.status.value.lower()
        )
        if result.status in TERMINAL_STATUSES:
            if result.status is TaskStatus.SUCCEEDED:
                TELEMETRY.metrics.counter("task_success_total")
            else:
                TELEMETRY.metrics.counter(
                    "task_terminal_failure_total", status=result.status.value.lower()
                )
        TELEMETRY.record_span(
            "task.run",
            duration * 1_000,
            {"task.id": task_id, "workpilot.tenant.id": tenant_id},
        )
        return result

    def replan(self, tenant_id: str, task_id: str, candidate) -> tuple[TaskRun, dict]:
        task = self.repository.get(tenant_id, task_id)
        if task.plan is None:
            raise ValueError("task has no existing plan")
        validate_plan(candidate, self.registry.names, self.registry.risks, self.max_steps)
        self._validate_recipient_domains(candidate)
        candidate.version = task.plan.version + 1
        completed = {
            step_id for step_id, run in task.steps.items() if run.status is StepStatus.SUCCEEDED
        }
        plan_diff = diff_plans(task.plan, candidate, completed)
        previous_runs = task.steps
        task.plan = candidate
        task.steps = {
            step.id: previous_runs.get(step.id, StepRun(step=step)).model_copy(
                update={"step": step}
            )
            for step in candidate.steps
        }
        self._event(task, "plan.replanned", "执行计划已更新", details=plan_diff)
        self._checkpoint(task)
        return self.repository.save(task, expected_version=task.version), plan_diff

    def _new_task(self, tenant_id: str, user_id: str, goal: str) -> TaskRun:
        task = TaskRun(
            id=f"taskrun-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            goal=goal,
        )
        self._event(task, "task.created", "任务已创建")
        self._transition(task, TaskStatus.PLANNING, "planner.started", "开始生成执行计划")
        return task

    def _store_planning_failure(self, task: TaskRun, exc: Exception) -> TaskRun:
        self._apply_planning_failure(task, exc)
        return self.repository.add(task)

    def _apply_planning_failure(self, task: TaskRun, exc: Exception) -> None:
        self._transition(task, TaskStatus.FAILED, "plan.failed", str(exc))

    def _store_planning_decision(
        self, task: TaskRun, exc: PlanningDecisionError
    ) -> TaskRun:
        self._apply_planning_decision(task, exc)
        return self.repository.add(task)

    def _apply_planning_decision(self, task: TaskRun, exc: PlanningDecisionError) -> None:
        decision = exc.decision
        task.planning_disposition = decision.disposition
        task.planning_reason = decision.reason
        task.clarification_questions = list(decision.questions)
        if decision.disposition is PlanningDisposition.NEEDS_CLARIFICATION:
            self._transition(
                task,
                TaskStatus.NEEDS_CLARIFICATION,
                "plan.clarification_required",
                decision.reason,
                details={"questions": list(decision.questions)},
            )
            TELEMETRY.metrics.counter("planning_disposition_total", disposition="clarification")
        else:
            self._transition(task, TaskStatus.REJECTED, "plan.rejected", decision.reason)
            TELEMETRY.metrics.counter("planning_disposition_total", disposition="rejected")
        self._checkpoint(task)

    def _store_plan(self, task: TaskRun, plan) -> TaskRun:
        self._apply_plan(task, plan)
        return self.repository.add(task)

    def _apply_plan(self, task: TaskRun, plan) -> None:
        task.plan = plan
        task.planning_disposition = PlanningDisposition.EXECUTABLE
        task.planning_reason = "请求已通过支持域、计划和安全校验"
        task.clarification_questions = []
        task.steps = {step.id: StepRun(step=step) for step in plan.steps}
        self._transition(task, TaskStatus.PLAN_READY, "plan.ready", "执行计划已通过确定性校验")
        self._checkpoint(task)

    async def _run(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        if task.status is TaskStatus.PLAN_READY:
            self._transition(task, TaskStatus.RUNNING, "task.running", "任务开始执行")
        elif task.status is not TaskStatus.RUNNING:
            raise ValueError(f"task cannot run from {task.status.value}")
        assert task.plan is not None

        for step_id in topological_order(task.plan.steps):
            step_run = task.steps[step_id]
            if step_run.status is StepStatus.SUCCEEDED:
                continue
            if any(
                task.steps[item].status is not StepStatus.SUCCEEDED
                for item in step_run.step.depends_on
            ):
                continue

            step = step_run.step
            channel = self.registry.channel_for(step.capability, step.preferred_channel)
            with TELEMETRY.span(
                "policy.evaluate",
                {
                    "task.id": task_id,
                    "step.id": step.id,
                    "tool.name": step.capability,
                },
            ):
                decision = self.policy.evaluate(step, self.registry.risks[step.capability], channel)
            if not decision.allowed:
                TELEMETRY.metrics.counter(
                    "policy_denied_total", capability=step.capability, risk=step.risk.value
                )
                step_run.status = StepStatus.FAILED
                step_run.error = decision.reason
                self._transition(task, TaskStatus.FAILED, "policy.denied", decision.reason, step_id)
                self._checkpoint(task)
                return self.repository.save(task, expected_version=task.version)

            action = ActionRequest(
                tenant_id=tenant_id,
                task_id=task.id,
                step_id=step.id,
                capability=step.capability,
                parameters=step.parameters,
                channel=channel,
                deadline_at=utc_now() + timedelta(seconds=60),
            )
            params_hash = parameter_hash(action.parameters)
            adapter = self.registry.adapter_for(step.capability)
            if decision.requires_approval and not self._has_valid_approval(
                task, step.id, params_hash
            ):
                preview = await adapter.preview(action)
                self._ensure_pending_approval(task, action, preview.human_summary, params_hash)
                step_run.status = StepStatus.WAITING_APPROVAL
                self._transition(
                    task,
                    TaskStatus.WAITING_APPROVAL,
                    "approval.requested",
                    preview.human_summary,
                    step.id,
                    {"parameter_hash": params_hash, "parameters": redact(action.parameters)},
                )
                self._checkpoint(task)
                return self.repository.save(task, expected_version=task.version)

            step_run.status = StepStatus.RUNNING
            step_run.started_at = utc_now()
            self._event(task, "step.started", step.description, step.id)
            key = idempotency_key(tenant_id, task.id, step.id, step.capability, action.parameters)
            existing = next((item for item in task.ledger if item.idempotency_key == key), None)
            if existing is not None and existing.status in {"CONFIRMED", "EXECUTED"}:
                result = self._result_from_ledger(existing)
            else:
                if existing is None:
                    existing = ActionLedgerEntry(
                        idempotency_key=key,
                        step_id=step.id,
                        action=step.capability,
                        channel=channel,
                        parameter_hash=params_hash,
                        status="RESERVED",
                    )
                    task.ledger.append(existing)
                    self._event(
                        task,
                        "action.reserved",
                        "动作已使用幂等键预占",
                        step.id,
                        {"idempotency_key": key},
                    )
                    task = self.repository.save(task, expected_version=task.version)
                    step_run = task.steps[step_id]
                    existing = next(item for item in task.ledger if item.idempotency_key == key)

                with TELEMETRY.span(
                    "tool.lookup",
                    {"task.id": task_id, "step.id": step.id, "tool.name": step.capability},
                ):
                    result = await adapter.lookup(action, key)
                if result is None:
                    existing.attempt += 1
                    existing.last_attempt_at = utc_now()
                    existing.last_error = None
                    existing.next_retry_at = None
                    try:
                        with TELEMETRY.span(
                            "tool.execute",
                            {
                                "task.id": task_id,
                                "step.id": step.id,
                                "tool.name": step.capability,
                                "workpilot.retry.count": existing.attempt - 1,
                            },
                        ):
                            result = await adapter.execute(action, key)
                        TELEMETRY.metrics.counter("tool_call_total", capability=step.capability)
                    except ConnectorError as exc:
                        TELEMETRY.metrics.counter(
                            "tool_error_total",
                            capability=step.capability,
                            error_type=type(exc).__name__,
                        )
                        existing.last_error = str(exc)
                        existing.next_retry_at = (
                            utc_now() + timedelta(seconds=min(2**existing.attempt, 60))
                            if exc.retryable
                            else None
                        )
                        if exc.outcome_unknown:
                            existing.status = "UNKNOWN"
                            existing.reconciliation_status = "REQUIRED"
                        else:
                            existing.status = "RETRYABLE" if exc.retryable else "FAILED"
                        self._event(
                            task,
                            "action.unknown" if exc.outcome_unknown else "action.failed",
                            "动作结果未知，重试前必须查询远端状态",
                            step.id,
                            {
                                "retryable": exc.retryable,
                                "attempt": existing.attempt,
                                "next_retry_at": existing.next_retry_at.isoformat()
                                if existing.next_retry_at
                                else None,
                            },
                        )
                        self.repository.save(task, expected_version=task.version)
                        raise
                    except Exception as exc:
                        TELEMETRY.metrics.counter(
                            "tool_error_total",
                            capability=step.capability,
                            error_type=type(exc).__name__,
                        )
                        existing.status = "UNKNOWN"
                        existing.last_error = str(exc)
                        existing.next_retry_at = utc_now() + timedelta(
                            seconds=min(2**existing.attempt, 60)
                        )
                        existing.reconciliation_status = "REQUIRED"
                        self._event(
                            task,
                            "action.unknown",
                            "动作结果未知，重试前必须查询远端状态",
                            step.id,
                            {"attempt": existing.attempt},
                        )
                        self.repository.save(task, expected_version=task.version)
                        raise
                existing.remote_id = result.remote_id
                existing.status = "DISPATCHED" if result.success else "FAILED"
                existing.result = redact(result.model_dump(mode="json"))
                if result.duplicate:
                    TELEMETRY.metrics.counter("tool_duplicate_total", capability=step.capability)

            artifact = Artifact(
                id=f"artifact-{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                task_id=task.id,
                step_id=step.id,
                type="tool_result",
                content=redact(result.model_dump(mode="json")),
            )
            task.artifacts.append(artifact)
            with TELEMETRY.span(
                "tool.verify",
                {"task.id": task_id, "step.id": step.id, "tool.name": step.capability},
            ):
                verification = await adapter.verify(action, result)
            verification.evidence_refs = list(
                dict.fromkeys([f"artifact://{artifact.id}", *verification.evidence_refs])
            )
            task.verifications[step.id] = verification
            if verification.status is not VerificationStatus.PASSED:
                step_run.status = StepStatus.FAILED
                step_run.error = verification.reason
                step_run.completed_at = utc_now()
                self._transition(
                    task,
                    TaskStatus.FAILED,
                    "step.verification_failed",
                    verification.reason,
                    step.id,
                )
                self._checkpoint(task)
                return self.repository.save(task, expected_version=task.version)

            step_run.status = StepStatus.SUCCEEDED
            step_run.result = result.model_dump(mode="json")
            step_run.completed_at = utc_now()
            existing.status = "CONFIRMED"
            existing.reconciliation_status = "CONFIRMED"
            existing.last_error = None
            existing.next_retry_at = None
            self._event(task, "step.succeeded", "远端状态已独立验证", step.id)
            self._checkpoint(task)
            task = self.repository.save(task, expected_version=task.version)

        if all(item.status is StepStatus.SUCCEEDED for item in task.steps.values()):
            self._transition(task, TaskStatus.SUCCEEDED, "task.succeeded", "所有目标均已验证通过")
            self._checkpoint(task)
        return self.repository.save(task, expected_version=task.version)

    def approve(
        self,
        tenant_id: str,
        task_id: str,
        step_id: str,
        supplied_hash: str,
        approver: str,
    ) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status is not TaskStatus.WAITING_APPROVAL:
            raise ValueError("task is not waiting for approval")
        approval = self._pending_approval(task, step_id)
        if approval.parameter_hash != supplied_hash:
            raise ValueError("approval parameter hash does not match the current preview")
        current_hash = parameter_hash(task.steps[step_id].step.parameters)
        if current_hash != approval.parameter_hash:
            approval.status = ApprovalStatus.EXPIRED
            raise ValueError("action parameters changed; a new approval is required")
        approval.status = ApprovalStatus.APPROVED
        approval.decided_at = utc_now()
        approval.decided_by = approver
        task.steps[step_id].status = StepStatus.PENDING
        self._transition(task, TaskStatus.RUNNING, "approval.approved", "审批已通过", step_id)
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def reject(
        self, tenant_id: str, task_id: str, step_id: str, approver: str, reason: str
    ) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        approval = self._pending_approval(task, step_id)
        approval.status = ApprovalStatus.REJECTED
        approval.decided_at = utc_now()
        approval.decided_by = approver
        approval.reason = reason
        task.steps[step_id].status = StepStatus.CANCELLED
        self._transition(task, TaskStatus.CANCELLED, "approval.rejected", reason, step_id)
        self._checkpoint(task)
        saved = self.repository.save(task, expected_version=version)
        TELEMETRY.metrics.counter("task_terminal_failure_total", status="cancelled")
        return saved

    def pause(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        pausable = {
            TaskStatus.PLAN_READY,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_APPROVAL,
        }
        if task.status not in pausable:
            raise ValueError(f"task cannot pause from {task.status.value}")
        task.paused_from = task.status
        self._transition(task, TaskStatus.PAUSED, "task.paused", "任务已安全暂停")
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def resume(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status is not TaskStatus.PAUSED or task.paused_from is None:
            raise ValueError("task is not paused")
        target = task.paused_from
        task.paused_from = None
        self._transition(task, target, "task.resumed", "任务已从最近检查点恢复")
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def cancel(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status in TERMINAL_STATUSES:
            raise ValueError(f"task is already terminal: {task.status.value}")
        for step in task.steps.values():
            if step.status in {StepStatus.PENDING, StepStatus.WAITING_APPROVAL}:
                step.status = StepStatus.CANCELLED
        self._transition(task, TaskStatus.CANCELLED, "task.cancelled", "任务已取消")
        self._checkpoint(task)
        saved = self.repository.save(task, expected_version=version)
        TELEMETRY.metrics.counter("task_terminal_failure_total", status="cancelled")
        return saved

    def recovery_cases(self, tenant_id: str) -> list[dict]:
        return [
            {
                "task_id": task.id,
                "task_status": task.status.value,
                "step_id": entry.step_id,
                "action": entry.action,
                "status": entry.status,
                "attempt": entry.attempt,
                "last_error": entry.last_error,
                "next_retry_at": entry.next_retry_at,
                "reconciliation_status": entry.reconciliation_status,
            }
            for task in self.repository.list(tenant_id)
            for entry in task.ledger
            if entry.status in {"UNKNOWN", "RETRYABLE"} or entry.reconciliation_status == "REQUIRED"
        ]

    def _validate_recipient_domains(self, plan) -> None:
        for step in plan.steps:
            if step.capability != "mail.send":
                continue
            recipients = step.parameters.get("to", [])
            invalid = [
                item
                for item in recipients
                if not isinstance(item, str)
                or "@" not in item
                or item.rsplit("@", 1)[1].lower() not in self.allowed_recipient_domains
            ]
            if invalid:
                raise ValueError("mail recipients must belong to an allowed tenant domain")

    def _transition(
        self,
        task: TaskRun,
        status: TaskStatus,
        event_type: str,
        message: str,
        step_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        ensure_transition(task.status, status)
        task.status = status
        self._event(task, event_type, message, step_id, details)

    @staticmethod
    def _event(
        task: TaskRun,
        event_type: str,
        message: str,
        step_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        task.events.append(
            TimelineEvent(
                sequence=len(task.events) + 1,
                type=event_type,
                message=message,
                task_status=task.status,
                step_id=step_id,
                details=details or {},
            )
        )

    @staticmethod
    def _checkpoint(task: TaskRun) -> None:
        task.checkpoints.append(
            Checkpoint(
                sequence=len(task.checkpoints) + 1,
                task_status=task.status,
                plan_version=task.plan.version if task.plan else 0,
                completed_steps=[
                    step_id
                    for step_id, run in task.steps.items()
                    if run.status is StepStatus.SUCCEEDED
                ],
                ledger_keys=[item.idempotency_key for item in task.ledger],
            )
        )

    @staticmethod
    def _has_valid_approval(task: TaskRun, step_id: str, params_hash: str) -> bool:
        if task.plan is None:
            return False
        return any(
            item.step_id == step_id
            and item.parameter_hash == params_hash
            and item.plan_version == task.plan.version
            and item.status is ApprovalStatus.APPROVED
            for item in task.approvals
        )

    @staticmethod
    def _ensure_pending_approval(
        task: TaskRun,
        action: ActionRequest,
        summary: str,
        params_hash: str,
    ) -> Approval:
        if task.plan is None:
            raise ValueError("task has no validated plan")
        existing = next(
            (
                item
                for item in task.approvals
                if item.step_id == action.step_id
                and item.parameter_hash == params_hash
                and item.status is ApprovalStatus.PENDING
            ),
            None,
        )
        if existing:
            return existing
        approval = Approval(
            id=f"approval-{uuid4().hex[:12]}",
            tenant_id=task.tenant_id,
            task_id=task.id,
            step_id=action.step_id,
            action_type=action.capability,
            parameter_preview={"summary": summary, **redact(action.parameters)},
            parameter_hash=params_hash,
            plan_version=task.plan.version,
        )
        task.approvals.append(approval)
        return approval

    @staticmethod
    def _pending_approval(task: TaskRun, step_id: str) -> Approval:
        approval = next(
            (
                item
                for item in reversed(task.approvals)
                if item.step_id == step_id and item.status is ApprovalStatus.PENDING
            ),
            None,
        )
        if approval is None:
            raise ValueError(f"no pending approval for step: {step_id}")
        return approval

    @staticmethod
    def _result_from_ledger(entry: ActionLedgerEntry):
        from workpilot.models import ActionResult

        stored = dict(entry.result)
        stored["duplicate"] = True
        return ActionResult.model_validate(stored)
