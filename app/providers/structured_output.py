from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class OutlinesStructuredOutputProvider:
    """Structured-output facade for Outlines-compatible model callables."""

    def __init__(self, model_service: str) -> None:
        self.model_service = model_service

    def generate(self, prompt: str, output_type: type[T], model: Any | None = None) -> T:
        if model is None:
            raise RuntimeError(
                "Outlines structured generation requires a configured model backend. "
                f"Current model_service is '{self.model_service}'."
            )
        try:
            import outlines  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("outlines is required for structured generation.") from exc

        result = model(prompt, output_type)
        if isinstance(result, output_type):
            return result
        if isinstance(result, dict):
            return output_type.model_validate(result)
        if isinstance(result, str):
            return output_type.model_validate_json(result)
        return output_type.model_validate(result)
