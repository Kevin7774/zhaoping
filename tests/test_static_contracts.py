from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.core.config import load_app_config
from app.core.intelligence_archive import IntelligenceArchive
from app.core.integration_status import get_integration_status
from app.core.prompt_config import load_system_prompt
from app.core.orchestrator import (
    SEARCH_SOURCE_LAYER_METADATA,
    _a_industry,
    _a_plan,
    _c_eval,
    _c_finalize,
    _calibrated_target_sources,
    _d_plan,
    _d_signals,
    _job_profile_match,
    _live_services_for_search_config,
    get_meta,
    task_store,
)
from app.core.router import ServiceRouter
from app.api.main import app
from app.rag.ingest_worker import chunk_markdown, stable_point_id
from app.schemas.tasks import AgentEventCreate
from app.skills.tech_space import (
    CAPABILITY_STANDARDS,
    CAPABILITY_TRACEABILITY_OVERRIDES,
    EVIDENCE_RECORD_SCHEMA,
    ROBOT_ROLES_METADATA,
    ROBOT_TEAM_PROFILES,
    STATIC_DYNAMIC_DECISION_TABLE,
    get_capabilities_for_role,
    get_capability_traceability,
    get_role_capability_traceability,
    validate_role_capabilities,
)
from app.skills.search_sources import SEARCH_DATA_SOURCES
from app.skills.recruiting_scenarios import (
    HOME_ROBOT_RECRUITING_SCENARIOS,
    build_talent_map,
    build_talent_map_from_job,
    evaluate_candidate,
    score_candidate_against_job,
    generate_job_profile_and_jd,
    generate_weekly_report,
    infer_role_key,
)
from scripts.run_watchlist import render_markdown_report, run_watchlist


def test_all_role_capabilities_exist() -> None:
    validate_role_capabilities()
    assert len(ROBOT_ROLES_METADATA) == 12
    assert len(ROBOT_TEAM_PROFILES) == 6
    assert len(SEARCH_DATA_SOURCES) == 35
    assert "github" in SEARCH_DATA_SOURCES
    assert "ai_communities" in SEARCH_DATA_SOURCES
    assert "video_platforms" in SEARCH_DATA_SOURCES
    assert "agent_reach_social_search" in SEARCH_DATA_SOURCES
    assert "opencli_platform_search" in SEARCH_DATA_SOURCES
    assert "opencli_web_read_search" in SEARCH_DATA_SOURCES
    assert "opencli_crawl_scrape" in SEARCH_DATA_SOURCES
    assert "openalex_author_institution_search" in SEARCH_DATA_SOURCES
    assert "semantic_scholar_research" in SEARCH_DATA_SOURCES
    assert "education_competition_monitor" in SEARCH_DATA_SOURCES
    assert "regulatory_filings_global" in SEARCH_DATA_SOURCES
    assert "funding_private_market" in SEARCH_DATA_SOURCES
    assert "market_data_secondary" in SEARCH_DATA_SOURCES
    assert {
        "people_data_labs_people",
        "x_recent_posts_search",
        "crustdata_signals",
        "email_discovery_verification",
        "compliant_outreach_and_scraping",
        "scrapling_adaptive_scrape",
        "public_web_snapshot_monitor",
        "browser_use_agent_search",
        "claude_chrome_supervised_search",
        "web_access_cdp_search",
    }.isdisjoint(SEARCH_DATA_SOURCES)
    assert "cap_vla_imitation" in CAPABILITY_STANDARDS
    assert "cap_laser_visual_slam" in CAPABILITY_TRACEABILITY_OVERRIDES
    assert any(item["item"] == "能力与岗位映射" for item in STATIC_DYNAMIC_DECISION_TABLE)
    assert "source_type" in EVIDENCE_RECORD_SCHEMA["required_fields"]


def test_get_capabilities_for_role_includes_ids() -> None:
    capabilities = get_capabilities_for_role("robot_data_infrastructure")
    assert {capability["capability_id"] for capability in capabilities} == {
        "cap_teleop_system",
        "cap_data_alignment",
        "cap_data_cleaning_pipeline",
    }


def test_bp_pipeline_prompts_replace_legacy_deconstructor_prompt() -> None:
    legacy_prompt = Path("app/core/prompts/bp_deconstructor_v2.yaml")

    assert not legacy_prompt.exists()

    claims_prompt = load_system_prompt("bp_claims_v1")
    capability_prompt = load_system_prompt("bp_capability_graph_v1")
    gap_prompt = load_system_prompt("bp_gap_analysis_v1")
    role_prompt = load_system_prompt("bp_role_designer_v1")
    combined = "\n".join([claims_prompt, capability_prompt, gap_prompt, role_prompt])

    assert "stage_id: bp_claims" in claims_prompt
    assert "stage_id: bp_capability_graph" in capability_prompt
    assert "stage_id: bp_gap_analysis" in gap_prompt
    assert "stage_id: bp_role_design" in role_prompt
    assert combined.count("JSON-only") >= 4
    assert "quote 必须是输入材料中的逐字片段" in claims_prompt
    assert "硬件研发（PCB、BOM、电源、结构、量产测试）" in capability_prompt
    assert "resolution\": \"hire|vendor|partner|existing\"" in gap_prompt
    assert "must_have_skills" in role_prompt
    assert "search_strategy" in role_prompt
    assert "why_hire_not_vendor" in role_prompt
    assert "不可编造" in role_prompt


def test_outreach_agent_v2_prompt_controls_tone_and_requires_evidence() -> None:
    prompt = load_system_prompt("outreach_agent_v2")

    assert "JSON-only" in prompt
    assert "硬核极客" in prompt
    assert "智能硬件交付" in prompt
    assert "不可编造候选人经历" in prompt
    assert "candidate_evidence" in prompt
    assert "tone_control" in prompt


def test_chunking_and_stable_ids() -> None:
    text = "short\n\n" + ("具身智能数据采集 " * 10) + "\n\n" + ("Diffusion Policy " * 10)
    chunks = chunk_markdown(text)
    assert len(chunks) == 2
    assert stable_point_id("cand_1", 0) == stable_point_id("cand_1", 0)
    assert stable_point_id("cand_1", 0) != stable_point_id("cand_1", 1)


def test_service_config_defaults_exist() -> None:
    config = load_app_config()
    assert config.default_service_name("document_parser") == "auto_document_parser"
    assert config.default_service_name("evaluation") == "self_rsi_evaluator"
    assert config.service("self_rsi_evaluator").provider == "self_rsi"
    assert config.service("self_rsi_evaluator").model_extra["suite_id"] == "candidate_evaluation_core"
    assert config.service("bge_m3_local").provider == "sentence_transformers"
    assert config.service("qdrant_local").model_extra["vector_size"] == 1024
    assert config.default_service_name("ocr") == "aliyun_ocr"
    assert config.default_service_name("llm") == "openrouter_auto_reasoning"
    assert config.default_service_name("search") == "due_diligence_federated_search"
    assert config.service("due_diligence_federated_search").provider == "due_diligence_federated"
    assert config.service("due_diligence_federated_search").model_extra["source_catalog_service"] == "talent_source_catalog"
    assert config.service("agent_reach_social_search").provider == "agent_reach_social"
    assert config.service("agent_reach_social_search").model_extra["required_commands"] == ["agent-reach", "mcporter", "opencli"]
    assert set(config.service("agent_reach_social_search").model_extra["platform_commands"]) >= {
        "weibo",
        "bilibili",
        "v2ex",
        "zhihu",
        "juejin",
        "csdn",
        "segmentfault",
    }
    assert config.service("opencli_platform_search").provider == "opencli_command"
    assert config.service("opencli_platform_search").model_extra["required_command"] == "opencli"
    assert config.service("opencli_platform_search").model_extra["requires_browser_bridge"] is True
    assert set(config.service("opencli_platform_search").model_extra["platform_commands"]) >= {
        "bilibili",
        "zhihu",
        "xiaohongshu",
        "linkedin",
        "youtube",
        "twitter",
        "reddit",
        "weixin",
    }
    assert config.service("opencli_web_read_search").provider == "opencli_command"
    assert config.service("opencli_web_read_search").model_extra["source_type"] == "adaptive_web_scraping"
    assert config.service("opencli_web_read_search").model_extra["requires_absolute_url"] is True
    assert config.default_service_name("scraping") == "opencli_crawl_scrape"
    assert config.service("opencli_crawl_scrape").provider == "opencli_crawl"
    assert config.service("opencli_crawl_scrape").model_extra["required_command"] == "opencli"
    assert config.service("opencli_crawl_scrape").model_extra["requires_browser_bridge"] is True
    assert config.service("opencli_crawl_scrape").model_extra["command_args"] == [
        "web",
        "read",
        "--url",
        "{url}",
        "-f",
        "json",
    ]
    assert config.service("brave_web_search").provider == "brave_web"
    assert config.service("brave_web_search").model_extra["api_key_env"] == "BRAVE_SEARCH_API_KEY"
    assert config.service("github_repositories").provider == "github_repositories"
    assert config.service("github_repositories").model_extra["endpoint"] == "https://api.github.com/search/repositories"
    assert config.service("github_repositories").model_extra["token_env"] == "GITHUB_TOKEN"
    assert config.service("github_candidates").provider == "github_candidates"
    assert config.service("github_candidates").model_extra["users_endpoint"] == "https://api.github.com/search/users"
    assert config.service("github_candidates").model_extra["repositories_endpoint"] == "https://api.github.com/search/repositories"
    assert config.service("github_candidates").model_extra["code_endpoint"] == "https://api.github.com/search/code"
    assert config.service("github_candidates").model_extra["token_env"] == "GITHUB_TOKEN"
    assert config.service("github_candidates").model_extra["token_required"] is True
    assert config.service("github_users").provider == "github_users"
    assert config.service("github_users").model_extra["endpoint"] == "https://api.github.com/search/users"
    assert config.service("github_code").provider == "github_code"
    assert config.service("github_code").model_extra["endpoint"] == "https://api.github.com/search/code"
    assert config.service("github_topics").provider == "github_topics"
    assert config.service("github_topics").model_extra["endpoint"] == "https://api.github.com/search/topics"
    assert config.service("huggingface_models").provider == "huggingface_models"
    assert config.service("huggingface_models").model_extra["endpoint"] == "https://huggingface.co/api/models"
    assert config.service("huggingface_models").model_extra["token_env"] == "HF_TOKEN"
    assert config.service("openalex_authors_search").provider == "openalex_authors"
    assert config.service("openalex_authors_search").model_extra["endpoint"] == "https://api.openalex.org/authors"
    assert config.service("openalex_institutions_search").provider == "openalex_institutions"
    assert config.service("openalex_institutions_search").model_extra["endpoint"] == "https://api.openalex.org/institutions"
    assert config.service("semantic_scholar_papers_search").provider == "semantic_scholar_papers"
    assert config.service("semantic_scholar_papers_search").model_extra["endpoint"] == "https://api.semanticscholar.org/graph/v1/paper/search"
    assert config.service("semantic_scholar_authors_search").provider == "semantic_scholar_authors"
    assert config.service("semantic_scholar_authors_search").model_extra["endpoint"] == "https://api.semanticscholar.org/graph/v1/author/search"
    assert config.service("education_competition_monitor").provider == "education_competition_monitor"
    assert len(config.service("education_competition_monitor").model_extra["targets"]) >= 8
    assert config.service("openalex_works_search").provider == "openalex_works"
    assert config.service("openalex_works_search").model_extra["endpoint"] == "https://api.openalex.org/works"
    assert config.service("sec_edgar_company_filings").provider == "sec_edgar_company_filings"
    assert config.service("sec_edgar_company_filings").model_extra["company_tickers_url"] == "https://www.sec.gov/files/company_tickers.json"
    assert config.service("sec_company_facts").provider == "sec_company_facts"
    assert config.service("sec_company_facts").model_extra["companyfacts_url_template"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    assert config.service("sec_insider_transactions").provider == "sec_insider_transactions"
    assert config.service("sec_insider_transactions").model_extra["submissions_url_template"] == "https://data.sec.gov/submissions/CIK{cik}.json"
    assert config.service("sec_ownership_activism").provider == "sec_ownership_activism"
    assert config.service("sec_ownership_activism").model_extra["submissions_url_template"] == "https://data.sec.gov/submissions/CIK{cik}.json"
    assert config.service("sec_investment_adviser_reports").provider == "sec_investment_adviser_reports"
    assert config.service("sec_investment_adviser_reports").model_extra["report_url"] == "https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126.zip"
    assert config.service("fdic_bankfind_institutions").provider == "fdic_bankfind_institutions"
    assert config.service("fdic_bankfind_institutions").model_extra["endpoint"] == "https://api.fdic.gov/banks/institutions"
    assert config.service("federal_register_documents").provider == "federal_register_documents"
    assert config.service("federal_register_documents").model_extra["endpoint"] == "https://www.federalregister.gov/api/v1/documents.json"
    assert config.service("cpsc_recalls").provider == "cpsc_recalls"
    assert config.service("cpsc_recalls").model_extra["endpoint"] == "https://www.saferproducts.gov/RestWebServices/Recall"
    assert config.service("fda_enforcement_recalls").provider == "fda_enforcement_recalls"
    assert config.service("fda_enforcement_recalls").model_extra["endpoints"]["device"] == "https://api.fda.gov/device/enforcement.json"
    assert config.service("fda_device_510k").provider == "fda_device_510k"
    assert config.service("fda_device_510k").model_extra["endpoint"] == "https://api.fda.gov/device/510k.json"
    assert config.service("fda_device_events").provider == "fda_device_events"
    assert config.service("fda_device_events").model_extra["endpoint"] == "https://api.fda.gov/device/event.json"
    assert config.service("fda_device_classification").provider == "fda_device_classification"
    assert config.service("fda_device_classification").model_extra["endpoint"] == "https://api.fda.gov/device/classification.json"
    assert config.service("fda_device_registration_listing").provider == "fda_device_registration_listing"
    assert config.service("fda_device_registration_listing").model_extra["endpoint"] == "https://api.fda.gov/device/registrationlisting.json"
    assert config.service("cfpb_consumer_complaints").provider == "cfpb_consumer_complaints"
    assert config.service("cfpb_consumer_complaints").model_extra["endpoint"] == "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
    assert config.service("nhtsa_recalls").provider == "nhtsa_recalls"
    assert config.service("nhtsa_recalls").model_extra["endpoint"] == "https://api.nhtsa.gov/recalls/recallsByVehicle"
    assert config.service("epa_echo_facilities").provider == "epa_echo_facilities"
    assert config.service("epa_echo_facilities").model_extra["endpoint"] == "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"
    assert config.service("clinicaltrials_studies").provider == "clinicaltrials_studies"
    assert config.service("clinicaltrials_studies").model_extra["endpoint"] == "https://clinicaltrials.gov/api/v2/studies"
    assert config.service("cms_openpayments").provider == "cms_openpayments"
    assert config.service("cms_openpayments").model_extra["metastore_endpoint"] == "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items"
    assert config.service("cms_openpayments").model_extra["datastore_endpoint_template"] == "https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0"
    assert config.service("gdelt_doc_news").provider == "gdelt_doc_news"
    assert config.service("gdelt_doc_news").model_extra["endpoint"] == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert config.service("gnews_funding_news").provider == "gnews_funding_news"
    assert config.service("gnews_funding_news").model_extra["api_key_env"] == "GNEWS_API_KEY"
    assert config.service("sec_enforcement_search").provider == "sec_enforcement"
    assert config.service("sec_enforcement_search").model_extra["endpoint"] == "https://www.sec.gov/enforcement-litigation/litigation-releases"
    assert config.service("usaspending_awards").provider == "usaspending_awards"
    assert config.service("usaspending_awards").model_extra["endpoint"] == "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    assert config.service("grants_gov_opportunities").provider == "grants_gov_opportunities"
    assert config.service("grants_gov_opportunities").model_extra["endpoint"] == "https://api.grants.gov/v1/api/search2"
    assert config.service("patentsview_patents").provider == "patentsview_patents"
    assert config.service("patentsview_patents").model_extra["endpoint"] == "https://search.patentsview.org/api/v1/patent/"
    assert config.service("ofac_sanctions_lists").provider == "ofac_sanctions_lists"
    assert config.service("ofac_sanctions_lists").model_extra["sdn_xml_url"] == "https://www.treasury.gov/ofac/downloads/sdn.xml"
    assert config.service("due_diligence_federated_search").model_extra["live_search_services"] == [
        "sec_edgar_company_filings",
        "sec_company_facts",
        "sec_insider_transactions",
        "sec_ownership_activism",
        "sec_investment_adviser_reports",
        "fdic_bankfind_institutions",
        "federal_register_documents",
        "cpsc_recalls",
        "fda_enforcement_recalls",
        "fda_device_510k",
        "fda_device_events",
        "fda_device_classification",
        "fda_device_registration_listing",
        "cfpb_consumer_complaints",
        "nhtsa_recalls",
        "epa_echo_facilities",
        "clinicaltrials_studies",
        "cms_openpayments",
        "openalex_works_search",
        "openalex_authors_search",
        "openalex_institutions_search",
        "semantic_scholar_papers_search",
        "semantic_scholar_authors_search",
        "gdelt_doc_news",
        "gnews_funding_news",
        "sec_enforcement_search",
        "usaspending_awards",
        "grants_gov_opportunities",
        "patentsview_patents",
        "ofac_sanctions_lists",
        "github_candidates",
        "github_repositories",
        "github_code",
        "github_topics",
            "github_users",
            "huggingface_models",
            "agent_reach_social_search",
            "opencli_platform_search",
            "opencli_web_read_search",
            "education_competition_monitor",
        ]
    assert config.service("openrouter_auto_reasoning").provider == "openrouter_chat"
    assert config.service("openrouter_auto_reasoning").model_extra["api_key_env"] == "OPENROUTER_API_KEY"
    assert config.service("openrouter_online_research").model_extra["tools"] == [
        {"type": "openrouter:web_search"}
    ]
    assert "robot_role_metadata" in config.skills
    assert "robot_team_profiles" in config.skills
    assert "robot_capability_governance" in config.skills
    assert "robot_capability_traceability" in config.skills
    assert "evidence_record_schema" in config.skills
    assert "search_data_sources" in config.skills
    assert "home_robot_recruiting_scenarios" in config.skills


def test_no_key_or_unavailable_integrations_are_not_registered() -> None:
    config = load_app_config()
    retired_services = {
        "pdl_people_search",
        "x_recent_posts_search",
        "crustdata_signal_search",
        "companies_house_search",
        "courtlistener_search",
        "census_international_trade",
        "fred_series_search",
        "usajobs_search",
        "sam_gov_opportunities",
        "scrapling_adaptive_scrape",
        "browser_use_agent_search",
        "claude_chrome_supervised_search",
        "web_access_cdp_search",
        "hunter_email_finder",
        "zerobounce_email_validation",
        "neverbounce_email_validation",
        "postmark_compliant_email",
        "sendgrid_compliant_email",
        "mailtrap_smtp_email",
        "firecrawl_scrape",
        "apify_actor_run",
        "brightdata_web_unlocker",
        "browserbase_session",
        "public_web_snapshot_monitor",
        "token_plan_anthropic",
    }

    assert retired_services.isdisjoint(config.services)
    # Email capabilities are first-class registered services; without keys they
    # surface as missing_key instead of pretending the capability doesn't exist.
    assert config.default_service_name("email_delivery") == "resend_email_delivery"
    assert config.default_service_name("email_discovery") == "hunter_email_discovery"
    assert config.default_service_name("email_verification") == "zerobounce_email_verification"
    assert config.default_service_name("scraping") == "opencli_crawl_scrape"

    status = get_integration_status(config)
    services = {service["name"]: service for service in status["services"]}
    assert retired_services.isdisjoint(services)
    # Only the explicitly onboarded email capabilities may sit in missing_key
    # while their credentials are pending; everything else must be keyed or retired.
    missing_key_types = {
        service["type"] for service in services.values() if service["status"] == "missing_key"
    }
    assert missing_key_types <= {"email_delivery", "email_discovery", "email_verification"}


def test_search_source_layers_reference_real_routable_providers() -> None:
    config = load_app_config()
    router = ServiceRouter(config)
    for layer_name, metadata in SEARCH_SOURCE_LAYER_METADATA.items():
        services = tuple(str(service) for service in metadata.get("services", ()))
        assert services, f"{layer_name} must map to at least one real search provider"
        for service_name in services:
            assert config.service(service_name).type == "search"
            provider = router.search(service_name)
            assert callable(getattr(provider, "search", None)), service_name

        source_layers = {name: name == layer_name for name in SEARCH_SOURCE_LAYER_METADATA}
        selected = _live_services_for_search_config(
            {
                "execution_policy": "bounded_live",
                "source_layers": source_layers,
                "budget": {
                    "max_providers": 50,
                    "per_provider_limit": 1,
                    "timeout_seconds": 1,
                    "max_crawl_pages": 0,
                },
            }
        )
        assert selected == services


def test_router_uses_plain_text_parser_without_embedding(tmp_path: Path) -> None:
    resume = tmp_path / "resume.md"
    resume.write_text("# 候选人\n\nDiffusion Policy 项目经验。", encoding="utf-8")

    router = ServiceRouter(load_app_config())
    parser = router.document_parser("plain_text_document_parser")

    assert parser.parse(str(resume)).startswith("# 候选人")


def test_router_registries_and_structured_output_provider() -> None:
    router = ServiceRouter(load_app_config())

    assert "robot_capability_standards" in router.skill_registry.all()
    assert "robot_team_profiles" in router.skill_registry.all()
    assert "robot_capability_governance" in router.skill_registry.all()
    assert "robot_capability_traceability" in router.skill_registry.all()
    assert "evidence_record_schema" in router.skill_registry.all()
    assert "search_data_sources" in router.skill_registry.all()
    assert "home_robot_recruiting_scenarios" in router.skill_registry.all()
    assert "disabled_mcp" in router.mcp_registry.services()
    assert router.structured_output("outlines_structured_output").model_service == "openrouter_auto_reasoning"
    assert router.llm().model == load_app_config().service("openrouter_auto_reasoning").model_extra["model"]


def test_self_rsi_evaluator_runs_feedback_iteration_cycle() -> None:
    router = ServiceRouter(load_app_config())
    report = router.evaluation("self_rsi_evaluator").evaluate()

    assert report["suite_id"] == "candidate_evaluation_core"
    assert report["rsi_cycle"] == ["evaluate", "test", "feedback", "iterate"]
    assert report["summary"]["case_count"] >= 2
    assert report["summary"]["check_count"] >= report["summary"]["case_count"]
    assert report["status"] in {"passed", "needs_iteration"}
    assert all(case["feedback"] for case in report["case_results"])
    assert report["feedback"]["strengths"] or report["feedback"]["gaps"]
    assert report["iteration"]["next_actions"]
    assert any(item["type"] == "regression_case" for item in report["iteration"]["generated_tests"])


def test_self_rsi_full_mode_uses_search_rag_and_llm_capabilities() -> None:
    class FakeSearchProvider:
        def search(self, query: str, limit: int = 10) -> list[dict]:
            return [
                {
                    "source_key": "fake_live_search",
                    "title": "Robot VLA deployment evidence",
                    "snippet": query,
                    "url": "https://example.test/robot-vla",
                }
            ][:limit]

    class FakeLLMProvider:
        def text(self, prompt: str, max_tokens: int = 64) -> str:
            return f"judge:{max_tokens}:{prompt[:24]}"

    class FakeEmbeddingProvider:
        def embed_texts(self, texts: list[str]):
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeVectorStore:
        def search(self, query_vector, top_k: int = 3) -> list[dict]:
            return [{"candidate_id": "cand_rsi", "content": "本地 RAG 命中真实机器人部署证据", "score": 0.91}][:top_k]

    class FakeRouter:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, service_name: str | None = None):
            self.calls.append(f"search:{service_name or 'default'}")
            return FakeSearchProvider()

        def llm(self, service_name: str | None = None):
            self.calls.append(f"llm:{service_name or 'default'}")
            return FakeLLMProvider()

        def embedding(self, service_name: str | None = None):
            self.calls.append(f"embedding:{service_name or 'default'}")
            return FakeEmbeddingProvider()

        def vector_store(self, service_name: str | None = None):
            self.calls.append(f"vector_store:{service_name or 'default'}")
            return FakeVectorStore()

    fake_router = FakeRouter()
    report = ServiceRouter(load_app_config()).evaluation("self_rsi_evaluator").evaluate(
        mode="full",
        allow_live=True,
        router=fake_router,
        max_live_results=1,
    )
    trace = {item["capability"]: item for item in report["capability_trace"]}

    assert report["mode"] == "full"
    assert trace["candidate_evaluation"]["status"] == "used"
    assert trace["live_search"]["status"] == "used"
    assert trace["llm_judge"]["status"] == "used"
    assert trace["rag_vector"]["status"] == "used"
    assert report["full_mode_artifacts"]["live_search"]["result_count"] == 1
    assert report["full_mode_artifacts"]["llm_judge"]["status"] == "used"
    assert report["full_mode_artifacts"]["rag_vector"]["result_count"] == 1
    assert fake_router.calls == [
        "search:default",
        "llm:openrouter_evidence_judge",
        "embedding:default",
        "vector_store:default",
    ]


