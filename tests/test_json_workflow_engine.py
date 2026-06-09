import json
from pathlib import Path

import pytest

from app.core.workflow_dsl import WorkflowDefinition, WorkflowValidationException
from app.core.workflow_context import render_template, render_value
from app.core.workflow_executor import (
    HumanGateRequiredException,
    StepExecutor,
    WorkflowRuntimeState,
)
from app.core.workflow_runner import WorkflowTaskRunner


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
