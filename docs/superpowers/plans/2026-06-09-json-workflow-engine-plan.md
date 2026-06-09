# JSON Workflow Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend-only JSON Step-based Workflow Engine that validates, runs, checkpoints, suspends, resumes, and completes user-defined workflows without touching existing A/B/C/D scenario logic.

**Architecture:** Use a strangler-fig approach: add new workflow modules beside the existing hard-coded recruiting orchestrator. `WorkflowDefinition` owns static JSON DSL validation, `WorkflowRuntimeState` owns persisted runtime snapshots, `StepExecutor` executes atomic steps through `ServiceRouter`, and `WorkflowTaskRunner` owns task lifecycle using existing `TaskModel`, `AgentEventModel`, `task_store` snapshots, and SSE event publishing.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy task models, existing `ServiceRouter`, pytest, no new provider configuration, no frontend editor.

---

## Hard Constraints

- Do not modify `SCENARIO_PLANS`, A/B/C/D step handlers, or `AgentRunner` business behavior in `app/core/orchestrator.py`.
- `StepExecutor` must import `ServiceRouter` / `get_router` only; it must not import any concrete provider from `app.providers`.
- Add tests in `tests/test_json_workflow_engine.py` before implementation in each phase.
- Reuse `TaskModel` and `AgentEventModel`; do not add new tables or migrations.
- Persist runtime state under `TaskModel.frontend_state["json_workflow_runtime"]`.
- Expose `workflow_id` in task snapshots, SSE event payloads, and final task result so JSON workflow tasks are distinguishable from A/B/C/D tasks in UI and reports.
- Runtime state, `context`, `artifacts`, `awaiting`, and `result` must contain JSON-serializable values only; never store provider objects, exception objects, raw datetime objects, open file handles, or other Python runtime instances.
- Use existing event types only: `step_start`, `tool_call`, `evidence`, `summary`, `human_gate`, `error`, `cancelled`.
- Human gate must checkpoint and release execution; it must not wait on `DBTaskStore._wait_for_human`.
- `POST /tasks/{task_id}/confirm` must check for `json_workflow_runtime` before calling legacy `task_store.confirm(...)`.
- Suspended JSON workflows with `status="awaiting_human"` must not be recovered as interrupted errors on backend restart.
- Interrupted JSON workflows with `status="processing"` must not silently hang; first implementation must mark them `error` with an explicit interrupted recovery event unless automatic resume is implemented in the same phase.
- Unit tests must mock external services; no live LLM/search calls during tests.

## File Map

- Create: `app/core/workflow_dsl.py`  
  Static DSL models, placeholder scanning, dependency validation, validation response helpers.

- Create: `app/core/workflow_context.py`  
  `render_value`, `render_template`, `normalize_context_value`, `truncate_text`, retry prompt rendering.

- Create: `app/core/workflow_executor.py`  
  `StepResult`, workflow exceptions, `StepExecutor`, structured extract retry loop, minimal JSON-schema-like validation.

- Create: `app/core/workflow_runner.py`  
  `WorkflowRuntimeState`, `WorkflowTaskRunner`, checkpoint persistence, task creation, resume, finalization.

- Create: `app/schemas/workflows.py`  
  FastAPI request/response schemas for `/workflows/validate` and `/workflows/run`.

- Modify: `app/api/main.py`  
  Add `/workflows/validate`, `/workflows/run`; route JSON workflow confirmations before legacy `task_store.confirm`.

- Modify: `app/core/orchestrator.py`  
  Minimal recovery guard only: suspended JSON workflow tasks stay `awaiting_human`; interrupted processing JSON workflow tasks are explicitly marked `error` with recovery metadata.

- Modify: `tests/test_static_contracts.py`  
  Add OpenAPI assertions for `/workflows/validate` and `/workflows/run`.

- Create: `tests/test_json_workflow_engine.py`  
  All phase tests, with mocked routers/providers only.

## TaskModel / AgentEventModel Reuse Contract