def test_integration_status_exposes_self_rsi_evaluation_api_without_secrets() -> None:
    payload = get_integration_status(load_app_config())
    capability = next(item for item in payload["capabilities"] if item["id"] == "evaluation_api")

    assert capability["status"] == "active"
    assert capability["connected"] is True
    assert capability["connected_name_zh"] == "自我 RSI 评估器"
    assert capability["code_path"] == "app/providers/evaluation.py"
    assert "self_rsi_evaluator" in json.dumps(capability, ensure_ascii=False)
    assert "api_key" not in json.dumps(capability, ensure_ascii=False).lower()


def test_opencli_browser_bridge_gap_is_reported_as_manual_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.integration_status as integration_status

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else f"/usr/bin/{command}"

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert args == ["opencli", "doctor"]
        assert capture_output is True
        assert text is True
        assert check is False
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="[MISSING] Extension: not connected\n[FAIL] Connectivity: failed (Browser Bridge extension not connected)",
            stderr="",
        )

    monkeypatch.setattr(integration_status.shutil, "which", fake_which)
    monkeypatch.setattr(integration_status.subprocess, "run", fake_run)

    status = get_integration_status(load_app_config())
    services = {service["name"]: service for service in status["services"]}
    opencli_scrape = services["opencli_crawl_scrape"]
    opencli_platform = services["opencli_platform_search"]

    assert opencli_scrape["status"] == "manual_setup"
    assert opencli_platform["status"] == "manual_setup"
    assert {
        "type": "browser_bridge",
        "name": "OpenCLI Browser Bridge",
        "present": False,
        "command": "opencli",
        "reason": "Browser Bridge extension not connected",
    } in opencli_scrape["runtime_requirements"]


def test_slam_capability_traceability_has_route_breakdown_and_evidence_requirements() -> None:
    capability = get_capability_traceability("cap_laser_visual_slam")
    role_traceability = get_role_capability_traceability("slam_navigation_expert")

    assert capability["validation_status"] == "unverified_static_baseline"
    assert any(route["route_id"] == "sensor_calibration_sync" for route in capability["route_breakdown"])
    assert any(requirement["source_type"] == "academic" for requirement in capability["evidence_requirements"])
    assert role_traceability["static_base"]["capability_ids"] == [
        "cap_laser_visual_slam",
        "cap_dynamic_obstacle_avoidance",
        "cap_long_term_localization",
    ]
    assert "能力是否仍应列为必备" in role_traceability["dynamic_calibration_targets"]


def test_home_robot_recruiting_scenarios_cover_a_b_c_d() -> None:
    workflows = HOME_ROBOT_RECRUITING_SCENARIOS["workflows"]

    assert set(workflows) == {
        "scenario_a_job_profile_jd",
        "scenario_b_talent_map",
        "scenario_c_candidate_evaluation",
        "scenario_d_weekly_report",
    }
    assert "生成 JD" in workflows["scenario_a_job_profile_jd"]["workflow"]
    assert "触达策略" in workflows["scenario_b_talent_map"]["output_fields"]
    assert workflows["scenario_c_candidate_evaluation"]["scoring_weights"]["核心技术能力匹配度"] == 25
    assert workflows["scenario_d_weekly_report"]["name_zh"] == "场景 D：招聘周报"
    assert "MCP Connectors" in HOME_ROBOT_RECRUITING_SCENARIOS["infrastructure_layer"]
    assert "知识库持续进化" in HOME_ROBOT_RECRUITING_SCENARIOS["data_flywheel"]


def test_orchestrator_meta_is_frontend_protocol_source() -> None:
    meta = get_meta()

    assert meta["scenarios"]
    assert meta["task_statuses"]["done"]["name_zh"] == "已完成"
    assert meta["task_statuses"]["cancelled"]["name_zh"] == "已取消"
    assert all("steps" in scenario for scenario in meta["scenarios"])


def test_frontend_surfaces_live_step_outputs_for_mobile() -> None:
    project_page_source = Path("frontend/src/pages/ProjectDetailPage.tsx").read_text(encoding="utf-8")
    live_summary_source = Path("frontend/src/features/projects/components/LiveTaskSummary.tsx").read_text(encoding="utf-8")

    assert "LiveTaskSummary" in project_page_source
    assert "任务实时日志" in live_summary_source
    assert "搜索运行追踪" in live_summary_source
    assert "候选人线索入库" in live_summary_source
    assert "卡住" not in project_page_source


def test_frontend_polls_even_when_sse_stream_is_open_for_mobile_cloudflare() -> None:
    hook_source = Path("frontend/src/shared/hooks/useTaskStream.ts").read_text(encoding="utf-8")

    assert "const source = new EventSource(taskStreamUrl(taskId))" in hook_source
    assert "scheduleSnapshotRefresh()" in hook_source
    assert "startFallbackPolling()" in hook_source
    assert "Task stream disconnected; falling back to task polling." in hook_source


def test_frontend_uses_ts_entry_and_has_no_legacy_workbench() -> None:
    index_source = Path("frontend/index.html").read_text(encoding="utf-8")
    ts_main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    active_app_source = Path("frontend/src/app/App.tsx").read_text(encoding="utf-8")
    legacy_paths = [
        Path("frontend/src/main.jsx"),
        Path("frontend/src/App.jsx"),
        Path("frontend/src/api.js"),
        Path("frontend/src/agent"),
        Path("frontend/src/components"),
        Path("frontend/src/hooks"),
        Path("frontend/src/workbench"),
        Path("frontend/src/App.css"),
        Path("frontend/src/assets/react.svg"),
        Path("frontend/src/assets/vite.svg"),
        Path("frontend/src/assets/hero.png"),
    ]

    assert 'src="/src/main.tsx"' in index_source
    assert 'import App from "./app/App"' in ts_main_source
    assert "RouterProvider" in active_app_source
    assert [str(path) for path in legacy_paths if path.exists()] == []


def test_generated_runtime_artifacts_are_not_versioned() -> None:
    forbidden_tracked_patterns = [
        r"^artifacts/",
        r"^e2e-hanno-report\.(json|md)$",
        r"^test-results/",
        r"^data/ocr_smoke\.png$",
    ]
    tracked_files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    forbidden_tracked = [
        path
        for path in tracked_files
        if any(re.search(pattern, path) for pattern in forbidden_tracked_patterns)
    ]
    ignored_paths = [
        "artifacts/e2e_evidence/e2e-run.json",
        "artifacts/e2e_reports/report.md",
        "artifacts/e2e_hanno/screenshots/project-detail.png",
        "test-results/.last-run.json",
        "data/ocr_smoke.png",
    ]

    assert forbidden_tracked == []
    for path in ignored_paths:
        assert subprocess.run(["git", "check-ignore", "-q", path], check=False).returncode == 0


def test_active_frontend_api_client_wraps_project_workspace_endpoints() -> None:
    api_source = Path("frontend/src/features/projects/api.ts").read_text(encoding="utf-8")
    auth_source = Path("frontend/src/features/auth/api.ts").read_text(encoding="utf-8")
    client_source = Path("frontend/src/shared/api/client.ts").read_text(encoding="utf-8")
    expected_functions = {
        "getProject": "/projects/",
        "listProjects": "/projects",
        "uploadProjectMaterial": "/materials/upload",
        "previewProjectFromBp": "/preview-from-bp",
        "initializeProjectFromBp": "/initialize-from-bp",
        "runProjectScenario": "/scenarios/run",
        "confirmTask": "/tasks/",
        "querySegmentCandidates": "/segments/query",
        "createOutreachDraft": "/outreach/draft",
        "sendOutreachDraft": "/outreach/send",
        "saveWeeklyReport": "/reports/weekly",
        "getCandidateSearchSchedules": "/candidate-search-schedules",
    }

    for function_name, path in expected_functions.items():
        assert re.search(rf"export\s+(?:async\s+)?function\s+{function_name}\b", api_source)
        assert path in api_source
    assert "export async function loginWithCompanyEmail" in auth_source
    assert "/auth/login" in auth_source
    assert "setJwtTokenProvider" in client_source


def test_frontend_capability_registry_productizes_all_backend_paths() -> None:
    registry_source = Path("frontend/src/capabilities/capabilityRegistry.js").read_text(encoding="utf-8")
    backend_paths = set(app.openapi()["paths"])
    registry_paths = {
        match.group(1)
        for match in re.finditer(
            r"^\s*'([^']+)':\s*'(?:productized|system|closed)'",
            registry_source,
            flags=re.MULTILINE,
        )
    }

    assert sorted(backend_paths - registry_paths) == []
    assert sorted(registry_paths - backend_paths) == []
    assert "/projects/{project_id}/candidates/{job_candidate_id}/compliance-review" in registry_paths
    for status in ["productized", "system", "closed"]:
        assert status in registry_source
    for artifact_type in [
        "search_plan",
        "search_results",
        "evidence_records",
        "intel_brief",
        "archive_record",
        "watchlist_run",
        "resume_ingest",
        "candidate_matches",
        "rsi_report",
        "workflow_snapshot",
        "outreach_draft",
        "outreach_history",
        "segment",
        "weekly_report",
        "candidate_search_schedule",
    ]:
        assert artifact_type in registry_source


def test_frontend_search_capability_chain_requires_human_confirmation() -> None:
    registry_source = Path("frontend/src/capabilities/capabilityRegistry.js").read_text(encoding="utf-8")
    chain_start = registry_source.index("search_intel_pipeline")

    assert registry_source.index("/search/plan", chain_start) < registry_source.index("/search/run", chain_start)
    assert registry_source.index("/search/run", chain_start) < registry_source.index("/search/evidence", chain_start)
    assert registry_source.index("/search/evidence", chain_start) < registry_source.index("/search/brief", chain_start)
    assert registry_source.index("/search/archive", chain_start) > registry_source.index("/search/brief", chain_start)
    assert "requiresConfirmation: true" in registry_source[chain_start:]
    assert "writeScope: 'optional_archive'" in registry_source[chain_start:]


def test_frontend_chat_shell_recommends_without_auto_execution() -> None:
    registry_source = Path("frontend/src/capabilities/capabilityRegistry.js").read_text(encoding="utf-8")

    assert "export function detectIntent" in registry_source
    assert "export function getCapabilitiesByWorkspace" in registry_source
    assert "export function suggestCapabilitiesForInput" in registry_source
    assert "requiresConfirmation: true" in registry_source
    assert "writeScope: 'optional_archive'" in registry_source
    assert "ChatShell" not in registry_source


def test_db_task_store_persists_audit_events_and_cancel() -> None:
    task = task_store.create("A", "我们想招一个家庭机器人 VLA 算法工程师")
    event = task_store.append_event(
        task.task_id,
        AgentEventCreate(
            type="summary",
            agent_id="orchestrator",
            message="unit audit event",
            data={"raw_thought": "must not leak", "summary": "safe"},
            status="processing",
        ),
    )
    snapshot = task_store.snapshot(task.task_id)
    cancelled = task_store.cancel(task.task_id)

    assert event is not None
    assert snapshot is not None
    assert snapshot["scenario_id"] == "A"
    assert any(item["message"] == "unit audit event" for item in snapshot["audit_events"])
    assert "raw_thought" not in json.dumps(snapshot["audit_events"], ensure_ascii=False)
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert any(item["type"] == "cancelled" for item in cancelled["audit_events"])


def test_run_request_scenario_is_dynamic_in_openapi() -> None:
    schema = app.openapi()
    scenario_schema = schema["components"]["schemas"]["RunRequest"]["properties"]["scenario"]
    run_properties = schema["components"]["schemas"]["RunRequest"]["properties"]

    assert scenario_schema["type"] == "string"
    assert "enum" not in scenario_schema
    assert "frontend_state" in run_properties
    assert "/search/plan" in schema["paths"]
    assert "/search/run" in schema["paths"]
    assert "/search/evidence" in schema["paths"]
    assert "/search/brief" in schema["paths"]
    assert "/search/archive" in schema["paths"]
    assert "/search/archive/recent" in schema["paths"]
    assert "/search/archive/diff" in schema["paths"]
    assert "/search/watchlist/run" in schema["paths"]
    assert "/tasks/{task_id}/probe-feedback" in schema["paths"]
    assert "/tasks/{task_id}/artifacts" in schema["paths"]
    assert "/tasks/{task_id}/stream" in schema["paths"]
    assert "/tasks/{task_id}/cancel" in schema["paths"]
    assert "/tasks/{task_id}/retry" in schema["paths"]
    assert "/workflow/meta" in schema["paths"]
    assert "/workflow/sessions" in schema["paths"]
    assert "/workflow/sessions/{task_id}/nodes/{node_id}/run" in schema["paths"]
    assert "/workflow/sessions/{task_id}/nodes/{node_id}/skip" in schema["paths"]
    assert "/workflow/sessions/{task_id}/nodes/{node_id}/retry" in schema["paths"]
    assert "/workflows/validate" in schema["paths"]
    assert "/workflows/run" in schema["paths"]
    assert "/rsi/evaluate" in schema["paths"]


def test_atomic_workflow_api_exposes_nodes_and_controls_single_step() -> None:
    client = TestClient(app)

    meta_response = client.get("/workflow/meta")
    create_response = client.post(
        "/workflow/sessions",
        json={
            "scenario": "A",
            "input": "我们想招一个家庭机器人 VLA 算法工程师",
            "team_constraint": "真机泛化",
            "aperture_weight": 0.7,
            "frontend_state": {"mode": "atomic"},
        },
    )

    assert meta_response.status_code == 200
    meta = meta_response.json()
    scenario_a = next(scenario for scenario in meta["scenarios"] if scenario["id"] == "A")
    assert scenario_a["nodes"][0]["node_id"] == "A.0"
    assert scenario_a["nodes"][0]["label"] == "拆解需求"
    assert scenario_a["nodes"][0]["outputs"] == ["role_key", "role_name", "tech_layer"]

    assert create_response.status_code == 200
    session = create_response.json()
    assert session["status"] == "processing"
    assert session["workflow"]["mode"] == "atomic"
    assert session["workflow"]["nodes"][0]["status"] == "idle"

    run_response = client.post(f"/workflow/sessions/{session['task_id']}/nodes/A.0/run")
    assert run_response.status_code == 200
    after_run = run_response.json()
    first_node = after_run["workflow"]["nodes"][0]
    assert first_node["status"] == "done"
    assert first_node["output"]["role_key"] == "vla_embodied_expert"
    assert after_run["workflow"]["artifacts"]["role_key"] == "vla_embodied_expert"
    assert any(event["data"].get("atomic_node_id") == "A.0" for event in after_run["audit_events"])

    skip_response = client.post(f"/workflow/sessions/{session['task_id']}/nodes/A.1/skip")
    assert skip_response.status_code == 200
    after_skip = skip_response.json()
    assert after_skip["workflow"]["nodes"][1]["status"] == "skipped"

    retry_response = client.post(f"/workflow/sessions/{session['task_id']}/nodes/A.0/retry")
    assert retry_response.status_code == 200
    after_retry = retry_response.json()
    assert after_retry["workflow"]["nodes"][0]["run_count"] == 2
    assert after_retry["workflow"]["nodes"][0]["status"] == "done"


def test_api_prefix_routes_return_json_not_spa_html() -> None:
    client = TestClient(app)

    meta_response = client.get("/api/scenarios/meta")
    integrations_response = client.get("/api/integrations/status")
    openapi_response = client.get("/api/openapi.json")

    assert meta_response.status_code == 200
    assert meta_response.headers["content-type"].startswith("application/json")
    assert meta_response.json()["scenarios"]
    assert integrations_response.status_code == 200
    assert integrations_response.headers["content-type"].startswith("application/json")
    assert integrations_response.json()["capabilities"]
    assert openapi_response.status_code == 200
    assert openapi_response.headers["content-type"].startswith("application/json")
    assert "/rsi/evaluate" in openapi_response.json()["paths"]


def test_frontend_index_response_is_not_cached_when_dist_exists() -> None:
    if not Path("frontend/dist/index.html").exists():
        pytest.skip("frontend production build is not available")

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_public_cloudflare_start_script_serializes_restarts() -> None:
    script = Path("scripts/start_public_cloudflare.sh").read_text(encoding="utf-8")

    assert "public_cloudflare.lock" in script
    assert "flock" in script
    assert "exec 9>&-" in script


def test_public_cloudflare_watchdog_checks_public_url_health() -> None:
    watcher = Path("scripts/watch_public_cloudflare.sh").read_text(encoding="utf-8")
    starter = Path("scripts/start_public_cloudflare.sh").read_text(encoding="utf-8")

    assert "public_healthy" in watcher
    assert "FORCE_TUNNEL_RESTART" in watcher
    assert "public_url_healthy" in starter


