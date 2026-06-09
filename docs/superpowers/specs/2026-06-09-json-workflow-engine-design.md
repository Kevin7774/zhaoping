# JSON Workflow Engine Design

## Status

Approved design for the first backend-only implementation of a JSON DSL driven workflow engine.

This design adds a generic step-based orchestration layer alongside the existing hard-coded recruiting scenarios. It does not replace scenario A/B/C/D in the first implementation phase.

## Goal

Build a backend API-only JSON workflow engine that can validate, run, checkpoint, suspend, resume, and finish user-defined prompt chains while reusing the repository's existing task persistence, audit events, SSE stream, and `ServiceRouter` capability routing.

## Non-Goals

- No visual workflow editor in the first version.
- No migration of existing A/B/C/D recruiting scenarios in the first version.
- No new provider configuration format outside `config/services.toml`.
- No direct imports of concrete provider classes from the workflow engine.
- No long-running blocked worker while waiting for human confirmation.
- No full long-term conversational memory layer in the first version; only reserve `conversation_id` and runtime fields for future memory integration.

## Source Of Truth

The implementation must follow these existing repository contracts:

- `docs/capability_integration.md`: service routing and task orchestration contract.
- `config/services.toml`: active service and skill registry.
- `app/core/router.py`: `ServiceRouter` capability resolution.
- `app/core/orchestrator.py`: current task persistence, audit event, SSE, and human gate patterns.
- `app/db/task_models.py`: task and agent event storage.
- `app/schemas/tasks.py`: allowed task statuses and event types.
- `app/api/main.py`: FastAPI app entrypoint and task endpoints.

## Architecture

The engine is split into four core objects:

```text
+--------------------------+
|    WorkflowDefinition    |  static JSON DSL contract, no runtime state
+--------------------------+
             |
             v
+--------------------------+
|   WorkflowRuntimeState   |  dynamic context snapshot, pointer, checkpoint
+--------------------------+
             |
             v
+--------------------------+
|    WorkflowTaskRunner    |  state machine controller and persistence boundary
+--------------------------+
             |
             v
+--------------------------+
|       StepExecutor       |  stateless atomic capability executor
+--------------------------+
             |
             v
+--------------------------+
|       ServiceRouter      |  configured capability routing
+--------------------------+
             |
             v
+--------------------------+
|         Provider         |  concrete search, LLM, OCR, structured output, etc.
+--------------------------+
```

The separation is intentional:

- `WorkflowDefinition` validates what the user wants to run.
- `WorkflowRuntimeState` records where the workflow is right now.
- `WorkflowTaskRunner` owns lifecycle, checkpointing, resume, status changes, and audit events.
- `StepExecutor` executes one atomic step and returns a structured result or structured exception.
- `ServiceRouter` remains the only path to configured capabilities.

## Component Contracts

### WorkflowDefinition

`WorkflowDefinition` is a pure Pydantic model for the static JSON DSL.

Responsibilities:

- Deserialize user JSON.
- Validate step shape and supported step types.
- Validate step IDs are unique.
- Validate each `output_key` is unique unless explicitly marked as overwrite.
- Scan template placeholders such as `{{ user_input }}` and `{{ search_results }}`.
- Reject workflows with unresolved static dependencies.
- Reject workflows with topology that requires a future output before it exists.
- Expose a deterministic normalized representation for persistence.

Core fields:

```python
class WorkflowDefinition(BaseModel):
    id: str
    name: str | None = None
    version: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepDefinition]
```

`inputs` declares initial context keys expected at run time. `steps` defines the chain.

### StepDefinition

`StepDefinition` describes one static DSL node.

Core fields:

```python
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
```

Validation rules:

- `search` requires `input` and `output_key`.
- `llm_prompt` requires `prompt` and `output_key`.
- `structured_extract` requires `input`, `schema`, and `output_key`.
- `save_artifact` requires `input` and `output_key`.
- `human_gate` requires `prompt`; `output_key` is optional.
- `max_retries` must be between 0 and 5 in the first version.
- `limit` must be between 1 and 50.
- `max_tokens` must be between 1 and 8192.

### WorkflowRuntimeState

