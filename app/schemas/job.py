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


class JobRationale(CamelModel):
    why_needed: str | None = None
    bp_evidence: list[str] = Field(default_factory=list)
    business_commitments: list[str] = Field(default_factory=list)
    capability_gaps: list[str] = Field(default_factory=list)
    why_hire_not_vendor: str | None = None
    if_not_hired_risk: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    first_90_day_outcomes: list[str] = Field(default_factory=list)
    hiring_priority: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class JobResponse(CamelModel):
    id: str
    project_id: str
    title: str
    headcount: int = Field(ge=0)
    status: str
    pipeline_status: str
    candidate_count: int = Field(ge=0)
    average_match_score: int = Field(ge=0, le=100)
    seniority: str | None = None
    responsibilities: list[str] | None = None
    must_have_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    target_companies: list[str] | None = None
    exclusion_signals: list[str] | None = None
    interview_questions: list[str] | None = None
    scoring_rubric: dict[str, int | float | str] | None = None
    search_strategy: dict[str, str | list[str]] | None = None
    rationale: JobRationale | None = None
