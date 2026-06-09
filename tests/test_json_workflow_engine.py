import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
import app.core.orchestrator as orchestrator
from app.api.main import app
from app.core.orchestrator import SCENARIO_PLANS, get_meta
from app.core.workflow_dsl import WorkflowDefinition, WorkflowValidationException
from app.core.workflow_context import render_template, render_value
from app.core.workflow_executor import (
    HumanGateRequiredException,
    StepExecutor,
    WorkflowFatalException,
    WorkflowRuntimeState,
)
from app.core.workflow_runner import WorkflowTaskRunner


WORKFLOW_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "json_workflows"


def workflow_fixture(filename: str) -> dict:
    return json.loads((WORKFLOW_FIXTURE_DIR / filename).read_text(encoding="utf-8"))


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
                "output_type": "artifact",
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
    assert workflow.steps[0].output_type == "artifact"
    assert workflow.steps[1].output_type == "context"
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


def test_workflow_definition_rejects_search_context_output() -> None:
    payload = valid_workflow()
    payload["steps"][0]["output_type"] = "context"
    with pytest.raises(WorkflowValidationException, match="search step output_type must be artifact"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_definition_maps_legacy_output_storage_metadata_to_output_type() -> None:
    payload = valid_workflow()
    payload["steps"][0].pop("output_type")
    payload["steps"][0]["metadata"] = {"output_storage": "artifact"}
    workflow = WorkflowDefinition.model_validate(payload)
    assert workflow.steps[0].output_type == "artifact"


def test_workflow_definition_rejects_invalid_structured_extract_schema_type() -> None:
    payload = {
        "id": "bad_extract_schema",
        "inputs": {"source": {"type": "string"}},
        "steps": [
            {
                "id": "extract",
                "type": "structured_extract",
                "input": "{{ source }}",
                "schema": {"type": "object_bad"},
                "output_key": "entities",
            }
        ],
    }
    with pytest.raises(WorkflowValidationException, match="Unsupported schema type"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_definition_rejects_required_schema_field_not_declared_in_properties() -> None:
    payload = {
        "id": "bad_extract_schema",
        "inputs": {"source": {"type": "string"}},
        "steps": [
            {
                "id": "extract",
                "type": "structured_extract",
                "input": "{{ source }}",
                "schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {},
                },
                "output_key": "entities",
            }
        ],
    }
    with pytest.raises(WorkflowValidationException, match="required field 'name' must be declared in properties"):
        WorkflowDefinition.model_validate(payload)


class FakeSearchProvider:
    def __init__(self) -> None:
        self.calls = []
        self.results = None

    def search(self, query: str, limit: int = 10):
        self.calls.append({"query": query, "limit": limit})
        if self.results is not None:
            return self.results
        return [{"title": "Result", "snippet": query}]


class FakeLLMProvider:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or ["ok"])
        self.prompts = []

    def text(self, prompt: str, max_tokens: int = 256) -> str:
        self.prompts.append({"prompt": prompt, "max_tokens": max_tokens})
        if not self.outputs:
            raise AssertionError("Unexpected LLM call")
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


@pytest.fixture
def isolated_task_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{tmp_path / 'tasks.sqlite3'}")
    monkeypatch.setenv("WORKFLOW_ARTIFACT_DIR", str(tmp_path / "workflow_artifacts"))
    store = orchestrator.DBTaskStore()
    monkeypatch.setattr(orchestrator, "task_store", store)
    monkeypatch.setattr(api_main, "task_store", store)
    return store


