from __future__ import annotations

import os
import importlib.util
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from time import monotonic
from typing import Any

from app.core.config import AppConfig, ServiceConfig, load_app_config


CAPABILITY_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "search_api",
        "service_type": "search",
        "label": "Search API",
        "name_zh": "搜索 API",
        "description": "Search, source planning, and external/internal retrieval capability.",
    },
    {
        "id": "embedding_api",
        "service_type": "embedding",
        "label": "Embedding API",
        "name_zh": "向量化 API",
        "description": "Text embedding capability used before vector search or indexing.",
    },
    {
        "id": "evaluation_api",
        "service_type": "evaluation",
        "label": "Evaluation API",
        "name_zh": "评估 API",
        "description": "Self-RSI evaluation, test, feedback, and iteration capability.",
    },
    {
        "id": "scraping_api",
        "service_type": "scraping",
        "label": "Scraping API",
        "name_zh": "抓取 API",
        "description": "Compliant scraping and managed browser infrastructure capability.",
    },
    {
        "id": "vector_api",
        "service_type": "vector_store",
        "label": "Vector API",
        "name_zh": "向量库 API",
        "description": "Vector index/search capability for candidate and knowledge retrieval.",
    },
    {
        "id": "llm_api",
        "service_type": "llm",
        "label": "LLM API",
        "name_zh": "大模型 API",
        "description": "Language model capability for live generation and reasoning calls.",
    },
    {
        "id": "ocr_api",
        "service_type": "ocr",
        "label": "OCR API",
        "name_zh": "OCR 识别 API",
        "description": "Document/image OCR capability.",
    },
    {
        "id": "structured_output_api",
        "service_type": "structured_output",
        "label": "Structured Output API",
        "name_zh": "结构化输出 API",
        "description": "Schema-constrained generation facade.",
    },
    {
        "id": "document_parser_api",
        "service_type": "document_parser",
        "label": "Document Parser API",
        "name_zh": "文档解析 API",
        "description": "Resume/document parsing capability.",
    },
)

ENDPOINT_CAPABILITY_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "segments.query",
        "service_type": "segments.query",
        "label": "Segments Query API",
        "name_zh": "人群查询 API",
        "description": "Built-in candidate segment query endpoint backed by the project database.",
        "code_path": "app/api/routers/segments.py",
    },
    {
        "id": "segments.create",
        "service_type": "segments.create",
        "label": "Segments Create API",
        "name_zh": "人群保存 API",
        "description": "Built-in candidate segment persistence endpoint backed by the project database.",
        "code_path": "app/api/routers/segments.py",
    },
    {
        "id": "segments.read",
        "service_type": "segments.read",
        "label": "Segments Read API",
        "name_zh": "人群读取 API",
        "description": "Built-in candidate segment read/list endpoints backed by the project database.",
        "code_path": "app/api/routers/segments.py",
    },
)

SECRET_FIELD_MARKERS = ("secret", "token", "password", "credential", "api_key", "access_key")
CONNECTED_STATUSES = {"active", "available"}
CODED_STATUSES = CONNECTED_STATUSES | {"missing_key", "missing_tool", "manual_setup"}

