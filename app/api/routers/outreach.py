from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.integration_status import get_integration_status
from app.db.session import get_project_session
from app.models import Candidate, Job, OutreachDraft, OutreachHistory, Project
from app.schemas.outreach import (
    OutreachDraftPatchRequest,
    OutreachDraftRequest,
    OutreachDraftResponse,
    OutreachHistoryRecord,
    OutreachHistoryResponse,
    OutreachSendRequest,
)

router = APIRouter(prefix="/outreach", tags=["outreach"])


@router.post("/draft", response_model=OutreachDraftResponse)
def create_outreach_draft(
    request: OutreachDraftRequest,
    session: Session = Depends(get_project_session),
) -> OutreachDraftResponse:
    project = _require_project(session, request.project_id)
    job = _require_job(session, request.job_id, request.project_id)
    candidate = _require_candidate(session, request.candidate_id)
    now = _now()
    draft = OutreachDraft(
        id=_new_id("draft"),
        project_id=project.id,
        job_id=job.id,
        candidate_id=candidate.id,
        segment_id=request.segment_id,
        subject=f"关于「{job.title}」的一次沟通邀请",
        body=_build_backend_draft(project, job, candidate),
        status="draft",
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return _draft_response(draft)


@router.patch("/drafts/{draft_id}", response_model=OutreachDraftResponse)
def update_outreach_draft(
    draft_id: str,
    request: OutreachDraftPatchRequest,
    session: Session = Depends(get_project_session),
) -> OutreachDraftResponse:
    draft = _require_draft(session, draft_id)
    if request.subject is not None:
        draft.subject = request.subject
    if request.body is not None:
        draft.body = request.body
    draft.updated_at = _now()
    session.commit()
    session.refresh(draft)
    return _draft_response(draft)


@router.post("/send", response_model=OutreachHistoryRecord)
def send_outreach_draft(
    request: OutreachSendRequest,
    session: Session = Depends(get_project_session),
) -> OutreachHistoryRecord:
    draft = _require_draft(session, request.draft_id)
    if request.decision != "approve":
        raise HTTPException(status_code=409, detail="Outreach send requires approve decision")

    candidate = _require_candidate(session, draft.candidate_id)
    if not candidate.email:
        raise HTTPException(status_code=409, detail="Candidate email is required before outreach send")

    if not request.simulate and not _email_delivery_active():
        raise HTTPException(status_code=503, detail="email_delivery is not active; real send is disabled")
    if not request.simulate:
        raise HTTPException(status_code=501, detail="Real email provider send is not implemented; use simulate=true")

    now = _now()
    draft.status = "simulated"
    draft.updated_at = now
    history = OutreachHistory(
        id=_new_id("history"),
        project_id=draft.project_id,
        job_id=draft.job_id,
        candidate_id=draft.candidate_id,
        draft_id=draft.id,
        segment_id=draft.segment_id,
        email=candidate.email,
        subject=draft.subject,
        body=draft.body,
        status="simulated",
        delivery_mode="simulated",
        provider_status="simulated",
        created_at=now,
    )
    session.add(history)
    session.commit()
    session.refresh(history)
    return _history_response(history)


@router.get("/history", response_model=OutreachHistoryResponse)
def get_outreach_history(
    project_id: str = Query(..., alias="projectId"),
    candidate_id: str | None = Query(default=None, alias="candidateId"),
    segment_id: str | None = Query(default=None, alias="segmentId"),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_project_session),
) -> OutreachHistoryResponse:
    _require_project(session, project_id)
    query = select(OutreachHistory).where(OutreachHistory.project_id == project_id)
    if candidate_id:
        query = query.where(OutreachHistory.candidate_id == candidate_id)
    if segment_id:
        query = query.where(OutreachHistory.segment_id == segment_id)
    records = session.execute(query.order_by(OutreachHistory.created_at.desc()).limit(limit)).scalars().all()
    return OutreachHistoryResponse(items=[_history_response(record) for record in records])


def _build_backend_draft(project: Project, job: Job, candidate: Candidate) -> str:
    company = candidate.current_company or "近期项目"
    return "\n".join(
        [
            f"Hi {candidate.name},",
            "",
            f"我们正在推进「{project.name}」中的「{job.title}」岗位，看到你在 {company} 的经历，想邀请你做一次初步沟通。",
            "",
            "如果你方便，我们可以先约 20 分钟交流岗位背景、团队约束和你关注的问题。",
        ]
    )


def _email_delivery_active() -> bool:
    status = get_integration_status()
    capabilities = status.get("capabilities", [])
    return any(
        capability.get("service_type") == "email_delivery" and capability.get("status") in {"active", "available"}
        for capability in capabilities
    )


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


def _require_job(session: Session, job_id: str, project_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


def _require_candidate(session: Session, candidate_id: str) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
    return candidate


def _require_draft(session: Session, draft_id: str) -> OutreachDraft:
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Outreach draft not found: {draft_id}")
    return draft


def _draft_response(draft: OutreachDraft) -> OutreachDraftResponse:
    return OutreachDraftResponse(
        draft_id=draft.id,
        project_id=draft.project_id,
        job_id=draft.job_id,
        candidate_id=draft.candidate_id,
        segment_id=draft.segment_id,
        subject=draft.subject,
        body=draft.body,
        status=draft.status,
        backend_generated=True,
        created_at=_as_utc(draft.created_at),
        updated_at=_as_utc(draft.updated_at),
    )


def _history_response(history: OutreachHistory) -> OutreachHistoryRecord:
    return OutreachHistoryRecord(
        history_id=history.id,
        project_id=history.project_id,
        job_id=history.job_id,
        candidate_id=history.candidate_id,
        draft_id=history.draft_id,
        segment_id=history.segment_id,
        email=history.email,
        subject=history.subject,
        body=history.body,
        status=history.status,
        delivery_mode=history.delivery_mode,
        provider_status=history.provider_status,
        created_at=_as_utc(history.created_at),
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
