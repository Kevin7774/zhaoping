from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.bp_pipeline import BpNoAcceptedRolesError, BpStageOutputError, run_bp_pipeline
from app.core.router import get_router
from app.db.session import get_project_session, project_session_factory
from app.models import Candidate, CandidateSearchSchedule, Job, JobCandidate, Project
from app.schemas.candidate_search_schedule import (
    CandidateSearchScheduleListResponse,
    CandidateSearchScheduleRequest,
    CandidateSearchScheduleResponse,
)
from app.schemas.candidate import CandidateComplianceReviewRequest, CandidateResponse, UniqueCandidateResponse
from app.schemas.job import JobResponse
from app.schemas.project import (
    ProjectBpInitializeRequest,
    ProjectBpInitializeResponse,
    ProjectCreate,
    ProjectGenerationMode,
    ProjectMaterialUploadResponse,
    ProjectResponse,
    ProjectRoleRejection,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])

PENDING_COMPLIANCE_REVIEW_STATUS = "pending_compliance_review"
PIPELINE_STATUS_PRIORITY = (PENDING_COMPLIANCE_REVIEW_STATUS, "awaiting_human", "processing", "pending_outreach", "sourced", "done")
# Five-stage pipeline: claims -> capability graph -> gap analysis -> role design -> critic gate.
BP_PIPELINE_PROMPT_NAME = "bp_pipeline_v1"
BP_PIPELINE_ROLE_MAX_TOKENS = 12000
BP_PIPELINE_MAX_ATTEMPTS = 3
# Per-stage budget; the five-stage pipeline makes up to 5 sequential LLM calls.
# Live measurement 2026-06-10: the claims call alone took ~123s on the default provider.
BP_PIPELINE_CALL_TIMEOUT_SECONDS = 180.0
PROJECT_MATERIAL_DIR = Path("data") / "input" / "projects"
PROJECT_MATERIAL_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
PROJECT_MATERIAL_PARSE_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
PROJECT_MATERIAL_EXTENSIONS = PROJECT_MATERIAL_TEXT_EXTENSIONS | PROJECT_MATERIAL_PARSE_EXTENSIONS
PROJECT_MATERIAL_MAX_BYTES = 20 * 1024 * 1024


class JobStats(TypedDict):
    candidate_count: int
    average_match_score: int
    pipeline_status: str | None


@router.get("", response_model=list[ProjectResponse])
def list_projects(session: Session = Depends(get_project_session)) -> list[ProjectResponse]:
    projects = session.scalars(select(Project).order_by(Project.created_at.desc(), Project.id.asc())).all()
    return [_project_response(project, _project_stats(session, project.id)) for project in projects]


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(request: ProjectCreate, session: Session = Depends(get_project_session)) -> ProjectResponse:
    if session.get(Project, request.id) is not None:
        raise HTTPException(status_code=409, detail=f"Project already exists: {request.id}")
    project = Project(id=request.id, name=request.name, status=request.status)
    session.add(project)
    session.commit()
    session.refresh(project)
    return _project_response(project, _project_stats(session, project.id))


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    request: ProjectUpdate,
    session: Session = Depends(get_project_session),
) -> ProjectResponse:
    project = _require_project(session, project_id)
    project.name = request.name
    project.status = request.status
    session.commit()
    session.refresh(project)
    return _project_response(project, _project_stats(session, project.id))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_project_session)) -> Response:
    project = _require_project(session, project_id)
    session.delete(project)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/{project_id}/preview-from-bp",
    response_model=ProjectBpInitializeResponse,
    response_model_exclude_none=True,
)
def preview_project_from_bp(
    project_id: str,
    request: ProjectBpInitializeRequest,
) -> ProjectBpInitializeResponse:
    matrix, jobs = _build_jobs_from_bp_pipeline(project_id, request)
    return _bp_initialize_response(project_id, request, matrix, jobs)


@router.post(
    "/{project_id}/initialize-from-bp",
    response_model=ProjectBpInitializeResponse,
    response_model_exclude_none=True,
)
def initialize_project_from_bp(
    project_id: str,
    request: ProjectBpInitializeRequest,
) -> ProjectBpInitializeResponse:
    matrix, jobs = _build_jobs_from_bp_pipeline(project_id, request)
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

    return _bp_initialize_response(project_id, request, matrix, jobs)


