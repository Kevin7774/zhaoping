"""Lightweight in-memory agent orchestrator.

The orchestration logic (which agents run, in what order, where humans intervene)
lives here in the backend, not in the frontend. The frontend only listens to task
state via polling and renders whatever the backend reports.

Real capabilities come from ``app.skills.recruiting_scenarios``; this module wraps
those deterministic functions into a step-by-step, trackable, human-interruptible
task so the UI behaves like an agent runtime dashboard instead of a video player.
"""

from __future__ import annotations

import asyncio
import inspect
import importlib.util
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.candidate_lead_ingestion import (
    PERSON_SEARCH_SOURCE_KEYS,
    empty_lead_ingestion_result,
    extract_candidate_leads,
    ingest_candidate_leads,
    preview_candidate_leads,
)
from app.core.intelligence_archive import ARCHIVE_PATH_ENV, IntelligenceArchive
from app.db.session import project_session_factory
from app.db.task_models import AgentEventModel, TaskModel, make_task_session_factory
from app.models import Candidate, Job, JobCandidate, Project
from app.providers.common import RetryPolicy, call_with_retries, friendly_error
from app.core.router import get_router
from app.schemas.tasks import AgentEventCreate, AgentEventRead
from app.skills.recruiting_scenarios import (
    HOME_ROBOT_TALENT_SOURCE_MAP,
    apply_evidence_context_to_candidate_evaluation,
    build_search_keywords,
    build_talent_map,
    build_talent_map_from_job,
    evaluate_candidate,
    score_candidate_against_job,
    generate_job_profile_and_jd,
    generate_weekly_report,
    infer_role_key,
)
from app.skills.tech_space import ROBOT_ROLES_METADATA, get_capabilities_for_role


# --------------------------------------------------------------------------- #
# Agent registry: persona / icon / output format for fully dynamic UI render  #
# --------------------------------------------------------------------------- #

AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "orchestrator": {
        "name_zh": "任务编排 Agent",
        "persona": "把一句模糊的招聘需求拆解成可执行的子任务，并决定调用哪些下游 Agent。",
        "icon": "🧭",
        "output_format": "任务拆解与岗位识别",
    },
    "industry": {
        "name_zh": "行业研究 Agent",
        "persona": "扫描机器人赛道的目标公司、实验室与人才流动信号。",
        "icon": "🔭",
        "output_format": "目标公司 / 实验室列表",
    },
    "tech_route": {
        "name_zh": "技术路线 Agent",
        "persona": "把岗位拆成家庭机器人技术栈上的核心能力矩阵。",
        "icon": "🧬",
        "output_format": "能力矩阵",
    },
    "job_model": {
        "name_zh": "岗位建模 Agent",
        "persona": "产出岗位画像、JD 与面试问题。",
        "icon": "📋",
        "output_format": "岗位画像 / JD",
    },
    "talent_map": {
        "name_zh": "人才地图 Agent",
        "persona": "绘制候选人来源层级、搜索关键词与触达策略。",
        "icon": "🗺️",
        "output_format": "人才地图",
    },
    "candidate_eval": {
        "name_zh": "候选人评估 Agent",
        "persona": "把候选人材料重构成工程事实链，并模拟能力向量能否平移到当前团队卡点。",
        "icon": "🎯",
        "output_format": "事实链 / 能力频谱 / 平移推演",
    },
    "resume_design": {
        "name_zh": "履历设计 Agent",
        "persona": "围绕候选人的事实链、潜在边界和团队卡点设计苏格拉底追问。",
        "icon": "✍️",
        "output_format": "追问武器库 / 反馈信号",
    },
    "strategy": {
        "name_zh": "招聘策略 Agent",
        "persona": "综合信息制定招聘优先级、节奏与触达计划。",
        "icon": "♟️",
        "output_format": "招聘策略",
    },
    "reflection": {
        "name_zh": "反思审核 Agent",
        "persona": "对中间结论做自检，标记排除项、能力缺口和风险。",
        "icon": "🔍",
        "output_format": "反思结论",
    },
    "report": {
        "name_zh": "报告生成 Agent",
        "persona": "把所有中间结论汇总成结构化最终报告。",
        "icon": "📊",
        "output_format": "结构化报告",
    },
    "human_expert": {
        "name_zh": "人类专家 (Human-in-the-loop)",
        "persona": "在关键节点暂停流程，由人工确认、修改或拒绝后再继续。",
        "icon": "🧑‍⚖️",
        "output_format": "人工决策",
    },
}

TASK_STATUS_META: Dict[str, Dict[str, str]] = {
    "idle": {
        "name_zh": "未运行",
        "help": "选择场景后输入招聘需求即可启动。",
    },
    "processing": {
        "name_zh": "执行中",
        "help": "后端正在编排多 Agent 任务。",
    },
    "awaiting_human": {
        "name_zh": "等待人工确认",
        "help": "流程暂停，等待人工确认。",
    },
    "done": {
        "name_zh": "已完成",
        "help": "最终结构化报告已生成。",
    },
    "error": {
        "name_zh": "已终止",
        "help": "流程异常终止，请查看错误信息。",
    },
    "cancelled": {
        "name_zh": "已取消",
        "help": "任务已取消，审计事件已落库。",
    },
}


# --------------------------------------------------------------------------- #
# Step + scenario plan definitions (the orchestration logic, in the backend)  #
# --------------------------------------------------------------------------- #


@dataclass
class Step:
    agent_id: str
    label: str
    message: str
    kind: str  # compute | reflect | hitl | finalize
    handler: Optional[Callable[[Dict[str, Any]], Any]] = None


LIVE_RECRUITING_SEARCH_SERVICES = (
    "openalex_works_search",
    "openalex_authors_search",
    "openalex_institutions_search",
    "semantic_scholar_papers_search",
    "github_candidates",
    "github_users",
    "github_repositories",
    "github_code",
    "github_topics",
    "huggingface_models",
    "brave_web_search",
    "agent_reach_social_search",
    "gnews_funding_news",
    "education_competition_monitor",
)
MAX_LIVE_RECRUITING_PROVIDERS = 14
MAX_DEEP_LIVE_PROVIDERS = 36

LIVE_RESULT_SOURCE_KEYS = {
    *LIVE_RECRUITING_SEARCH_SERVICES,
}

DEFAULT_SEARCH_PROFILE = "candidate_sourcing"
DEFAULT_EXECUTION_POLICY = "bounded_live"

SEARCH_PROFILE_METADATA: dict[str, dict[str, str]] = {
    "candidate_sourcing": {
        "label": "找候选人",
        "description": "围绕岗位画像叠加技术、人脉、社媒、新闻和学校竞赛线索。",
    },
    "due_diligence": {
        "label": "尽调深搜",
        "description": "在候选人搜索基础上叠加公司、监管、专利、诉讼和合规信号。",
    },
}

SEARCH_EXECUTION_POLICY_METADATA: dict[str, dict[str, Any]] = {
    "bounded_live": {
        "label": "标准联网",
        "external_request_policy": "bounded_live",
        "budget": {"max_providers": MAX_LIVE_RECRUITING_PROVIDERS, "per_provider_limit": 3, "timeout_seconds": 10, "max_crawl_pages": 0},
    },
    "deep_live": {
        "label": "深度联网",
        "external_request_policy": "deep_live",
        "budget": {"max_providers": MAX_DEEP_LIVE_PROVIDERS, "per_provider_limit": 4, "timeout_seconds": 18, "max_crawl_pages": 3},
    },
}

SEARCH_SOURCE_LAYER_METADATA: dict[str, dict[str, Any]] = {
    "live_web": {
        "label": "开放网页",
        "services": ("brave_web_search",),
    },
    "academic": {
        "label": "学术论文/机构",
        "services": (
            "openalex_works_search",
            "openalex_authors_search",
            "openalex_institutions_search",
            "semantic_scholar_papers_search",
        ),
    },
    "code_model": {
        "label": "代码/模型",
        "services": (
            "github_candidates",
            "github_repositories",
            "github_code",
            "github_topics",
            "github_users",
            "huggingface_models",
        ),
    },
    "social": {
        "label": "社媒/社区",
        "services": ("agent_reach_social_search",),
    },
    "platform_search": {
        "label": "授权平台搜索",
        "services": ("opencli_platform_search",),
    },
    "news_funding": {
        "label": "新闻/融资",
        "services": ("gnews_funding_news",),
    },
    "education_competition": {
        "label": "学校/竞赛",
        "services": ("education_competition_monitor",),
    },
    "crawler_snapshot": {
        "label": "网页抓取/快照",
        "services": ("opencli_web_read_search",),
    },
    "due_diligence": {
        "label": "公司/合规尽调",
        "services": (
            "sec_edgar_company_filings",
            "sec_company_facts",
            "sec_insider_transactions",
            "sec_ownership_activism",
            "sec_investment_adviser_reports",
            "federal_register_documents",
            "cpsc_recalls",
            "fda_enforcement_recalls",
            "sec_enforcement_search",
        ),
    },
    "financial_regulatory": {
        "label": "金融/投诉",
        "services": ("fdic_bankfind_institutions", "cfpb_consumer_complaints"),
    },
    "healthcare_regulatory": {
        "label": "医疗/FDA",
        "services": (
            "fda_device_510k",
            "fda_device_events",
            "fda_device_classification",
            "fda_device_registration_listing",
            "clinicaltrials_studies",
        ),
    },
    "safety_environment": {
        "label": "安全/环境",
        "services": ("nhtsa_recalls", "epa_echo_facilities"),
    },
    "public_funding": {
        "label": "政府资金",
        "services": ("usaspending_awards", "grants_gov_opportunities"),
    },
}

SERVICE_SOURCE_LAYER_INDEX: dict[str, str] = {
    str(service): layer_name
    for layer_name, layer in SEARCH_SOURCE_LAYER_METADATA.items()
    for service in layer.get("services", ())
}

SEARCH_PROFILE_DEFAULT_LAYERS: dict[str, tuple[str, ...]] = {
    "candidate_sourcing": (
        "live_web",
        "academic",
        "code_model",
        "social",
        "news_funding",
        "education_competition",
    ),
    "due_diligence": (
        "live_web",
        "academic",
        "code_model",
        "social",
        "news_funding",
        "education_competition",
        "due_diligence",
        "financial_regulatory",
        "healthcare_regulatory",
        "safety_environment",
        "public_funding",
    ),
}

SEARCH_SOURCE_LAYER_ALIASES = {
    "codeModel": "code_model",
    "peopleDatabase": "people_database",
    "newsFunding": "news_funding",
    "educationCompetition": "education_competition",
    "crawlerSnapshot": "crawler_snapshot",
    "dueDiligence": "due_diligence",
    "platformSearch": "platform_search",
    "financialRegulatory": "financial_regulatory",
    "healthcareRegulatory": "healthcare_regulatory",
    "safetyEnvironment": "safety_environment",
    "publicFunding": "public_funding",
    "liveWeb": "live_web",
}

TOP_DOWN_RESEARCH_LAYERS = (
    {
        "id": "market_map",
        "name_zh": "行业/市场地图",
        "purpose": "先确认公司、融资、招聘需求和市场变化，避免直接从单个候选人猜方向。",
        "services": ("brave_web_search", "gnews_funding_news"),
    },
    {
        "id": "technical_evidence",
        "name_zh": "技术证据",
        "purpose": "用论文、代码、模型和机构证据验证岗位能力是不是赛道真实需求。",
        "services": (
            "openalex_works_search",
            "github_candidates",
            "github_users",
            "github_repositories",
            "github_code",
            "github_topics",
            "huggingface_models",
        ),
    },
    {
        "id": "people_network",
        "name_zh": "人才网络",
        "purpose": "从人员库、作者网络和开源/社媒身份定位可触达候选人。",
        "services": (
            "openalex_authors_search",
            "github_candidates",
            "github_users",
            "github_repositories",
            "agent_reach_social_search",
        ),
    },
    {
        "id": "social_signal",
        "name_zh": "社媒/社区信号",
        "purpose": "补充微博、B站、知乎、V2EX 等社区里的近期项目、Demo 和流动信号。",
        "services": ("agent_reach_social_search",),
    },
    {
        "id": "school_competition",
        "name_zh": "学校/竞赛源",
        "purpose": "从高校实验室、竞赛和排行榜发现早期高潜人才与导师网络。",
        "services": ("openalex_institutions_search", "education_competition_monitor"),
    },
)

LIVE_ROLE_QUERY_OVERRIDES = {
    "vla_embodied_expert": "robotics diffusion policy vision language action robot manipulation",
    "slam_navigation_expert": "robot SLAM navigation mapping localization",
    "dexterous_hand_control": "dexterous hand tactile manipulation robotics",
    "motion_control_mpc_wbc": "humanoid robot MPC WBC whole body control locomotion",
    "robot_data_infrastructure": "robotics teleoperation data collection imitation learning",
    "embedded_foc_engineer": "robot motor control FOC embedded firmware",
    "qa_reliability_engineer": "robot reliability testing hardware validation",
    "manipulation_grasping": "robot manipulation grasping policy planning",
    "vision_3d_algorithm": "robot 3D vision RGB-D pose estimation reconstruction",
    "multimodal_perception": "robot multimodal perception VLM grounding",
    "world_model_simulation": "robot world model simulation synthetic data",
    "robot_system_architect": "robot system architecture hardware software integration",
}

ENTITY_TEXT_FIELDS = ("title", "snippet")
STRUCTURED_COMPANY_FIELDS = ("company", "company_name", "companies", "assignees", "awardee_name")
STRUCTURED_LAB_FIELDS = ("institution", "institutions", "affiliation", "affiliations", "lab", "labs")
HANDLE_ENTITY_FIELDS = ("owner_login", "author")
GENERIC_ENTITY_NAMES = {
    "AI",
    "VLA",
    "Robot",
    "Robotics",
    "Robot VLA",
    "Robot Foundation Model",
    "Diffusion Policy",
    "GitHub",
    "Hugging Face",
    "OpenAlex",
    "Brave Search",
    "家庭机器人",
    "人形机器人",
    "具身智能",
    "机器人基础模型",
    "机器人算法",
    "大模型",
}
DOMAIN_ENTITY_EXCLUDE = {
    "github",
    "huggingface",
    "openalex",
    "arxiv",
    "ieee",
    "acm",
    "nature",
    "science",
    "reuters",
    "bloomberg",
    "forbes",
    "techcrunch",
    "theverge",
    "therobotreport",
    "globenewswire",
    "prnewswire",
    "medium",
    "linkedin",
    "youtube",
    "wikipedia",
}
ENGLISH_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.+-]*|[0-9]+X|[A-Z]{2,})"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&.+-]*|AI|ML|XR|Robotics|Robot|Labs?|Technologies|Tech|Intelligence|Dynamics|Systems|Research|Institute|University|CSAIL|BAIR|IRIS)){0,5}"
    r"\s+(?:AI|Robotics|Labs?|Technologies|Tech|Intelligence|Dynamics|Systems|Research|Institute|University|CSAIL|BAIR|IRIS)\b"
)
CHINESE_ENTITY_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9·（）()]{2,30}"
    r"(?:机器人|科技|智能|动力|感知|通用|大模型|实验室|研究院|大学|学院|中心|团队)"
)


def _calibrated_target_sources(
    role_key: str,
    intelligence: Dict[str, Any],
    seed_sources: Dict[str, List[str]] | None = None,
) -> Dict[str, Any]:
    """Promote live company/lab signals into the main target-source output.

    Static scenario sources are seeds only. They remain visible for audit/fallback,
    but live entities take over the primary lists once the search layer returns
    usable organization or lab signals. When the task carries a project job
    profile, its target companies replace the home-robot seed lists.
    """

    if seed_sources is not None:
        seed_companies = list(seed_sources.get("目标公司") or [])
        seed_secondary = list(seed_sources.get("次优来源公司") or [])
        seed_labs = list(seed_sources.get("高校实验室") or [])
    else:
        source_map = HOME_ROBOT_TALENT_SOURCE_MAP.get(role_key, {})
        seed_companies = list(source_map.get("priority_sources", ROBOT_ROLES_METADATA[role_key]["target_targets"]))
        seed_secondary = list(source_map.get("secondary_sources", []))
        seed_labs = list(source_map.get("labs", []))

    dynamic_entities = _extract_dynamic_source_entities(intelligence)
    dynamic_companies = [
        item["name"]
        for item in dynamic_entities
        if item["entity_type"] == "company" and item["score"] >= 2
    ]
    dynamic_labs = [
        item["name"]
        for item in dynamic_entities
        if item["entity_type"] == "lab" and item["score"] >= 2
    ]
    dynamic_teams = [
        item["name"]
        for item in dynamic_entities
        if item["entity_type"] == "team" and item["score"] >= 2
    ]

    live_result_count = ((intelligence.get("实时检索") or {}).get("result_count") or 0)
    has_dynamic_targets = bool(dynamic_companies or dynamic_labs or dynamic_teams)
    return {
        "目标公司": _merge_unique(dynamic_companies),
        "高校实验室": _merge_unique(dynamic_labs),
        "次优来源公司": _merge_unique(dynamic_teams),
        "动态目标公司": _merge_unique(dynamic_companies),
        "动态实验室": _merge_unique(dynamic_labs),
        "动态团队": _merge_unique(dynamic_teams),
        "动态目标线索": dynamic_entities[:12],
        "静态种子": {
            "目标公司": seed_companies,
            "次优来源公司": seed_secondary,
            "高校实验室": seed_labs,
        },
        "校准状态": {
            "status": "live_calibrated" if has_dynamic_targets else "static_fallback_no_entity_hits",
            "live_result_count": live_result_count,
            "dynamic_entity_count": len(dynamic_entities),
            "说明": (
                "已用实时检索实体替换主目标列表，静态来源仅作为审计兜底。"
                if has_dynamic_targets
                else "实时检索未抽取到可用公司/实验室实体，主目标列表保持为空；静态种子仅作为下一轮检索起点，不作为目标名单。"
            ),
        },
    }


