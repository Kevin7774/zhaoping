from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["processing", "awaiting_human", "done", "error", "cancelled"]
AgentEventType = Literal[
    "step_start",
    "tool_call",
    "evidence",
    "summary",
    "human_gate",
    "error",
    "cancelled",
]

TASK_STATUSES: tuple[str, ...] = (
    "processing",
    "awaiting_human",
    "done",
    "error",
    "cancelled",
)

AGENT_EVENT_TYPES: tuple[str, ...] = (
    "step_start",
    "tool_call",
    "evidence",
    "summary",
    "human_gate",
    "error",
    "cancelled",
)


class AgentEventCreate(BaseModel):
    type: AgentEventType
    agent_id: str | None = None
    step_index: int | None = None
    step_label: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus | None = None


class AgentEventRead(AgentEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    scenario_id: str
    status: TaskStatus
    team_constraint: str
    aperture_weight: float
    created_at: datetime
    updated_at: datetime
