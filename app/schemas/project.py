from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.job import JobResponse

ProjectGenerationMode = Literal["bp_file", "prompt", "bp_plus_prompt"]


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
    generation_mode: ProjectGenerationMode = "bp_file"
    bp_file_path: str | None = Field(default=None, min_length=1, max_length=512)
    project_prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    industry_research_prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    llm_service: str | None = Field(default=None, max_length=128)
    minimum_role_count: int = Field(default=14, ge=1, le=64)


class ProjectResearchTraceItem(CamelModel):
    stage: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risk: str | None = Field(default=None, max_length=2000)


class ProjectRoleRejection(CamelModel):
    title: str = Field(min_length=1, max_length=128)
    reasons: list[str] = Field(default_factory=list)


class ProjectBpInitializeResponse(CamelModel):
    project_id: str
    project_name: str
    prompt_name: str
    generation_mode: ProjectGenerationMode = "bp_file"
    job_count: int = Field(ge=0)
    jobs: list[JobResponse]
    industry_reading: str | None = None
    technical_assumptions: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    research_trace: list[ProjectResearchTraceItem] = Field(default_factory=list)
    # Five-stage pipeline outputs (auditable chain commitments -> capabilities -> gaps -> roles).
    claims: dict[str, Any] | None = None
    capability_graph: dict[str, Any] | None = None
    gap_analysis: dict[str, Any] | None = None
    rejected_roles: list[ProjectRoleRejection] = Field(default_factory=list)
    generation_degraded: bool = False