def test_self_rsi_evaluate_api_accepts_custom_cases_and_returns_iteration_plan() -> None:
    client = TestClient(app)

    response = client.post(
        "/rsi/evaluate",
        json={
            "threshold": 0.95,
            "cases": [
                {
                    "case_id": "sim_only_guardrail",
                    "name": "仿真候选人不能被误判为强实机",
                    "candidate_material": "参与 Isaac Sim 仿真环境搭建和策略训练，主要负责边缘模块。",
                    "target": "家庭机器人 VLA 算法工程师",
                    "team_constraint": "真机泛化",
                    "expectations": {
                        "max_score": 55,
                        "allowed_levels": ["备选", "不推荐"],
                        "required_risk_terms": ["真实机器人/硬件部署"],
                        "required_output_paths": ["decision_sandbox.feedback_loop.status"],
                    },
                },
                {
                    "case_id": "deliberate_gap_for_iteration",
                    "name": "刻意暴露未接入外部证据的迭代缺口",
                    "candidate_material": (
                        "主导家庭机器人 VLA 项目，负责第一视角遥操作数据、Action Token、"
                        "Diffusion Policy，ROS 实机部署，控制链路延迟 12ms。"
                    ),
                    "target": "家庭机器人 VLA 算法工程师",
                    "team_constraint": "真机动作延迟高",
                    "expectations": {
                        "min_score": 70,
                        "required_evidence_flags": {"真实机器人证据": True},
                        "required_output_paths": ["decision_sandbox.evidence_dependency_contract.guardrail"],
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_iteration"
    assert payload["summary"]["case_count"] == 2
    assert payload["feedback"]["gaps"]
    assert any(gap["case_id"] == "deliberate_gap_for_iteration" for gap in payload["feedback"]["gaps"])
    assert any(item["source_case_id"] == "deliberate_gap_for_iteration" for item in payload["iteration"]["generated_tests"])
    assert all("candidate_material" not in gap for gap in payload["feedback"]["gaps"])


def test_self_rsi_recruiting_effect_case_ranks_candidates_against_job_rubric() -> None:
    report = ServiceRouter(load_app_config()).evaluation("self_rsi_evaluator").evaluate(
        suite="recruiting_effect_v1",
        threshold=1.0,
        cases=[
            {
                "case_type": "job_candidate_ranking",
                "case_id": "fde_business_builder_ranking",
                "name": "AI Native FDE 岗位应把业务闭环 builder 排在 prompt operator 前面",
                "job_profile": {
                    "title": "AI Native FDE / Agentic Builder",
                    "must_have_skills": ["全栈开发", "Agentic workflow"],
                    "scoring_rubric": {
                        "完整业务工程闭环（问题定义/上线/指标复盘）": 3,
                        "业务抽象能力（订单/支付/风控）": 2,
                    },
                    "rationale": {
                        "must_have_signals": ["AI coding"],
                        "risk_signals": ["只会写 prompt"],
                    },
                },
                "candidates": [
                    {
                        "candidate_id": "cand_prompt_operator",
                        "name": "Prompt Operator",
                        "candidate_material": "使用 AI coding 编写 prompt demo，了解 Agentic workflow，只会写 prompt。",
                    },
                    {
                        "candidate_id": "cand_fde_builder",
                        "name": "FDE Builder",
                        "candidate_material": (
                            "主导订单支付风控系统上线，问题定义到指标复盘，全栈开发 "
                            "Agentic workflow AI coding。"
                        ),
                    },
                    {
                        "candidate_id": "cand_general_fullstack",
                        "name": "General Fullstack",
                        "candidate_material": "负责后台 CRUD 和报表，全栈开发，交付过内部工具。",
                    },
                ],
                "expectations": {
                    "top_candidate_id": "cand_fde_builder",
                    "ranking_order": ["cand_fde_builder", "cand_general_fullstack", "cand_prompt_operator"],
                    "min_top_score": 80,
                    "score_gap_min": 20,
                    "max_scores": {"cand_prompt_operator": 60},
                    "allowed_levels": {"cand_fde_builder": ["强推"], "cand_prompt_operator": ["不推荐", "备选"]},
                    "required_risk_terms": {"cand_prompt_operator": ["只会写 prompt"]},
                },
            }
        ],
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 1
    case = report["case_results"][0]
    assert case["case_type"] == "job_candidate_ranking"
    summary = case["result_summary"]
    assert summary["top_candidate_id"] == "cand_fde_builder"
    assert [item["candidate_id"] for item in summary["ranked_candidates"]] == [
        "cand_fde_builder",
        "cand_general_fullstack",
        "cand_prompt_operator",
    ]
    assert summary["ranked_candidates"][0]["score"] >= 80
    assert "candidate_material" not in json.dumps(report, ensure_ascii=False)
    assert "订单支付风控系统上线" not in json.dumps(report, ensure_ascii=False)


def test_self_rsi_recruiting_effect_suite_has_default_offline_cases() -> None:
    response = TestClient(app).post(
        "/rsi/evaluate",
        json={"suite": "recruiting_effect_v1", "threshold": 1.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suite_id"] == "recruiting_effect_v1"
    assert payload["status"] == "passed"
    assert payload["summary"]["case_count"] >= 15
    assert all(case["case_type"] == "job_candidate_ranking" for case in payload["case_results"])
    case_ids = [case["case_id"] for case in payload["case_results"]]
    assert len(case_ids) == len(set(case_ids))
    targets = " ".join(str(case["target"]) for case in payload["case_results"])
    for expected_domain in [
        "AI Native FDE",
        "VLA",
        "数据平台",
        "运动控制",
        "嵌入式",
        "SLAM",
        "评测",
        "现场",
    ]:
        assert expected_domain in targets
    assert payload["operator_summary"]["manual_labeling_required"] is False
    assert payload["operator_summary"]["human_role"] == "decision_maker"
    assert payload["operator_summary"]["human_touch_level"] == "light"
    assert payload["operator_summary"]["automation_default"] == "ai_runs_full_pipeline"
    assert payload["operator_summary"]["human_decisions"] == ["approve", "reject", "adjust"]
    assert "manual_tagging" not in payload["operator_summary"]["ai_automation_scope"]
    assert payload["operator_summary"]["review_count"] == 0
    assert payload["operator_summary"]["visible_case_count"] <= 5
    assert len(payload["operator_summary"]["coverage_domains"]) <= 8
    assert all("matched_skills" not in card for card in payload["operator_summary"]["visible_case_cards"])
    assert "candidate_material" not in json.dumps(payload, ensure_ascii=False)


def test_self_rsi_full_mode_api_uses_router_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEvaluationProvider:
        def evaluate(self, **kwargs) -> dict:
            return {
                "mode": kwargs["mode"],
                "allow_live": kwargs["allow_live"],
                "max_live_results": kwargs["max_live_results"],
                "router_passed": kwargs["router"] is fake_router,
                "capability_trace": [{"capability": "live_search", "status": "used"}],
            }

    class FakeRouter:
        def evaluation(self, service_name: str | None = None):
            return FakeEvaluationProvider()

    fake_router = FakeRouter()
    monkeypatch.setattr(api_main, "get_router", lambda: fake_router)
    client = TestClient(app)

    response = client.post(
        "/rsi/evaluate",
        json={"mode": "full", "allow_live": True, "max_live_results": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "full"
    assert payload["allow_live"] is True
    assert payload["max_live_results"] == 1
    assert payload["router_passed"] is True


def test_search_api_exposes_due_diligence_plan_and_safe_results() -> None:
    client = TestClient(app)

    plan_response = client.post(
        "/search/plan",
        json={"query": "机器人 公司 融资 年报 研发人员", "limit": 8},
    )
    run_response = client.post(
        "/search/run",
        json={"query": "机器人 公司 融资 年报 研发人员", "limit": 4, "service": " "},
    )
    empty_response = client.post("/search/plan", json={"query": "   "})

    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["mode"] == "financial_due_diligence_intelligence"
    assert any(source["source_key"] == "regulatory_filings_global" for source in plan["recommended_sources"])
    assert any("不绕过登录" in guardrail for guardrail in plan["guardrails"])

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["limit"] == 4
    assert payload["results"]
    assert payload["results"][0]["source_type"] == "source_catalog"
    assert payload["results"][0]["retrieval_status"] == "planned"

    assert empty_response.status_code == 422


def test_agent_reach_social_provider_runs_platform_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        if command in {"agent-reach", "mcporter", "opencli"}:
            return f"/usr/bin/{command}"
        return original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        check: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        command_text = " ".join(args)
        if "weibo.search_content" in command_text:
            stdout = json.dumps({"results": [{"title": "微博 VLA 讨论", "url": "https://weibo.com/1", "text": "机器人 Demo"}]})
        elif "site:bilibili.com/video" in command_text:
            stdout = json.dumps([{"title": "B站机器人视频", "url": "https://bilibili.com/video/BV1"}])
        elif "site:v2ex.com/t" in command_text:
            stdout = json.dumps({"results": [{"title": "V2EX robot thread", "url": "https://v2ex.com/t/1"}]})
        else:
            stdout = json.dumps([])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = ServiceRouter(load_app_config()).search("agent_reach_social_search")
    results = provider.search("机器人 VLA demo", limit=1)
    plan = provider.plan("机器人 VLA demo", limit=1)

    assert any(call[0] == "mcporter" for call in calls)
    assert any("site:bilibili.com/video" in " ".join(call) for call in calls)
    assert any("site:v2ex.com/t" in " ".join(call) for call in calls)
    assert results
    assert {result["platform"] for result in results} >= {"weibo", "bilibili", "v2ex"}
    assert results[0]["source_key"] == "agent_reach_social_search"
    assert results[0]["source_type"] == "social_platform_search"
    assert results[0]["retrieval_status"] == "retrieved"
    assert plan["mode"] == "agent_reach_social_search"
    assert plan["supported_platforms"]
    assert any("不绕过" in guardrail for guardrail in plan["guardrails"])


def test_search_evidence_api_returns_traceable_review_records() -> None:
    client = TestClient(app)

    response = client.post(
        "/search/evidence",
        json={
            "query": "机器人 公司 融资 年报 研发人员",
            "claim": "目标公司研发投入和融资热度正在上升",
            "limit": 6,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["claim"] == "目标公司研发投入和融资热度正在上升"
    assert payload["records"]
    assert payload["review"]["record_count"] == len(payload["records"])
    assert payload["review"]["cross_check_status"] in {
        "ready_for_human_review",
        "needs_authoritative_source",
        "single_source_only",
    }
    assert any(
        record["source_tier"] == "primary_or_authoritative"
        for record in payload["records"]
    )
    first_record = payload["records"][0]
    assert first_record["record_id"].startswith("ev_")
    assert first_record["validation_status"] in {
        "planned_authoritative_source",
        "planned_unverified",
        "requires_interview_confirmation",
        "single_source",
    }
    assert first_record["confidence"] > 0
    assert "保留来源" in first_record["compliance_notes"][0]
    assert payload["review"]["next_actions"]


def test_search_brief_api_returns_due_diligence_report_sections() -> None:
    client = TestClient(app)

    response = client.post(
        "/search/brief",
        json={
            "query": "机器人 公司 融资 年报 研发人员",
            "claim": "目标公司研发投入和融资热度正在上升",
            "limit": 6,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["brief_type"] == "financial_due_diligence_intelligence_brief"
    assert payload["executive_summary"]["status"] == "ready_for_human_review"
    assert payload["priority_evidence"]
    assert payload["priority_evidence"][0]["record_id"].startswith("ev_")
    assert payload["risk_register"]
    assert payload["intelligence_gaps"]
    assert payload["next_search_actions"]
    assert any(action["action"] == "run_query_template" for action in payload["next_search_actions"])
    assert any("不是投资建议" in guardrail for guardrail in payload["report_guardrails"])


def test_search_archive_persists_brief_to_jsonl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "intelligence_archive.jsonl"
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))
    client = TestClient(app)

    archive_response = client.post(
        "/search/archive",
        json={
            "query": "机器人 公司 融资 年报 研发人员",
            "claim": "目标公司研发投入和融资热度正在上升",
            "limit": 5,
            "artifact_type": "brief",
        },
    )
    recent_response = client.get("/search/archive/recent", params={"limit": 5})

    assert archive_response.status_code == 200
    archive_payload = archive_response.json()
    assert archive_payload["archive_id"].startswith("intel_")
    assert archive_payload["artifact_type"] == "brief"
    assert archive_payload["archive_path"] == str(archive_path)
    assert archive_path.exists()

    assert recent_response.status_code == 200
    recent_payload = recent_response.json()
    assert recent_payload["records"]
    latest = recent_payload["records"][0]
    assert latest["archive_id"] == archive_payload["archive_id"]
    assert latest["artifact_type"] == "brief"
    assert latest["artifact"]["brief_type"] == "financial_due_diligence_intelligence_brief"


def test_search_archive_diff_detects_source_and_risk_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "intelligence_archive.jsonl"
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))
    archive = IntelligenceArchive()
    client = TestClient(app)

    archive.append(
        "brief",
        {
            "query": "机器人 公司 融资",
            "claim": "融资热度变化",
            "brief_type": "financial_due_diligence_intelligence_brief",
            "executive_summary": {
                "status": "needs_authoritative_source",
                "source_tier_counts": {"licensed_or_structured_database": 1},
            },
            "priority_evidence": [
                {"source_key": "funding_private_market"},
            ],
            "watchlist_item": {"name": "机器人融资", "tags": ["funding"]},
            "risk_register": [
                {"risk": "missing_authoritative_source"},
            ],
            "intelligence_gaps": ["缺少监管披露、公告、招股书、年报或公司一手材料。"],
        },
    )
    archive.append(
        "brief",
        {
            "query": "机器人 公司 融资",
            "claim": "融资热度变化",
            "brief_type": "financial_due_diligence_intelligence_brief",
            "executive_summary": {
                "status": "ready_for_human_review",
                "source_tier_counts": {
                    "licensed_or_structured_database": 1,
                    "primary_or_authoritative": 1,
                },
            },
            "priority_evidence": [
                {"source_key": "funding_private_market"},
                {"source_key": "regulatory_filings_global"},
            ],
            "watchlist_item": {"name": "机器人融资", "tags": ["funding"]},
            "risk_register": [
                {"risk": "human_review_required"},
            ],
            "intelligence_gaps": ["暂无结构性缺口；下一步重点是原文核验、冲突证据和人工判断。"],
        },
    )

    response = client.get(
        "/search/archive/diff",
        params={"artifact_type": "brief", "watchlist_name": "机器人融资"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["watchlist_name"] == "机器人融资"
    assert payload["changed"] is True
    assert payload["source_changes"]["added"] == ["regulatory_filings_global"]
    assert payload["risk_changes"]["added"] == ["human_review_required"]
    assert payload["risk_changes"]["removed"] == ["missing_authoritative_source"]
    assert payload["status_change"] == {
        "previous": "needs_authoritative_source",
        "current": "ready_for_human_review",
        "changed": True,
    }
    assert payload["source_tier_count_change"]["deltas"]["primary_or_authoritative"]["delta"] == 1


def test_search_watchlist_run_archives_multiple_briefs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "watchlist_archive.jsonl"
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))
    client = TestClient(app)

    response = client.post(
        "/search/watchlist/run",
        json={
            "limit": 4,
            "archive": True,
            "items": [
                {
                    "name": "机器人融资",
                    "query": "机器人 公司 融资 年报 研发人员",
                    "claim": "机器人公司融资和研发投入变化",
                    "tags": ["funding", "robotics"],
                },
                {
                    "name": "VLA 人才",
                    "query": "VLA 机器人 招聘 薪酬",
                    "claim": "VLA 人才供给和薪酬变化",
                    "tags": ["talent", "vla"],
                },
            ],
        },
    )
    recent_response = client.get("/search/archive/recent", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_count"] == 2
    assert payload["archived"] is True
    assert all(result["archive"]["archive_id"].startswith("intel_") for result in payload["results"])
    assert all(result["top_source_keys"] for result in payload["results"])
    assert payload["results"][0]["status"] == "ready_for_human_review"

    assert recent_response.status_code == 200
    recent_payload = recent_response.json()
    assert len(recent_payload["records"]) == 2
    assert {record["artifact"]["watchlist_item"]["name"] for record in recent_payload["records"]} == {
        "机器人融资",
        "VLA 人才",
    }


def test_watchlist_cli_config_runs_and_archives_briefs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "watchlist_cli_archive.jsonl"
    config_path = tmp_path / "watchlist.toml"
    config_path.write_text(
        """
[watchlist]
limit = 4
service = "due_diligence_federated_search"
archive = true

[[items]]
name = "机器人融资"
query = "机器人 公司 融资 年报 研发人员"
claim = "机器人公司融资和研发投入变化"
tags = ["funding", "robotics"]

[[items]]
name = "VLA 人才"
query = "VLA 机器人 招聘 薪酬"
claim = "VLA 人才供给和薪酬变化"
tags = ["talent", "vla"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))

    first_result = run_watchlist(config_path)
    second_result = run_watchlist(config_path)
    records = IntelligenceArchive().recent(limit=10)

    assert Path("config/watchlist.example.toml").exists()
    assert first_result["item_count"] == 2
    assert first_result["archived"] is True
    assert all(item["archive"]["archive_id"].startswith("intel_") for item in first_result["results"])
    assert all(item["diff"]["status"] == "insufficient_history" for item in first_result["results"])
    assert second_result["item_count"] == 2
    assert all(item["diff"]["status"] == "ready" for item in second_result["results"])
    assert all(item["diff"]["watchlist_name"] == item["name"] for item in second_result["results"])
    assert len(records) == 4
    assert {record["artifact"]["watchlist_item"]["name"] for record in records} == {
        "机器人融资",
        "VLA 人才",
    }


def test_watchlist_markdown_report_contains_diff_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "watchlist_report_archive.jsonl"
    config_path = tmp_path / "watchlist.toml"
    report_path = tmp_path / "watchlist_report.md"
    config_path.write_text(
        """
[watchlist]
limit = 4
service = "due_diligence_federated_search"
archive = true

[[items]]
name = "机器人融资"
query = "机器人 公司 融资 年报 研发人员"
claim = "机器人公司融资和研发投入变化"
tags = ["funding", "robotics"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))

    first_result = run_watchlist(config_path)
    second_result = run_watchlist(config_path)
    report_path.write_text(render_markdown_report(second_result), encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")

    assert first_result["results"][0]["diff"]["status"] == "insufficient_history"
    assert second_result["results"][0]["diff"]["status"] == "ready"
    assert "# Intelligence Watchlist Report" in report
    assert "## 机器人融资" in report
    assert "- Diff status: `ready`" in report
    assert "- Added sources:" in report
    assert "- Status change:" in report


def test_watchlist_scheduling_doc_contains_operational_contracts() -> None:
    doc = Path("docs/watchlist_scheduling.md").read_text(encoding="utf-8")

    assert "scripts/run_watchlist.py" in doc
    assert "config/watchlist.example.toml" in doc
    assert "INTELLIGENCE_ARCHIVE_PATH" in doc
    assert "/home/lison/Desktop/zhaoping/data/intelligence_archive.jsonl" in doc
    assert "30 8 * * 1-5" in doc
    assert "systemctl --user enable --now zhaoping-watchlist.timer" in doc
    assert "journalctl --user -u zhaoping-watchlist.service -n 100" in doc
    assert "curl 'http://localhost:8000/search/archive/diff?artifact_type=brief&watchlist_name=机器人融资'" in doc
    assert "without bypassing login, paywalls, robots.txt, or access controls" in doc


def test_search_smoke_script_and_readme_document_live_sources() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    script = Path("scripts/smoke_search_sources.py").read_text(encoding="utf-8")

    active_tokens = {
        "scripts/smoke_search_sources.py",
        "agent_reach_social_search",
        "opencli_platform_search",
        "opencli_web_read_search",
        "opencli_crawl_scrape",
        "github_repositories",
        "huggingface_models",
        "openalex_works_search",
        "openalex_authors_search",
        "openalex_institutions_search",
        "semantic_scholar_papers_search",
        "semantic_scholar_authors_search",
        "education_competition_monitor",
        "sec_edgar_company_filings",
        "sec_company_facts",
        "sec_insider_transactions",
        "sec_ownership_activism",
        "sec_investment_adviser_reports",
        "fdic_bankfind_institutions",
        "federal_register_documents",
        "cpsc_recalls",
        "fda_enforcement_recalls",
        "fda_device_510k",
        "fda_device_events",
        "fda_device_classification",
        "fda_device_registration_listing",
        "cfpb_consumer_complaints",
        "nhtsa_recalls",
        "epa_echo_facilities",
        "clinicaltrials_studies",
        "cms_openpayments",
        "gdelt_doc_news",
        "gnews_funding_news",
        "sec_enforcement_search",
        "usaspending_awards",
        "grants_gov_opportunities",
        "patentsview_patents",
        "ofac_sanctions_lists",
        "BRAVE_SEARCH_API_KEY",
    }
    for token in active_tokens:
        assert token in readme or token in script

    retired_tokens = {
        "pdl_people_search",
        "x_recent_posts_search",
        "crustdata_signal_search",
        "companies_house_search",
        "courtlistener_search",
        "census_international_trade",
        "fred_series_search",
        "usajobs_search",
        "sam_gov_opportunities",
        "scrapling_adaptive_scrape",
        "browser_use_agent_search",
        "claude_chrome_supervised_search",
        "web_access_cdp_search",
        "hunter_email_finder",
        "zerobounce_email_validation",
        "neverbounce_email_validation",
        "postmark_compliant_email",
        "sendgrid_compliant_email",
        "mailtrap_smtp_email",
        "firecrawl_scrape",
        "apify_actor_run",
        "brightdata_web_unlocker",
        "browserbase_session",
        "public_web_snapshot_monitor",
        "https://api.peopledatalabs.com/v5/person/search",
        "https://api.x.com/2/tweets/search/recent",
        "https://api.crustdata.com/web/search/live",
        "https://api.hunter.io/v2/email-finder",
        "https://api.zerobounce.net/v2/validate",
        "https://api.postmarkapp.com/email",
        "https://api.firecrawl.dev/v2/scrape",
        "https://api.company-information.service.gov.uk/search/companies",
        "https://www.courtlistener.com/api/rest/v4/search/",
        "https://github.com/D4Vinci/Scrapling",
        "https://github.com/browser-use/browser-use",
        "https://claude.ai/chrome",
        "https://github.com/eze-is/web-access",
        "https://api.census.gov/data/timeseries/intltrade/imports/hs",
        "https://api.stlouisfed.org/fred/series/search",
        "https://data.usajobs.gov/api/Search",
        "https://api.sam.gov/opportunities/v2/search",
    }
    for token in retired_tokens:
        assert token not in readme
        assert token not in script


def test_integration_status_exposes_capabilities_without_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-openrouter-secret-value")
    monkeypatch.setenv("GITHUB_TOKEN", "unit-github-secret-value")
    monkeypatch.setenv("HF_TOKEN", "unit-hf-secret-value")
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "unit-companies-house-secret-value")
    monkeypatch.setenv("COURTLISTENER_TOKEN", "unit-courtlistener-secret-value")
    monkeypatch.setenv("GNEWS_API_KEY", "unit-gnews-secret-value")
    monkeypatch.setenv("CENSUS_API_KEY", "unit-census-secret-value")
    monkeypatch.setenv("USAJOBS_API_KEY", "unit-usajobs-secret-value")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "unit-usajobs-user-agent-secret-value")
    monkeypatch.setenv("ANTHROPIC_COMPATIBLE_API_KEY", "")

    import app.core.integration_status as integration_status

    monkeypatch.setattr(integration_status.shutil, "which", lambda command: None)
    monkeypatch.setattr(integration_status.importlib.util, "find_spec", lambda module: None)

    status = get_integration_status(load_app_config())
    capabilities = {capability["id"]: capability for capability in status["capabilities"]}

    assert {"search_api", "code_api", "vector_api", "llm_api"}.issubset(capabilities)
    assert capabilities["search_api"]["default_service"] == "due_diligence_federated_search"
    assert capabilities["search_api"]["connected"] is True
    assert capabilities["search_api"]["connected_name_zh"] == "尽调级联邦情报搜索"
    assert capabilities["search_api"]["code_path"] == "app/providers/search.py"
    search_services = {service["name"]: service for service in capabilities["search_api"]["services"]}
    assert search_services["agent_reach_social_search"]["status"] == "missing_tool"
    assert search_services["agent_reach_social_search"]["name_zh"] == "Agent-Reach 社媒搜索"
    assert search_services["agent_reach_social_search"]["code_path"] == "app/providers/search.py"
    assert search_services["openalex_authors_search"]["status"] == "available"
    assert search_services["openalex_authors_search"]["name_zh"] == "OpenAlex 作者搜索"
    assert search_services["openalex_institutions_search"]["status"] == "available"
    assert search_services["semantic_scholar_papers_search"]["status"] == "available"
    assert search_services["semantic_scholar_authors_search"]["status"] == "available"
    assert search_services["education_competition_monitor"]["status"] == "available"
    assert search_services["github_repositories"]["status"] == "available"
    assert search_services["github_repositories"]["name_zh"] == "GitHub 代码仓库搜索"
    assert search_services["huggingface_models"]["status"] == "available"
    assert search_services["huggingface_models"]["name_zh"] == "Hugging Face 模型搜索"
    removed_search_services = {
        "pdl_people_search",
        "x_recent_posts_search",
        "crustdata_signal_search",
        "companies_house_search",
        "courtlistener_search",
        "census_international_trade",
        "fred_series_search",
        "usajobs_search",
        "sam_gov_opportunities",
        "scrapling_adaptive_scrape",
        "browser_use_agent_search",
        "claude_chrome_supervised_search",
        "web_access_cdp_search",
    }
    assert removed_search_services.isdisjoint(search_services)
    assert search_services["sec_company_facts"]["status"] == "available"
    assert search_services["sec_company_facts"]["name_zh"] == "SEC Company Facts 财务事实"
    assert search_services["sec_insider_transactions"]["status"] == "available"
    assert search_services["sec_insider_transactions"]["name_zh"] == "SEC 内部人交易披露"
    assert search_services["sec_ownership_activism"]["status"] == "available"
    assert search_services["sec_ownership_activism"]["name_zh"] == "SEC 重大持股与控制权披露"
    assert search_services["sec_investment_adviser_reports"]["status"] == "available"
    assert search_services["sec_investment_adviser_reports"]["name_zh"] == "SEC 投顾/ERA Form ADV 数据"
    assert search_services["fdic_bankfind_institutions"]["status"] == "available"
    scraping_services = {service["name"]: service for service in capabilities["scraping_api"]["services"]}
    assert scraping_services["opencli_crawl_scrape"]["status"] == "missing_tool"
    assert scraping_services["opencli_crawl_scrape"]["name_zh"] == "OpenCLI 本地抓取"
    assert scraping_services["opencli_crawl_scrape"]["code_path"] == "app/providers/scraping.py"
    assert search_services["fdic_bankfind_institutions"]["name_zh"] == "FDIC BankFind 银行机构"
    assert search_services["federal_register_documents"]["status"] == "available"
    assert search_services["federal_register_documents"]["name_zh"] == "Federal Register 监管文件"
    assert search_services["cpsc_recalls"]["status"] == "available"
    assert search_services["cpsc_recalls"]["name_zh"] == "CPSC 产品召回"
    assert search_services["fda_enforcement_recalls"]["status"] == "available"
    assert search_services["fda_enforcement_recalls"]["name_zh"] == "FDA Enforcement 召回"
    assert search_services["fda_device_510k"]["status"] == "available"
    assert search_services["fda_device_510k"]["name_zh"] == "FDA 510(k) 器械准入"
    assert search_services["fda_device_events"]["status"] == "available"
    assert search_services["fda_device_events"]["name_zh"] == "FDA MAUDE 器械不良事件"
    assert search_services["fda_device_classification"]["status"] == "available"
    assert search_services["fda_device_classification"]["name_zh"] == "FDA 器械分类与产品代码"
    assert search_services["fda_device_registration_listing"]["status"] == "available"
    assert search_services["fda_device_registration_listing"]["name_zh"] == "FDA 器械注册与列名"
    assert search_services["cfpb_consumer_complaints"]["status"] == "available"
    assert search_services["cfpb_consumer_complaints"]["name_zh"] == "CFPB 消费金融投诉"
    assert search_services["nhtsa_recalls"]["status"] == "available"
    assert search_services["nhtsa_recalls"]["name_zh"] == "NHTSA 车辆召回"
    assert search_services["epa_echo_facilities"]["status"] == "available"
    assert search_services["epa_echo_facilities"]["name_zh"] == "EPA ECHO 设施合规"
    assert search_services["clinicaltrials_studies"]["status"] == "available"
    assert search_services["clinicaltrials_studies"]["name_zh"] == "ClinicalTrials.gov 试验登记"
    assert search_services["cms_openpayments"]["status"] == "available"
    assert search_services["cms_openpayments"]["name_zh"] == "CMS Open Payments 医疗付款"
    assert search_services["openalex_works_search"]["status"] == "available"
    assert search_services["openalex_works_search"]["name_zh"] == "OpenAlex 学术作品搜索"
    assert search_services["sec_edgar_company_filings"]["status"] == "available"
    assert search_services["sec_edgar_company_filings"]["name_zh"] == "SEC EDGAR 公司披露"
    assert search_services["gdelt_doc_news"]["status"] == "available"
    assert search_services["gdelt_doc_news"]["name_zh"] == "GDELT 全球新闻"
    assert search_services["gnews_funding_news"]["status"] == "available"
    assert search_services["gnews_funding_news"]["name_zh"] == "GNews 融资事件新闻"
    assert search_services["sec_enforcement_search"]["status"] == "available"
    assert search_services["sec_enforcement_search"]["name_zh"] == "SEC 执法/处罚搜索"
    assert search_services["usaspending_awards"]["status"] == "available"
    assert search_services["usaspending_awards"]["name_zh"] == "USAspending 政府采购与拨款"
    assert search_services["grants_gov_opportunities"]["status"] == "available"
    assert search_services["grants_gov_opportunities"]["name_zh"] == "Grants.gov 资助机会"
    assert search_services["patentsview_patents"]["status"] == "available"
    assert search_services["patentsview_patents"]["name_zh"] == "PatentsView 专利检索"
    assert search_services["ofac_sanctions_lists"]["status"] == "available"
    assert search_services["ofac_sanctions_lists"]["name_zh"] == "OFAC 制裁清单"
    assert capabilities["code_api"]["status"] == "not_configured"
    assert capabilities["code_api"]["connected"] is False
    assert capabilities["code_api"]["connected_name_zh"] == "未接入"
    assert capabilities["code_api"]["code_path"] is None
    assert capabilities["vector_api"]["status"] == "active"
    assert capabilities["vector_api"]["connected_name_zh"] == "本地 Qdrant 向量库"
    assert capabilities["vector_api"]["code_path"] == "app/providers/vector_store.py"
    assert capabilities["llm_api"]["status"] == "active"
    assert capabilities["llm_api"]["default_service"] == "openrouter_auto_reasoning"
    assert capabilities["llm_api"]["connected_name_zh"] == "OpenRouter 自动推理"
    assert capabilities["llm_api"]["code_path"] == "app/providers/llm.py"
    for capability_id in ("segments.query", "segments.create", "segments.read"):
        assert capabilities[capability_id]["status"] == "active"
        assert capabilities[capability_id]["connected"] is True
        assert capabilities[capability_id]["credential_status"] == "not_required"
        assert capabilities[capability_id]["code_path"] == "app/api/routers/segments.py"
    assert any(
        credential["env"] == "OPENROUTER_API_KEY" and credential["present"]
        for credential in capabilities["llm_api"]["credentials"]
    )
    assert "unit-openrouter-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-github-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-hf-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-companies-house-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-courtlistener-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-gnews-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-usajobs-secret-value" not in json.dumps(status, ensure_ascii=False)
    assert "unit-usajobs-user-agent-secret-value" not in json.dumps(status, ensure_ascii=False)


def test_generate_vla_job_profile_is_robot_specific() -> None:
    result = generate_job_profile_and_jd("我们想招一个家庭机器人 VLA 算法工程师")

    assert infer_role_key("家庭机器人 VLA 算法工程师") == "vla_embodied_expert"
    assert infer_role_key("找一个家庭机器人算法工程师") == "vla_embodied_expert"
    assert "VLA / 具身智能算法工程师" in result["岗位定位"]
    assert "连续动作空间离散化与多模态Token编排" in result["能力矩阵"]["必备能力"]
    assert result["能力矩阵"]["能力画像"]
    assert result["证据链与验证"]["当前状态"].startswith("静态基线")
    assert "是否理解 action token 和连续动作离散化" in result["能力矩阵"]["加分能力"]
    assert "纯NLP" in result["能力矩阵"]["排除项"]
    assert any("Diffusion Policy" in keyword for keyword in result["候选人来源"]["岗位关键词"])


def test_industry_step_uses_search_source_coverage_for_generic_algorithm_role(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self):
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        if "openalex.org/works" in url:
            return Response({"results": [{"display_name": "Robot VLA Paper", "primary_location": {"landing_page_url": "https://arxiv.org/abs/1"}, "authorships": []}]})
        if "api.github.com/search/repositories" in url:
            return Response({"items": [{"full_name": "skild-ai/openvla", "html_url": "https://github.com/skild-ai/openvla", "description": "VLA policy", "owner": {"login": "skild-ai", "type": "Organization"}}]})
        if "huggingface.co/api/models" in url:
            return Response([{"modelId": "robot/vla-model", "downloads": 12, "likes": 3, "tags": ["robotics"]}])
        if "api.gdeltproject.org" in url:
            return Response({"articles": [{"title": "Stanford IRIS robot learning benchmark", "url": "https://news.example/robot", "seendate": "20260603T120000Z"}]})
        if "patentsview.org" in url:
            return Response({"patents": [{"patent_number": "1", "patent_title": "Robot manipulation patent"}]})
        return Response({})

    import requests

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "")
    monkeypatch.setattr(requests, "get", fake_get)
    ctx = {"input": "找一个家庭机器人算法工程师", "data": {}, "human": None}

    plan_output = _a_plan(ctx)
    industry_output = _a_industry(ctx)

    assert plan_output["role_key"] == "vla_embodied_expert"
    assert industry_output["目标公司"]
    assert industry_output["高校实验室"]
    assert industry_output["校准状态"]["status"] == "live_calibrated"
    assert industry_output["目标公司"] == ["Skild AI"]
    assert industry_output["推荐信源"]
    assert industry_output["证据记录"]
    assert any(source["source_key"] in {"conference_paper_lists", "github", "model_hubs"} for source in industry_output["推荐信源"])
    assert industry_output["实时检索"]["result_count"] >= 4
    assert any(result["source_key"] == "github_repositories" for result in industry_output["实时检索"]["results"])
    assert any(error["reason"].startswith("missing_credentials:BRAVE_SEARCH_API_KEY") for error in industry_output["实时检索"]["errors"])
    assert "source catalog" in industry_output["检索说明"]


def test_calibrated_target_sources_promotes_live_entities_over_static_seed() -> None:
    intelligence = {
        "实时检索": {
            "result_count": 3,
            "results": [
                {
                    "source_key": "brave_web_search",
                    "source_name": "Brave Search",
                    "source_type": "open_web",
                    "title": "Skild AI raises funding for robot foundation models",
                    "snippet": "Skild AI is hiring robot learning researchers.",
                    "url": "https://www.skild.ai/news",
                },
                {
                    "source_key": "gdelt_doc_news",
                    "source_type": "news_media",
                    "title": "Figure AI launches humanoid robot team",
                    "snippet": "Figure AI expands robotics hiring.",
                    "url": "https://news.example/figure",
                },
                {
                    "source_key": "brave_web_search",
                    "source_type": "open_web",
                    "title": "Stanford IRIS robot learning lab releases benchmark",
                    "snippet": "Stanford IRIS works on robot learning and manipulation.",
                    "url": "https://irislab.stanford.edu/",
                },
            ],
        }
    }

    targets = _calibrated_target_sources("vla_embodied_expert", intelligence)

    assert targets["校准状态"]["status"] == "live_calibrated"
    assert set(targets["目标公司"]) == {"Figure AI", "Skild AI"}
    assert "Physical Intelligence" not in targets["目标公司"]
    assert "Physical Intelligence" in targets["静态种子"]["目标公司"]
    assert targets["高校实验室"] == ["Stanford IRIS"]
    assert targets["动态目标线索"]


def test_calibrated_target_sources_does_not_fallback_seed_as_targets() -> None:
    targets = _calibrated_target_sources(
        "vla_embodied_expert",
        {
            "实时检索": {
                "result_count": 1,
                "results": [
                    {
                        "source_key": "openalex_works_search",
                        "source_type": "academic",
                        "title": "Robot foundation model benchmark",
                        "url": "https://arxiv.org/abs/1",
                    }
                ],
            }
        },
    )

    assert targets["校准状态"]["status"] == "static_fallback_no_entity_hits"
    assert targets["目标公司"] == []
    assert targets["高校实验室"] == []
    assert "Physical Intelligence" in targets["静态种子"]["目标公司"]


def test_candidate_eval_and_weekly_signals_attach_capability_context(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_source_intelligence(user_input: str, role_key: str, limit: int = 12) -> dict:
        return {
            "query": user_input,
            "推荐信源": [{"source_key": "github", "name_zh": "GitHub"}],
            "证据记录": [{"source_key": "github", "source_name": "GitHub"}],
            "实时检索": {
                "services": ["github_repositories"],
                "results": [{"source_key": "github_repositories", "title": "robot/vla"}],
                "errors": [],
                "result_count": 1,
            },
            "检索说明": "unit search context",
        }

    def fake_rag_context(query: str, top_k: int = 5) -> dict:
        return {
            "status": "retrieved",
            "query": query[:80],
            "result_count": 1,
            "results": [{"candidate_id": "cand_1", "chunk_index": 0, "score": 0.91, "content": "Diffusion Policy 实机部署"}],
        }

    monkeypatch.setattr("app.core.orchestrator._source_intelligence", fake_source_intelligence)
    monkeypatch.setattr("app.core.orchestrator._rag_context", fake_rag_context)

    candidate_ctx = {
        "input": "候选人主导 VLA Diffusion Policy ROS 实机部署，控制链路延迟 12ms。",
        "team_constraint": "真机动作延迟高",
        "aperture_weight": 0.85,
        "data": {},
        "human": None,
    }
    candidate_ctx["role_key"] = "vla_embodied_expert"
    candidate_output = _c_eval(candidate_ctx)

    assert candidate_output["本地RAG"]["result_count"] == 1
    assert candidate_output["公开检索"]["实时检索"]["result_count"] == 1
    assert candidate_output["工程事实链"]
    assert candidate_output["能力平移推演"]
    assert "真机动作延迟高" in candidate_output["增量价值"]
    assert candidate_output["aperture_anchor"]["source"] == "frontend_payload"
    assert candidate_output["capability_spectrum"]
    assert candidate_output["narrative_stream"]["status"] in {
        "evidence_supported_projection",
        "candidate_quantified_requires_validation",
        "insufficient_data",
    }
    assert candidate_output["probing_toolkit"]
    assert candidate_output["evidence_dependency_contract"]["task_a"]["fact_count"] >= 1
    assert candidate_ctx["data"]["evaluation"]["证据链"]["本地RAG命中数"] == 1
    assert "隐私说明" in candidate_ctx["data"]["evaluation"]["能力证据"]
    assert candidate_ctx["data"]["evaluation"]["decision_sandbox"]["agent_matrix"][1]["status"] == "ready"

    weekly_ctx = {"input": "本周 VLA 招聘有融资和 GitHub 信号。", "data": {}, "human": None}
    _d_plan(weekly_ctx)
    weekly_output = _d_signals(weekly_ctx)

    assert weekly_output["市场搜索证据"]["实时检索"]["result_count"] == 1
    assert weekly_ctx["data"]["weekly"]["市场搜索证据"]["推荐信源"]


def test_finalize_attaches_human_report_with_clickable_citation_contract() -> None:
    ctx = {
        "scenario": "C",
        "input": "候选人主导 VLA Diffusion Policy ROS 实机部署。",
        "role_key": "vla_embodied_expert",
        "data": {
            "evaluation": {
                "适合岗位": "VLA / 具身智能算法工程师",
                "推荐等级": "强推",
                "匹配评分": 93,
                "推荐结论": "建议进入下一轮",
                "技术强项": ["Diffusion Policy", "ROS"],
                "风险点": ["需要确认项目独立贡献边界"],
                "证据链": {},
            },
            "candidate_capability_context": {
                "公开检索": {
                    "实时检索": {
                        "result_count": 1,
                        "results": [
                            {
                                "source_key": "github_repositories",
                                "source_name": "GitHub 代码仓库",
                                "source_type": "code_repository",
                                "title": "real-stanford/diffusion_policy",
                                "url": "https://github.com/real-stanford/diffusion_policy",
                                "snippet": "Robot diffusion policy implementation.",
                            }
                        ],
                        "errors": [{"service": "brave_web_search", "reason": "missing_credentials:BRAVE_SEARCH_API_KEY"}],
                    }
                },
                "本地RAG": {
                    "status": "retrieved",
                    "result_count": 1,
                    "results": [{"candidate_id": "cand_1", "content": "实机部署证据"}],
                },
                "隐私说明": "候选人原始材料只用于本地 heuristic 与本地 RAG。",
            },
        },
        "human": None,
    }

    result = _c_finalize(ctx)
    report = result["human_report"]

    assert report["title"] == "VLA / 具身智能算法工程师候选人评估"
    assert report["summary"][0]["citations"] == ["1"]
    assert report["citations"][0]["id"] == "1"
    assert report["citations"][0]["url"] == "https://github.com/real-stanford/diffusion_policy"
    assert report["diagnostics"]["error_count"] == 1


def test_build_slam_talent_map_uses_transfer_sources() -> None:
    result = build_talent_map("家庭机器人 SLAM 工程师")

    assert "科沃斯" in result["优先来源公司"]
    assert "科沃斯" in result["目标公司"]
    assert "AR 空间计算团队" in result["次优来源公司"]
    assert "纯网页前端" in result["排除来源"]
    assert any(keyword == "SLAM / 导航算法工程师" for keyword in result["候选人关键词"])
    assert any(keyword == "SLAM / 导航算法工程师" for keyword in result["搜索关键词"])
    assert any(profile["能力名称"] == "激光/视觉/IMU多传感器融合建图" for profile in result["能力细分"])
    assert "动态校准目标" in result["溯源验证计划"]


def test_build_talent_map_from_job_keeps_job_domain() -> None:
    job_profile = {
        "id": "job_fde_1",
        "title": "AI Native FDE / Agentic Builder",
        "seniority": "Senior",
        "must_have_skills": ["全栈开发", "AI coding 实战", "Agentic workflow"],
        "nice_to_have_skills": ["电商 SaaS 经验"],
        "target_companies": ["AI 应用创业公司"],
        "exclusion_signals": ["只会写 prompt"],
        "rationale": {
            "sourcing_keywords": ["Agentic Builder", "FDE"],
            "outreach_angle": "用真实业务问题和完整 SDLC 主导权吸引 builder。",
        },
    }

    result = build_talent_map_from_job(job_profile)

    assert result["优先来源公司"] == ["AI 应用创业公司"]
    assert result["排除来源"] == ["只会写 prompt"]
    assert "AI Native FDE / Agentic Builder" in result["搜索关键词"]
    assert "Agentic Builder" in result["搜索关键词"]
    assert "全栈开发" in result["触达话术"]
    assert "用真实业务问题和完整 SDLC 主导权吸引 builder。" in result["触达话术"]
    assert "机器人" not in result["触达话术"]
    assert result["候选人来源"]["优先来源公司"] == ["AI 应用创业公司"]
    assert result["岗位上下文"]["job_id"] == "job_fde_1"


def test_job_profile_match_reports_job_specific_coverage() -> None:
    match = _job_profile_match(
        {
            "title": "AI Native FDE / Agentic Builder",
            "must_have_skills": ["全栈开发", "Agentic workflow", "支付风控"],
            "rationale": {
                "must_have_signals": ["AI coding 实战"],
                "risk_signals": ["只会写 prompt"],
            },
        },
        "候选人主导全栈开发和 Agentic workflow 项目，有 AI coding 实战，但部分模块只会写 prompt。",
    )

    assert match["岗位"] == "AI Native FDE / Agentic Builder"
    assert match["必备技能命中"] == ["全栈开发", "Agentic workflow"]
    assert match["必备技能缺口"] == ["支付风控"]
    assert match["加分信号命中"] == ["AI coding 实战"]
    assert match["风险信号命中"] == ["只会写 prompt"]
    assert match["技能覆盖率"] == 0.67


def test_score_candidate_against_job_uses_job_rubric() -> None:
    job_profile = {
        "title": "AI Native FDE / Agentic Builder",
        "must_have_skills": ["全栈开发", "Agentic workflow"],
        "scoring_rubric": {
            "完整业务工程闭环（问题定义/上线/指标复盘）": 3,
            "业务抽象能力（订单/支付/风控）": 2,
        },
        "rationale": {
            "must_have_signals": ["AI coding"],
            "risk_signals": ["只会写 prompt"],
        },
    }
    material = "主导订单支付风控系统上线，问题定义到指标复盘，全栈开发 Agentic workflow AI coding"

    scoring = score_candidate_against_job(job_profile, material)

    # 55×0.75(rubric) + 30×1.0(技能) + 5(主导) + 5(上线) + 5(AI coding) = 86.25 → 86
    assert scoring["匹配评分"] == 86
    assert scoring["推荐等级"] == "强推"
    assert scoring["必备技能命中"] == ["全栈开发", "Agentic workflow"]
    assert scoring["必备技能缺口"] == []
    assert len(scoring["评分维度"]) == 2
    assert all(dim["覆盖率"] == 0.75 for dim in scoring["评分维度"])
    assert scoring["风险点"] == []

    risky = score_candidate_against_job(job_profile, material + " 但部分模块只会写 prompt")
    assert risky["匹配评分"] == 76
    assert any("只会写 prompt" in item for item in risky["风险点"])


def test_evaluate_candidate_distinguishes_real_robot_from_sim_only() -> None:
    real_robot = evaluate_candidate(
        "主导家庭机器人 VLA 项目，负责第一视角遥操作数据、Action Token、Diffusion Policy，"
        "ROS 实机部署，处理长程任务失败恢复和家具变化长尾场景，控制回路延迟 12ms。",
        target="家庭机器人 VLA 算法工程师",
        team_constraint="真机动作延迟高",
    )
    sim_only = evaluate_candidate(
        "参与 Isaac Sim 仿真环境搭建和策略训练，主要负责边缘模块。",
        target="家庭机器人 VLA 算法工程师",
    )

    assert real_robot["推荐等级"] in {"强推", "可面"}
    assert real_robot["匹配评分"] > sim_only["匹配评分"]
    assert any("真实机器人/硬件部署" in risk for risk in sim_only["风险点"])
    assert real_robot["推荐结论"] == real_robot["结论"]
    assert real_robot["证据链"]["真实机器人证据"] is True
    assert real_robot["decision_sandbox"]["aperture"]["team_constraint"] == "真机动作延迟高"
    assert real_robot["decision_sandbox"]["aperture_anchor"]["team_constraint"] == "真机动作延迟高"
    assert any(fact["id"] == "fact_control_latency" and fact["value"] == "12ms" for fact in real_robot["工程事实链"])
    assert real_robot["追问武器库"][0]["question"].startswith("你材料中的")
    assert any(item["energy"] is None for item in sim_only["decision_sandbox"]["capability_spectrum"])
    assert sim_only["decision_sandbox"]["narrative_stream"]["status"] in {
        "candidate_quantified_requires_validation",
        "insufficient_data",
    }


def test_probe_feedback_api_updates_task_result() -> None:
    task = task_store.create("C", "候选人材料", team_constraint="真机泛化", aperture_weight=0.7)
    task_store.update(task.task_id, status="done", result={"decision_sandbox": {"feedback_loop": {}}})
    client = TestClient(app)

    response = client.post(
        f"/tasks/{task.task_id}/probe-feedback",
        json={"probe_id": "probe_1", "answered": True, "note": "能说清楚延迟指标"},
    )
    snapshot = task_store.snapshot(task.task_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "recorded"
    assert payload["latest_update"]["answered_count"] == 1
    assert snapshot["result"]["decision_sandbox"]["feedback_loop"]["feedback"][0]["probe_id"] == "probe_1"


def test_generate_weekly_report_routes_to_data_flywheel() -> None:
    report = generate_weekly_report(
        "本周 VLA 岗位面试反馈已校准，GitHub 和 B站 Demo 发现两个候选人，暂无 offer 结果。",
        focus_roles=["家庭机器人 VLA 算法工程师"],
    )

    assert "招聘周报" in HOME_ROBOT_RECRUITING_SCENARIOS["workflows"]["scenario_d_weekly_report"]["name_zh"]
    assert "本周招聘结论" in report
    assert "GitHub" in report["市场人才信号"]
    assert "B站" in report["市场人才信号"]
    assert report["回流目标"] == ["知识库", "画像库", "评分体系"]


def test_search_source_catalog_provider_returns_recruiting_sources() -> None:
    router = ServiceRouter(load_app_config())
    search = router.search("talent_source_catalog")

    results = search.search("VLA 机器人 招聘 薪酬", limit=3)
    assert results
    assert results[0]["source_key"] == "recruitment_boards_cn"
    assert "Boss直聘" in results[0]["source_names"]

    plan = search.plan("ICRA humanoid control", limit=5)
    assert plan["recommended_sources"]
    assert any(source["source_key"] == "conference_paper_lists" for source in plan["recommended_sources"])
    assert any("不绕过登录" in guardrail for guardrail in plan["guardrails"])


def test_due_diligence_federated_search_plans_financial_intelligence_sources() -> None:
    router = ServiceRouter(load_app_config())
    search = router.search()

    results = search.search("机器人 公司 融资 年报 研发人员", limit=6)
    plan = search.plan("机器人 公司 融资 年报 研发人员", limit=10)
    evidence = search.evidence("机器人 公司 融资 年报 研发人员", limit=6, claim="融资和研发投入变化")
    brief = search.brief("机器人 公司 融资 年报 研发人员", limit=6, claim="融资和研发投入变化")

    assert results
    assert results[0]["source_type"] == "source_catalog"
    assert results[0]["retrieval_status"] == "planned"
    assert plan["mode"] == "financial_due_diligence_intelligence"
    assert any(source["source_key"] == "regulatory_filings_global" for source in plan["recommended_sources"])
    assert any(source["source_key"] == "funding_private_market" for source in plan["recommended_sources"])
    assert {source["source_key"] for source in plan["registered_live_sources"]} >= {
        "sec_edgar_company_filings",
        "sec_company_facts",
        "sec_insider_transactions",
        "sec_ownership_activism",
        "sec_investment_adviser_reports",
        "fdic_bankfind_institutions",
        "federal_register_documents",
        "cpsc_recalls",
        "fda_enforcement_recalls",
        "fda_device_510k",
        "fda_device_events",
        "fda_device_classification",
        "fda_device_registration_listing",
        "cfpb_consumer_complaints",
        "nhtsa_recalls",
        "epa_echo_facilities",
        "clinicaltrials_studies",
        "cms_openpayments",
        "openalex_works_search",
        "gdelt_doc_news",
        "gnews_funding_news",
        "sec_enforcement_search",
        "usaspending_awards",
        "grants_gov_opportunities",
        "patentsview_patents",
        "ofac_sanctions_lists",
        "github_repositories",
        "huggingface_models",
        "brave_web_search",
    }
    assert {phase["phase"] for phase in plan["search_phases"]} >= {
        "market_map",
        "compliance_risk",
        "operational_risk",
        "governance_and_contracts",
    }
    assert set(plan["coverage_matrix"]) >= {
        "primary_disclosure",
        "market_and_funding",
        "macro_market_context",
        "non_dilutive_funding",
        "technical_evidence",
        "regulatory_enforcement",
        "product_quality_safety",
        "ownership_governance",
        "investment_adviser_due_diligence",
        "financial_institution_risk",
        "environmental_supply_chain",
        "clinical_validation",
        "healthcare_commercial_relationships",
        "government_procurement",
    }
    assert "sec_enforcement_search" in plan["coverage_matrix"]["regulatory_enforcement"]
    assert "cpsc_recalls" in plan["coverage_matrix"]["product_quality_safety"]
    assert "fda_device_510k" in plan["coverage_matrix"]["product_quality_safety"]
    assert "fda_device_events" in plan["coverage_matrix"]["product_quality_safety"]
    assert "fda_device_classification" in plan["coverage_matrix"]["product_quality_safety"]
    assert "fda_device_registration_listing" in plan["coverage_matrix"]["product_quality_safety"]
    assert "sec_insider_transactions" in plan["coverage_matrix"]["ownership_governance"]
    assert "sec_investment_adviser_reports" in plan["coverage_matrix"]["ownership_governance"]
    assert "sec_investment_adviser_reports" in plan["coverage_matrix"]["investment_adviser_due_diligence"]
    assert "sec_investment_adviser_reports" in plan["coverage_matrix"]["financial_institution_risk"]
    assert "fdic_bankfind_institutions" in plan["coverage_matrix"]["market_and_funding"]
    assert "grants_gov_opportunities" in plan["coverage_matrix"]["market_and_funding"]
    assert "grants_gov_opportunities" in plan["coverage_matrix"]["non_dilutive_funding"]
    assert "fdic_bankfind_institutions" in plan["coverage_matrix"]["ownership_governance"]
    assert "fdic_bankfind_institutions" in plan["coverage_matrix"]["financial_institution_risk"]
    assert "epa_echo_facilities" in plan["coverage_matrix"]["environmental_supply_chain"]
    assert "fda_device_registration_listing" in plan["coverage_matrix"]["environmental_supply_chain"]
    assert "clinicaltrials_studies" in plan["coverage_matrix"]["clinical_validation"]
    assert "fda_device_510k" in plan["coverage_matrix"]["clinical_validation"]
    assert "fda_device_classification" in plan["coverage_matrix"]["clinical_validation"]
    assert "fda_device_registration_listing" in plan["coverage_matrix"]["clinical_validation"]
    assert "cms_openpayments" in plan["coverage_matrix"]["healthcare_commercial_relationships"]
    assert "usaspending_awards" in plan["coverage_matrix"]["government_procurement"]
    assert "grants_gov_opportunities" in plan["coverage_matrix"]["government_procurement"]
    assert any("OFAC" in query for query in plan["query_templates"])
    assert any("Form ADV" in query for query in plan["query_templates"])
    assert any("FDIC BankFind" in query for query in plan["query_templates"])
    assert any("510(k)" in query for query in plan["query_templates"])
    assert any("FDA classification" in query for query in plan["query_templates"])
    assert any("FDA registration listing" in query for query in plan["query_templates"])
    assert any("MAUDE" in query for query in plan["query_templates"])
    assert any("Open Payments" in query for query in plan["query_templates"])
    assert any("USAspending" in query for query in plan["query_templates"])
    assert any("Grants.gov" in query for query in plan["query_templates"])
    assert any("至少需要两个独立来源" in rule for rule in plan["evidence_rules"])
    assert evidence["records"]
    assert evidence["records"][0]["claim"] == "融资和研发投入变化"
    assert evidence["review"]["source_tier_counts"]
    assert evidence["review"]["cross_check_status"] == "ready_for_human_review"
    assert brief["brief_type"] == "financial_due_diligence_intelligence_brief"
    assert brief["executive_summary"]["status"] == "ready_for_human_review"
    assert brief["coverage_matrix"]["primary_disclosure"]
    assert brief["coverage_matrix"]["non_dilutive_funding"]
    assert brief["coverage_matrix"]["regulatory_enforcement"]
    assert brief["coverage_matrix"]["product_quality_safety"]
    assert brief["coverage_matrix"]["financial_institution_risk"]
    assert brief["coverage_matrix"]["investment_adviser_due_diligence"]


def test_brave_web_search_provider_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "web": {
                    "results": [
                        {
                            "title": "Robot SLAM Example",
                            "url": "https://example.com/slam",
                            "description": "A public technical page about robot SLAM.",
                            "page_age": "2026-06-01",
                            "language": "en",
                            "family_friendly": True,
                        }
                    ]
                }
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("brave_web_search").search("robot slam", limit=25)

    assert calls["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert calls["params"]["q"] == "robot slam"
    assert calls["params"]["count"] == 20
    assert calls["params"]["result_filter"] == "web"
    assert calls["headers"]["X-Subscription-Token"] == "test-token"
    assert results[0]["source_key"] == "brave_web_search"
    assert results[0]["title"] == "Robot SLAM Example"
    assert results[0]["url"] == "https://example.com/slam"


def test_github_repository_search_provider_maps_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "items": [
                    {
                        "full_name": "robotics/foundation-model",
                        "html_url": "https://github.com/robotics/foundation-model",
                        "description": "Robot foundation model code.",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-06-01T00:00:00Z",
                        "pushed_at": "2026-06-02T00:00:00Z",
                        "owner": {"login": "robotics", "type": "Organization"},
                        "language": "Python",
                        "stargazers_count": 1200,
                        "forks_count": 88,
                        "open_issues_count": 7,
                        "license": {"spdx_id": "Apache-2.0"},
                        "topics": ["robotics", "foundation-model"],
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("GITHUB_TOKEN", "unit-github-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("github_repositories").search("robotics foundation model", limit=150)

    assert calls["url"] == "https://api.github.com/search/repositories"
    assert calls["params"]["q"] == "robotics foundation model"
    assert calls["params"]["per_page"] == 100
    assert calls["params"]["sort"] == "stars"
    assert calls["headers"]["Accept"] == "application/vnd.github+json"
    assert calls["headers"]["Authorization"] == "Bearer unit-github-token"
    assert results[0]["source_key"] == "github_repositories"
    assert results[0]["source_type"] == "code_repository"
    assert results[0]["title"] == "robotics/foundation-model"
    assert results[0]["stars"] == 1200
    assert results[0]["topics"] == ["robotics", "foundation-model"]


def test_github_candidate_search_provider_enriches_people_repositories_and_code(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""
        headers = {
            "X-RateLimit-Limit": "30",
            "X-RateLimit-Remaining": "29",
            "X-RateLimit-Reset": "1770000000",
            "X-RateLimit-Resource": "search",
        }

        def __init__(self, payload) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self):
            return self.payload

    def fake_get(url: str, *, params: dict | None = None, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params or {}, "headers": headers, "timeout": timeout})
        if url == "https://api.github.com/search/users":
            return Response(
                {
                    "items": [
                        {
                            "login": "alice-robotics",
                            "html_url": "https://github.com/alice-robotics",
                            "score": 1.0,
                            "type": "User",
                        }
                    ]
                }
            )
        if url == "https://api.github.com/search/repositories":
            return Response(
                {
                    "items": [
                        {
                            "full_name": "alice-robotics/agentic-rag-robot",
                            "html_url": "https://github.com/alice-robotics/agentic-rag-robot",
                            "description": "Agentic workflow and RAG system for robot manipulation.",
                            "owner": {"login": "alice-robotics", "type": "User"},
                            "language": "TypeScript",
                            "stargazers_count": 860,
                            "forks_count": 74,
                            "topics": ["agentic-workflow", "rag", "robotics", "mcp"],
                            "pushed_at": "2026-06-01T12:00:00Z",
                            "updated_at": "2026-06-01T12:00:00Z",
                        }
                    ]
                }
            )
        if url == "https://api.github.com/search/code":
            return Response(
                {
                    "items": [
                        {
                            "name": "workflow.ts",
                            "path": "src/workflow.ts",
                            "html_url": "https://github.com/alice-robotics/agentic-rag-robot/blob/main/src/workflow.ts",
                            "repository": {
                                "full_name": "alice-robotics/agentic-rag-robot",
                                "html_url": "https://github.com/alice-robotics/agentic-rag-robot",
                                "owner": {"login": "alice-robotics", "type": "User"},
                            },
                            "text_matches": [
                                {
                                    "fragment": "createAgenticWorkflow({ mcp, rag, fullstack })",
                                    "matches": [{"text": "mcp"}, {"text": "rag"}],
                                }
                            ],
                        }
                    ]
                }
            )
        if url == "https://api.github.com/users/alice-robotics":
            return Response(
                {
                    "login": "alice-robotics",
                    "name": "Alice Robotics",
                    "html_url": "https://github.com/alice-robotics",
                    "company": "Open Robot Lab",
                    "location": "San Francisco",
                    "email": "alice@example.com",
                    "bio": "Building agentic workflow, MCP, RAG and fullstack robot tooling.",
                    "followers": 128,
                    "public_repos": 24,
                    "blog": "https://alice.example",
                    "updated_at": "2026-06-02T00:00:00Z",
                }
            )
        if url == "https://api.github.com/users/alice-robotics/repos":
            return Response(
                [
                    {
                        "full_name": "alice-robotics/agentic-rag-robot",
                        "html_url": "https://github.com/alice-robotics/agentic-rag-robot",
                        "description": "Agentic workflow and RAG system for robot manipulation.",
                        "language": "TypeScript",
                        "stargazers_count": 860,
                        "forks_count": 74,
                        "topics": ["agentic-workflow", "rag", "robotics", "mcp"],
                        "pushed_at": "2026-06-01T12:00:00Z",
                        "updated_at": "2026-06-01T12:00:00Z",
                    },
                    {
                        "full_name": "alice-robotics/mcp-fullstack-saas",
                        "html_url": "https://github.com/alice-robotics/mcp-fullstack-saas",
                        "description": "Fullstack SaaS MCP integration examples.",
                        "language": "TypeScript",
                        "stargazers_count": 120,
                        "forks_count": 12,
                        "topics": ["mcp", "fullstack", "saas"],
                        "pushed_at": "2026-05-20T12:00:00Z",
                        "updated_at": "2026-05-20T12:00:00Z",
                    },
                ]
            )
        raise AssertionError(f"unexpected GitHub URL: {url}")

    import requests

    monkeypatch.setenv("GITHUB_TOKEN", "unit-github-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("github_candidates").search('"Agentic workflow" MCP RAG fullstack', limit=3)

    assert calls[0]["headers"]["Authorization"] == "Bearer unit-github-token"
    assert {call["url"] for call in calls} >= {
        "https://api.github.com/search/users",
        "https://api.github.com/search/repositories",
        "https://api.github.com/search/code",
        "https://api.github.com/users/alice-robotics",
        "https://api.github.com/users/alice-robotics/repos",
    }
    assert results[0]["source_key"] == "github_candidates"
    assert results[0]["source_type"] == "developer_profile"
    assert results[0]["source_platform"] == "github_candidates"
    assert results[0]["name"] == "Alice Robotics"
    assert results[0]["github_url"] == "https://github.com/alice-robotics"
    assert results[0]["email"] == "alice@example.com"
    assert results[0]["confidence"] >= 0.8
    assert results[0]["github_score"] >= 80
    assert results[0]["representative_repositories"][0]["full_name"] == "alice-robotics/agentic-rag-robot"
    assert results[0]["repository_evidence"][0]["source"] in {"repository", "code"}
    assert {"agentic", "mcp", "rag", "fullstack"}.intersection(set(results[0]["matched_keywords"]))
    assert results[0]["rate_limit"]["remaining"] == 29


def test_github_code_and_topic_search_providers_map_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""
        headers = {"X-RateLimit-Remaining": "8", "X-RateLimit-Resource": "code_search"}

        def __init__(self, payload) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self):
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url == "https://api.github.com/search/code":
            return Response(
                {
                    "items": [
                        {
                            "name": "agent.ts",
                            "path": "src/agent.ts",
                            "html_url": "https://github.com/alice/agentic/blob/main/src/agent.ts",
                            "repository": {
                                "full_name": "alice/agentic",
                                "html_url": "https://github.com/alice/agentic",
                                "owner": {"login": "alice", "type": "User"},
                            },
                            "text_matches": [{"fragment": "MCP RAG workflow"}],
                        }
                    ]
                }
            )
        if url == "https://api.github.com/search/topics":
            return Response(
                {
                    "items": [
                        {
                            "name": "agentic-workflow",
                            "display_name": "Agentic Workflow",
                            "short_description": "Agent workflow systems",
                            "description": "Repositories about agent workflow systems.",
                            "created_by": "github",
                            "featured": True,
                            "curated": True,
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected GitHub URL: {url}")

    import requests

    monkeypatch.setenv("GITHUB_TOKEN", "unit-github-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    code_results = router.search("github_code").search("MCP RAG", limit=2)
    topic_results = router.search("github_topics").search("agentic workflow", limit=2)

    assert code_results[0]["source_key"] == "github_code"
    assert code_results[0]["source_type"] == "code_search"
    assert code_results[0]["owner_login"] == "alice"
    assert code_results[0]["github_url"] == "https://github.com/alice"
    assert code_results[0]["repository_full_name"] == "alice/agentic"
    assert "MCP RAG workflow" in code_results[0]["snippet"]
    assert topic_results[0]["source_key"] == "github_topics"
    assert topic_results[0]["source_type"] == "code_topic"
    assert topic_results[0]["url"] == "https://github.com/topics/agentic-workflow"
    assert calls[0]["headers"]["Authorization"] == "Bearer unit-github-token"


def test_huggingface_model_search_provider_maps_models(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> list[dict]:
            return [
                {
                    "modelId": "robotics/foundation-model",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "lastModified": "2026-06-01T00:00:00Z",
                    "author": "robotics",
                    "downloads": 50000,
                    "likes": 900,
                    "pipeline_tag": "robotics",
                    "library_name": "transformers",
                    "tags": ["robotics", "vision-language-action"],
                }
            ]

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("HF_TOKEN", "unit-hf-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("huggingface_models").search("robotics", limit=150)

    assert calls["url"] == "https://huggingface.co/api/models"
    assert calls["params"]["search"] == "robotics"
    assert calls["params"]["limit"] == 100
    assert calls["params"]["sort"] == "downloads"
    assert calls["params"]["full"] == "true"
    assert calls["headers"]["Authorization"] == "Bearer unit-hf-token"
    assert results[0]["source_key"] == "huggingface_models"
    assert results[0]["source_type"] == "model_repository"
    assert results[0]["title"] == "robotics/foundation-model"
    assert results[0]["downloads"] == 50000
    assert results[0]["tags"] == ["robotics", "vision-language-action"]


def test_companies_house_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("companies_house_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "items": [
                    {
                        "title": "OPENAI UK LTD",
                        "company_number": "12345678",
                        "company_status": "active",
                        "company_type": "ltd",
                        "date_of_creation": "2026-01-01",
                        "description": "12345678 - Incorporated on 1 January 2026",
                        "address_snippet": "London, United Kingdom",
                        "matches": {"title": [1, 6]},
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, auth: tuple[str, str], headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["auth"] = auth
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "unit-companies-house-key")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("companies_house_search").search("openai", limit=150)

    assert calls["url"] == "https://api.company-information.service.gov.uk/search/companies"
    assert calls["params"]["q"] == "openai"
    assert calls["params"]["items_per_page"] == 100
    assert calls["auth"] == ("unit-companies-house-key", "")
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "companies_house_search"
    assert results[0]["source_type"] == "company_registry"
    assert results[0]["company_number"] == "12345678"
    assert results[0]["company_status"] == "active"
    assert results[0]["url"] == "https://find-and-update.company-information.service.gov.uk/company/12345678"


def test_courtlistener_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("courtlistener_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "caseName": "Robotics Inc. v. Supplier LLC",
                        "absolute_url": "/opinion/123/robotics-v-supplier/",
                        "snippet": "Contract dispute involving robotics components.",
                        "dateFiled": "2026-02-01",
                        "court": "United States District Court",
                        "court_id": "cand",
                        "docketNumber": "1:26-cv-00001",
                        "citation": ["999 F. Supp. 3d 1"],
                        "status": "Published",
                        "judge": "Example Judge",
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("COURTLISTENER_TOKEN", "unit-courtlistener-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("courtlistener_search").search("robotics", limit=150)

    assert calls["url"] == "https://www.courtlistener.com/api/rest/v4/search/"
    assert calls["params"]["q"] == "robotics"
    assert calls["params"]["type"] == "o"
    assert calls["params"]["page_size"] == 100
    assert calls["headers"]["Authorization"] == "Token unit-courtlistener-token"
    assert results[0]["source_key"] == "courtlistener_search"
    assert results[0]["source_type"] == "litigation"
    assert results[0]["title"] == "Robotics Inc. v. Supplier LLC"
    assert results[0]["url"] == "https://www.courtlistener.com/opinion/123/robotics-v-supplier/"
    assert results[0]["docket_number"] == "1:26-cv-00001"


def test_sec_company_facts_provider_maps_financial_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url == "https://www.sec.gov/files/company_tickers.json":
            return Response(
                {
                    "0": {
                        "cik_str": 789019,
                        "ticker": "MSFT",
                        "title": "MICROSOFT CORP",
                    }
                }
            )
        return Response(
            {
                "entityName": "MICROSOFT CORP",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "label": "Revenues",
                            "description": "Revenue from contracts.",
                            "units": {
                                "USD": [
                                    {
                                        "val": 100,
                                        "fy": 2025,
                                        "fp": "FY",
                                        "form": "10-K",
                                        "filed": "2025-07-30",
                                        "end": "2025-06-30",
                                        "accn": "0000789019-25-000001",
                                    },
                                    {
                                        "val": 120,
                                        "fy": 2026,
                                        "fp": "FY",
                                        "form": "10-K",
                                        "filed": "2026-07-30",
                                        "end": "2026-06-30",
                                        "accn": "0000789019-26-000001",
                                    },
                                ]
                            },
                        }
                    }
                },
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_company_facts").search("MSFT revenue", limit=5)

    assert calls[0]["url"] == "https://www.sec.gov/files/company_tickers.json"
    assert calls[1]["url"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"
    assert calls[0]["headers"]["User-Agent"] == "zhaoping-agent/0.1 research contact@example.invalid"
    assert results[0]["source_key"] == "sec_company_facts"
    assert results[0]["source_type"] == "financial_facts"
    assert results[0]["ticker"] == "MSFT"
    assert results[0]["tag"] == "Revenues"
    assert results[0]["value"] == 120
    assert results[0]["fiscal_year"] == 2026


def test_sec_investment_adviser_report_provider_maps_adv_roster_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    import csv
    import io
    import zipfile

    csv_buffer = io.StringIO()
    fieldnames = [
        "SEC Region",
        "Organization CRD#",
        "Additional CRD Number",
        "SEC#",
        "Firm Type",
        "CIK#",
        "Primary Business Name",
        "Legal Name",
        "Main Office Street Address 1",
        "Main Office Street Address 2",
        "Main Office City",
        "Main Office State",
        "Main Office Country",
        "Main Office Postal Code",
        "Main Office Telephone Number",
        "Total number of offices, other than your Principal Office and place of business",
        "SEC Current Status",
        "SEC Status Effective Date",
        "Latest ADV Filing Date",
        "Form Version",
        "Website Address",
        "Location of Books and Records City",
        "Location of Books and Records State",
        "Jurisdiction Notice Filed-Effective Date",
        "1O - If yes, approx. amount of assets",
        "11",
    ]
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(
        {
            "SEC Region": "NYRO",
            "Organization CRD#": "107105",
            "SEC#": "801-47710",
            "Firm Type": "Registered",
            "CIK#": "1364742",
            "Primary Business Name": "BLACKROCK ADVISORS LLC",
            "Legal Name": "BLACKROCK ADVISORS LLC",
            "Main Office Street Address 1": "50 HUDSON YARDS",
            "Main Office City": "NEW YORK",
            "Main Office State": "NY",
            "Main Office Country": "United States",
            "Main Office Postal Code": "10001",
            "Main Office Telephone Number": "2128105300",
            "Total number of offices, other than your Principal Office and place of business": "12",
            "SEC Current Status": "Approved",
            "SEC Status Effective Date": "01/01/2026",
            "Latest ADV Filing Date": "06/01/2026",
            "Form Version": "10/2021",
            "Website Address": "www.blackrock.com",
            "Location of Books and Records City": "NEW YORK",
            "Location of Books and Records State": "NY",
            "Jurisdiction Notice Filed-Effective Date": "01/01/2026",
            "1O - If yes, approx. amount of assets": "1000000000",
            "11": "Y",
        }
    )

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("IA_SEC_ROSTER.CSV", csv_buffer.getvalue())

    class Response:
        status_code = 200
        text = ""
        content = archive_buffer.getvalue()

        @staticmethod
        def raise_for_status() -> None:
            return None

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_investment_adviser_reports").search("BlackRock", limit=200)

    assert calls["url"] == "https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126.zip"
    assert calls["headers"]["User-Agent"] == "zhaoping-agent/0.1 research contact@example.invalid"
    assert results[0]["source_key"] == "sec_investment_adviser_reports"
    assert results[0]["source_type"] == "investment_adviser_registry"
    assert results[0]["title"] == "BLACKROCK ADVISORS LLC"
    assert results[0]["crd_number"] == "107105"
    assert results[0]["sec_number"] == "801-47710"
    assert results[0]["firm_type"] == "Registered"
    assert results[0]["cik"] == "1364742"
    assert results[0]["sec_current_status"] == "Approved"
    assert results[0]["latest_adv_filing_date"] == "06/01/2026"
    assert results[0]["main_office_city"] == "NEW YORK"
    assert results[0]["website"] == "www.blackrock.com"
    assert results[0]["approx_private_fund_assets"] == "1000000000"
    assert results[0]["url"] == "https://adviserinfo.sec.gov/firm/summary/107105"


def test_fdic_bankfind_provider_maps_institution_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "meta": {"total": 1},
                "data": [
                    {
                        "data": {
                            "NAME": "Silicon Valley Bank",
                            "CERT": 24735,
                            "ACTIVE": 0,
                            "CITY": "Santa Clara",
                            "STALP": "CA",
                            "STNAME": "California",
                            "ADDRESS": "3003 Tasman Drive",
                            "ZIP": "95054",
                            "WEBADDR": "www.svb.com",
                            "PHONE": "4086547400",
                            "REGAGNT": "FED",
                            "INSAGNT": "FDIC",
                            "CHARTAGNT": "STATE",
                            "BKCLASS": "SM",
                            "ASSET": 209026000,
                            "DEPDOM": 161479000,
                            "NETINC": 2024000,
                            "ROA": 0.9569929993881674,
                            "ROE": 13.43,
                            "REPDTE": "12/31/2022",
                            "ESTYMD": "10/17/1983",
                            "DATEUPDT": "03/10/2023",
                            "OFFDOM": 17,
                            "OFFFOR": 0,
                            "ID": "24735",
                        },
                        "score": 0,
                    }
                ],
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fdic_bankfind_institutions").search("Silicon Valley Bank", limit=2000)

    assert calls["url"] == "https://api.fdic.gov/banks/institutions"
    assert calls["params"]["limit"] == 1000
    assert calls["params"]["format"] == "json"
    assert 'NAME:"Silicon Valley Bank"' in calls["params"]["filters"]
    assert "CERT" in calls["params"]["fields"]
    assert "ASSET" in calls["params"]["fields"]
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fdic_bankfind_institutions"
    assert results[0]["source_type"] == "financial_institution_registry"
    assert results[0]["title"] == "Silicon Valley Bank"
    assert results[0]["fdic_certificate"] == 24735
    assert results[0]["active"] == 0
    assert results[0]["primary_regulator"] == "FED"
    assert results[0]["insurance_regulator"] == "FDIC"
    assert results[0]["bank_class"] == "SM"
    assert results[0]["assets"] == 209026000
    assert results[0]["domestic_deposits"] == 161479000
    assert results[0]["return_on_equity"] == 13.43
    assert results[0]["report_date"] == "12/31/2022"
    assert results[0]["url"] == "https://banks.data.fdic.gov/bankfind-suite/bankfind/details/24735"


def test_sec_insider_transactions_provider_maps_ownership_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url == "https://www.sec.gov/files/company_tickers.json":
            return Response(
                {
                    "0": {
                        "cik_str": 789019,
                        "ticker": "MSFT",
                        "title": "MICROSOFT CORP",
                    }
                }
            )
        return Response(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K", "4", "4/A", "8-K"],
                        "filingDate": ["2026-07-30", "2026-06-03", "2026-06-04", "2026-05-01"],
                        "reportDate": ["2026-06-30", "2026-06-01", "2026-06-01", "2026-04-30"],
                        "accessionNumber": [
                            "0000789019-26-000001",
                            "0000789019-26-000010",
                            "0000789019-26-000011",
                            "0000789019-26-000005",
                        ],
                        "primaryDocument": ["msft-10k.htm", "xslF345X05/doc4.xml", "xslF345X05/doc4a.xml", "msft-8k.htm"],
                        "primaryDocDescription": ["Annual report", "Statement of changes", "Amended ownership", "Current report"],
                    }
                }
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_insider_transactions").search("MSFT insider transactions", limit=5)

    assert calls[0]["url"] == "https://www.sec.gov/files/company_tickers.json"
    assert calls[1]["url"] == "https://data.sec.gov/submissions/CIK0000789019.json"
    assert calls[0]["headers"]["User-Agent"] == "zhaoping-agent/0.1 research contact@example.invalid"
    assert [result["form"] for result in results] == ["4", "4/A"]
    assert results[0]["source_key"] == "sec_insider_transactions"
    assert results[0]["source_type"] == "insider_transactions"
    assert results[0]["ticker"] == "MSFT"
    assert results[0]["ownership_form"] == "4"
    assert results[0]["url"] == "https://www.sec.gov/Archives/edgar/data/789019/000078901926000010/xslF345X05/doc4.xml"
    assert "Annual report" not in {result["snippet"] for result in results}


def test_sec_ownership_activism_provider_maps_control_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url == "https://www.sec.gov/files/company_tickers.json":
            return Response(
                {
                    "0": {
                        "cik_str": 1067983,
                        "ticker": "BRK-A",
                        "title": "BERKSHIRE HATHAWAY INC",
                    }
                }
            )
        return Response(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K", "SC 13D", "13F-HR", "144", "8-K"],
                        "filingDate": ["2026-02-28", "2026-06-03", "2026-05-15", "2026-05-20", "2026-04-01"],
                        "reportDate": ["2025-12-31", "2026-06-01", "2026-03-31", "2026-05-18", "2026-03-31"],
                        "accessionNumber": [
                            "0001067983-26-000001",
                            "0001067983-26-000010",
                            "0001067983-26-000011",
                            "0001067983-26-000012",
                            "0001067983-26-000013",
                        ],
                        "primaryDocument": ["brka-10k.htm", "sc13d.htm", "form13fInfoTable.xml", "xsl144X01/primary_doc.xml", "brka-8k.htm"],
                        "primaryDocDescription": [
                            "Annual report",
                            "Acquisition of beneficial ownership",
                            "Institutional investment manager holdings report",
                            "Notice of proposed sale of securities",
                            "Current report",
                        ],
                    }
                }
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_ownership_activism").search("Berkshire Hathaway 13F", limit=10)

    assert calls[0]["url"] == "https://www.sec.gov/files/company_tickers.json"
    assert calls[1]["url"] == "https://data.sec.gov/submissions/CIK0001067983.json"
    assert [result["form"] for result in results] == ["SC 13D", "13F-HR", "144"]
    assert results[0]["source_key"] == "sec_ownership_activism"
    assert results[0]["source_type"] == "ownership_activism"
    assert results[0]["ticker"] == "BRK-A"
    assert results[0]["ownership_form"] == "SC 13D"
    assert results[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1067983/000106798326000010/sc13d.htm"
    assert "Annual report" not in {result["snippet"] for result in results}
    assert "Current report" not in {result["snippet"] for result in results}


def test_federal_register_provider_maps_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "title": "Robotics Safety Rule",
                        "abstract": "A proposed rule for robotics safety.",
                        "document_number": "2026-12345",
                        "type": "Proposed Rule",
                        "publication_date": "2026-06-03",
                        "agency_names": ["Occupational Safety and Health Administration"],
                        "html_url": "https://www.federalregister.gov/documents/2026/06/03/2026-12345/robotics-safety-rule",
                        "pdf_url": "https://www.federalregister.gov/documents/full_text/pdf",
                        "citation": "91 FR 12345",
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("federal_register_documents").search("robotics", limit=1500)

    assert calls["url"] == "https://www.federalregister.gov/api/v1/documents.json"
    assert calls["params"]["conditions[term]"] == "robotics"
    assert calls["params"]["per_page"] == 1000
    assert calls["params"]["order"] == "newest"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "federal_register_documents"
    assert results[0]["source_type"] == "regulatory_policy"
    assert results[0]["document_number"] == "2026-12345"
    assert results[0]["agency_names"] == ["Occupational Safety and Health Administration"]


def test_cpsc_recall_provider_maps_product_safety_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> list[dict]:
            return [
                {
                    "RecallID": "2026-001",
                    "RecallNumber": "26-123",
                    "RecallDate": "2026-06-03",
                    "Title": "Robot Vacuum Recalled Due to Fire Hazard",
                    "Description": "The battery pack can overheat.",
                    "URL": "https://www.cpsc.gov/Recalls/2026/robot-vacuum-recalled",
                    "Products": [
                        {
                            "Name": "Robot Vacuum X",
                            "Description": "Autonomous vacuum cleaner.",
                        }
                    ],
                    "Hazards": [{"Name": "Fire"}],
                    "Remedies": [{"Name": "Refund"}, {"Name": "Repair"}],
                    "Manufacturers": [{"Name": "Example Robotics Co."}],
                    "Importers": [{"Name": "Example Import LLC"}],
                    "ConsumerContact": "example.com/recall",
                    "Units": "About 10,000",
                }
            ]

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("cpsc_recalls").search("robot vacuum", limit=500)

    assert calls["url"] == "https://www.saferproducts.gov/RestWebServices/Recall"
    assert calls["params"]["ProductName"] == "robot vacuum"
    assert calls["params"]["format"] == "json"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "cpsc_recalls"
    assert results[0]["source_type"] == "product_safety_recall"
    assert results[0]["title"] == "Robot Vacuum Recalled Due to Fire Hazard"
    assert results[0]["published_at"] == "2026-06-03"
    assert results[0]["recall_number"] == "26-123"
    assert results[0]["product_names"] == ["Robot Vacuum X"]
    assert results[0]["hazards"] == ["Fire"]
    assert results[0]["remedies"] == ["Refund", "Repair"]
    assert results[0]["companies"] == ["Example Robotics Co.", "Example Import LLC"]


def test_fda_enforcement_recall_provider_maps_multi_endpoint_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = ""

        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self.payload = payload or {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url == "https://api.fda.gov/food/enforcement.json":
            return Response(404)
        if url == "https://api.fda.gov/device/enforcement.json":
            return Response(
                200,
                {
                    "results": [
                        {
                            "classification": "Class II",
                            "status": "Ongoing",
                            "recalling_firm": "Example Surgical Robotics",
                            "product_description": "Robotic surgical system accessory",
                            "reason_for_recall": "Software issue may interrupt movement.",
                            "report_date": "20260603",
                            "recall_number": "Z-1234-2026",
                            "event_id": "123456",
                            "recall_initiation_date": "20260501",
                            "distribution_pattern": "Nationwide",
                            "product_quantity": "500 units",
                            "voluntary_mandated": "Voluntary: Firm initiated",
                            "city": "Boston",
                            "state": "MA",
                            "country": "United States",
                        }
                    ]
                },
            )
        return Response(
            200,
            {
                "results": [
                    {
                        "classification": "Class I",
                        "status": "Completed",
                        "recalling_firm": "Example Drug Co.",
                        "product_description": "Sterile device-adjacent kit",
                        "reason_for_recall": "Potential contamination.",
                        "report_date": "20260604",
                        "recall_number": "D-1234-2026",
                    }
                ]
            },
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fda_enforcement_recalls").search("robotic surgical system", limit=5)

    assert [call["url"] for call in calls] == [
        "https://api.fda.gov/device/enforcement.json",
        "https://api.fda.gov/food/enforcement.json",
        "https://api.fda.gov/drug/enforcement.json",
    ]
    assert calls[0]["params"]["search"] == 'recalling_firm:"robotic surgical system" product_description:"robotic surgical system" reason_for_recall:"robotic surgical system"'
    assert calls[0]["params"]["limit"] == 5
    assert calls[0]["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fda_enforcement_recalls"
    assert results[0]["source_type"] == "fda_enforcement_recall"
    assert results[0]["product_type"] == "device"
    assert results[0]["classification"] == "Class II"
    assert results[0]["recalling_firm"] == "Example Surgical Robotics"
    assert results[0]["reason_for_recall"] == "Software issue may interrupt movement."
    assert results[0]["distribution_pattern"] == "Nationwide"
    assert results[1]["product_type"] == "drug"
    assert results[1]["classification"] == "Class I"

def test_fda_device_510k_provider_maps_clearance_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "k_number": "K250674",
                        "device_name": "Vessel Sealer Curved",
                        "applicant": "Intuitive Surgical, Inc.",
                        "decision_date": "2025-06-13",
                        "decision_code": "SESE",
                        "decision_description": "Substantially Equivalent",
                        "date_received": "2025-03-06",
                        "clearance_type": "Traditional",
                        "product_code": "NAY",
                        "advisory_committee": "GU",
                        "advisory_committee_description": "Gastroenterology, Urology",
                        "review_advisory_committee": "SU",
                        "statement_or_summary": "Summary",
                        "third_party_flag": "N",
                        "expedited_review_flag": "",
                        "city": "Sunnyvale",
                        "state": "CA",
                        "country_code": "US",
                        "openfda": {
                            "device_name": "System, Surgical, Computer Controlled Instrument",
                            "device_class": "2",
                            "regulation_number": "876.1500",
                            "medical_specialty_description": "Gastroenterology, Urology",
                            "registration_number": ["1226146", "3017636737"],
                            "fei_number": ["3002681132"],
                        },
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fda_device_510k").search("robotic surgical system", limit=2000)

    assert calls["url"] == "https://api.fda.gov/device/510k.json"
    assert calls["params"]["limit"] == 1000
    assert 'device_name:"robotic surgical system"' in calls["params"]["search"]
    assert 'applicant:"robotic surgical system"' in calls["params"]["search"]
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fda_device_510k"
    assert results[0]["source_type"] == "fda_device_clearance"
    assert results[0]["k_number"] == "K250674"
    assert results[0]["device_name"] == "Vessel Sealer Curved"
    assert results[0]["applicant"] == "Intuitive Surgical, Inc."
    assert results[0]["decision_description"] == "Substantially Equivalent"
    assert results[0]["clearance_type"] == "Traditional"
    assert results[0]["product_code"] == "NAY"
    assert results[0]["openfda_device_class"] == "2"
    assert results[0]["openfda_regulation_number"] == "876.1500"


def test_fda_device_events_provider_maps_maude_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "event_type": "Injury",
                        "report_number": "MW5007258",
                        "date_received": "20080610",
                        "date_of_event": "20080429",
                        "date_added": "20080623",
                        "type_of_report": ["Initial submission"],
                        "source_type": ["User facility report"],
                        "report_to_fda": "N",
                        "product_problem_flag": "Y",
                        "pma_pmn_number": "K250674",
                        "device": [
                            {
                                "brand_name": "GYNECARE & INTUITIVE SURGICAL",
                                "generic_name": "MORCELLATOR X- TRACT, DAVINCI S SURGICAL ROBOT",
                                "manufacturer_d_name": "Intuitive Surgical, Inc.",
                                "device_report_product_code": "HET",
                                "device_operator": "HEALTH PROFESSIONAL",
                                "model_number": "DV-1",
                                "catalog_number": "CAT-1",
                                "lot_number": "LOT-1",
                                "udi_di": "UDI-DI",
                                "udi_public": "UDI-PUBLIC",
                                "openfda": {
                                    "device_name": "Laparoscope, Gynecologic",
                                    "device_class": "2",
                                    "regulation_number": "884.1720",
                                    "medical_specialty_description": "Obstetrics/Gynecology",
                                },
                            }
                        ],
                        "patient": [
                            {
                                "sequence_number_treatment": ["Hospitalization"],
                                "sequence_number_outcome": ["Required Intervention"],
                            }
                        ],
                        "mdr_text": [
                            {"text": "Device malfunctioned during a robotic surgical procedure."}
                        ],
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fda_device_events").search("robotic surgical system", limit=2000)

    assert calls["url"] == "https://api.fda.gov/device/event.json"
    assert calls["params"]["limit"] == 1000
    assert 'device.brand_name:"robotic surgical system"' in calls["params"]["search"]
    assert 'device.generic_name:"robotic surgical system"' in calls["params"]["search"]
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fda_device_events"
    assert results[0]["source_type"] == "fda_device_adverse_event"
    assert results[0]["event_type"] == "Injury"
    assert results[0]["report_number"] == "MW5007258"
    assert results[0]["device_brand_name"] == "GYNECARE & INTUITIVE SURGICAL"
    assert results[0]["device_product_code"] == "HET"
    assert results[0]["pma_pmn_number"] == "K250674"
    assert results[0]["openfda_device_class"] == "2"
    assert "Device malfunctioned" in results[0]["snippet"]


def test_fda_device_classification_provider_maps_product_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "product_code": "NAY",
                        "device_name": "System, Surgical, Computer Controlled Instrument",
                        "device_class": "2",
                        "regulation_number": "876.1500",
                        "medical_specialty": "GU",
                        "medical_specialty_description": "Gastroenterology, Urology",
                        "review_panel": "SU",
                        "review_code": "",
                        "submission_type_id": "1",
                        "third_party_flag": "N",
                        "life_sustain_support_flag": "N",
                        "implant_flag": "N",
                        "gmp_exempt_flag": "N",
                        "summary_malfunction_reporting": "Ineligible",
                        "unclassified_reason": "",
                        "definition": "Validated reprocessing instructions are required.",
                        "openfda": {
                            "k_number": ["K250674", "K243641"],
                            "registration_number": ["1226146"],
                            "fei_number": ["3002681132"],
                        },
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fda_device_classification").search("NAY", limit=2000)

    assert calls["url"] == "https://api.fda.gov/device/classification.json"
    assert calls["params"]["limit"] == 1000
    assert 'product_code:"NAY"' in calls["params"]["search"]
    assert 'device_name:"NAY"' in calls["params"]["search"]
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fda_device_classification"
    assert results[0]["source_type"] == "fda_device_classification"
    assert results[0]["product_code"] == "NAY"
    assert results[0]["device_name"] == "System, Surgical, Computer Controlled Instrument"
    assert results[0]["device_class"] == "2"
    assert results[0]["regulation_number"] == "876.1500"
    assert results[0]["submission_type_id"] == "1"
    assert results[0]["summary_malfunction_reporting"] == "Ineligible"
    assert results[0]["openfda_k_numbers"] == ["K250674", "K243641"]


def test_fda_device_registration_listing_provider_maps_establishments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "proprietary_name": ["Intuitive5779 (SDA,GP) - MCS Tip Cover"],
                        "establishment_type": [
                            "Sterilize Medical Device for Another Party (Contract Sterilizer)"
                        ],
                        "registration": {
                            "registration_number": "2032112",
                            "fei_number": "3003076831",
                            "status_code": "1",
                            "initial_importer_flag": "N",
                            "reg_expiry_date_year": "2026",
                            "name": "Isomedix Operations Inc.",
                            "address_line_1": "7685 ST.ANDREWS AVE.",
                            "city": "SAN DIEGO",
                            "state_code": "CA",
                            "iso_country_code": "US",
                            "zip_code": "92154",
                            "owner_operator": {
                                "firm_name": "STERIS Corporation",
                                "owner_operator_number": "9072619",
                                "contact_address": {
                                    "city": "Mentor",
                                    "state_code": "OH",
                                    "iso_country_code": "US",
                                },
                            },
                        },
                        "pma_number": "",
                        "k_number": "K250674",
                        "products": [
                            {
                                "product_code": "NAY",
                                "created_date": "2023-06-22",
                                "owner_operator_number": "9072619",
                                "exempt": "",
                                "openfda": {
                                    "device_name": "System, Surgical, Computer Controlled Instrument",
                                    "medical_specialty_description": "Gastroenterology, Urology",
                                    "regulation_number": "876.1500",
                                    "device_class": "2",
                                },
                            }
                        ],
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fda_device_registration_listing").search("NAY", limit=2000)

    assert calls["url"] == "https://api.fda.gov/device/registrationlisting.json"
    assert calls["params"]["limit"] == 1000
    assert 'products.product_code:"NAY"' in calls["params"]["search"]
    assert 'registration.name:"NAY"' in calls["params"]["search"]
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "fda_device_registration_listing"
    assert results[0]["source_type"] == "fda_device_registration_listing"
    assert results[0]["registration_number"] == "2032112"
    assert results[0]["fei_number"] == "3003076831"
    assert results[0]["firm_name"] == "Isomedix Operations Inc."
    assert results[0]["owner_operator_firm_name"] == "STERIS Corporation"
    assert results[0]["product_codes"] == ["NAY"]
    assert results[0]["product_count"] == 1
    assert results[0]["openfda_device_class"] == "2"
    assert results[0]["openfda_regulation_number"] == "876.1500"
    assert results[0]["establishment_types"] == [
        "Sterilize Medical Device for Another Party (Contract Sterilizer)"
    ]
    assert results[0]["proprietary_names"] == ["Intuitive5779 (SDA,GP) - MCS Tip Cover"]


def test_cfpb_complaint_provider_maps_consumer_complaints(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "complaint_id": "1234567",
                                "date_received": "2026-06-03",
                                "company": "Example Fintech Lender",
                                "product": "Consumer Loan",
                                "sub_product": "Installment loan",
                                "issue": "Problem with the payoff process",
                                "sub_issue": "Fees or interest",
                                "consumer_complaint_narrative": "Consumer says payoff balance was unclear.",
                                "company_response": "Closed with explanation",
                                "company_public_response": "Company believes it acted appropriately.",
                                "timely": "Yes",
                                "consumer_disputed": "N/A",
                                "submitted_via": "Web",
                                "date_sent_to_company": "2026-06-04",
                                "state": "CA",
                                "tags": "Servicemember",
                            }
                        }
                    ]
                }
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("cfpb_consumer_complaints").search("fintech lender", limit=500)

    assert calls["url"] == "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
    assert calls["params"]["search_term"] == "fintech lender"
    assert calls["params"]["size"] == 100
    assert calls["params"]["sort"] == "created_date_desc"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "cfpb_consumer_complaints"
    assert results[0]["source_type"] == "consumer_finance_complaint"
    assert results[0]["title"] == "Example Fintech Lender Consumer Loan Problem with the payoff process"
    assert results[0]["published_at"] == "2026-06-03"
    assert results[0]["complaint_id"] == "1234567"
    assert results[0]["company_response"] == "Closed with explanation"
    assert results[0]["timely_response"] == "Yes"
    assert results[0]["state"] == "CA"


def test_nhtsa_recall_provider_maps_vehicle_recalls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "Count": 1,
                "results": [
                    {
                        "NHTSACampaignNumber": "26V123000",
                        "Manufacturer": "Tesla, Inc.",
                        "Make": "Tesla",
                        "Model": "Model Y",
                        "ModelYear": "2024",
                        "Component": "ELECTRICAL SYSTEM",
                        "Summary": "The vehicle may lose rearview camera display.",
                        "Consequence": "Loss of rear visibility can increase crash risk.",
                        "Remedy": "Dealers will update software.",
                        "Notes": "Owners may contact customer service.",
                        "ReportReceivedDate": "2026-06-03",
                    }
                ],
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("nhtsa_recalls").search("2024 Tesla Model Y recall", limit=500)

    assert calls["url"] == "https://api.nhtsa.gov/recalls/recallsByVehicle"
    assert calls["params"] == {
        "make": "Tesla",
        "model": "Model Y",
        "modelYear": "2024",
    }
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "nhtsa_recalls"
    assert results[0]["source_type"] == "vehicle_safety_recall"
    assert results[0]["campaign_number"] == "26V123000"
    assert results[0]["manufacturer"] == "Tesla, Inc."
    assert results[0]["component"] == "ELECTRICAL SYSTEM"
    assert results[0]["consequence"] == "Loss of rear visibility can increase crash risk."
    assert results[0]["remedy"] == "Dealers will update software."


def test_epa_echo_provider_maps_facility_compliance_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url.endswith("get_facilities"):
            return Response({"Results": {"Message": "Success", "QueryID": "998", "QueryRows": "1"}})
        return Response(
            {
                "Results": {
                    "Message": "Working",
                    "Facilities": [
                        {
                            "RegistryID": "110000123456",
                            "FacName": "Example Battery Manufacturing",
                            "FacStreet": "100 Industrial Way",
                            "FacCity": "Fremont",
                            "FacState": "CA",
                            "FacZip": "94538",
                            "FacCounty": "Alameda",
                            "FacLat": "37.5483",
                            "FacLong": "-121.9886",
                            "FacSICCodes": "3691",
                            "FacNAICSCodes": "335911",
                            "FacComplianceStatus": "Significant Violation",
                            "FacQtrsWithNC": "3",
                            "FacFormalActionCount": "2",
                            "FacPenaltyCount": "1",
                            "LastRefreshDate": "2026-06-03",
                        }
                    ],
                }
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("epa_echo_facilities").search("battery manufacturing", limit=500)

    assert calls[0]["url"] == "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"
    assert calls[0]["params"]["p_fn"] == "battery manufacturing"
    assert calls[0]["params"]["output"] == "json"
    assert calls[0]["params"]["responseset"] == 100
    assert calls[1]["url"] == "https://echodata.epa.gov/echo/echo_rest_services.get_qid"
    assert calls[1]["params"]["qid"] == "998"
    assert calls[1]["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "epa_echo_facilities"
    assert results[0]["source_type"] == "environmental_compliance"
    assert results[0]["facility_name"] == "Example Battery Manufacturing"
    assert results[0]["registry_id"] == "110000123456"
    assert results[0]["city"] == "Fremont"
    assert results[0]["state"] == "CA"
    assert results[0]["compliance_status"] == "Significant Violation"
    assert results[0]["quarters_in_noncompliance"] == "3"
    assert results[0]["formal_actions"] == "2"
    assert results[0]["penalties"] == "1"
    assert results[0]["url"] == "https://echo.epa.gov/detailed-facility-report?fid=110000123456"


def test_clinicaltrials_provider_maps_study_records(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT01234567",
                                "briefTitle": "Robotic Surgery Trial",
                                "officialTitle": "A Study of a Robotic Surgical System",
                            },
                            "statusModule": {
                                "overallStatus": "RECRUITING",
                                "studyFirstSubmitDate": "2026-06-03",
                                "startDateStruct": {"date": "2026-07"},
                                "primaryCompletionDateStruct": {"date": "2027-07"},
                                "completionDateStruct": {"date": "2028-01"},
                            },
                            "sponsorCollaboratorsModule": {
                                "leadSponsor": {"name": "Example Robotics Health", "class": "INDUSTRY"},
                                "collaborators": [{"name": "Example Hospital"}],
                            },
                            "designModule": {
                                "studyType": "INTERVENTIONAL",
                                "phases": ["NA"],
                                "enrollmentInfo": {"count": 120, "type": "ESTIMATED"},
                            },
                            "conditionsModule": {
                                "conditions": ["Surgery"],
                            },
                            "armsInterventionsModule": {
                                "interventions": [{"name": "Robotic surgical system"}],
                            },
                            "outcomesModule": {
                                "primaryOutcomes": [{"measure": "Procedure success rate"}],
                            },
                            "contactsLocationsModule": {
                                "locations": [
                                    {
                                        "facility": "Example Hospital",
                                        "city": "Boston",
                                        "country": "United States",
                                    }
                                ]
                            },
                        }
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("clinicaltrials_studies").search("robotic surgery", limit=500)

    assert calls["url"] == "https://clinicaltrials.gov/api/v2/studies"
    assert calls["params"]["query.term"] == "robotic surgery"
    assert calls["params"]["pageSize"] == 100
    assert calls["params"]["format"] == "json"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "clinicaltrials_studies"
    assert results[0]["source_type"] == "clinical_trial_registry"
    assert results[0]["nct_id"] == "NCT01234567"
    assert results[0]["overall_status"] == "RECRUITING"
    assert results[0]["lead_sponsor"] == "Example Robotics Health"
    assert results[0]["lead_sponsor_class"] == "INDUSTRY"
    assert results[0]["phases"] == ["NA"]
    assert results[0]["enrollment_count"] == 120
    assert results[0]["conditions"] == ["Surgery"]
    assert results[0]["interventions"] == ["Robotic surgical system"]
    assert results[0]["primary_outcomes"] == ["Procedure success rate"]
    assert results[0]["locations"] == ["Example Hospital, Boston, United States"]


def test_cms_openpayments_provider_discovers_latest_datasets_and_maps_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict | list) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict | list:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url == "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items":
            return Response(
                [
                    {
                        "title": "2023 General Payment Data",
                        "identifier": "general-2023",
                        "description": "All general payments from the 2023 program year",
                    },
                    {
                        "title": "2024 General Payment Data",
                        "identifier": "general-2024",
                        "description": "All general payments from the 2024 program year",
                    },
                    {
                        "title": "2024 Research Payment Data",
                        "identifier": "research-2024",
                        "description": "Research Payment Data - Detailed Dataset 2024 Reporting Year",
                    },
                    {
                        "title": "2024 Ownership Payment Data",
                        "identifier": "ownership-2024",
                        "description": "Ownership Payment Data - Detailed Dataset 2024 Reporting Year",
                    },
                ]
            )
        return Response(
            {
                "results": [
                    {
                        "applicable_manufacturer_or_applicable_gpo_making_payment_name": "Medtronic USA, Inc.",
                        "covered_recipient_first_name": "Ada",
                        "covered_recipient_last_name": "Lovelace",
                        "covered_recipient_type": "Covered Recipient Physician",
                        "covered_recipient_npi": "1234567890",
                        "recipient_state": "MA",
                        "recipient_country": "United States",
                        "total_amount_of_payment_usdollars": "1200.50",
                        "date_of_payment": "01/15/2024",
                        "nature_of_payment_or_transfer_of_value": "Consulting Fee",
                        "form_of_payment_or_transfer_of_value": "Cash or cash equivalent",
                        "name_of_drug_or_biological_or_device_or_medical_supply_1": "Robotic surgical system",
                        "contextual_information": "Research and training relationship",
                    }
                ]
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("cms_openpayments").search("Medtronic", limit=6)

    assert calls[0]["url"] == "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items"
    assert calls[0]["params"]["limit"] == 100
    queried_urls = [str(call["url"]) for call in calls[1:]]
    assert "https://openpaymentsdata.cms.gov/api/1/datastore/query/general-2024/0" in queried_urls
    assert "https://openpaymentsdata.cms.gov/api/1/datastore/query/research-2024/0" in queried_urls
    assert "https://openpaymentsdata.cms.gov/api/1/datastore/query/ownership-2024/0" in queried_urls
    assert all(call["params"]["q"] == "Medtronic" for call in calls[1:])
    assert results[0]["source_key"] == "cms_openpayments"
    assert results[0]["source_type"] == "healthcare_payments"
    assert results[0]["program_year"] == "2024"
    assert results[0]["payment_type"] == "general"
    assert results[0]["manufacturer_or_gpo"] == "Medtronic USA, Inc."
    assert results[0]["covered_recipient"] == "Ada Lovelace"
    assert results[0]["covered_recipient_npi"] == "1234567890"
    assert results[0]["total_amount_usd"] == "1200.50"
    assert results[0]["nature_of_payment"] == "Consulting Fee"
    assert results[0]["related_product"] == "Robotic surgical system"


def test_census_trade_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("census_international_trade")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> list[list[str]]:
            return [
                ["CTY_CODE", "CTY_NAME", "I_COMMODITY", "I_COMMODITY_LDESC", "GEN_VAL_MO", "GEN_VAL_YR", "time"],
                ["5700", "CHINA", "854231", "Electronic integrated circuits", "1000000", "12000000", "2026-05"],
            ]

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("CENSUS_API_KEY", "unit-census-key")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("census_international_trade").search("854231 imports", limit=200)

    assert calls["url"] == "https://api.census.gov/data/timeseries/intltrade/imports/hs"
    assert calls["params"]["get"] == "CTY_CODE,CTY_NAME,I_COMMODITY,I_COMMODITY_LDESC,GEN_VAL_MO,GEN_VAL_YR"
    assert calls["params"]["I_COMMODITY"] == "854231"
    assert calls["params"]["time"] == "latest"
    assert calls["params"]["key"] == "unit-census-key"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "census_international_trade"
    assert results[0]["source_type"] == "trade_flows"
    assert results[0]["country_name"] == "CHINA"
    assert results[0]["commodity_code"] == "854231"
    assert results[0]["monthly_value"] == "1000000"


def test_fred_series_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("fred_series_search")
    return

    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url == "https://api.stlouisfed.org/fred/series/search":
            return Response(
                {
                    "seriess": [
                        {
                            "id": "CPIAUCSL",
                            "title": "Consumer Price Index for All Urban Consumers: All Items",
                            "observation_start": "1947-01-01",
                            "observation_end": "2026-05-01",
                            "frequency": "Monthly",
                            "frequency_short": "M",
                            "units": "Index 1982-1984=100",
                            "units_short": "Index",
                            "seasonal_adjustment": "Seasonally Adjusted",
                            "last_updated": "2026-06-01 07:45:00-05",
                            "popularity": 94,
                            "group_popularity": 94,
                            "notes": "CPI inflation benchmark.",
                        }
                    ]
                }
            )
        return Response(
            {
                "observations": [
                    {
                        "realtime_start": "2026-06-03",
                        "realtime_end": "2026-06-03",
                        "date": "2026-05-01",
                        "value": "320.580",
                    }
                ]
            }
        )

    import requests

    monkeypatch.setenv("FRED_API_KEY", "unit-fred-key")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("fred_series_search").search("inflation", limit=2000)

    assert calls[0]["url"] == "https://api.stlouisfed.org/fred/series/search"
    assert calls[0]["params"]["api_key"] == "unit-fred-key"
    assert calls[0]["params"]["file_type"] == "json"
    assert calls[0]["params"]["search_text"] == "inflation"
    assert calls[0]["params"]["limit"] == 1000
    assert calls[1]["url"] == "https://api.stlouisfed.org/fred/series/observations"
    assert calls[1]["params"]["series_id"] == "CPIAUCSL"
    assert calls[1]["params"]["sort_order"] == "desc"
    assert calls[1]["params"]["limit"] == 1
    assert results[0]["source_key"] == "fred_series_search"
    assert results[0]["source_type"] == "macroeconomic_time_series"
    assert results[0]["series_id"] == "CPIAUCSL"
    assert results[0]["latest_date"] == "2026-05-01"
    assert results[0]["latest_value"] == "320.580"
    assert results[0]["frequency"] == "Monthly"
    assert results[0]["units"] == "Index 1982-1984=100"
    assert results[0]["url"] == "https://fred.stlouisfed.org/series/CPIAUCSL"


def test_gnews_funding_provider_maps_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "articles": [
                    {
                        "title": "Robotics startup raises Series B",
                        "description": "The company raised new financing.",
                        "content": "Robotics funding news.",
                        "url": "https://example.com/robotics-series-b",
                        "image": "https://example.com/image.jpg",
                        "publishedAt": "2026-06-03T12:00:00Z",
                        "source": {
                            "name": "Example News",
                            "url": "https://example.com",
                        },
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("GNEWS_API_KEY", "unit-gnews-token")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("gnews_funding_news").search("robotics", limit=50)

    assert calls["url"] == "https://gnews.io/api/v4/search"
    assert calls["params"]["q"] == "(robotics) AND (funding OR financing OR acquisition OR merger OR investment OR venture)"
    assert calls["params"]["max"] == 10
    assert calls["params"]["apikey"] == "unit-gnews-token"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "gnews_funding_news"
    assert results[0]["source_type"] == "funding_news"
    assert results[0]["title"] == "Robotics startup raises Series B"
    assert results[0]["source_name"] == "Example News"


def test_sec_enforcement_provider_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = """
<html>
  <body>
    <a href="/enforcement-litigation/litigation-releases/rss">Litigation Releases RSS Feed</a>
    <time datetime="2026-06-05T00:00:00Z">June 5, 2026</time>
    <a href="/enforcement-litigation/litigation-releases/lr-26561">JianQing Li</a>
    <span>Release No. LR-26561</span>
  </body>
</html>
"""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            raise ValueError("HTML response")

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_enforcement_search").search("robotics", limit=75)

    assert calls["url"] == "https://www.sec.gov/enforcement-litigation/litigation-releases"
    assert calls["params"] == {}
    assert calls["headers"]["Accept"] == "text/html,application/xhtml+xml,application/json"
    assert calls["headers"]["User-Agent"] == "zhaoping-agent/0.1 research contact@example.invalid"
    assert results[0]["source_key"] == "sec_enforcement_search"
    assert results[0]["source_type"] == "regulatory_enforcement"
    assert results[0]["title"] == "JianQing Li"
    assert results[0]["url"] == "https://www.sec.gov/enforcement-litigation/litigation-releases/lr-26561"
    assert results[0]["published_at"] == "2026-06-05"
    assert results[0]["release_no"] == "LR-26561"
    assert results[0]["agency"] == "SEC"


def test_usajobs_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("usajobs_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "SearchResult": {
                    "SearchResultItems": [
                        {
                            "MatchedObjectDescriptor": {
                                "PositionTitle": "Robotics Engineer",
                                "PositionURI": "https://www.usajobs.gov/job/123456789",
                                "QualificationSummary": "Build and evaluate robotics systems.",
                                "PublicationStartDate": "2026-06-01",
                                "ApplicationCloseDate": "2026-06-15",
                                "OrganizationName": "National Robotics Lab",
                                "DepartmentName": "Department of Example",
                                "PositionRemuneration": [
                                    {
                                        "MinimumRange": "110000",
                                        "MaximumRange": "155000",
                                        "RateIntervalCode": "PA",
                                    }
                                ],
                                "PositionLocation": [
                                    {"LocationName": "Pittsburgh, Pennsylvania"},
                                    {"LocationName": "Boston, Massachusetts"},
                                ],
                                "JobGrade": ["GS-14"],
                                "PositionSchedule": [{"Name": "Full-time"}],
                            }
                        }
                    ]
                }
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("USAJOBS_API_KEY", "unit-usajobs-key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "unit@example.com")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("usajobs_search").search("robotics engineer", limit=600)

    assert calls["url"] == "https://data.usajobs.gov/api/Search"
    assert calls["params"]["Keyword"] == "robotics engineer"
    assert calls["params"]["ResultsPerPage"] == 500
    assert calls["headers"]["Authorization-Key"] == "unit-usajobs-key"
    assert calls["headers"]["User-Agent"] == "unit@example.com"
    assert calls["headers"]["Host"] == "data.usajobs.gov"
    assert results[0]["source_key"] == "usajobs_search"
    assert results[0]["source_type"] == "job_salary"
    assert results[0]["title"] == "Robotics Engineer"
    assert results[0]["salary_min"] == "110000"
    assert results[0]["salary_max"] == "155000"
    assert results[0]["salary_rate_interval"] == "PA"
    assert results[0]["locations"] == ["Pittsburgh, Pennsylvania", "Boston, Massachusetts"]


def test_openalex_works_search_provider_maps_academic_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W123",
                        "doi": "https://doi.org/10.48550/arXiv.2401.00001",
                        "display_name": "Robot Foundation Model",
                        "publication_date": "2026-05-01",
                        "publication_year": 2026,
                        "cited_by_count": 42,
                        "primary_location": {
                            "landing_page_url": "https://arxiv.org/abs/2401.00001",
                        },
                        "authorships": [
                            {
                                "author": {"display_name": "A. Researcher"},
                                "institutions": [{"display_name": "Tsinghua University"}],
                            },
                        ],
                        "concepts": [
                            {"display_name": "Robotics"},
                        ],
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("openalex_works_search").search("robot foundation model", limit=30)

    assert calls["url"] == "https://api.openalex.org/works"
    assert calls["params"]["search"] == "robot foundation model"
    assert calls["params"]["per-page"] == 25
    assert calls["params"]["sort"] == "relevance_score:desc"
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "openalex_works_search"
    assert results[0]["source_type"] == "academic"
    assert results[0]["title"] == "Robot Foundation Model"
    assert results[0]["url"] == "https://arxiv.org/abs/2401.00001"
    assert results[0]["authors"] == ["A. Researcher"]
    assert results[0]["institutions"] == ["Tsinghua University"]


def test_openalex_author_and_institution_providers_map_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url.endswith("/authors"):
            return Response(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/A123",
                            "display_name": "Ada Researcher",
                            "works_count": 12,
                            "cited_by_count": 120,
                            "last_known_institutions": [{"display_name": "Zhejiang University"}],
                            "topics": [{"display_name": "Robot learning"}],
                        }
                    ]
                }
            )
        return Response(
            {
                "results": [
                    {
                        "id": "https://openalex.org/I123",
                        "display_name": "Shanghai Jiao Tong University",
                        "homepage_url": "https://www.sjtu.edu.cn",
                        "country_code": "CN",
                        "works_count": 50000,
                        "cited_by_count": 900000,
                    }
                ]
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    authors = router.search("openalex_authors_search").search("robot learning zhejiang", limit=50)
    institutions = router.search("openalex_institutions_search").search("Shanghai Jiao Tong robotics", limit=50)

    assert calls[0]["url"] == "https://api.openalex.org/authors"
    assert calls[0]["params"]["per-page"] == 25
    assert authors[0]["source_key"] == "openalex_authors_search"
    assert authors[0]["source_type"] == "academic_author"
    assert authors[0]["title"] == "Ada Researcher"
    assert authors[0]["institutions"] == ["Zhejiang University"]
    assert authors[0]["topics"] == ["Robot learning"]
    assert calls[1]["url"] == "https://api.openalex.org/institutions"
    assert institutions[0]["source_key"] == "openalex_institutions_search"
    assert institutions[0]["source_type"] == "academic_institution"
    assert institutions[0]["url"] == "https://www.sjtu.edu.cn"


def test_semantic_scholar_paper_and_author_providers_map_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if "/paper/search" in url:
            return Response(
                {
                    "data": [
                        {
                            "paperId": "paper_1",
                            "title": "Vision-Language-Action Robotics",
                            "url": "https://www.semanticscholar.org/paper/paper_1",
                            "abstract": "Robotics policy learning.",
                            "year": 2026,
                            "citationCount": 10,
                            "authors": [{"name": "Ada Researcher", "authorId": "a1"}],
                            "venue": "CoRL",
                        }
                    ]
                }
            )
        return Response(
            {
                "data": [
                    {
                        "authorId": "a1",
                        "name": "Ada Researcher",
                        "url": "https://www.semanticscholar.org/author/a1",
                        "paperCount": 7,
                        "citationCount": 80,
                        "hIndex": 5,
                    }
                ]
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    papers = router.search("semantic_scholar_papers_search").search("robot VLA", limit=200)
    authors = router.search("semantic_scholar_authors_search").search("Ada Researcher", limit=200)

    assert calls[0]["url"] == "https://api.semanticscholar.org/graph/v1/paper/search"
    assert calls[0]["params"]["limit"] == 100
    assert "title,year,authors" in calls[0]["params"]["fields"]
    assert papers[0]["source_key"] == "semantic_scholar_papers_search"
    assert papers[0]["source_type"] == "academic"
    assert papers[0]["title"] == "Vision-Language-Action Robotics"
    assert papers[0]["authors"] == ["Ada Researcher"]
    assert calls[1]["url"] == "https://api.semanticscholar.org/graph/v1/author/search"
    assert authors[0]["source_key"] == "semantic_scholar_authors_search"
    assert authors[0]["source_type"] == "academic_author"
    assert authors[0]["h_index"] == 5


def test_sec_edgar_provider_maps_company_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url == "https://www.sec.gov/files/company_tickers.json":
            return Response(
                {
                    "0": {
                        "cik_str": 789019,
                        "ticker": "MSFT",
                        "title": "MICROSOFT CORP",
                    }
                }
            )
        return Response(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K", "8-K"],
                        "filingDate": ["2026-06-01", "2026-05-20"],
                        "reportDate": ["2026-03-31", "2026-05-20"],
                        "accessionNumber": ["0000950170-26-000001", "0000950170-26-000002"],
                        "primaryDocument": ["msft-20260331.htm", "msft-8k.htm"],
                        "primaryDocDescription": ["Annual report", "Current report"],
                    }
                }
            }
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sec_edgar_company_filings").search("MSFT annual report", limit=1)

    assert calls[0]["url"] == "https://www.sec.gov/files/company_tickers.json"
    assert calls[1]["url"] == "https://data.sec.gov/submissions/CIK0000789019.json"
    assert calls[0]["headers"]["User-Agent"] == "zhaoping-agent/0.1 research contact@example.invalid"
    assert results[0]["source_key"] == "sec_edgar_company_filings"
    assert results[0]["source_type"] == "regulatory_filings"
    assert results[0]["ticker"] == "MSFT"
    assert results[0]["form"] == "10-K"
    assert results[0]["url"] == "https://www.sec.gov/Archives/edgar/data/789019/000095017026000001/msft-20260331.htm"


def test_gdelt_doc_news_provider_maps_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
            self.status_code = status_code
            self.payload = payload or {}
            self.text = text

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                import requests

                raise requests.HTTPError("rate limited", response=self)

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if len(calls) == 1:
            return Response(429, text="Please limit requests to one every 5 seconds")
        return Response(
            200,
            {
                "articles": [
                    {
                        "title": "Robotics startup raises new funding",
                        "url": "https://example-news.com/robotics-funding",
                        "seendate": "20260603T120000Z",
                        "domain": "example-news.com",
                        "sourcecountry": "US",
                        "language": "English",
                        "socialimage": "https://example-news.com/image.jpg",
                    }
                ]
            },
        )

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    router = ServiceRouter(load_app_config())
    results = router.search("gdelt_doc_news").search("robotics funding", limit=300)

    assert len(calls) == 2
    assert calls[0]["url"] == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert calls[0]["params"]["query"] == "robotics funding"
    assert calls[0]["params"]["mode"] == "ArtList"
    assert calls[0]["params"]["format"] == "json"
    assert calls[0]["params"]["maxrecords"] == 250
    assert calls[0]["params"]["timespan"] == "7d"
    assert results[0]["source_key"] == "gdelt_doc_news"
    assert results[0]["source_type"] == "news_media"
    assert results[0]["title"] == "Robotics startup raises new funding"
    assert results[0]["domain"] == "example-news.com"


def test_usaspending_award_provider_maps_awards(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "Award ID": "CONT_AWD_123",
                        "Recipient Name": "ROBOTICS INC",
                        "Award Amount": 1250000.0,
                        "Start Date": "2026-01-01",
                        "End Date": "2026-12-31",
                        "Awarding Agency": "Department of Defense",
                        "Awarding Sub Agency": "Defense Advanced Research Projects Agency",
                        "Description": "Robotics research contract",
                        "Award Type": "Definitive Contract",
                    }
                ]
            }

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    router = ServiceRouter(load_app_config())
    results = router.search("usaspending_awards").search("robotics", limit=150)

    assert calls["url"] == "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    assert calls["headers"]["Content-Type"] == "application/json"
    assert calls["json"]["filters"]["keywords"] == ["robotics"]
    assert calls["json"]["filters"]["award_type_codes"] == ["A", "B", "C", "D"]
    assert calls["json"]["limit"] == 100
    assert calls["json"]["sort"] == "Award Amount"
    assert calls["json"]["filters"]["time_period"] == [
        {"start_date": "2023-10-01", "end_date": "2026-09-30"}
    ]
    assert results[0]["source_key"] == "usaspending_awards"
    assert results[0]["source_type"] == "procurement_awards"
    assert results[0]["recipient_name"] == "ROBOTICS INC"
    assert results[0]["award_amount"] == 1250000.0


def test_sam_gov_opportunity_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("sam_gov_opportunities")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "totalRecords": 1,
                "opportunitiesData": [
                    {
                        "noticeId": "ff826a59eac743c4a1a07ff5e0cf3e3a",
                        "title": "Robotics autonomy prototype",
                        "solicitationNumber": "DARPA-RA-26-001",
                        "fullParentPathName": "DEPARTMENT OF DEFENSE.DEFENSE ADVANCED RESEARCH PROJECTS AGENCY",
                        "fullParentPathCode": "097.5700",
                        "postedDate": "2026-06-03",
                        "type": "Sources Sought",
                        "baseType": "Sources Sought",
                        "archiveType": "autocustom",
                        "archiveDate": "2027-01-02",
                        "typeOfSetAsideDescription": "Small Business Set-Aside",
                        "typeOfSetAside": "SBA",
                        "responseDeadLine": "2026-07-01T16:00:00-05:00",
                        "naicsCode": "541715",
                        "classificationCode": "AC13",
                        "active": "Yes",
                        "award": {
                            "date": "2026-08-01",
                            "number": "HR001126C0001",
                            "amount": "2500000",
                            "awardee": {
                                "name": "ROBOTICS INC",
                                "ueiSAM": "025114695AST",
                            },
                        },
                        "pointOfContact": [
                            {
                                "type": "primary",
                                "email": "contracting@example.mil",
                                "phone": "5551234567",
                                "title": "Contracting Officer",
                                "fullName": "Ada Contracting",
                            }
                        ],
                        "description": "https://api.sam.gov/prod/opportunities/v1/noticedesc?noticeid=ff826",
                        "organizationType": "OFFICE",
                        "officeAddress": {
                            "zipcode": "22203",
                            "city": "ARLINGTON",
                            "state": "VA",
                        },
                        "placeOfPerformance": {
                            "city": {"name": "Pittsburgh"},
                            "state": {"code": "PA"},
                            "zip": "15213",
                            "country": {"code": "USA"},
                        },
                        "additionalInfoLink": "https://sam.gov/additional",
                        "uiLink": "https://sam.gov/opp/ff826/view",
                        "resourceLinks": ["https://sam.gov/api/prod/opps/v3/opportunities/resources/files/123/download"],
                    }
                ],
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("SAM_GOV_API_KEY", "unit-sam-key")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("sam_gov_opportunities").search("robotics", limit=2000)

    assert calls["url"] == "https://api.sam.gov/opportunities/v2/search"
    assert calls["params"]["api_key"] == "unit-sam-key"
    assert calls["params"]["title"] == "robotics"
    assert calls["params"]["postedFrom"] == "01/01/2025"
    assert calls["params"]["postedTo"] == "12/31/2026"
    assert calls["params"]["limit"] == 1000
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "sam_gov_opportunities"
    assert results[0]["source_type"] == "procurement_opportunity"
    assert results[0]["title"] == "Robotics autonomy prototype"
    assert results[0]["notice_id"] == "ff826a59eac743c4a1a07ff5e0cf3e3a"
    assert results[0]["solicitation_number"] == "DARPA-RA-26-001"
    assert results[0]["opportunity_type"] == "Sources Sought"
    assert results[0]["set_aside_code"] == "SBA"
    assert results[0]["naics_code"] == "541715"
    assert results[0]["response_deadline"] == "2026-07-01T16:00:00-05:00"
    assert results[0]["awardee_name"] == "ROBOTICS INC"
    assert results[0]["contact_email"] == "contracting@example.mil"
    assert results[0]["place_of_performance_state"] == "PA"
    assert results[0]["resource_links"] == [
        "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/123/download"
    ]


def test_grants_gov_opportunity_provider_maps_grant_opportunities(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "errorcode": 0,
                "msg": "Webservice Succeeds",
                "data": {
                    "hitCount": 1,
                    "oppHits": [
                        {
                            "id": "324369",
                            "number": "PD-20-144Y",
                            "title": "Foundational Research in Robotics",
                            "agencyCode": "NSF",
                            "agency": "U.S. National Science Foundation",
                            "openDate": "02/12/2020",
                            "closeDate": "",
                            "oppStatus": "posted",
                            "docType": "synopsis",
                            "cfdaList": ["47.041", "47.070"],
                        }
                    ],
                },
            }

    def fake_post(url: str, *, json: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    router = ServiceRouter(load_app_config())
    results = router.search("grants_gov_opportunities").search("robotics", limit=2000)

    assert calls["url"] == "https://api.grants.gov/v1/api/search2"
    assert calls["json"] == {
        "rows": 1000,
        "keyword": "robotics",
        "oppStatuses": "forecasted|posted",
    }
    assert calls["headers"]["Accept"] == "application/json"
    assert calls["headers"]["Content-Type"] == "application/json"
    assert results[0]["source_key"] == "grants_gov_opportunities"
    assert results[0]["source_type"] == "grant_opportunity"
    assert results[0]["title"] == "Foundational Research in Robotics"
    assert results[0]["opportunity_id"] == "324369"
    assert results[0]["opportunity_number"] == "PD-20-144Y"
    assert results[0]["agency_code"] == "NSF"
    assert results[0]["agency"] == "U.S. National Science Foundation"
    assert results[0]["open_date"] == "02/12/2020"
    assert results[0]["opportunity_status"] == "posted"
    assert results[0]["document_type"] == "synopsis"
    assert results[0]["cfda_list"] == ["47.041", "47.070"]
    assert results[0]["url"] == "https://www.grants.gov/search-results-detail/324369"


def test_patentsview_provider_maps_patents(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "data": [
                    {
                        "patent_id": "12345678",
                        "patent_title": "Robot manipulation system",
                        "patent_date": "2026-02-01",
                        "patent_abstract": "A robotic manipulation method.",
                        "assignees": [
                            {"assignee_organization": "ROBOTICS LAB INC"},
                        ],
                        "inventors": [
                            {"inventor_first_name": "Ada", "inventor_last_name": "Lovelace"},
                        ],
                    }
                ]
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("patentsview_patents").search("robot manipulation", limit=150)

    assert calls["url"] == "https://search.patentsview.org/api/v1/patent/"
    assert json.loads(calls["params"]["q"])["_or"][0]["_text_any"]["patent_title"] == "robot manipulation"
    assert "patent_id" in json.loads(calls["params"]["f"])
    assert json.loads(calls["params"]["o"])["size"] == 100
    assert calls["headers"]["Accept"] == "application/json"
    assert results[0]["source_key"] == "patentsview_patents"
    assert results[0]["source_type"] == "patent"
    assert results[0]["patent_number"] == "12345678"
    assert results[0]["assignees"] == ["ROBOTICS LAB INC"]
    assert results[0]["inventors"] == ["Ada Lovelace"]


def test_patentsview_provider_returns_transition_notice_for_migrated_api(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 301
        text = "<html>PatentsView transition guide</html>"
        headers = {"location": "https://data.uspto.gov/support/transition-guide/patentsview"}

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            raise ValueError("HTML response")

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("patentsview_patents").search("robot manipulation", limit=1)

    assert results[0]["source_key"] == "patentsview_patents"
    assert results[0]["retrieval_status"] == "temporarily_unavailable"
    assert results[0]["url"] == "https://data.uspto.gov/support/transition-guide/patentsview"


def test_patentsview_provider_returns_transition_notice_for_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, params: dict, headers: dict, timeout: int):
        import requests

        raise requests.ConnectionError("PatentsView migrated")

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("patentsview_patents").search("robot manipulation", limit=1)

    assert results[0]["source_key"] == "patentsview_patents"
    assert results[0]["retrieval_status"] == "temporarily_unavailable"


def test_ofac_sanctions_provider_maps_xml_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    sdn_xml = b"""
<sdnList>
  <sdnEntry>
    <uid>42</uid>
    <firstName>Example</firstName>
    <lastName>Robotics</lastName>
    <sdnType>Entity</sdnType>
    <programList><program>CYBER2</program></programList>
  </sdnEntry>
</sdnList>
"""
    consolidated_xml = b"<consolidatedList></consolidatedList>"

    class Response:
        status_code = 200
        text = ""

        def __init__(self, content: bytes) -> None:
            self.content = content

        @staticmethod
        def raise_for_status() -> None:
            return None

    def fake_get(url: str, *, headers: dict, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url == "https://www.treasury.gov/ofac/downloads/sdn.xml":
            return Response(sdn_xml)
        return Response(consolidated_xml)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    results = router.search("ofac_sanctions_lists").search("Example Robotics", limit=5)

    assert calls[0]["url"] == "https://www.treasury.gov/ofac/downloads/sdn.xml"
    assert calls[0]["headers"]["Accept"] == "application/xml,text/xml,*/*"
    assert results[0]["source_key"] == "ofac_sanctions_lists"
    assert results[0]["source_type"] == "sanctions"
    assert results[0]["uid"] == "42"
    assert results[0]["title"] == "Example Robotics"
    assert results[0]["programs"] == ["CYBER2"]


def test_openrouter_chat_provider_maps_messages_and_models(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class ChatResponse:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "id": "chatcmpl_test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                        }
                    }
                ],
            }

    class ModelsResponse:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"data": [{"id": "openrouter/auto", "name": "Auto Router"}]}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> ChatResponse:
        calls["post_url"] = url
        calls["post_headers"] = headers
        calls["post_json"] = json
        calls["post_timeout"] = timeout
        return ChatResponse()

    def fake_get(url: str, *, headers: dict, timeout: int) -> ModelsResponse:
        calls["get_url"] = url
        calls["get_headers"] = headers
        calls["get_timeout"] = timeout
        return ModelsResponse()

    import requests

    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-openrouter-token")
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    llm = router.llm("openrouter_online_research")
    response = llm.message("judge this evidence", max_tokens=32)
    models = llm.list_models()

    assert calls["post_url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls["post_headers"]["Authorization"] == "Bearer unit-openrouter-token"
    assert calls["post_headers"]["X-Title"] == "Zhaoping Robot Talent Agent"
    assert calls["post_json"]["model"] == "openrouter/auto"
    assert calls["post_json"]["tools"] == [{"type": "openrouter:web_search"}]
    assert calls["post_json"]["messages"] == [{"role": "user", "content": "judge this evidence"}]
    assert response["choices"][0]["message"]["content"] == "ok"
    assert calls["get_url"] == "https://openrouter.ai/api/v1/models"
    assert models[0]["id"] == "openrouter/auto"


def test_recruiting_growth_services_are_configured() -> None:
    config = load_app_config()

    # Email capabilities are first-class registered services; without keys they
    # surface as missing_key instead of pretending the capability doesn't exist.
    assert config.default_service_name("email_delivery") == "resend_email_delivery"
    assert config.default_service_name("email_discovery") == "hunter_email_discovery"
    assert config.default_service_name("email_verification") == "zerobounce_email_verification"
    assert config.default_service_name("scraping") == "opencli_crawl_scrape"

    retired_services = {
        "pdl_people_search",
        "x_recent_posts_search",
        "crustdata_signal_search",
        "hunter_email_finder",
        "zerobounce_email_validation",
        "neverbounce_email_validation",
        "postmark_compliant_email",
        "sendgrid_compliant_email",
        "mailtrap_smtp_email",
        "firecrawl_scrape",
        "apify_actor_run",
        "brightdata_web_unlocker",
        "browserbase_session",
    }
    assert retired_services.isdisjoint(config.services)
    assert config.service("opencli_crawl_scrape").provider == "opencli_crawl"


def test_recruiting_growth_services_show_status_without_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    secrets = {
        "PDL_API_KEY": "unit-pdl-secret",
        "X_BEARER_TOKEN": "unit-x-secret",
        "CRUSTDATA_API_KEY": "unit-crustdata-secret",
        "HUNTER_API_KEY": "unit-hunter-secret",
        "ZEROBOUNCE_API_KEY": "unit-zerobounce-secret",
        "NEVERBOUNCE_API_KEY": "unit-neverbounce-secret",
        "POSTMARK_SERVER_TOKEN": "unit-postmark-secret",
        "SENDGRID_API_KEY": "unit-sendgrid-secret",
        "MAILTRAP_SMTP_HOST": "sandbox.smtp.mailtrap.io",
        "MAILTRAP_SMTP_PORT": "2525",
        "MAILTRAP_SMTP_USERNAME": "unit-mailtrap-user",
        "MAILTRAP_SMTP_PASSWORD": "unit-mailtrap-secret",
        "RECRUITING_CONTACT_EMAIL": "recruiting@example.com",
        "UNSUBSCRIBE_BASE_URL": "https://example.com/unsubscribe",
        "APIFY_API_TOKEN": "unit-apify-secret",
        "BRIGHTDATA_API_KEY": "unit-brightdata-secret",
        "BRIGHTDATA_ZONE": "unit-zone",
        "BROWSERBASE_API_KEY": "unit-browserbase-secret",
        "BROWSERBASE_PROJECT_ID": "unit-project",
        "FIRECRAWL_API_KEY": "unit-firecrawl-secret",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)

    status = get_integration_status(load_app_config())
    payload = json.dumps(status, ensure_ascii=False)
    services = {service["name"]: service for service in status["services"]}
    capabilities = {capability["id"]: capability for capability in status["capabilities"]}

    retired_services = {
        "pdl_people_search",
        "x_recent_posts_search",
        "crustdata_signal_search",
        "hunter_email_finder",
        "zerobounce_email_validation",
        "neverbounce_email_validation",
        "postmark_compliant_email",
        "sendgrid_compliant_email",
        "mailtrap_smtp_email",
        "firecrawl_scrape",
        "apify_actor_run",
        "brightdata_web_unlocker",
        "browserbase_session",
    }
    assert retired_services.isdisjoint(services)
    # Hunter/ZeroBounce keys are set by this test, so discovery/verification
    # connect; delivery still lacks RESEND_API_KEY/OUTREACH_FROM_EMAIL.
    assert capabilities["email_discovery_api"]["status"] in {"active", "available"}
    assert capabilities["email_verification_api"]["status"] in {"active", "available"}
    assert capabilities["email_delivery_api"]["status"] == "missing_key"
    assert capabilities["scraping_api"]["connected_name_zh"] == "OpenCLI 本地抓取"
    assert services["opencli_crawl_scrape"]["name_zh"] == "OpenCLI 本地抓取"
    assert services["opencli_crawl_scrape"]["code_path"] == "app/providers/scraping.py"
    for value in secrets.values():
        assert value not in payload


def test_integration_env_save_updates_local_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("GITHUB_TOKEN=old-token\nHF_TOKEN=\n", encoding="utf-8")
    monkeypatch.setenv("ROBOT_AGENT_ENV_PATH", str(env_path))

    client = TestClient(app)
    response = client.post(
        "/api/integrations/env",
        json={"values": {"GITHUB_TOKEN": "new-token", "HF_TOKEN": "hf-token"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == ["GITHUB_TOKEN", "HF_TOKEN"]
    assert "new-token" not in json.dumps(payload)
    saved = env_path.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN=new-token" in saved
    assert "HF_TOKEN=hf-token" in saved


def test_integration_env_save_rejects_unknown_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ROBOT_AGENT_ENV_PATH", str(env_path))

    client = TestClient(app)
    response = client.post("/api/integrations/env", json={"values": {"NOT_ALLOWED": "secret"}})

    assert response.status_code == 422
    assert env_path.read_text(encoding="utf-8") == ""


def test_pdl_people_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("pdl_people_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "status": 200,
                "data": [
                    {
                        "id": "pdl_1",
                        "full_name": "Ada Lovelace",
                        "job_title": "Robotics ML Lead",
                        "job_company_name": "Robot Labs",
                        "location_name": "San Francisco, California",
                        "linkedin_url": "https://www.linkedin.com/in/ada",
                        "github_url": "https://github.com/ada",
                        "emails": [{"address": "ada@robot.example", "type": "professional"}],
                    }
                ],
                "total": 1,
            }

    def fake_get(url: str, *, headers: dict, params: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["headers"] = headers
        calls["params"] = params
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("PDL_API_KEY", "unit-pdl-key")
    monkeypatch.setattr(requests, "get", fake_get)

    results = ServiceRouter(load_app_config()).search("pdl_people_search").search("robotics ml", limit=150)

    assert calls["url"] == "https://api.peopledatalabs.com/v5/person/search"
    assert calls["headers"]["X-api-key"] == "unit-pdl-key"
    assert calls["params"]["size"] == 100
    assert results[0]["source_key"] == "pdl_people_search"
    assert results[0]["source_type"] == "identity_enrichment"
    assert results[0]["title"] == "Ada Lovelace"
    assert results[0]["company"] == "Robot Labs"
    assert results[0]["social_links"]["github"] == "https://github.com/ada"


def test_x_recent_posts_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("x_recent_posts_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "data": [
                    {
                        "id": "1800000000000000000",
                        "author_id": "42",
                        "text": "Robot VLA demo released",
                        "created_at": "2026-06-01T12:00:00Z",
                        "public_metrics": {"like_count": 10, "retweet_count": 2},
                    }
                ],
                "includes": {
                    "users": [
                        {
                            "id": "42",
                            "username": "roboticist",
                            "name": "Roboticist",
                            "public_metrics": {"followers_count": 1000},
                        }
                    ]
                },
            }

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("X_BEARER_TOKEN", "unit-x-token")
    monkeypatch.setattr(requests, "get", fake_get)

    results = ServiceRouter(load_app_config()).search("x_recent_posts_search").search("robot VLA -is:retweet", limit=200)

    assert calls["url"] == "https://api.x.com/2/tweets/search/recent"
    assert calls["params"]["max_results"] == 100
    assert calls["headers"]["Authorization"] == "Bearer unit-x-token"
    assert results[0]["source_key"] == "x_recent_posts_search"
    assert results[0]["source_type"] == "social_platform_search"
    assert results[0]["url"] == "https://x.com/roboticist/status/1800000000000000000"
    assert results[0]["author_username"] == "roboticist"


def test_crustdata_signal_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).search("crustdata_signal_search")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "results": [
                    {
                        "source": "news",
                        "title": "Robot Labs raises Series B",
                        "url": "https://news.example/robot-labs",
                        "snippet": "Hiring robotics engineers after financing.",
                        "position": 1,
                    }
                ],
                "metadata": {"total_results": 1},
            }

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("CRUSTDATA_API_KEY", "unit-crustdata-token")
    monkeypatch.setattr(requests, "post", fake_post)

    results = ServiceRouter(load_app_config()).search("crustdata_signal_search").search("robotics hiring funding", limit=3)

    assert calls["url"] == "https://api.crustdata.com/web/search/live"
    assert calls["headers"]["Authorization"] == "Bearer unit-crustdata-token"
    assert calls["headers"]["x-api-version"] == "2025-11-01"
    assert calls["json"]["sources"] == ["web", "news", "social"]
    assert results[0]["source_key"] == "crustdata_signal_search"
    assert results[0]["source_type"] == "market_signal"
    assert results[0]["title"] == "Robot Labs raises Series B"


def test_email_discovery_and_verification_providers_are_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    router = ServiceRouter(load_app_config())
    with pytest.raises(KeyError):
        router.email_discovery("hunter_email_finder")
    with pytest.raises(KeyError):
        router.email_verification("zerobounce_email_validation")
    with pytest.raises(KeyError):
        router.email_verification("neverbounce_email_validation")
    return

    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, *, params: dict, timeout: int) -> Response:
        calls.append({"url": url, "params": params, "timeout": timeout})
        if "hunter.io" in url:
            return Response({"data": {"email": "ada@robot.example", "score": 97, "sources": []}})
        if "zerobounce" in url:
            return Response({"address": "ada@robot.example", "status": "valid", "sub_status": "", "mx_found": True})
        return Response({"status": "success", "result": "valid", "flags": ["has_dns_mx"]})

    import requests

    monkeypatch.setenv("HUNTER_API_KEY", "unit-hunter-key")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "unit-zb-key")
    monkeypatch.setenv("NEVERBOUNCE_API_KEY", "unit-nb-key")
    monkeypatch.setattr(requests, "get", fake_get)

    router = ServiceRouter(load_app_config())
    discovery = router.email_discovery("hunter_email_finder").find(
        full_name="Ada Lovelace",
        domain="robot.example",
    )
    zb = router.email_verification("zerobounce_email_validation").verify("ada@robot.example")
    nb = router.email_verification("neverbounce_email_validation").verify("ada@robot.example")

    assert discovery["email"] == "ada@robot.example"
    assert discovery["quality"] == "high_confidence"
    assert zb["status"] == "valid"
    assert zb["deliverable"] is True
    assert nb["result"] == "valid"
    assert nb["deliverable"] is True
    assert calls[0]["url"] == "https://api.hunter.io/v2/email-finder"
    assert calls[1]["url"] == "https://api.zerobounce.net/v2/validate"
    assert calls[2]["url"] == "https://api.neverbounce.com/v4.2/single/check"


def test_compliant_postmark_sender_requires_approval_and_writes_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).email_delivery("postmark_compliant_email")
    return

    calls: dict[str, object] = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"MessageID": "msg_1", "SubmittedAt": "2026-06-01T12:00:00Z"}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> Response:
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    import requests

    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "unit-postmark-token")
    monkeypatch.setenv("RECRUITING_CONTACT_EMAIL", "recruiting@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.com/unsubscribe")
    monkeypatch.setattr(requests, "post", fake_post)

    sender = ServiceRouter(load_app_config()).email_delivery("postmark_compliant_email")
    sender.suppression_list_path = str(tmp_path / "suppression.jsonl")
    sender.audit_log_path = str(tmp_path / "audit.jsonl")

    with pytest.raises(RuntimeError, match="approval"):
        sender.send(to="ada@robot.example", subject="Role", text_body="Hello", approved=False)

    result = sender.send(to="ada@robot.example", subject="Role", text_body="Hello", approved=True)

    assert calls["url"] == "https://api.postmarkapp.com/email"
    assert calls["headers"]["X-Postmark-Server-Token"] == "unit-postmark-token"
    assert calls["json"]["From"] == "recruiting@example.com"
    assert "unsubscribe" in calls["json"]["TextBody"]
    assert result["status"] == "sent"
    assert (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_mailtrap_email_provider_is_not_routable_from_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        ServiceRouter(load_app_config()).email_delivery("mailtrap_smtp_email")
    return

    calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls["host"] = host
            calls["port"] = port
            calls["timeout"] = timeout

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        def starttls(self) -> None:
            calls["starttls"] = True

        def login(self, username: str, password: str) -> None:
            calls["username"] = username
            calls["password"] = password

        def send_message(self, message) -> None:  # noqa: ANN001
            calls["message"] = message

    import smtplib

    monkeypatch.setenv("MAILTRAP_SMTP_HOST", "sandbox.smtp.mailtrap.io")
    monkeypatch.setenv("MAILTRAP_SMTP_PORT", "2525")
    monkeypatch.setenv("MAILTRAP_SMTP_USERNAME", "unit-mailtrap-user")
    monkeypatch.setenv("MAILTRAP_SMTP_PASSWORD", "unit-mailtrap-secret")
    monkeypatch.setenv("RECRUITING_CONTACT_EMAIL", "recruiting@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.com/unsubscribe")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    sender = ServiceRouter(load_app_config()).email_delivery("mailtrap_smtp_email")
    sender.suppression_list_path = str(tmp_path / "suppression.jsonl")
    sender.audit_log_path = str(tmp_path / "audit.jsonl")

    result = sender.send(
        to="ada@robot.example",
        subject="真机部署问题切磋",
        text_body="看到你做过 ROS2 nav2 真机调参。",
        approved=True,
    )

    assert result["status"] == "sent"
    assert result["provider"] == "mailtrap_smtp_email"
    assert calls["host"] == "sandbox.smtp.mailtrap.io"
    assert calls["port"] == 2525
    assert calls["starttls"] is True
    assert calls["username"] == "unit-mailtrap-user"
    assert calls["password"] == "unit-mailtrap-secret"
    message = calls["message"]
    assert message["To"] == "ada@robot.example"
    assert message["From"] == "recruiting@example.com"
    assert "List-Unsubscribe" in message
    assert "ROS2 nav2" in message.get_content()


def test_keyed_scraping_providers_are_not_routable_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    router = ServiceRouter(load_app_config())
    for service_name in {
        "firecrawl_scrape",
        "apify_actor_run",
        "brightdata_web_unlocker",
        "browserbase_session",
    }:
        with pytest.raises(KeyError):
            router.scraping(service_name)
    return

    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_post(url: str, *, headers: dict, json: dict | None = None, timeout: int) -> Response:
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if "firecrawl" in url:
            return Response({"success": True, "data": {"markdown": "# Page", "metadata": {"title": "Page"}}})
        if "brightdata" in url:
            return Response({"body": "<html>ok</html>", "status_code": 200})
        if "browserbase" in url:
            return Response({"id": "session_1", "connectUrl": "wss://browserbase.example"})
        return Response({"data": {"id": "run_1", "status": "READY", "defaultDatasetId": "dataset_1"}})

    import requests

    monkeypatch.setenv("FIRECRAWL_API_KEY", "unit-firecrawl-key")
    monkeypatch.setenv("APIFY_API_TOKEN", "unit-apify-token")
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "unit-brightdata-key")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "unit-zone")
    monkeypatch.setenv("BROWSERBASE_API_KEY", "unit-browserbase-key")
    monkeypatch.setenv("BROWSERBASE_PROJECT_ID", "unit-project")
    monkeypatch.setattr(requests, "post", fake_post)

    router = ServiceRouter(load_app_config())
    firecrawl = router.scraping("firecrawl_scrape").scrape("https://example.com")
    apify = router.scraping("apify_actor_run").run_actor("user~actor", {"url": "https://example.com"})
    brightdata = router.scraping("brightdata_web_unlocker").scrape("https://example.com")
    browserbase = router.scraping("browserbase_session").create_session()

    assert firecrawl["markdown"] == "# Page"
    assert apify["run_id"] == "run_1"
    assert brightdata["status_code"] == 200
    assert browserbase["session_id"] == "session_1"
    assert calls[0]["url"] == "https://api.firecrawl.dev/v2/scrape"
    assert calls[1]["url"] == "https://api.apify.com/v2/acts/user~actor/runs"
    assert calls[2]["url"] == "https://api.brightdata.com/request"
    assert calls[3]["url"] == "https://api.browserbase.com/v1/sessions"


def test_opencli_crawl_provider_runs_configured_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls["args"] = args
        calls["capture_output"] = capture_output
        calls["text"] = text
        calls["timeout"] = timeout
        calls["check"] = check
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "markdown": "# Team\nAda Lovelace",
                    "metadata": {"title": "Team"},
                    "url": "https://example.com/team",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = ServiceRouter(load_app_config()).scraping("opencli_crawl_scrape").scrape(
        "https://example.com/team",
        formats=["markdown"],
    )

    assert calls["args"] == ["opencli", "web", "read", "--url", "https://example.com/team", "-f", "json"]
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert calls["check"] is True
    assert result["provider"] == "opencli_crawl"
    assert result["url"] == "https://example.com/team"
    assert result["markdown"] == "# Team\nAda Lovelace"
    assert result["metadata"] == {"title": "Team"}
    assert result["raw"]["url"] == "https://example.com/team"


def test_opencli_crawl_provider_reads_saved_markdown_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    saved_path = tmp_path / "web-articles" / "Example_Domain" / "Example_Domain.md"
    saved_path.parent.mkdir(parents=True)
    saved_path.write_text("# Example Domain\n\nThis domain is for examples.", encoding="utf-8")
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "title": "Example Domain",
                        "author": "-",
                        "publish_time": "-",
                        "status": "success",
                        "size": "226.0 B",
                        "saved": "web-articles/Example_Domain/Example_Domain.md",
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = ServiceRouter(load_app_config(Path(__file__).resolve().parents[1] / "config" / "services.toml")).scraping(
        "opencli_crawl_scrape"
    ).scrape(
        "https://example.com",
        formats=["markdown"],
    )

    assert result["provider"] == "opencli_crawl"
    assert result["url"] == "https://example.com"
    assert result["markdown"] == "# Example Domain\n\nThis domain is for examples."
    assert result["metadata"]["title"] == "Example Domain"
    assert result["metadata"]["saved"] == "web-articles/Example_Domain/Example_Domain.md"
    assert result["raw"][0]["saved"] == "web-articles/Example_Domain/Example_Domain.md"


def test_opencli_platform_search_provider_runs_configured_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert capture_output is True
        assert text is True
        assert check is False
        if args == ["opencli", "doctor"]:
            assert timeout == 10
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="[OK] Connectivity: ready", stderr="")
        assert timeout == 60
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "data": [
                        {
                            "title": "Robotics Diffusion Policy Demo",
                            "url": "https://www.bilibili.com/video/BV1robot",
                            "description": "A public robot manipulation demo.",
                            "created_at": "2026-06-01",
                        }
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = ServiceRouter(load_app_config()).search("opencli_platform_search").search(
        "robotics diffusion policy",
        limit=2,
    )

    assert calls[0] == ["opencli", "doctor"]
    assert calls[1] == ["opencli", "bilibili", "search", "robotics diffusion policy", "--limit", "2", "-f", "json"]
    assert ["opencli", "twitter", "search", "robotics diffusion policy", "--limit", "2", "-f", "json"] in calls
    assert ["opencli", "reddit", "search", "robotics diffusion policy", "--limit", "2", "-f", "json"] in calls
    assert ["opencli", "weixin", "search", "robotics diffusion policy", "--limit", "2", "-f", "json"] in calls
    assert results[0]["source_key"] == "opencli_platform_search"
    assert results[0]["name_zh"] == "OpenCLI 平台搜索"
    assert results[0]["source_type"] == "browser_platform_search"
    assert results[0]["platform"] == "bilibili"
    assert results[0]["title"] == "Robotics Diffusion Policy Demo"
    assert results[0]["url"] == "https://www.bilibili.com/video/BV1robot"
    assert results[0]["snippet"] == "A public robot manipulation demo."
    assert results[0]["retrieval_status"] == "retrieved"


def test_opencli_platform_search_skips_commands_when_browser_bridge_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert capture_output is True
        assert text is True
        assert timeout == 10
        assert check is False
        assert args == ["opencli", "doctor"]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="[MISSING] Extension: not connected\n[FAIL] Connectivity: failed (Browser Bridge extension not connected)",
            stderr="",
        )

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = ServiceRouter(load_app_config()).search("opencli_platform_search").search(
        "robotics diffusion policy",
        limit=2,
    )

    assert calls == [["opencli", "doctor"]]
    assert results == [
        {
            "source_key": "opencli_platform_search",
            "name_zh": "OpenCLI 平台搜索",
            "source_type": "browser_platform_search",
            "query": "robotics diffusion policy",
            "rank": 1,
            "platform": "bilibili",
            "platform_name_zh": "B站",
            "title": "B站 manual_setup",
            "url": "https://github.com/jackwener/OpenCLI",
            "snippet": "OpenCLI Browser Bridge: Browser Bridge extension not connected",
            "published_at": None,
            "retrieval_status": "manual_setup",
            "error": "OpenCLI Browser Bridge: Browser Bridge extension not connected",
            "risk_level": "high",
            "freshness": "daily",
        }
    ]


def test_opencli_web_read_search_requires_absolute_url_without_launching(monkeypatch: pytest.MonkeyPatch) -> None:
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fail_run(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("OpenCLI web read search should not launch without an absolute URL")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fail_run)

    results = ServiceRouter(load_app_config()).search("opencli_web_read_search").search(
        "robotics official team page",
        limit=1,
    )

    assert results == [
        {
            "source_key": "opencli_web_read_search",
            "name_zh": "OpenCLI 网页正文读取",
            "source_type": "adaptive_web_scraping",
            "query": "robotics official team page",
            "rank": 1,
            "platform": "web_read",
            "platform_name_zh": "网页正文",
            "title": "网页正文 requires_url",
            "url": "https://github.com/jackwener/OpenCLI",
            "snippet": "OpenCLI web read requires an absolute http(s) URL.",
            "published_at": None,
            "retrieval_status": "requires_url",
            "error": "OpenCLI web read requires an absolute http(s) URL.",
            "risk_level": "high",
            "freshness": "on_demand",
        }
    ]


def test_opencli_web_read_search_uses_saved_markdown_as_snippet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    saved_path = tmp_path / "web-articles" / "Example_Domain" / "Example_Domain.md"
    saved_path.parent.mkdir(parents=True)
    saved_path.write_text("# Example Domain\n\nThis domain is for examples.", encoding="utf-8")
    calls: list[list[str]] = []
    original_which = shutil.which

    def fake_which(command: str) -> str | None:
        return f"/usr/bin/{command}" if command == "opencli" else original_which(command)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["opencli", "doctor"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="[OK] Connectivity: ready", stderr="")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "title": "Example Domain",
                        "author": "-",
                        "publish_time": "-",
                        "status": "success",
                        "size": "226.0 B",
                        "saved": "web-articles/Example_Domain/Example_Domain.md",
                    }
                ]
            ),
            stderr="",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    results = ServiceRouter(load_app_config(Path(__file__).resolve().parents[1] / "config" / "services.toml")).search(
        "opencli_web_read_search"
    ).search(
        "https://example.com",
        limit=1,
    )

    assert calls == [
        ["opencli", "doctor"],
        ["opencli", "web", "read", "--url", "https://example.com", "-f", "json"],
    ]
    assert results[0]["source_key"] == "opencli_web_read_search"
    assert results[0]["title"] == "Example Domain"
    assert results[0]["snippet"] == "# Example Domain\n\nThis domain is for examples."
    assert results[0]["raw"]["saved"] == "web-articles/Example_Domain/Example_Domain.md"


def test_education_competition_monitor_returns_curated_targets() -> None:
    results = ServiceRouter(load_app_config()).search("education_competition_monitor").search("机器人 天池 高校 实验室", limit=5)

    assert results
    assert results[0]["source_key"] == "education_competition_monitor"
    assert results[0]["source_type"] in {"university_lab", "competition"}
    assert results[0]["url"].startswith("https://")
    assert results[0]["retrieval_status"] == "monitor_target"
    assert "snapshot_recommended" in results[0]["next_actions"]


def test_public_web_snapshot_monitor_writes_snapshot(tmp_path: Path) -> None:
    class FakeScrapeProvider:
        def scrape(self, url: str, *, formats: list[str] | None = None) -> dict:
            return {
                "provider": "fake_scrape",
                "url": url,
                "markdown": f"# Snapshot\n{url}",
                "html": None,
                "metadata": {"title": "Snapshot"},
                "raw": {"ok": True},
            }

    class FakeBrowserbaseProvider:
        def create_session(self, **options: object) -> dict:
            return {"provider": "browserbase_session", "session_id": "session_1", "raw": options}

    from app.providers.scraping import PublicWebSnapshotMonitorProvider

    monitor = PublicWebSnapshotMonitorProvider(
        snapshot_dir=str(tmp_path),
        primary_scrape_provider=FakeScrapeProvider(),
        browser_session_provider=FakeBrowserbaseProvider(),
        target_groups={"schools": ["https://example.com/lab"]},
    )

    result = monitor.snapshot(
        urls=["https://example.com/lab"],
        job_name="unit-schools",
        use_browserbase=True,
    )

    assert result["provider"] == "public_web_snapshot_monitor"
    assert result["job_name"] == "unit-schools"
    assert result["browserbase_session"]["session_id"] == "session_1"
    assert result["items"][0]["status"] == "saved"
    assert Path(result["items"][0]["markdown_path"]).exists()
    assert Path(result["manifest_path"]).exists()
    assert "https://example.com/lab" in Path(result["manifest_path"]).read_text(encoding="utf-8")


def test_config_rejects_vector_size_mismatch(tmp_path: Path) -> None:
    config = tmp_path / "services.toml"
    config.write_text(
        """
[defaults]
embedding = "emb"
vector_store = "store"

[services.emb]
type = "embedding"
provider = "sentence_transformers"
model_name = "BAAI/bge-m3"
vector_size = 1024

[services.store]
type = "vector_store"
provider = "qdrant_local"
path = "./qdrant_mvp_store"
collection_name = "robot_talents"
distance = "cosine"
embedding_service = "emb"
vector_size = 768
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="vector_size"):
        load_app_config(config)