- `TaskModel.scenario_id = "json_workflow"`.
- `TaskModel.input = json.dumps(initial_context, ensure_ascii=False)`.
- `TaskModel.total_steps = len(workflow.steps)`.
- `TaskModel.current_step = state.current_step_index`.
- `TaskModel.current_agent = "json_workflow"` or current step type.
- `TaskModel.frontend_state["json_workflow_runtime"] = WorkflowRuntimeState.model_dump(mode="json")`.
- `TaskModel.frontend_state["json_workflow"] = {"workflow_id": workflow.id, "workflow_name": workflow.name}` for UI/report visibility.
- `TaskModel.awaiting` stores human gate payload.
- `TaskModel.result` stores:
  ```python
  {
      "workflow_id": state.workflow_id,
      "context": state.context,
      "artifacts": state.artifacts,
      "final_output": state.context.get(last_output_key),
  }
  ```
- `AgentEventModel` rows are created through `task_store.append_event(...)` where possible so SSE subscribers receive events through the existing bus.
- Every JSON workflow `AgentEventModel.data` payload includes `{"workflow_id": state.workflow_id, "json_workflow": True}`.
- Every runtime checkpoint is normalized through `normalize_context_value(...)` before writing to `TaskModel.frontend_state`.
- `TaskModel.awaiting` and `TaskModel.result` are normalized through `normalize_context_value(...)` before persistence.

---

## Phase 1: DSL Definition

**Files:**
- Create: `app/core/workflow_dsl.py`
- Create: `tests/test_json_workflow_engine.py`

- [ ] **Step 1: Write failing DSL tests**

Add these tests to `tests/test_json_workflow_engine.py`:

```python
import pytest

from app.core.workflow_dsl import WorkflowDefinition, WorkflowValidationException


def valid_workflow() -> dict:
    return {
        "id": "research_report",
        "inputs": {"user_input": {"type": "string"}},
        "steps": [
            {
                "id": "search",
                "type": "search",
                "input": "{{ user_input }}",
                "limit": 5,
                "output_key": "search_results",
            },
            {
                "id": "summary",
                "type": "llm_prompt",
                "prompt": "Summarize: {{ search_results }}",
                "output_key": "summary",
            },
        ],
    }


def test_workflow_definition_accepts_valid_minimal_workflow() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    assert workflow.id == "research_report"
    assert [step.id for step in workflow.steps] == ["search", "summary"]
    assert workflow.dependency_summary()["declared_inputs"] == ["user_input"]
    assert workflow.dependency_summary()["produced_outputs"] == ["search_results", "summary"]


def test_workflow_definition_rejects_duplicate_step_ids() -> None:
    payload = valid_workflow()
    payload["steps"][1]["id"] = "search"
    with pytest.raises(WorkflowValidationException, match="Duplicate step id"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_definition_rejects_unresolved_placeholder() -> None:
    payload = valid_workflow()
    payload["steps"][0]["input"] = "{{ missing_query }}"
    with pytest.raises(WorkflowValidationException, match="Unresolved template variable"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_definition_rejects_future_dependency() -> None:
    payload = valid_workflow()
    payload["steps"][0]["input"] = "{{ summary }}"
    with pytest.raises(WorkflowValidationException, match="future output"):
        WorkflowDefinition.model_validate(payload)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'app.core.workflow_dsl'`.

- [ ] **Step 3: Implement DSL models**

Create `app/core/workflow_dsl.py` with:

```python
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
```

- [ ] **Step 4: Run Phase 1 tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: 4 passed.

- [ ] **Step 5: Commit Phase 1**

```bash
git add app/core/workflow_dsl.py tests/test_json_workflow_engine.py
git commit -m "feat: add json workflow dsl validation"
```

---

## Phase 2: Executor And Context Rendering

**Files:**
- Create: `app/core/workflow_context.py`
- Create: `app/core/workflow_executor.py`
- Modify: `tests/test_json_workflow_engine.py`

- [ ] **Step 1: Add failing context/executor tests**

Append to `tests/test_json_workflow_engine.py`:

