from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class WorkflowValidationException(ValueError):
    pass


class StepDefinition(BaseModel):
    id: str
    type: Literal["search", "llm_prompt", "structured_extract", "save_artifact", "human_gate"]
    input: str | dict[str, Any] | None = None
    prompt: str | None = None
    output_key: str | None = None
    service: str | None = None
    limit: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    schema: dict[str, Any] | None = None
    max_retries: int = 0
    on_failure: Literal["error", "human_gate"] = "error"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> "StepDefinition":
        try:
            return super().model_validate(obj, *args, **kwargs)
        except ValidationError as exc:
            _raise_workflow_validation_exception(exc)
            raise

    @model_validator(mode="after")
    def validate_step_contract(self) -> "StepDefinition":
        if self.type == "search" and (self.input is None or not self.output_key):
            raise WorkflowValidationException("search step requires input and output_key")
        if self.type == "llm_prompt" and (not self.prompt or not self.output_key):
            raise WorkflowValidationException("llm_prompt step requires prompt and output_key")
        if self.type == "structured_extract" and (self.input is None or not self.schema or not self.output_key):
            raise WorkflowValidationException("structured_extract step requires input, schema, and output_key")
        if self.type == "save_artifact" and (self.input is None or not self.output_key):
            raise WorkflowValidationException("save_artifact step requires input and output_key")
        if self.type == "human_gate" and not self.prompt:
            raise WorkflowValidationException("human_gate step requires prompt")
        if self.max_retries < 0 or self.max_retries > 5:
            raise WorkflowValidationException("max_retries must be between 0 and 5")
        if self.limit is not None and (self.limit < 1 or self.limit > 50):
            raise WorkflowValidationException("limit must be between 1 and 50")
        if self.max_tokens is not None and (self.max_tokens < 1 or self.max_tokens > 8192):
            raise WorkflowValidationException("max_tokens must be between 1 and 8192")
        return self

    def placeholders(self) -> set[str]:
        found: set[str] = set()
        found.update(_placeholders_in_value(self.input))
        found.update(_placeholders_in_value(self.prompt))
        return found


class WorkflowDefinition(BaseModel):
    id: str
    name: str | None = None
    version: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepDefinition]

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> "WorkflowDefinition":
        try:
            return super().model_validate(obj, *args, **kwargs)
        except ValidationError as exc:
            _raise_workflow_validation_exception(exc)
            raise

    @model_validator(mode="after")
    def validate_workflow_contract(self) -> "WorkflowDefinition":
        if not self.steps:
            raise WorkflowValidationException("workflow must contain at least one step")
        seen_step_ids: set[str] = set()
        seen_outputs: set[str] = set()
        available = set(self.inputs.keys())
        all_outputs = {step.output_key for step in self.steps if step.output_key}

        for step in self.steps:
            if step.id in seen_step_ids:
                raise WorkflowValidationException(f"Duplicate step id: {step.id}")
            seen_step_ids.add(step.id)

            for placeholder in sorted(step.placeholders()):
                if placeholder not in available:
                    if placeholder in all_outputs:
                        raise WorkflowValidationException(
                            f"Step '{step.id}' references future output: {placeholder}"
                        )
                    raise WorkflowValidationException(
                        f"Unresolved template variable in step '{step.id}': {placeholder}"
                    )

            if step.output_key:
                if step.output_key in seen_outputs:
                    raise WorkflowValidationException(f"Duplicate output_key: {step.output_key}")
                seen_outputs.add(step.output_key)
                available.add(step.output_key)

        return self

    def dependency_summary(self) -> dict[str, list[str]]:
        return {
            "declared_inputs": sorted(self.inputs.keys()),
            "produced_outputs": [step.output_key for step in self.steps if step.output_key],
        }


def _placeholders_in_value(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(PLACEHOLDER_RE.findall(value))
    if isinstance(value, dict):
        found: set[str] = set()
        for child in value.values():
            found.update(_placeholders_in_value(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_placeholders_in_value(child))
        return found
    return set()


def _raise_workflow_validation_exception(exc: ValidationError) -> None:
    for error in exc.errors():
        cause = (error.get("ctx") or {}).get("error")
        if isinstance(cause, WorkflowValidationException):
            raise cause from exc
