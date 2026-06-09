from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.api.routers.projects import _utc_datetime
from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project, ProjectBase


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
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

    try:
        yield session_factory
    finally:
        engine.dispose()


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
            "pipelineStatus": "awaiting_human",
            "candidateCount": 2,
            "averageMatchScore": 85,
        },
        {
            "id": "job_robot_data_platform",
            "projectId": "project_2026_ai_team",
            "title": "机器人数据平台工程师",
            "headcount": 1,
            "status": "offer",
            "pipelineStatus": "done",
            "candidateCount": 1,
            "averageMatchScore": 85,
        },
    ]


def test_get_project_jobs_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/jobs?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    assert response.headers["x-has-more"] == "false"
    assert response.json() == [
        {
            "id": "job_robot_data_platform",
            "projectId": "project_2026_ai_team",
            "title": "机器人数据平台工程师",
            "headcount": 1,
            "status": "offer",
            "pipelineStatus": "done",
            "candidateCount": 1,
            "averageMatchScore": 85,
        }
    ]


def test_get_project_jobs_uses_bounded_queries(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                Job(
                    id=f"job_extra_{index}",
                    project_id="project_2026_ai_team",
                    title=f"Extra role {index}",
                    headcount=1,
                    status="sourcing",
                )
                for index in range(4)
            ]
        )
        session.commit()

    with session_factory() as session:
        bind = session.get_bind()

    select_statements: list[str] = []

    def count_selects(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(bind, "before_cursor_execute", count_selects)
    try:
        response = client.get("/projects/project_2026_ai_team/jobs")
    finally:
        event.remove(bind, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert len(response.json()) == 6
    assert len(select_statements) <= 5


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


def test_get_project_candidates_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "true"
    assert response.json() == [
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
        }
    ]


def test_get_project_candidates_marks_last_page_in_pagination_headers(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates?skip=2&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "false"
    assert [candidate["id"] for candidate in response.json()] == ["cand_wang_ke"]


def test_get_project_unique_candidates_deduplicates_candidates(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            JobCandidate(
                job_id="job_robot_data_platform",
                candidate_id="cand_lin_chen",
                match_score=88,
                pipeline_status="pending_outreach",
            )
        )
        session.commit()

    response = client.get("/projects/project_2026_ai_team/candidates/unique")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "cand_lin_chen",
            "name": "Alex Chen",
            "currentCompany": "Embodied AI Lab",
            "city": "深圳",
            "email": "alex.chen@example.com",
        },
        {
            "id": "cand_wang_ke",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
        },
        {
            "id": "cand_zhou_han",
            "name": "Zhou Han",
            "currentCompany": "Robot Foundation Team",
            "city": "上海",
            "email": "zhou.han@example.com",
        },
    ]


def test_get_project_unique_candidates_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates/unique?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "true"
    assert response.json() == [
        {
            "id": "cand_wang_ke",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
        }
    ]


def test_empty_project_lists_return_empty_arrays(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_empty",
                name="Empty project",
                status="active",
                created_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
            )
        )
        session.commit()

    assert client.get("/projects/project_empty/jobs").json() == []
    assert client.get("/projects/project_empty/candidates").json() == []
    assert client.get("/projects/project_empty/candidates/unique").json() == []


def test_project_created_at_naive_datetime_is_returned_as_utc(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_naive_time",
                name="Naive time project",
                status="active",
                created_at=datetime(2026, 6, 9, 12, 30),
            )
        )
        session.commit()

    response = client.get("/projects/project_naive_time")

    assert response.status_code == 200
    assert response.json()["createdAt"] == "2026-06-09T12:30:00Z"


def test_utc_datetime_converts_aware_datetime_to_utc() -> None:
    value = datetime(2026, 6, 9, 8, 30, tzinfo=timezone(timedelta(hours=8)))

    assert _utc_datetime(value) == datetime(2026, 6, 9, 0, 30, tzinfo=timezone.utc)


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
