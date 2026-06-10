from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.job import JobResponse


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


class ProjectBpInitializeRequest(CamelModel):
    project_name: str = Field(min_length=1, max_length=128)
    bp_file_path: str = Field(min_length=1)
    llm_service: str | None = Field(default=None, max_length=128)
    minimum_role_count: int = Field(default=14, ge=1, le=64)


class ProjectBpInitializeResponse(CamelModel):
    project_id: str
    project_name: str
    prompt_name: str
    job_count: int = Field(ge=0)
    jobs: list[JobResponse]
    industry_reading: str | None = None
    technical_assumptions: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