SERVICE_NAME_ZH = {
    "auto_document_parser": "自动文档解析",
    "docling_document_parser": "Docling 文档解析",
    "plain_text_document_parser": "纯文本解析",
    "bge_m3_local": "本地 BGE-M3 向量化",
    "self_rsi_evaluator": "自我 RSI 评估器",
    "qdrant_local": "本地 Qdrant 向量库",
    "docling_ocr": "Docling OCR",
    "aliyun_ocr": "阿里云 OCR",
    "talent_source_catalog": "人才来源目录搜索",
    "agent_reach_social_search": "Agent-Reach 社媒搜索",
    "opencli_platform_search": "OpenCLI 平台搜索",
    "opencli_web_read_search": "OpenCLI 网页正文读取",
    "brave_web_search": "Brave 开放网页搜索",
    "github_repositories": "GitHub 代码仓库搜索",
    "github_candidates": "GitHub 候选人搜索",
    "github_users": "GitHub 用户搜索",
    "github_code": "GitHub 代码搜索",
    "github_topics": "GitHub Topic 搜索",
    "huggingface_models": "Hugging Face 模型搜索",
    "openalex_works_search": "OpenAlex 学术作品搜索",
    "openalex_authors_search": "OpenAlex 作者搜索",
    "openalex_institutions_search": "OpenAlex 机构搜索",
    "semantic_scholar_papers_search": "Semantic Scholar 论文搜索",
    "education_competition_monitor": "学校/竞赛监控",
    "sec_edgar_company_filings": "SEC EDGAR 公司披露",
    "sec_company_facts": "SEC Company Facts 财务事实",
    "sec_insider_transactions": "SEC 内部人交易披露",
    "sec_ownership_activism": "SEC 重大持股与控制权披露",
    "sec_investment_adviser_reports": "SEC 投顾/ERA Form ADV 数据",
    "fdic_bankfind_institutions": "FDIC BankFind 银行机构",
    "federal_register_documents": "Federal Register 监管文件",
    "cpsc_recalls": "CPSC 产品召回",
    "fda_enforcement_recalls": "FDA Enforcement 召回",
    "fda_device_510k": "FDA 510(k) 器械准入",
    "fda_device_events": "FDA MAUDE 器械不良事件",
    "fda_device_classification": "FDA 器械分类与产品代码",
    "fda_device_registration_listing": "FDA 器械注册与列名",
    "cfpb_consumer_complaints": "CFPB 消费金融投诉",
    "nhtsa_recalls": "NHTSA 车辆召回",
    "epa_echo_facilities": "EPA ECHO 设施合规",
    "clinicaltrials_studies": "ClinicalTrials.gov 试验登记",
    "gnews_funding_news": "GNews 融资事件新闻",
    "sec_enforcement_search": "SEC 执法/处罚搜索",
    "usaspending_awards": "USAspending 政府采购与拨款",
    "grants_gov_opportunities": "Grants.gov 资助机会",
    "due_diligence_federated_search": "尽调级联邦情报搜索",
    "outlines_structured_output": "Outlines 结构化输出",
    "openrouter_auto_reasoning": "OpenRouter 自动推理",
    "openrouter_online_research": "OpenRouter 联网研究",
    "openrouter_evidence_judge": "OpenRouter 证据裁判",
    "opencli_crawl_scrape": "OpenCLI 本地抓取",
}

PROVIDER_CODE_PATHS = {
    ("database", "postgres"): "app/providers/database.py",
    ("document_parser", "auto"): "app/providers/document.py",
    ("document_parser", "docling"): "app/providers/document.py",
    ("document_parser", "plain_text"): "app/providers/document.py",
    ("embedding", "sentence_transformers"): "app/providers/embedding.py",
    ("evaluation", "self_rsi"): "app/providers/evaluation.py",
    ("llm", "anthropic_compatible"): "app/providers/llm.py",
    ("llm", "openrouter_chat"): "app/providers/llm.py",
    ("mcp", "local"): "app/providers/mcp.py",
    ("ocr", "aliyun_ocr"): "app/providers/ocr.py",
    ("ocr", "docling"): "app/providers/ocr.py",
    ("search", "brave_web"): "app/providers/search.py",
    ("search", "agent_reach_social"): "app/providers/search.py",
    ("search", "opencli_command"): "app/providers/search.py",
    ("search", "external_search_tool"): "app/providers/search.py",
    ("search", "github_repositories"): "app/providers/search.py",
    ("search", "github_candidates"): "app/providers/search.py",
    ("search", "github_users"): "app/providers/search.py",
    ("search", "github_code"): "app/providers/search.py",
    ("search", "github_topics"): "app/providers/search.py",
    ("search", "huggingface_models"): "app/providers/search.py",
    ("search", "due_diligence_federated"): "app/providers/search.py",
    ("search", "openalex_works"): "app/providers/search.py",
    ("search", "openalex_authors"): "app/providers/search.py",
    ("search", "openalex_institutions"): "app/providers/search.py",
    ("search", "semantic_scholar_papers"): "app/providers/search.py",
    ("search", "education_competition_monitor"): "app/providers/search.py",
    ("search", "sec_edgar_company_filings"): "app/providers/search.py",
    ("search", "sec_company_facts"): "app/providers/search.py",
    ("search", "sec_insider_transactions"): "app/providers/search.py",
    ("search", "sec_ownership_activism"): "app/providers/search.py",
    ("search", "sec_investment_adviser_reports"): "app/providers/search.py",
    ("search", "fdic_bankfind_institutions"): "app/providers/search.py",
    ("search", "federal_register_documents"): "app/providers/search.py",
    ("search", "cpsc_recalls"): "app/providers/search.py",
    ("search", "fda_enforcement_recalls"): "app/providers/search.py",
    ("search", "fda_device_510k"): "app/providers/search.py",
    ("search", "fda_device_events"): "app/providers/search.py",
    ("search", "fda_device_classification"): "app/providers/search.py",
    ("search", "fda_device_registration_listing"): "app/providers/search.py",
    ("search", "cfpb_consumer_complaints"): "app/providers/search.py",
    ("search", "nhtsa_recalls"): "app/providers/search.py",
    ("search", "epa_echo_facilities"): "app/providers/search.py",
    ("search", "clinicaltrials_studies"): "app/providers/search.py",
    ("search", "gnews_funding_news"): "app/providers/search.py",
    ("search", "sec_enforcement"): "app/providers/search.py",
    ("search", "usaspending_awards"): "app/providers/search.py",
    ("search", "grants_gov_opportunities"): "app/providers/search.py",
    ("search", "source_catalog"): "app/providers/search.py",
    ("scraping", "opencli_crawl"): "app/providers/scraping.py",
    ("structured_output", "outlines"): "app/providers/structured_output.py",
    ("vector_store", "qdrant_local"): "app/providers/vector_store.py",
}


