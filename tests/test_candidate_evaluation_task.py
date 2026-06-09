from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.db.session import make_project_session_factory, project_session_factory
from app.models import JobCandidate
from scripts.seed_db import seed_project_mock_data


def test_scenario_c_candidate_evaluation_human_gate_updates_job_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'projects.sqlite3'}"
    monkeypatch.setenv("PROJECT_DATABASE_URL", database_url)
    monkeypatch.setenv("CANDIDATE_EVALUATION_DELAY_SECONDS", "0")
    project_session_factory.cache_clear()
    try:
        seed_project_mock_data(database_url)

        client = TestClient(app)
        response = client.post(
            "/scenarios/run",
            json={
                "scenario": "C",
                "input": "请评估候选人 Zhou Han 与 VLA 岗位的匹配度。",
                "frontend_state": {
                    "project_id": "project_2026_ai_team",
                    "candidate_id": "cand_zhou_han",
                    "job_id": "job_vla_algorithm",
                    "action": "candidate_evaluation",
                },
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]
        awaiting = _wait_for_status(client, task_id, "awaiting_human")

        events = awaiting["audit_events"]
        assert any(
            event["type"] == "step_start" and event["data"].get("message") == "正在提取候选人简历特征..."
            for event in events
        )
        assert any(
            event["type"] == "step_start"
            and event["data"].get("message") == "正在与【2026 AI 团队】岗位要求进行向量匹配..."
            for event in events
        )
        human_gate = next(
            event for event in events if event["type"] == "human_gate" and event["status"] == "awaiting_human"
        )
        assert "匹配度 92 分" in json.dumps(human_gate["data"], ensure_ascii=False)

        confirm_response = client.post(
            f"/tasks/{task_id}/confirm",
            json={"action": "approve", "data": {"draft": "批准评估结论"}},
        )
        assert confirm_response.status_code == 200

        done = _wait_for_status(client, task_id, "done")
        assert done["result"]["database_update"] == {
            "candidate_id": "cand_zhou_han",
            "job_id": "job_vla_algorithm",
            "match_score": 92,
            "pipeline_status": "pending_outreach",
        }

        session_factory = make_project_session_factory(database_url)
        with session_factory() as session:
            match = session.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == "job_vla_algorithm",
                    JobCandidate.candidate_id == "cand_zhou_han",
                )
            )

        assert match is not None
        assert match.match_score == 92
        assert match.pipeline_status == "pending_outreach"
    finally:
        project_session_factory.cache_clear()


def _wait_for_status(client: TestClient, task_id: str, expected: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    latest: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == expected:
            return latest
        time.sleep(0.05)
    pytest.fail(f"Task {task_id} did not reach {expected}; latest={latest}")
