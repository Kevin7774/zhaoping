from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project, Segment
from app.schemas.candidate import CandidateResponse
from app.schemas.segments import (
    SegmentCreateRequest,
    SegmentCriteria,
    SegmentListResponse,
    SegmentQueryRequest,
    SegmentQueryResponse,
    SegmentResponse,
)

router = APIRouter(prefix="/segments", tags=["segments"])


@router.post("/query", response_model=SegmentQueryResponse)
def query_segment_candidates(
    request: SegmentQueryRequest,
    session: Session = Depends(get_project_session),
) -> SegmentQueryResponse:
    _require_project(session, request.project_id)
    candidates = _query_candidates(session, request.project_id, request.criteria)
    return SegmentQueryResponse(
        project_id=request.project_id,
        criteria=_criteria_dict(request.criteria),
        total=len(candidates),
        candidates=candidates,
    )


@router.post("", response_model=SegmentResponse)
def create_segment(
    request: SegmentCreateRequest,
    session: Session = Depends(get_project_session),
) -> SegmentResponse:
    _require_project(session, request.project_id)
    candidates = _query_candidates(session, request.project_id, request.criteria)
    candidate_ids = request.candidate_ids or [candidate.id for candidate in candidates]
    now = datetime.now(timezone.utc)
    segment = Segment(
        id=f"segment_{uuid4().hex[:12]}",
        project_id=request.project_id,
        name=request.name,
        criteria_json=_to_json(_criteria_dict(request.criteria)),
        candidate_ids_json=_to_json(candidate_ids),
        created_at=now,
    )
    session.add(segment)
    session.commit()
    session.refresh(segment)
    return _segment_response(segment, candidates)


@router.get("", response_model=SegmentListResponse)
def list_segments(
    project_id: str = Query(..., alias="projectId"),
    session: Session = Depends(get_project_session),
) -> SegmentListResponse:
    _require_project(session, project_id)
    segments = (
        session.execute(select(Segment).where(Segment.project_id == project_id).order_by(Segment.created_at.desc()))
        .scalars()
        .all()
    )
    return SegmentListResponse(items=[_segment_response(segment, []) for segment in segments])


@router.get("/{segment_id}", response_model=SegmentResponse)
def get_segment(segment_id: str, session: Session = Depends(get_project_session)) -> SegmentResponse:
    segment = session.get(Segment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    candidates = _candidate_responses_for_ids(session, segment.project_id, _load_json_list(segment.candidate_ids_json))
    return _segment_response(segment, candidates)


def _query_candidates(session: Session, project_id: str, criteria: SegmentCriteria) -> list[CandidateResponse]:
    query = (
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id)
    )
    if criteria.job_profile_id and criteria.job_profile_id != "all":
        query = query.where(Job.id == criteria.job_profile_id)
    if criteria.min_score:
        query = query.where(JobCandidate.match_score >= criteria.min_score)
    if criteria.city:
        query = query.where(Candidate.city == criteria.city)
    if criteria.has_email == "yes":
        query = query.where(Candidate.email.is_not(None), Candidate.email != "")
    elif criteria.has_email == "no":
        query = query.where((Candidate.email.is_(None)) | (Candidate.email == ""))
    if criteria.keyword:
        keyword = f"%{criteria.keyword.strip()}%"
        query = query.where(
            (Candidate.name.like(keyword))
            | (Candidate.current_company.like(keyword))
            | (Job.title.like(keyword))
            | (Candidate.city.like(keyword))
        )

    rows = session.execute(query.order_by(JobCandidate.match_score.desc(), JobCandidate.id)).all()
    return [_candidate_response(job_candidate, candidate, job) for job_candidate, candidate, job in rows]


def _candidate_responses_for_ids(session: Session, project_id: str, candidate_ids: list[str]) -> list[CandidateResponse]:
    if not candidate_ids:
        return []
    rows = session.execute(
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id, Candidate.id.in_(candidate_ids))
        .order_by(JobCandidate.match_score.desc(), JobCandidate.id)
    ).all()
    return [_candidate_response(job_candidate, candidate, job) for job_candidate, candidate, job in rows]


def _candidate_response(job_candidate: JobCandidate, candidate: Candidate, job: Job) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        job_candidate_id=job_candidate.id,
        job_id=job.id,
        job_title=job.title,
        name=candidate.name,
        current_company=candidate.current_company,
        city=candidate.city,
        email=candidate.email,
        match_score=job_candidate.match_score,
        pipeline_status=job_candidate.pipeline_status,
    )


def _segment_response(segment: Segment, candidates: list[CandidateResponse]) -> SegmentResponse:
    candidate_ids = _load_json_list(segment.candidate_ids_json)
    return SegmentResponse(
        segment_id=segment.id,
        project_id=segment.project_id,
        name=segment.name,
        criteria=_load_json_object(segment.criteria_json),
        candidate_ids=candidate_ids,
        candidate_count=len(candidate_ids),
        created_at=_as_utc(segment.created_at),
        candidates=candidates,
    )


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


def _criteria_dict(criteria: SegmentCriteria) -> dict[str, Any]:
    return criteria.model_dump(by_alias=True, exclude_none=True)


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_json_object(value: str) -> dict[str, Any]:
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


def _load_json_list(value: str) -> list[str]:
    data = json.loads(value)
    return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
