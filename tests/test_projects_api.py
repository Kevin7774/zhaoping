from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project, ProjectBase


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ProjectBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    with session_factory() as session:
        _seed_project(session)

    def override_project_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_project_session] = override_project_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_get_project_returns_base_info_and_stats(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team")

    assert response.status_code == 200
    assert response.json() == {
        "id": "project_2026_ai_team",
        "name": "2026 AI 团队招聘",
        "status": "active",
        "createdAt": "2026-06-09T00:00:00Z",
        "openJobs": 2,
        "totalCandidates": 3,
        "awaitingHuman": 1,
        "averageMatchScore": 85,
    }


def test_get_project_jobs_returns_pipeline_status_and_rollups(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/jobs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "job_vla_algorithm",
            "projectId": "project_2026_ai_team",
            "title": "VLA / 具身智能算法工程师",
            "headcount": 2,
            "status": "processing",
            "pipelineStatus": "processing",
            "candidateCount": 2,
            "averageMatchScore": 85,
        },
        {
            "id": "job_robot_data_platform",
            "projectId": "project_2026_ai_team",
            "title": "机器人数据平台工程师",
            "headcount": 1,
            "status": "offer",
            "pipelineStatus": "offer",
            "candidateCount": 1,
            "averageMatchScore": 85,
        },
    ]


def test_get_project_candidates_returns_joined_candidate_matches(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "cand_lin_chen",
            "jobCandidateId": 1,
            "jobId": "job_vla_algorithm",
            "jobTitle": "VLA / 具身智能算法工程师",
            "name": "Alex Chen",
            "currentCompany": "Embodied AI Lab",
            "city": "深圳",
            "email": "alex.chen@example.com",
            "matchScore": 92,
            "pipelineStatus": "processing",
        },
        {
            "id": "cand_zhou_han",
            "jobCandidateId": 2,
            "jobId": "job_vla_algorithm",
            "jobTitle": "VLA / 具身智能算法工程师",
            "name": "Zhou Han",
            "currentCompany": "Robot Foundation Team",
            "city": "上海",
            "email": "zhou.han@example.com",
            "matchScore": 78,
            "pipelineStatus": "awaiting_human",
        },
        {
            "id": "cand_wang_ke",
            "jobCandidateId": 3,
            "jobId": "job_robot_data_platform",
            "jobTitle": "机器人数据平台工程师",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
            "matchScore": 85,
            "pipelineStatus": "done",
        },
    ]


def test_unknown_project_returns_404(client: TestClient) -> None:
    response = client.get("/projects/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found: missing"


def _seed_project(session: Session) -> None:
    project = Project(
        id="project_2026_ai_team",
        name="2026 AI 团队招聘",
        status="active",
        created_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
    )
    jobs = [
        Job(
            id="job_vla_algorithm",
            project_id=project.id,
            title="VLA / 具身智能算法工程师",
            headcount=2,
            status="processing",
        ),
        Job(
            id="job_robot_data_platform",
            project_id=project.id,
            title="机器人数据平台工程师",
            headcount=1,
            status="offer",
        ),
    ]
    candidates = [
        Candidate(
            id="cand_lin_chen",
            name="Alex Chen",
            current_company="Embodied AI Lab",
            city="深圳",
            email="alex.chen@example.com",
        ),
        Candidate(
            id="cand_zhou_han",
            name="Zhou Han",
            current_company="Robot Foundation Team",
            city="上海",
            email="zhou.han@example.com",
        ),
        Candidate(
            id="cand_wang_ke",
            name="Wang Ke",
            current_company="Autonomous Driving Data",
            city="上海",
            email="wang.ke@example.com",
        ),
    ]
    matches = [
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_lin_chen", match_score=92, pipeline_status="processing"),
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_zhou_han", match_score=78, pipeline_status="awaiting_human"),
        JobCandidate(job_id="job_robot_data_platform", candidate_id="cand_wang_ke", match_score=85, pipeline_status="done"),
    ]

    session.add(project)
    session.add_all(jobs)
    session.add_all(candidates)
    session.flush()
    session.add_all(matches)
    session.commit()
