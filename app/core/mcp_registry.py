from __future__ import annotations

from app.core.config import AppConfig, ServiceConfig


class MCPRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def services(self) -> dict[str, ServiceConfig]:
        return {
            name: service
            for name, service in self.config.services.items()
            if service.type == "mcp"
        }

    def configured(self) -> list[str]:
        return [
            name
            for name, service in self.services().items()
            if service.provider != "disabled"
        ]