def _extract_dynamic_source_entities(intelligence: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    live = intelligence.get("实时检索") or {}
    for result in live.get("results", []):
        if not isinstance(result, dict):
            continue
        source_key = str(result.get("source_key") or "unknown")
        source_name = result.get("source_name")
        title = str(result.get("title") or "")
        url = result.get("url")

        for field_name in STRUCTURED_COMPANY_FIELDS:
            for raw in _values_from_result(result.get(field_name)):
                _add_entity_candidate(candidates, raw, "company", 3, source_key, field_name, title, url)
        for field_name in STRUCTURED_LAB_FIELDS:
            for raw in _values_from_result(result.get(field_name)):
                _add_entity_candidate(candidates, raw, "lab", 3, source_key, field_name, title, url)
        for field_name in HANDLE_ENTITY_FIELDS:
            for raw in _values_from_result(result.get(field_name)):
                entity_name = _humanize_org_handle(raw)
                if entity_name:
                    score = 2 if result.get("owner_type") == "Organization" else 1
                    _add_entity_candidate(candidates, entity_name, None, score, source_key, field_name, title, url)
        for field_name in ENTITY_TEXT_FIELDS:
            for entity_name in _extract_entities_from_text(str(result.get(field_name) or "")):
                _add_entity_candidate(candidates, entity_name, None, 2, source_key, field_name, title, url)

        domain_entity = _entity_from_result_url(str(url or ""), source_key)
        if domain_entity:
            _add_entity_candidate(candidates, domain_entity, None, 1, source_key, "url_domain", title or str(source_name or ""), url)

    entities = []
    for item in candidates.values():
        evidence = item["evidence"][:3]
        source_keys = sorted(item["source_keys"])
        score = int(item["score"])
        entities.append(
            {
                "name": item["name"],
                "entity_type": item["entity_type"],
                "score": score,
                "confidence": min(0.95, round(0.42 + score * 0.08 + len(source_keys) * 0.04, 2)),
                "source_keys": source_keys,
                "evidence": evidence,
            }
        )
    return sorted(entities, key=lambda item: (-item["score"], item["name"]))[:20]


def _values_from_result(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item]
    return [value]


def _extract_entities_from_text(text: str) -> List[str]:
    if not text:
        return []
    scrubbed = re.sub(r"https?://\S+", " ", text)
    entities = [match.group(0) for match in ENGLISH_ENTITY_RE.finditer(scrubbed)]
    entities.extend(match.group(0) for match in CHINESE_ENTITY_RE.finditer(scrubbed))
    return entities


def _add_entity_candidate(
    candidates: dict[str, dict[str, Any]],
    raw_name: Any,
    entity_type: str | None,
    score: int,
    source_key: str,
    reason: str,
    title: str,
    url: Any,
) -> None:
    name = _clean_entity_name(raw_name)
    if not name:
        return
    normalized = _entity_key(name)
    if normalized in {item.casefold() for item in GENERIC_ENTITY_NAMES}:
        return
    inferred_type = entity_type or _classify_entity_type(name)
    item = candidates.setdefault(
        normalized,
        {
            "name": name,
            "entity_type": inferred_type,
            "score": 0,
            "source_keys": set(),
            "evidence": [],
        },
    )
    if item["entity_type"] == "company" and inferred_type in {"lab", "team"}:
        item["entity_type"] = inferred_type
    item["score"] += max(1, score)
    item["source_keys"].add(source_key)
    item["evidence"].append(
        {
            "source_key": source_key,
            "reason": reason,
            "title": title,
            "url": str(url or ""),
        }
    )


def _clean_entity_name(raw_name: Any) -> str:
    name = str(raw_name or "").strip()
    if "/" in name and "北大/清华" not in name:
        name = name.split("/")[0].strip()
    name = re.sub(r"[_-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" \t\r\n-_|:：,，.。()（）[]【】'\"")
    name = re.sub(r"\b(?:Inc\.?|Corp\.?|Corporation|Ltd\.?|Limited|LLC|Co\.?)$", "", name).strip()
    name = re.sub(r"(?:股份)?有限公司$", "", name).strip()
    if len(name) < 2 or len(name) > 48:
        return ""
    if name in GENERIC_ENTITY_NAMES:
        return ""
    if name.casefold() in {item.casefold() for item in GENERIC_ENTITY_NAMES}:
        return ""
    if len(name.split()) > 6:
        return ""
    if re.fullmatch(r"[a-z0-9_.-]+", name) and len(name) < 4:
        return ""
    return name


def _entity_key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def _classify_entity_type(name: str) -> str:
    lower = name.casefold()
    academic_markers = (
        "university",
        "stanford",
        "berkeley",
        "mit ",
        "cmu",
        "eth ",
        "caltech",
        "harvard",
        "csail",
        "bair",
        "iris",
        "大学",
        "高校",
        "学院",
        "实验室",
        "北大",
        "清华",
        "浙大",
        "上交",
        "上海交大",
    )
    team_markers = ("team", "research", "institute", "团队", "研究院", "研究所", "组")
    if any(marker in lower or marker in name for marker in academic_markers):
        return "lab"
    if any(marker in lower or marker in name for marker in team_markers):
        return "team"
    return "company"


def _humanize_org_handle(raw_name: Any) -> str:
    handle = str(raw_name or "").strip()
    if not handle or handle.casefold() in {"none", "null", "unknown"}:
        return ""
    handle = handle.split("/")[0]
    if not re.search(r"[A-Za-z]", handle):
        return ""
    words = [word for word in re.split(r"[-_\s]+", handle) if word]
    if not words:
        return ""
    if len(words) == 1 and len(words[0]) < 4:
        return ""
    return " ".join(word.upper() if word.casefold() in {"ai", "ml", "pi", "1x"} else word.title() for word in words)


def _entity_from_result_url(url: str, source_key: str) -> str:
    if not url or source_key != "brave_web_search":
        return ""
    host = urlparse(url).netloc.casefold()
    host = host.removeprefix("www.")
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) < 2:
        return ""
    base = labels[-2]
    if base in DOMAIN_ENTITY_EXCLUDE or len(base) < 4:
        return ""
    return _humanize_org_handle(base)


def _merge_unique(*items: List[str]) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for values in items:
        for value in values:
            cleaned = _clean_entity_name(value)
            if not cleaned:
                continue
            key = _entity_key(cleaned)
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return merged


def _apply_calibrated_targets_to_job_profile(result: Dict[str, Any], targets: Dict[str, Any]) -> None:
    sources = result.setdefault("候选人来源", {})
    sources["公司"] = targets["目标公司"]
    sources["实验室"] = targets["高校实验室"]
    sources["动态目标公司"] = targets["动态目标公司"]
    sources["动态实验室"] = targets["动态实验室"]
    sources["动态目标线索"] = targets["动态目标线索"]
    sources["静态种子"] = targets["静态种子"]
    sources["校准状态"] = targets["校准状态"]


def _apply_calibrated_targets_to_talent_map(result: Dict[str, Any], targets: Dict[str, Any]) -> None:
    target_companies = targets["目标公司"]
    labs = targets["高校实验室"]
    secondary = targets["次优来源公司"]
    result["目标公司"] = target_companies
    result["目标团队"] = _merge_unique(labs, secondary)
    result["优先来源公司"] = target_companies
    result["次优来源公司"] = secondary
    result["高校/实验室"] = labs
    result["动态目标公司"] = targets["动态目标公司"]
    result["动态实验室"] = targets["动态实验室"]
    result["动态目标线索"] = targets["动态目标线索"]
    result["静态种子"] = targets["静态种子"]
    result["校准状态"] = targets["校准状态"]
    candidate_sources = result.setdefault("候选人来源", {})
    candidate_sources["优先来源公司"] = target_companies
    candidate_sources["次优来源公司"] = secondary
    candidate_sources["高校/实验室"] = labs
    candidate_sources["动态目标公司"] = targets["动态目标公司"]
    candidate_sources["动态实验室"] = targets["动态实验室"]
    candidate_sources["动态目标线索"] = targets["动态目标线索"]
    candidate_sources["静态种子"] = targets["静态种子"]
    candidate_sources["校准状态"] = targets["校准状态"]


# ---- Scenario A: job profile & JD ----------------------------------------- #


def _a_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    job_profile = _job_profile_for_sourcing(ctx)
    if job_profile is not None:
        ctx["log"] = f"已拆解招聘需求，目标岗位为项目岗位「{job_profile['title']}」"
        return {"role_key": role_key, "岗位": job_profile["title"], "岗位来源": "project_job_profile"}
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已拆解招聘需求，目标岗位识别为「{role['name_zh']}」"
    return {"role_key": role_key, "岗位": role["name_zh"], "技术层": role["tech_layer"]}


def _a_industry(ctx: Dict[str, Any]) -> Any:
    role_key = ctx["role_key"]
    intelligence = _source_intelligence_with_audit(ctx["input"], role_key, ctx=ctx, agent_id="industry")
    ctx["data"]["industry_intelligence"] = intelligence
    targets = _calibrated_target_sources(role_key, intelligence, seed_sources=_job_seed_sources(_job_profile_for_sourcing(ctx)))
    ctx["data"]["calibrated_targets"] = targets
    companies = targets["目标公司"]
    labs = targets["高校实验室"]
    ctx["log"] = (
        f"检索到 {len(companies)} 家优先目标公司、{len(labs)} 个高校实验室，"
        f"覆盖 {len(intelligence['推荐信源'])} 类搜索信源，"
        f"校准状态：{targets['校准状态']['status']}"
    )
    return {
        "目标公司": companies,
        "高校实验室": labs,
        "动态目标公司": targets["动态目标公司"],
        "动态实验室": targets["动态实验室"],
        "动态目标线索": targets["动态目标线索"],
        "静态种子": targets["静态种子"],
        "校准状态": targets["校准状态"],
        "推荐信源": intelligence["推荐信源"],
        "证据记录": intelligence["证据记录"],
        "实时检索": intelligence["实时检索"],
        "检索说明": intelligence["检索说明"],
    }


def _a_tech(ctx: Dict[str, Any]) -> Any:
    caps = get_capabilities_for_role(ctx["role_key"])
    names = [c["capability_name_zh"] for c in caps]
    ctx["log"] = f"拆解出 {len(names)} 项核心能力要求"
    return {"能力矩阵": names}


def _a_job_model(ctx: Dict[str, Any]) -> Any:
    result = generate_job_profile_and_jd(ctx["input"])
    if ctx["data"].get("industry_intelligence"):
        result["行业搜索证据"] = ctx["data"]["industry_intelligence"]
    if ctx["data"].get("calibrated_targets"):
        _apply_calibrated_targets_to_job_profile(result, ctx["data"]["calibrated_targets"])
    ctx["data"]["job_profile"] = result
    ctx["log"] = "已生成岗位画像、JD 与面试问题草稿"
    return {"岗位定位": result["岗位定位"], "JD职责": result["JD"]["职责"]}


def _a_reflect(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["job_profile"]
    exclusions = result["能力矩阵"]["排除项"]
    notes = [f"面试中需规避：{x}" for x in exclusions]
    ctx["data"]["reflection"] = notes
    ctx["log"] = f"反思完成，标记 {len(notes)} 条排除项风险"
    return {"反思结论": notes}


def _a_hitl(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["job_profile"]
    return {
        "prompt": "请确认岗位定位与面试问题，可直接通过，或填写修改意见后继续。",
        "draft": {
            "岗位定位": result["岗位定位"],
            "面试问题": result["面试问题"],
        },
    }


def _a_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["job_profile"])
    result["反思结论"] = ctx["data"].get("reflection", [])
    if ctx["data"].get("industry_intelligence"):
        result["行业搜索证据"] = ctx["data"]["industry_intelligence"]
    _apply_human_edits(ctx, result)
    _attach_human_report(ctx, result)
    ctx["log"] = "已汇总生成最终岗位画像报告"
    return result


# ---- Scenario B: talent map ----------------------------------------------- #


def _b_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    job_profile = _job_profile_for_sourcing(ctx)
    if job_profile is not None:
        ctx["log"] = f"已加载项目岗位「{job_profile['title']}」，准备绘制人才地图"
        return {"role_key": role_key, "岗位": job_profile["title"], "岗位来源": "project_job_profile"}
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已识别目标方向「{role['name_zh']}」，准备绘制人才地图"
    return {"role_key": role_key, "岗位": role["name_zh"]}


def _b_map(ctx: Dict[str, Any]) -> Any:
    job_profile = _job_profile_for_sourcing(ctx)
    result = build_talent_map_from_job(job_profile) if job_profile is not None else build_talent_map(ctx["input"])
    intelligence = _source_intelligence_with_audit(ctx["input"], ctx["role_key"], ctx=ctx, agent_id="talent_map")
    targets = _calibrated_target_sources(ctx["role_key"], intelligence, seed_sources=_job_seed_sources(job_profile))
    _apply_calibrated_targets_to_talent_map(result, targets)
    ctx["data"]["talent_map"] = result
    ctx["data"]["industry_intelligence"] = intelligence
    ctx["data"]["calibrated_targets"] = targets
    ctx["log"] = (
        f"已绘制人才地图，覆盖 {len(result['目标公司'])} 家目标公司、"
        f"{len(intelligence['推荐信源'])} 类搜索信源，"
        f"校准状态：{targets['校准状态']['status']}"
    )
    return {
        "目标公司": result["目标公司"],
        "目标团队": result["目标团队"],
        "搜索关键词": result["搜索关键词"][:12],
        "动态目标公司": targets["动态目标公司"],
        "动态实验室": targets["动态实验室"],
        "动态目标线索": targets["动态目标线索"],
        "静态种子": targets["静态种子"],
        "校准状态": targets["校准状态"],
        "推荐信源": intelligence["推荐信源"],
        "证据记录": intelligence["证据记录"],
        "实时检索": intelligence["实时检索"],
        "研究框架": intelligence.get("研究框架", {}),
        "检索说明": intelligence["检索说明"],
    }


def _b_strategy(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["talent_map"]
    intelligence = ctx["data"].get("industry_intelligence", {})
    strategy = {
        "优先来源": result["候选人来源"]["优先来源公司"],
        "次优来源": result["候选人来源"]["次优来源公司"],
        "触达话术": result["触达策略"],
        "搜索证据摘要": _evidence_summary(intelligence),
    }
    ctx["data"]["strategy"] = strategy
    ctx["log"] = "已制定分层触达策略"
    return strategy


def _b_hitl(ctx: Dict[str, Any]) -> Any:
    lead_preview = _preview_scenario_b_candidate_leads(ctx)
    return {
        "prompt": "请确认目标公司与触达策略，可通过或填写调整意见。",
        "draft": ctx["data"]["strategy"],
        "requires_lead_preview": True,
        "lead_preview": lead_preview,
    }


def _b_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["talent_map"])
    result["招聘策略"] = ctx["data"].get("strategy", {})
    if ctx["data"].get("industry_intelligence"):
        result["搜索证据"] = ctx["data"]["industry_intelligence"]
    _apply_human_edits(ctx, result)
    ingestion = _ingest_scenario_b_candidate_leads(ctx, result)
    diagnostics = _scenario_b_lead_diagnostics(ctx, ingestion)
    if diagnostics:
        ingestion["diagnostics"] = diagnostics
    result["lead_ingestion"] = ingestion
    _attach_human_report(ctx, result)
    _emit_audit_event(
        ctx,
        "evidence",
        "talent_map",
        (
            "候选人线索入库完成："
            f"发现 {ingestion['found']}，新增 {ingestion['inserted_candidates']}，"
            f"更新 {ingestion['updated_candidates']}，关联 {ingestion['linked_job_candidates']}，"
            f"去重 {ingestion['duplicates']}，拒绝 {ingestion['rejected']}"
        ),
        {"lead_ingestion": ingestion},
    )
    if diagnostics:
        _emit_audit_event(
            ctx,
            "error",
            "talent_map",
            f"警告：人才地图工作流未发现可入库候选人线索（{diagnostics['原因']}）",
            {"lead_ingestion_diagnostics": diagnostics},
        )
    ctx["log"] = (
        "已汇总生成最终人才地图报告；"
        f"候选人入库新增 {ingestion['inserted_candidates']} 人，"
        f"关联岗位 {ingestion['linked_job_candidates']} 条"
        + ("（警告：本轮实时检索未产出可入库线索，详见 lead_ingestion.diagnostics）" if diagnostics else "")
    )
    return result


def _scenario_b_lead_diagnostics(ctx: Dict[str, Any], ingestion: Dict[str, Any]) -> Dict[str, Any] | None:
    """Explain why the talent-map workflow produced no ingestible leads.

    found=0 must never be silent: the run looks successful while the final
    candidate list ends up sourced entirely by the fallback provider sweep."""

    if int(ingestion.get("found") or 0) > 0:
        return None
    intelligence = ctx["data"].get("industry_intelligence") or {}
    live = intelligence.get("实时检索") if isinstance(intelligence, dict) else {}
    live = live if isinstance(live, dict) else {}
    live_results = [item for item in live.get("results") or [] if isinstance(item, dict)]
    person_results = [
        item
        for item in live_results
        if str(item.get("source_key") or "") in PERSON_SEARCH_SOURCE_KEYS
    ]
    if not live_results:
        reason = "实时检索没有返回任何结果"
    elif not person_results:
        reason = "实时检索结果中没有人选类信源（github_candidates/github_users/openalex_authors/semantic_scholar_authors）命中"
    else:
        reason = "实时检索有人选类结果，但全部被线索抽取过滤，请检查结果字段结构"
    return {
        "原因": reason,
        "live_result_count": int(live.get("result_count") or 0),
        "live_services": list(live.get("services") or []),
        "person_source_result_count": len(person_results),
        "provider_errors": list(live.get("errors") or [])[:10],
        "rejected_reasons": dict(ingestion.get("rejected_reasons") or {}),
    }


def _ingest_scenario_b_candidate_leads(ctx: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(ctx.get("task_id") or "")
    target = _project_sourcing_target(ctx.get("frontend_state"))
    if target is None:
        return empty_lead_ingestion_result(task_id, "project_id/job_id not provided")
    project_id, job_id = target
    raw_leads = extract_candidate_leads(result)
    with project_session_factory()() as session:
        return ingest_candidate_leads(
            session,
            project_id=project_id,
            job_id=job_id,
            source_task_id=task_id,
            raw_leads=raw_leads,
        )


def _preview_scenario_b_candidate_leads(ctx: Dict[str, Any]) -> Dict[str, Any]:
    target = _project_sourcing_target(ctx.get("frontend_state"))
    if target is None:
        return {
            "total_count": 0,
            "omitted_count": 0,
            "leads": [],
            "rejected_reasons": {"project_id/job_id not provided": 1},
        }
    project_id, job_id = target
    preview_source = dict(ctx["data"].get("talent_map") or {})
    if ctx["data"].get("industry_intelligence"):
        preview_source["搜索证据"] = ctx["data"]["industry_intelligence"]
    raw_leads = extract_candidate_leads(preview_source)
    with project_session_factory()() as session:
        preview = preview_candidate_leads(
            session,
            project_id=project_id,
            job_id=job_id,
            raw_leads=raw_leads,
            limit=5,
        )
    search_trace = _lead_search_trace(preview_source)
    if search_trace:
        preview["search_trace"] = search_trace
    return preview


def _lead_search_trace(source: Dict[str, Any]) -> Dict[str, Any] | None:
    intelligence = source.get("搜索证据") if isinstance(source, dict) else None
    if not isinstance(intelligence, dict):
        return None
    live = intelligence.get("实时检索")
    if not isinstance(live, dict):
        return None
    services = [str(service) for service in live.get("services", []) if service]
    errors = [dict(error) for error in live.get("errors", []) if isinstance(error, dict)]
    layers = [
        {
            "id": str(layer.get("id") or ""),
            "name_zh": str(layer.get("name_zh") or layer.get("name") or ""),
            "purpose": str(layer.get("purpose") or ""),
            "services": [str(service) for service in layer.get("services", []) if service],
            "result_count": int(layer.get("result_count") or 0),
            "error_count": int(layer.get("error_count") or 0),
        }
        for layer in live.get("research_layers", [])
        if isinstance(layer, dict)
    ]
    return {
        "query": str(live.get("query") or intelligence.get("query") or ""),
        "services": services,
        "result_count": int(live.get("result_count") or 0),
        "errors": errors,
        "research_layers": layers,
    }


def _project_sourcing_target(frontend_state: Optional[Dict[str, Any]]) -> tuple[str, str] | None:
    project_id = _frontend_state_value(frontend_state, "project_id", "projectId")
    job_id = _frontend_state_value(frontend_state, "job_id", "jobId", "job_profile_id", "jobProfileId", "jobProfileID")
    if project_id and job_id:
        return project_id, job_id
    return None


def _job_profile_for_sourcing(ctx: Dict[str, Any]) -> Dict[str, Any] | None:
    """Load the project job profile referenced by the task's frontend_state.

    Returns None for legacy free-text runs without project/job context, or when
    the job cannot be read; callers then fall back to the static role metadata.
    """

    if "sourcing_job_profile" in ctx:
        return ctx["sourcing_job_profile"]
    profile: Dict[str, Any] | None = None
    target = _project_sourcing_target(ctx.get("frontend_state"))
    if target is not None:
        project_id, job_id = target
        try:
            with project_session_factory()() as session:
                job = session.get(Job, job_id)
                if job is not None and job.project_id == project_id:
                    profile = {
                        "id": job.id,
                        "title": job.title,
                        "seniority": job.seniority,
                        "responsibilities": job.responsibilities or [],
                        "must_have_skills": job.must_have_skills or [],
                        "nice_to_have_skills": job.nice_to_have_skills or [],
                        "target_companies": job.target_companies or [],
                        "exclusion_signals": job.exclusion_signals or [],
                        "search_strategy": job.search_strategy or {},
                        "rationale": job.rationale or {},
                        "scoring_rubric": job.scoring_rubric or {},
                        "interview_questions": job.interview_questions or [],
                    }
        except Exception:  # noqa: BLE001 - job context is best-effort enrichment.
            profile = None
    ctx["sourcing_job_profile"] = profile
    return profile


def _job_seed_sources(job_profile: Dict[str, Any] | None) -> Dict[str, List[str]] | None:
    if job_profile is None:
        return None
    return {
        "目标公司": [str(item) for item in job_profile.get("target_companies") or []],
        "次优来源公司": [],
        "高校实验室": [],
    }


# ---- Scenario C: candidate evaluation ------------------------------------- #


def _c_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    job_profile = _job_profile_for_sourcing(ctx)
    if job_profile is not None:
        ctx["log"] = f"已解析候选人材料，对标项目岗位「{job_profile['title']}」"
        return {"对标岗位": job_profile["title"], "岗位来源": "project_job_profile"}
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已解析候选人材料，对标岗位「{role['name_zh']}」"
    return {"对标岗位": role["name_zh"]}


def _job_profile_match(job_profile: Dict[str, Any], candidate_material: str) -> Dict[str, Any]:
    """Deterministic per-job match detail: which of the job's own requirements
    the candidate material covers, misses, or trips as a risk signal."""

    text = candidate_material.lower()

    def _hits(items: Any) -> tuple[list[str], list[str]]:
        cleaned = [str(item).strip() for item in items or [] if str(item).strip()]
        matched = [item for item in cleaned if item.lower() in text]
        missing = [item for item in cleaned if item.lower() not in text]
        return matched, missing

    matched_skills, missing_skills = _hits(job_profile.get("must_have_skills"))
    rationale = job_profile.get("rationale") if isinstance(job_profile.get("rationale"), dict) else {}
    matched_signals, _ = _hits((rationale or {}).get("must_have_signals"))
    risk_hits, _ = _hits((rationale or {}).get("risk_signals"))
    total = len(matched_skills) + len(missing_skills)
    return {
        "岗位": job_profile.get("title"),
        "必备技能命中": matched_skills,
        "必备技能缺口": missing_skills,
        "加分信号命中": matched_signals,
        "风险信号命中": risk_hits,
        "技能覆盖率": round(len(matched_skills) / total, 2) if total else None,
        "说明": "命中基于候选人材料的关键词证据，仅作为初筛参考；最终判断以追问和人工评估为准。",
    }


def _c_eval(ctx: Dict[str, Any]) -> Any:
    result = evaluate_candidate(
        ctx["input"],
        team_constraint=ctx.get("team_constraint"),
        aperture_weight=ctx.get("aperture_weight", 0.7),
    )
    capability_context = _candidate_capability_context(ctx)
    result = apply_evidence_context_to_candidate_evaluation(
        result,
        capability_context,
        ctx["input"],
        aperture_weight=ctx.get("aperture_weight", 0.7),
    )
    result["decision_sandbox"]["aperture_anchor"]["frontend_state"] = ctx.get("frontend_state", {})
    result["decision_sandbox"]["aperture"] = result["decision_sandbox"]["aperture_anchor"]
    result["证据链"]["本地RAG命中数"] = capability_context["本地RAG"]["result_count"]
    result["证据链"]["公开检索命中数"] = capability_context["公开检索"]["实时检索"]["result_count"]
    result["能力证据"] = capability_context
    job_profile = _job_profile_for_sourcing(ctx)
    if job_profile is not None:
        job_scoring = score_candidate_against_job(job_profile, ctx["input"])
        result["岗位匹配"] = {
            **_job_profile_match(job_profile, ctx["input"]),
            "评分维度": job_scoring["评分维度"],
            "评分依据": job_scoring["评分依据"],
        }
        result["适合岗位"] = job_profile["title"]
        result["匹配评分"] = job_scoring["匹配评分"]
        result["推荐等级"] = job_scoring["推荐等级"]
        result["推荐结论"] = job_scoring["推荐结论"]
        result["结论"] = job_scoring["推荐结论"]
        result["技术强项"] = job_scoring["技术强项"]
        result["风险点"] = job_scoring["风险点"]
        if job_profile.get("interview_questions"):
            result["面试追问"] = list(job_profile["interview_questions"])
    ctx["data"]["evaluation"] = result
    ctx["data"]["candidate_capability_context"] = capability_context
    dependency = result["decision_sandbox"]["evidence_dependency_contract"]
    ctx["log"] = (
        f"Task A 输出 {dependency['task_a']['fact_count']} 条事实；"
        f"Task B/C 核验命中 {dependency['task_b_c']['matched_fact_count']} 条事实；"
        f"Task D 基于 {len(dependency['task_d']['input_fact_ids'])} 条可用事实生成 {dependency['task_d']['projection_count']} 条推演"
    )
    return {
        "aperture_anchor": result["decision_sandbox"]["aperture_anchor"],
        "工程事实链": result["decision_sandbox"]["fact_chain"],
        "capability_spectrum": result["decision_sandbox"]["capability_spectrum"],
        "能力频谱": result["decision_sandbox"]["capability_spectrum"],
        "narrative_stream": result["decision_sandbox"]["narrative_stream"],
        "增量价值": result["decision_sandbox"]["narrative_stream"]["core_incremental_value"],
        "probing_toolkit": result["decision_sandbox"]["probing_toolkit"],
        "能力平移推演": result["decision_sandbox"]["cognitive_projection"],
        "evidence_dependency_contract": dependency,
        "本地RAG": capability_context["本地RAG"],
        "公开检索": capability_context["公开检索"],
        **({"岗位匹配": result["岗位匹配"]} if "岗位匹配" in result else {}),
    }


def _c_resume(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    probes = result["追问武器库"]
    narrative_status = result["decision_sandbox"]["narrative_stream"]["status"]
    ctx["log"] = f"围绕「{result['decision_sandbox']['aperture_anchor']['team_constraint']}」按 {narrative_status} 状态生成 {len(probes)} 条追问"
    return {"probing_toolkit": probes, "narrative_status": narrative_status}


def _c_reflect(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    ctx["log"] = f"反思完成，识别 {len(result['潜在工程边界'])} 个潜在工程边界"
    return {
        "潜在工程边界": result["潜在工程边界"],
        "风险点": result["风险点"],
        "证据链": result["证据链"],
        "能力证据": result.get("能力证据", {}),
    }


def _c_hitl(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    draft = {
        "aperture_anchor": result["decision_sandbox"]["aperture_anchor"],
        "narrative_stream": result["decision_sandbox"]["narrative_stream"],
        "潜在工程边界": result["潜在工程边界"],
        "probing_toolkit": result["追问武器库"],
    }
    if "岗位匹配" in result:
        draft["岗位匹配"] = result["岗位匹配"]
    return {
        "prompt": "请确认增量价值推演与追问武器库，可通过或填写人工评价后继续。",
        "draft": draft,
    }


def _c_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["evaluation"])
    if ctx["data"].get("candidate_capability_context"):
        result["能力证据"] = ctx["data"]["candidate_capability_context"]
    _apply_human_edits(ctx, result)
    _attach_human_report(ctx, result)
    ctx["log"] = "已汇总生成最终候选人评估报告"
    return result


# ---- Scenario D: weekly report -------------------------------------------- #


def _d_plan(ctx: Dict[str, Any]) -> Any:
    ctx["data"]["weekly"] = generate_weekly_report(ctx["input"])
    ctx["log"] = "已解析本周招聘数据，识别关注岗位"
    return {"本周招聘结论": ctx["data"]["weekly"]["本周招聘结论"]}


def _d_signals(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    role_key = infer_role_key(ctx["input"])
    job_profile = _job_profile_for_sourcing(ctx)
    focus_name = (
        str(job_profile.get("title") or "").strip()
        if job_profile is not None
        else ROBOT_ROLES_METADATA[role_key]["name_zh"]
    ) or ROBOT_ROLES_METADATA[role_key]["name_zh"]
    market_intelligence = _source_intelligence_with_audit(
        f"{focus_name} 招聘 市场人才信号 融资 产品发布 论文 GitHub",
        role_key,
        limit=10,
        ctx=ctx,
        agent_id="industry",
    )
    weekly["市场搜索证据"] = market_intelligence
    ctx["data"]["market_intelligence"] = market_intelligence
    ctx["log"] = (
        f"归纳出 {len(weekly['市场人才信号'])} 条市场人才信号，"
        f"公开检索命中 {market_intelligence['实时检索']['result_count']} 条"
    )
    return {
        "市场人才信号": weekly["市场人才信号"],
        "关键岗位进展": weekly["关键岗位进展"],
        "市场搜索证据": market_intelligence,
    }


def _d_reflect(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    ctx["log"] = f"反思完成，识别 {len(weekly['招聘风险'])} 项招聘风险"
    return {
        "招聘风险": weekly["招聘风险"],
        "搜索证据摘要": _evidence_summary(ctx["data"].get("market_intelligence", {})),
    }


def _d_hitl(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    return {
        "prompt": "请确认下周行动建议，可通过或填写人工补充后继续。",
        "draft": {"下周行动建议": weekly["下周行动建议"]},
    }


def _d_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["weekly"])
    if ctx["data"].get("market_intelligence"):
        result["市场搜索证据"] = ctx["data"]["market_intelligence"]
    _apply_human_edits(ctx, result)
    _attach_human_report(ctx, result)
    ctx["log"] = "已汇总生成最终招聘周报"
    return result


def _attach_human_report(ctx: Dict[str, Any], result: Dict[str, Any]) -> None:
    citations = _collect_citations(result)
    citation_ids = [citation["id"] for citation in citations]
    scenario = ctx["scenario"]
    if scenario == "A":
        report = _job_profile_human_report(ctx, result, citation_ids)
    elif scenario == "B":
        report = _talent_map_human_report(ctx, result, citation_ids)
    elif scenario == "C":
        report = _candidate_human_report(ctx, result, citation_ids)
    else:
        report = _weekly_human_report(ctx, result, citation_ids)
    report["citations"] = citations
    report["diagnostics"] = _collect_evidence_diagnostics(result)
    report["markdown"] = _human_report_markdown(report)
    result["human_report"] = report


def _human_report_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# {report.get('title') or '招聘分析报告'}",
        "",
        "## 分析摘要",
    ]
    for item in report.get("summary", []):
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(f"- {text}")

    lines.extend(["", "## 关键判断"])
    for section in report.get("sections", []):
        heading = section.get("heading") or "未命名章节"
        lines.extend(["", f"### {heading}"])
        for paragraph in section.get("paragraphs", []):
            text = str(paragraph.get("text", "")).strip()
            if text:
                lines.append(text)
        for bullet in section.get("bullets", []):
            lines.append(f"- {bullet}")

    diagnostics = report.get("diagnostics") or {}
    if diagnostics.get("error_count"):
        lines.extend(["", "## 风险点", f"- 检索或工具调用存在 {diagnostics['error_count']} 条诊断信息，需人工复核。"])

    lines.extend(["", "## 下一步建议"])
    lines.append("- 复核高影响判断对应的证据来源。")
    lines.append("- 将人工门控意见回写到岗位画像、候选人画像或下周招聘计划。")
    lines.append("- 对缺证据或冲突证据的判断重新检索或安排面试验证。")

    return "\n".join(lines).strip()


def _calibration_state_from_sources(sources: Dict[str, Any], result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return sources.get("校准状态") or (result or {}).get("校准状态") or {}


def _is_live_calibrated(calibration: Dict[str, Any]) -> bool:
    return calibration.get("status") == "live_calibrated"


def _calibration_paragraph(calibration: Dict[str, Any], citation_ids: list[str]) -> Dict[str, Any]:
    status = calibration.get("status") or "unknown"
    if _is_live_calibrated(calibration):
        text = (
            f"目标来源已通过实时检索校准，动态实体 {calibration.get('dynamic_entity_count', 0)} 个；"
            "静态种子仅保留为审计信息。"
        )
    else:
        text = (
            f"目标来源未通过实时检索校准（{status}）。"
            "前端主报告不展示静态种子为目标名单；需要补充可用检索源或扩大查询后再生成目标公司。"
        )
    return _paragraph(text, citation_ids[:3])


def _dynamic_source_bullets(
    *,
    calibration: Dict[str, Any],
    companies: List[str],
    labs: List[str],
    secondary: List[str] | None = None,
) -> List[str]:
    if not _is_live_calibrated(calibration):
        return [
            "动态目标公司：暂无可验证动态命中",
            "动态实验室：暂无可验证动态命中",
            "静态种子：仅保留在原始结构化数据中作为下一轮检索起点，不作为目标名单",
        ]
    bullets = [
        f"动态目标公司：{', '.join(companies[:10]) or '暂无'}",
        f"动态实验室：{', '.join(labs[:8]) or '暂无'}",
    ]
    if secondary is not None:
        bullets.append(f"动态团队/次优来源：{', '.join(secondary[:10]) or '暂无'}")
    return bullets


def _job_profile_human_report(ctx: Dict[str, Any], result: Dict[str, Any], citation_ids: list[str]) -> Dict[str, Any]:
    sources = result.get("候选人来源", {})
    calibration = _calibration_state_from_sources(sources, result)
    required = (result.get("能力矩阵") or {}).get("必备能力", [])
    exclusions = (result.get("能力矩阵") or {}).get("排除项", [])
    return {
        "title": f"{_role_name(ctx)}岗位画像与招聘建议",
        "subtitle": "面向招聘负责人和面试官的可读版本。证据角标可展开查看来源、URL、检索状态和摘要。",
        "summary": [
            _paragraph(result.get("岗位定位", "已生成岗位定位。"), citation_ids[:2]),
            _calibration_paragraph(calibration, citation_ids),
            _paragraph("建议先围绕真实机器人闭环、动作策略、数据质量和跨模块落地经验筛选候选人。", citation_ids[:3]),
        ],
        "sections": [
            {
                "heading": "岗位定位",
                "paragraphs": [_paragraph(result.get("岗位定位", ""), citation_ids[:2])],
                "bullets": result.get("核心任务", [])[:5],
            },
            {
                "heading": "核心能力",
                "paragraphs": [_paragraph("以下能力来自岗位能力矩阵，并需要通过项目证据、代码/论文/模型或实机部署记录交叉验证。", citation_ids[:3])],
                "bullets": required[:8],
            },
            {
                "heading": "候选人来源",
                "paragraphs": [_paragraph("目标公司和实验室只能来自动态检索或人工确认；静态种子不能作为最终名单展示。", citation_ids[:4])],
                "bullets": _dynamic_source_bullets(
                    calibration=calibration,
                    companies=sources.get("动态目标公司") or sources.get("公司", []),
                    labs=sources.get("动态实验室") or sources.get("实验室", []),
                )
                + [f"关键词：{', '.join(sources.get('岗位关键词', [])[:10])}"],
            },
            {
                "heading": "面试风险",
                "paragraphs": [_paragraph("下面这些排除项需要在简历筛选和技术面中明确验证。", [])],
                "bullets": exclusions[:8],
            },
        ],
    }


def _talent_map_human_report(ctx: Dict[str, Any], result: Dict[str, Any], citation_ids: list[str]) -> Dict[str, Any]:
    strategy = result.get("招聘策略", {})
    candidate_sources = result.get("候选人来源", {})
    calibration = _calibration_state_from_sources(candidate_sources, result)
    return {
        "title": f"{_role_name(ctx)}人才地图",
        "subtitle": "默认展示可执行来源和触达策略；证据细节折叠在角标和索引里。",
        "summary": [
            _calibration_paragraph(calibration, citation_ids),
            _paragraph("这张人才地图只展示动态检索或人工确认后的目标来源；未校准时不会把静态种子当成目标公司。", citation_ids[:4]),
        ],
        "sections": [
            {
                "heading": "优先来源",
                "paragraphs": [_paragraph("优先来源必须有实时检索实体或人工确认状态支撑。", citation_ids[:3])],
                "bullets": _dynamic_source_bullets(
                    calibration=calibration,
                    companies=candidate_sources.get("动态目标公司") or candidate_sources.get("优先来源公司", result.get("目标公司", [])),
                    labs=candidate_sources.get("动态实验室") or candidate_sources.get("高校/实验室", []),
                    secondary=candidate_sources.get("次优来源公司", []),
                ),
            },
            {
                "heading": "搜索关键词",
                "paragraphs": [_paragraph("关键词应分平台使用：GitHub/HF 用英文技术词，招聘站和新闻源可用中英文组合。", citation_ids[:4])],
                "bullets": result.get("搜索关键词", [])[:14],
            },
            {
                "heading": "触达策略",
                "paragraphs": [_paragraph(strategy.get("触达话术") or result.get("触达策略", ""), citation_ids[:2])],
                "bullets": [],
            },
        ],
    }


def _candidate_human_report(ctx: Dict[str, Any], result: Dict[str, Any], citation_ids: list[str]) -> Dict[str, Any]:
    evidence = result.get("能力证据", {})
    rag = evidence.get("本地RAG", {})
    public = (evidence.get("公开检索") or {}).get("实时检索", {})
    sandbox = result.get("decision_sandbox", {})
    aperture = sandbox.get("aperture_anchor") or sandbox.get("aperture", {})
    narrative = sandbox.get("narrative_stream", {})
    dependency = sandbox.get("evidence_dependency_contract", {})
    return {
        "title": f"{result.get('适合岗位', _role_name(ctx))}候选人评估",
        "subtitle": "候选人原始材料只用于本地评估和本地 RAG；公开检索只使用岗位/能力关键词。报告重点是事实重构、能力平移和面试反馈闭环。",
        "summary": [
            _paragraph(narrative.get("core_incremental_value") or result.get("增量价值") or f"推荐等级：{result.get('推荐等级')}；匹配评分：{result.get('匹配评分')}。{result.get('推荐结论', '')}", citation_ids[:3]),
            _paragraph(
                f"当前技术卡点：{aperture.get('team_constraint', '真机泛化')}；"
                f"Task A 事实 {dependency.get('task_a', {}).get('fact_count', len(result.get('工程事实链', [])))} 条，"
                f"Task B/C 匹配事实 {dependency.get('task_b_c', {}).get('matched_fact_count', 0)} 条，"
                f"Task D 推演 {dependency.get('task_d', {}).get('projection_count', len(result.get('能力平移推演', [])))} 条。",
                citation_ids[:3],
            ),
            _paragraph(f"本地 RAG 命中 {rag.get('result_count', 0)} 条，公开检索命中 {public.get('result_count', 0)} 条。", citation_ids[:3]),
        ],
        "sections": [
            {
                "heading": "工程事实链",
                "paragraphs": [_paragraph("以下事实来自候选人材料的工程指标、项目边界和能力关键词抽取，仍需面试确认。", citation_ids[:3])],
                "bullets": [
                    f"{fact.get('label')}：{fact.get('value')}"
                    for fact in result.get("工程事实链", [])[:8]
                ],
            },
            {
                "heading": "能力平移推演",
                "paragraphs": [_paragraph("这里不是简单判定匹配，而是模拟既有能力能否代偿当前团队卡点。", citation_ids[:3])],
                "bullets": [
                    f"{item.get('transfer')}：{item.get('projection')}"
                    for item in result.get("能力平移推演", [])[:6]
                ],
            },
            {
                "heading": "潜在工程边界",
                "paragraphs": [_paragraph("以下边界不作为否定标签，而是进入下一轮面试和试岗验证。", [])],
                "bullets": result.get("潜在工程边界", result.get("风险点", [])) or ["暂未识别明显边界，但仍需人工复核证据。"],
            },
            {
                "heading": "苏格拉底追问",
                "paragraphs": [_paragraph("面试官可直接复制追问，并在面试后把是否答出回流到候选人画像。", [])],
                "bullets": [
                    probe.get("question", "")
                    for probe in result.get("追问武器库", [])[:3]
                ],
            },
            {
                "heading": "证据覆盖",
                "paragraphs": [_paragraph(evidence.get("隐私说明", ""), citation_ids[:2])],
                "bullets": [
                    f"本地 RAG：{rag.get('status', 'unknown')}，命中 {rag.get('result_count', 0)} 条",
                    f"公开检索：命中 {public.get('result_count', 0)} 条",
                ],
            },
        ],
    }


def _weekly_human_report(ctx: Dict[str, Any], result: Dict[str, Any], citation_ids: list[str]) -> Dict[str, Any]:
    market = result.get("市场搜索证据", {})
    live = market.get("实时检索", {})
    return {
        "title": "招聘周报",
        "subtitle": "把本周进展、市场信号、风险和下周动作合成给业务负责人看的版本。",
        "summary": [
            _paragraph(result.get("本周招聘结论", ""), citation_ids[:3]),
            _paragraph(f"本周识别市场信号 {len(result.get('市场人才信号', []))} 条，公开检索命中 {live.get('result_count', 0)} 条。", citation_ids[:3]),
        ],
        "sections": [
            {
                "heading": "关键岗位进展",
                "paragraphs": [_paragraph("以下进展需要继续回流到岗位画像、候选人画像和评分体系。", [])],
                "bullets": result.get("关键岗位进展", []),
            },
            {
                "heading": "市场人才信号",
                "paragraphs": [_paragraph("市场信号来自本周输入和公开检索证据，应继续按来源质量做复核。", citation_ids[:4])],
                "bullets": result.get("市场人才信号", []),
            },
            {
                "heading": "风险与下周动作",
                "paragraphs": [_paragraph("优先处理会阻断招聘闭环和评分校准的问题。", [])],
                "bullets": [*result.get("招聘风险", []), *result.get("下周行动建议", [])],
            },
        ],
    }


def _paragraph(text: str, citations: list[str]) -> Dict[str, Any]:
    return {"text": text, "citations": citations}


def _role_name(ctx: Dict[str, Any]) -> str:
    job_profile = _job_profile_for_sourcing(ctx)
    if job_profile is not None and str(job_profile.get("title") or "").strip():
        return str(job_profile["title"]).strip()
    role_key = ctx.get("role_key") or infer_role_key(ctx.get("input", ""))
    return ROBOT_ROLES_METADATA[role_key]["name_zh"]


def _collect_citations(value: Any, limit: int = 14) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in _walk_dicts(value):
        source_key = item.get("source_key")
        if not source_key:
            continue
        if item.get("retrieval_status") == "skipped":
            continue
        title = item.get("title") or item.get("source_name") or item.get("name_zh") or item.get("source_key")
        candidates.append(
            {
                "title": str(title or "未命名来源"),
                "source_key": source_key,
                "source_name": item.get("source_name") or item.get("name_zh"),
                "source_type": item.get("source_type") or item.get("source_tier"),
                "validation_status": item.get("validation_status") or item.get("retrieval_status"),
                "confidence": item.get("confidence"),
                "url": item.get("url"),
                "snippet": item.get("snippet") or item.get("description") or item.get("purpose"),
                "published_at": item.get("published_at") or item.get("updated_at") or item.get("last_modified"),
            }
        )

    candidates = sorted(candidates, key=_citation_priority)
    unique: list[dict[str, Any]] = []
    seen = set()
    for item in candidates:
        key = (item.get("source_key"), item.get("url"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        item["id"] = str(len(unique) + 1)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _citation_priority(item: dict[str, Any]) -> tuple[int, int, str]:
    has_url_rank = 0 if item.get("url") else 1
    live_rank = 0 if item.get("source_key") in LIVE_RESULT_SOURCE_KEYS else 1
    return (has_url_rank, live_rank, str(item.get("title") or ""))


def _collect_evidence_diagnostics(value: Any) -> dict[str, Any]:
    errors = []
    for item in _walk_dicts(value):
        if "errors" in item and isinstance(item["errors"], list):
            errors.extend(item["errors"])
    return {"errors": errors[:12], "error_count": len(errors)}


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _apply_human_edits(ctx: Dict[str, Any], result: Dict[str, Any]) -> None:
    human = ctx.get("human") or {}
    edits = human.get("edits")
    if edits:
        result["人工修订意见"] = edits
    if human.get("decision"):
        result["人工决策"] = human["decision"]


def _search_config_from_ctx(ctx: Dict[str, Any] | None) -> dict[str, Any]:
    state = (ctx or {}).get("frontend_state")
    return _normalize_search_config(state if isinstance(state, dict) else {})


def _normalize_search_config(value: Any) -> dict[str, Any]:
    state = value if isinstance(value, dict) else {}

    raw_profile = state.get("search_profile") or state.get("searchProfile") or DEFAULT_SEARCH_PROFILE
    search_profile = str(raw_profile or DEFAULT_SEARCH_PROFILE).strip()
    if search_profile not in SEARCH_PROFILE_METADATA:
        search_profile = DEFAULT_SEARCH_PROFILE

    raw_policy = state.get("execution_policy") or state.get("executionPolicy") or DEFAULT_EXECUTION_POLICY
    execution_policy = str(raw_policy or DEFAULT_EXECUTION_POLICY).strip()
    if execution_policy not in SEARCH_EXECUTION_POLICY_METADATA:
        execution_policy = DEFAULT_EXECUTION_POLICY

    raw_layers = state.get("source_layers") or state.get("sourceLayers") or {}
    budget = _normalize_search_budget(execution_policy, state.get("search_budget") or state.get("budget") or {})
    source_layers = _normalize_source_layers(search_profile, raw_layers)
    if source_layers.get("crawler_snapshot") and (
        execution_policy != "deep_live" or int(budget.get("max_crawl_pages") or 0) <= 0
    ):
        source_layers["crawler_snapshot"] = False

    return {
        "search_profile": search_profile,
        "execution_policy": execution_policy,
        "source_layers": source_layers,
        "budget": budget,
    }


def _normalize_source_layers(search_profile: str, raw_layers: Any) -> dict[str, bool]:
    layers = {layer_name: False for layer_name in SEARCH_SOURCE_LAYER_METADATA}
    for layer_name in SEARCH_PROFILE_DEFAULT_LAYERS.get(search_profile, SEARCH_PROFILE_DEFAULT_LAYERS[DEFAULT_SEARCH_PROFILE]):
        layers[layer_name] = True

    if isinstance(raw_layers, dict):
        for raw_key, raw_enabled in raw_layers.items():
            layer_name = _normalize_source_layer_key(str(raw_key))
            if layer_name in layers:
                layers[layer_name] = bool(raw_enabled)
    elif isinstance(raw_layers, list):
        for raw_key in raw_layers:
            layer_name = _normalize_source_layer_key(str(raw_key))
            if layer_name in layers:
                layers[layer_name] = True
    return layers


def _normalize_source_layer_key(value: str) -> str:
    if value in SEARCH_SOURCE_LAYER_ALIASES:
        return SEARCH_SOURCE_LAYER_ALIASES[value]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).replace("-", "_").lower()


def _normalize_search_budget(execution_policy: str, raw_budget: Any) -> dict[str, int]:
    defaults = dict(SEARCH_EXECUTION_POLICY_METADATA[execution_policy]["budget"])
    if not isinstance(raw_budget, dict):
        return defaults

    key_aliases = {
        "maxProviders": "max_providers",
        "perProviderLimit": "per_provider_limit",
        "timeoutSeconds": "timeout_seconds",
        "maxCrawlPages": "max_crawl_pages",
    }
    for raw_key, raw_value in raw_budget.items():
        key = key_aliases.get(str(raw_key), str(raw_key))
        if key not in defaults:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        defaults[key] = value

    return {
        "max_providers": max(0, min(int(defaults["max_providers"]), MAX_DEEP_LIVE_PROVIDERS)),
        "per_provider_limit": max(0, min(int(defaults["per_provider_limit"]), 10)),
        "timeout_seconds": max(0, min(int(defaults["timeout_seconds"]), 60)),
        "max_crawl_pages": max(0, min(int(defaults["max_crawl_pages"]), 20)),
    }


def _live_services_for_search_config(search_config: dict[str, Any]) -> tuple[str, ...]:
    layer_services: list[list[str]] = []
    source_layers = search_config.get("source_layers")
    if not isinstance(source_layers, dict):
        source_layers = {}
    for layer_name, enabled in source_layers.items():
        if not enabled:
            continue
        layer = SEARCH_SOURCE_LAYER_METADATA.get(str(layer_name))
        if not layer:
            continue
        services = [str(service) for service in layer.get("services", ())]
        if services:
            layer_services.append(services)

    services: list[str] = []
    index = 0
    while True:
        appended = False
        for services_for_layer in layer_services:
            if index >= len(services_for_layer):
                continue
            services.append(services_for_layer[index])
            appended = True
        if not appended:
            break
        index += 1
    return tuple(dict.fromkeys(services))


def _prioritize_live_services_from_recommendations(
    live_services: tuple[str, ...],
    recommended_sources: list[dict[str, Any]] | None,
    search_config: dict[str, Any],
) -> tuple[str, ...]:
    if not recommended_sources:
        return live_services
    live_service_set = set(live_services)
    enabled_layers = {
        str(layer_name)
        for layer_name, enabled in (search_config.get("source_layers") or {}).items()
        if bool(enabled)
    }
    prioritized: list[str] = []
    for source in recommended_sources:
        if not isinstance(source, dict):
            continue
        frontend_layers = {str(layer) for layer in source.get("frontend_layers", []) if str(layer)}
        if frontend_layers and enabled_layers and not (frontend_layers & enabled_layers):
            continue
        candidate_services = [str(service) for service in source.get("executable_services", []) if str(service)]
        source_key = str(source.get("source_key") or "").removeprefix("catalog:")
        if source_key:
            candidate_services.append(source_key)
        for service_name in candidate_services:
            if service_name in live_service_set and service_name not in prioritized:
                prioritized.append(service_name)
    if not prioritized:
        return live_services
    return tuple(dict.fromkeys([*prioritized, *live_services]))


def _external_request_policy_for_search_config(search_config: dict[str, Any]) -> str:
    execution_policy = str(search_config.get("execution_policy") or DEFAULT_EXECUTION_POLICY)
    metadata = SEARCH_EXECUTION_POLICY_METADATA.get(execution_policy, SEARCH_EXECUTION_POLICY_METADATA[DEFAULT_EXECUTION_POLICY])
    return str(metadata["external_request_policy"])


def _empty_live_search_context(
    query: str,
    role_key: str | None,
    provider_health: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    search_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = search_config or _normalize_search_config({})
    errors = [{"service": "live_search", "reason": reason}] if reason else []
    return {
        "search_profile": config.get("search_profile"),
        "execution_policy": config.get("execution_policy"),
        "source_layers": config.get("source_layers", {}),
        "external_request_policy": _external_request_policy_for_search_config(config),
        "services": [],
        "query": _live_query(query, role_key, "default"),
        "results": [],
        "errors": errors,
        "result_count": 0,
        "research_layers": _research_layer_summaries([], errors),
        "provider_health": provider_health or [],
        "provider_budget": {
            "max_live_providers": int((config.get("budget") or {}).get("max_providers") or 0),
            "selected": 0,
            "skipped": len(provider_health or []) + len(errors),
        },
    }


def _build_search_run_trace(
    query: str,
    recommended_sources: list[dict[str, Any]],
    records: list[dict[str, Any]],
    live_context: dict[str, Any],
    search_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = search_config or _normalize_search_config({})
    source_layers = config.get("source_layers", {})
    if not isinstance(source_layers, dict):
        source_layers = {}
    return {
        "query": query,
        "search_profile": str(config.get("search_profile") or DEFAULT_SEARCH_PROFILE),
        "execution_policy": str(config.get("execution_policy") or DEFAULT_EXECUTION_POLICY),
        "source_layers": source_layers,
        "external_request_policy": str(
            live_context.get("external_request_policy") or _external_request_policy_for_search_config(config)
        ),
        "provider_budget": live_context.get("provider_budget")
        or {
            "max_live_providers": MAX_LIVE_RECRUITING_PROVIDERS,
            "selected": len(live_context.get("services", [])),
            "skipped": len(live_context.get("errors", [])),
        },
        "providers": {
            "selected": live_context.get("services", []),
            "health": live_context.get("provider_health", []),
            "errors": live_context.get("errors", []),
        },
        "result_count": int(live_context.get("result_count") or 0),
        "research_layers": live_context.get("research_layers", []),
        "evidence_counts": {
            "recommended_sources": len(recommended_sources),
            "records": len(records),
            "source_tiers": _count_record_field(records, "source_tier"),
            "validation_statuses": _count_record_field(records, "validation_status"),
        },
        "evidence_gaps": _search_evidence_gaps(config, live_context, records),
        "next_queries": _search_next_queries(query, config),
        "next_actions": [
            "补齐缺失 provider 的凭证或本地工具后重跑同一搜索配置。",
            "优先复核 primary/verified 证据；needs_cross_check 只能作为线索。",
            "将高置信来源写入候选人或情报归档前保留 source_url 和 validation_status。",
        ],
    }


def _count_record_field(records: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field_name)
        if not value:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _search_evidence_gaps(
    search_config: dict[str, Any],
    live_context: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    source_layers = search_config.get("source_layers")
    if not isinstance(source_layers, dict):
        source_layers = {}
    errors = live_context.get("errors", [])
    error_services = {
        str(error.get("service"))
        for error in errors
        if isinstance(error, dict) and error.get("service")
    }
    if source_layers.get("social") and error_services.intersection(SEARCH_SOURCE_LAYER_METADATA["social"]["services"]):
        gaps.append("社媒扩展层缺少可用 provider 或存在异常，需要补齐工具/Key 后复跑。")
    if source_layers.get("crawler_snapshot") and error_services.intersection(SEARCH_SOURCE_LAYER_METADATA["crawler_snapshot"]["services"]):
        gaps.append("网页抓取层需要人工配置或运行工具，当前只能作为待执行线索。")
    if source_layers.get("due_diligence") and error_services.intersection(SEARCH_SOURCE_LAYER_METADATA["due_diligence"]["services"]):
        gaps.append("尽调层存在缺失凭证或异常，监管/诉讼/专利证据可能不完整。")
    if not records and int(live_context.get("result_count") or 0) == 0:
        gaps.append("当前没有可交叉验证的实时证据，结果只能作为搜索计划。")
    return gaps


def _search_next_queries(query: str, search_config: dict[str, Any]) -> list[str]:
    source_layers = search_config.get("source_layers")
    if not isinstance(source_layers, dict):
        source_layers = {}
    next_queries: list[str] = []
    if source_layers.get("academic") or source_layers.get("code_model"):
        next_queries.append(f"{query} site:github.com")
    if source_layers.get("social"):
        next_queries.append(f"{query} demo hiring team")
    if source_layers.get("crawler_snapshot"):
        next_queries.append(f"{query} official team page")
    if source_layers.get("due_diligence"):
        next_queries.append(f"{query} litigation patent SEC")
    return next_queries[:4]


def _call_search_method_with_optional_config(
    method: Callable[..., dict[str, Any]],
    query: str,
    *,
    limit: int,
    search_config: dict[str, Any],
) -> dict[str, Any]:
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "search_config" in parameters:
        return method(query, limit=limit, search_config=search_config)
    return method(query, limit=limit)


def _source_intelligence(
    user_input: str,
    role_key: str,
    limit: int = 12,
    ctx: Dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> Dict[str, Any]:
    """Return source coverage plus bounded live hits for industry research."""

    job_profile = _job_profile_for_sourcing(ctx) if ctx is not None else None
    if job_profile is not None:
        focus_role_name = str(job_profile.get("title") or "")
        rationale = job_profile.get("rationale") if isinstance(job_profile.get("rationale"), dict) else {}
        focus_terms = [
            str(item).strip()
            for item in [*(rationale or {}).get("sourcing_keywords", []), *job_profile.get("must_have_skills", [])]
            if str(item).strip()
        ]
    else:
        focus_role_name = ROBOT_ROLES_METADATA[role_key]["name_zh"]
        focus_terms = [capability["capability_name_zh"] for capability in get_capabilities_for_role(role_key)]
    search_config = _search_config_from_ctx(ctx)
    live_role_key = None if job_profile is not None else role_key
    query = " ".join(
        [
            user_input,
            focus_role_name,
            *focus_terms[:4],
            "目标公司 实验室 招聘 论文 GitHub Hugging Face 专利 融资 新闻",
        ]
    )
    _emit_audit_event(
        ctx,
        "tool_call",
        agent_id or "industry",
        "规划搜索信源与公开检索",
        {
            "tool": "ServiceRouter.search",
            "query_preview": query[:240],
            "limit": limit,
            "search_profile": search_config["search_profile"],
            "execution_policy": search_config["execution_policy"],
            "source_layers": search_config["source_layers"],
        },
    )
    try:
        router = call_with_retries(
            get_router,
            provider="ServiceRouter",
            policy=RetryPolicy(attempts=2),
        )
        search = call_with_retries(
            router.search,
            provider="Search router",
            policy=RetryPolicy(attempts=2),
        )
        plan = (
            call_with_retries(
                lambda: _call_search_method_with_optional_config(
                    search.plan,
                    query,
                    limit=limit,
                    search_config=search_config,
                ),
                provider="Search plan",
                policy=RetryPolicy(attempts=2),
            )
            if hasattr(search, "plan")
            else {"recommended_sources": []}
        )
        evidence = (
            call_with_retries(
                lambda: _call_search_method_with_optional_config(
                    search.evidence,
                    query,
                    limit=limit,
                    search_config=search_config,
                ),
                provider="Search evidence",
                policy=RetryPolicy(attempts=2),
            )
            if hasattr(search, "evidence")
            else {"records": []}
        )
    except Exception as exc:  # noqa: BLE001 - keep orchestration usable when search is unavailable.
        error_message = friendly_error(exc, provider="Search")
        _emit_audit_event(
            ctx,
            "error",
            agent_id or "industry",
            error_message,
            {"tool": "ServiceRouter.search", "query_preview": query[:240]},
        )
        return {
            "query": query,
            "推荐信源": [],
            "证据记录": [],
            "实时检索": _empty_live_search_context(
                query,
                live_role_key,
                reason="search_provider_unavailable",
                search_config=search_config,
            ),
            "搜索运行追踪": _build_search_run_trace(
                query=query,
                recommended_sources=[],
                records=[],
                live_context=_empty_live_search_context(
                    query,
                    live_role_key,
                    reason="search_provider_unavailable",
                    search_config=search_config,
                ),
                search_config=search_config,
            ),
            "检索说明": f"搜索服务不可用，已回退到静态人才来源：{error_message}",
        }

    recommended_sources = [
        {
            "source_key": source.get("source_key"),
            "name_zh": source.get("name_zh"),
            "source_names": source.get("source_names", []),
            "talent_signals": source.get("talent_signals", []),
            "suggested_queries": source.get("suggested_queries", [])[:3],
        }
        for source in plan.get("recommended_sources", [])[:limit]
    ]
    records = [
        {
            "source_key": record.get("source_key"),
            "source_name": record.get("source_name"),
            "source_tier": record.get("source_tier"),
            "validation_status": record.get("validation_status"),
            "confidence": record.get("confidence"),
            "signals": record.get("signals", []),
            "snippet": record.get("snippet"),
        }
        for record in evidence.get("records", [])[:limit]
    ]
    live_context = _live_search_context(
        router,
        query,
        role_key=live_role_key,
        search_config=search_config,
        recommended_sources=recommended_sources,
    )
    search_run_trace = _build_search_run_trace(
        query=query,
        recommended_sources=recommended_sources,
        records=records,
        live_context=live_context,
        search_config=search_config,
    )
    evidence_ledger = _archive_search_evidence_ledger(
        query=query,
        search_config=search_config,
        recommended_sources=recommended_sources,
        records=records,
        live_context=live_context,
        search_run_trace=search_run_trace,
        ctx=ctx,
    )
    if evidence_ledger:
        search_run_trace["evidence_ledger"] = evidence_ledger
    result = {
        "query": query,
        "推荐信源": recommended_sources,
        "证据记录": records,
        "实时检索": live_context,
        "搜索运行追踪": search_run_trace,
        "证据账本": evidence_ledger,
        "研究框架": _top_down_research_framework(live_context),
        "检索说明": "该节点已使用 source catalog 规划、evidence 记录和选择性实时源检索；缺少密钥或请求失败的源会记录在实时检索 errors 中。",
    }
    _emit_audit_event(
        ctx,
        "evidence",
        agent_id or "industry",
        f"检索证据生成：推荐信源 {len(result['推荐信源'])}，证据记录 {len(result['证据记录'])}，实时命中 {result['实时检索']['result_count']}",
        {
            "query_preview": query[:240],
            "recommended_source_count": len(result["推荐信源"]),
            "evidence_record_count": len(result["证据记录"]),
            "live_result_count": result["实时检索"]["result_count"],
            "live_errors": result["实时检索"].get("errors", [])[:8],
            "search_run_trace": search_run_trace,
        },
    )
    return result


def _source_intelligence_with_audit(
    user_input: str,
    role_key: str,
    limit: int = 12,
    ctx: Dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> Dict[str, Any]:
    try:
        return _source_intelligence(user_input, role_key, limit=limit, ctx=ctx, agent_id=agent_id)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return _source_intelligence(user_input, role_key, limit=limit)


def _archive_search_evidence_ledger(
    query: str,
    search_config: dict[str, Any],
    recommended_sources: list[dict[str, Any]],
    records: list[dict[str, Any]],
    live_context: dict[str, Any],
    search_run_trace: dict[str, Any],
    ctx: Dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not _search_evidence_ledger_enabled(ctx):
        return None

    artifact = _build_search_evidence_ledger_artifact(
        query=query,
        search_config=search_config,
        recommended_sources=recommended_sources,
        records=records,
        live_context=live_context,
        search_run_trace=search_run_trace,
        ctx=ctx,
    )
    try:
        archive_result = IntelligenceArchive().append("search_evidence_ledger", artifact)
    except Exception as exc:  # noqa: BLE001 - search must remain usable if archive storage is unavailable.
        return {
            "status": "archive_failed",
            "artifact_type": "search_evidence_ledger",
            "error": friendly_error(exc, provider="Evidence ledger archive"),
            "record_count": len(records),
            "live_result_count": int(live_context.get("result_count") or 0),
        }

    return {
        **archive_result,
        "status": "archived",
        "record_count": len(records),
        "live_result_count": int(live_context.get("result_count") or 0),
    }


def _search_evidence_ledger_enabled(ctx: Dict[str, Any] | None) -> bool:
    state = (ctx or {}).get("frontend_state")
    if isinstance(state, dict) and state.get("archive_search_evidence") is True:
        return True
    return bool(os.environ.get(ARCHIVE_PATH_ENV))


def _build_search_evidence_ledger_artifact(
    query: str,
    search_config: dict[str, Any],
    recommended_sources: list[dict[str, Any]],
    records: list[dict[str, Any]],
    live_context: dict[str, Any],
    search_run_trace: dict[str, Any],
    ctx: Dict[str, Any] | None,
) -> dict[str, Any]:
    state = (ctx or {}).get("frontend_state")
    frontend_state = state if isinstance(state, dict) else {}
    return {
        "ledger_type": "search_evidence_ledger",
        "task_id": (ctx or {}).get("task_id"),
        "project_id": _frontend_state_value(frontend_state, "project_id", "projectId"),
        "job_id": _frontend_state_value(frontend_state, "job_id", "jobId", "job_profile_id", "jobProfileId"),
        "action": _frontend_state_value(frontend_state, "action"),
        "query": query,
        "search_profile": search_config.get("search_profile"),
        "execution_policy": search_config.get("execution_policy"),
        "source_layers": search_config.get("source_layers", {}),
        "budget": search_config.get("budget", {}),
        "recommended_sources": recommended_sources,
        "evidence_records": records,
        "live_results": live_context.get("results", []),
        "provider_errors": live_context.get("errors", []),
        "provider_health": live_context.get("provider_health", []),
        "research_layers": live_context.get("research_layers", []),
        "evidence_counts": search_run_trace.get("evidence_counts", {}),
        "evidence_gaps": search_run_trace.get("evidence_gaps", []),
        "next_queries": search_run_trace.get("next_queries", []),
        "guardrails": [
            "Only public, authorized, or user-provided sources are archived.",
            "Evidence records preserve source URLs/status for human review before candidate outreach.",
            "Unverified or single-source records remain leads, not final claims.",
        ],
    }


def _rag_context_with_audit(
    query: str,
    top_k: int = 5,
    ctx: Dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> Dict[str, Any]:
    try:
        return _rag_context(query, top_k=top_k, ctx=ctx, agent_id=agent_id)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return _rag_context(query, top_k=top_k)


def _candidate_capability_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    role_key = ctx["role_key"]
    role = ROBOT_ROLES_METADATA[role_key]
    capability_query = " ".join(
        [
            role["name_zh"],
            *[
                capability["capability_name_zh"]
                for capability in get_capabilities_for_role(role_key)
            ][:4],
            "候选人能力 公开项目 论文 GitHub 模型 实机部署",
        ]
    )
    return {
        "公开检索": _source_intelligence_with_audit(capability_query, role_key, limit=8, ctx=ctx, agent_id="candidate_eval"),
        "本地RAG": _rag_context_with_audit(ctx["input"], top_k=5, ctx=ctx, agent_id="candidate_eval"),
        "隐私说明": "候选人原始材料只用于本地 heuristic 与本地 RAG；公开检索只发送岗位和能力关键词，不发送简历全文。",
    }


def _rag_context(
    query: str,
    top_k: int = 5,
    ctx: Dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> Dict[str, Any]:
    _emit_audit_event(
        ctx,
        "tool_call",
        agent_id or "candidate_eval",
        "检索本地 Qdrant 候选人证据",
        {"tool": "embedding + qdrant.search", "top_k": top_k, "query_preview": query[:240]},
    )
    try:
        router = call_with_retries(
            get_router,
            provider="ServiceRouter",
            policy=RetryPolicy(attempts=2),
        )
        embeddings = call_with_retries(
            lambda: router.embedding().embed_texts([query]),
            provider="Embedding provider",
            policy=RetryPolicy(attempts=2),
        )
        vector = embeddings[0].tolist() if hasattr(embeddings[0], "tolist") else list(embeddings[0])
        results = call_with_retries(
            lambda: router.vector_store().search(vector, top_k=top_k),
            provider="Qdrant vector search",
            policy=RetryPolicy(attempts=2),
        )
    except Exception as exc:  # noqa: BLE001 - RAG should not break the agent flow.
        error_message = friendly_error(exc, provider="Qdrant RAG")
        _emit_audit_event(
            ctx,
            "error",
            agent_id or "candidate_eval",
            error_message,
            {"tool": "embedding + qdrant.search", "query_preview": query[:240]},
        )
        return {
            "status": "unavailable",
            "query": query[:240],
            "result_count": 0,
            "results": [],
            "error": error_message,
        }

    result = {
        "status": "retrieved" if results else "empty",
        "query": query[:240],
        "result_count": len(results),
        "results": [
            {
                "candidate_id": (item.get("payload") or {}).get("candidate_id"),
                "chunk_index": (item.get("payload") or {}).get("chunk_index"),
                "score": item.get("score"),
                "content": str((item.get("payload") or {}).get("content", ""))[:500],
            }
            for item in results
        ],
    }
    _emit_audit_event(
        ctx,
        "evidence",
        agent_id or "candidate_eval",
        f"本地 RAG 检索完成：命中 {len(results)} 条",
        {
            "tool": "qdrant.search",
            "top_k": top_k,
            "result_count": len(results),
            "status": result["status"],
        },
    )
    return result


def _live_search_context(
    router,
    query: str,
    role_key: str | None = None,
    per_service_limit: int | None = None,
    timeout_seconds: float | None = None,
    search_config: dict[str, Any] | None = None,
    recommended_sources: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    config = search_config or _normalize_search_config({})
    budget = config.get("budget") if isinstance(config.get("budget"), dict) else {}
    max_providers = int(budget.get("max_providers", MAX_LIVE_RECRUITING_PROVIDERS))
    service_limit = int(per_service_limit if per_service_limit is not None else budget.get("per_provider_limit", 2))
    service_timeout = float(timeout_seconds if timeout_seconds is not None else budget.get("timeout_seconds", 6.0))
    live_services = _prioritize_live_services_from_recommendations(
        _live_services_for_search_config(config),
        recommended_sources,
        config,
    )
    if not live_services:
        return _empty_live_search_context(
            query,
            role_key,
            reason="live_search_blocked_by_mode",
            search_config=config,
        )

    skipped = []
    provider_health = []
    ready_by_layer: dict[str, list[str]] = {}
    for service_name in live_services:
        health = _search_service_health(router, service_name)
        provider_health.append(health)
        if health["status"] != "ready":
            skipped.append({"service": service_name, "reason": _provider_skip_reason(health)})
            continue
        layer_name = SERVICE_SOURCE_LAYER_INDEX.get(service_name, "other")
        ready_by_layer.setdefault(layer_name, []).append(service_name)

    # 层间轮转分配预算：每轮从每个信源层各取一个 ready provider，保证学术、
    # 代码/模型、社媒、新闻等层都先有覆盖，预算才轮到层内的次选 provider。
    selected_services: list[str] = []
    round_index = 0
    while len(selected_services) < max_providers:
        appended = False
        for layer_ready in ready_by_layer.values():
            if round_index >= len(layer_ready) or len(selected_services) >= max_providers:
                continue
            selected_services.append(layer_ready[round_index])
            appended = True
        if not appended:
            break
        round_index += 1
    selected_set = set(selected_services)
    for layer_ready in ready_by_layer.values():
        for service_name in layer_ready:
            if service_name not in selected_set:
                skipped.append({"service": service_name, "reason": "deferred_by_live_budget"})

    providers = []
    for service_name in selected_services:
        try:
            providers.append((service_name, router.search(service_name)))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"service": service_name, "reason": str(exc)})

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = list(skipped)
    if providers:
        executor = ThreadPoolExecutor(max_workers=min(16, len(providers)))
        future_map = {
            executor.submit(_provider_live_search, provider, _live_query(query, role_key, service_name), service_limit): service_name
            for service_name, provider in providers
        }
        done, pending = wait(future_map, timeout=service_timeout)
        for future in done:
            service_name = future_map[future]
            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001
                errors.append({"service": service_name, "reason": str(exc)})
                continue
            for provider_error in payload["errors"]:
                errors.append({"service": service_name, **provider_error})
            results.extend(_summarize_live_result(item) for item in payload["results"])
        for future in pending:
            service_name = future_map[future]
            future.cancel()
            errors.append({"service": service_name, "reason": f"timeout_after_{service_timeout:g}s"})
        executor.shutdown(wait=False, cancel_futures=True)

    bounded_results = results[: max(1, service_limit) * max(1, len(providers))]
    layer_coverage: dict[str, int] = {}
    for service_name, _ in providers:
        layer_name = SERVICE_SOURCE_LAYER_INDEX.get(service_name, "other")
        layer_coverage[layer_name] = layer_coverage.get(layer_name, 0) + 1
    return {
        "search_profile": config.get("search_profile"),
        "execution_policy": config.get("execution_policy"),
        "source_layers": config.get("source_layers", {}),
        "external_request_policy": _external_request_policy_for_search_config(config),
        "services": [service_name for service_name, _ in providers],
        "query": _live_query(query, role_key, "default"),
        "results": bounded_results,
        "errors": errors,
        "result_count": len(results),
        "research_layers": _research_layer_summaries(bounded_results, errors),
        "provider_health": provider_health,
        "provider_budget": {
            "max_live_providers": max_providers,
            "selected": len(providers),
            "skipped": len(skipped),
            "layer_coverage": layer_coverage,
        },
    }


LIVE_RESULT_ERROR_STATUSES = {
    "error",
    "failed",
    "timeout",
    "setup_required",
    "manual_required",
    "manual_setup",
    "config_error",
    "temporarily_unavailable",
    "skipped",
    "deferred",
    "empty",
}


def _provider_live_search(provider, query: str, limit: int) -> dict[str, list[dict[str, Any]]]:
    """Run one provider search and keep error/status entries out of results.

    Providers that expose search_with_errors already separate the two; for the
    rest, entries whose retrieval_status marks a failure are rerouted to errors
    so they never reach lead extraction or evidence summaries as results."""

    search_with_errors = getattr(provider, "search_with_errors", None)
    if callable(search_with_errors):
        payload = search_with_errors(query, limit)
        raw_results = list(payload.get("results") or [])
        errors = [dict(error) for error in payload.get("errors") or []]
    else:
        raw_results = list(provider.search(query, limit) or [])
        errors = []

    results: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("retrieval_status") or "").strip().lower()
        if status in LIVE_RESULT_ERROR_STATUSES:
            error_entry: dict[str, Any] = {
                "status": status,
                "reason": str(item.get("error") or item.get("snippet") or status)[:300],
            }
            if item.get("platform"):
                error_entry["platform"] = item["platform"]
            errors.append(error_entry)
            continue
        results.append(item)
    return {"results": results, "errors": errors}


def _search_service_health(router, service_name: str) -> dict[str, Any]:
    try:
        service = router.config.service(service_name)
    except KeyError:
        return {"service": service_name, "status": "not_configured"}

    settings = service.model_extra or {}
    enabled_env = settings.get("enabled_env")
    if isinstance(enabled_env, str) and enabled_env:
        enabled_value = os.environ.get(enabled_env)
        if enabled_value is not None and enabled_value.strip().lower() in {"0", "false", "no", "off"}:
            return {
                "service": service_name,
                "provider": service.provider,
                "status": "disabled",
                "disabled_by": enabled_env,
                "missing_credentials": [],
                "missing_runtime": [],
            }

    missing_credentials = _missing_required_credentials(service)
    missing_runtime = _missing_runtime_requirements(service)
    missing_manual_setup = _missing_manual_setup_requirements(service)
    if missing_credentials:
        status = "missing_key"
    elif missing_runtime:
        status = "missing_tool"
    elif missing_manual_setup or (service.model_extra or {}).get("manual_setup_required"):
        status = "manual_setup"
    else:
        status = "ready"
    return {
        "service": service_name,
        "provider": service.provider,
        "status": status,
        "missing_credentials": missing_credentials,
        "missing_runtime": missing_runtime,
        "missing_manual_setup": missing_manual_setup,
    }


def _provider_skip_reason(health: dict[str, Any]) -> str:
    status = str(health.get("status") or "unavailable")
    if status == "missing_key":
        return "missing_credentials:" + ",".join(str(item) for item in health.get("missing_credentials", []))
    if status == "missing_tool":
        return "missing_tool:" + ",".join(str(item) for item in health.get("missing_runtime", []))
    if status == "manual_setup":
        missing = ",".join(str(item) for item in health.get("missing_manual_setup", []))
        return "manual_setup:" + missing if missing else "manual_setup"
    return status


def _research_layer_summaries(
    results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for result in results:
        source_key = str(result.get("source_key") or "")
        if source_key:
            result_counts[source_key] = result_counts.get(source_key, 0) + 1
    for error in errors:
        service = str(error.get("service") or "")
        if service:
            error_counts[service] = error_counts.get(service, 0) + 1

    summaries = []
    for layer in TOP_DOWN_RESEARCH_LAYERS:
        services = [str(service) for service in layer["services"]]
        summaries.append(
            {
                "id": str(layer["id"]),
                "name_zh": str(layer["name_zh"]),
                "purpose": str(layer["purpose"]),
                "services": services,
                "result_count": sum(result_counts.get(service, 0) for service in services),
                "error_count": sum(error_counts.get(service, 0) for service in services),
            }
        )
    return summaries


def _top_down_research_framework(live_context: dict[str, Any]) -> dict[str, Any]:
    layers = live_context.get("research_layers") if isinstance(live_context, dict) else []
    if not isinstance(layers, list):
        layers = []
    return {
        "logic": "Top-down: 先看行业/市场，再看技术证据，再定位人才网络，最后用社媒/学校竞赛补新鲜线索。",
        "layer_count": len(layers),
        "layers": layers,
        "coverage_status": "live_with_gaps" if (live_context.get("errors") or []) else "live",
    }


def _live_query(fallback_query: str, role_key: str | None, service_name: str) -> str:
    if not role_key:
        return fallback_query
    role_query = LIVE_ROLE_QUERY_OVERRIDES.get(role_key)
    if not role_query:
        capability_terms = " ".join(
            str(capability.get("capability_name_en", ""))
            for capability in get_capabilities_for_role(role_key)
        )
        keywords = " ".join(keyword for keyword in build_search_keywords(role_key) if keyword.isascii())
        role_query = f"robotics {capability_terms} {keywords}".strip()
    if role_key == "vla_embodied_expert" and service_name in {"github_candidates", "github_users", "github_repositories", "github_code"}:
        return "robotics diffusion policy language:Python"
    if role_key == "vla_embodied_expert" and service_name == "openalex_works_search":
        return "robot foundation model"
    if service_name == "openalex_authors_search":
        return f"{role_query} researcher engineer".strip()
    if service_name == "agent_reach_social_search":
        return f"{role_query} hiring demo team"
    if service_name == "opencli_web_read_search":
        return fallback_query if urlparse(fallback_query).scheme in {"http", "https"} else f"{role_query} official team page"
    if service_name in {"github_candidates", "github_users", "github_repositories", "github_code"}:
        return f"{role_query} language:Python"
    if service_name == "github_topics":
        return role_query
    if service_name == "huggingface_models":
        return "robotics" if role_key == "vla_embodied_expert" else role_query
    if service_name == "brave_web_search":
        return f"{role_query} companies labs hiring"
    return role_query


def _missing_required_credentials(service) -> list[str]:
    settings = service.model_extra or {}
    required_env_fields = (
        "api_key_env",
        "access_key_id_env",
        "access_key_secret_env",
        "bearer_token_env",
        "user_agent_env",
    )
    missing = []
    for field_name in required_env_fields:
        env_name = settings.get(field_name)
        if env_name and not os.environ.get(str(env_name)):
            missing.append(str(env_name))
    token_env = settings.get("token_env")
    if settings.get("token_required") and token_env and not os.environ.get(str(token_env)):
        missing.append(str(token_env))
    return missing


def _missing_runtime_requirements(service) -> list[str]:
    settings = service.model_extra or {}
    missing: list[str] = []
    required_command = settings.get("required_command")
    if isinstance(required_command, str) and required_command and not shutil.which(required_command):
        missing.append(required_command)

    required_commands = settings.get("required_commands")
    if isinstance(required_commands, list):
        for command in required_commands:
            if isinstance(command, str) and command and not shutil.which(command):
                missing.append(command)

    required_python_module = settings.get("required_python_module")
    if (
        isinstance(required_python_module, str)
        and required_python_module
        and importlib.util.find_spec(required_python_module) is None
    ):
        missing.append(required_python_module)

    required_skill_path = settings.get("required_skill_path")
    if isinstance(required_skill_path, str) and required_skill_path:
        expanded_path = os.path.expanduser(required_skill_path)
        if not os.path.exists(expanded_path):
            missing.append(required_skill_path)
    return missing


def _missing_manual_setup_requirements(service) -> list[str]:
    settings = service.model_extra or {}
    if not settings.get("requires_browser_bridge"):
        return []
    command = settings.get("required_command")
    command_name = str(command) if isinstance(command, str) and command else "opencli"
    if not shutil.which(command_name):
        return []
    try:
        completed = subprocess.run(
            [command_name, "doctor"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ["OpenCLI Browser Bridge: opencli doctor timed out"]
    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    connected = completed.returncode == 0 and not _opencli_doctor_output_has_failure(output)
    if connected:
        return []
    reason = _opencli_doctor_failure_reason(output, completed.returncode)
    return [f"OpenCLI Browser Bridge: {reason}"]


def _opencli_doctor_output_has_failure(output: str) -> bool:
    normalized = output.lower()
    return any(marker in normalized for marker in ("[fail]", "[missing]", "not connected", "connectivity: failed"))


def _opencli_doctor_failure_reason(output: str, returncode: int) -> str:
    if "Browser Bridge extension not connected" in output:
        return "Browser Bridge extension not connected"
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "[FAIL]" in line or "[MISSING]" in line or "not connected" in line.lower():
            return line
    return f"opencli doctor exited {returncode}"


def _summarize_live_result(item: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "source_key": item.get("source_key"),
        "source_name": item.get("name_zh") or item.get("source_name"),
        "source_type": item.get("source_type"),
        "title": item.get("title"),
        "url": item.get("url"),
        "snippet": item.get("snippet") or item.get("description"),
        "published_at": item.get("published_at") or item.get("updated_at") or item.get("last_modified"),
        "rank": item.get("rank"),
    }
    for field_name in (
        "name",
        "source_platform",
        "source_url",
        "github_url",
        "linkedin_url",
        "homepage_url",
        "email",
        "evidence",
        "skills",
        "matched_keywords",
        "confidence",
        "github_score",
        "representative_repositories",
        "repository_evidence",
        "recent_activity",
        "scoring_signals",
        "followers",
        "public_repos",
        "rate_limit",
        "owner_login",
        "owner_type",
        "author",
        "company",
        "company_name",
        "companies",
        "assignees",
        "awardee_name",
        "institution",
        "institutions",
        "affiliation",
        "affiliations",
        "lab",
        "labs",
    ):
        if item.get(field_name):
            summary[field_name] = item.get(field_name)
    return summary


def _evidence_summary(intelligence: Dict[str, Any]) -> Dict[str, Any]:
    live = intelligence.get("实时检索") or {}
    return {
        "推荐信源数": len(intelligence.get("推荐信源", [])),
        "证据记录数": len(intelligence.get("证据记录", [])),
        "实时命中数": live.get("result_count", 0),
        "实时源": live.get("services", []),
        "错误或跳过源": live.get("errors", []),
    }


RAW_THOUGHT_KEYS = {
    "thought",
    "thinking",
    "chain_of_thought",
    "raw_thought",
    "raw_thought_chain",
    "cot",
    "reasoning_trace",
}


def _sanitize_event_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in RAW_THOUGHT_KEYS:
                continue
            sanitized[str(key)] = _sanitize_event_value(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_event_value(child) for child in value]
    return value


def _emit_audit_event(
    ctx: Dict[str, Any] | None,
    event_type: str,
    agent_id: str,
    message: str,
    data: Dict[str, Any] | None = None,
) -> None:
    task_id = (ctx or {}).get("task_id")
    if not task_id:
        return
    try:
        task_store.append_event(
            task_id,
            AgentEventCreate(
                type=event_type,  # type: ignore[arg-type]
                agent_id=agent_id,
                step_index=(ctx or {}).get("current_step"),
                step_label=(ctx or {}).get("current_step_label"),
                message=message,
                data=_sanitize_event_value(data or {}),
            ),
        )
    except Exception:
        return


SCENARIO_PLANS: Dict[str, Dict[str, Any]] = {
    "A": {
        "name_zh": "场景 A：岗位画像与 JD",
        "input_hint": "用一句话描述招聘需求，例如：我们想招一个家庭机器人 VLA 算法工程师。",
        "example": "我们想招一个家庭机器人 VLA 算法工程师，要有 Diffusion Policy 和真实机器人部署经验。",
        "steps": [
            Step("orchestrator", "拆解需求", "识别岗位与技术层", "compute", _a_plan),
            Step("industry", "行业研究", "检索目标公司与实验室", "compute", _a_industry),
            Step("tech_route", "技术路线", "拆解能力矩阵", "compute", _a_tech),
            Step("job_model", "岗位建模", "生成岗位画像与 JD", "compute", _a_job_model),
            Step("reflection", "反思审核", "校验排除项与风险", "reflect", _a_reflect),
            Step("human_expert", "人工确认", "等待人类专家确认岗位定位", "hitl", _a_hitl),
            Step("report", "报告生成", "汇总最终岗位画像报告", "finalize", _a_finalize),
        ],
    },
    "B": {
        "name_zh": "场景 B：人才地图",
        "input_hint": "描述目标岗位或技术方向，例如：灵巧手控制负责人。",
        "example": "帮我画一张家庭机器人 SLAM 导航工程师的人才地图。",
        "steps": [
            Step("orchestrator", "拆解需求", "识别目标方向", "compute", _b_plan),
            Step("talent_map", "人才地图", "绘制候选人来源层级", "compute", _b_map),
            Step("strategy", "招聘策略", "制定分层触达策略", "compute", _b_strategy),
            Step("human_expert", "人工确认", "等待人类专家确认触达策略", "hitl", _b_hitl),
            Step("report", "报告生成", "汇总最终人才地图报告", "finalize", _b_finalize),
        ],
    },
    "C": {
        "name_zh": "场景 C：候选人评估",
        "input_hint": "粘贴候选人简历 / 作品 / 项目经历文本。顶部 Aperture 可设置当前团队技术卡点。",
        "example": "候选人在 Isaac Sim 搭建家庭厨房洗碗仿真，复现 Diffusion Policy，做过遥操作数据清洗与多摄像头时间戳对齐，控制链路延迟 12ms。",
        "steps": [
            Step("orchestrator", "解析材料", "对标目标岗位", "compute", _c_plan),
            Step("candidate_eval", "事实重构", "解构工程事实链并交叉补充证据", "compute", _c_eval),
            Step("resume_design", "追问武器库", "生成针对卡点的苏格拉底追问", "compute", _c_resume),
            Step("reflection", "边界模拟", "识别能力平移边界与验证条件", "reflect", _c_reflect),
            Step("human_expert", "认知门控", "等待人类专家确认推演与追问", "hitl", _c_hitl),
            Step("report", "报告生成", "汇总最终决策沙盒报告", "finalize", _c_finalize),
        ],
    },
    "D": {
        "name_zh": "场景 D：招聘周报",
        "input_hint": "粘贴本周招聘进展、候选人状态、面试反馈、市场信号。",
        "example": "本周推进 VLA 算法工程师招聘，3 人进入终面，1 人 offer，市场有新融资和产品发布。",
        "steps": [
            Step("orchestrator", "解析数据", "识别本周关注岗位", "compute", _d_plan),
            Step("industry", "市场信号", "归纳市场人才信号", "compute", _d_signals),
            Step("reflection", "反思审核", "识别招聘风险", "reflect", _d_reflect),
            Step("human_expert", "人工确认", "等待人类专家确认下周计划", "hitl", _d_hitl),
            Step("report", "报告生成", "汇总最终招聘周报", "finalize", _d_finalize),
        ],
    },
}


# --------------------------------------------------------------------------- #
# Atomic workflow protocol                                                     #
# --------------------------------------------------------------------------- #


ATOMIC_NODE_CONTRACTS: dict[tuple[str, int], dict[str, list[str]]] = {
    ("A", 0): {"inputs": ["input"], "requires": [], "outputs": ["role_key", "role_name", "tech_layer"]},
    ("A", 1): {"inputs": ["role_key"], "requires": ["role_key"], "outputs": ["target_companies", "labs", "source_evidence"]},
    ("A", 2): {"inputs": ["role_key"], "requires": ["role_key"], "outputs": ["competency_matrix"]},
    ("A", 3): {"inputs": ["input"], "requires": [], "outputs": ["role_profile", "jd"]},
    ("A", 4): {"inputs": ["role_profile"], "requires": ["data.job_profile"], "outputs": ["reflection"]},
    ("A", 5): {"inputs": ["role_profile"], "requires": ["data.job_profile"], "outputs": ["human_decision"]},
    ("A", 6): {"inputs": ["role_profile", "human_decision"], "requires": ["data.job_profile"], "outputs": ["human_report", "role_profile"]},
    ("B", 0): {"inputs": ["input"], "requires": [], "outputs": ["role_key", "role_name"]},
    ("B", 1): {"inputs": ["role_key"], "requires": ["role_key"], "outputs": ["target_companies", "sourcing_keywords", "source_evidence"]},
    ("B", 2): {"inputs": ["talent_map"], "requires": ["data.talent_map"], "outputs": ["outreach_strategy"]},
    ("B", 3): {"inputs": ["outreach_strategy"], "requires": ["data.strategy"], "outputs": ["human_decision"]},
    ("B", 4): {"inputs": ["talent_map", "human_decision"], "requires": ["data.talent_map"], "outputs": ["human_report", "talent_map"]},
    ("C", 0): {"inputs": ["input"], "requires": [], "outputs": ["role_name"]},
    ("C", 1): {"inputs": ["input", "team_constraint"], "requires": [], "outputs": ["candidate_scorecard", "decision_sandbox", "evidence_chain"]},
    ("C", 2): {"inputs": ["decision_sandbox"], "requires": ["data.evaluation"], "outputs": ["follow_up_questions"]},
    ("C", 3): {"inputs": ["decision_sandbox"], "requires": ["data.evaluation"], "outputs": ["risks", "evidence_chain"]},
    ("C", 4): {"inputs": ["decision_sandbox"], "requires": ["data.evaluation"], "outputs": ["human_decision"]},
    ("C", 5): {"inputs": ["decision_sandbox", "human_decision"], "requires": ["data.evaluation"], "outputs": ["human_report", "candidate_scorecard"]},
    ("D", 0): {"inputs": ["input"], "requires": [], "outputs": ["weekly_summary"]},
    ("D", 1): {"inputs": ["weekly_summary"], "requires": ["data.weekly"], "outputs": ["market_signals", "source_evidence"]},
    ("D", 2): {"inputs": ["weekly_summary"], "requires": ["data.weekly"], "outputs": ["risks"]},
    ("D", 3): {"inputs": ["weekly_summary"], "requires": ["data.weekly"], "outputs": ["human_decision"]},
    ("D", 4): {"inputs": ["weekly_summary", "human_decision"], "requires": ["data.weekly"], "outputs": ["human_report", "weekly_summary"]},
}


def _atomic_contract(scenario_id: str, index: int) -> dict[str, list[str]]:
    return ATOMIC_NODE_CONTRACTS.get((scenario_id, index), {"inputs": [], "requires": [], "outputs": []})


def _atomic_node_id(scenario_id: str, index: int) -> str:
    return f"{scenario_id}.{index}"


def _parse_atomic_node_id(node_id: str) -> tuple[str, int]:
    try:
        scenario_id, raw_index = node_id.split(".", 1)
        return scenario_id, int(raw_index)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid node_id: {node_id}") from exc


def _atomic_node_meta(scenario_id: str, index: int, step: Step) -> dict[str, Any]:
    contract = _atomic_contract(scenario_id, index)
    return {
        "node_id": _atomic_node_id(scenario_id, index),
        "scenario": scenario_id,
        "index": index,
        "agent_id": step.agent_id,
        "agent": AGENT_REGISTRY.get(step.agent_id, {}),
        "label": step.label,
        "message": step.message,
        "kind": step.kind,
        "inputs": contract["inputs"],
        "requires": contract["requires"],
        "outputs": contract["outputs"],
        "requires_human": step.kind == "hitl",
        "can_run": True,
        "can_skip": True,
        "can_retry": True,
    }


def _atomic_nodes_for_scenario(scenario_id: str) -> list[dict[str, Any]]:
    plan = SCENARIO_PLANS[scenario_id]
    return [
        {
            **_atomic_node_meta(scenario_id, index, step),
            "status": "idle",
            "run_count": 0,
            "output": None,
            "error": None,
            "updated_at": None,
        }
        for index, step in enumerate(plan["steps"])
    ]


def _new_atomic_workflow(scenario_id: str) -> dict[str, Any]:
    return {
        "mode": "atomic",
        "scenario_id": scenario_id,
        "artifacts": {},
        "context": {},
        "nodes": _atomic_nodes_for_scenario(scenario_id),
    }


def _public_workflow(frontend_state: dict[str, Any] | None) -> dict[str, Any] | None:
    workflow = (frontend_state or {}).get("workflow")
    if not isinstance(workflow, dict):
        return None
    return {key: value for key, value in workflow.items() if key != "context"}


def _snapshot_with_workflow(snapshot: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if snapshot is None:
        return None
    workflow = _public_workflow(snapshot.get("frontend_state") or {})
    if workflow is not None:
        snapshot = dict(snapshot)
        snapshot["workflow"] = workflow
    return snapshot


def get_workflow_meta() -> dict[str, Any]:
    scenarios = []
    for scenario_id, plan in SCENARIO_PLANS.items():
        scenarios.append(
            {
                "id": scenario_id,
                "name_zh": plan["name_zh"],
                "input_hint": plan["input_hint"],
                "example": plan.get("example", ""),
                "nodes": [
                    _atomic_node_meta(scenario_id, index, step)
                    for index, step in enumerate(plan["steps"])
                ],
            }
        )
    return {"agents": AGENT_REGISTRY, "task_statuses": TASK_STATUS_META, "scenarios": scenarios}


def create_workflow_session(
    scenario: str,
    user_input: str,
    team_constraint: str | None = None,
    aperture_weight: float = 0.7,
    frontend_state: Optional[Dict[str, Any]] = None,
) -> dict[str, Any]:
    if scenario not in SCENARIO_PLANS:
        raise KeyError(scenario)
    state = dict(frontend_state or {})
    state["workflow"] = _new_atomic_workflow(scenario)
    task = task_store.create(
        scenario,
        user_input,
        team_constraint=_resolve_team_constraint(team_constraint, frontend_state),
        aperture_weight=aperture_weight,
        frontend_state=state,
    )
    snapshot = _snapshot_with_workflow(task_store.snapshot(task.task_id))
    if snapshot is None:
        raise RuntimeError(f"Workflow session create failed: {task.task_id}")
    return snapshot


def _workflow_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    workflow = (snapshot.get("frontend_state") or {}).get("workflow")
    if not isinstance(workflow, dict):
        workflow = _new_atomic_workflow(snapshot["scenario_id"])
    return {
        **workflow,
        "nodes": [dict(node) for node in workflow.get("nodes", [])],
        "artifacts": dict(workflow.get("artifacts") or {}),
        "context": dict(workflow.get("context") or {}),
    }


def _save_workflow(task_id: str, snapshot: dict[str, Any], workflow: dict[str, Any]) -> None:
    state = dict(snapshot.get("frontend_state") or {})
    state["workflow"] = _sanitize_event_value(workflow)
    task_store.update(task_id, frontend_state=state)


def _find_workflow_node(workflow: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in workflow.get("nodes", []):
        if node.get("node_id") == node_id:
            return node
    raise KeyError(node_id)


def _path_exists(value: Any, dotted_path: str) -> bool:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current not in (None, "", [])


def _build_atomic_context(snapshot: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
    saved_context = workflow.get("context") or {}
    artifacts = workflow.get("artifacts") or {}
    ctx: dict[str, Any] = {
        "task_id": snapshot["task_id"],
        "input": snapshot["input"],
        "scenario": snapshot["scenario_id"],
        "team_constraint": snapshot.get("team_constraint") or "真机泛化",
        "aperture_weight": snapshot.get("aperture_weight") or 0.7,
        "frontend_state": snapshot.get("frontend_state") or {},
        "data": dict(saved_context.get("data") or {}),
        "human": saved_context.get("human"),
    }
    if saved_context.get("role_key"):
        ctx["role_key"] = saved_context["role_key"]
    elif artifacts.get("role_key"):
        ctx["role_key"] = artifacts["role_key"]
    return ctx


def _validate_atomic_requirements(ctx: dict[str, Any], node: dict[str, Any]) -> None:
    missing = [path for path in node.get("requires", []) if not _path_exists(ctx, path)]
    if missing:
        raise RuntimeError(f"Atomic node {node['node_id']} missing inputs: {', '.join(missing)}")


def _persist_atomic_context(workflow: dict[str, Any], ctx: dict[str, Any]) -> None:
    context: dict[str, Any] = {"data": ctx.get("data", {})}
    if ctx.get("role_key"):
        context["role_key"] = ctx["role_key"]
    if ctx.get("human"):
        context["human"] = ctx["human"]
    workflow["context"] = _sanitize_event_value(context)


def _derive_atomic_artifacts(scenario_id: str, index: int, output: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {}
    if scenario_id == "A" and index == 0:
        return {
            "role_key": output.get("role_key"),
            "role_name": output.get("岗位"),
            "tech_layer": output.get("技术层"),
        }
    if scenario_id == "A" and index == 1:
        return {
            "target_companies": output.get("目标公司"),
            "labs": output.get("高校实验室"),
            "source_evidence": output.get("证据记录"),
        }
    if scenario_id == "A" and index == 2:
        return {"competency_matrix": output.get("能力矩阵")}
    if scenario_id == "A" and index == 3:
        job_profile = ctx.get("data", {}).get("job_profile")
        return {"role_profile": job_profile, "jd": job_profile.get("JD") if isinstance(job_profile, dict) else None}
    if scenario_id == "A" and index == 4:
        return {"reflection": output.get("反思结论")}
    if scenario_id == "B" and index == 0:
        return {"role_key": output.get("role_key"), "role_name": output.get("岗位")}
    if scenario_id == "B" and index == 1:
        return {
            "target_companies": output.get("目标公司"),
            "sourcing_keywords": output.get("搜索关键词"),
            "source_evidence": output.get("证据记录"),
        }
    if scenario_id == "B" and index == 2:
        return {"outreach_strategy": output}
    if scenario_id == "C" and index == 0:
        return {"role_name": output.get("对标岗位")}
    if scenario_id == "C" and index == 1:
        return {
            "candidate_scorecard": ctx.get("data", {}).get("evaluation"),
            "decision_sandbox": output.get("decision_sandbox") or output,
            "evidence_chain": output.get("证据链") or output.get("能力证据"),
        }
    if scenario_id == "C" and index == 2:
        return {"follow_up_questions": output.get("probing_toolkit")}
    if scenario_id == "C" and index == 3:
        return {"risks": output.get("风险点"), "evidence_chain": output.get("证据链")}
    if scenario_id == "D" and index == 0:
        return {"weekly_summary": output.get("本周招聘结论")}
    if scenario_id == "D" and index == 1:
        return {"market_signals": output.get("市场人才信号"), "source_evidence": output.get("市场搜索证据")}
    if scenario_id == "D" and index == 2:
        return {"risks": output.get("招聘风险")}
    if output.get("human_report"):
        return {"human_report": output["human_report"]}
    return {}


def _merge_atomic_artifacts(workflow: dict[str, Any], artifacts: dict[str, Any]) -> None:
    cleaned = {
        key: value
        for key, value in _sanitize_event_value(artifacts).items()
        if value not in (None, "", [])
    }
    workflow.setdefault("artifacts", {}).update(cleaned)


def _update_atomic_node(
    node: dict[str, Any],
    status: str,
    output: Any = None,
    error: str | None = None,
    increment_run_count: bool = False,
) -> None:
    node["status"] = status
    node["error"] = error
    node["updated_at"] = _now()
    if output is not None:
        node["output"] = _sanitize_event_value(output)
    if increment_run_count:
        node["run_count"] = int(node.get("run_count") or 0) + 1


def run_workflow_node(
    task_id: str,
    node_id: str,
    decision: str | None = None,
    edits: str | None = None,
    retry: bool = False,
) -> Optional[dict[str, Any]]:
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        return None
    scenario_id, index = _parse_atomic_node_id(node_id)
    if scenario_id != snapshot["scenario_id"]:
        raise ValueError(f"Node {node_id} does not belong to scenario {snapshot['scenario_id']}")
    plan = SCENARIO_PLANS[scenario_id]
    if index < 0 or index >= len(plan["steps"]):
        raise KeyError(node_id)
    step = plan["steps"][index]
    workflow = _workflow_from_snapshot(snapshot)
    node = _find_workflow_node(workflow, node_id)
    if node.get("status") == "done" and not retry:
        return _snapshot_with_workflow(snapshot)

    ctx = _build_atomic_context(snapshot, workflow)
    _validate_atomic_requirements(ctx, node)
    ctx["current_step"] = index
    ctx["current_step_label"] = step.label

    task_store.start_step(task_id, index, step)
    task_store.append_event(
        task_id,
        AgentEventCreate(
            type="tool_call",
            agent_id=step.agent_id,
            step_index=index,
            step_label=step.label,
            message=f"原子节点执行：{node_id} {step.label}",
            data={"handler": getattr(step.handler, "__name__", None), "kind": step.kind, "atomic_node_id": node_id},
            status="processing",
        ),
    )

    try:
        if step.kind == "hitl" and not decision:
            payload = (
                _run_step_handler_guarded(step.handler, ctx, store=task_store, task_id=task_id, label=step.label)
                if step.handler
                else {"prompt": "请确认", "draft": {}}
            )
            awaiting = {"agent": step.agent_id, "prompt": payload.get("prompt", "请确认"), "draft": payload.get("draft", {})}
            task_store.set_awaiting(task_id, step, index, awaiting)
            _update_atomic_node(node, "awaiting", awaiting, increment_run_count=False)
            _persist_atomic_context(workflow, ctx)
            _save_workflow(task_id, snapshot, workflow)
            return _snapshot_with_workflow(task_store.snapshot(task_id))

        if step.kind == "hitl":
            if decision == "reject":
                _update_atomic_node(node, "error", {"人工决策": "reject", "修改意见": edits}, "人工拒绝", increment_run_count=True)
                _save_workflow(task_id, snapshot, workflow)
                task_store.set_error(task_id, step.agent_id, "人工拒绝，原子流程终止。", {"atomic_node_id": node_id})
                return _snapshot_with_workflow(task_store.snapshot(task_id))
            ctx["human"] = {"decision": decision or "approve", "edits": edits}
            output = {"人工决策": ctx["human"]["decision"], "修改意见": edits}
            message = f"原子人工门控已{ctx['human']['decision']}。"
        else:
            output = (
                _run_step_handler_guarded(step.handler, ctx, store=task_store, task_id=task_id, label=step.label)
                if step.handler
                else None
            )
            message = ctx.pop("log", None) or f"{AGENT_REGISTRY[step.agent_id]['name_zh']} 完成原子节点：{step.label}"

        task_store.complete_step(task_id, step, index, output, message, final=step.kind == "finalize")
        _update_atomic_node(node, "done", output, increment_run_count=True)
        _merge_atomic_artifacts(workflow, _derive_atomic_artifacts(scenario_id, index, output, ctx))
        if step.kind == "hitl":
            _merge_atomic_artifacts(workflow, {"human_decision": ctx.get("human")})
        if step.kind == "finalize" and isinstance(output, dict) and output.get("human_report"):
            _merge_atomic_artifacts(workflow, {"human_report": output["human_report"]})
        _persist_atomic_context(workflow, ctx)
        _save_workflow(task_id, snapshot, workflow)
        if step.kind == "finalize":
            task_store.mark_done(task_id)
        return _snapshot_with_workflow(task_store.snapshot(task_id))
    except TaskCancelled:
        message = "任务已取消，原子节点执行中止。"
        _update_atomic_node(node, "error", error=message, increment_run_count=True)
        _save_workflow(task_id, snapshot, workflow)
        return _snapshot_with_workflow(task_store.snapshot(task_id))
    except Exception as exc:  # noqa: BLE001 - report node failures to the UI.
        message = friendly_error(exc, provider=step.agent_id)
        _update_atomic_node(node, "error", error=message, increment_run_count=True)
        _save_workflow(task_id, snapshot, workflow)
        task_store.set_error(task_id, step.agent_id, message, {"atomic_node_id": node_id})
        return _snapshot_with_workflow(task_store.snapshot(task_id))


def retry_workflow_node(task_id: str, node_id: str, decision: str | None = None, edits: str | None = None) -> Optional[dict[str, Any]]:
    return run_workflow_node(task_id, node_id, decision=decision, edits=edits, retry=True)


def skip_workflow_node(task_id: str, node_id: str, reason: str = "用户跳过原子节点") -> Optional[dict[str, Any]]:
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        return None
    scenario_id, index = _parse_atomic_node_id(node_id)
    if scenario_id != snapshot["scenario_id"]:
        raise ValueError(f"Node {node_id} does not belong to scenario {snapshot['scenario_id']}")
    workflow = _workflow_from_snapshot(snapshot)
    node = _find_workflow_node(workflow, node_id)
    _update_atomic_node(node, "skipped", {"reason": reason})
    _save_workflow(task_id, snapshot, workflow)
    task_store.append_event(
        task_id,
        AgentEventCreate(
            type="summary",
            agent_id="orchestrator",
            step_index=index,
            step_label=node.get("label"),
            message=f"已跳过原子节点：{node_id} {node.get('label')}",
            data={"atomic_node_id": node_id, "node_status": "skipped", "reason": reason},
            status=snapshot["status"],
        ),
    )
    return _snapshot_with_workflow(task_store.snapshot(task_id))


# --------------------------------------------------------------------------- #
# Task store + runner                                                         #
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskCancelled(RuntimeError):
    pass


_NODE_HANDLER_TIMEOUT_SECONDS = max(60.0, float(os.environ.get("SCENARIO_NODE_TIMEOUT_SECONDS", "600")))


def _run_step_handler_guarded(
    handler: Callable[[Dict[str, Any]], Any],
    ctx: Dict[str, Any],
    *,
    store: "DBTaskStore",
    task_id: str,
    label: str,
) -> Any:
    # Handler 在工作线程中执行：内部挂起的调用不能把任务永远钉在 processing，
    # 取消在 ~1s 内生效而不是只在步与步之间。超时/取消后线程被弃置，结果丢弃。
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"node-{task_id[:8]}")
    future = executor.submit(handler, ctx)
    deadline = time.monotonic() + _NODE_HANDLER_TIMEOUT_SECONDS
    try:
        while True:
            try:
                return future.result(timeout=1.0)
            except FuturesTimeoutError:
                if store.is_cancelled(task_id):
                    raise TaskCancelled(task_id)
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"节点「{label}」执行超过 {_NODE_HANDLER_TIMEOUT_SECONDS:.0f} 秒，已按超时终止；可重试该节点。"
                    )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


LEGACY_SCENARIO_RUNTIME_KEY = "legacy_scenario_runtime"
PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY = "project_candidate_evaluation_runtime"


def _frontend_state_without_internal_runtime(frontend_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = dict(frontend_state or {})
    state.pop(LEGACY_SCENARIO_RUNTIME_KEY, None)
    state.pop(PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY, None)
    return state


@dataclass
class TaskState:
    task_id: str
    scenario_id: str
    input: str
    team_constraint: str = "真机泛化"
    aperture_weight: float = 0.7
    frontend_state: Dict[str, Any] = field(default_factory=dict)
    status: str = "processing"
    current_agent: Optional[str] = None
    current_step: int = -1
    total_steps: int = 0
    logs: List[Dict[str, str]] = field(default_factory=list)
    steps_done: List[Dict[str, Any]] = field(default_factory=list)
    awaiting: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def scenario(self) -> str:
        return self.scenario_id


@dataclass
class AsyncTaskSubscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop

    def publish(self, event: dict[str, Any]) -> None:
        if self.loop.is_closed():
            return
        try:
            self.loop.call_soon_threadsafe(self._put_event, event)
        except RuntimeError:
            return

    def _put_event(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        try:
            self.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            return


class TaskEventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, dict[asyncio.Queue, AsyncTaskSubscriber]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        subscriber = AsyncTaskSubscriber(queue=queue, loop=asyncio.get_running_loop())
        with self._lock:
            self._subscribers.setdefault(task_id, {})[queue] = subscriber
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(task_id)
            if not subscribers:
                return
            subscribers.pop(queue, None)
            if not subscribers:
                self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(task_id, {}).values())
        for subscriber in subscribers:
            subscriber.publish(event)


class DBTaskStore:
    """Transactional task registry backed by SQLAlchemy."""

    INTERRUPTED_TASK_GRACE_SECONDS = 300

    def __init__(self) -> None:
        self._session_factory = make_task_session_factory()
        self._lock = threading.RLock()
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._bus = TaskEventBus()
        self._recover_interrupted_tasks()

    def create(
        self,
        scenario_id: str,
        user_input: str,
        team_constraint: str = "真机泛化",
        aperture_weight: float = 0.7,
        frontend_state: Optional[Dict[str, Any]] = None,
    ) -> TaskState:
        task_id = uuid.uuid4().hex[:12]
        now = _dt_now()
        total_steps = len(SCENARIO_PLANS.get(scenario_id, {}).get("steps", []))
        row = TaskModel(
            task_id=task_id,
            scenario_id=scenario_id,
            input=user_input,
            status="processing",
            team_constraint=team_constraint,
            aperture_weight=aperture_weight,
            frontend_state=frontend_state or {},
            current_step=-1,
            total_steps=total_steps,
            steps_done=[],
            created_at=now,
            updated_at=now,
        )
        event: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                session.add(row)
                session.flush()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="summary",
                        agent_id="orchestrator",
                        message="任务已创建，等待 AgentRunner 调度。",
                        data={"scenario_id": scenario_id, "total_steps": total_steps},
                        status="processing",
                    ),
                )
        with self._lock:
            self._cancel_flags[task_id] = threading.Event()
        if event:
            self._bus.publish(task_id, event)
        task = self.get(task_id)
        if task is None:
            raise RuntimeError(f"Task create failed: {task_id}")
        return task

    def get(self, task_id: str) -> Optional[TaskState]:
        snapshot = self.snapshot(task_id)
        if snapshot is None:
            return None
        return TaskState(
            task_id=snapshot["task_id"],
            scenario_id=snapshot["scenario_id"],
            input=snapshot["input"],
            team_constraint=snapshot["team_constraint"],
            aperture_weight=snapshot["aperture_weight"],
            frontend_state=snapshot["frontend_state"],
            status=snapshot["status"],
            current_agent=snapshot["current_agent"],
            current_step=snapshot["current_step"],
            total_steps=snapshot["total_steps"],
            logs=snapshot["logs"],
            steps_done=snapshot["steps_done"],
            awaiting=snapshot["awaiting"],
            result=snapshot["result"],
            error=snapshot["error"],
            created_at=snapshot["created_at"],
            updated_at=snapshot["updated_at"],
        )

    def snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            row = session.get(TaskModel, task_id)
            if row is None:
                return None
            events = session.execute(
                select(AgentEventModel)
                .where(AgentEventModel.task_id == task_id)
                .order_by(AgentEventModel.id)
            ).scalars().all()
            return self._row_to_snapshot(row, events)

    def events_after(self, task_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            if session.get(TaskModel, task_id) is None:
                return []
            events = session.execute(
                select(AgentEventModel)
                .where(AgentEventModel.task_id == task_id, AgentEventModel.id > after_id)
                .order_by(AgentEventModel.id)
            ).scalars().all()
            return [self._event_to_dict(event) for event in events]

    def subscribe(self, task_id: str) -> asyncio.Queue:
        return self._bus.subscribe(task_id)

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        self._bus.unsubscribe(task_id, queue)

    def append_event(self, task_id: str, event: AgentEventCreate) -> dict[str, Any] | None:
        event_dict: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                if session.get(TaskModel, task_id) is None:
                    return None
                event_dict = self._insert_event(session, task_id, event)
        if event_dict:
            self._bus.publish(task_id, event_dict)
        return event_dict

    def update(self, task_id: str, **fields: Any) -> None:
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None:
                    return
                for key, value in fields.items():
                    if not hasattr(row, key):
                        continue
                    setattr(row, key, _sanitize_event_value(value))
                row.updated_at = _dt_now()

    def set_frontend_runtime(self, task_id: str, key: str, runtime: dict[str, Any] | None) -> None:
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None:
                    return
                frontend_state = dict(row.frontend_state or {})
                if runtime is None:
                    frontend_state.pop(key, None)
                else:
                    frontend_state[key] = _sanitize_event_value(runtime)
                row.frontend_state = _sanitize_event_value(frontend_state)
                row.updated_at = _dt_now()

    def start_step(self, task_id: str, index: int, step: Step) -> None:
        event: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or row.status == "cancelled":
                    return
                row.status = "processing"
                row.current_step = index
                row.current_agent = step.agent_id
                row.awaiting = None
                row.updated_at = _dt_now()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="step_start",
                        agent_id=step.agent_id,
                        step_index=index,
                        step_label=step.label,
                        message=f"{AGENT_REGISTRY[step.agent_id]['name_zh']} 开始：{step.message}",
                        data={"kind": step.kind, "message": step.message, "node_status": "active"},
                        status="processing",
                    ),
                )
        if event:
            self._bus.publish(task_id, event)

    def complete_step(self, task_id: str, step: Step, index: int, output: Any, message: str, final: bool = False) -> None:
        event: dict[str, Any] | None = None
        sanitized_output = _sanitize_event_value(output)
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or row.status == "cancelled":
                    return
                steps_done = list(row.steps_done or [])
                entry = {"agent_id": step.agent_id, "label": step.label, "output": sanitized_output}
                steps_done.append(entry)
                row.steps_done = steps_done
                row.current_step = index
                row.current_agent = step.agent_id
                row.status = "processing"
                if final:
                    row.result = sanitized_output
                row.updated_at = _dt_now()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="summary",
                        agent_id=step.agent_id,
                        step_index=index,
                        step_label=step.label,
                        message=message,
                        data={
                            "output": sanitized_output,
                            "step_done": entry,
                            "node_status": "done",
                            "result": sanitized_output if final else None,
                        },
                        status="processing",
                    ),
                )
        if event:
            self._bus.publish(task_id, event)

    def set_awaiting(self, task_id: str, step: Step, index: int, awaiting: Dict[str, Any]) -> None:
        event: dict[str, Any] | None = None
        sanitized = _sanitize_event_value(awaiting)
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or row.status == "cancelled":
                    return
                row.status = "awaiting_human"
                row.current_agent = step.agent_id
                row.current_step = index
                row.awaiting = sanitized
                row.updated_at = _dt_now()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="human_gate",
                        agent_id=step.agent_id,
                        step_index=index,
                        step_label=step.label,
                        message=f"流程暂停，等待人工确认：{awaiting.get('prompt', '')}",
                        data={"awaiting": sanitized, "node_status": "awaiting"},
                        status="awaiting_human",
                    ),
                )
        if event:
            self._bus.publish(task_id, event)

    def confirm(self, task_id: str, decision: str, edits: Optional[str]) -> bool:
        event_dict: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if not row or row.status != "awaiting_human":
                    return False
                row.human_decision = {"decision": decision, "edits": edits}
                row.status = "processing"
                row.awaiting = None
                row.updated_at = _dt_now()
                event_dict = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="human_gate",
                        agent_id="human_expert",
                        step_index=row.current_step,
                        message=f"人工门控结果：{decision}",
                        data={"decision": decision, "edits": edits, "node_status": "done"},
                        status="processing",
                    ),
                )
        if event_dict:
            self._bus.publish(task_id, event_dict)
        return True

    def consume_human_decision(self, task_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or not row.human_decision:
                    return None
                decision = dict(row.human_decision)
                row.human_decision = None
                row.updated_at = _dt_now()
                return _sanitize_event_value(decision)

    def mark_done(self, task_id: str) -> None:
        event: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or row.status == "cancelled":
                    return
                row.status = "done"
                row.current_agent = None
                row.updated_at = _dt_now()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="summary",
                        agent_id="report",
                        message="全部流程完成。",
                        data={"node_status": "done", "result": _sanitize_event_value(row.result)},
                        status="done",
                    ),
                )
        if event:
            self._bus.publish(task_id, event)

    def set_error(self, task_id: str, agent_id: str, message: str, data: Dict[str, Any] | None = None) -> None:
        event: dict[str, Any] | None = None
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None or row.status == "cancelled":
                    return
                row.status = "error"
                row.current_agent = None
                row.error = message
                row.updated_at = _dt_now()
                event = self._insert_event(
                    session,
                    task_id,
                    AgentEventCreate(
                        type="error",
                        agent_id=agent_id,
                        step_index=row.current_step,
                        message=message,
                        data=_sanitize_event_value(data or {}),
                        status="error",
                    ),
                )
        if event:
            self._bus.publish(task_id, event)

    def cancel(self, task_id: str, reason: str = "用户取消任务") -> Optional[Dict[str, Any]]:
        flag = self._cancel_flags.setdefault(task_id, threading.Event())
        flag.set()
        event: dict[str, Any] | None = None
        terminal_snapshot: Optional[Dict[str, Any]] = None
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None:
                    return None
                if row.status in {"done", "error", "cancelled"}:
                    terminal_snapshot = self._row_to_snapshot(row, [])
                else:
                    row.status = "cancelled"
                    row.current_agent = None
                    row.awaiting = None
                    row.error = reason
                    row.updated_at = _dt_now()
                    event = self._insert_event(
                        session,
                        task_id,
                        AgentEventCreate(
                            type="cancelled",
                            agent_id="orchestrator",
                            message=reason,
                            data={
                                "resource_release": [
                                    "database_session_closed_by_context_manager",
                                    "provider_calls_bounded_by_timeout",
                                    "qdrant_client_released_when_provider_closes",
                                ],
                                "node_status": "error",
                            },
                            status="cancelled",
                        ),
                    )
        if terminal_snapshot is not None:
            return self.snapshot(task_id)
        if event:
            self._bus.publish(task_id, event)
        return self.snapshot(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        flag = self._cancel_flags.get(task_id)
        if flag and flag.is_set():
            return True
        with self._session_factory() as session:
            row = session.get(TaskModel, task_id)
            return bool(row and row.status == "cancelled")

    def _insert_event(self, session, task_id: str, event: AgentEventCreate) -> dict[str, Any]:
        payload = event.model_dump()
        event_row = AgentEventModel(
            task_id=task_id,
            type=payload["type"],
            agent_id=payload.get("agent_id"),
            step_index=payload.get("step_index"),
            step_label=payload.get("step_label"),
            message=payload["message"],
            data=_sanitize_event_value(payload.get("data") or {}),
            status=payload.get("status"),
            created_at=_dt_now(),
        )
        session.add(event_row)
        session.flush()
        return self._event_to_dict(event_row)

    def _event_to_dict(self, event: AgentEventModel) -> dict[str, Any]:
        return AgentEventRead.model_validate(event).model_dump(mode="json")

    def _event_to_log(self, event: dict[str, Any]) -> dict[str, str]:
        level = {"human_gate": "hitl", "error": "error", "cancelled": "error"}.get(event["type"], "info")
        if event.get("status") == "done":
            level = "done"
        return {
            "ts": event["created_at"],
            "agent": event.get("agent_id") or "orchestrator",
            "message": event.get("message") or "",
            "level": level,
            "event_type": event["type"],
        }

    def _row_to_snapshot(self, row: TaskModel, events: list[AgentEventModel]) -> Dict[str, Any]:
        event_dicts = [self._event_to_dict(event) for event in events]
        return {
            "task_id": row.task_id,
            "scenario": row.scenario_id,
            "scenario_id": row.scenario_id,
            "input": row.input,
            "team_constraint": row.team_constraint,
            "aperture_weight": row.aperture_weight,
            "frontend_state": row.frontend_state or {},
            "status": row.status,
            "current_agent": row.current_agent,
            "current_step": row.current_step,
            "total_steps": row.total_steps,
            "logs": [self._event_to_log(event) for event in event_dicts],
            "steps_done": row.steps_done or [],
            "awaiting": row.awaiting,
            "result": row.result,
            "error": row.error,
            "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at),
            "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else str(row.updated_at),
            "audit_events": event_dicts,
        }

    def _recover_interrupted_tasks(self) -> None:
        recovery_events: list[tuple[str, dict[str, Any]]] = []
        now = _dt_now()
        with self._session_factory() as session:
            with session.begin():
                rows = session.execute(
                    select(TaskModel).where(TaskModel.status.in_(["processing", "awaiting_human"]))
                ).scalars().all()
                for row in rows:
                    frontend_state = row.frontend_state or {}
                    json_runtime = frontend_state.get("json_workflow_runtime")
                    legacy_runtime = frontend_state.get(LEGACY_SCENARIO_RUNTIME_KEY)
                    project_candidate_runtime = frontend_state.get(PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY)
                    if isinstance(json_runtime, dict):
                        workflow_id = str(json_runtime.get("workflow_id") or "")
                        if row.status == "awaiting_human":
                            continue
                        if row.status == "processing":
                            row.status = "error"
                            row.current_agent = None
                            row.awaiting = None
                            row.error = "JSON workflow interrupted by backend restart. Please retry the workflow task."
                            row.updated_at = _dt_now()
                            event = self._insert_event(
                                session,
                                row.task_id,
                                AgentEventCreate(
                                    type="error",
                                    agent_id="json_workflow",
                                    message=row.error,
                                    data={
                                        "recovery": "json_workflow_interrupted",
                                        "workflow_id": workflow_id,
                                        "json_workflow": True,
                                    },
                                    status="error",
                                ),
                            )
                            recovery_events.append((row.task_id, event))
                            continue
                    if row.status == "awaiting_human" and (
                        isinstance(legacy_runtime, dict) or isinstance(project_candidate_runtime, dict)
                    ):
                        continue
                    updated_at = row.updated_at
                    if updated_at is not None and updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if updated_at is not None:
                        age_seconds = (now - updated_at).total_seconds()
                        if age_seconds < self.INTERRUPTED_TASK_GRACE_SECONDS:
                            continue
                    row.status = "error"
                    row.current_agent = None
                    row.awaiting = None
                    row.error = "后端服务重启，原执行线程已中断。请使用 retry 创建新任务。"
                    row.updated_at = _dt_now()
                    event = self._insert_event(
                        session,
                        row.task_id,
                        AgentEventCreate(
                            type="error",
                            agent_id="orchestrator",
                            message=row.error,
                            data={"recovery": "interrupted_on_backend_startup"},
                            status="error",
                        ),
                    )
                    recovery_events.append((row.task_id, event))
        for task_id, event in recovery_events:
            self._bus.publish(task_id, event)


task_store = DBTaskStore()

CANDIDATE_EVALUATION_APPROVED_SCORE = 92
CANDIDATE_EVALUATION_APPROVED_STATUS = "pending_outreach"
PROJECT_CANDIDATE_EVALUATION_STEP_COUNT = 3

_active_runners: dict[str, threading.Thread] = {}
_active_runners_lock = threading.Lock()


def _frontend_state_value(frontend_state: Optional[Dict[str, Any]], *keys: str) -> str | None:
    if not frontend_state:
        return None
    for key in keys:
        value = frontend_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _project_candidate_evaluation_ids(frontend_state: Optional[Dict[str, Any]]) -> tuple[str, str] | None:
    candidate_id = _frontend_state_value(frontend_state, "candidate_id", "candidateId")
    job_id = _frontend_state_value(frontend_state, "job_id", "jobId", "targetJobProfileId", "job_profile_id")
    if candidate_id and job_id:
        return candidate_id, job_id
    return None


def _project_team_label(project_name: str | None) -> str:
    name = (project_name or "").strip()
    if name.endswith("招聘"):
        name = name.removesuffix("招聘").strip()
    return name or "2026 AI 团队"


class ProjectCandidateEvaluationRunner(threading.Thread):
    """Scenario C runner for real project/job/candidate rows."""

    def __init__(
        self,
        store: DBTaskStore,
        task: TaskState,
        candidate_id: str,
        job_id: str,
    ) -> None:
        super().__init__(daemon=True)
        self._store = store
        self._task = task
        self._candidate_id = candidate_id
        self._job_id = job_id

    def run(self) -> None:
        task_id = self._task.task_id
        try:
            resume_decision = self._store.consume_human_decision(task_id)
            if resume_decision is not None:
                self._resume_after_human_gate(task_id, resume_decision)
                return

            context = self._load_context()
            self._emit_step(
                0,
                Step("candidate_eval", "简历特征提取", "正在提取候选人简历特征...", "compute"),
                {
                    "candidate_id": self._candidate_id,
                    "candidate_name": context["candidate_name"],
                    "current_company": context["current_company"],
                    "city": context["city"],
                },
            )
            self._delay(0.15)

            job_profile = context.get("job_profile")
            scoring = (
                score_candidate_against_job(job_profile, context.get("candidate_material") or "")
                if job_profile
                else None
            )
            team_label = _project_team_label(context["project_name"])
            match_message = (
                f"正在按「{context['job_title']}」岗位评分标准（scoring_rubric）进行匹配..."
                if scoring is not None
                else f"正在与【{team_label}】岗位要求进行向量匹配..."
            )
            self._emit_step(
                1,
                Step("candidate_eval", "岗位匹配评分", match_message, "compute"),
                {
                    "candidate_id": self._candidate_id,
                    "job_id": self._job_id,
                    "job_title": context["job_title"],
                    "project_id": context["project_id"],
                    **({"评分维度": scoring["评分维度"], "评分依据": scoring["评分依据"]} if scoring else {}),
                },
            )
            self._delay(_candidate_evaluation_delay_seconds())

            if scoring is not None:
                match_score = int(scoring["匹配评分"])
                summary_bits = []
                if scoring["必备技能命中"]:
                    summary_bits.append(f"必备技能命中：{', '.join(scoring['必备技能命中'][:6])}")
                if scoring["必备技能缺口"]:
                    summary_bits.append(f"待确认缺口：{', '.join(scoring['必备技能缺口'][:6])}")
                if scoring["风险信号命中"]:
                    summary_bits.append(f"风险信号：{', '.join(scoring['风险信号命中'][:4])}")
                detail = "；".join(summary_bits) or "命中明细见评分维度"
                report = (
                    f"该候选人与「{context['job_title']}」匹配度 {match_score} 分（{scoring['推荐等级']}）。"
                    f"{detail}。{scoring['推荐结论']}。是否自动生成邀约邮件？"
                )
            else:
                match_score = CANDIDATE_EVALUATION_APPROVED_SCORE
                report = (
                    f"该候选人匹配度 {CANDIDATE_EVALUATION_APPROVED_SCORE} 分，"
                    "具备丰富的大模型工程经验，建议进入下一轮。是否自动生成邀约邮件？"
                )
            awaiting_step = Step("human_expert", "人工网闸", "等待 HR 确认 AI 候选评估报告", "hitl")
            self._store.set_frontend_runtime(
                task_id,
                PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY,
                {
                    "type": PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY,
                    "candidate_id": self._candidate_id,
                    "job_id": self._job_id,
                    "context": context,
                    "report": report,
                    "match_score": match_score,
                    "scoring": scoring,
                    "awaiting_step_index": 2,
                },
            )
            draft = {
                "candidate_id": self._candidate_id,
                "candidate_name": context["candidate_name"],
                "job_id": self._job_id,
                "job_title": context["job_title"],
                "body": report,
                "report": report,
            }
            if scoring is not None:
                draft["岗位匹配"] = {
                    "评分维度": scoring["评分维度"],
                    "必备技能命中": scoring["必备技能命中"],
                    "必备技能缺口": scoring["必备技能缺口"],
                    "风险点": scoring["风险点"],
                    "评分依据": scoring["评分依据"],
                }
            self._store.set_awaiting(
                task_id,
                awaiting_step,
                2,
                {
                    "agent": "candidate_eval",
                    "prompt": f"AI 已为候选人 {context['candidate_name']} 生成评估报告，请确认是否批准推进。",
                    "draft": draft,
                    "match_score": match_score,
                    "pipeline_status": CANDIDATE_EVALUATION_APPROVED_STATUS,
                },
            )
        except TaskCancelled:
            self._store.cancel(task_id, "用户取消任务")
        except Exception as exc:  # noqa: BLE001 - task failures must be visible to SSE clients.
            message = friendly_error(exc, provider="candidate_eval")
            self._store.set_error(task_id, "candidate_eval", message)
        finally:
            with _active_runners_lock:
                _active_runners.pop(task_id, None)

    def _resume_after_human_gate(self, task_id: str, decision: dict[str, Any]) -> None:
        runtime = self._project_candidate_runtime()
        report = str(runtime.get("report") or "")
        try:
            approved_score = int(runtime.get("match_score"))
        except (TypeError, ValueError):
            approved_score = CANDIDATE_EVALUATION_APPROVED_SCORE
        awaiting_step = Step("human_expert", "人工网闸", "等待 HR 确认 AI 候选评估报告", "hitl")
        if decision.get("decision") == "reject":
            self._store.complete_step(
                task_id,
                awaiting_step,
                2,
                {
                    "decision": "reject",
                    "candidate_id": self._candidate_id,
                    "job_id": self._job_id,
                    "database_updated": False,
                },
                "HR 已拒绝自动推进，未更新候选人状态。",
                final=True,
            )
            self._store.mark_done(task_id)
            self._store.set_frontend_runtime(task_id, PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY, None)
            return

        database_update = self._apply_approved_result(approved_score)
        self._store.complete_step(
            task_id,
            awaiting_step,
            2,
            {
                "decision": decision.get("decision", "approve"),
                "evaluation_report": report,
                "database_update": database_update,
            },
            "HR 已批准评估结论，候选人匹配分与 pipeline 状态已写回数据库。",
            final=True,
        )
        self._store.mark_done(task_id)
        self._store.set_frontend_runtime(task_id, PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY, None)

    def _project_candidate_runtime(self) -> dict[str, Any]:
        runtime = (self._task.frontend_state or {}).get(PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY)
        return runtime if isinstance(runtime, dict) else {}

    def _load_context(self) -> dict[str, Any]:
        with project_session_factory()() as session:
            row = session.execute(
                select(Candidate, Job, Project, JobCandidate)
                .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
                .join(Job, Job.id == JobCandidate.job_id)
                .join(Project, Project.id == Job.project_id)
                .where(Candidate.id == self._candidate_id, Job.id == self._job_id)
            ).first()
            if row is None:
                raise ValueError(
                    f"Candidate/job link not found: candidate_id={self._candidate_id}, job_id={self._job_id}"
                )
            candidate, job, project, link = row
            material_parts = [
                candidate.name or "",
                candidate.title or "",
                candidate.current_company or "",
                " ".join(str(item) for item in candidate.skills or []),
                " ".join(str(item) for item in candidate.evidence or []),
                " ".join(str(item) for item in link.evidence or []) if isinstance(link.evidence, list) else "",
            ]
            has_job_profile = bool(job.scoring_rubric or job.must_have_skills or job.rationale)
            return {
                "candidate_id": candidate.id,
                "candidate_name": candidate.name,
                "current_company": candidate.current_company,
                "city": candidate.city,
                "job_id": job.id,
                "job_title": job.title,
                "project_id": project.id,
                "project_name": project.name,
                "existing_match_score": link.match_score,
                "existing_pipeline_status": link.pipeline_status,
                "candidate_material": " ".join(part for part in material_parts if part),
                "job_profile": (
                    {
                        "id": job.id,
                        "title": job.title,
                        "must_have_skills": job.must_have_skills or [],
                        "nice_to_have_skills": job.nice_to_have_skills or [],
                        "scoring_rubric": job.scoring_rubric or {},
                        "rationale": job.rationale or {},
                        "interview_questions": job.interview_questions or [],
                    }
                    if has_job_profile
                    else None
                ),
            }

    def _apply_approved_result(self, match_score: int) -> dict[str, Any]:
        with project_session_factory()() as session:
            with session.begin():
                link = session.scalar(
                    select(JobCandidate).where(
                        JobCandidate.job_id == self._job_id,
                        JobCandidate.candidate_id == self._candidate_id,
                    )
                )
                if link is None:
                    raise ValueError(
                        f"Candidate/job link not found: candidate_id={self._candidate_id}, job_id={self._job_id}"
                    )
                link.match_score = match_score
                link.pipeline_status = CANDIDATE_EVALUATION_APPROVED_STATUS
        return {
            "candidate_id": self._candidate_id,
            "job_id": self._job_id,
            "match_score": match_score,
            "pipeline_status": CANDIDATE_EVALUATION_APPROVED_STATUS,
        }

    def _emit_step(self, index: int, step: Step, output: dict[str, Any]) -> None:
        self._raise_if_cancelled()
        self._store.start_step(self._task.task_id, index, step)
        self._store.complete_step(
            self._task.task_id,
            step,
            index,
            output,
            step.message,
        )

    def _delay(self, seconds: float) -> None:
        remaining = max(seconds, 0.0)
        while remaining > 0:
            self._raise_if_cancelled()
            chunk = min(0.1, remaining)
            time.sleep(chunk)
            remaining -= chunk

    def _raise_if_cancelled(self) -> None:
        if self._store.is_cancelled(self._task.task_id):
            raise TaskCancelled("任务已取消")


def _candidate_evaluation_delay_seconds() -> float:
    raw = os.environ.get("CANDIDATE_EVALUATION_DELAY_SECONDS")
    if raw is None:
        return 1.2
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.2


class AgentRunner(threading.Thread):
    """Runs one scenario plan step-by-step, updating DBTaskStore."""

    STEP_DELAY_SECONDS = 0.6

    def __init__(self, store: DBTaskStore, task: TaskState) -> None:
        super().__init__(daemon=True)
        self._store = store
        self._task = task

    def run(self) -> None:
        task_id = self._task.task_id
        scenario = self._task.scenario
        plan = SCENARIO_PLANS[scenario]
        ctx, start_index, awaiting_step_index = self._load_runtime_context()

        try:
            for idx, step in enumerate(plan["steps"][start_index:], start=start_index):
                self._raise_if_cancelled()
                ctx["current_step"] = idx
                ctx["current_step_label"] = step.label
                agent = AGENT_REGISTRY[step.agent_id]["name_zh"]
                resumed_human_gate = step.kind == "hitl" and awaiting_step_index == idx
                if not resumed_human_gate:
                    self._store.start_step(task_id, idx, step)
                    self._store.append_event(
                        task_id,
                        AgentEventCreate(
                            type="tool_call",
                            agent_id=step.agent_id,
                            step_index=idx,
                            step_label=step.label,
                            message=f"调用节点处理器：{step.label}",
                            data={"handler": getattr(step.handler, "__name__", None), "kind": step.kind},
                            status="processing",
                        ),
                    )
                    self._interruptible_delay()

                if step.kind == "hitl":
                    decision = self._store.consume_human_decision(task_id) if resumed_human_gate else None
                    if decision is None:
                        payload = (
                            _run_step_handler_guarded(
                                step.handler, ctx, store=self._store, task_id=task_id, label=step.label
                            )
                            if step.handler
                            else {"prompt": "请确认", "draft": {}}
                        )
                        awaiting = {
                            "agent": step.agent_id,
                            "prompt": payload.get("prompt", "请确认"),
                            "draft": payload.get("draft", {}),
                        }
                        for key, value in payload.items():
                            if key not in awaiting:
                                awaiting[key] = value
                        if _should_auto_confirm_human_gate(ctx):
                            decision = {"decision": "approve", "edits": "scheduler auto approve"}
                            ctx["human"] = decision
                            self._store.complete_step(
                                task_id,
                                step,
                                idx,
                                {"人工决策": "approve", "修改意见": decision["edits"], "auto_confirmed": True},
                                "自动搜候选人任务已自动通过人工门控，继续执行入库。",
                            )
                            self._save_runtime_context(ctx, idx + 1)
                            continue
                        self._save_runtime_context(ctx, idx, awaiting_step_index=idx)
                        self._store.set_awaiting(task_id, step, idx, awaiting)
                        return
                    if decision.get("decision") == "reject":
                        self._clear_runtime_context()
                        self._store.set_error(task_id, step.agent_id, "人工拒绝，流程终止。")
                        return
                    ctx["human"] = decision
                    self._store.complete_step(
                        task_id,
                        step,
                        idx,
                        {"人工决策": decision.get("decision"), "修改意见": decision.get("edits")},
                        f"人类专家已{decision.get('decision')}，继续执行。",
                    )
                    self._save_runtime_context(ctx, idx + 1)
                    continue

                output = (
                    _run_step_handler_guarded(step.handler, ctx, store=self._store, task_id=task_id, label=step.label)
                    if step.handler
                    else None
                )
                self._raise_if_cancelled()
                log_message = ctx.pop("log", None) or f"{agent} 完成：{step.label}"
                self._store.complete_step(task_id, step, idx, output, log_message, final=step.kind == "finalize")
                self._save_runtime_context(ctx, idx + 1)

            self._store.mark_done(task_id)
            self._clear_runtime_context()
        except TaskCancelled:
            self._clear_runtime_context()
            self._store.cancel(task_id, "用户取消任务")
        except Exception as exc:  # noqa: BLE001 - surface handler failures to the UI.
            self._clear_runtime_context()
            message = friendly_error(exc, provider=self._task.current_agent or "AgentRunner")
            self._store.set_error(task_id, self._task.current_agent or "orchestrator", message)
        finally:
            with _active_runners_lock:
                _active_runners.pop(task_id, None)

    def _load_runtime_context(self) -> tuple[Dict[str, Any], int, int | None]:
        runtime = (self._task.frontend_state or {}).get(LEGACY_SCENARIO_RUNTIME_KEY)
        if isinstance(runtime, dict) and runtime.get("scenario") == self._task.scenario:
            raw_context = runtime.get("context")
            ctx = dict(raw_context) if isinstance(raw_context, dict) else {}
            ctx["task_id"] = self._task.task_id
            ctx["input"] = self._task.input
            ctx["scenario"] = self._task.scenario
            ctx["team_constraint"] = self._task.team_constraint
            ctx["aperture_weight"] = self._task.aperture_weight
            ctx["frontend_state"] = _frontend_state_without_internal_runtime(
                ctx.get("frontend_state") if isinstance(ctx.get("frontend_state"), dict) else self._task.frontend_state
            )
            ctx.setdefault("data", {})
            ctx.setdefault("human", None)
            start_index = int(runtime.get("next_step_index") or 0)
            awaiting_index = runtime.get("awaiting_step_index")
            return ctx, max(0, start_index), int(awaiting_index) if awaiting_index is not None else None

        return (
            {
                "task_id": self._task.task_id,
                "input": self._task.input,
                "scenario": self._task.scenario,
                "team_constraint": self._task.team_constraint,
                "aperture_weight": self._task.aperture_weight,
                "frontend_state": _frontend_state_without_internal_runtime(self._task.frontend_state),
                "data": {},
                "human": None,
            },
            0,
            None,
        )

    def _save_runtime_context(
        self,
        ctx: Dict[str, Any],
        next_step_index: int,
        awaiting_step_index: int | None = None,
    ) -> None:
        runtime = {
            "type": LEGACY_SCENARIO_RUNTIME_KEY,
            "scenario": self._task.scenario,
            "next_step_index": next_step_index,
            "awaiting_step_index": awaiting_step_index,
            "context": _sanitize_event_value(
                {
                    **ctx,
                    "frontend_state": _frontend_state_without_internal_runtime(ctx.get("frontend_state")),
                }
            ),
        }
        self._store.set_frontend_runtime(self._task.task_id, LEGACY_SCENARIO_RUNTIME_KEY, runtime)

    def _clear_runtime_context(self) -> None:
        self._store.set_frontend_runtime(self._task.task_id, LEGACY_SCENARIO_RUNTIME_KEY, None)

    def _raise_if_cancelled(self) -> None:
        if self._store.is_cancelled(self._task.task_id):
            raise TaskCancelled("任务已取消")

    def _interruptible_delay(self) -> None:
        remaining = self.STEP_DELAY_SECONDS
        while remaining > 0:
            self._raise_if_cancelled()
            chunk = min(0.1, remaining)
            time.sleep(chunk)
            remaining -= chunk


def _should_auto_confirm_human_gate(ctx: Dict[str, Any]) -> bool:
    state = ctx.get("frontend_state") or {}
    return bool(
        ctx.get("scenario") == "B"
        and state.get("source") == "CandidateSearchScheduler"
        and state.get("action") == "find_candidates"
        and state.get("auto_confirm_human_gate") is True
    )


def _resolve_team_constraint(
    team_constraint: str | None,
    frontend_state: Optional[Dict[str, Any]],
) -> str:
    """Anchor the evaluation aperture on the project job when one is in context.

    Explicit user input wins; the home-robot default only applies to legacy
    free-text runs without a job profile."""

    explicit = str(team_constraint or "").strip()
    if explicit:
        return explicit
    job_profile = _job_profile_for_sourcing({"frontend_state": frontend_state}) if frontend_state else None
    if job_profile is not None and str(job_profile.get("title") or "").strip():
        return f"{job_profile['title']} 工程落地"
    return "真机泛化"


def start_task(
    scenario: str,
    user_input: str,
    team_constraint: str | None = None,
    aperture_weight: float = 0.7,
    frontend_state: Optional[Dict[str, Any]] = None,
) -> TaskState:
    if scenario not in SCENARIO_PLANS:
        raise KeyError(scenario)
    project_candidate_ids = _project_candidate_evaluation_ids(frontend_state) if scenario == "C" else None
    task = task_store.create(
        scenario,
        user_input,
        team_constraint=_resolve_team_constraint(team_constraint, frontend_state),
        aperture_weight=aperture_weight,
        frontend_state=frontend_state,
    )
    if project_candidate_ids:
        task_store.update(task.task_id, total_steps=PROJECT_CANDIDATE_EVALUATION_STEP_COUNT)
        task = task_store.get(task.task_id) or task
        runner: threading.Thread = ProjectCandidateEvaluationRunner(
            task_store,
            task,
            candidate_id=project_candidate_ids[0],
            job_id=project_candidate_ids[1],
        )
    else:
        runner = AgentRunner(task_store, task)
    with _active_runners_lock:
        _active_runners[task.task_id] = runner
    runner.start()
    return task


def cancel_task(task_id: str) -> Optional[Dict[str, Any]]:
    return task_store.cancel(task_id)


def resume_task_after_confirm(task_id: str) -> Optional[Dict[str, Any]]:
    task = task_store.get(task_id)
    if task is None:
        return None
    frontend_state = task.frontend_state or {}
    runner: threading.Thread | None = None
    project_runtime = frontend_state.get(PROJECT_CANDIDATE_EVALUATION_RUNTIME_KEY)
    if isinstance(project_runtime, dict):
        candidate_id = str(project_runtime.get("candidate_id") or "")
        job_id = str(project_runtime.get("job_id") or "")
        if not candidate_id or not job_id:
            task_store.set_error(task_id, "candidate_eval", "候选人评估恢复失败：缺少 candidate_id 或 job_id。")
            return task_store.snapshot(task_id)
        runner = ProjectCandidateEvaluationRunner(
            task_store,
            task,
            candidate_id=candidate_id,
            job_id=job_id,
        )
    elif isinstance(frontend_state.get(LEGACY_SCENARIO_RUNTIME_KEY), dict):
        runner = AgentRunner(task_store, task)

    if runner is not None:
        with _active_runners_lock:
            _active_runners[task.task_id] = runner
        runner.start()
    return task_store.snapshot(task_id)


def retry_task(task_id: str) -> Optional[TaskState]:
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        return None
    return start_task(
        snapshot["scenario_id"],
        snapshot["input"],
        team_constraint=snapshot.get("team_constraint") or "真机泛化",
        aperture_weight=float(snapshot.get("aperture_weight") or 0.7),
        frontend_state=snapshot.get("frontend_state") or {},
    )


def get_meta() -> Dict[str, Any]:
    """Serialize the orchestration protocol for fully dynamic frontend rendering."""

    scenarios = []
    for scenario_id, plan in SCENARIO_PLANS.items():
        scenarios.append(
            {
                "id": scenario_id,
                "name_zh": plan["name_zh"],
                "input_hint": plan["input_hint"],
                "example": plan.get("example", ""),
                "steps": [
                    {
                        "agent_id": step.agent_id,
                        "label": step.label,
                        "message": step.message,
                        "kind": step.kind,
                    }
                    for step in plan["steps"]
                ],
            }
        )
    return {"agents": AGENT_REGISTRY, "task_statuses": TASK_STATUS_META, "scenarios": scenarios}