```python
import json
from pathlib import Path

from app.core.workflow_context import render_template, render_value
from app.core.workflow_executor import (
    HumanGateRequiredException,
    StepExecutor,
    WorkflowRuntimeState,
)


class FakeSearchProvider:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query: str, limit: int = 10):
        self.calls.append({"query": query, "limit": limit})
        return [{"title": "Result", "snippet": query}]


class FakeLLMProvider:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or ["ok"])
        self.prompts = []

    def text(self, prompt: str, max_tokens: int = 256) -> str:
        self.prompts.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.outputs.pop(0)


class FakeRouter:
    def __init__(self, llm_outputs: list[str] | None = None) -> None:
        self.search_provider = FakeSearchProvider()
        self.llm_provider = FakeLLMProvider(llm_outputs)

    def search(self, service_name: str | None = None):
        return self.search_provider

    def llm(self, service_name: str | None = None):
        return self.llm_provider

    def structured_output(self, service_name: str | None = None):
        raise RuntimeError("structured output backend unavailable in unit test")


def test_render_value_uses_json_for_non_strings() -> None:
    rendered = render_value({"ok": True, "missing": None, "items": [{"name": "OpenAI"}]})
    parsed = json.loads(rendered)
    assert parsed["ok"] is True
    assert parsed["missing"] is None
    assert "'ok'" not in rendered
    assert "None" not in rendered


def test_render_template_injects_context_as_formatted_json() -> None:
    prompt = render_template("Entities:\n{{ entities }}", {"entities": [{"name": "OpenAI"}]})
    assert json.loads(prompt.split("Entities:\n", 1)[1]) == [{"name": "OpenAI"}]


def test_step_executor_uses_service_router_for_search() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    state = WorkflowRuntimeState.from_definition(workflow, {"user_input": "robotics"})
    router = FakeRouter()
    result = StepExecutor(router=router).execute_step(workflow.steps[0], state)
    assert router.search_provider.calls == [{"query": "robotics", "limit": 5}]
    assert result.output_key == "search_results"
    assert result.value[0]["snippet"] == "robotics"


def test_step_executor_uses_service_router_for_llm_prompt() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    state = WorkflowRuntimeState.from_definition(workflow, {"user_input": "robotics"})
    state.context["search_results"] = [{"title": "A"}]
    router = FakeRouter(llm_outputs=["summary"])
    result = StepExecutor(router=router).execute_step(workflow.steps[1], state)
    assert router.llm_provider.prompts[0]["max_tokens"] == 256
    assert result.value == "summary"


def test_step_executor_does_not_import_concrete_providers() -> None:
    source = Path("app/core/workflow_executor.py").read_text(encoding="utf-8")
    assert "app.providers" not in source
    assert "OpenRouterChatLLMProvider" not in source
    assert "BraveWebSearchProvider" not in source


def test_structured_extract_retries_with_only_last_failure() -> None:
    payload = {
        "id": "extract",
        "inputs": {"source": {"type": "string"}},
        "steps": [
            {
                "id": "extract_entities",
                "type": "structured_extract",
                "input": "{{ source }}",
                "schema": {
                    "type": "object",
                    "required": ["entities"],
                    "properties": {"entities": {"type": "array"}},
                },
                "max_retries": 2,
                "output_key": "entities",
            }
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    state = WorkflowRuntimeState.from_definition(workflow, {"source": "OpenAI hired Alice"})
    router = FakeRouter(llm_outputs=["not json", "{\"wrong\": []}", "{\"entities\": []}"])
    result = StepExecutor(router=router).execute_step(workflow.steps[0], state)
    assert result.value == {"entities": []}
    assert len(router.llm_provider.prompts) == 3
    last_prompt = router.llm_provider.prompts[-1]["prompt"]
    assert "not json" not in last_prompt
    assert "\"wrong\": []" in last_prompt


def test_structured_extract_exhaustion_can_raise_human_gate() -> None:
    payload = {
        "id": "extract",
        "inputs": {"source": {"type": "string"}},
        "steps": [
            {
                "id": "extract_entities",
                "type": "structured_extract",
                "input": "{{ source }}",
                "schema": {
                    "type": "object",
                    "required": ["entities"],
                    "properties": {"entities": {"type": "array"}},
                },
                "max_retries": 1,
                "on_failure": "human_gate",
                "output_key": "entities",
            }
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    state = WorkflowRuntimeState.from_definition(workflow, {"source": "bad"})
    router = FakeRouter(llm_outputs=["bad", "{\"wrong\": []}"])
    with pytest.raises(HumanGateRequiredException) as exc:
        StepExecutor(router=router).execute_step(workflow.steps[0], state)
    assert exc.value.awaiting["agent"] == "json_workflow"
    assert exc.value.awaiting["draft"]["step_id"] == "extract_entities"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: fail with missing `workflow_context`, `workflow_executor`, and `WorkflowRuntimeState`.

- [ ] **Step 3: Implement context rendering**

Create `app/core/workflow_context.py`:

```python
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def normalize_context_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): normalize_context_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_context_value(child) for child in value]
    try:
        json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)
    return value