`WorkflowRuntimeState` is a pure data snapshot. It maps directly to `TaskModel.frontend_state["json_workflow_runtime"]`.

Core fields:

```python
class WorkflowRuntimeState(BaseModel):
    workflow_id: str
    workflow: dict[str, Any]
    current_step_index: int = 0
    context: dict[str, Any] = Field(default_factory=dict)
    retry_state: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    human_decision: dict[str, Any] | None = None
```

Checkpoint JSON must include at least:

```json
{
  "workflow_id": "research_report",
  "workflow": {"id": "research_report", "steps": []},
  "current_step_index": 2,
  "context": {},
  "retry_state": {
    "step_id": "extract_entities",
    "retry_count": 1,
    "last_error": "field required: entities"
  },
  "artifacts": {},
  "conversation_id": "optional-conversation-id",
  "human_decision": null
}
```

Persistence rules:

- `context` must contain JSON-serializable Python primitives only after checkpoint normalization.
- Pydantic models must be converted with `model_dump(mode="json")`.
- Values that cannot be serialized by the standard JSON encoder must be converted with `default=str`.
- Secret values must not be stored in `context`, `artifacts`, `retry_state`, or audit events.

### StepExecutor

`StepExecutor` is stateless at the workflow level. It receives one `StepDefinition` plus the current `WorkflowRuntimeState`, executes that step, and returns a `StepResult` or raises a structured exception.

The executor must use `ServiceRouter`; it must not import concrete providers.

Enforced constructor contract:

```python
class StepExecutor:
    def __init__(self, router: ServiceRouter | None = None) -> None:
        # Hard constraint: no concrete provider import is allowed in this class.
        self.router = router or get_router()

    async def execute_step(
        self,
        step_def: StepDefinition,
        state: WorkflowRuntimeState,
    ) -> StepResult:
        handler = self._handlers[step_def.type]
        return await handler(step_def, state)
```

Capability routing rules:

- `search`: call `self.router.search(service_name).search(query, limit=limit)`.
- `llm_prompt`: call `self.router.llm(service_name).text(prompt, max_tokens=max_tokens)`.
- `structured_extract`: prefer `self.router.structured_output(service_name)` when usable; fallback to `self.router.llm(service_name).text()` plus Pydantic/JSON validation in the first version.
- `save_artifact`: write a rendered value into `state.artifacts` through the runner.
- `human_gate`: raise `HumanGateRequiredException`; do not call any provider.

Concrete provider classes such as `OpenRouterChatLLMProvider`, `BraveWebSearchProvider`, or `OutlinesStructuredOutputProvider` must not be imported by `StepExecutor`.

### StepResult

`StepResult` normalizes step output before the runner stores it.

```python
class StepResult(BaseModel):
    step_id: str
    output_key: str | None = None
    value: Any = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
```

The runner is responsible for writing `value` to `state.context[output_key]` when `output_key` is present.

### WorkflowTaskRunner

`WorkflowTaskRunner` is the state machine and persistence boundary.

Responsibilities:

- Create a `TaskModel` for a JSON workflow run.
- Initialize and checkpoint `WorkflowRuntimeState`.
- Emit audit events after each lifecycle transition.
- Execute steps in order.
- Persist after every successful step.
- Suspend safely at `human_gate`.
- Resume from a persisted checkpoint after human confirmation.
- Mark task `done`, `error`, or `awaiting_human`.

Core method contracts:

- `start(workflow_def, initial_context, conversation_id) -> task_id`
- `resume(task_id, decision, user_data) -> task_snapshot`

`start()` validates the definition, creates a task, stores the initial checkpoint, and starts execution. `resume()` loads `TaskModel.frontend_state["json_workflow_runtime"]`, records the human decision, and continues from the persisted pointer.

Main loop contract:

