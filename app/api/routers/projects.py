from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_project_session
from app.models import Candidate, CandidateSearchSchedule, Job, JobCandidate, Project
from app.schemas.candidate_search_schedule import (
    CandidateSearchScheduleListResponse,
    CandidateSearchScheduleRequest,
    CandidateSearchScheduleResponse,
)
from app.schemas.candidate import CandidateComplianceReviewRequest, CandidateResponse, UniqueCandidateResponse
from app.schemas.job import JobResponse
from app.schemas.project import ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])

PENDING_COMPLIANCE_REVIEW_STATUS = "pending_compliance_review"
PIPELINE_STATUS_PRIORITY = (PENDING_COMPLIANCE_REVIEW_STATUS, "awaiting_human", "processing", "pending_outreach", "sourced", "done")


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
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[JobResponse]:
    _require_project(session, project_id)
    total_count = _project_job_count(session, project_id)
    _set_pagination_headers(response, total_count=total_count, skip=skip, limit=limit)
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


@router.get("/{project_id}/candidates", response_model=list[CandidateResponse], response_model_exclude_none=True)
def get_project_candidates(
    project_id: str,
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[CandidateResponse]:
    _require_project(session, project_id)
    total_count = _project_candidate_match_count(session, project_id)
    _set_pagination_headers(response, total_count=total_count, skip=skip, limit=limit)
    rows = session.execute(
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(Job.project_id == project_id)
        .order_by(JobCandidate.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return [_candidate_response(job_candidate, candidate, job) for job_candidate, candidate, job in rows]


@router.post(
    "/{project_id}/candidates/{job_candidate_id}/compliance-review",
    response_model=CandidateResponse,
    response_model_exclude_none=True,
)
def confirm_candidate_contact_compliance(
    project_id: str,
    job_candidate_id: int,
    request: CandidateComplianceReviewRequest,
    session: Session = Depends(get_project_session),
) -> CandidateResponse:
    _require_project(session, project_id)
    row = session.execute(
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .where(JobCandidate.id == job_candidate_id, Job.project_id == project_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Project candidate not found: {job_candidate_id}")
    job_candidate, candidate, job = row
    if request.decision != "approve":
        raise HTTPException(status_code=409, detail="Compliance review currently supports approve decisions only")
    if job_candidate.pipeline_status == PENDING_COMPLIANCE_REVIEW_STATUS:
        job_candidate.pipeline_status = "pending_outreach" if candidate.email else "sourced"
        session.commit()
        session.refresh(job_candidate)
    return _candidate_response(job_candidate, candidate, job)


@router.get("/{project_id}/candidates/unique", response_model=list[UniqueCandidateResponse], response_model_exclude_none=True)
def get_project_unique_candidates(
    project_id: str,
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_project_session),
) -> list[UniqueCandidateResponse]:
    _require_project(session, project_id)
    total_count = _project_unique_candidate_count(session, project_id)
    _set_pagination_headers(response, total_count=total_count, skip=skip, limit=limit)
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
            title=candidate.title,
            current_company=candidate.current_company,
            location=candidate.location,
            city=candidate.city,
            email=candidate.email,
            github_url=candidate.github_url,
            linkedin_url=candidate.linkedin_url,
            homepage_url=candidate.homepage_url,
            source_platform=candidate.source_platform,
            source_url=candidate.source_url,
            evidence=candidate.evidence,
            skills=candidate.skills,
            created_from_task_id=candidate.created_from_task_id,
        )
        for candidate in candidates
    ]


@router.get(
    "/{project_id}/candidate-search-schedules",
    response_model=CandidateSearchScheduleListResponse,
    response_model_exclude_none=True,
)
def list_candidate_search_schedules(
    project_id: str,
    session: Session = Depends(get_project_session),
) -> CandidateSearchScheduleListResponse:
    _require_project(session, project_id)
    rows = session.execute(
        select(CandidateSearchSchedule, Job)
        .join(Job, Job.id == CandidateSearchSchedule.job_id)
        .where(CandidateSearchSchedule.project_id == project_id)
        .order_by(Job.id)
    ).all()
    return CandidateSearchScheduleListResponse(
        items=[_candidate_search_schedule_response(schedule, job) for schedule, job in rows]
    )


@router.put(
    "/{project_id}/jobs/{job_id}/candidate-search-schedule",
    response_model=CandidateSearchScheduleResponse,
    response_model_exclude_none=True,
)
def upsert_candidate_search_schedule(
    project_id: str,
    job_id: str,
    request: CandidateSearchScheduleRequest,
    session: Session = Depends(get_project_session),
) -> CandidateSearchScheduleResponse:
    _require_project(session, project_id)
    job = session.get(Job, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Job not found in project: {job_id}")
    schedule = session.scalar(
        select(CandidateSearchSchedule).where(
            CandidateSearchSchedule.project_id == project_id,
            CandidateSearchSchedule.job_id == job_id,
        )
    )
    now = _dt_now()
    if schedule is None:
        schedule = CandidateSearchSchedule(project_id=project_id, job_id=job_id)
        session.add(schedule)
    was_enabled = bool(schedule.enabled)
    schedule.enabled = request.enabled
    schedule.interval_minutes = request.interval_minutes
    if request.enabled and (not was_enabled or schedule.next_run_at is None):
        schedule.next_run_at = now
    if not request.enabled:
        schedule.next_run_at = None
    schedule.updated_at = now
    session.commit()
    session.refresh(schedule)
    return _candidate_search_schedule_response(schedule, job)


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


def _candidate_search_schedule_response(
    schedule: CandidateSearchSchedule,
    job: Job,
) -> CandidateSearchScheduleResponse:
    last_status = _schedule_task_status(schedule) or schedule.last_status
    return CandidateSearchScheduleResponse(
        id=schedule.id,
        project_id=schedule.project_id,
        job_id=schedule.job_id,
        job_title=job.title,
        enabled=schedule.enabled,
        interval_minutes=schedule.interval_minutes,
        next_run_at=_utc_datetime(schedule.next_run_at),
        last_run_at=_utc_datetime(schedule.last_run_at),
        last_task_id=schedule.last_task_id,
        last_status=last_status,
        last_error=schedule.last_error,
    )


def _schedule_task_status(schedule: CandidateSearchSchedule) -> str | None:
    if not schedule.last_task_id:
        return None
    try:
        from app.core import orchestrator

        snapshot = orchestrator.task_store.snapshot(schedule.last_task_id)
    except Exception:
        return None
    if not snapshot:
        return None
    status = snapshot.get("status")
    return str(status) if status else None


def _set_pagination_headers(response: Response, *, total_count: int, skip: int, limit: int) -> None:
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Has-More"] = "true" if skip + limit < total_count else "false"


def _project_job_count(session: Session, project_id: str) -> int:
    return int(session.scalar(select(func.count(Job.id)).where(Job.project_id == project_id)) or 0)


def _project_candidate_match_count(session: Session, project_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(JobCandidate.id))
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.project_id == project_id)
        )
        or 0
    )


