from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

from app.core.router import ServiceRouter, get_router
from app.core.workflow_context import (
    DEFAULT_PROMPT_CONTEXT_BUDGET_CHARS,
    build_prompt_context,
    normalize_context_value,
    render_template,
    retry_prompt,
    sanitize_failure_text,
    truncate_text,
)
from app.core.workflow_dsl import StepDefinition, WorkflowDefinition


class WorkflowFatalException(Exception):
    def __init__(self, message: str, safe_payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.safe_payload = safe_payload or {"message": message}


class StepExecutionException(Exception):
    pass


class HumanGateRequiredException(Exception):
    def __init__(self, awaiting: dict[str, Any]) -> None:
        super().__init__(awaiting.get("prompt", "Human input required"))
        self.awaiting = awaiting


class WorkflowRuntimeState(BaseModel):
    workflow_id: str
    workflow: dict[str, Any]
    current_step_index: int = 0
    context: dict[str, Any] = Field(default_factory=dict)
    retry_state: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    human_decision: dict[str, Any] | None = None

    @classmethod
    def from_definition(
        cls,
        workflow: WorkflowDefinition,
        initial_context: dict[str, Any],
        conversation_id: str | None = None,
    ) -> "WorkflowRuntimeState":
        return cls(
            workflow_id=workflow.id,
            workflow=workflow.model_dump(mode="json"),
            context=normalize_context_value(initial_context),
            conversation_id=conversation_id,
        )


class StepResult(BaseModel):
    step_id: str
    output_key: str | None = None
    value: Any = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class StepExecutor:
    def __init__(self, router: ServiceRouter | None = None) -> None:
        self.router = router or get_router()

    def execute_step(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        if step_def.type == "search":
            return self._execute_search(step_def, state)
        if step_def.type == "llm_prompt":
            return self._execute_llm_prompt(step_def, state)
        if step_def.type == "structured_extract":
            return self._execute_structured_extract(step_def, state)
        if step_def.type == "save_artifact":
            return self._execute_save_artifact(step_def, state)
        if step_def.type == "human_gate":
            prompt = _render_prompt_template(step_def.prompt or "请确认", state.context)
            raise HumanGateRequiredException(
                {"agent": "json_workflow", "prompt": prompt, "draft": state.context}
            )
        raise WorkflowFatalException(f"Unsupported step type: {step_def.type}")

    def _execute_search(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        query = render_template(str(step_def.input or ""), state.context)
        provider = self.router.search(step_def.service)
        value = provider.search(query, limit=step_def.limit or 10)
        return StepResult(step_id=step_def.id, output_key=step_def.output_key, value=normalize_context_value(value))

    def _execute_llm_prompt(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        prompt = _render_prompt_template(step_def.prompt or "", state.context)
        max_tokens = step_def.max_tokens or 256
        usage = _reserve_llm_budget(state, step_def.id, prompt, max_tokens)
        llm = self.router.llm(step_def.service)
        value = llm.text(prompt, max_tokens=max_tokens)
        return StepResult(step_id=step_def.id, output_key=step_def.output_key, value=value, usage=usage)

    def _execute_save_artifact(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        value = render_template(str(step_def.input or ""), state.context)
        return StepResult(
            step_id=step_def.id,
            output_key=step_def.output_key,
            value=value,
            artifacts={step_def.output_key or step_def.id: value},
        )

    def _execute_structured_extract(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        source = _render_prompt_template(str(step_def.input or ""), state.context)
        llm = self.router.llm(step_def.service)
        prompt = (
            "请从输入中抽取结构化数据。只输出合法 JSON，不要输出 Markdown 或解释。\n\n"
            f"Schema:\n{json.dumps(step_def.schema, ensure_ascii=False, indent=2)}\n\n"
            f"Input:\n{source}"
        )
        last_output = ""
        last_error = ""
        usage: dict[str, Any] = {}
        for attempt in range((step_def.max_retries or 0) + 1):
            max_tokens = step_def.max_tokens or 1024
            usage = _reserve_llm_budget(state, step_def.id, prompt, max_tokens)
            output = llm.text(prompt, max_tokens=max_tokens)
            try:
                parsed = json.loads(output)
                _validate_schema(parsed, step_def.schema or {})
                return StepResult(
                    step_id=step_def.id,
                    output_key=step_def.output_key,
                    value=normalize_context_value(parsed),
                    usage=usage,
                    diagnostics={"attempts": attempt + 1},
                )
            except Exception as exc:
                last_output = output
                raw_error = str(exc)
                last_error = sanitize_failure_text(raw_error)
                state.retry_state = {
                    "step_id": step_def.id,
                    "retry_count": attempt + 1,
                    "last_error": last_error,
                }
                prompt = retry_prompt(step_def.schema or {}, last_output, raw_error)
        if step_def.on_failure == "human_gate":
            raise HumanGateRequiredException(
                {
                    "agent": "json_workflow",
                    "prompt": f"结构化抽取失败，需要人工确认：{step_def.id}",
                    "draft": {
                        "step_id": step_def.id,
                        "last_error": last_error,
                        "last_output": truncate_text(sanitize_failure_text(last_output), 1200),
                    },
                }
            )
        raise WorkflowFatalException(
            f"structured_extract failed for step {step_def.id}",
            {"step_id": step_def.id, "last_error": last_error},
        )


def _render_prompt_template(
    template: str,
    context: dict[str, Any],
    max_chars: int = DEFAULT_PROMPT_CONTEXT_BUDGET_CHARS,
) -> str:
    return render_template(template, build_prompt_context(template, context, max_chars=max_chars))


def _reserve_llm_budget(
    state: WorkflowRuntimeState,
    step_id: str,
    prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    budget = _task_token_budget()
    if budget is None:
        return {}
    estimated_prompt_tokens = _estimate_tokens(prompt)
    requested_tokens = estimated_prompt_tokens + max_tokens
    usage = dict(state.retry_state.get("token_budget") or {})
    used_tokens = int(usage.get("used_tokens") or 0)
    if used_tokens + requested_tokens > budget:
        raise HumanGateRequiredException(
            {
                "agent": "json_workflow",
                "prompt": f"任务 Token 预算已触发熔断：{used_tokens + requested_tokens}/{budget}",
                "draft": {
                    "reason": "token_budget_exceeded",
                    "step_id": step_id,
                    "budget_tokens": budget,
                    "used_tokens": used_tokens,
                    "requested_tokens": requested_tokens,
                    "estimated_prompt_tokens": estimated_prompt_tokens,
                    "max_tokens": max_tokens,
                },
            }
        )
    updated_usage = {
        "budget_tokens": budget,
        "used_tokens": used_tokens + requested_tokens,
        "last_step_id": step_id,
        "last_requested_tokens": requested_tokens,
    }
    state.retry_state["token_budget"] = updated_usage
    return updated_usage


def _task_token_budget() -> int | None:
    raw = os.environ.get("ZHAOPING_TASK_TOKEN_BUDGET")
    if raw in (None, ""):
        return None
    try:
        budget = int(raw)
    except ValueError:
        raise WorkflowFatalException(
            "ZHAOPING_TASK_TOKEN_BUDGET must be an integer",
            {"env_var": "ZHAOPING_TASK_TOKEN_BUDGET", "value": raw},
        )
    return budget if budget > 0 else None


def _estimate_tokens(text: str) -> int:
    normalized_length = len(text.strip())
    if normalized_length <= 0:
        return 0
    return max(1, (normalized_length + 3) // 4)


def _validate_schema(value: Any, schema: dict[str, Any]) -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise ValueError("expected object")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"missing required field: {key}")
        properties = schema.get("properties", {})
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(value[key], child_schema)
    elif schema_type == "array":
        if not isinstance(value, list):
            raise ValueError("expected array")
        item_schema = schema.get("items")
        if item_schema:
            for item in value:
                _validate_schema(item, item_schema)
    elif schema_type == "string" and not isinstance(value, str):
        raise ValueError("expected string")
    elif schema_type == "number" and not isinstance(value, (int, float)):
        raise ValueError("expected number")
    elif schema_type == "integer" and not isinstance(value, int):
        raise ValueError("expected integer")
    elif schema_type == "boolean" and not isinstance(value, bool):
        raise ValueError("expected boolean")