PROBE_ERROR_STATUSES = {
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
}
PROBE_DEFAULT_QUERY = "robotics"
PROBE_DEFAULT_TIMEOUT_SECONDS = 12.0
PROBE_MAX_TIMEOUT_SECONDS = 30.0


def probe_search_services(
    config: AppConfig | None = None,
    services: list[str] | None = None,
    timeout_seconds: float = PROBE_DEFAULT_TIMEOUT_SECONDS,
    probe_query: str = PROBE_DEFAULT_QUERY,
) -> dict[str, Any]:
    """Live preflight: run a 1-result query against each configured search service.

    Config-level status only proves keys/tools exist; rate limits, query
    restrictions, and upstream outages surface only on a real request. The
    result distinguishes verified / probe_failed / probe_timeout so the UI can
    stop showing config-only services as unconditionally ready."""

    from app.core.router import ServiceRouter

    config = config or load_app_config()
    timeout = max(1.0, min(float(timeout_seconds), PROBE_MAX_TIMEOUT_SECONDS))
    requested = {str(name) for name in services} if services else None

    candidates: list[dict[str, Any]] = []
    for service in config.services.values():
        if service.type != "search":
            continue
        if requested is not None and service.name not in requested:
            continue
        status = _service_status(config, service)
        if status["status"] in {"active", "available"}:
            candidates.append(status)

    router = ServiceRouter(config)
    probes: list[dict[str, Any]] = []
    if candidates:
        executor = ThreadPoolExecutor(max_workers=min(16, len(candidates)))
        future_map = {
            executor.submit(_probe_one_search_service, router, status["name"], probe_query): status
            for status in candidates
        }
        done, pending = wait(future_map, timeout=timeout)
        for future in done:
            status = future_map[future]
            try:
                probes.append(future.result())
            except Exception as exc:  # noqa: BLE001 - probe must report, not crash.
                probes.append(
                    {
                        "service": status["name"],
                        "name_zh": status["name_zh"],
                        "probe_status": "probe_failed",
                        "reason": str(exc)[:300],
                    }
                )
        for future in pending:
            status = future_map[future]
            future.cancel()
            probes.append(
                {
                    "service": status["name"],
                    "name_zh": status["name_zh"],
                    "probe_status": "probe_timeout",
                    "reason": f"timeout_after_{timeout:g}s",
                }
            )
        executor.shutdown(wait=False, cancel_futures=True)

    probes.sort(key=lambda item: str(item.get("service") or ""))
    verified = sum(1 for item in probes if item["probe_status"] == "verified")
    return {
        "probe_query": probe_query,
        "timeout_seconds": timeout,
        "probed": len(probes),
        "verified": verified,
        "failed": len(probes) - verified,
        "probes": probes,
    }


