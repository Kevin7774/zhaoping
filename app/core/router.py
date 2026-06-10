from __future__ import annotations

from functools import cached_property
from typing import Any

from app.core.config import AppConfig, ServiceConfig, load_app_config
from app.core.mcp_registry import MCPRegistry
from app.providers.database import PostgresDatabaseProvider
from app.providers.common import DisabledProvider
from app.providers.document import AutoDocumentParser, DoclingDocumentParser, PlainTextDocumentParser
from app.providers.embedding import SentenceTransformerEmbeddingProvider
from app.providers.evaluation import SelfRSIEvaluator
from app.providers.llm import AnthropicCompatibleLLMProvider, OpenRouterChatLLMProvider
from app.providers.ocr import AliyunOCRProvider, DoclingOCRProvider
from app.providers.scraping import OpenCLICrawlProvider
from app.providers.search import (
    AgentReachSocialSearchProvider,
    BraveWebSearchProvider,
    CFPBConsumerComplaintProvider,
    CMSOpenPaymentsSearchProvider,
    ClinicalTrialsStudySearchProvider,
    CPSCRecallSearchProvider,
    DueDiligenceFederatedSearchProvider,
    EPAEchoFacilityComplianceProvider,
    ExternalSearchToolProvider,
    FDICBankFindInstitutionProvider,
    FDADevice510kClearanceProvider,
    FDADeviceAdverseEventProvider,
    FDADeviceClassificationProvider,
    FDADeviceRegistrationListingProvider,
    FDAEnforcementRecallProvider,
    FederalRegisterDocumentSearchProvider,
    GDELTDocNewsSearchProvider,
    GNewsFundingNewsProvider,
    GrantsGovOpportunitySearchProvider,
    GitHubCandidateSearchProvider,
    GitHubCodeSearchProvider,
    GitHubRepositorySearchProvider,
    GitHubTopicSearchProvider,
    GitHubUserSearchProvider,
    HuggingFaceModelSearchProvider,
    NHTSARecallSearchProvider,
    OFACSanctionsListSearchProvider,
    OpenAlexAuthorsSearchProvider,
    OpenCLICommandSearchProvider,
    OpenAlexInstitutionsSearchProvider,
    OpenAlexWorksSearchProvider,
    PatentsViewPatentSearchProvider,
    EducationCompetitionMonitorProvider,
    SECEdgarCompanyFilingsProvider,
    SECEnforcementSearchProvider,
    SECCompanyFactsProvider,
    SECInsiderTransactionsProvider,
    SECInvestmentAdviserReportProvider,
    SECOwnershipActivismProvider,
    SearchSourceCatalogProvider,
    SemanticScholarAuthorSearchProvider,
    SemanticScholarPaperSearchProvider,
    USASpendingAwardSearchProvider,
)
from app.providers.structured_output import OutlinesStructuredOutputProvider
from app.providers.vector_store import QdrantLocalVectorStore
from app.core.skill_registry import SkillRegistry


