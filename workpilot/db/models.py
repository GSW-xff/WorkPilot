from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskRunRecord(Base):
    __tablename__ = "task_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_task_runs_tenant_id_id"),
        Index("ix_task_runs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    paused_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    steps: Mapped[list[TaskStepRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    approvals: Mapped[list[ApprovalRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    ledger: Mapped[list[ActionLedgerRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    verifications: Mapped[list[VerificationRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    artifacts: Mapped[list[ArtifactRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    events: Mapped[list[TimelineEventRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )
    checkpoints: Mapped[list[CheckpointRecord]] = relationship(
        cascade="all, delete-orphan", back_populates="task"
    )


class TaskStepRecord(Base):
    __tablename__ = "task_steps"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), primary_key=True
    )
    step_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[TaskRunRecord] = relationship(back_populates="steps")


class ApprovalRecord(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_task_step", "task_id", "step_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    parameter_preview: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)

    task: Mapped[TaskRunRecord] = relationship(back_populates="approvals")


class ActionLedgerRecord(Base):
    __tablename__ = "action_ledger"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped[TaskRunRecord] = relationship(back_populates="ledger")


class VerificationRecord(Base):
    __tablename__ = "verifications"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), primary_key=True
    )
    step_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    task: Mapped[TaskRunRecord] = relationship(back_populates="verifications")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_id: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped[TaskRunRecord] = relationship(back_populates="artifacts")


class TimelineEventRecord(Base):
    __tablename__ = "timeline_events"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped[TaskRunRecord] = relationship(back_populates="events")


class CheckpointRecord(Base):
    __tablename__ = "checkpoints"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ledger_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped[TaskRunRecord] = relationship(back_populates="checkpoints")


class OutboxEventRecord(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_outbox_task_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
