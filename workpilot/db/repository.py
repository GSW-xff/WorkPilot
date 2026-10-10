from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, delete, select, text, update
from sqlalchemy.orm import Session, selectinload, sessionmaker

from workpilot.db.models import (
    ActionLedgerRecord,
    ApprovalRecord,
    ArtifactRecord,
    Base,
    CheckpointRecord,
    OutboxEventRecord,
    TaskRunRecord,
    TaskStepRecord,
    TimelineEventRecord,
    VerificationRecord,
)
from workpilot.models import (
    ActionLedgerEntry,
    Approval,
    Artifact,
    Checkpoint,
    StepRun,
    TaskPlan,
    TaskRun,
    TimelineEvent,
    VerificationResult,
    utc_now,
)
from workpilot.repository import ConcurrentUpdateError, TaskNotFoundError, TaskRepository

LOAD_OPTIONS = (
    selectinload(TaskRunRecord.steps),
    selectinload(TaskRunRecord.approvals),
    selectinload(TaskRunRecord.ledger),
    selectinload(TaskRunRecord.verifications),
    selectinload(TaskRunRecord.artifacts),
    selectinload(TaskRunRecord.events),
    selectinload(TaskRunRecord.checkpoints),
)


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


class SQLAlchemyTaskRepository(TaskRepository):
    """Normalized, tenant-scoped repository with optimistic locking and an event outbox."""

    def __init__(self, engine: Engine, *, create_schema: bool = False) -> None:
        self.engine = engine
        if create_schema:
            Base.metadata.create_all(engine)
        self._session_factory = sessionmaker(engine, class_=Session, expire_on_commit=False)

    def add(self, task: TaskRun) -> TaskRun:
        with self._session_factory.begin() as session:
            self._set_tenant(session, task.tenant_id)
            if session.get(TaskRunRecord, task.id) is not None:
                raise ValueError(f"task already exists: {task.id}")
            record = self._new_task_record(task)
            session.add(record)
            self._replace_children(session, record, task)
            self._append_outbox(session, task, after_sequence=0)
        return self.get(task.tenant_id, task.id)

    def get(self, tenant_id: str, task_id: str) -> TaskRun:
        with self._session_factory() as session:
            self._set_tenant(session, tenant_id)
            statement = (
                select(TaskRunRecord)
                .where(
                    TaskRunRecord.id == task_id,
                    TaskRunRecord.tenant_id == tenant_id,
                )
                .options(*LOAD_OPTIONS)
            )
            record = session.scalar(statement)
            if record is None:
                raise TaskNotFoundError(task_id)
            return self._to_domain(record)

    def save(self, task: TaskRun, expected_version: int | None = None) -> TaskRun:
        expected = task.version if expected_version is None else expected_version
        next_version = expected + 1
        with self._session_factory.begin() as session:
            self._set_tenant(session, task.tenant_id)
            current = session.scalar(
                select(TaskRunRecord).where(
                    TaskRunRecord.id == task.id,
                    TaskRunRecord.tenant_id == task.tenant_id,
                )
            )
            if current is None:
                raise TaskNotFoundError(task.id)
            previous_event_count = (
                session.scalar(
                    select(TimelineEventRecord.sequence)
                    .where(TimelineEventRecord.task_id == task.id)
                    .order_by(TimelineEventRecord.sequence.desc())
                    .limit(1)
                )
                or 0
            )
            result = session.execute(
                update(TaskRunRecord)
                .where(
                    TaskRunRecord.id == task.id,
                    TaskRunRecord.tenant_id == task.tenant_id,
                    TaskRunRecord.version == expected,
                )
                .values(
                    user_id=task.user_id,
                    goal=task.goal,
                    status=task.status.value,
                    plan=task.plan.model_dump(mode="json") if task.plan else None,
                    paused_from=task.paused_from.value if task.paused_from else None,
                    updated_at=utc_now(),
                    version=next_version,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                raise ConcurrentUpdateError("task was updated concurrently")
            self._delete_children(session, task.id)
            self._replace_children(session, current, task)
            self._append_outbox(session, task, after_sequence=previous_event_count)
        return self.get(task.tenant_id, task.id)

    def list(self, tenant_id: str) -> list[TaskRun]:
        with self._session_factory() as session:
            self._set_tenant(session, tenant_id)
            statement = (
                select(TaskRunRecord)
                .where(TaskRunRecord.tenant_id == tenant_id)
                .options(*LOAD_OPTIONS)
                .order_by(TaskRunRecord.created_at.desc())
            )
            return [self._to_domain(record) for record in session.scalars(statement)]

    def close(self) -> None:
        self.engine.dispose()

    def pending_outbox(self, tenant_id: str, limit: int = 100) -> Sequence[dict[str, object]]:
        with self._session_factory() as session:
            self._set_tenant(session, tenant_id)
            statement = (
                select(OutboxEventRecord)
                .where(
                    OutboxEventRecord.tenant_id == tenant_id,
                    OutboxEventRecord.published_at.is_(None),
                )
                .order_by(OutboxEventRecord.id)
                .limit(limit)
            )
            return [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "sequence": row.sequence,
                    "event_type": row.event_type,
                    "payload": row.payload,
                }
                for row in session.scalars(statement)
            ]

    def mark_outbox_published(self, tenant_id: str, event_ids: Iterable[int]) -> int:
        ids = list(event_ids)
        if not ids:
            return 0
        with self._session_factory.begin() as session:
            self._set_tenant(session, tenant_id)
            result = session.execute(
                update(OutboxEventRecord)
                .where(
                    OutboxEventRecord.tenant_id == tenant_id,
                    OutboxEventRecord.id.in_(ids),
                )
                .values(published_at=datetime.now(UTC))
            )
            return int(getattr(result, "rowcount", 0) or 0)

    def _set_tenant(self, session: Session, tenant_id: str) -> None:
        if self.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": tenant_id},
            )

    @staticmethod
    def _new_task_record(task: TaskRun) -> TaskRunRecord:
        return TaskRunRecord(
            id=task.id,
            tenant_id=task.tenant_id,
            user_id=task.user_id,
            goal=task.goal,
            status=task.status.value,
            plan=task.plan.model_dump(mode="json") if task.plan else None,
            paused_from=task.paused_from.value if task.paused_from else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
            version=task.version,
        )

    @staticmethod
    def _delete_children(session: Session, task_id: str) -> None:
        for model in (
            TaskStepRecord,
            ApprovalRecord,
            ActionLedgerRecord,
            VerificationRecord,
            ArtifactRecord,
            TimelineEventRecord,
            CheckpointRecord,
        ):
            session.execute(delete(model).where(model.task_id == task_id))

    @staticmethod
    def _replace_children(session: Session, record: TaskRunRecord, task: TaskRun) -> None:
        session.add_all(
            TaskStepRecord(
                task_id=task.id,
                step_id=step_id,
                position=position,
                step=run.step.model_dump(mode="json"),
                status=run.status.value,
                result=run.result,
                error=run.error,
                started_at=run.started_at,
                completed_at=run.completed_at,
            )
            for position, (step_id, run) in enumerate(task.steps.items())
        )
        session.add_all(
            ApprovalRecord(
                id=item.id,
                task_id=task.id,
                tenant_id=item.tenant_id,
                step_id=item.step_id,
                action_type=item.action_type,
                parameter_preview=item.parameter_preview,
                parameter_hash=item.parameter_hash,
                plan_version=item.plan_version,
                status=item.status.value,
                requested_at=item.requested_at,
                decided_at=item.decided_at,
                decided_by=item.decided_by,
                reason=item.reason,
            )
            for item in task.approvals
        )
        session.add_all(
            ActionLedgerRecord(
                idempotency_key=item.idempotency_key,
                task_id=task.id,
                tenant_id=task.tenant_id,
                step_id=item.step_id,
                action=item.action,
                channel=item.channel.value,
                parameter_hash=item.parameter_hash,
                remote_id=item.remote_id,
                status=item.status,
                result=item.result,
                attempt=item.attempt,
                last_error=item.last_error,
                next_retry_at=item.next_retry_at,
                reconciliation_status=item.reconciliation_status,
                last_attempt_at=item.last_attempt_at,
                created_at=item.created_at,
            )
            for item in task.ledger
        )
        session.add_all(
            VerificationRecord(
                task_id=task.id,
                step_id=step_id,
                payload=item.model_dump(mode="json"),
            )
            for step_id, item in task.verifications.items()
        )
        session.add_all(
            ArtifactRecord(
                id=item.id,
                task_id=task.id,
                tenant_id=item.tenant_id,
                step_id=item.step_id,
                type=item.type,
                content=item.content,
                created_at=item.created_at,
            )
            for item in task.artifacts
        )
        session.add_all(
            TimelineEventRecord(
                task_id=task.id,
                sequence=item.sequence,
                type=item.type,
                message=item.message,
                task_status=item.task_status.value,
                step_id=item.step_id,
                details=item.details,
                created_at=item.created_at,
            )
            for item in task.events
        )
        session.add_all(
            CheckpointRecord(
                task_id=task.id,
                sequence=item.sequence,
                task_status=item.task_status.value,
                plan_version=item.plan_version,
                completed_steps=item.completed_steps,
                ledger_keys=item.ledger_keys,
                created_at=item.created_at,
            )
            for item in task.checkpoints
        )
        session.flush()

    @staticmethod
    def _append_outbox(session: Session, task: TaskRun, after_sequence: int) -> None:
        session.add_all(
            OutboxEventRecord(
                tenant_id=task.tenant_id,
                task_id=task.id,
                sequence=event.sequence,
                event_type=event.type,
                payload=event.model_dump(mode="json"),
                created_at=event.created_at,
            )
            for event in task.events
            if event.sequence > after_sequence
        )

    @staticmethod
    def _to_domain(record: TaskRunRecord) -> TaskRun:
        return TaskRun(
            id=record.id,
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            goal=record.goal,
            status=record.status,
            plan=TaskPlan.model_validate(record.plan) if record.plan else None,
            steps={
                item.step_id: StepRun(
                    step=item.step,
                    status=item.status,
                    result=item.result,
                    error=item.error,
                    started_at=item.started_at,
                    completed_at=item.completed_at,
                )
                for item in sorted(record.steps, key=lambda row: row.position)
            },
            approvals=[
                Approval.model_validate(
                    {
                        "id": item.id,
                        "tenant_id": item.tenant_id,
                        "task_id": item.task_id,
                        "step_id": item.step_id,
                        "action_type": item.action_type,
                        "parameter_preview": item.parameter_preview,
                        "parameter_hash": item.parameter_hash,
                        "plan_version": item.plan_version,
                        "status": item.status,
                        "requested_at": item.requested_at,
                        "decided_at": item.decided_at,
                        "decided_by": item.decided_by,
                        "reason": item.reason,
                    }
                )
                for item in sorted(record.approvals, key=lambda row: row.requested_at)
            ],
            ledger=[
                ActionLedgerEntry.model_validate(
                    {
                        "idempotency_key": item.idempotency_key,
                        "step_id": item.step_id,
                        "action": item.action,
                        "channel": item.channel,
                        "parameter_hash": item.parameter_hash,
                        "remote_id": item.remote_id,
                        "status": item.status,
                        "result": item.result,
                        "attempt": item.attempt,
                        "last_error": item.last_error,
                        "next_retry_at": item.next_retry_at,
                        "reconciliation_status": item.reconciliation_status,
                        "last_attempt_at": item.last_attempt_at,
                        "created_at": item.created_at,
                    }
                )
                for item in sorted(record.ledger, key=lambda row: row.created_at)
            ],
            verifications={
                item.step_id: VerificationResult.model_validate(item.payload)
                for item in record.verifications
            },
            artifacts=[
                Artifact.model_validate(
                    {
                        "id": item.id,
                        "tenant_id": item.tenant_id,
                        "task_id": item.task_id,
                        "step_id": item.step_id,
                        "type": item.type,
                        "content": item.content,
                        "created_at": item.created_at,
                    }
                )
                for item in sorted(record.artifacts, key=lambda row: row.created_at)
            ],
            events=[
                TimelineEvent.model_validate(
                    {
                        "sequence": item.sequence,
                        "type": item.type,
                        "message": item.message,
                        "task_status": item.task_status,
                        "step_id": item.step_id,
                        "details": item.details,
                        "created_at": item.created_at,
                    }
                )
                for item in sorted(record.events, key=lambda row: row.sequence)
            ],
            checkpoints=[
                Checkpoint.model_validate(
                    {
                        "sequence": item.sequence,
                        "task_status": item.task_status,
                        "plan_version": item.plan_version,
                        "completed_steps": item.completed_steps,
                        "ledger_keys": item.ledger_keys,
                        "created_at": item.created_at,
                    }
                )
                for item in sorted(record.checkpoints, key=lambda row: row.sequence)
            ],
            paused_from=record.paused_from,
            created_at=record.created_at,
            updated_at=record.updated_at,
            version=record.version,
        )