```python
while state.current_step_index < len(workflow.steps):
    step = workflow.steps[state.current_step_index]
    try:
        result = await executor.execute_step(step, state)
        if result.output_key:
            state.context[result.output_key] = normalize_context_value(result.value)
        state.artifacts.update(result.artifacts)
        state.current_step_index += 1
        await save_checkpoint_to_db(task_id, state, status="processing")
        await emit_event(task_id, "summary", step, result)
    except HumanGateRequiredException as exc:
        await save_checkpoint_to_db(task_id, state, status="awaiting_human", awaiting=exc.awaiting)
        await emit_event(task_id, "human_gate", step, exc.awaiting)
        return
    except WorkflowFatalException as exc:
        await save_checkpoint_to_db(task_id, state, status="error")
        await emit_event(task_id, "error", step, exc.safe_payload)
        return

await finalize_task(task_id, state, status="done")
```

## JSON DSL

Example workflow:

```json
{
  "id": "research_report",
  "name": "Research Report",
  "inputs": {
    "user_input": {"type": "string"}
  },
  "steps": [
    {
      "id": "search",
      "type": "search",
      "input": "{{ user_input }}",
      "limit": 5,
      "output_key": "search_results"
    },
    {
      "id": "summarize",
      "type": "llm_prompt",
      "prompt": "基于以下搜索结果生成摘要：\n{{ search_results }}",
      "max_tokens": 800,
      "output_key": "summary"
    },
    {
      "id": "extract_entities",
      "type": "structured_extract",
      "input": "{{ summary }}",
      "schema": {
        "type": "object",
        "properties": {
          "entities": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "type": {"type": "string"}
              },
              "required": ["name", "type"]
            }
          }
        },
        "required": ["entities"]
      },
      "max_retries": 2,
      "on_failure": "human_gate",
      "output_key": "entities"
    },
    {
      "id": "report",
      "type": "llm_prompt",
      "prompt": "根据摘要和实体生成报告。\n摘要：{{ summary }}\n实体：{{ entities }}",
      "max_tokens": 1200,
      "output_key": "final_report"
    }
  ]
}
```

## Template Rendering And Context Serialization

The engine must never use `str(dict)` for prompt rendering.

Internal `context` may contain:

- `str`
- `int`
- `float`
- `bool`
- `None`
- `dict`
- `list`
- Pydantic model instances before checkpoint normalization

Prompt rendering must call `render_value()` for every placeholder.

Rendering rules:

- `str`: inserted as-is.
- Pydantic model: `model_dump(mode="json")`, then JSON formatting.
- `dict`, `list`, `bool`, `None`, number: `json.dumps(value, ensure_ascii=False, indent=2, default=str)`.
- Unknown object: `json.dumps(value, ensure_ascii=False, indent=2, default=str)`.

Required helper behavior:

```python
def render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
```

This guarantees that `{{ entities }}` becomes valid JSON:

```json
{
  "entities": [
    {
      "name": "OpenAI",
      "type": "company"
    }
  ]
}
```

It must not become a Python literal:

```text
{'entities': [{'name': 'OpenAI', 'type': 'company'}], 'ok': True, 'missing': None}
```

## Self-Correction Loop

`structured_extract` supports autonomous retry when output fails schema validation.

`max_retries` means additional attempts after the first attempt. For `max_retries = 2`, total attempts are 3.

Retry context must not grow with all previous failures. It only includes:

- Original extraction input.
- Expected schema.
- Last failed output, truncated to a fixed maximum.
- Last validation error, truncated to a fixed maximum.
- Current retry index and max retries.

Default first-version truncation:

- `last_output`: 4000 characters.
- `validation_error`: 2000 characters.
- `schema`: 4000 characters after JSON formatting.

Standard retry prompt:

```text
你是一个数据修正助手。上一次你的输出未通过 Pydantic 校验。

【期待的 Schema】：
{schema_json}

【你上一次的错误输出】：
{truncated_last_output}

【校验失败原因】：
{truncated_validation_error}

请重新调整你的输出。只输出符合 Schema 的合法 JSON，不要输出解释、Markdown 或额外文本。
```

Retry event logging:

- Each failed attempt emits an `error` or `evidence` audit event with sanitized diagnostics.
- The retry prompt is not logged in full.
- The raw failed output is truncated before entering audit events.
- Secrets and raw private material are never added to retry diagnostics.

Retry terminal behavior:

