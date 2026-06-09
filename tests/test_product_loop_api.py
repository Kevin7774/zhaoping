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


def test_outreach_draft_edit_send_and_history_loop(client: TestClient) -> None:
    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["draftId"].startswith("draft_")
    assert draft["backendGenerated"] is True
    assert draft["projectId"] == "project_2026_ai_team"
    assert draft["jobId"] == "job_vla_algorithm"
    assert draft["candidateId"] == "cand_lin_chen"
    assert draft["strategyTag"] == "场景叙事类"
    assert "量化派" in draft["subject"]
    assert "羊小咩" in draft["subject"]
    assert "Alex Chen" in draft["body"]
    assert "量化派" in draft["body"]
    assert "羊小咩" in draft["body"]
    assert "消费撮合决策" in draft["body"]
    assert "AI 应用公司" in draft["body"]

    patch_response = client.patch(
        f"/outreach/drafts/{draft['draftId']}",
        json={"subject": "更新后的主题", "body": "人工编辑后的正文"},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["subject"] == "更新后的主题"
    assert patch_response.json()["body"] == "人工编辑后的正文"

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft["draftId"], "decision": "approve", "simulate": True},
    )

    assert send_response.status_code == 200
    send_result = send_response.json()
    assert send_result["status"] == "simulated"
    assert send_result["deliveryMode"] == "simulated"
    assert send_result["historyId"].startswith("history_")
    assert send_result["draftId"] == draft["draftId"]
    assert send_result["strategyTag"] == "场景叙事类"

    history_response = client.get("/outreach/history?projectId=project_2026_ai_team")

    assert history_response.status_code == 200
    assert history_response.json()["items"] == [
        {
            "historyId": send_result["historyId"],
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
            "draftId": draft["draftId"],
            "segmentId": None,
            "email": "alex.chen@example.com",
            "strategyTag": "场景叙事类",
            "subject": "更新后的主题",
            "body": "人工编辑后的正文",
            "status": "simulated",
            "deliveryMode": "simulated",
            "providerStatus": "simulated",
            "createdAt": send_result["createdAt"],
        }
    ]


def test_outreach_draft_allows_hardcore_strategy_tag_for_kpi_grouping(client: TestClient) -> None:
    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
            "strategyTag": "硬核技术类",
        },
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["strategyTag"] == "硬核技术类"
    assert "硬核技术类" in draft["body"]

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft["draftId"], "decision": "approve", "simulate": True},
    )

    assert send_response.status_code == 200
    assert send_response.json()["strategyTag"] == "硬核技术类"


def test_outreach_send_requires_real_candidate_email(client: TestClient) -> None:
    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_no_email",
        },
    )

    assert draft_response.status_code == 200

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": True},
    )

    assert send_response.status_code == 409
    assert "email" in send_response.json()["detail"].lower()


def test_outreach_real_send_is_blocked_when_email_delivery_is_not_active(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    monkeypatch.setattr("app.api.routers.outreach._email_delivery_active", lambda: False)

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": False},
    )

    assert send_response.status_code == 503
    assert send_response.json()["detail"] == "email_delivery is not active; real send is disabled"


def test_segments_query_save_list_and_detail(client: TestClient) -> None:
    query_response = client.post(
        "/segments/query",
        json={
            "projectId": "project_2026_ai_team",
            "criteria": {"jobProfileId": "job_vla_algorithm", "minScore": 80, "hasEmail": "yes"},
        },
    )

    assert query_response.status_code == 200
    assert query_response.json()["total"] == 1
    assert query_response.json()["candidates"][0]["id"] == "cand_lin_chen"

    create_response = client.post(
        "/segments",
        json={
            "projectId": "project_2026_ai_team",
            "name": "VLA 高匹配可触达人群",
            "criteria": {"jobProfileId": "job_vla_algorithm", "minScore": 80, "hasEmail": "yes"},
        },
    )

    assert create_response.status_code == 200
    segment = create_response.json()
    assert segment["segmentId"].startswith("segment_")
    assert segment["candidateCount"] == 1
    assert segment["candidateIds"] == ["cand_lin_chen"]

    list_response = client.get("/segments?projectId=project_2026_ai_team")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["segmentId"] == segment["segmentId"]

    detail_response = client.get(f"/segments/{segment['segmentId']}")

    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "VLA 高匹配可触达人群"
    assert detail_response.json()["candidates"][0]["id"] == "cand_lin_chen"


