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
