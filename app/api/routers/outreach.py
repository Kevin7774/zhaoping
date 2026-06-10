from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_optional_current_user
from app.core.prompt_config import load_system_prompt
from app.core.integration_status import get_integration_status
from app.core.router import get_router
from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, OutreachDraft, OutreachHistory, Project, User
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
OUTREACH_FORBIDDEN_PHRASES = (
    "希望这封邮件没有打扰到您",
    "我正在寻找优秀的人才",
    "优秀的人才",
    "招聘黑话",
    "招聘团队",
    "面试",
)


@router.post("/draft", response_model=OutreachDraftResponse)
def create_outreach_draft(
    request: OutreachDraftRequest,
    session: Session = Depends(get_project_session),
    current_user: User | None = Depends(get_optional_current_user),
) -> OutreachDraftResponse:
    project = _require_project(session, request.project_id)
    job = _require_job(session, request.job_id, request.project_id)
    candidate = _require_candidate(session, request.candidate_id)
    _require_contact_compliance_unlocked(session, job.id, candidate.id)
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
        created_by_user_id=current_user.id if current_user else None,
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
    current_user: User | None = Depends(get_optional_current_user),
) -> OutreachHistoryRecord:
    draft = _require_draft(session, request.draft_id)
    if request.decision != "approve":
        raise HTTPException(status_code=409, detail="Outreach send requires approve decision")

    candidate = _require_candidate(session, draft.candidate_id)
    if not candidate.email:
        raise HTTPException(status_code=409, detail="Candidate email is required before outreach send")

    compliance_status = _contact_compliance_status(session, draft.job_id, candidate.id)
    if compliance_status in {"pending_compliance_review", "rejected"}:
        if not request.simulate:
            raise HTTPException(
                status_code=403,
                detail=f"Candidate contact compliance status blocks real send: {compliance_status}",
            )
        return _record_outreach_history(
            session,
            draft=draft,
            candidate=candidate,
            current_user=current_user,
            status="blocked_simulation",
            delivery_mode="simulated",
            provider_status=f"blocked_by_compliance:{compliance_status}",
        )

    if not request.simulate and not _email_delivery_active():
        raise HTTPException(status_code=503, detail="email_delivery is not active; real send is disabled")

    provider_result: dict[str, Any] | None = None
    delivery_mode = "simulated"
    history_status = "simulated"
    provider_status = "simulated"
    if not request.simulate:
        try:
            provider_result = _send_real_email(
                to=candidate.email,
                subject=draft.subject,
                body=draft.body,
                sender_email=current_user.email if current_user else None,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"email_delivery send failed: {exc}") from exc
        delivery_mode = "real"
        history_status = str(provider_result.get("status") or "sent")
        provider_status = _provider_status(provider_result)

    return _record_outreach_history(
        session,
        draft=draft,
        candidate=candidate,
        current_user=current_user,
        status=history_status,
        delivery_mode=delivery_mode,
        provider_status=provider_status,
    )


