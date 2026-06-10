from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.prompt_config import load_system_prompt
from app.core.router import get_router
from app.core.workflow_context import retry_prompt
from app.db.session import get_project_session, project_session_factory
from app.models import Candidate, CandidateSearchSchedule, Job, JobCandidate, Project
from app.schemas.candidate_search_schedule import (
    CandidateSearchScheduleListResponse,
    CandidateSearchScheduleRequest,
    CandidateSearchScheduleResponse,
)
from app.schemas.candidate import CandidateComplianceReviewRequest, CandidateResponse, UniqueCandidateResponse
from app.schemas.job import JobResponse
from app.schemas.project import ProjectBpInitializeRequest, ProjectBpInitializeResponse, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])

PENDING_COMPLIANCE_REVIEW_STATUS = "pending_compliance_review"
PIPELINE_STATUS_PRIORITY = (PENDING_COMPLIANCE_REVIEW_STATUS, "awaiting_human", "processing", "pending_outreach", "sourced", "done")
BP_DECONSTRUCTOR_PROMPT_NAME = "bp_deconstructor_v2"
BP_DECONSTRUCTOR_MAX_TOKENS = 16000
BP_DECONSTRUCTOR_MAX_ATTEMPTS = 3
BP_DECONSTRUCTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["industry_reading", "technical_assumptions", "roles", "coverage_gaps"],
    "properties": {
        "industry_reading": {"type": "string"},
        "technical_assumptions": {"type": "array", "items": {"type": "string"}},
        "coverage_gaps": {"type": "array", "items": {"type": "string"}},
        "roles": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "title",
                    "seniority",
                    "responsibilities",
                    "must_have_skills",
                    "nice_to_have_skills",
                    "target_companies",
                    "exclusion_signals",
                    "interview_questions",
                    "scoring_rubric",
                    "search_strategy",
                ],
            },
        },
    },
}


class JobStats(TypedDict):
    candidate_count: int
    average_match_score: int
    pipeline_status: str | None


@router.post(
    "/{project_id}/initialize-from-bp",
    response_model=ProjectBpInitializeResponse,
    response_model_exclude_none=True,
)
def initialize_project_from_bp(
    project_id: str,
    request: ProjectBpInitializeRequest,
) -> ProjectBpInitializeResponse:
    bp_path = Path(request.bp_file_path)
    if not bp_path.is_file():
        raise HTTPException(status_code=404, detail=f"BP file not found: {request.bp_file_path}")
    bp_text = bp_path.read_text(encoding="utf-8")
    if not bp_text.strip():
        raise HTTPException(status_code=422, detail="BP file is empty")

    prompt = _build_bp_deconstructor_prompt(bp_text)
    try:
        llm = get_router().llm(request.llm_service)
        matrix = _deconstruct_bp_matrix(llm, prompt, minimum_role_count=request.minimum_role_count)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"BP deconstructor LLM failed: {exc}") from exc
    roles = matrix.get("roles")
    if not isinstance(roles, list) or not roles:
        raise HTTPException(status_code=502, detail="BP deconstructor returned no roles")

    jobs = [_job_from_role(project_id, role, index) for index, role in enumerate(roles)]
    factory = project_session_factory()
    with factory() as session:
        existing_job_ids = set(session.scalars(select(Job.id).where(Job.project_id == project_id)).all())
        if existing_job_ids:
            session.execute(delete(JobCandidate).where(JobCandidate.job_id.in_(existing_job_ids)))
        session.execute(delete(Job).where(Job.project_id == project_id))
        project = session.get(Project, project_id)
        if project is None:
            project = Project(id=project_id, name=request.project_name, status="active")
            session.add(project)
        else:
            project.name = request.project_name
            project.status = "active"
        session.flush()
        session.add_all(jobs)
        session.commit()
        response_jobs = [
            _job_response(job, {"candidate_count": 0, "average_match_score": 0, "pipeline_status": None})
            for job in jobs
        ]

    return ProjectBpInitializeResponse(
        project_id=project_id,
        project_name=request.project_name,
        prompt_name=BP_DECONSTRUCTOR_PROMPT_NAME,
        job_count=len(response_jobs),
        jobs=response_jobs,
        industry_reading=_clean_text(matrix.get("industry_reading")),
        technical_assumptions=_string_list(matrix.get("technical_assumptions")),
        coverage_gaps=_string_list(matrix.get("coverage_gaps")),
    )


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


@router.get("/{project_id}/jobs", response_model=list[JobResponse], response_model_exclude_none=True)
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
        _job_response(job, stats)
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


def _job_response(job: Job, stats: JobStats) -> JobResponse:
    return JobResponse(
        id=job.id,
        project_id=job.project_id,
        title=job.title,
        headcount=job.headcount,
        status=job.status,
        pipeline_status=stats["pipeline_status"] or job.status,
        candidate_count=stats["candidate_count"],
        average_match_score=stats["average_match_score"],
        seniority=_clean_text(job.seniority),
        responsibilities=_non_empty_list(job.responsibilities),
        must_have_skills=_non_empty_list(job.must_have_skills),
        nice_to_have_skills=_non_empty_list(job.nice_to_have_skills),
        target_companies=_non_empty_list(job.target_companies),
        exclusion_signals=_non_empty_list(job.exclusion_signals),
        interview_questions=_non_empty_list(job.interview_questions),
        scoring_rubric=_non_empty_dict(job.scoring_rubric),
        search_strategy=_non_empty_dict(job.search_strategy),
    )