class ServiceRouter:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_app_config()
        self._instances: dict[str, Any] = {}

    def resolve(self, service_type: str, service_name: str | None = None):
        name = service_name or self.config.default_service_name(service_type)
        service = self.config.service(name)
        if service.type != service_type:
            raise ValueError(f"Service '{name}' is type '{service.type}', not requested type '{service_type}'.")
        if name not in self._instances:
            self._instances[name] = self._build(service)
        return self._instances[name]

    def document_parser(self, service_name: str | None = None):
        return self.resolve("document_parser", service_name)

    def embedding(self, service_name: str | None = None):
        return self.resolve("embedding", service_name)

    def evaluation(self, service_name: str | None = None):
        return self.resolve("evaluation", service_name)

    def vector_store(self, service_name: str | None = None):
        return self.resolve("vector_store", service_name)

    def search(self, service_name: str | None = None):
        return self.resolve("search", service_name)

    def ocr(self, service_name: str | None = None):
        return self.resolve("ocr", service_name)

    def mcp(self, service_name: str | None = None):
        return self.resolve("mcp", service_name)

    def structured_output(self, service_name: str | None = None):
        return self.resolve("structured_output", service_name)

    def database(self, service_name: str | None = None):
        return self.resolve("database", service_name)

    def llm(self, service_name: str | None = None):
        return self.resolve("llm", service_name)

    def email_discovery(self, service_name: str | None = None):
        return self.resolve("email_discovery", service_name)

    def email_verification(self, service_name: str | None = None):
        return self.resolve("email_verification", service_name)

    def email_delivery(self, service_name: str | None = None):
        return self.resolve("email_delivery", service_name)

    def scraping(self, service_name: str | None = None):
        return self.resolve("scraping", service_name)

    @cached_property
    def skills(self) -> dict[str, Any]:
        return self.skill_registry.all()

    @cached_property
    def skill_registry(self) -> SkillRegistry:
        return SkillRegistry(self.config)

    @cached_property
    def mcp_registry(self) -> MCPRegistry:
        return MCPRegistry(self.config)

    def _build(self, service: ServiceConfig):
        provider = service.provider
        settings = dict(service.model_extra or {})

        if service.type == "document_parser":
            if provider == "auto":
                return AutoDocumentParser()
            if provider == "plain_text":
                return PlainTextDocumentParser()
            if provider == "docling":
                return DoclingDocumentParser()

        if service.type == "embedding" and provider == "sentence_transformers":
            return SentenceTransformerEmbeddingProvider(
                model_name=str(settings["model_name"]),
                vector_size=int(settings["vector_size"]),
                device=str(settings.get("device", "auto")),
                batch_size=int(settings.get("batch_size", 8)),
                show_progress_bar=bool(settings.get("show_progress_bar", True)),
            )

        if service.type == "evaluation" and provider == "self_rsi":
            return SelfRSIEvaluator(
                suite_id=str(settings["suite_id"]),
                baseline_threshold=float(settings.get("baseline_threshold", 0.8)),
            )

        if service.type == "vector_store" and provider == "qdrant_local":
            return QdrantLocalVectorStore(
                path=str(settings["path"]),
                collection_name=str(settings["collection_name"]),
                vector_size=int(settings["vector_size"]),
                distance=str(settings.get("distance", "cosine")),
            )

        if service.type == "ocr" and provider == "docling":
            return DoclingOCRProvider()

        if service.type == "ocr" and provider == "aliyun_ocr":
            return AliyunOCRProvider(
                access_key_id_env=str(settings["access_key_id_env"]),
                access_key_secret_env=str(settings["access_key_secret_env"]),
                region_id=str(settings["region_id"]),
                endpoint=str(settings["endpoint"]),
            )

        if service.type == "structured_output" and provider == "outlines":
            return OutlinesStructuredOutputProvider(model_service=str(settings["model_service"]))

        if service.type == "search" and provider == "source_catalog":
            skill_name = str(settings["skill_name"])
            return SearchSourceCatalogProvider(self.skill_registry.get(skill_name))

        if service.type == "search" and provider == "agent_reach_social":
            return AgentReachSocialSearchProvider(
                service_name=service.name,
                platform_commands={
                    str(platform): dict(platform_settings)
                    for platform, platform_settings in settings.get("platform_commands", {}).items()
                },
                supported_platforms=[str(item) for item in settings.get("supported_platforms", [])],
                required_commands=[str(item) for item in settings.get("required_commands", [])],
                project_url=str(settings.get("project_url", "https://github.com/Panniantong/Agent-Reach")),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
                risk_level=str(settings.get("risk_level", "high")),
                freshness=str(settings.get("freshness", "daily")),
            )

        if service.type == "search" and provider == "opencli_command":
            return OpenCLICommandSearchProvider(
                service_name=service.name,
                display_name_zh=str(settings["display_name_zh"]),
                source_type=str(settings["source_type"]),
                platform_commands={
                    str(platform): dict(platform_settings)
                    for platform, platform_settings in settings.get("platform_commands", {}).items()
                },
                required_command=str(settings.get("required_command", "opencli")),
                supported_platforms=[str(item) for item in settings.get("supported_platforms", [])],
                project_url=str(settings.get("project_url", "https://github.com/jackwener/OpenCLI")),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
                risk_level=str(settings.get("risk_level", "high")),
                freshness=str(settings.get("freshness", "daily")),
                requires_absolute_url=bool(settings.get("requires_absolute_url", False)),
                requires_browser_bridge=bool(settings.get("requires_browser_bridge", False)),
            )

        if service.type == "search" and provider == "external_search_tool":
            return ExternalSearchToolProvider(
                service_name=service.name,
                tool_name=str(settings["tool_name"]),
                source_key=str(settings["source_key"]),
                name_zh=str(settings["display_name_zh"]),
                source_type=str(settings["source_type"]),
                project_url=str(settings["project_url"]),
                purpose=str(settings["purpose"]),
                access_pattern=str(settings["access_pattern"]),
                risk_level=str(settings["risk_level"]),
                freshness=str(settings["freshness"]),
                supported_platforms=[str(item) for item in settings.get("supported_platforms", [])],
                install_hint=str(settings["install_hint"]) if "install_hint" in settings else None,
                setup_steps=[str(item) for item in settings.get("setup_steps", [])],
                guardrails=[str(item) for item in settings.get("guardrails", [])],
                required_command=str(settings["required_command"]) if "required_command" in settings else None,
                required_python_module=str(settings["required_python_module"]) if "required_python_module" in settings else None,
                required_skill_path=str(settings["required_skill_path"]) if "required_skill_path" in settings else None,
                command_args=[str(item) for item in settings.get("command_args", [])],
                execute_enabled=bool(settings.get("execute_enabled", False)),
                manual_setup_required=bool(settings.get("manual_setup_required", True)),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
            )

        if service.type == "search" and provider == "brave_web":
            return BraveWebSearchProvider(
                api_key_env=str(settings["api_key_env"]),
                endpoint=str(settings["endpoint"]),
                country=str(settings.get("country", "US")),
                search_lang=str(settings.get("search_lang", "en")),
                ui_lang=str(settings.get("ui_lang", "en-US")),
                safesearch=str(settings.get("safesearch", "moderate")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "github_repositories":
            return GitHubRepositorySearchProvider(
                endpoint=str(settings["endpoint"]),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "github_users":
            return GitHubUserSearchProvider(
                endpoint=str(settings["endpoint"]),
                user_endpoint_template=str(settings.get("user_endpoint_template", "https://api.github.com/users/{login}")),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "github_code":
            return GitHubCodeSearchProvider(
                endpoint=str(settings["endpoint"]),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "github_topics":
            return GitHubTopicSearchProvider(
                endpoint=str(settings["endpoint"]),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "github_candidates":
            return GitHubCandidateSearchProvider(
                users_endpoint=str(settings["users_endpoint"]),
                repositories_endpoint=str(settings["repositories_endpoint"]),
                code_endpoint=str(settings["code_endpoint"]),
                user_endpoint_template=str(settings.get("user_endpoint_template", "https://api.github.com/users/{login}")),
                user_repos_endpoint_template=str(settings.get("user_repos_endpoint_template", "https://api.github.com/users/{login}/repos")),
                rate_limit_endpoint=str(settings.get("rate_limit_endpoint", "https://api.github.com/rate_limit")),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
                enrichment_repo_limit=int(settings.get("enrichment_repo_limit", 8)),
            )

        if service.type == "search" and provider == "huggingface_models":
            return HuggingFaceModelSearchProvider(
                endpoint=str(settings["endpoint"]),
                token_env=str(settings["token_env"]) if "token_env" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "openalex_works":
            return OpenAlexWorksSearchProvider(
                endpoint=str(settings["endpoint"]),
                mailto=str(settings["mailto"]) if "mailto" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "openalex_authors":
            return OpenAlexAuthorsSearchProvider(
                endpoint=str(settings["endpoint"]),
                mailto=str(settings["mailto"]) if "mailto" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "openalex_institutions":
            return OpenAlexInstitutionsSearchProvider(
                endpoint=str(settings["endpoint"]),
                mailto=str(settings["mailto"]) if "mailto" in settings else None,
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "semantic_scholar_papers":
            return SemanticScholarPaperSearchProvider(
                endpoint=str(settings["endpoint"]),
                fields=str(settings["fields"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "semantic_scholar_authors":
            return SemanticScholarAuthorSearchProvider(
                endpoint=str(settings["endpoint"]),
                fields=str(settings["fields"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "education_competition_monitor":
            return EducationCompetitionMonitorProvider(
                targets=[dict(target) for target in settings.get("targets", [])],
            )

        if service.type == "search" and provider == "sec_edgar_company_filings":
            return SECEdgarCompanyFilingsProvider(
                company_tickers_url=str(settings["company_tickers_url"]),
                submissions_url_template=str(settings["submissions_url_template"]),
                archives_url_template=str(settings["archives_url_template"]),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "sec_insider_transactions":
            return SECInsiderTransactionsProvider(
                company_tickers_url=str(settings["company_tickers_url"]),
                submissions_url_template=str(settings["submissions_url_template"]),
                archives_url_template=str(settings["archives_url_template"]),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "sec_ownership_activism":
            return SECOwnershipActivismProvider(
                company_tickers_url=str(settings["company_tickers_url"]),
                submissions_url_template=str(settings["submissions_url_template"]),
                archives_url_template=str(settings["archives_url_template"]),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "sec_company_facts":
            return SECCompanyFactsProvider(
                company_tickers_url=str(settings["company_tickers_url"]),
                companyfacts_url_template=str(settings["companyfacts_url_template"]),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "sec_investment_adviser_reports":
            return SECInvestmentAdviserReportProvider(
                report_url=str(settings["report_url"]),
                landing_page_url=str(settings.get("landing_page_url", "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers")),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 30)),
            )

        if service.type == "search" and provider == "fdic_bankfind_institutions":
            return FDICBankFindInstitutionProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "federal_register_documents":
            return FederalRegisterDocumentSearchProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "cpsc_recalls":
            return CPSCRecallSearchProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "fda_enforcement_recalls":
            return FDAEnforcementRecallProvider(
                endpoints={str(key): str(value) for key, value in settings["endpoints"].items()},
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "fda_device_510k":
            return FDADevice510kClearanceProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "fda_device_events":
            return FDADeviceAdverseEventProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "fda_device_classification":
            return FDADeviceClassificationProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "fda_device_registration_listing":
            return FDADeviceRegistrationListingProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "cfpb_consumer_complaints":
            return CFPBConsumerComplaintProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "nhtsa_recalls":
            return NHTSARecallSearchProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "epa_echo_facilities":
            return EPAEchoFacilityComplianceProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "clinicaltrials_studies":
            return ClinicalTrialsStudySearchProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "cms_openpayments":
            return CMSOpenPaymentsSearchProvider(
                metastore_endpoint=str(settings["metastore_endpoint"]),
                datastore_endpoint_template=str(settings["datastore_endpoint_template"]),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
                dataset_limit=int(settings.get("dataset_limit", 100)),
            )

        if service.type == "search" and provider == "gdelt_doc_news":
            return GDELTDocNewsSearchProvider(
                endpoint=str(settings["endpoint"]),
                timespan=str(settings.get("timespan", "7d")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "gnews_funding_news":
            return GNewsFundingNewsProvider(
                endpoint=str(settings["endpoint"]),
                api_key_env=str(settings["api_key_env"]),
                lang=str(settings.get("lang", "en")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "sec_enforcement":
            return SECEnforcementSearchProvider(
                endpoint=str(settings["endpoint"]),
                user_agent=str(settings.get("user_agent", "zhaoping-agent/0.1 research contact@example.invalid")),
                timeout_seconds=int(settings.get("timeout_seconds", 20)),
            )

        if service.type == "search" and provider == "usaspending_awards":
            return USASpendingAwardSearchProvider(
                endpoint=str(settings["endpoint"]),
                fiscal_years=[int(year) for year in settings.get("fiscal_years", [])],
                timeout_seconds=int(settings.get("timeout_seconds", 30)),
            )

        if service.type == "search" and provider == "grants_gov_opportunities":
            return GrantsGovOpportunitySearchProvider(
                endpoint=str(settings["endpoint"]),
                opportunity_statuses=str(settings.get("opportunity_statuses", "forecasted|posted")),
                timeout_seconds=int(settings.get("timeout_seconds", 30)),
            )

        if service.type == "search" and provider == "patentsview_patents":
            return PatentsViewPatentSearchProvider(
                endpoint=str(settings["endpoint"]),
                timeout_seconds=int(settings.get("timeout_seconds", 30)),
            )

        if service.type == "search" and provider == "ofac_sanctions_lists":
            return OFACSanctionsListSearchProvider(
                sdn_xml_url=str(settings["sdn_xml_url"]),
                consolidated_xml_url=str(settings["consolidated_xml_url"]),
                timeout_seconds=int(settings.get("timeout_seconds", 30)),
            )

        if service.type == "search" and provider == "due_diligence_federated":
            source_catalog = self.search(str(settings["source_catalog_service"]))
            web_search_name = settings.get("web_search_service")
            web_search = self.search(str(web_search_name)) if web_search_name else None
            live_searches = [
                self.search(str(service_name))
                for service_name in settings.get("live_search_services", [])
            ]
            return DueDiligenceFederatedSearchProvider(
                source_catalog=source_catalog,
                web_search=web_search,
                live_searches=live_searches,
                web_enabled_by_default=bool(settings.get("web_enabled_by_default", False)),
                live_enabled_by_default=bool(settings.get("live_enabled_by_default", False)),
            )

        if service.type == "llm" and provider == "anthropic_compatible":
            return AnthropicCompatibleLLMProvider(
                base_url=str(settings["base_url"]),
                api_key_env=str(settings["api_key_env"]),
                model=str(settings["model"]),
                anthropic_version=str(settings["anthropic_version"]),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
            )

        if service.type == "llm" and provider == "openrouter_chat":
            return OpenRouterChatLLMProvider(
                base_url=str(settings["base_url"]),
                api_key_env=str(settings["api_key_env"]),
                model=str(settings["model"]),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
                app_referer=str(settings["app_referer"]) if "app_referer" in settings else None,
                app_title=str(settings["app_title"]) if "app_title" in settings else None,
                models=[str(model) for model in settings.get("models", [])],
                plugins=list(settings.get("plugins", [])),
                tools=list(settings.get("tools", [])),
            )

        if service.type == "database" and provider == "postgres":
            import os

            env_name = str(settings["database_url_env"])
            database_url = os.environ.get(env_name)
            if not database_url:
                raise RuntimeError(f"Missing required environment variable: {env_name}")
            return PostgresDatabaseProvider(database_url)

        if service.type == "scraping" and provider == "opencli_crawl":
            return OpenCLICrawlProvider(
                command=str(settings.get("required_command", "opencli")),
                command_args=[str(item) for item in settings.get("command_args", [])],
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
            )

        if provider == "disabled":
            return DisabledProvider(service.type, service.name)

        raise ValueError(f"Unsupported provider '{provider}' for service '{service.name}' ({service.type}).")


def get_router(config_path: str | None = None) -> ServiceRouter:
    return ServiceRouter(load_app_config(config_path) if config_path else None)