def _probe_one_search_service(router: Any, service_name: str, probe_query: str) -> dict[str, Any]:
    started = monotonic()
    name_zh = SERVICE_NAME_ZH.get(service_name, service_name)
    try:
        provider = router.search(service_name)
        raw_results = list(provider.search(probe_query, 1) or [])
    except Exception as exc:  # noqa: BLE001 - any provider failure is a probe result.
        return {
            "service": service_name,
            "name_zh": name_zh,
            "probe_status": "probe_failed",
            "latency_ms": int((monotonic() - started) * 1000),
            "reason": str(exc)[:300],
        }

    latency_ms = int((monotonic() - started) * 1000)
    real_results = []
    error_reasons = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("retrieval_status") or "").strip().lower()
        if status in PROBE_ERROR_STATUSES:
            error_reasons.append(str(item.get("error") or item.get("snippet") or status)[:200])
        elif status != "empty":
            real_results.append(item)
    if not real_results and error_reasons:
        return {
            "service": service_name,
            "name_zh": name_zh,
            "probe_status": "probe_failed",
            "latency_ms": latency_ms,
            "reason": "; ".join(error_reasons[:3]),
        }
    return {
        "service": service_name,
        "name_zh": name_zh,
        "probe_status": "verified",
        "latency_ms": latency_ms,
        "result_count": len(real_results),
    }


def get_integration_status(config: AppConfig | None = None) -> dict[str, Any]:
    """Return safe, UI-ready integration status from the service registry.

    The response includes environment variable names and boolean presence only;
    it never includes the environment variable values.
    """

    config = config or load_app_config()
    services = [_service_status(config, service) for service in config.services.values()]
    services_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for service in services:
        services_by_type[service["type"]].append(service)

    capability_specs = list(CAPABILITY_SPECS)
    known_types = {spec["service_type"] for spec in capability_specs}
    for service_type in sorted(set(services_by_type) - known_types):
        capability_specs.append(
            {
                "id": f"{service_type}_api",
                "service_type": service_type,
                "label": f"{service_type.replace('_', ' ').title()} API",
                "name_zh": f"{service_type.replace('_', ' ')} API",
                "description": "Service capability discovered from config/services.toml.",
            }
        )

    return {
        "config_path": str(config.path),
        "defaults": dict(config.defaults),
        "capabilities": [
            _capability_status(spec, config, services_by_type.get(spec["service_type"], []))
            for spec in capability_specs
        ]
        + [_endpoint_capability_status(spec) for spec in ENDPOINT_CAPABILITY_SPECS],
        "services": services,
    }


def _service_status(config: AppConfig, service: ServiceConfig) -> dict[str, Any]:
    settings = service.model_extra or {}
    credentials = _credential_requirements(settings)
    missing_credentials = [item for item in credentials if not item["present"]]
    runtime_requirements = _runtime_requirements(settings)
    missing_runtime = [
        item
        for item in runtime_requirements
        if not item["present"] and item.get("type") != "browser_bridge"
    ]
    missing_manual_setup = [
        item
        for item in runtime_requirements
        if not item["present"] and item.get("type") == "browser_bridge"
    ]
    is_default = config.defaults.get(service.type) == service.name

    if service.provider == "disabled":
        status = "disabled"
    elif _is_disabled_by_env(settings):
        status = "disabled"
    elif missing_credentials:
        status = "missing_key"
    elif missing_runtime:
        status = "missing_tool"
    elif missing_manual_setup or settings.get("manual_setup_required"):
        status = "manual_setup"
    elif is_default:
        status = "active"
    else:
        status = "available"

    return {
        "name": service.name,
        "type": service.type,
        "provider": service.provider,
        "name_zh": SERVICE_NAME_ZH.get(service.name, service.name),
        "description": service.description,
        "is_default": is_default,
        "status": status,
        # 配置级检查只验证密钥/工具存在；429、查询限制、上游故障要实测才知道。
        "verification": "config_only",
        "code_path": _provider_code_path(service) if status in CODED_STATUSES else None,
        "credentials": credentials,
        "runtime_requirements": runtime_requirements,
        "settings": _safe_settings(settings),
    }


def _capability_status(
    spec: dict[str, str],
    config: AppConfig,
    services: list[dict[str, Any]],
) -> dict[str, Any]:
    service_type = spec["service_type"]
    default_service_name = config.defaults.get(service_type)
    default_service = next((service for service in services if service["name"] == default_service_name), None)
    connected_service = next((service for service in services if service["status"] in CONNECTED_STATUSES), None)
    coded_service = next((service for service in services if service["status"] in CODED_STATUSES), None)
    primary_service = (
        default_service
        if default_service and default_service["status"] in CONNECTED_STATUSES
        else connected_service or default_service or coded_service or next(iter(services), None)
    )

    if primary_service is None:
        status = "not_configured"
    else:
        status = primary_service["status"]

    credentials = _unique_credentials(services)
    connected = status in CONNECTED_STATUSES
    code_path = primary_service["code_path"] if primary_service and status in CODED_STATUSES else None

    return {
        **spec,
        "status": status,
        "connected": connected,
        "connected_name_zh": primary_service["name_zh"] if primary_service and status in CODED_STATUSES else "未接入",
        "code_path": code_path,
        "default_service": default_service_name,
        "credential_status": _credential_status(credentials),
        "credentials": credentials,
        "services": [
            {
                "name": service["name"],
                "name_zh": service["name_zh"],
                "provider": service["provider"],
                "status": service["status"],
                "connected": service["status"] in CONNECTED_STATUSES,
                "code_path": service["code_path"],
                "is_default": service["is_default"],
            }
            for service in services
        ],
    }