def _record_outreach_history(
    session: Session,
    *,
    draft: OutreachDraft,
    candidate: Candidate,
    current_user: User | None,
    status: str,
    delivery_mode: str,
    provider_status: str,
) -> OutreachHistoryRecord:
    now = _now()
    draft.status = status
    draft.updated_at = now
    history = OutreachHistory(
        id=_new_id("history"),
        project_id=draft.project_id,
        job_id=draft.job_id,
        candidate_id=draft.candidate_id,
        draft_id=draft.id,
        segment_id=draft.segment_id,
        email=candidate.email,
        sender_email=current_user.email if current_user else None,
        strategy_tag=draft.strategy_tag,
        subject=draft.subject,
        body=draft.body,
        status=status,
        delivery_mode=delivery_mode,
        provider_status=provider_status,
        sent_by_user_id=current_user.id if current_user else None,
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


def _job_rationale(job: Job) -> dict:
    return job.rationale if isinstance(job.rationale, dict) else {}


def _job_driven_outreach(job: Job) -> bool:
    """Jobs designed from project materials carry a rationale and drive their own outreach narrative.

    Legacy seeded jobs without rationale keep the original hardware-delivery copy.
    """
    return bool(_job_rationale(job))


def _outreach_challenge(project: Project, job: Job, candidate: Candidate) -> str:
    rationale = _job_rationale(job)
    base = str(
        rationale.get("business_context") or rationale.get("job_scope") or rationale.get("why_needed") or ""
    ).strip()
    if base:
        return f"把「{_excerpt(base, 80)}」从方案推进到可上线、可迭代的真实交付"
    return _hardware_challenge_for_candidate(job, candidate)


def _outreach_must_mention(project: Project, job: Job) -> list[str]:
    if _job_driven_outreach(job):
        return [item for item in [project.name, job.title] if item]
    return ["智能硬件交付"]


def _build_quantgroup_subject(job: Job, candidate: Candidate) -> str:
    specialty = _candidate_specialty(job, candidate)
    if _job_driven_outreach(job):
        return f"关于 {specialty} 在「{job.title}」方向落地的技术切磋"
    return f"关于 {specialty} 真机部署问题的技术切磋"


def _build_backend_draft(
    project: Project,
    job: Job,
    candidate: Candidate,
    strategy_tag: OutreachStrategyTag = DEFAULT_STRATEGY_TAG,
) -> str:
    llm_draft = _build_llm_hardware_draft(project, job, candidate, strategy_tag)
    if llm_draft:
        return llm_draft

    recent_work = _candidate_recent_work(candidate)
    technical_detail = _candidate_technical_detail(job, candidate)
    business_challenge = _outreach_challenge(project, job, candidate)
    domain = _candidate_domain(candidate)
    project_name = project.name or "当前项目"
    if _job_driven_outreach(job):
        return "\n".join(
            [
                f"看到你材料里写到的「{recent_work}」，这个工程取舍很扎实。",
                "",
                f"{candidate.name}，你好。我这边负责「{project_name}」里「{job.title}」方向的落地，最近卡在"
                f"{business_challenge}：方案在评审里能讲通，但一到真实业务交付，就会被需求边界、数据质量和"
                "上线节奏一起放大。",
                "",
                f"你在 {technical_detail} 上的经历，和我们现在要把这件事从 demo 推到真实商业化的阶段很接近。"
                "我更想拿一个具体技术问题和你对齐：在不牺牲系统可维护性的前提下，哪些约束应该先固化进交付链路，"
                "哪些应该留给数据和模型迭代？",
                "",
                f"这封触达采用 {strategy_tag} 策略：不聊流程，只做一次平等的技术切磋。"
                "如果你愿意，我想约 20 分钟，把我们现在的未解瓶颈摊开，请你按专家视角直接挑问题。",
                "",
                "研发总监",
            ]
        )
    return "\n".join(
        [
            f"看到你材料里写到的「{recent_work}」，这个工程取舍很硬核。",
            "",
            f"{candidate.name}，你好。我这边负责 {project_name} 的核心硬件产品落地，最近卡在"
            f"{business_challenge}：算法在离线指标里能跑通，但一到真机部署，就会被时延、传感器噪声、"
            "执行器余量和现场稳定性一起放大。",
            "",
            f"你在 {technical_detail} 上的经历，和我们现在要把 {domain} 从 demo 推到真实商业化的阶段很接近。"
            "我更想拿一个具体技术问题和你对齐：在不牺牲系统可维护性的前提下，哪些约束应该进控制/规划闭环，"
            "哪些应该留给数据和模型迭代？",
            "",
            f"这封触达采用 {strategy_tag} 策略：不聊流程，只做一次平等的技术切磋。"
            "如果你愿意，我想约 20 分钟，把我们现在的未解瓶颈摊开，请你按专家视角直接挑问题。",
            "",
            "研发总监",
        ]
    )


def _build_llm_hardware_draft(
    project: Project,
    job: Job,
    candidate: Candidate,
    strategy_tag: OutreachStrategyTag,
) -> str | None:
    job_driven = _job_driven_outreach(job)
    system_prompt = load_system_prompt("outreach_agent_v3" if job_driven else "outreach_agent_v2")
    if not system_prompt:
        return None
    candidate_detail = {
        "name": candidate.name,
        "title": candidate.title,
        "current_company": candidate.current_company,
        "email": candidate.email,
        "skills": _candidate_skills(candidate),
        "evidence": _candidate_evidence(candidate),
        "github_url": candidate.github_url,
        "source_platform": candidate.source_platform,
    }
    job_challenge = {
        "project_name": project.name,
        "job_title": job.title,
        "challenge": _outreach_challenge(project, job, candidate),
        "strategy_tag": strategy_tag,
    }
    if job_driven:
        rationale = _job_rationale(job)
        job_challenge.update(
            {
                "business_context": rationale.get("business_context"),
                "job_scope": rationale.get("job_scope"),
                "outreach_angle": rationale.get("outreach_angle"),
                "must_have_skills": list(job.must_have_skills or [])[:8],
            }
        )
    candidate_evidence = _candidate_evidence(candidate)
    tone_control = {
        "style": "硬核极客",
        "must_mention": _outreach_must_mention(project, job),
        "forbidden": list(OUTREACH_FORBIDDEN_PHRASES),
    }
    prompt = (
        f"{system_prompt}\n\n"
        "只输出邮件正文，不要 Markdown，不要解释。\n"
        f"candidate_detail:\n{json.dumps(candidate_detail, ensure_ascii=False, indent=2)}\n\n"
        f"candidate_evidence:\n{json.dumps(candidate_evidence, ensure_ascii=False, indent=2)}\n\n"
        f"job_challenge:\n{json.dumps(job_challenge, ensure_ascii=False, indent=2)}\n\n"
        f"tone_control:\n{json.dumps(tone_control, ensure_ascii=False, indent=2)}"
    )
    try:
        draft = get_router().llm().text(prompt, max_tokens=900)
    except Exception:
        return None
    draft = _clean_generated_draft(draft)
    if not draft:
        return None
    if any(phrase in draft for phrase in OUTREACH_FORBIDDEN_PHRASES):
        return None
    if candidate.name and candidate.name not in draft:
        return None
    if strategy_tag and strategy_tag not in draft:
        return None
    return draft


def _clean_generated_draft(value: str) -> str | None:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text|markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    return text if len(text) >= 80 else None


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


def _hardware_challenge_for_candidate(job: Job, candidate: Candidate) -> str:
    text = " ".join(
        [
            job.title or "",
            candidate.title or "",
            candidate.current_company or "",
            " ".join(_candidate_skills(candidate)),
            " ".join(_candidate_evidence(candidate)),
        ]
    ).lower()
    if any(keyword in text for keyword in ("ros", "slam", "nav2", "navigation", "定位", "建图", "导航")):
        return "ROS2/nav2 在复杂室内场景下的定位漂移、恢复策略和行为树稳定性"
    if any(keyword in text for keyword in ("foc", "motor", "servo", "电机", "伺服", "控制")):
        return "电机控制链路在高频通信、热漂移和负载突变下的闭环稳定性"
    if any(keyword in text for keyword in ("vla", "diffusion", "imitation", "policy", "具身", "强化学习")):
        return "端到端策略从仿真/离线数据迁移到真机后的泛化与安全边界"
    if any(keyword in text for keyword in ("嵌入式", "stm32", "firmware", "rtos", "sensor", "传感器")):
        return "嵌入式传感器、实时任务和上层算法之间的时序一致性"
    return "算法、硬件拓扑和现场交付节奏之间的系统级取舍"


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


def _industry_internal_question(domain: str, business_challenge: str) -> str:
    if domain == "供应链与履约优化":
        return (
            "在供给波动已经传导到前端排序时，策略引擎应该优先保护履约确定性，"
            "还是保留足够探索来捕捉瞬时消费意图？前者容易牺牲转化，后者会把库存噪声放大。"
        )
    if domain == "数据工程与实时特征平台":
        return (
            "实时特征到底应该追求秒级新鲜度，还是优先保证跨渠道口径一致？"
            "在羊小咩这种高频流量里，前者会引入抖动，后者又会错过短周期意图。"
        )
    if domain == "推荐排序与消费意图建模":
        return (
            "用户意图校准应该放在召回前的特征门控，还是放在排序后的策略约束？"
            "前者压缩探索空间，后者会在大促和长尾供给里放大延迟反馈。"
        )
    if domain == "AI 建模与复杂决策":
        return (
            "大模型语义理解应该直接进入在线决策，还是只作为离线策略蒸馏的教师信号？"
            "前者难控延迟和成本，后者又可能丢掉长尾消费意图。"
        )
    return (
        f"{business_challenge} 中，系统应该优先优化可解释的规则稳定性，"
        "还是让模型保留足够自由度去捕捉短周期行为漂移？这两者在真实商业流量里经常互相拉扯。"
    )


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


def _send_real_email(*, to: str, subject: str, body: str, sender_email: str | None = None) -> dict[str, Any]:
    provider = get_router().email_delivery()
    return provider.send(to=to, subject=subject, text_body=body, sender_email=sender_email, approved=True)


def _provider_status(result: dict[str, Any]) -> str:
    provider = str(result.get("provider") or "email_delivery")
    status = str(result.get("status") or "sent")
    return f"{provider}:{status}"


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


def _require_contact_compliance_unlocked(session: Session, job_id: str, candidate_id: str) -> None:
    status = _contact_compliance_status(session, job_id, candidate_id)
    if status in {"pending_compliance_review", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail=f"Candidate contact compliance status blocks outreach drafting: {status}",
        )


def _contact_compliance_status(session: Session, job_id: str, candidate_id: str) -> str | None:
    link = session.scalar(
        select(JobCandidate).where(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
    )
    return link.pipeline_status if link is not None else None


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
        created_by_user_id=draft.created_by_user_id,
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
        sender_email=history.sender_email,
        sent_by_user_id=history.sent_by_user_id,
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
