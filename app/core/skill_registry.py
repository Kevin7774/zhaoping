from __future__ import annotations

import importlib
from typing import Any

from app.core.config import AppConfig


class SkillRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._loaded: dict[str, Any] = {}

    def get(self, name: str) -> Any:
        if name not in self._loaded:
            skill = self.config.skills[name]
            module = importlib.import_module(skill.module)
            self._loaded[name] = getattr(module, skill.entrypoint)
        return self._loaded[name]

    def all(self) -> dict[str, Any]:
        return {name: self.get(name) for name in self.config.skills}
