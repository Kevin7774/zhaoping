from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.api.main import ConfirmRequest
from app.core.orchestrator import TaskState


def test_confirm_request_accepts_action_data_payload() -> None:
    request = ConfirmRequest.model_validate(
        {
            "action": "approve",
            "data": {
                "draft": "Hi Alex, updated.",
            },
        }
    )

    assert request.decision == "approve"
    assert request.edits == "Hi Alex, updated."


def test_confirm_request_still_accepts_legacy_payload() -> None:
    request = ConfirmRequest.model_validate({"decision": "reject", "edits": "not a fit"})

    assert request.decision == "reject"
    assert request.edits == "not a fit"


def _awaiting_task(awaiting: dict) -> TaskState:
    return TaskState(
        task_id="task_lead_preview_guard",
        scenario_id="B",
        input="测试",
        status="awaiting_human",
        awaiting=awaiting,
    )


@pytest.fixture()
def confirm_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    confirmed: list[tuple[str, str]] = []

    def fake_confirm(task_id: str, decision: str, edits) -> bool:
        confirmed.append((task_id, decision))
        return True

    monkeypatch.setattr(api_main.task_store, "confirm", fake_confirm)
    monkeypatch.setattr(api_main, "resume_task_after_confirm", lambda task_id: {"task_id": task_id, "status": "processing"})
    client = TestClient(app=api_main.app)
    client.confirmed = confirmed  # type: ignore[attr-defined]
    return client


def test_confirm_approve_blocked_when_required_lead_preview_missing(
    monkeypatch: pytest.MonkeyPatch, confirm_client: TestClient
) -> None:
    task = _awaiting_task({"prompt": "确认线索", "requires_lead_preview": True})
    monkeypatch.setattr(api_main.task_store, "get", lambda task_id: task)

    response = confirm_client.post(
        "/tasks/task_lead_preview_guard/confirm",
        json={"decision": "approve"},
    )

    assert response.status_code == 409
    assert "lead_preview" in response.json()["detail"]
    assert confirm_client.confirmed == []  # type: ignore[attr-defined]


def test_confirm_edit_blocked_when_required_lead_preview_missing(
    monkeypatch: pytest.MonkeyPatch, confirm_client: TestClient
) -> None:
    task = _awaiting_task({"prompt": "确认线索", "requires_lead_preview": True, "lead_preview": None})
    monkeypatch.setattr(api_main.task_store, "get", lambda task_id: task)

    response = confirm_client.post(
        "/tasks/task_lead_preview_guard/confirm",
        json={"decision": "edit", "edits": "调整目标公司"},
    )

    assert response.status_code == 409
    assert confirm_client.confirmed == []  # type: ignore[attr-defined]


def test_confirm_reject_allowed_when_required_lead_preview_missing(
    monkeypatch: pytest.MonkeyPatch, confirm_client: TestClient
) -> None:
    task = _awaiting_task({"prompt": "确认线索", "requires_lead_preview": True})
    monkeypatch.setattr(api_main.task_store, "get", lambda task_id: task)

    response = confirm_client.post(
        "/tasks/task_lead_preview_guard/confirm",
        json={"decision": "reject", "edits": "线索不可信"},
    )

    assert response.status_code == 200
    assert confirm_client.confirmed == [("task_lead_preview_guard", "reject")]  # type: ignore[attr-defined]


def test_confirm_approve_allowed_when_lead_preview_present(
    monkeypatch: pytest.MonkeyPatch, confirm_client: TestClient
) -> None:
    task = _awaiting_task(
        {
            "prompt": "确认线索",
            "requires_lead_preview": True,
            "lead_preview": {"total_count": 2, "omitted_count": 0, "leads": [{"name": "张三"}, {"name": "李四"}]},
        }
    )
    monkeypatch.setattr(api_main.task_store, "get", lambda task_id: task)

    response = confirm_client.post(
        "/tasks/task_lead_preview_guard/confirm",
        json={"decision": "approve"},
    )

    assert response.status_code == 200
    assert confirm_client.confirmed == [("task_lead_preview_guard", "approve")]  # type: ignore[attr-defined]