def test_weekly_report_can_be_saved_and_reloaded_as_latest(client: TestClient) -> None:
    empty_latest = client.get("/projects/project_2026_ai_team/reports/latest")

    assert empty_latest.status_code == 404

    create_response = client.post(
        "/reports/weekly",
        json={
            "projectId": "project_2026_ai_team",
            "sourceTaskId": "task_weekly_1",
            "report": {
                "conclusion": "本周完成真实候选人初筛。",
                "keyProgress": ["完成 2 个岗位的候选人评估"],
                "topCandidates": ["Alex Chen"],
                "risks": ["邮件送达能力未完全接入"],
                "nextActions": ["安排人工确认"],
            },
        },
    )

    assert create_response.status_code == 200
    report = create_response.json()
    assert report["reportId"].startswith("report_")
    assert report["projectId"] == "project_2026_ai_team"
    assert report["content"]["conclusion"] == "本周完成真实候选人初筛。"

    latest_response = client.get("/projects/project_2026_ai_team/reports/latest")

    assert latest_response.status_code == 200
    assert latest_response.json()["reportId"] == report["reportId"]
    assert latest_response.json()["content"]["risks"] == ["邮件送达能力未完全接入"]

    detail_response = client.get(f"/reports/{report['reportId']}")

    assert detail_response.status_code == 200
    assert detail_response.json()["sourceTaskId"] == "task_weekly_1"


def test_jobs_match_falls_back_to_real_project_database_matches_when_provider_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEmbedding:
        def embed_texts(self, texts: list[str]):  # noqa: ANN201
            raise RuntimeError("embedding provider unavailable")

    class StubRouter:
        def embedding(self) -> FailingEmbedding:
            return FailingEmbedding()

    monkeypatch.setattr("app.api.main.get_router", lambda: StubRouter())

    response = client.post("/jobs/match", json={"query": "VLA / 具身智能算法工程师", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["source"] == "project_database_fallback"
    assert response.json()["provider_error"] == "embedding provider unavailable"
    assert response.json()["results"] == [
        {
            "candidate_id": "cand_lin_chen",
            "candidate_name": "Alex Chen",
            "job_id": "job_vla_algorithm",
            "job_title": "VLA / 具身智能算法工程师",
            "match_score": 92,
            "pipeline_status": "processing",
            "source": "project_database",
        },
        {
            "candidate_id": "cand_no_email",
            "candidate_name": "No Email",
            "job_id": "job_vla_algorithm",
            "job_title": "VLA / 具身智能算法工程师",
            "match_score": 83,
            "pipeline_status": "pending_outreach",
            "source": "project_database",
        },
    ]


def test_jobs_match_falls_back_to_real_project_database_matches_when_provider_raises_unexpected_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEmbedding:
        def embed_texts(self, texts: list[str]):  # noqa: ANN201
            raise ValueError("embedding provider internal error")

    class StubRouter:
        def embedding(self) -> FailingEmbedding:
            return FailingEmbedding()

    monkeypatch.setattr("app.api.main.get_router", lambda: StubRouter())

    response = client.post("/jobs/match", json={"query": "VLA / 具身智能算法工程师", "top_k": 1})

    assert response.status_code == 200
    assert response.json()["source"] == "project_database_fallback"
    assert response.json()["provider_error"] == "embedding provider internal error"
    assert response.json()["results"] == [
        {
            "candidate_id": "cand_lin_chen",
            "candidate_name": "Alex Chen",
            "job_id": "job_vla_algorithm",
            "job_title": "VLA / 具身智能算法工程师",
            "match_score": 92,
            "pipeline_status": "processing",
            "source": "project_database",
        }
    ]


def test_jobs_match_returns_503_when_provider_and_database_fallback_are_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEmbedding:
        def embed_texts(self, texts: list[str]):  # noqa: ANN201
            raise RuntimeError("embedding provider unavailable")

    class StubRouter:
        def embedding(self) -> FailingEmbedding:
            return FailingEmbedding()

    monkeypatch.setattr("app.api.main.get_router", lambda: StubRouter())

    response = client.post("/jobs/match", json={"query": "不存在的岗位", "top_k": 3})

    assert response.status_code == 503
    assert response.json()["detail"] == "embedding provider unavailable"


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
        )
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
            id="cand_no_email",
            name="No Email",
            current_company="Unknown Lab",
            city="上海",
            email=None,
        ),
    ]
    matches = [
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_lin_chen", match_score=92, pipeline_status="processing"),
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_no_email", match_score=83, pipeline_status="pending_outreach"),
    ]

    session.add(project)
    session.add_all(jobs)
    session.add_all(candidates)
    session.flush()
    session.add_all(matches)
    session.commit()
