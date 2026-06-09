from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.api.main as api_main
import app.core.orchestrator as orchestrator
from app.api.main import app
from app.db.session import get_project_session, make_project_session_factory
from app.models import Candidate, Job, JobCandidate, Project


@pytest.fixture()
def session_factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    database_url = f"sqlite:///{tmp_path / 'projects.sqlite3'}"
    factory = make_project_session_factory(database_url)
    with factory() as session:
        session.add(Project(id="project_2026_ai_team", name="2026 AI 团队招聘", status="active"))
        session.add(
            Job(
                id="job_vla_algorithm",
                project_id="project_2026_ai_team",
                title="VLA / 具身智能算法工程师",
                headcount=2,
                status="sourcing",
            )
        )
        session.add(Candidate(id="cand_existing", name="Existing Lead", current_company="Existing Robotics", city="上海"))
        session.add(
            JobCandidate(
                project_id="project_2026_ai_team",
                job_id="job_vla_algorithm",
                candidate_id="cand_existing",
                match_score=80,
                pipeline_status="processing",
            )
        )
        session.commit()
    yield factory


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_project_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_project_session] = override_project_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def isolated_task_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{tmp_path / 'tasks.sqlite3'}")
    store = orchestrator.DBTaskStore()
    monkeypatch.setattr(orchestrator, "task_store", store)
    monkeypatch.setattr(api_main, "task_store", store)
    return store


def test_candidate_search_schedule_api_crud(client: TestClient) -> None:
    response = client.put(
        "/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule",
        json={"enabled": True, "intervalMinutes": 120},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["intervalMinutes"] == 120
    assert response.json()["projectId"] == "project_2026_ai_team"
    assert response.json()["jobId"] == "job_vla_algorithm"

    schedules = client.get("/projects/project_2026_ai_team/candidate-search-schedules")
    assert schedules.status_code == 200
    assert schedules.json()["items"][0]["enabled"] is True


def test_candidate_search_scheduler_starts_due_b_task_and_ingests_leads(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.candidate_search_scheduler import CandidateSearchScheduler
    from app.models import CandidateSearchSchedule

    monkeypatch.setattr(orchestrator.AgentRunner, "STEP_DELAY_SECONDS", 0)
    monkeypatch.setattr(orchestrator, "_source_intelligence_with_audit", fake_source_intelligence)
    monkeypatch.setattr(orchestrator, "project_session_factory", lambda: session_factory)

    before = client.get("/projects/project_2026_ai_team/candidates")
    assert before.headers["x-total-count"] == "1"

    client.put(
        "/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule",
        json={"enabled": True, "intervalMinutes": 60},
    )
    with session_factory() as session:
        schedule = session.scalar(select(CandidateSearchSchedule))
        assert schedule is not None
        schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    scheduler = CandidateSearchScheduler(session_factory=session_factory, poll_interval_seconds=0.1)
    launched = scheduler.run_due_once(now=datetime.now(timezone.utc))

    assert launched == 1
    with session_factory() as session:
        schedule = session.scalar(select(CandidateSearchSchedule))
        assert schedule is not None
        assert schedule.last_task_id
        task_id = schedule.last_task_id
        assert schedule.next_run_at is not None
        assert schedule.next_run_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    done = wait_for_status(client, task_id, "done")
    ingestion = done["result"]["lead_ingestion"]
    assert ingestion["found"] == 2
    assert ingestion["inserted_candidates"] == 2
    assert ingestion["linked_job_candidates"] == 2

    after = client.get("/projects/project_2026_ai_team/candidates")
    assert after.headers["x-total-count"] == "3"

    launched_again = scheduler.run_due_once(now=datetime.now(timezone.utc))
    assert launched_again == 0


def test_disabled_candidate_search_schedule_does_not_start_task(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
) -> None:
    from app.core.candidate_search_scheduler import CandidateSearchScheduler
    from app.models import CandidateSearchSchedule

    client.put(
        "/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule",
        json={"enabled": False, "intervalMinutes": 60},
    )
    with session_factory() as session:
        schedule = session.scalar(select(CandidateSearchSchedule))
        assert schedule is not None
        schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    scheduler = CandidateSearchScheduler(session_factory=session_factory, poll_interval_seconds=0.1)
    assert scheduler.run_due_once(now=datetime.now(timezone.utc)) == 0


def fake_source_intelligence(*args, **kwargs) -> dict:  # noqa: ANN002, ANN003
    return {
        "query": "robotics VLA",
        "推荐信源": [],
        "证据记录": [],
        "实时检索": {
            "services": ["github_repositories"],
            "results": [
                {
                    "source_key": "github_repositories",
                    "source_name": "GitHub",
                    "title": "robot-vla",
                    "url": "https://github.com/alicewang/robot-vla",
                    "snippet": "Alice Wang maintains robot-vla with diffusion policy examples.",
                    "owner_login": "alicewang",
                    "owner_type": "User",
                    "company": "Open Robotics",
                    "topics": ["robotics", "VLA"],
                    "rank": 1,
                },
                {
                    "source_key": "github_repositories",
                    "source_name": "GitHub",
                    "title": "embodied-agent-stack",
                    "url": "https://github.com/bobli/embodied-agent-stack",
                    "snippet": "Bob Li builds embodied agent infrastructure.",
                    "owner_login": "bobli",
                    "owner_type": "User",
                    "company": "Robot Lab",
                    "topics": ["embodied-ai", "agents"],
                    "rank": 2,
                },
            ],
            "errors": [],
            "result_count": 2,
        },
        "检索说明": "test",
    }


def wait_for_status(client: TestClient, task_id: str, expected: str, timeout: float = 3.0) -> dict:
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