def render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(normalize_context_value(value), ensure_ascii=False, indent=2, default=str)


def render_template(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"Missing template variable: {key}")
        return render_value(context[key])

    return PLACEHOLDER_RE.sub(replace, template)


def truncate_text(value: Any, max_chars: int) -> str:
    text = value if isinstance(value, str) else render_value(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...[truncated]"


def retry_prompt(schema: dict[str, Any], last_output: str, validation_error: str) -> str:
    return (
        "你是一个数据修正助手。上一次你的输出未通过 Pydantic 校验。\n\n"
        f"【期待的 Schema】：\n{truncate_text(schema, 4000)}\n\n"
        f"【你上一次的错误输出】：\n{truncate_text(last_output, 4000)}\n\n"
        f"【校验失败原因】：\n{truncate_text(validation_error, 2000)}\n\n"
        "请重新调整你的输出。只输出符合 Schema 的合法 JSON，不要输出解释、Markdown 或额外文本。"
    )
```

- [ ] **Step 4: Implement executor and runtime state**

Create `app/core/workflow_executor.py` with these exact public objects:

```python
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.core.router import ServiceRouter, get_router
from app.core.workflow_context import normalize_context_value, render_template, retry_prompt
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
            prompt = render_template(step_def.prompt or "请确认", state.context)
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
        prompt = render_template(step_def.prompt or "", state.context)
        llm = self.router.llm(step_def.service)
        value = llm.text(prompt, max_tokens=step_def.max_tokens or 256)
        return StepResult(step_id=step_def.id, output_key=step_def.output_key, value=value)

    def _execute_save_artifact(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        value = render_template(str(step_def.input or ""), state.context)
        return StepResult(
            step_id=step_def.id,
            output_key=step_def.output_key,
            value=value,
            artifacts={step_def.output_key or step_def.id: value},
        )

    def _execute_structured_extract(self, step_def: StepDefinition, state: WorkflowRuntimeState) -> StepResult:
        source = render_template(str(step_def.input or ""), state.context)
        llm = self.router.llm(step_def.service)
        prompt = (
            "请从输入中抽取结构化数据。只输出合法 JSON，不要输出 Markdown 或解释。\n\n"
            f"Schema:\n{json.dumps(step_def.schema, ensure_ascii=False, indent=2)}\n\n"
            f"Input:\n{source}"
        )
        last_output = ""
        last_error = ""
        for attempt in range((step_def.max_retries or 0) + 1):
            output = llm.text(prompt, max_tokens=step_def.max_tokens or 1024)
            try:
                parsed = json.loads(output)
                _validate_schema(parsed, step_def.schema or {})
                return StepResult(
                    step_id=step_def.id,
                    output_key=step_def.output_key,
                    value=normalize_context_value(parsed),
                    diagnostics={"attempts": attempt + 1},
                )
            except Exception as exc:
                last_output = output
                last_error = str(exc)
                state.retry_state = {
                    "step_id": step_def.id,
                    "retry_count": attempt + 1,
                    "last_error": last_error,
                }
                prompt = retry_prompt(step_def.schema or {}, last_output, last_error)
        if step_def.on_failure == "human_gate":
            raise HumanGateRequiredException(
                {
                    "agent": "json_workflow",
                    "prompt": f"结构化抽取失败，需要人工确认：{step_def.id}",
                    "draft": {"step_id": step_def.id, "last_error": last_error, "last_output": last_output[:1200]},
                }
            )
        raise WorkflowFatalException(
            f"structured_extract failed for step {step_def.id}",
            {"step_id": step_def.id, "last_error": last_error},
        )


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
```

- [ ] **Step 5: Run Phase 2 tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: all Phase 1 and Phase 2 tests pass.

- [ ] **Step 6: Commit Phase 2**

```bash
git add app/core/workflow_context.py app/core/workflow_executor.py tests/test_json_workflow_engine.py
git commit -m "feat: add json workflow executor"
```

---

## Phase 3: Runner And Checkpoint State Machine

**Files:**
- Create: `app/core/workflow_runner.py`
- Modify: `app/core/orchestrator.py`
- Modify: `tests/test_json_workflow_engine.py`

- [ ] **Step 1: Add failing runner/checkpoint tests**

Append to `tests/test_json_workflow_engine.py`:

```python
from app.core.workflow_runner import WorkflowTaskRunner


def test_runner_creates_task_and_checkpoints_runtime_state() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["summary"]))
    task_id = runner.start(workflow, {"user_input": "robotics"}, auto_run=False)
    snapshot = runner.snapshot(task_id)
    runtime = snapshot["frontend_state"]["json_workflow_runtime"]
    assert snapshot["scenario_id"] == "json_workflow"
    assert snapshot["frontend_state"]["json_workflow"]["workflow_id"] == "research_report"
    assert runtime["workflow_id"] == "research_report"
    assert runtime["current_step_index"] == 0
    assert runtime["context"]["user_input"] == "robotics"
    json.dumps(runtime, ensure_ascii=False)


