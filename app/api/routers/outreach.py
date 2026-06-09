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
    OutreachStrategyTag,
)

router = APIRouter(prefix="/outreach", tags=["outreach"])

DEFAULT_STRATEGY_TAG: OutreachStrategyTag = "场景叙事类"
QUANTGROUP_SYSTEM_PROMPT = (
    "量化派的目标是做 AI 应用公司，强调技术的商业落地能力。触达邮件应体现出"
    "用技术解决 10 亿级用户消费决策难题的使命感，而非仅仅追求算法极致。"
)


@router.post("/draft", response_model=OutreachDraftResponse)
def create_outreach_draft(
    request: OutreachDraftRequest,
    session: Session = Depends(get_project_session),
) -> OutreachDraftResponse:
    project = _require_project(session, request.project_id)
    job = _require_job(session, request.job_id, request.project_id)
    candidate = _require_candidate(session, request.candidate_id)
    now = _now()
    strategy_tag = request.strategy_tag or DEFAULT_STRATEGY_TAG
    draft = OutreachDraft(
        id=_new_id("draft"),
        project_id=project.id,
        job_id=job.id,
        candidate_id=candidate.id,
        segment_id=request.segment_id,
        subject=_build_quantgroup_subject(job, candidate),
        body=_build_backend_draft(project, job, candidate, strategy_tag),
        strategy_tag=strategy_tag,
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
    if request.strategy_tag is not None:
        draft.strategy_tag = request.strategy_tag
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
        strategy_tag=draft.strategy_tag,
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


def _build_quantgroup_subject(job: Job, candidate: Candidate) -> str:
    specialty = _candidate_specialty(job, candidate)
    return f"关于 {specialty} 与量化派“羊小咩”场景下的决策链路探讨"


def _build_backend_draft(
    project: Project,
    job: Job,
    candidate: Candidate,
    strategy_tag: OutreachStrategyTag = DEFAULT_STRATEGY_TAG,
) -> str:
    recent_work = _candidate_recent_work(candidate)
    technical_detail = _candidate_technical_detail(job, candidate)
    business_challenge = _business_challenge_for_candidate(job, candidate)
    quantgroup_method = _quantgroup_technical_method(candidate)
    domain = _candidate_domain(candidate)
    return "\n".join(
        [
            f"{candidate.name} 兄，",
            "",
            f"最近关注到你在 {recent_work} 上的思考，尤其是关于 {technical_detail} 的处理方式，"
            "这种在复杂海量数据下追求极速响应的思路很有价值。",
            "",
            "我是量化派的招聘团队。我们最近在重构“羊小咩”背后的智能决策引擎，"
            "旨在将 AI 从单纯的推荐，进化为更精准的消费撮合决策。"
            f"在处理 {business_challenge} 时，我们遇到了类似你过往项目里"
            "高吞吐、低延迟与策略准确性之间取舍的瓶颈，"
            f"目前正尝试通过 {quantgroup_method} 寻求突破。",
            "",
            "我们团队现在正处于从“智能金融技术”向“智能生活场景”全速切换的关键期，"
            "量化派不是只做算法指标的团队，而是 AI 应用公司，核心是用模块化数字化服务能力，"
            "把模型判断落到真实商业流量和消费场景里。"
            f"{QUANTGROUP_SYSTEM_PROMPT}",
            "",
            f"这封触达采用 {strategy_tag} 策略：希望把你的 {domain} 经验，"
            "放到“羊小咩”电商平台化和 AI 决策服务结合的场景里讨论，而不是直接进入面试流程。",
            "",
            f"如果你这周五下午或者下周一晚上有 20 分钟，我们可以就 {technical_detail} "
            f"和 {business_challenge} 对齐一下思路？纯技术推演，不聊面试。",
            "",
            "祝好，",
            "量化派招聘团队",
            f"项目：{project.name} / {job.title}",
        ]
    )


def _candidate_specialty(job: Job, candidate: Candidate) -> str:
    skills = _candidate_skills(candidate)
    if skills:
        return " / ".join(skills[:2])
    if candidate.title:
        return candidate.title
    return job.title


def _candidate_recent_work(candidate: Candidate) -> str:
    evidence = _candidate_evidence(candidate)
    if evidence:
        return _excerpt(evidence[0], 72)
    return candidate.current_company or "近期项目"


def _candidate_technical_detail(job: Job, candidate: Candidate) -> str:
    skills = _candidate_skills(candidate)
    if skills:
        return "、".join(skills[:3])
    if candidate.title:
        return candidate.title
    return job.title


def _candidate_domain(candidate: Candidate) -> str:
    title = candidate.title or ""
    company = candidate.current_company or ""
    skills = " ".join(_candidate_skills(candidate))
    text = f"{title} {company} {skills}".lower()
    if any(keyword in text for keyword in ("supply", "供应链", "inventory", "fulfillment")):
        return "供应链与履约优化"
    if any(keyword in text for keyword in ("data", "feature", "数据", "平台", "pipeline")):
        return "数据工程与实时特征平台"
    if any(keyword in text for keyword in ("recommend", "rank", "ranking", "推荐", "排序", "搜索")):
        return "推荐排序与消费意图建模"
    if any(keyword in text for keyword in ("ai", "ml", "vla", "算法", "model", "模型")):
        return "AI 建模与复杂决策"
    return "复杂业务系统工程"


def _business_challenge_for_candidate(job: Job, candidate: Candidate) -> str:
    domain = _candidate_domain(candidate)
    if domain == "供应链与履约优化":
        return "复杂供应链链路优化和消费供给匹配"
    if domain == "数据工程与实时特征平台":
        return "海量用户行为数据下的实时特征处理"
    if domain == "推荐排序与消费意图建模":
        return "高并发下的用户行为预测与消费意图建模"
    if domain == "AI 建模与复杂决策":
        return "高并发下的用户行为预测与智能消费决策"
    if "数据" in job.title or "平台" in job.title:
        return "海量用户行为数据下的实时特征处理"
    return "复杂业务场景下的智能消费决策链路优化"


def _quantgroup_technical_method(candidate: Candidate) -> str:
    domain = _candidate_domain(candidate)
    if domain == "供应链与履约优化":
        return "场景化策略引擎、动态定价信号和供应链履约特征"
    if domain == "数据工程与实时特征平台":
        return "实时特征治理、在线实验和模块化数字化服务"
    if domain == "推荐排序与消费意图建模":
        return "多源行为特征、实时排序和可解释策略评估"
    if domain == "AI 建模与复杂决策":
        return "大模型语义理解、实时决策特征和业务闭环评估"
    return "模块化数字化服务、在线策略评估和消费场景反馈闭环"


def _candidate_skills(candidate: Candidate) -> list[str]:
    if not candidate.skills:
        return []
    return [_excerpt(str(skill), 32) for skill in candidate.skills if str(skill).strip()]


def _candidate_evidence(candidate: Candidate) -> list[str]:
    if not candidate.evidence:
        return []
    return [_excerpt(str(item), 120) for item in candidate.evidence if str(item).strip()]


def _excerpt(value: str, limit: int) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


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
        strategy_tag=draft.strategy_tag,
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
        strategy_tag=history.strategy_tag,
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