@router.post(
    "/{project_id}/materials/upload",
    response_model=ProjectMaterialUploadResponse,
)
async def upload_project_material(
    project_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_project_session),
) -> ProjectMaterialUploadResponse:
    _require_project(session, project_id)
    return await _save_project_material(file)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, session: Session = Depends(get_project_session)) -> ProjectResponse:
    project = _require_project(session, project_id)
    return _project_response(project, _project_stats(session, project_id))


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
    if request.decision == "reject":
        job_candidate.pipeline_status = "rejected"
        session.commit()
        session.refresh(job_candidate)
        return _candidate_response(job_candidate, candidate, job)
    if request.decision == "approve":
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


async def _save_project_material(file: UploadFile) -> ProjectMaterialUploadResponse:
    filename = _safe_project_material_filename(file.filename or "project-material.md")
    suffix = Path(filename).suffix.lower()
    if suffix not in PROJECT_MATERIAL_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Project material must be PDF, Word, image, Markdown, or TXT")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Project material file is empty")
    if len(content) > PROJECT_MATERIAL_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Project material file is too large")

    PROJECT_MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    source_path = PROJECT_MATERIAL_DIR / filename
    source_path.write_bytes(content)
    bp_path = _project_material_bp_path(source_path)
    parsed_text, metadata = _parse_project_material_for_bp(source_path, suffix)
    if bp_path == source_path:
        source_path.write_text(parsed_text, encoding="utf-8")
    else:
        bp_path.write_text(parsed_text, encoding="utf-8")

    return ProjectMaterialUploadResponse(
        file_name=filename,
        bp_file_path=bp_path.as_posix(),
        source_file_path=source_path.as_posix(),
        size_bytes=len(content),
        parser=_clean_text(metadata.get("parser")) or _clean_text(metadata.get("provider")),
        confidence=_metadata_confidence(metadata),
        degraded_reason=_clean_text(metadata.get("degraded_reason")),
    )


def _safe_project_material_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "project-material.md"
    cleaned = re.sub(r"[^\w._-]+", "-", name, flags=re.UNICODE).strip(".-")
    return cleaned[:160] or "project-material.md"


def _project_material_bp_path(source_path: Path) -> Path:
    if source_path.suffix.lower() in PROJECT_MATERIAL_TEXT_EXTENSIONS:
        return source_path
    return source_path.with_suffix(".md")


def _parse_project_material_for_bp(source_path: Path, suffix: str) -> tuple[str, dict[str, Any]]:
    if suffix in PROJECT_MATERIAL_TEXT_EXTENSIONS:
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="Project material must be UTF-8 text") from exc
        if not text.strip():
            raise HTTPException(status_code=422, detail="Project material file is empty")
        return text, {"parser": "plain_text", "provider": "local_file", "confidence": 0.99, "degraded_reason": None}

    router = get_router()
    document_error: Exception | None = None
    try:
        parser = router.document_parser()
        text = parser.parse(str(source_path))
        if text.strip():
            return text, dict(getattr(parser, "last_metadata", {}) or {})
        document_error = RuntimeError("document parser returned empty text")
    except Exception as exc:
        document_error = exc

    try:
        ocr_provider = router.ocr()
        if hasattr(ocr_provider, "extract_text"):
            ocr_text = ocr_provider.extract_text(file_path=str(source_path))
        elif hasattr(ocr_provider, "parse"):
            ocr_text = ocr_provider.parse(str(source_path))
        else:
            raise RuntimeError("OCR provider does not expose extract_text or parse")
        if not ocr_text.strip():
            raise RuntimeError("OCR provider returned empty text")
        return ocr_text, {
            "parser": "ocr",
            "provider": type(ocr_provider).__name__,
            "confidence": 0.65,
            "degraded_reason": f"Document parser fallback reason: {document_error}",
        }
    except Exception as ocr_exc:
        raise HTTPException(
            status_code=422,
            detail=f"Project material parsing failed: {document_error}; OCR fallback failed: {ocr_exc}",
        ) from ocr_exc


