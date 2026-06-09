from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Project, WeeklyReportRecord
from app.schemas.reports import WeeklyReportCreateRequest, WeeklyReportContent, WeeklyReportResponse

router = APIRouter(tags=["reports"])


@router.post("/reports/weekly", response_model=WeeklyReportResponse)
def create_weekly_report(
    request: WeeklyReportCreateRequest,
    session: Session = Depends(get_project_session),
) -> WeeklyReportResponse:
    _require_project(session, request.project_id)
    report = WeeklyReportRecord(
        id=f"report_{uuid4().hex[:12]}",
        project_id=request.project_id,
        source_task_id=request.source_task_id,
        content_json=json.dumps(request.report.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True),
        created_at=datetime.now(timezone.utc),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return _report_response(report)


@router.get("/projects/{project_id}/reports/latest", response_model=WeeklyReportResponse)
def get_latest_weekly_report(
    project_id: str,
    session: Session = Depends(get_project_session),
) -> WeeklyReportResponse:
    _require_project(session, project_id)
    report = (
        session.execute(
            select(WeeklyReportRecord)
            .where(WeeklyReportRecord.project_id == project_id)
            .order_by(WeeklyReportRecord.created_at.desc(), WeeklyReportRecord.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail=f"Weekly report not found for project: {project_id}")
    return _report_response(report)


@router.get("/reports/{report_id}", response_model=WeeklyReportResponse)
def get_weekly_report(report_id: str, session: Session = Depends(get_project_session)) -> WeeklyReportResponse:
    report = session.get(WeeklyReportRecord, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Weekly report not found: {report_id}")
    return _report_response(report)


def _report_response(report: WeeklyReportRecord) -> WeeklyReportResponse:
    return WeeklyReportResponse(
        report_id=report.id,
        project_id=report.project_id,
        source_task_id=report.source_task_id,
        content=_content_from_json(report.content_json),
        created_at=_as_utc(report.created_at),
    )


def _content_from_json(value: str) -> WeeklyReportContent:
    data = json.loads(value)
    if not isinstance(data, dict):
        data = {}
    return WeeklyReportContent(
        conclusion=_read_string(data.get("conclusion")),
        key_progress=_read_string_list(data.get("keyProgress") or data.get("key_progress")),
        top_candidates=_read_string_list(data.get("topCandidates") or data.get("top_candidates")),
        risks=_read_string_list(data.get("risks")),
        next_actions=_read_string_list(data.get("nextActions") or data.get("next_actions")),
    )


def _read_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _read_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
