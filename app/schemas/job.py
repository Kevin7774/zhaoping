from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class JobRequest(CamelModel):
    title: str = Field(min_length=1, max_length=128)
    headcount: int = Field(default=1, ge=0)
    status: str = Field(default="sourcing", min_length=1, max_length=32)


class JobCreate(JobRequest):
    id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)


class JobResponse(CamelModel):
    id: str
    project_id: str
    title: str
    headcount: int = Field(ge=0)
    status: str
    pipeline_status: str
    candidate_count: int = Field(ge=0)
    average_match_score: int = Field(ge=0, le=100)