def _metadata_confidence(metadata: dict[str, Any]) -> float | None:
    value = metadata.get("confidence")
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return None


def _project_response(project: Project, stats: dict[str, int]) -> ProjectResponse:
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


def _no_accepted_roles_detail(exc: BpNoAcceptedRolesError) -> str:
    detail = "素材未能解析出任何通过证据审核的岗位。"
    rejected_summary = "；".join(
        f"「{item.get('title') or '未命名岗位'}」：{'；'.join(str(reason) for reason in item.get('reasons') or [])}"
        for item in exc.rejected[:5]
        if isinstance(item, dict)
    )
    if rejected_summary:
        detail += f"被拒绝的岗位及原因：{rejected_summary}。"
    detail += "请确认素材包含岗位职责、技能要求等原文内容后重试。"
    return detail


def _build_jobs_from_bp_pipeline(
    project_id: str,
    request: ProjectBpInitializeRequest,
) -> tuple[dict[str, Any], list[Job]]:
    bp_text = _bp_text_from_request(request)
    project_prompt = _clean_text(request.project_prompt)
    industry_research_prompt = _clean_text(request.industry_research_prompt)
    _validate_generation_inputs(request.generation_mode, bp_text, project_prompt, industry_research_prompt)

    source_sections = _generation_source_sections(
        bp_text=bp_text,
        project_prompt=project_prompt,
        industry_research_prompt=industry_research_prompt,
    )
    try:
        llm = get_router().llm(request.llm_service)
        matrix = run_bp_pipeline(
            llm,
            source_sections=source_sections,
            minimum_role_count=request.minimum_role_count,
            call_timeout_seconds=BP_PIPELINE_CALL_TIMEOUT_SECONDS,
            max_attempts=BP_PIPELINE_MAX_ATTEMPTS,
            roles_max_tokens=BP_PIPELINE_ROLE_MAX_TOKENS,
        )
    except HTTPException:
        raise
    except BpNoAcceptedRolesError as exc:
        raise HTTPException(status_code=422, detail=_no_accepted_roles_detail(exc)) from exc
    except BpStageOutputError as exc:
        matrix = _fallback_bp_matrix(
            bp_text=bp_text,
            project_prompt=project_prompt,
            industry_research_prompt=industry_research_prompt,
            generation_mode=request.generation_mode,
            minimum_role_count=request.minimum_role_count,
            reason=str(exc),
        )
    except TimeoutError as exc:
        matrix = _fallback_bp_matrix(
            bp_text=bp_text,
            project_prompt=project_prompt,
            industry_research_prompt=industry_research_prompt,
            generation_mode=request.generation_mode,
            minimum_role_count=request.minimum_role_count,
            reason=str(exc),
        )
    except Exception as exc:
        matrix = _fallback_bp_matrix(
            bp_text=bp_text,
            project_prompt=project_prompt,
            industry_research_prompt=industry_research_prompt,
            generation_mode=request.generation_mode,
            minimum_role_count=request.minimum_role_count,
            reason=f"LLM failed: {exc}",
        )
    roles = matrix.get("roles")
    if not isinstance(roles, list) or not roles:
        raise HTTPException(status_code=502, detail="BP pipeline returned no roles")
    return matrix, [_job_from_role(project_id, role, index) for index, role in enumerate(roles)]


