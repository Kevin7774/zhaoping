from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class CandidateSearchScheduleRequest(CamelModel):
    enabled: bool = True
    interval_minutes: int = Field(default=360, ge=15, le=10080)


class CandidateSearchScheduleResponse(CamelModel):
    id: int
    project_id: str
    job_id: str
    job_title: str
    enabled: bool
    interval_minutes: int
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_task_id: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class CandidateSearchScheduleListResponse(CamelModel):
    items: list[CandidateSearchScheduleResponse]
