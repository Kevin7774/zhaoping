from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.db.session import make_project_session_factory, project_session_factory
from app.models import Candidate, Job, JobCandidate
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


def test_candidate_evaluation_scores_against_job_scoring_rubric(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'projects.sqlite3'}"
    monkeypatch.setenv("PROJECT_DATABASE_URL", database_url)
    monkeypatch.setenv("CANDIDATE_EVALUATION_DELAY_SECONDS", "0")
    project_session_factory.cache_clear()
    try:
        seed_project_mock_data(database_url)
        session_factory = make_project_session_factory(database_url)
        with session_factory() as session:
            session.add(
                Job(
                    id="job_fde_eval",
                    project_id="project_2026_ai_team",
                    title="AI Native FDE / Agentic Builder",
                    headcount=1,
                    status="sourcing",
                    must_have_skills=["全栈开发", "Agentic workflow"],
                    scoring_rubric={
                        "完整业务工程闭环（问题定义/上线/指标复盘）": 3,
                        "业务抽象能力（订单/支付/风控）": 2,
                    },
                    rationale={
                        "must_have_signals": ["AI coding"],
                        "risk_signals": ["只会写 prompt"],
                    },
                )
            )
            session.add(
                Candidate(
                    id="cand_fde_builder",
                    name="Fde Builder",
                    title="全栈工程师",
                    skills=["全栈开发", "Agentic workflow", "AI coding"],
                    evidence=["主导订单支付风控系统上线", "问题定义到指标复盘全流程"],
                )
            )
            session.flush()
            session.add(
                JobCandidate(
                    job_id="job_fde_eval",
                    candidate_id="cand_fde_builder",
                    match_score=0,
                    pipeline_status="sourced",
                )
            )
            session.commit()

        client = TestClient(app)
        response = client.post(
            "/scenarios/run",
            json={
                "scenario": "C",
                "input": "请评估候选人 Fde Builder 与 AI Native FDE 岗位的匹配度。",
                "frontend_state": {
                    "project_id": "project_2026_ai_team",
                    "candidate_id": "cand_fde_builder",
                    "job_id": "job_fde_eval",
                    "action": "candidate_evaluation",
                },
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]
        awaiting = _wait_for_status(client, task_id, "awaiting_human")

        gate_payload = json.dumps(
            next(
                event
                for event in awaiting["audit_events"]
                if event["type"] == "human_gate" and event["status"] == "awaiting_human"
            )["data"],
            ensure_ascii=False,
        )
        assert "匹配度 86 分" in gate_payload
        assert "评分维度" in gate_payload
        assert "92" not in gate_payload

        confirm_response = client.post(
            f"/tasks/{task_id}/confirm",
            json={"action": "approve", "data": {"draft": "批准评估结论"}},
        )
        assert confirm_response.status_code == 200

        done = _wait_for_status(client, task_id, "done")
        assert done["result"]["database_update"]["match_score"] == 86

        with session_factory() as session:
            match = session.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == "job_fde_eval",
                    JobCandidate.candidate_id == "cand_fde_builder",
                )
            )

        assert match is not None
        assert match.match_score == 86
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