def _endpoint_capability_status(spec: dict[str, str]) -> dict[str, Any]:
    return {
        **spec,
        "status": "active",
        "connected": True,
        "connected_name_zh": "内置项目数据库",
        "code_path": spec["code_path"],
        "default_service": None,
        "credential_status": "not_required",
        "credentials": [],
        "services": [],
    }


def _provider_code_path(service: ServiceConfig) -> str | None:
    return PROVIDER_CODE_PATHS.get((service.type, service.provider))


def _credential_requirements(settings: dict[str, Any]) -> list[dict[str, Any]]:
    credentials: list[dict[str, Any]] = []
    for field_name, env_name in sorted(settings.items()):
        if field_name == "enabled_env":
            continue
        if not field_name.endswith("_env") or not isinstance(env_name, str) or not env_name:
            continue
        credentials.append(
            {
                "field": field_name,
                "env": env_name,
                "present": bool(os.getenv(env_name)),
                "required": True,
            }
        )
    return credentials


def _is_disabled_by_env(settings: dict[str, Any]) -> bool:
    enabled_env = settings.get("enabled_env")
    if not isinstance(enabled_env, str) or not enabled_env:
        return False
    value = os.getenv(enabled_env)
    return value is not None and value.strip().lower() in {"0", "false", "no", "off"}


def _runtime_requirements(settings: dict[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    required_command = settings.get("required_command")
    if isinstance(required_command, str) and required_command:
        requirements.append(
            {
                "type": "command",
                "name": required_command,
                "present": bool(shutil.which(required_command)),
            }
        )

    required_commands = settings.get("required_commands")
    if isinstance(required_commands, list):
        for command in required_commands:
            if isinstance(command, str) and command:
                requirements.append(
                    {
                        "type": "command",
                        "name": command,
                        "present": bool(shutil.which(command)),
                    }
                )

    required_python_module = settings.get("required_python_module")
    if isinstance(required_python_module, str) and required_python_module:
        requirements.append(
            {
                "type": "python_module",
                "name": required_python_module,
                "present": importlib.util.find_spec(required_python_module) is not None,
            }
        )

    if settings.get("requires_browser_bridge"):
        command = required_command if isinstance(required_command, str) and required_command else "opencli"
        requirements.append(_opencli_browser_bridge_requirement(command))

    required_skill_path = settings.get("required_skill_path")
    if isinstance(required_skill_path, str) and required_skill_path:
        expanded_path = os.path.expanduser(required_skill_path)
        requirements.append(
            {
                "type": "skill_path",
                "name": required_skill_path,
                "present": os.path.exists(expanded_path),
            }
        )
    return requirements


def _opencli_browser_bridge_requirement(command: str) -> dict[str, Any]:
    command_present = bool(shutil.which(command))
    return {
        "type": "browser_bridge",
        "name": "OpenCLI Browser Bridge",
        "present": command_present,
        "command": command,
        "reason": (
            "not checked by integration status; run search probe or OpenCLI search to verify"
            if command_present
            else f"{command} command not found"
        ),
    }

def _unique_credentials(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for service in services:
        for credential in service["credentials"]:
            key = (credential["field"], credential["env"])
            unique[key] = credential
    return list(unique.values())


def _credential_status(credentials: list[dict[str, Any]]) -> str:
    if not credentials:
        return "not_required"
    if all(credential["present"] for credential in credentials):
        return "ready"
    if any(credential["present"] for credential in credentials):
        return "partial"
    return "missing"


def _safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in settings.items():
        if key.endswith("_env") or _looks_secret_field(key):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def _looks_secret_field(field_name: str) -> bool:
    normalized = field_name.lower()
    return any(marker in normalized for marker in SECRET_FIELD_MARKERS)