def _bp_initialize_response(
    project_id: str,
    request: ProjectBpInitializeRequest,
    matrix: dict[str, Any],
    jobs: list[Job],
) -> ProjectBpInitializeResponse:
    empty_stats: JobStats = {"candidate_count": 0, "average_match_score": 0, "pipeline_status": None}
    response_jobs = [_job_response(job, empty_stats) for job in jobs]
    return ProjectBpInitializeResponse(
        project_id=project_id,
        project_name=request.project_name,
        prompt_name=BP_PIPELINE_PROMPT_NAME,
        generation_mode=request.generation_mode,
        job_count=len(response_jobs),
        jobs=response_jobs,
        industry_reading=_clean_text(matrix.get("industry_reading")),
        technical_assumptions=_string_list(matrix.get("technical_assumptions")),
        coverage_gaps=_string_list(matrix.get("coverage_gaps")),
        research_trace=_research_trace(matrix, request),
        claims=_non_empty_dict(matrix.get("claims")),
        capability_graph=_non_empty_dict(matrix.get("capability_graph")),
        gap_analysis=_non_empty_dict(matrix.get("gap_analysis")),
        rejected_roles=[
            ProjectRoleRejection(
                title=str(item.get("title") or "未命名岗位"),
                reasons=_string_list(item.get("reasons")),
                critic_category=_clean_text(item.get("critic_category")),
                missing_evidence=_string_list(item.get("missing_evidence")),
            )
            for item in matrix.get("rejected_roles") or []
            if isinstance(item, dict)
        ],
        generation_degraded=bool(matrix.get("degraded")),
    )


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
        rationale=_non_empty_dict(job.rationale),
    )


def _bp_text_from_request(request: ProjectBpInitializeRequest) -> str | None:
    if request.generation_mode == "prompt":
        return None
    bp_file_path = _clean_text(request.bp_file_path)
    if not bp_file_path:
        if request.generation_mode == "bp_file":
            raise HTTPException(status_code=422, detail="bpFilePath is required for bp_file generation")
        return None
    bp_path = Path(bp_file_path)
    if not bp_path.is_file():
        raise HTTPException(status_code=404, detail=f"BP file not found: {bp_file_path}")
    bp_text = bp_path.read_text(encoding="utf-8")
    if not bp_text.strip():
        raise HTTPException(status_code=422, detail="BP file is empty")
    return bp_text


def _validate_generation_inputs(
    generation_mode: ProjectGenerationMode,
    bp_text: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
) -> None:
    if generation_mode == "bp_file" and not bp_text:
        raise HTTPException(status_code=422, detail="bpFilePath is required for bp_file generation")
    if generation_mode == "prompt" and not (project_prompt or industry_research_prompt):
        raise HTTPException(status_code=422, detail="projectPrompt or industryResearchPrompt is required for prompt generation")
    if generation_mode == "bp_plus_prompt" and not (bp_text or project_prompt or industry_research_prompt):
        raise HTTPException(
            status_code=422,
            detail="bpFilePath, projectPrompt, or industryResearchPrompt is required for bp_plus_prompt generation",
        )


