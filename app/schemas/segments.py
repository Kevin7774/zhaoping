from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.candidate import CandidateResponse
from app.schemas.common import CamelModel


class SegmentCriteria(CamelModel):
    job_profile_id: str | None = None
    min_score: int = 0
    city: str | None = None
    keyword: str | None = None
    outreach_status: str | None = None
    has_email: str | None = None
    source_platform: str | None = None


class SegmentQueryRequest(CamelModel):
    project_id: str
    criteria: SegmentCriteria


class SegmentCreateRequest(CamelModel):
    project_id: str
    name: str
    criteria: SegmentCriteria
    candidate_ids: list[str] | None = None


class SegmentQueryResponse(CamelModel):
    project_id: str
    criteria: dict[str, Any]
    total: int
    candidates: list[CandidateResponse]


class SegmentResponse(CamelModel):
    segment_id: str
    project_id: str
    name: str
    criteria: dict[str, Any]
    candidate_ids: list[str]
    candidate_count: int
    created_at: datetime
    candidates: list[CandidateResponse] = []


class SegmentListResponse(CamelModel):
    items: list[SegmentResponse]
