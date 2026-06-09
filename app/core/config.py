from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path("config/services.toml")
CONFIG_PATH_ENV = "ROBOT_AGENT_CONFIG"
ENV_PATH_ENV = "ROBOT_AGENT_ENV_PATH"

ServiceType = Literal[
    "database",
    "document_parser",
    "embedding",
    "email_delivery",
    "email_discovery",
    "email_verification",
    "evaluation",
    "llm",
    "mcp",
    "ocr",
    "scraping",
    "search",
    "structured_output",
    "vector_store",
]


class ServiceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: ServiceType
    provider: str
    description: str | None = None


class SkillConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    module: str
    entrypoint: str
    description: str | None = None


class AppConfig(BaseModel):
    defaults: dict[str, str] = Field(default_factory=dict)
    services: dict[str, ServiceConfig] = Field(default_factory=dict)
    skills: dict[str, SkillConfig] = Field(default_factory=dict)
    path: Path

    def default_service_name(self, service_type: str) -> str:
        try:
            return self.defaults[service_type]
        except KeyError as exc:
            raise KeyError(f"No default service configured for type: {service_type}") from exc

    def service(self, name: str) -> ServiceConfig:
        try:
            return self.services[name]
        except KeyError as exc:
            raise KeyError(f"Unknown service configured: {name}") from exc

    @model_validator(mode="after")
    def validate_references(self) -> "AppConfig":
        for service_type, service_name in self.defaults.items():
            service = self.services.get(service_name)
            if service is None:
                raise ValueError(f"Default '{service_type}' references unknown service '{service_name}'.")
            if service.type != service_type:
                raise ValueError(
                    f"Default '{service_type}' references service '{service_name}' with type '{service.type}'."
                )

        for service in self.services.values():
            self._validate_service_required_fields(service)
            self._validate_service_references(service)
        return self

    def _validate_service_required_fields(self, service: ServiceConfig) -> None:
        data = service.model_extra or {}
        required_by_provider = {
            ("embedding", "sentence_transformers"): ("model_name", "vector_size"),
            ("evaluation", "self_rsi"): ("suite_id", "baseline_threshold"),
            ("vector_store", "qdrant_local"): ("path", "collection_name", "distance", "embedding_service", "vector_size"),
            ("structured_output", "outlines"): ("model_service",),
            ("database", "postgres"): ("database_url_env",),
            ("llm", "anthropic_compatible"): ("base_url", "api_key_env", "model", "anthropic_version"),
            ("llm", "openrouter_chat"): ("base_url", "api_key_env", "model"),
            ("ocr", "aliyun_ocr"): ("access_key_id_env", "access_key_secret_env", "region_id", "endpoint"),
            ("search", "source_catalog"): ("skill_name",),
            ("search", "agent_reach_social"): ("platform_commands", "supported_platforms", "required_commands"),
            ("search", "brave_web"): ("api_key_env", "endpoint"),
            ("search", "people_data_labs_people"): ("api_key_env", "endpoint"),
            ("search", "x_recent_posts"): ("bearer_token_env", "endpoint"),
            ("search", "crustdata_signals"): ("api_key_env", "endpoint", "api_version"),
            ("search", "github_repositories"): ("endpoint",),
            ("search", "huggingface_models"): ("endpoint",),
            ("search", "companies_house"): ("endpoint", "api_key_env"),
            ("search", "courtlistener"): ("endpoint",),
            ("search", "openalex_works"): ("endpoint",),
            ("search", "openalex_authors"): ("endpoint",),
            ("search", "openalex_institutions"): ("endpoint",),
            ("search", "semantic_scholar_papers"): ("endpoint", "fields"),
            ("search", "semantic_scholar_authors"): ("endpoint", "fields"),
            ("search", "education_competition_monitor"): ("targets",),
            ("search", "sec_edgar_company_filings"): (
                "company_tickers_url",
                "submissions_url_template",
                "archives_url_template",
            ),
            ("search", "sec_insider_transactions"): (
                "company_tickers_url",
                "submissions_url_template",
                "archives_url_template",
            ),
            ("search", "sec_ownership_activism"): (
                "company_tickers_url",
                "submissions_url_template",
                "archives_url_template",
            ),
            ("search", "sec_company_facts"): ("company_tickers_url", "companyfacts_url_template"),
            ("search", "sec_investment_adviser_reports"): ("report_url",),
            ("search", "fdic_bankfind_institutions"): ("endpoint",),
            ("search", "federal_register_documents"): ("endpoint",),
            ("search", "cpsc_recalls"): ("endpoint",),
            ("search", "fda_enforcement_recalls"): ("endpoints",),
            ("search", "fda_device_510k"): ("endpoint",),
            ("search", "fda_device_events"): ("endpoint",),
            ("search", "fda_device_classification"): ("endpoint",),
            ("search", "fda_device_registration_listing"): ("endpoint",),
            ("search", "cfpb_consumer_complaints"): ("endpoint",),
            ("search", "nhtsa_recalls"): ("endpoint",),
            ("search", "epa_echo_facilities"): ("endpoint",),
            ("search", "clinicaltrials_studies"): ("endpoint",),
            ("search", "cms_openpayments"): ("metastore_endpoint", "datastore_endpoint_template"),
            ("search", "census_international_trade"): ("imports_endpoint", "exports_endpoint"),
            ("search", "fred_series_search"): ("search_endpoint", "observations_endpoint", "api_key_env"),
            ("search", "gdelt_doc_news"): ("endpoint",),
            ("search", "gnews_funding_news"): ("endpoint", "api_key_env"),
            ("search", "sec_enforcement"): ("endpoint",),
            ("search", "usajobs"): ("endpoint", "api_key_env", "user_agent_env"),
            ("search", "usaspending_awards"): ("endpoint",),
            ("search", "sam_gov_opportunities"): ("endpoint", "api_key_env"),
            ("search", "grants_gov_opportunities"): ("endpoint",),
            ("search", "patentsview_patents"): ("endpoint",),
            ("search", "ofac_sanctions_lists"): ("sdn_xml_url", "consolidated_xml_url"),
            ("search", "due_diligence_federated"): ("source_catalog_service",),
            ("search", "external_search_tool"): (
                "tool_name",
                "source_key",
                "display_name_zh",
                "source_type",
                "project_url",
                "purpose",
                "access_pattern",
                "risk_level",
                "freshness",
            ),
            ("email_discovery", "hunter_email_finder"): ("endpoint", "api_key_env"),
            ("email_verification", "zerobounce_email_validation"): ("endpoint", "api_key_env"),
            ("email_verification", "neverbounce_email_validation"): ("endpoint", "api_key_env"),
            ("email_delivery", "postmark_compliant_email"): (
                "endpoint",
                "server_token_env",
                "from_email_env",
                "unsubscribe_base_url_env",
                "suppression_list_path",
                "audit_log_path",
                "daily_send_limit",
            ),
            ("email_delivery", "sendgrid_compliant_email"): (
                "endpoint",
                "api_key_env",
                "from_email_env",
                "unsubscribe_base_url_env",
                "suppression_list_path",
                "audit_log_path",
                "daily_send_limit",
            ),
            ("scraping", "firecrawl_scrape"): ("endpoint", "api_key_env"),
            ("scraping", "apify_actor_run"): ("endpoint_template", "api_token_env"),
            ("scraping", "brightdata_web_unlocker"): ("endpoint", "api_key_env", "zone_env"),
            ("scraping", "browserbase_session"): ("endpoint", "api_key_env", "project_id_env"),
            ("scraping", "opencli_crawl"): ("required_command", "command_args"),
            ("scraping", "public_web_snapshot_monitor"): (
                "primary_scraping_service",
                "browser_session_service",
                "snapshot_dir",
                "target_groups",
            ),
        }
        for field_name in required_by_provider.get((service.type, service.provider), ()):
            if field_name not in data:
                raise ValueError(f"Service '{service.name}' missing required field '{field_name}'.")

    def _validate_service_references(self, service: ServiceConfig) -> None:
        data = service.model_extra or {}
        if service.type == "vector_store" and service.provider == "qdrant_local":
            embedding_name = str(data["embedding_service"])
            embedding = self.services.get(embedding_name)
            if embedding is None:
                raise ValueError(f"Vector store '{service.name}' references unknown embedding '{embedding_name}'.")
            if embedding.type != "embedding":
                raise ValueError(f"Vector store '{service.name}' embedding_service must point to an embedding service.")
            vector_size = int(data["vector_size"])
            embedding_size = int((embedding.model_extra or {})["vector_size"])
            if vector_size != embedding_size:
                raise ValueError(
                    f"Vector store '{service.name}' vector_size={vector_size} does not match "
                    f"embedding '{embedding_name}' vector_size={embedding_size}."
                )

        if service.type == "structured_output" and service.provider == "outlines":
            model_name = str(data["model_service"])
            model = self.services.get(model_name)
            if model is None:
                raise ValueError(f"Structured output '{service.name}' references unknown model service '{model_name}'.")
            if model.type != "llm":
                raise ValueError(f"Structured output '{service.name}' model_service must point to an llm service.")

        if service.type == "search" and service.provider == "source_catalog":
            skill_name = str(data["skill_name"])
            if skill_name not in self.skills:
                raise ValueError(f"Search source catalog '{service.name}' references unknown skill '{skill_name}'.")

        if service.type == "search" and service.provider == "due_diligence_federated":
            source_catalog_name = str(data["source_catalog_service"])
            source_catalog = self.services.get(source_catalog_name)
            if source_catalog is None:
                raise ValueError(
                    f"Federated search '{service.name}' references unknown source_catalog_service "
                    f"'{source_catalog_name}'."
                )
            if source_catalog.type != "search":
                raise ValueError(
                    f"Federated search '{service.name}' source_catalog_service must point to a search service."
                )
            web_search_name = data.get("web_search_service")
            if web_search_name:
                web_search = self.services.get(str(web_search_name))
                if web_search is None:
                    raise ValueError(
                        f"Federated search '{service.name}' references unknown web_search_service "
                        f"'{web_search_name}'."
                    )
                if web_search.type != "search":
                    raise ValueError(
                        f"Federated search '{service.name}' web_search_service must point to a search service."
                    )
            for live_search_name in data.get("live_search_services", []):
                live_search = self.services.get(str(live_search_name))
                if live_search is None:
                    raise ValueError(
                        f"Federated search '{service.name}' references unknown live_search_service "
                        f"'{live_search_name}'."
                    )
                if live_search.type != "search":
                    raise ValueError(
                        f"Federated search '{service.name}' live_search_services must point to search services."
                    )

        if service.type == "scraping" and service.provider == "public_web_snapshot_monitor":
            for referenced_field in ("primary_scraping_service", "browser_session_service"):
                referenced_name = str(data[referenced_field])
                referenced = self.services.get(referenced_name)
                if referenced is None:
                    raise ValueError(
                        f"Public web snapshot monitor '{service.name}' references unknown "
                        f"{referenced_field} '{referenced_name}'."
                    )
                if referenced.type != "scraping":
                    raise ValueError(
                        f"Public web snapshot monitor '{service.name}' {referenced_field} must point to a scraping service."
                    )


def _build_services(raw_services: dict[str, dict[str, Any]]) -> dict[str, ServiceConfig]:
    return {
        name: ServiceConfig(name=name, **settings)
        for name, settings in raw_services.items()
    }


def _build_skills(raw_skills: dict[str, dict[str, Any]]) -> dict[str, SkillConfig]:
    return {
        name: SkillConfig(name=name, **settings)
        for name, settings in raw_skills.items()
    }


def load_app_config(config_path: str | Path | None = None) -> AppConfig:
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(Path(os.environ.get(ENV_PATH_ENV) or ".env"))

    path = Path(config_path or os.environ.get(CONFIG_PATH_ENV, DEFAULT_CONFIG_PATH))
    if not path.exists():
        raise FileNotFoundError(f"Service config does not exist: {path}")

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return AppConfig(
        defaults=raw.get("defaults", {}),
        services=_build_services(raw.get("services", {})),
        skills=_build_skills(raw.get("skills", {})),
        path=path,
    )