- If validation succeeds, write the parsed structured value into `context[output_key]`.
- If retries are exhausted and `on_failure == "error"`, raise `WorkflowFatalException`.
- If retries are exhausted and `on_failure == "human_gate"`, raise `HumanGateRequiredException` with the last safe diagnostics as the draft.

## Human Gate Suspension And Resume

`human_gate` must use checkpoint/resume semantics. It must not hold a worker thread or async task while waiting for user input.

Suspension flow:

1. `StepExecutor` reaches a `human_gate` step or a step configured with `on_failure == "human_gate"`.
2. `StepExecutor` raises `HumanGateRequiredException`.
3. `WorkflowTaskRunner` writes `TaskModel.status = "awaiting_human"`.
4. `WorkflowTaskRunner` writes `TaskModel.awaiting`.
5. `WorkflowTaskRunner` writes `TaskModel.frontend_state["json_workflow_runtime"]`.
6. `WorkflowTaskRunner` emits a `human_gate` audit event.
7. `WorkflowTaskRunner` returns and releases the execution thread or coroutine.

Resume flow:

1. User calls `POST /tasks/{task_id}/confirm`.
2. Backend detects that the task contains `frontend_state["json_workflow_runtime"]`.
3. Backend stores the human decision in runtime state.
4. Backend advances past the human gate step when appropriate.
5. Backend starts a new runner execution from the persisted checkpoint.
6. Runner continues from `current_step_index`.

This differs from the current blocking `AgentRunner` pattern. The JSON workflow engine must be resumable from persisted state.

## API Contract

### POST /workflows/validate

Purpose: validate a JSON workflow definition without creating a task.

Request:

```json
{
  "workflow": {
    "id": "research_report",
    "steps": []
  }
}
```

Response on success:

```json
{
  "valid": true,
  "workflow_id": "research_report",
  "step_count": 4,
  "dependencies": {
    "declared_inputs": ["user_input"],
    "produced_outputs": ["search_results", "summary", "entities", "final_report"]
  }
}
```

Response on validation failure:

```json
{
  "valid": false,
  "errors": [
    {
      "path": "steps[2].input",
      "message": "Unresolved template variable: missing_summary"
    }
  ]
}
```

### POST /workflows/run

Purpose: validate and start a JSON workflow task.

Request:

```json
{
  "workflow": {
    "id": "research_report",
    "steps": []
  },
  "input": {
    "user_input": "研究 1929 年股市崩盘原因和政策应对"
  },
  "conversation_id": "optional-conversation-id"
}
```

Response:

```json
{
  "task_id": "task-id",
  "workflow_id": "research_report",
  "status": "processing"
}
```

### Existing Task APIs

The JSON workflow engine reuses:

- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/stream`
- `POST /tasks/{task_id}/confirm`
- `POST /tasks/{task_id}/cancel`
- `POST /tasks/{task_id}/retry`

If `POST /tasks/{task_id}/confirm` currently assumes only A/B/C/D tasks, it must be extended to route JSON workflow tasks through `WorkflowTaskRunner.resume()`.

## Persistence Contract

Runtime state is stored in:

```python
TaskModel.frontend_state["json_workflow_runtime"]
```

Task statuses:

- `processing`: workflow is actively running or ready to continue.
- `awaiting_human`: workflow is suspended at a human gate.
- `done`: workflow completed.
- `error`: workflow failed and cannot continue without retry.
- `cancelled`: workflow was cancelled by the user.

Final task result:

```python
TaskModel.result = {
    "workflow_id": state.workflow_id,
    "context": state.context,
    "artifacts": state.artifacts,
    "final_output": state.context.get(last_output_key),
}
```

The final output key is the last step's `output_key` when present.

## Event Contract

The engine emits existing allowed event types:

- `step_start`
- `tool_call`
- `evidence`
- `summary`
- `human_gate`
- `error`
- `cancelled`

No raw chain-of-thought is emitted.

Event payloads may include:

- Step ID.
- Step type.
- Rendered prompt preview with truncation.
- Search query preview.
- Result summary.
- Retry count.
- Validation error summary.
- Human gate prompt and draft.

Event payloads must not include:

- Secret values.
- Full API keys.
- Raw cookies.
- Internal credentials.
- Unbounded private document content.
- Raw LLM reasoning traces.

## Error Taxonomy

Use structured exceptions inside the engine:

- `WorkflowValidationException`: static DSL validation failure before task creation.
- `WorkflowFatalException`: unrecoverable runtime failure after retry and routing decisions.
- `HumanGateRequiredException`: controlled suspension requiring human input.
- `StepExecutionException`: provider or step-level failure that the runner may route to retry, human gate, or fatal error.

Expected behavior:

- Static DSL problems raise `WorkflowValidationException` before task creation.
- Runtime provider failures raise `StepExecutionException`, then runner converts them to retry, human gate, or fatal error depending on step config.
- Exhausted self-correction raises `WorkflowFatalException` or `HumanGateRequiredException`.
- Human gate raises `HumanGateRequiredException`.

## Security And Guardrails

- Do not store or return secret values.
- Do not allow DSL to execute arbitrary Python.
- Do not allow shell commands in the first version.
- Do not allow direct provider selection outside configured `ServiceRouter` names.
- Do not allow user-supplied import paths.
- Cap `max_retries`, `max_tokens`, `limit`, and rendered prompt size.
- Truncate diagnostic data before storing in audit events.
- Keep live external calls controlled by existing provider behavior and credentials.

## Testing Strategy

Create a new test file:

```text
tests/test_json_workflow_engine.py
```

Initial tests should cover:

1. `WorkflowDefinition` accepts a valid minimal JSON workflow.
2. `WorkflowDefinition` rejects duplicate step IDs.
3. `WorkflowDefinition` rejects unresolved placeholders.
4. `WorkflowDefinition` rejects a future dependency.
5. `render_value()` renders dict/list/None/bool as valid JSON.
6. `StepExecutor` uses `ServiceRouter.search()` for `search`.
7. `StepExecutor` uses `ServiceRouter.llm()` for `llm_prompt`.
8. `structured_extract` retries after invalid JSON.
9. `structured_extract` retry context includes only the last failure.
10. `structured_extract` moves to human gate after exhausted retries when configured.
11. `human_gate` writes checkpoint and returns without blocking.
12. `POST /workflows/validate` appears in OpenAPI.
13. `POST /workflows/run` appears in OpenAPI.
14. `POST /tasks/{task_id}/confirm` resumes a JSON workflow from checkpoint.
15. Completed JSON workflow writes `TaskModel.result`.

External API calls must be mocked in unit tests.

Recommended verification commands:

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
.venv/bin/python -m pytest tests/test_static_contracts.py -q
.venv/bin/python -c "from app.api.main import app; print(app.title)"
```

If `.venv` is unavailable, use the repository's active Python environment.

## Rollout Plan

Phase 1: Backend engine MVP

- Add DSL models.
- Add runtime state model.
- Add template rendering helpers.
- Add step executor.
- Add task runner with checkpoint/resume.
- Add `/workflows/validate` and `/workflows/run`.
- Add tests with mocked services.

Phase 2: Hardening

- Add provider timeout controls per step.
- Add richer validation error paths.
- Add retry diagnostics summary.
- Add task retry support for JSON workflows.
- Add metrics for step duration and retry count.

Phase 3: Productization

- Add frontend JSON editor.
- Add saved workflow registry.
- Add workflow versioning.
- Add memory provider integration.
- Add optional graph editor after backend contracts stabilize.

## Acceptance Criteria

The first implementation is complete when:

- A valid JSON workflow can be submitted to `/workflows/validate`.
- Invalid placeholder dependencies are rejected before task creation.
- A valid JSON workflow can be submitted to `/workflows/run`.
- The API returns a `task_id`.
- Task events stream through existing `GET /tasks/{task_id}/stream`.
- `search` and `llm_prompt` steps call `ServiceRouter`.
- `structured_extract` validates output and retries with bounded retry context.
- Non-string context values render into prompts as formatted JSON.
- `human_gate` checkpoints task state and releases execution.
- `POST /tasks/{task_id}/confirm` resumes the workflow from checkpoint.
- Successful completion writes `TaskModel.result`.
- Unit tests pass without live external API calls.
