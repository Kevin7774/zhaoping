from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.core.candidate_lead_ingestion import ingest_candidate_leads
from app.core.router import ServiceRouter, get_router
from app.db.session import project_session_factory
from app.schemas.tasks import AgentEventCreate


RESUME_IMPORT_SCENARIO = "RESUME_IMPORT"


class ResumeLeadExtract(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    current_company: str | None = None
    title: str | None = None
    location: str | None = None
    email: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    homepage_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.68

    @field_validator("skills", "evidence", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list | tuple | set):
            return [str(item) for item in value if str(item or "").strip()]
        return [str(value)]


def parse_resume_file(
    file_path: str,
    *,
    router: ServiceRouter | None = None,
    document_parser_service: str | None = None,
) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")
    active_router = router or get_router()
    return active_router.document_parser(document_parser_service).parse(str(path))


def extract_resume_lead(
    markdown: str,
    *,
    source_file: str,
    router: ServiceRouter | None = None,
    llm_service: str | None = None,
) -> dict[str, Any]:
    source_path = Path(source_file)
    extracted = _extract_with_llm(markdown, router=router, llm_service=llm_service) or _heuristic_extract(markdown)
    evidence = _clean_items(extracted.evidence)
    if not evidence:
        evidence = [_excerpt(markdown, 700)]
    evidence = _clean_items([*evidence, f"来源文件：{source_path.name}"])
    skills = _clean_items(extracted.skills)
    payload: dict[str, Any] = {
        "name": _clean_text(extracted.name),
        "current_company": _clean_text(extracted.current_company),
        "title": _clean_text(extracted.title),
        "location": _clean_text(extracted.location),
        "email": _clean_text(extracted.email),
        "github_url": _clean_text(extracted.github_url),
        "linkedin_url": _clean_text(extracted.linkedin_url),
        "homepage_url": _clean_text(extracted.homepage_url),
        "source_platform": "resume_file",
        "source_url": _public_url(extracted),
        "evidence": evidence,
        "skills": skills,
        "matched_keywords": skills,
        "confidence": extracted.confidence,
        "source_file": str(source_path),
        "source_filename": source_path.name,
    }
    payload["raw_payload"] = {
        **payload,
        "markdown_preview": _excerpt(markdown, 1000),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def import_resume_to_project(
    session: Session,
    *,
    project_id: str,
    job_id: str,
    file_path: str,
    source_task_id: str,
    router: ServiceRouter | None = None,
    document_parser_service: str | None = None,
    llm_service: str | None = None,
) -> dict[str, Any]:
    markdown = parse_resume_file(file_path, router=router, document_parser_service=document_parser_service)
    lead = extract_resume_lead(markdown, source_file=file_path, router=router, llm_service=llm_service)
    result = ingest_candidate_leads(
        session,
        project_id=project_id,
        job_id=job_id,
        source_task_id=source_task_id,
        raw_leads=[lead],
    )
    result.update(
        {
            "project_id": project_id,
            "job_id": job_id,
            "file_path": file_path,
            "markdown_preview": markdown[:500],
            "lead": {
                "name": lead.get("name"),
                "email": lead.get("email"),
                "source_platform": lead.get("source_platform"),
            },
        }
    )
    return result


def run_resume_import_task(
    task_id: str,
    *,
    project_id: str,
    job_id: str,
    file_path: str,
    task_store: Any,
    session_factory: sessionmaker[Session] | None = None,
    router: ServiceRouter | None = None,
) -> dict[str, Any] | None:
    task_store.append_event(
        task_id,
        AgentEventCreate(
            type="step_start",
            agent_id="resume_ingestion",
            step_index=0,
            step_label="简历解析入库",
            message="开始解析简历并写入项目候选人库。",
            data={"project_id": project_id, "job_id": job_id, "file_path": file_path},
            status="processing",
        ),
    )
    try:
        factory = session_factory or project_session_factory()
        with factory() as session:
            result = import_resume_to_project(
                session,
                project_id=project_id,
                job_id=job_id,
                file_path=file_path,
                source_task_id=task_id,
                router=router,
            )
        task_store.update(task_id, result=result, current_step=0, current_agent=None)
        task_store.append_event(
            task_id,
            AgentEventCreate(
                type="summary",
                agent_id="resume_ingestion",
                step_index=0,
                step_label="简历解析入库",
                message=(
                    "简历入库完成："
                    f"新增 {result['inserted_candidates']}，更新 {result['updated_candidates']}，"
                    f"关联 {result['linked_job_candidates']}，拒绝 {result['rejected']}"
                ),
                data={"result": result},
                status="processing",
            ),
        )
        task_store.mark_done(task_id)
        return task_store.snapshot(task_id)
    except Exception as exc:
        task_store.set_error(
            task_id,
            "resume_ingestion",
            f"简历入库失败：{exc}",
            {"project_id": project_id, "job_id": job_id, "file_path": file_path},
        )
        return task_store.snapshot(task_id)


def start_resume_import_task(
    *,
    project_id: str,
    job_id: str,
    file_path: str,
    task_store: Any,
    session_factory: sessionmaker[Session] | None = None,
    router: ServiceRouter | None = None,
) -> dict[str, Any]:
    task = create_resume_import_task(
        project_id=project_id,
        job_id=job_id,
        file_path=file_path,
        task_store=task_store,
    )
    snapshot = run_resume_import_task(
        task["task_id"],
        project_id=project_id,
        job_id=job_id,
        file_path=file_path,
        task_store=task_store,
        session_factory=session_factory,
        router=router,
    )
    if snapshot is None:
        raise RuntimeError(f"Resume import task disappeared: {task['task_id']}")
    return snapshot


def create_resume_import_task(
    *,
    project_id: str,
    job_id: str,
    file_path: str,
    task_store: Any,
) -> dict[str, Any]:
    task = task_store.create(
        RESUME_IMPORT_SCENARIO,
        f"导入简历：{Path(file_path).name}",
        frontend_state={
            "source": "resume_local_import",
            "project_id": project_id,
            "job_id": job_id,
            "file_path": file_path,
        },
    )
    snapshot = task_store.snapshot(task.task_id)
    if snapshot is None:
        raise RuntimeError(f"Resume import task disappeared: {task.task_id}")
    return snapshot


def _extract_with_llm(
    markdown: str,
    *,
    router: ServiceRouter | None,
    llm_service: str | None,
) -> ResumeLeadExtract | None:
    active_router = router or get_router()
    prompt = _resume_extract_prompt(markdown)
    try:
        output = active_router.llm(llm_service).text(prompt, max_tokens=1200)
        return ResumeLeadExtract.model_validate(_loads_json_object(output))
    except Exception:
        return None


def _resume_extract_prompt(markdown: str) -> str:
    schema = {
        "name": "string|null",
        "current_company": "string|null",
        "title": "string|null",
        "location": "string|null",
        "email": "string|null",
        "github_url": "string|null",
        "linkedin_url": "string|null",
        "homepage_url": "string|null",
        "skills": ["string"],
        "evidence": ["string"],
        "confidence": "number 0-1",
    }
    return (
        "请从候选人简历中抽取项目入库字段。只输出合法 JSON，不要输出 Markdown 或解释。\n"
        "字段缺失时填 null 或空数组；evidence 必须是简历中的具体事实，不要泛泛总结。\n\n"
        f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Resume:\n{markdown[:8000]}"
    )


def _heuristic_extract(markdown: str) -> ResumeLeadExtract:
    lines = [line.strip(" #\t") for line in markdown.splitlines() if line.strip()]
    first_line = lines[0] if lines else None
    email_match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", markdown)
    urls = re.findall(r"https?://[^\s)>\"]+", markdown)
    skills = [keyword for keyword in _known_skill_keywords() if keyword.casefold() in markdown.casefold()]
    evidence = [line for line in lines if any(skill.casefold() in line.casefold() for skill in skills)][:4]
    return ResumeLeadExtract(
        name=first_line,
        email=email_match.group(0) if email_match else None,
        github_url=next((url for url in urls if "github.com" in url), None),
        linkedin_url=next((url for url in urls if "linkedin.com" in url), None),
        homepage_url=next((url for url in urls if "github.com" not in url and "linkedin.com" not in url), None),
        skills=skills,
        evidence=evidence,
        confidence=0.62 if first_line or email_match else 0.52,
    )


def _loads_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Resume extract output must be a JSON object.")
    return parsed


def _public_url(extracted: ResumeLeadExtract) -> str | None:
    return extracted.github_url or extracted.linkedin_url or extracted.homepage_url


def _clean_items(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text[:700])
    return cleaned[:20]


def _clean_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or None


def _excerpt(value: str, limit: int) -> str:
    text = _clean_text(value) or ""
    return text[:limit]


def _known_skill_keywords() -> tuple[str, ...]:
    return (
        "VLA",
        "Diffusion Policy",
        "robot",
        "机器人",
        "OCR",
        "RAG",
        "Agent",
        "LLM",
        "Python",
        "PyTorch",
        "数据平台",
        "实时特征",
        "推荐",
        "排序",
    )