def _build_bp_deconstructor_prompt(bp_text: str) -> str:
    system_prompt = load_system_prompt(BP_DECONSTRUCTOR_PROMPT_NAME)
    if not system_prompt:
        raise HTTPException(status_code=500, detail=f"Missing prompt: {BP_DECONSTRUCTOR_PROMPT_NAME}")
    return (
        f"{system_prompt}\n\n"
        "输入 BP 如下。只输出一个 JSON 对象；不要 Markdown，不要代码围栏，不要解释。\n"
        "bp_markdown:\n"
        f"{bp_text}"
    )


def _parse_bp_deconstructor_output(raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"BP deconstructor returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="BP deconstructor returned non-object JSON")
    return payload


def _deconstruct_bp_matrix(
    llm: Any,
    initial_prompt: str,
    *,
    minimum_role_count: int,
) -> dict[str, Any]:
    prompt = initial_prompt
    last_error = "unknown structured output error"
    for _attempt in range(BP_DECONSTRUCTOR_MAX_ATTEMPTS):
        output = llm.text(prompt, max_tokens=BP_DECONSTRUCTOR_MAX_TOKENS)
        try:
            matrix = _parse_bp_deconstructor_output(output)
            _validate_minimum_role_count(matrix, minimum_role_count=minimum_role_count)
            return matrix
        except HTTPException as exc:
            last_error = str(exc.detail)
            prompt = _bp_repair_prompt(output, last_error, minimum_role_count)
    raise HTTPException(status_code=502, detail=f"BP deconstructor structured output failed: {last_error}")


def _validate_minimum_role_count(matrix: dict[str, Any], *, minimum_role_count: int) -> None:
    roles = matrix.get("roles")
    role_count = len(roles) if isinstance(roles, list) else 0
    if role_count < minimum_role_count:
        raise HTTPException(
            status_code=502,
            detail=f"BP deconstructor returned {role_count} roles; expected at least {minimum_role_count}",
        )


def _bp_repair_prompt(last_output: str, validation_error: str, minimum_role_count: int) -> str:
    repair = retry_prompt(
        BP_DECONSTRUCTOR_SCHEMA,
        last_output,
        validation_error,
    )
    return (
        f"{repair}\n\n"
        "输出紧凑 JSON：每个数组保留 2-4 条最关键内容，search_strategy 每个字段使用一句 Boolean/关键词策略，"
        "scoring_rubric 保留 3-5 个维度。\n"
        f"数量硬约束：至少输出 {minimum_role_count} 个 roles；不要用重复岗位凑数。"
    )


def _job_from_role(project_id: str, role: Any, index: int) -> Job:
    if not isinstance(role, dict):
        raise HTTPException(status_code=502, detail=f"Role #{index + 1} is not an object")
    title = _clean_text(role.get("title"))
    if not title:
        raise HTTPException(status_code=502, detail=f"Role #{index + 1} is missing title")
    return Job(
        id=_stable_job_id(project_id, role, index),
        project_id=project_id,
        title=title[:128],
        headcount=_headcount(role.get("headcount")),
        status="sourcing",
        seniority=_clean_text(role.get("seniority")),
        responsibilities=_string_list(role.get("responsibilities")),
        must_have_skills=_string_list(role.get("must_have_skills") or role.get("hard_requirements")),
        nice_to_have_skills=_string_list(role.get("nice_to_have_skills")),
        target_companies=_string_list(role.get("target_companies")),
        exclusion_signals=_string_list(role.get("exclusion_signals")),
        interview_questions=_string_list(role.get("interview_questions")),
        scoring_rubric=_object_dict(role.get("scoring_rubric")),
        search_strategy=_search_strategy(role),
    )


def _stable_job_id(project_id: str, role: dict[str, Any], index: int) -> str:
    raw = _clean_text(role.get("role_id")) or _clean_text(role.get("title")) or f"role_{index}"
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").lower() or f"role_{index}"
    digest = hashlib.sha1(f"{project_id}:{raw}:{index}".encode("utf-8")).hexdigest()[:8]
    return f"job_{slug[:42]}_{digest}"[:64]


def _search_strategy(role: dict[str, Any]) -> dict[str, Any]:
    raw_strategy = role.get("search_strategy")
    if isinstance(raw_strategy, dict):
        return {str(key): value for key, value in raw_strategy.items() if value not in (None, "", [], {})}
    search_queries = role.get("search_queries")
    if isinstance(search_queries, dict):
        return {str(key): value for key, value in search_queries.items() if value not in (None, "", [], {})}
    queries = _string_list(search_queries)
    return {"queries": queries} if queries else {}


def _headcount(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 1
    return max(0, min(count, 99))


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if str(item or "").strip()]
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return [str(value).strip()]


def _object_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if item not in (None, "", [], {})}


def _non_empty_list(value: Any) -> list[str] | None:
    items = _string_list(value)
    return items or None


def _non_empty_dict(value: Any) -> dict[str, Any] | None:
    payload = _object_dict(value)
    return payload or None


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
