from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowValidateRequest(BaseModel):
    workflow: dict[str, Any]


class WorkflowRunRequest(BaseModel):
    workflow: dict[str, Any]
    input: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None


class WorkflowValidateResponse(BaseModel):
    valid: bool
    workflow_id: str | None = None
    step_count: int = 0
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)


class WorkflowRunResponse(BaseModel):
    task_id: str
    workflow_id: str
    status: str