def _generation_source_sections(
    *,
    bp_text: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if bp_text:
        sections.append(("bp_markdown", bp_text))
    if project_prompt:
        sections.append(("project_prompt", project_prompt))
    if industry_research_prompt:
        sections.append(("industry_research_prompt", industry_research_prompt))
    return sections


def _fallback_bp_matrix(
    *,
    bp_text: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
    generation_mode: ProjectGenerationMode,
    minimum_role_count: int,
    reason: str,
) -> dict[str, Any]:
    role_specs = [
        ("industry_solution_lead", "行业研究与解决方案负责人", "Lead", ["拆解 BP 的目标行业、客户场景和交付边界", "把行业痛点转成岗位矩阵、解决方案包和售前验证清单"], ["行业研究", "解决方案架构", "B2B 交付"], ["咨询公司 AI/IoT 团队", "政企数字化服务商"]),
        ("edge_ai_architect", "边缘 AI 架构师", "Senior", ["设计边缘计算、模型推理、设备接入和云端管理的总体架构", "定义边缘盒子、工控机、GPU/NPU 和现场网络的技术选型"], ["Edge AI", "边缘计算", "系统架构"], ["边缘计算平台公司", "智能硬件厂商"]),
        ("cloud_edge_platform", "云边协同平台工程师", "Senior", ["建设设备注册、远程配置、任务下发和状态回传链路", "维护边缘节点与云端控制面的可靠同步"], ["Kubernetes", "MQTT", "API Gateway"], ["物联网平台团队", "工业互联网公司"]),
        ("data_governance_engineer", "数据治理与实时数据工程师", "Senior", ["设计多源数据采集、清洗、质量检查和权限分层", "支撑模型训练、RAG 检索和现场运营分析"], ["PostgreSQL", "ETL", "Data Quality"], ["数据中台团队", "工业数据公司"]),
        ("rag_application_engineer", "RAG 与知识库应用工程师", "Senior", ["建设文档解析、向量检索、召回评估和答案证据链", "把行业知识、设备手册和项目文档接入应用工作流"], ["RAG", "向量数据库", "文档解析"], ["企业知识库团队", "AI 应用公司"]),
        ("ocr_multimodal_engineer", "OCR 与多模态识别工程师", "Senior", ["处理票据、表单、现场图片和传感器上下文的结构化识别", "设计 OCR、多模态模型和人工复核闭环"], ["OCR", "多模态模型", "CV"], ["OCR 厂商", "视觉 AI 团队"]),
        ("agent_workflow_engineer", "AI Agent 工作流工程师", "Senior", ["设计任务编排、人工确认、工具调用和失败恢复流程", "把岗位分析、候选人搜索、评估和周报纳入可观测工作流"], ["FastAPI", "Agent Workflow", "SSE"], ["AI Agent 初创公司", "自动化平台团队"]),
        ("hardware_delivery_engineer", "智能硬件交付工程师", "Senior", ["负责边缘盒子、传感器、网关和现场设备联调", "形成安装、验收、故障排查和备件策略"], ["IoT", "工控机", "现场部署"], ["智能硬件厂商", "系统集成商"]),
        ("devops_private_deployment", "DevOps 与私有化部署工程师", "Senior", ["建设私有化部署、环境初始化、监控告警和升级回滚链路", "保障客户现场网络、容器、数据库和服务稳定运行"], ["Docker", "Linux", "Observability"], ["SaaS 私有化团队", "政企交付团队"]),
        ("fullstack_product_engineer", "全栈产品工程师", "Senior", ["实现客户工作台、配置后台、数据看板和权限入口", "把复杂 AI 能力包装成可操作的业务流程"], ["React", "TypeScript", "FastAPI"], ["B2B SaaS 团队", "AI 产品团队"]),
        ("qa_evaluation_engineer", "测试质量与模型评估工程师", "Senior", ["建立端到端测试、模型评估、回归集和现场验收指标", "覆盖 API、前端、任务流、模型输出和数据质量"], ["E2E Testing", "Model Evaluation", "pytest"], ["测试平台团队", "AI 评测团队"]),
        ("security_compliance_engineer", "数据安全与合规工程师", "Senior", ["设计隐私、权限、审计、数据留存和合规检查机制", "支撑医疗、教育、政企等高约束场景落地"], ["数据安全", "权限审计", "隐私合规"], ["安全合规团队", "政企解决方案团队"]),
        ("product_delivery_manager", "AI 产品交付经理", "Lead", ["把 BP 路线图拆成项目计划、里程碑、风险和验收标准", "协调研发、硬件、客户和供应商完成交付闭环"], ["项目管理", "AI 产品交付", "客户沟通"], ["AI 解决方案公司", "系统集成团队"]),
        ("customer_success_engineer", "客户成功与运维工程师", "Senior", ["运营上线后的客户问题、使用反馈和价值复盘", "沉淀常见问题、培训材料和续费扩展线索"], ["客户成功", "运维支持", "业务复盘"], ["企业服务团队", "政企客户成功团队"]),
    ]
    while len(role_specs) < minimum_role_count:
        index = len(role_specs) + 1
        role_specs.append(
            (
                f"bp_specialist_{index}",
                f"BP 专项交付工程师 {index}",
                "Senior",
                ["补齐 BP 中未完全展开的专项交付链路", "形成可验证的技术方案和交付清单"],
                ["系统交付", "问题定位", "技术文档"],
                ["AI 解决方案团队", "企业服务团队"],
            )
        )
    roles = []
    for role_id, title, seniority, responsibilities, skills, target_companies in role_specs[:minimum_role_count]:
        roles.append(
            {
                "role_id": role_id,
                "title": title,
                "seniority": seniority,
                "responsibilities": responsibilities,
                "must_have_skills": skills,
                "nice_to_have_skills": ["边缘计算", "AI 工程化", "客户现场经验"],
                "target_companies": target_companies,
                "exclusion_signals": ["只做概念 Demo，缺少生产交付或现场问题闭环"],
                "interview_questions": [f"请拆解一个与「{title}」相关的复杂交付问题，并说明排查路径。"],
                "scoring_rubric": {"domain_fit": 35, "engineering_depth": 35, "delivery_risk_control": 30},
                "search_strategy": {
                    "community": f'"{skills[0]}" AND "{skills[-1]}" AND production',
                    "academic": f'"{skills[0]}" AND evaluation AND deployment',
                    "industry": f'"{title}" OR "{target_companies[0]}"',
                },
                # Degraded output: no audited commitment->gap chain exists, say so explicitly.
                "why_needed": f"降级产出（{reason}）：未完成承诺-能力-缺口审计链，仅按保守矩阵覆盖「{title}」交付链路。",
                "bp_evidence": [],
                "business_commitments": [],
                "capability_gaps": [],
                "why_hire_not_vendor": None,
                "if_not_hired_risk": None,
                "dependencies": [],
                "first_90_day_outcomes": [],
                "hiring_priority": "P2",
                "confidence": 0.2,
            }
        )
    input_excerpt = _generation_input_excerpt(bp_text, project_prompt, industry_research_prompt)
    return {
        "degraded": True,
        "industry_reading": f"基于输入材料生成保守岗位矩阵：{input_excerpt}",
        "technical_assumptions": [
            "输入材料涉及边缘计算、AI 应用、智能硬件和私有化交付，需要按产品、工程、硬件、交付和合规分层招聘。",
            "当前矩阵为 LLM 超时或不可用时的保守 fallback，适合先启动项目空间，后续可再次用 LLM 精修。",
        ],
        "roles": roles,
        "coverage_gaps": [reason, "fallback 未读取外部行业资料；建议在 LLM 可用时重新预览岗位矩阵。"],
        "research_trace": [
            {
                "stage": "项目输入",
                "summary": _generation_input_summary(generation_mode, bp_text, project_prompt, industry_research_prompt),
                "evidence": _generation_input_evidence(bp_text, project_prompt, industry_research_prompt),
                "assumptions": ["未调用外部行业资料；fallback 只按内置岗位矩阵保守覆盖关键链路。"],
                "risk": reason,
            },
            {
                "stage": "岗位矩阵生成",
                "summary": "按行业研究、云边架构、硬件交付、AI 应用、质量、安全和客户成功拆出岗位。",
                "evidence": ["内置保守岗位矩阵", f"最少岗位数：{minimum_role_count}"],
                "assumptions": ["后续应在 LLM 可用时重新生成，以补齐更精细的行业和公司搜索策略。"],
                "risk": "fallback 结果可用于启动项目，但不应作为最终招聘方案。",
            },
        ],
    }


def _research_trace(matrix: dict[str, Any], request: ProjectBpInitializeRequest) -> list[dict[str, Any]]:
    model_trace = _coerce_research_trace(matrix.get("research_trace") or matrix.get("researchTrace"))
    if model_trace:
        return model_trace
    project_prompt = _clean_text(request.project_prompt)
    industry_research_prompt = _clean_text(request.industry_research_prompt)
    bp_reference = _clean_text(f"BP 文件：{request.bp_file_path}") if request.bp_file_path else None
    return [
        {
            "stage": "项目输入",
            "summary": _generation_input_summary(
                request.generation_mode,
                bp_reference,
                project_prompt,
                industry_research_prompt,
            ),
            "evidence": _request_input_evidence(request),
            "assumptions": [
                "岗位矩阵来自用户确认的项目输入；未在此接口中写入候选人或触达记录。",
                "行业研究偏好仅作为岗位拆解方向，不代表已经完成外部事实检索。",
            ],
            "risk": "如果输入材料过短，岗位边界和搜索策略需要人工复核。",
        },
        {
            "stage": "岗位矩阵生成",
            "summary": "按行业研究、技术架构、硬件或软件交付、质量、安全和客户成功拆解岗位并生成评估维度。",
            "evidence": [f"最少岗位数：{request.minimum_role_count}", f"Prompt：{BP_PIPELINE_PROMPT_NAME}"],
            "assumptions": ["预览阶段不写数据库；只有确认覆盖后才重建项目岗位。"],
            "risk": "确认覆盖会清空旧岗位和旧岗位候选人关联。",
        },
    ]


def _coerce_research_trace(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    trace: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stage = _clean_text(item.get("stage"))
        summary = _clean_text(item.get("summary"))
        if not stage or not summary:
            continue
        trace.append(
            {
                "stage": stage,
                "summary": summary,
                "evidence": _string_list(item.get("evidence") or item.get("source_evidence")),
                "assumptions": _string_list(item.get("assumptions") or item.get("technical_assumptions")),
                "risk": _clean_text(item.get("risk") or item.get("limitation")),
            }
        )
    return trace


def _generation_input_excerpt(
    bp_text: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
) -> str:
    materials = [text for text in [bp_text, project_prompt, industry_research_prompt] if text]
    if not materials:
        return "未提供有效输入材料"
    return " / ".join(" ".join(text.split())[:180] for text in materials)


def _generation_input_summary(
    generation_mode: ProjectGenerationMode,
    bp_text_or_reference: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
) -> str:
    parts = [f"生成模式：{generation_mode}"]
    if bp_text_or_reference:
        parts.append(f"BP 输入：{_short_text(bp_text_or_reference, 120)}")
    if project_prompt:
        parts.append(f"用户项目提示：{_short_text(project_prompt, 120)}")
    if industry_research_prompt:
        parts.append(f"行业研究偏好：{_short_text(industry_research_prompt, 120)}")
    return "；".join(parts)


def _generation_input_evidence(
    bp_text: str | None,
    project_prompt: str | None,
    industry_research_prompt: str | None,
) -> list[str]:
    evidence: list[str] = []
    if bp_text:
        evidence.append("BP 内容片段")
    if project_prompt:
        evidence.append("用户项目提示词")
    if industry_research_prompt:
        evidence.append("行业研究偏好")
    return evidence or ["无有效输入材料"]


def _request_input_evidence(request: ProjectBpInitializeRequest) -> list[str]:
    evidence: list[str] = []
    if request.bp_file_path:
        evidence.append(f"BP 文件路径：{request.bp_file_path}")
    if _clean_text(request.project_prompt):
        evidence.append("用户项目提示词")
    if _clean_text(request.industry_research_prompt):
        evidence.append("行业研究偏好")
    return evidence or ["无有效输入材料"]


def _short_text(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


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
        rationale=_role_rationale(role),
    )


def _role_rationale(role: dict[str, Any]) -> dict[str, Any] | None:
    confidence: float | None
    try:
        confidence = max(0.0, min(float(role.get("confidence")), 1.0))
    except (TypeError, ValueError):
        confidence = None
    rationale = {
        "why_needed": _clean_text(role.get("why_needed")),
        "bp_evidence": _string_list(role.get("bp_evidence")),
        "business_commitments": _string_list(role.get("business_commitments")),
        "capability_gaps": _string_list(role.get("capability_gaps")),
        "why_hire_not_vendor": _clean_text(role.get("why_hire_not_vendor")),
        "if_not_hired_risk": _clean_text(role.get("if_not_hired_risk")),
        "dependencies": _string_list(role.get("dependencies")),
        "first_90_day_outcomes": _string_list(role.get("first_90_day_outcomes")),
        "hiring_priority": _clean_text(role.get("hiring_priority")),
        "confidence": confidence,
        "business_context": _clean_text(role.get("business_context")),
        "job_scope": _clean_text(role.get("job_scope")),
        "must_have_signals": _string_list(role.get("must_have_signals")),
        "bonus_signals": _string_list(role.get("bonus_signals")),
        "risk_signals": _string_list(role.get("risk_signals")),
        "sourcing_keywords": _string_list(role.get("sourcing_keywords")),
        "outreach_angle": _clean_text(role.get("outreach_angle")),
    }
    return rationale if any(value not in (None, [], "") for value in rationale.values()) else None


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
