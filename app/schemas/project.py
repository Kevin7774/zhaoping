from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class ProjectRequest(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="active", min_length=1, max_length=32)


class ProjectCreate(ProjectRequest):
    id: str = Field(min_length=1, max_length=64)


class ProjectResponse(CamelModel):
    id: str
    name: str
    status: str
    created_at: datetime
    open_jobs: int = Field(ge=0)
    total_candidates: int = Field(ge=0)
    awaiting_human: int = Field(ge=0)
    average_match_score: int = Field(ge=0, le=100)
