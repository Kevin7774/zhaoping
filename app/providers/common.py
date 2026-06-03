from __future__ import annotations

from typing import Any


class DisabledProvider:
    def __init__(self, service_type: str, service_name: str) -> None:
        self.service_type = service_type
        self.service_name = service_name

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            f"Service '{self.service_name}' for type '{self.service_type}' is disabled. "
            "Configure a concrete provider in config/services.toml before use."
        )