def _project_unique_candidate_count(session: Session, project_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(func.distinct(JobCandidate.candidate_id)))
            .join(Job, Job.id == JobCandidate.job_id)
            .where(Job.project_id == project_id)
        )
        or 0
    )


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
            .where(
                Job.project_id == project_id,
                JobCandidate.pipeline_status.in_(["awaiting_human", PENDING_COMPLIANCE_REVIEW_STATUS]),
            )
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


def _candidate_response(job_candidate: JobCandidate, candidate: Candidate, job: Job) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        job_candidate_id=job_candidate.id,
        job_id=job.id,
        job_title=job.title,
        name=candidate.name,
        title=candidate.title,
        current_company=candidate.current_company,
        location=candidate.location,
        city=candidate.city,
        email=candidate.email,
        github_url=candidate.github_url,
        linkedin_url=candidate.linkedin_url,
        homepage_url=candidate.homepage_url,
        source_platform=candidate.source_platform,
        source_url=candidate.source_url,
        evidence=candidate.evidence,
        skills=candidate.skills,
        created_from_task_id=candidate.created_from_task_id,
        match_score=job_candidate.match_score,
        pipeline_status=job_candidate.pipeline_status,
        job_evidence=job_candidate.evidence,
        source_task_id=job_candidate.source_task_id,
    )


def _rounded_score(value: object | None) -> int:
    if value is None:
        return 0
    return int(round(float(value)))


def _dt_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
