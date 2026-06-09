from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project
from app.schemas.candidate import CandidateResponse
from app.schemas.job import JobResponse
from app.schemas.project import ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


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
def get_project_jobs(project_id: str, session: Session = Depends(get_project_session)) -> list[JobResponse]:
    _require_project(session, project_id)
    jobs = session.execute(select(Job).where(Job.project_id == project_id)).scalars().all()
    return [
        JobResponse(
            id=job.id,
            project_id=job.project_id,
            title=job.title,
            headcount=job.headcount,
            status=job.status,
            pipeline_status=job.status,
            candidate_count=stats["candidate_count"],
            average_match_score=stats["average_match_score"],
        )
        for job in jobs
        for stats in [_job_stats(session, job.id)]
    ]


@router.get("/{project_id}/candidates", response_model=list[CandidateResponse])
def get_project_candidates(project_id: str, session: Session = Depends(get_project_session)) -> list[CandidateResponse]:
    _require_project(session, project_id)
    rows = session.execute(
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id)
        .order_by(JobCandidate.id)
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


def _job_stats(session: Session, job_id: str) -> dict[str, int]:
    candidate_count = session.scalar(select(func.count(JobCandidate.id)).where(JobCandidate.job_id == job_id)) or 0
    average_match_score = session.scalar(select(func.avg(JobCandidate.match_score)).where(JobCandidate.job_id == job_id))
    return {
        "candidate_count": int(candidate_count),
        "average_match_score": _rounded_score(average_match_score),
    }


def _rounded_score(value: object | None) -> int:
    if value is None:
        return 0
    return int(round(float(value)))


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
