from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path("config/services.toml")
CONFIG_PATH_ENV = "ROBOT_AGENT_CONFIG"

ServiceType = Literal[
    "database",
    "document_parser",
    "embedding",
    "llm",
    "mcp",
    "ocr",
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
            ("vector_store", "qdrant_local"): ("path", "collection_name", "distance", "embedding_service", "vector_size"),
            ("structured_output", "outlines"): ("model_service",),
            ("database", "postgres"): ("database_url_env",),
            ("llm", "anthropic_compatible"): ("base_url", "api_key_env", "model", "anthropic_version"),
            ("ocr", "aliyun_ocr"): ("access_key_id_env", "access_key_secret_env", "region_id", "endpoint"),
            ("search", "source_catalog"): ("skill_name",),
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
        load_dotenv()

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
