from __future__ import annotations

from datetime import datetime

from app.schemas.common import CamelModel


class WeeklyReportContent(CamelModel):
    conclusion: str | None = None
    key_progress: list[str] = []
    top_candidates: list[str] = []
    risks: list[str] = []
    next_actions: list[str] = []


class WeeklyReportCreateRequest(CamelModel):
    project_id: str
    source_task_id: str | None = None
    report: WeeklyReportContent


class WeeklyReportResponse(CamelModel):
    report_id: str
    project_id: str
    source_task_id: str | None = None
    content: WeeklyReportContent
    created_at: datetime
