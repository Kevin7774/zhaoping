from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project
from app.schemas.candidate import CandidateResponse, UniqueCandidateResponse
from app.schemas.job import JobResponse
from app.schemas.project import ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])

PIPELINE_STATUS_PRIORITY = ("awaiting_human", "processing", "pending_outreach", "sourced", "done")


class JobStats(TypedDict):
    candidate_count: int
    average_match_score: int
    pipeline_status: str | None


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, session: Session = Depends(get_project_session)) -> ProjectResponse:
    project = _require_project(session, project_id)
    stats = _project_stats(session, project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        status=project.status,
        created_at=_utc_datetime(project.created_at),
        open_jobs=stats["open_jobs"],
        total_candidates=stats["total_candidates"],
        awaiting_human=stats["awaiting_human"],
        average_match_score=stats["average_match_score"],
    )


@router.get("/{project_id}/jobs", response_model=list[JobResponse])
def get_project_jobs(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[JobResponse]:
    _require_project(session, project_id)
    jobs = session.execute(select(Job).where(Job.project_id == project_id).offset(skip).limit(limit)).scalars().all()
    stats_by_job_id = _job_stats_by_job_id(session, [job.id for job in jobs])
    return [
        JobResponse(
            id=job.id,
            project_id=job.project_id,
            title=job.title,
            headcount=job.headcount,
            status=job.status,
            pipeline_status=stats["pipeline_status"] or job.status,
            candidate_count=stats["candidate_count"],
            average_match_score=stats["average_match_score"],
        )
        for job in jobs
        for stats in [_job_stats_for(job.id, stats_by_job_id)]
    ]


@router.get("/{project_id}/candidates", response_model=list[CandidateResponse])
def get_project_candidates(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[CandidateResponse]:
    _require_project(session, project_id)
    rows = session.execute(
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id)
        .order_by(JobCandidate.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return [
        CandidateResponse(
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
        for job_candidate, candidate, job in rows
    ]


@router.get("/{project_id}/candidates/unique", response_model=list[UniqueCandidateResponse])
def get_project_unique_candidates(
    project_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[UniqueCandidateResponse]:
    _require_project(session, project_id)
    candidates = (
        session.execute(
            select(Candidate)
            .join(JobCandidate, Candidate.id == JobCandidate.candidate_id)
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.project_id == project_id)
            .distinct()
            .order_by(Candidate.id)
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        UniqueCandidateResponse(
            id=candidate.id,
            name=candidate.name,
            current_company=candidate.current_company,
            city=candidate.city,
            email=candidate.email,
        )
        for candidate in candidates
    ]


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


def _project_stats(session: Session, project_id: str) -> dict[str, int]:
    open_jobs = session.scalar(select(func.count(Job.id)).where(Job.project_id == project_id)) or 0
    total_candidates = (
        session.scalar(
            select(func.count(func.distinct(JobCandidate.candidate_id)))
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.project_id == project_id)
        )
        or 0
    )
    awaiting_human = (
        session.scalar(
            select(func.count(JobCandidate.id))
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.project_id == project_id, JobCandidate.pipeline_status == "awaiting_human")
        )
        or 0
    )
    average_match_score = session.scalar(
        select(func.avg(JobCandidate.match_score))
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id)
    )
    return {
        "open_jobs": int(open_jobs),
        "total_candidates": int(total_candidates),
        "awaiting_human": int(awaiting_human),
        "average_match_score": _rounded_score(average_match_score),
    }


def _job_stats_by_job_id(session: Session, job_ids: list[str]) -> dict[str, JobStats]:
    if not job_ids:
        return {}

    stats_by_job_id: dict[str, JobStats] = {
        job_id: {"candidate_count": 0, "average_match_score": 0, "pipeline_status": None}
        for job_id in job_ids
    }
    stats_rows = session.execute(
        select(
            JobCandidate.job_id,
            func.count(JobCandidate.id),
            func.avg(JobCandidate.match_score),
        )
        .where(JobCandidate.job_id.in_(job_ids))
        .group_by(JobCandidate.job_id)
    ).all()
    for job_id, candidate_count, average_match_score in stats_rows:
        stats_by_job_id[job_id] = {
            "candidate_count": int(candidate_count or 0),
            "average_match_score": _rounded_score(average_match_score),
            "pipeline_status": None,
        }

    status_rows = session.execute(
        select(JobCandidate.job_id, JobCandidate.pipeline_status)
        .where(JobCandidate.job_id.in_(job_ids))
        .order_by(JobCandidate.id)
    ).all()
    statuses_by_job_id: dict[str, list[str]] = {job_id: [] for job_id in job_ids}
    for job_id, pipeline_status in status_rows:
        if pipeline_status:
            statuses_by_job_id[job_id].append(pipeline_status)

    for job_id, statuses in statuses_by_job_id.items():
        stats_by_job_id[job_id]["pipeline_status"] = _aggregate_pipeline_status(statuses)

    return stats_by_job_id


def _job_stats_for(job_id: str, stats_by_job_id: dict[str, JobStats]) -> JobStats:
    return stats_by_job_id.get(
        job_id,
        {"candidate_count": 0, "average_match_score": 0, "pipeline_status": None},
    )


def _aggregate_pipeline_status(statuses: list[str]) -> str | None:
    if not statuses:
        return None
    status_set = set(statuses)
    for status in PIPELINE_STATUS_PRIORITY:
        if status in status_set:
            return status
    return statuses[0]


def _rounded_score(value: object | None) -> int:
    if value is None:
        return 0
    return int(round(float(value)))


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