def test_runner_runs_to_done_and_writes_task_result() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["summary"]))
    task_id = runner.start(workflow, {"user_input": "robotics"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)
    snapshot = runner.snapshot(task_id)
    assert snapshot["status"] == "done"
    assert snapshot["result"]["workflow_id"] == "research_report"
    assert snapshot["result"]["final_output"] == "summary"
    json.dumps(snapshot["result"], ensure_ascii=False)


def test_runner_human_gate_checkpoints_without_waiting() -> None:
    payload = {
        "id": "approval_flow",
        "inputs": {"draft": {"type": "string"}},
        "steps": [
            {"id": "gate", "type": "human_gate", "prompt": "Approve {{ draft }}", "output_key": "approval"},
            {"id": "final", "type": "llm_prompt", "prompt": "Decision {{ approval }}", "output_key": "done"},
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["finished"]))
    task_id = runner.start(workflow, {"draft": "hello"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)
    snapshot = runner.snapshot(task_id)
    assert snapshot["status"] == "awaiting_human"
    assert snapshot["awaiting"]["prompt"] == "Approve hello"
    assert snapshot["awaiting"]["workflow_id"] == "approval_flow"
    assert snapshot["frontend_state"]["json_workflow_runtime"]["current_step_index"] == 0
    json.dumps(snapshot["awaiting"], ensure_ascii=False)


def test_runner_resume_continues_after_human_gate() -> None:
    payload = {
        "id": "approval_flow",
        "inputs": {"draft": {"type": "string"}},
        "steps": [
            {"id": "gate", "type": "human_gate", "prompt": "Approve {{ draft }}", "output_key": "approval"},
            {"id": "final", "type": "llm_prompt", "prompt": "Decision {{ approval }}", "output_key": "done"},
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["finished"]))
    task_id = runner.start(workflow, {"draft": "hello"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)
    snapshot = runner.resume(task_id, "approve", {"note": "ok"}, auto_run=False)
    assert snapshot["frontend_state"]["json_workflow_runtime"]["context"]["approval"]["decision"] == "approve"
    runner.run_until_blocked_or_done(task_id)
    done = runner.snapshot(task_id)
    assert done["status"] == "done"
    assert done["result"]["final_output"] == "finished"


def test_runner_error_on_structured_extract_failure_emits_error_event() -> None:
    payload = {
        "id": "extract_error",
        "inputs": {"source": {"type": "string"}},
        "steps": [
            {
                "id": "extract_entities",
                "type": "structured_extract",
                "input": "{{ source }}",
                "schema": {
                    "type": "object",
                    "required": ["entities"],
                    "properties": {"entities": {"type": "array"}},
                },
                "max_retries": 1,
                "on_failure": "error",
                "output_key": "entities",
            }
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["bad", "{\"wrong\": []}"]))
    task_id = runner.start(workflow, {"source": "bad"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)
    snapshot = runner.snapshot(task_id)
    assert snapshot["status"] == "error"
    assert snapshot["error"]
    assert any(event["type"] == "error" and event["data"]["workflow_id"] == "extract_error" for event in snapshot["audit_events"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: fail with missing `app.core.workflow_runner`.

- [ ] **Step 3: Implement runner**

Create `app/core/workflow_runner.py`.

Required implementation details:

- Create `TaskModel` directly with `scenario_id="json_workflow"` because `task_store.create(...)` assumes `SCENARIO_PLANS[scenario_id]`.
- Use `make_task_session_factory()` from `app.db.task_models`.
- Use `task_store.append_event(...)` after row creation so existing SSE subscribers receive events through the current bus.
- Use `task_store.snapshot(task_id)` for public snapshots.
- Use `WorkflowRuntimeState.from_definition(...)` for initial state.
- Write both `frontend_state["json_workflow_runtime"]` and `frontend_state["json_workflow"]`.
- Ensure `frontend_state["json_workflow"]["workflow_id"]` is visible in task snapshots for UI/report rendering.
- Normalize every runtime checkpoint with `normalize_context_value(...)` before database writes.
- Add `workflow_id` and `json_workflow=True` to every JSON workflow audit event payload.
- On each step:
  - Set `TaskModel.current_step`.
  - Set `TaskModel.current_agent = step.type`.
  - Append `step_start` and `tool_call`.
  - Execute via `StepExecutor`.
  - Write `result.value` to `state.context[result.output_key]`.
  - Merge `result.artifacts`.
  - Increment `state.current_step_index`.
  - Persist checkpoint.
  - Append `summary`.
- On `HumanGateRequiredException`:
  - Persist checkpoint under `frontend_state["json_workflow_runtime"]`.
  - Set `TaskModel.status = "awaiting_human"`.
  - Set `TaskModel.awaiting = normalize_context_value({**exc.awaiting, "workflow_id": state.workflow_id, "json_workflow": True})`.
  - Append `human_gate`.
  - Return without waiting.
- On `WorkflowFatalException`:
  - Persist the latest checkpoint under `frontend_state["json_workflow_runtime"]`.
  - Set `TaskModel.status = "error"`.
  - Set `TaskModel.error`.
  - Append `error` with `workflow_id`, `json_workflow=True`, `step_id`, and a truncated error summary.
- On completion:
  - Set `TaskModel.status = "done"`.
  - Set `TaskModel.result = normalize_context_value({"workflow_id": state.workflow_id, "context": state.context, "artifacts": state.artifacts, "final_output": state.context.get(last_output_key)})`, where `last_output_key` is the last workflow step `output_key` that is not empty.
  - Append final `summary` with `status="done"` and `workflow_id`.
- Add `auto_run` option so API can spawn background execution and tests can run synchronously.

- [ ] **Step 4: Add recovery guard**

Modify only `_recover_interrupted_tasks()` in `app/core/orchestrator.py`:

- If `row.status == "awaiting_human"` and `(row.frontend_state or {}).get("json_workflow_runtime")` exists, skip interruption recovery and leave the task suspended.
- If `row.status == "processing"` and `(row.frontend_state or {}).get("json_workflow_runtime")` exists, mark the task `error` with message `JSON workflow interrupted by backend restart. Please retry the workflow task.` and append an `error` event with `{"recovery": "json_workflow_interrupted", "workflow_id": runtime["workflow_id"], "json_workflow": True}`.
- Do not modify `SCENARIO_PLANS`, step handlers, `AgentRunner`, or A/B/C/D logic.

- [ ] **Step 5: Run Phase 3 tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: all Phase 1-3 tests pass.

- [ ] **Step 6: Run existing task/static regression tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_static_contracts.py -q
```

Expected: pass; existing A/B/C/D contracts remain intact.

- [ ] **Step 7: Commit Phase 3**

```bash
git add app/core/workflow_runner.py app/core/orchestrator.py tests/test_json_workflow_engine.py
git commit -m "feat: add json workflow task runner"
```

---

## Phase 4: API And SSE Mounting

**Files:**
- Create: `app/schemas/workflows.py`
- Modify: `app/api/main.py`
- Modify: `tests/test_json_workflow_engine.py`
- Modify: `tests/test_static_contracts.py`

- [ ] **Step 1: Add failing API tests**

Append to `tests/test_json_workflow_engine.py`:

```python
from fastapi.testclient import TestClient
from app.api.main import app


def test_workflows_validate_api_accepts_valid_workflow() -> None:
    client = TestClient(app)
    response = client.post("/workflows/validate", json={"workflow": valid_workflow()})
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["workflow_id"] == "research_report"
    assert payload["step_count"] == 2


def test_workflows_validate_api_reports_invalid_workflow() -> None:
    client = TestClient(app)
    payload = valid_workflow()
    payload["steps"][0]["input"] = "{{ missing }}"
    response = client.post("/workflows/validate", json={"workflow": payload})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "Unresolved template variable" in body["errors"][0]["message"]


def test_workflows_run_api_creates_task() -> None:
    client = TestClient(app)
    response = client.post(
        "/workflows/run",
        json={"workflow": valid_workflow(), "input": {"user_input": "robotics"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_id"] == "research_report"
    assert payload["status"] == "processing"
    assert payload["task_id"]


def test_openapi_exposes_json_workflow_routes() -> None:
    schema = app.openapi()
    assert "/workflows/validate" in schema["paths"]
    assert "/workflows/run" in schema["paths"]


def test_confirm_route_checks_json_workflow_before_legacy_confirm() -> None:
    source = Path("app/api/main.py").read_text(encoding="utf-8")
    confirm_start = source.index("def confirm_task")
    json_runtime_check = source.index("json_workflow_runtime", confirm_start)
    legacy_confirm = source.index("task_store.confirm", confirm_start)
    assert json_runtime_check < legacy_confirm
```

- [ ] **Step 2: Add static contract assertions**

Modify `tests/test_static_contracts.py::test_run_request_scenario_is_dynamic_in_openapi` to include:

```python
assert "/workflows/validate" in schema["paths"]
assert "/workflows/run" in schema["paths"]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py tests/test_static_contracts.py::test_run_request_scenario_is_dynamic_in_openapi -q
```

Expected: fail because `/workflows/*` endpoints do not exist.

- [ ] **Step 4: Add workflow schemas**

Create `app/schemas/workflows.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowValidateRequest(BaseModel):
    workflow: dict[str, Any]


class WorkflowRunRequest(BaseModel):
    workflow: dict[str, Any]
    input: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None


class WorkflowValidateResponse(BaseModel):
    valid: bool
    workflow_id: str | None = None
    step_count: int = 0
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)


class WorkflowRunResponse(BaseModel):
    task_id: str
    workflow_id: str
    status: str
```

- [ ] **Step 5: Add API endpoints**

Modify `app/api/main.py`:

- Import workflow schemas.
- Import `WorkflowDefinition`, `WorkflowValidationException`.
- Import `WorkflowTaskRunner`.
- Add `POST /workflows/validate`.
- Add `POST /workflows/run`.
- In `confirm_task`, branch JSON workflow tasks before legacy `task_store.confirm`.
- The JSON workflow branch must run after the normal task existence/status checks but before `ok = task_store.confirm(...)`.
- The JSON workflow branch must not call `task_store.confirm(...)`; it calls `WorkflowTaskRunner().resume(...)` instead.

Required confirm branching logic:

```python
runtime = (task.frontend_state or {}).get("json_workflow_runtime")
if runtime:
    return WorkflowTaskRunner().resume(
        task_id,
        request.decision,
        {"edits": request.edits, "data": request.data},
    )
```

- [ ] **Step 6: Run Phase 4 tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
.venv/bin/python -m pytest tests/test_static_contracts.py -q
```

Expected: pass.

- [ ] **Step 7: Verify app importability**

Run:

```bash
.venv/bin/python -c "from app.api.main import app; print(app.title)"
```

Expected:

```text
Robot Talent Agent MVP
```

- [ ] **Step 8: Commit Phase 4**

```bash
git add app/schemas/workflows.py app/api/main.py tests/test_json_workflow_engine.py tests/test_static_contracts.py
git commit -m "feat: expose json workflow api"
```

---

## Final Verification

Run:

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
.venv/bin/python -m pytest tests/test_static_contracts.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -c "from app.api.main import app; print(app.title)"
```

Expected:

- `compileall` succeeds.
- `tests/test_json_workflow_engine.py` passes.
- `tests/test_static_contracts.py` passes.
- Full backend suite remains green.
- Existing A/B/C/D scenario tests remain unchanged and passing.

## Plan Self-Review

- Spec coverage: covers DSL validation, ServiceRouter-only executor, JSON context rendering, bounded self-correction, checkpoint/resume, human gate suspension, API routes, SSE reuse, and task result persistence.
- Strangler check: no migration or refactor of A/B/C/D; only a guarded recovery exception in `orchestrator.py` and API confirm branching.
- Provider isolation check: `StepExecutor` must not import `app.providers`; test enforces this.
- Persistence check: no new tables; uses `TaskModel.frontend_state["json_workflow_runtime"]`, `TaskModel.awaiting`, `TaskModel.result`, and `AgentEventModel`.
- TDD check: each of the four phases starts with failing tests in `tests/test_json_workflow_engine.py`.
