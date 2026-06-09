from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.schemas.tasks import AGENT_EVENT_TYPES, TASK_STATUSES


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class TaskBase(DeclarativeBase):
    pass


class TaskModel(TaskBase):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    team_constraint: Mapped[str] = mapped_column(String(256), nullable=False, default="真机泛化")
    aperture_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    frontend_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    current_agent: Mapped[str | None] = mapped_column(String(64))
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    awaiting: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    steps_done: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    human_decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({_quoted(TASK_STATUSES)})", name="ck_tasks_status"),
    )


class AgentEventModel(TaskBase):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64))
    step_index: Mapped[int | None] = mapped_column(Integer)
    step_label: Mapped[str | None] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"type IN ({_quoted(AGENT_EVENT_TYPES)})", name="ck_agent_events_type"),
        Index("ix_agent_events_task_id_id", "task_id", "id"),
    )


def task_database_url() -> str:
    return os.environ.get("TASK_DATABASE_URL", "sqlite:///data/tasks.sqlite3")


def make_task_engine(database_url: str | None = None):
    url = database_url or task_database_url()
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, future=True, connect_args={"check_same_thread": False})
    return create_engine(url, future=True, pool_pre_ping=True)


def make_task_session_factory(database_url: str | None = None):
    engine = make_task_engine(database_url)
    TaskBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
