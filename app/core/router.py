from __future__ import annotations

from functools import cached_property
from typing import Any

from app.core.config import AppConfig, ServiceConfig, load_app_config
from app.core.mcp_registry import MCPRegistry
from app.providers.database import PostgresDatabaseProvider
from app.providers.common import DisabledProvider
from app.providers.document import AutoDocumentParser, DoclingDocumentParser, PlainTextDocumentParser
from app.providers.embedding import SentenceTransformerEmbeddingProvider
from app.providers.llm import AnthropicCompatibleLLMProvider
from app.providers.ocr import AliyunOCRProvider, DoclingOCRProvider
from app.providers.search import SearchSourceCatalogProvider
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

        if service.type == "llm" and provider == "anthropic_compatible":
            return AnthropicCompatibleLLMProvider(
                base_url=str(settings["base_url"]),
                api_key_env=str(settings["api_key_env"]),
                model=str(settings["model"]),
                anthropic_version=str(settings["anthropic_version"]),
                timeout_seconds=int(settings.get("timeout_seconds", 60)),
            )

        if service.type == "database" and provider == "postgres":
            import os

            env_name = str(settings["database_url_env"])
            database_url = os.environ.get(env_name)
            if not database_url:
                raise RuntimeError(f"Missing required environment variable: {env_name}")
            return PostgresDatabaseProvider(database_url)

        if provider == "disabled":
            return DisabledProvider(service.type, service.name)

        raise ValueError(f"Unsupported provider '{provider}' for service '{service.name}' ({service.type}).")


def get_router(config_path: str | None = None) -> ServiceRouter:
    return ServiceRouter(load_app_config(config_path) if config_path else None)