def wait_for_task_status(client: TestClient, task_id: str, expected: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    latest: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == expected:
            return latest
        time.sleep(0.02)
    pytest.fail(f"Task {task_id} did not reach {expected}; latest={latest}")


def wait_for_runner_release(task_id: str, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with orchestrator._active_runners_lock:
            runner = orchestrator._active_runners.get(task_id)
        if runner is None or not runner.is_alive():
            return
        time.sleep(0.02)
    pytest.fail(f"Task {task_id} still holds an active runner while awaiting human confirmation")


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


def test_step_executor_suspends_llm_prompt_when_task_token_budget_is_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZHAOPING_TASK_TOKEN_BUDGET", "12")
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    state = WorkflowRuntimeState.from_definition(workflow, {"user_input": "robotics"})
    state.context["search_results"] = [{"title": "A"}]
    router = FakeRouter(llm_outputs=["summary"])

    with pytest.raises(HumanGateRequiredException) as exc:
        StepExecutor(router=router).execute_step(workflow.steps[1], state)

    assert exc.value.awaiting["agent"] == "json_workflow"
    assert exc.value.awaiting["draft"]["reason"] == "token_budget_exceeded"
    assert router.llm_provider.prompts == []


def test_step_executor_limits_llm_prompt_context_without_mutating_runtime_context() -> None:
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    state = WorkflowRuntimeState.from_definition(workflow, {"user_input": "robotics"})
    state.context["search_results"] = [
        {"title": f"Result {index}", "snippet": f"important-{index} " + ("x" * 1400)}
        for index in range(8)
    ]
    router = FakeRouter(llm_outputs=["summary"])

    StepExecutor(router=router).execute_step(workflow.steps[1], state)

    prompt = router.llm_provider.prompts[0]["prompt"]
    assert "important-0" in prompt
    assert "important-7" not in prompt
    assert len(prompt) < 4500
    assert state.context["search_results"][7]["snippet"].startswith("important-7")


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


def test_workflow_artifact_output_storage_keeps_large_payload_out_of_context(
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKFLOW_ARTIFACT_DIR", str(tmp_path / "workflow_artifacts"))
    tail_marker = "RAW_ARTIFACT_TAIL_SHOULD_NOT_BE_IN_SNAPSHOT"
    long_snippet = "raw-search-result " + ("x" * 6000) + tail_marker
    payload = {
        "id": "artifact_search_flow",
        "inputs": {"query": {"type": "string"}},
        "steps": [
            {
                "id": "raw_search",
                "type": "search",
                "input": "{{ query }}",
                "limit": 1,
                "output_key": "search_results",
                "metadata": {"output_storage": "artifact"},
            },
            {
                "id": "summarize_ref",
                "type": "llm_prompt",
                "prompt": "Summarize the artifact reference only: {{ search_results }}",
                "output_key": "summary",
            },
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    router = FakeRouter(llm_outputs=["summary"])
    router.search_provider.results = [{"title": "Huge Result", "snippet": long_snippet}]
    runner = WorkflowTaskRunner(router=router)

    task_id = runner.start(workflow, {"query": "robotics"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)
    snapshot = runner.snapshot(task_id)

    assert snapshot["status"] == "done"
    result = snapshot["result"]
    artifact_ref = result["context"]["search_results"]
    assert artifact_ref["type"] == "artifact_ref"
    assert artifact_ref["artifact_key"] in result["artifacts"]
    artifact_metadata = result["artifacts"][artifact_ref["artifact_key"]]
    artifact_path = Path(artifact_metadata["path"])
    assert artifact_path.exists()
    stored_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert stored_payload[0]["snippet"] == long_snippet
    assert artifact_metadata["size_chars"] > 6000

    serialized_snapshot = json.dumps(snapshot, ensure_ascii=False)
    assert tail_marker not in serialized_snapshot
    assert tail_marker in artifact_path.read_text(encoding="utf-8")
    assert "artifact_ref" in router.llm_provider.prompts[0]["prompt"]
    assert tail_marker not in router.llm_provider.prompts[0]["prompt"]


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


def test_legacy_scenario_human_gate_releases_runner_and_confirm_resumes(
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_id = "T"

    def plan_handler(ctx: dict) -> dict:
        ctx["data"]["draft"] = {"body": ctx["input"]}
        return {"draft": ctx["data"]["draft"]}

    def gate_handler(ctx: dict) -> dict:
        return {"prompt": "Approve draft?", "draft": ctx["data"]["draft"]}

    def finalize_handler(ctx: dict) -> dict:
        return {
            "draft": ctx["data"]["draft"],
            "human": ctx["human"],
        }

    monkeypatch.setitem(
        orchestrator.SCENARIO_PLANS,
        scenario_id,
        {
            "name_zh": "Test scenario",
            "input_hint": "input",
            "steps": [
                orchestrator.Step("orchestrator", "prepare", "Prepare draft", "compute", plan_handler),
                orchestrator.Step("human_expert", "review", "Wait for HR", "hitl", gate_handler),
                orchestrator.Step("report", "final", "Finalize", "finalize", finalize_handler),
            ],
        },
    )
    monkeypatch.setattr(orchestrator.AgentRunner, "STEP_DELAY_SECONDS", 0)
    client = TestClient(app)

    task = orchestrator.start_task(scenario_id, "candidate draft")
    awaiting = wait_for_task_status(client, task.task_id, "awaiting_human")

    assert awaiting["awaiting"]["draft"] == {"body": "candidate draft"}
    wait_for_runner_release(task.task_id)
    assert "legacy_scenario_runtime" in awaiting["frontend_state"]

    confirm_response = client.post(
        f"/tasks/{task.task_id}/confirm",
        json={"action": "approve", "data": {"draft": "approved with edits"}},
    )
    assert confirm_response.status_code == 200

    done = wait_for_task_status(client, task.task_id, "done")
    assert done["result"] == {
        "draft": {"body": "candidate draft"},
        "human": {"decision": "approve", "edits": "approved with edits"},
    }
    assert [step["label"] for step in done["steps_done"]] == ["prepare", "review", "final"]
    assert "legacy_scenario_runtime" not in done["frontend_state"]


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


def test_workflows_run_api_creates_task(isolated_task_store) -> None:
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


def test_workflows_run_api_returns_safe_payload_for_fatal_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class FatalRunner:
        def start(self, *args, **kwargs):
            raise WorkflowFatalException(
                "database password leaked in raw exception",
                {"message": "workflow failed safely", "code": "workflow_fatal"},
            )

    monkeypatch.setattr(api_main, "WorkflowTaskRunner", FatalRunner)
    client = TestClient(app)
    response = client.post(
        "/workflows/run",
        json={"workflow": valid_workflow(), "input": {"user_input": "robotics"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {"message": "workflow failed safely", "code": "workflow_fatal"}


def test_task_artifact_api_returns_registered_artifact_and_rejects_unsafe_paths(
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKFLOW_ARTIFACT_DIR", str(tmp_path / "workflow_artifacts"))
    workflow = WorkflowDefinition.model_validate(valid_workflow())
    runner = WorkflowTaskRunner(router=FakeRouter())
    task_id = runner.start(workflow, {"user_input": "robotics"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)

    snapshot = runner.snapshot(task_id)
    runtime = snapshot["frontend_state"]["json_workflow_runtime"]
    artifact_metadata = runtime["artifacts"][runtime["context"]["search_results"]["artifact_key"]]
    artifact_path = artifact_metadata["path"]

    client = TestClient(app)
    response = client.get(f"/tasks/{task_id}/artifacts", params={"path": artifact_path})
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["artifact_key"] == artifact_metadata["artifact_key"]
    assert body["mime_type"] == "application/json"
    assert body["content"][0]["snippet"] == "robotics"

    traversal_response = client.get(f"/tasks/{task_id}/artifacts", params={"path": "../../etc/passwd"})
    assert traversal_response.status_code == 400

    other_task_id = runner.start(workflow, {"user_input": "other"}, auto_run=False)
    other_response = client.get(f"/tasks/{other_task_id}/artifacts", params={"path": artifact_path})
    assert other_response.status_code == 403


def test_openapi_exposes_json_workflow_routes() -> None:
    schema = app.openapi()
    assert "/workflows/validate" in schema["paths"]
    assert "/workflows/run" in schema["paths"]
    assert "/tasks/{task_id}/artifacts" in schema["paths"]


def test_confirm_route_checks_json_workflow_before_legacy_confirm() -> None:
    source = Path("app/api/main.py").read_text(encoding="utf-8")
    confirm_start = source.index("def confirm_task")
    json_runtime_check = source.index("json_workflow_runtime", confirm_start)
    legacy_confirm = source.index("task_store.confirm", confirm_start)
    assert json_runtime_check < legacy_confirm


def test_task_event_bus_uses_asyncio_queue_without_threadpool_bridge() -> None:
    async def scenario() -> None:
        bus = orchestrator.TaskEventBus()
        queue = bus.subscribe("task_1")
        assert isinstance(queue, asyncio.Queue)
        bus.publish("task_1", {"id": 1, "type": "summary"})
        event = await asyncio.wait_for(queue.get(), timeout=0.1)
        assert event == {"id": 1, "type": "summary"}
        bus.unsubscribe("task_1", queue)

    asyncio.run(scenario())
    stream_source = Path("app/api/main.py").read_text(encoding="utf-8")
    stream_block = stream_source[
        stream_source.index("async def stream_task") : stream_source.index("@app.post(\"/tasks/{task_id}/cancel\")")
    ]
    assert "asyncio.to_thread" not in stream_block


def test_confirm_api_returns_safe_payload_for_json_workflow_fatal_exception(
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "fatal_confirm",
        "inputs": {"candidate": {"type": "string"}},
        "steps": [
            {
                "id": "hr_gate",
                "type": "human_gate",
                "prompt": "Review {{ candidate }}",
                "output_key": "hr_decision",
            }
        ],
    }
    runner = WorkflowTaskRunner()
    task_id = runner.start(WorkflowDefinition.model_validate(payload), {"candidate": "Lin Chen"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)

    class FatalResumeRunner:
        def resume(self, *args, **kwargs):
            raise WorkflowFatalException(
                "raw stack includes provider token",
                {"message": "resume failed safely", "code": "workflow_fatal"},
            )

    monkeypatch.setattr(api_main, "WorkflowTaskRunner", FatalResumeRunner)
    client = TestClient(app)
    response = client.post(f"/tasks/{task_id}/confirm", json={"action": "approve"})

    assert response.status_code == 400
    assert response.json()["detail"] == {"message": "resume failed safely", "code": "workflow_fatal"}


def test_recruiting_custom_pipeline_json_fixture_validates_runs_and_resumes(
    isolated_task_store,
) -> None:
    workflow_payload = workflow_fixture("advanced_ai_algorithm_recruiting.json")
    workflow = WorkflowDefinition.model_validate(workflow_payload)
    assert [step.type for step in workflow.steps] == [
        "search",
        "llm_prompt",
        "structured_extract",
        "human_gate",
        "save_artifact",
    ]

    client = TestClient(app)
    validate_response = client.post("/workflows/validate", json={"workflow": workflow_payload})
    assert validate_response.status_code == 200
    validate_body = validate_response.json()
    assert validate_body["valid"] is True
    assert validate_body["workflow_id"] == "advanced_ai_algorithm_recruiting"
    assert validate_body["step_count"] == 5

    run_response = client.post(
        "/workflows/run",
        json={
            "workflow": workflow_payload,
            "input": {"search_query": "GitHub VLA robot manipulation diffusion policy candidate"},
        },
    )
    assert run_response.status_code == 200
    task_id = run_response.json()["task_id"]

    candidate_profile = {
        "name": "Lin Chen",
        "current_company": "Intrinsic AI",
        "project_evidence": ["github.com/linchen/vla-robot-policy", "Mobile manipulation benchmark"],
        "core_capabilities": ["VLA policy learning", "robot manipulation", "large-scale evaluation"],
        "risks": ["No production deployment evidence yet"],
        "recommended_level": "strong_recommend",
    }
    router = FakeRouter(
        llm_outputs=[
            "Lin Chen has strong robotics project evidence and relevant VLA depth.",
            json.dumps(candidate_profile, ensure_ascii=False),
        ]
    )
    runner = WorkflowTaskRunner(router=router)
    runner.run_until_blocked_or_done(task_id)

    awaiting = client.get(f"/tasks/{task_id}").json()
    assert awaiting["status"] == "awaiting_human"
    assert awaiting["awaiting"]["json_workflow"] is True
    assert awaiting["frontend_state"]["json_workflow_runtime"]["current_step_index"] == 3
    assert "Lin Chen" in json.dumps(awaiting["awaiting"], ensure_ascii=False)
    assert "legacy_scenario_runtime" not in awaiting["frontend_state"]
    assert "project_candidate_evaluation_runtime" not in awaiting["frontend_state"]

    runtime = awaiting["frontend_state"]["json_workflow_runtime"]
    candidate_signal_ref = runtime["context"]["candidate_signals"]
    assert candidate_signal_ref["type"] == "artifact_ref"
    assert candidate_signal_ref["artifact_key"] in runtime["artifacts"]
    candidate_signal_artifact = runtime["artifacts"][candidate_signal_ref["artifact_key"]]
    candidate_signal_payload = json.loads(Path(candidate_signal_artifact["path"]).read_text(encoding="utf-8"))
    assert candidate_signal_payload[0]["snippet"] == "GitHub VLA robot manipulation diffusion policy candidate"
    assert runtime["context"]["project_review"].startswith("Lin Chen")
    assert runtime["context"]["candidate_profile"] == candidate_profile
    assert "hr_decision" not in runtime["context"]

    events = awaiting["audit_events"]
    event_pairs = {(event["type"], event["step_label"]) for event in events}
    for step in workflow.steps[:4]:
        assert ("step_start", step.id) in event_pairs
        assert ("tool_call", step.id) in event_pairs
    for step in workflow.steps[:3]:
        assert ("summary", step.id) in event_pairs
    assert ("human_gate", "hr_screen_gate") in event_pairs

    confirm_response = client.post(
        f"/tasks/{task_id}/confirm",
        json={"action": "approve", "data": {"note": "推进面谈"}},
    )
    assert confirm_response.status_code == 200
    done = wait_for_task_status(client, task_id, "done")

    result = done["result"]
    assert result["workflow_id"] == "advanced_ai_algorithm_recruiting"
    for key in [
        "candidate_signals",
        "project_review",
        "candidate_profile",
        "hr_decision",
        "candidate_artifact",
    ]:
        assert key in result["context"]
    assert result["context"]["hr_decision"]["decision"] == "approve"
    assert "candidate_artifact" in result["artifacts"]
    assert result["final_output"] == result["context"]["candidate_artifact"]
    assert "Lin Chen" in result["final_output"]

    done_pairs = {(event["type"], event["step_label"]) for event in done["audit_events"]}
    assert ("step_start", "candidate_summary_artifact") in done_pairs
    assert ("summary", "candidate_summary_artifact") in done_pairs

    assert set(SCENARIO_PLANS) == {"A", "B", "C", "D"}
    assert {scenario["id"] for scenario in get_meta()["scenarios"]} == {"A", "B", "C", "D"}


def test_json_workflow_human_gate_survives_store_restart_and_api_confirm_resumes(
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "long_running_hr_checkpoint",
        "inputs": {"candidate_summary": {"type": "string"}},
        "steps": [
            {
                "id": "candidate_search",
                "type": "search",
                "input": "{{ candidate_summary }}",
                "limit": 1,
                "output_type": "artifact",
                "output_key": "search_hits",
            },
            {
                "id": "hr_gate",
                "type": "human_gate",
                "prompt": "HR review: {{ search_hits }}",
                "output_key": "hr_decision",
            },
            {
                "id": "resume_after_gate",
                "type": "llm_prompt",
                "prompt": "Next interview action from {{ hr_decision }} and {{ search_hits }}",
                "output_key": "final_note",
            },
        ],
    }
    workflow = WorkflowDefinition.model_validate(payload)
    first_router = FakeRouter()
    runner = WorkflowTaskRunner(router=first_router)
    task_id = runner.start(workflow, {"candidate_summary": "robot VLA candidate"}, auto_run=False)
    runner.run_until_blocked_or_done(task_id)

    awaiting = isolated_task_store.snapshot(task_id)
    assert awaiting is not None
    assert awaiting["status"] == "awaiting_human"
    assert awaiting["frontend_state"]["json_workflow_runtime"]["current_step_index"] == 1
    assert awaiting["awaiting"]["workflow_id"] == "long_running_hr_checkpoint"
    assert awaiting["awaiting"]["json_workflow"] is True
    assert "legacy_scenario_runtime" not in awaiting["frontend_state"]
    assert "project_candidate_evaluation_runtime" not in awaiting["frontend_state"]

    restarted_store = orchestrator.DBTaskStore()
    monkeypatch.setattr(orchestrator, "task_store", restarted_store)
    monkeypatch.setattr(api_main, "task_store", restarted_store)
    after_restart = restarted_store.snapshot(task_id)
    assert after_restart is not None
    assert after_restart["status"] == "awaiting_human"
    assert after_restart["error"] is None
    assert after_restart["frontend_state"]["json_workflow_runtime"]["current_step_index"] == 1
    assert not any(
        event["type"] == "error" and event["data"].get("recovery") == "json_workflow_interrupted"
        for event in after_restart["audit_events"]
    )

    resume_router = FakeRouter(llm_outputs=["面谈推进：安排机器人项目深挖面。"])
    monkeypatch.setattr(api_main, "WorkflowTaskRunner", lambda: WorkflowTaskRunner(router=resume_router))
    client = TestClient(app)
    confirm_response = client.post(
        f"/tasks/{task_id}/confirm",
        json={"action": "approve", "data": {"note": "HR approved after delay"}},
    )
    assert confirm_response.status_code == 200
    done = wait_for_task_status(client, task_id, "done")
    assert done["result"]["final_output"] == "面谈推进：安排机器人项目深挖面。"
    assert done["result"]["context"]["hr_decision"]["decision"] == "approve"
    assert [step["label"] for step in done["steps_done"]].count("candidate_search") == 1
    assert first_router.search_provider.calls == [{"query": "robot VLA candidate", "limit": 1}]
    assert resume_router.search_provider.calls == []


def test_resume_and_jd_structured_extract_recover_dirty_json_and_type_errors(
    isolated_task_store,
) -> None:
    resume_payload = workflow_fixture("resume_structured_extract.json")
    resume_profile = {
        "name": "Zhou Han",
        "current_company": "Agility Robotics",
        "location": "Shenzhen / Seattle",
        "work_history": ["Agility Robotics - Robot Learning Engineer", "ByteDance AI Lab - Intern"],
        "education": ["CMU Robotics Institute MSc"],
        "skills": ["VLA", "diffusion policy", "PyTorch", "ROS2"],
        "robotics_experience": ["Mobile manipulation", "real robot data collection"],
        "llm_experience": ["VLM grounding", "instruction tuning"],
        "evidence": ["GitHub robot-policy repo", "RSS workshop paper"],
        "risks": ["Leadership scope unclear"],
        "recommended_level": "A",
    }
    resume_router = FakeRouter(
        llm_outputs=[
            "```json\n{\"name\":\"Zhou Han\",\"current_company\":\"Agility Robotics\"}\n```",
            json.dumps(
                {
                    **resume_profile,
                    "work_history": "Agility Robotics - Robot Learning Engineer",
                },
                ensure_ascii=False,
            ),
            json.dumps(resume_profile, ensure_ascii=False),
        ]
    )
    resume_runner = WorkflowTaskRunner(router=resume_router)
    resume_task_id = resume_runner.start(
        WorkflowDefinition.model_validate(resume_payload),
        {
            "resume_text": (
                "Zhou Han, CMU Robotics Institute MSc. Worked on VLA / diffusion policy "
                "for mobile manipulation. 中文项目：真实机器人数据采集、ROS2 部署、大模型指令跟随。"
            )
        },
        auto_run=False,
    )
    resume_runner.run_until_blocked_or_done(resume_task_id)
    resume_done = resume_runner.snapshot(resume_task_id)
    assert resume_done["status"] == "done"
    assert resume_done["result"]["context"]["resume_profile"] == resume_profile
    assert "```json" not in json.dumps(resume_done["result"]["context"]["resume_profile"], ensure_ascii=False)
    assert len(resume_router.llm_provider.prompts) == 3
    final_retry_prompt = resume_router.llm_provider.prompts[-1]["prompt"]
    assert "```json" not in final_retry_prompt
    assert "Agility Robotics - Robot Learning Engineer" in final_retry_prompt

    jd_payload = workflow_fixture("jd_structured_extract.json")
    jd_profile = {
        "role_name": "高级 AI 算法工程师 - 机器人 VLA",
        "must_have_skills": ["robot learning", "VLA/VLM", "PyTorch", "real robot evaluation"],
        "nice_to_have_skills": ["diffusion policy", "sim2real", "ROS2"],
        "responsibilities": ["构建机器人 VLA 策略", "设计项目证据评估标准"],
        "exclusion_signals": ["Only chatbot experience", "No embodied AI project evidence"],
        "target_companies": ["Physical Intelligence", "Intrinsic", "Covariant"],
        "interview_questions": ["如何验证 VLA 在真实机械臂上的泛化？"],
        "scoring_rubric": {"robotics_depth": 30, "llm_depth": 20, "evidence_quality": 30, "risk": 20},
    }
    jd_router = FakeRouter(
        llm_outputs=[
            "Here is the JSON:\n{\"role_name\":\"高级 AI 算法工程师 - 机器人 VLA\"}",
            json.dumps(
                {
                    **jd_profile,
                    "interview_questions": "如何验证 VLA 在真实机械臂上的泛化？",
                },
                ensure_ascii=False,
            ),
            json.dumps(jd_profile, ensure_ascii=False),
        ]
    )
    jd_runner = WorkflowTaskRunner(router=jd_router)
    jd_task_id = jd_runner.start(
        WorkflowDefinition.model_validate(jd_payload),
        {
            "jd_text": (
                "岗位职责：机器人 VLA 策略、真实机器人评测、候选人项目证据审核。"
                "必备：PyTorch、robot learning、VLM。加分：diffusion policy、sim2real。"
            )
        },
        auto_run=False,
    )
    jd_runner.run_until_blocked_or_done(jd_task_id)
    jd_done = jd_runner.snapshot(jd_task_id)
    assert jd_done["status"] == "done"
    assert jd_done["result"]["context"]["jd_profile"] == jd_profile
    assert isinstance(jd_done["result"]["context"]["jd_profile"]["interview_questions"], list)
    assert isinstance(jd_done["result"]["context"]["jd_profile"]["scoring_rubric"], dict)


def test_structured_extract_exhaustion_events_and_human_gate_payload_are_sanitized(
    isolated_task_store,
) -> None:
    resume_payload = workflow_fixture("resume_structured_extract.json")
    resume_payload["steps"][0]["max_retries"] = 1
    error_runner = WorkflowTaskRunner(router=FakeRouter(llm_outputs=["not-json", "{\"name\":\"Only Name\"}"]))
    error_task_id = error_runner.start(
        WorkflowDefinition.model_validate(resume_payload),
        {"resume_text": "复杂简历文本"},
        auto_run=False,
    )
    error_runner.run_until_blocked_or_done(error_task_id)
    error_snapshot = error_runner.snapshot(error_task_id)
    assert error_snapshot["status"] == "error"
    assert any(
        event["type"] == "error"
        and event["status"] == "error"
        and event["data"]["workflow_id"] == "resume_structured_extract"
        for event in error_snapshot["audit_events"]
    )

    jd_payload = workflow_fixture("jd_structured_extract.json")
    jd_payload["steps"][0]["max_retries"] = 1
    human_gate_router = FakeRouter(
        llm_outputs=[
            "OpenRouterChatLLMProvider raw debug: api_key=sk-live-secret-token email=lin@example.com",
            "still invalid token=ghp_1234567890abcdef",
        ]
    )
    human_gate_runner = WorkflowTaskRunner(router=human_gate_router)
    human_gate_task_id = human_gate_runner.start(
        WorkflowDefinition.model_validate(jd_payload),
        {"jd_text": "高级 AI 算法岗 JD 文本"},
        auto_run=False,
    )
    human_gate_runner.run_until_blocked_or_done(human_gate_task_id)
    human_gate_snapshot = human_gate_runner.snapshot(human_gate_task_id)
    assert human_gate_snapshot["status"] == "awaiting_human"
    assert human_gate_snapshot["awaiting"]["draft"]["step_id"] == "jd_profile_extract"

    retry_prompt_text = human_gate_router.llm_provider.prompts[1]["prompt"]
    human_gate_payload = json.dumps(
        {
            "awaiting": human_gate_snapshot["awaiting"],
            "events": human_gate_snapshot["audit_events"],
        },
        ensure_ascii=False,
    )
    combined = retry_prompt_text + human_gate_payload
    for forbidden in [
        "sk-live-secret-token",
        "OpenRouterChatLLMProvider",
        "lin@example.com",
        "ghp_1234567890abcdef",
    ]:
        assert forbidden not in combined
    assert "[redacted]" in combined
    assert "[provider-internal]" in combined
