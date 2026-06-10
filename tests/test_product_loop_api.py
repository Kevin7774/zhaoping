from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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


def _auth_headers(client: TestClient, email: str = "recruiter@hanno.ai") -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "name": "Recruiter"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def test_company_email_login_returns_current_user_and_org(client: TestClient) -> None:
    login_response = client.post("/auth/login", json={"email": "Recruiter@Hanno.AI", "name": "Recruiter"})

    assert login_response.status_code == 200
    login = login_response.json()
    assert login["tokenType"] == "bearer"
    assert login["user"]["email"] == "recruiter@hanno.ai"
    assert login["user"]["orgId"] == login["org"]["orgId"]
    assert login["org"]["domain"] == "hanno.ai"

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {login['accessToken']}"})

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "recruiter@hanno.ai"
    assert me_response.json()["org"]["domain"] == "hanno.ai"


def test_company_email_login_rejects_public_email_domains(client: TestClient) -> None:
    response = client.post("/auth/login", json={"email": "recruiter@gmail.com"})

    assert response.status_code == 422
    assert "company email" in response.json()["detail"].lower()


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
    assert "真机部署" in draft["subject"]
    assert "Alex Chen" in draft["body"]
    assert "真机部署" in draft["body"]
    assert "技术切磋" in draft["body"]
    assert "面试" not in draft["body"]
    assert "招聘团队" not in draft["body"]
    assert "希望这封邮件没有打扰到您" not in draft["body"]
    assert "项目：" not in draft["body"]

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
            "senderEmail": None,
            "sentByUserId": None,
            "strategyTag": "场景叙事类",
            "subject": "更新后的主题",
            "body": "人工编辑后的正文",
            "status": "simulated",
            "deliveryMode": "simulated",
            "providerStatus": "simulated",
            "createdAt": send_result["createdAt"],
        }
    ]


def test_outreach_records_logged_in_sender_and_user_ids(client: TestClient) -> None:
    headers = _auth_headers(client)
    draft_response = client.post(
        "/outreach/draft",
        headers=headers,
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["createdByUserId"]

    send_response = client.post(
        "/outreach/send",
        headers=headers,
        json={"draftId": draft["draftId"], "decision": "approve", "simulate": True},
    )

    assert send_response.status_code == 200
    history = send_response.json()
    assert history["senderEmail"] == "recruiter@hanno.ai"
    assert history["sentByUserId"] == draft["createdByUserId"]


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


def test_outreach_draft_rejects_llm_body_when_it_contains_recruiting_redlines(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlm:
        def text(self, prompt: str, max_tokens: int = 900) -> str:
            return (
                "看到你在真机部署项目里的数据闭环，我觉得很有意思。\n\n"
                "我们招聘团队希望约一次面试，聊聊你是否愿意加入。"
                "这段话故意超过八十个字符，用来证明后端会因为触达红线丢弃 LLM 正文。"
            )

    class FakeRouter:
        def llm(self) -> FakeLlm:
            return FakeLlm()

    monkeypatch.setattr("app.api.routers.outreach.load_system_prompt", lambda name: "system prompt")
    monkeypatch.setattr("app.api.routers.outreach.get_router", lambda: FakeRouter())

    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )

    assert draft_response.status_code == 200
    body = draft_response.json()["body"]
    assert "技术切磋" in body
    assert "面试" not in body
    assert "招聘团队" not in body
    assert "希望这封邮件没有打扰到您" not in body


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


def test_outreach_send_hard_blocks_pending_candidate_direct_api_bypass(
    client: TestClient,
    session_factory: sessionmaker[Session],
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
    assert draft_response.status_code == 200
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "pending_compliance_review"
        session.commit()
    monkeypatch.setattr("app.api.routers.outreach._email_delivery_active", lambda: True)

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": False},
    )

    assert send_response.status_code == 403
    detail = send_response.json()["detail"]
    assert "compliance" in detail.lower()
    assert "secret" not in detail.lower()
    assert "password" not in detail.lower()


def test_outreach_send_records_blocked_simulation_for_pending_candidate(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    assert draft_response.status_code == 200
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "pending_compliance_review"
        session.commit()

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": True},
    )

    assert send_response.status_code == 200
    payload = send_response.json()
    assert payload["status"] == "blocked_simulation"
    assert payload["deliveryMode"] == "simulated"
    assert payload["providerStatus"] == "blocked_by_compliance:pending_compliance_review"


def test_outreach_send_hard_blocks_rejected_candidate_direct_api_bypass(
    client: TestClient,
    session_factory: sessionmaker[Session],
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
    assert draft_response.status_code == 200
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "rejected"
        session.commit()
    monkeypatch.setattr("app.api.routers.outreach._email_delivery_active", lambda: True)

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": False},
    )

    assert send_response.status_code == 403
    assert "rejected" in send_response.json()["detail"].lower()

    simulated_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": True},
    )
    assert simulated_response.status_code == 200
    assert simulated_response.json()["status"] == "blocked_simulation"
    assert simulated_response.json()["providerStatus"] == "blocked_by_compliance:rejected"


def test_outreach_blocks_compliance_pending_candidate_until_hr_approval(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "pending_compliance_review"
        session.commit()

    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )

    assert draft_response.status_code == 409
    assert "compliance" in draft_response.json()["detail"].lower()

    candidates_before = client.get("/projects/project_2026_ai_team/candidates").json()
    job_candidate_id = candidates_before[0]["jobCandidateId"]

    review_response = client.post(
        f"/projects/project_2026_ai_team/candidates/{job_candidate_id}/compliance-review",
        json={"decision": "approve"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["pipelineStatus"] == "pending_outreach"

    draft_after_review = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    assert draft_after_review.status_code == 200


def test_compliance_review_can_reject_candidate_contact_source(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "pending_compliance_review"
        session.commit()

    candidates_before = client.get("/projects/project_2026_ai_team/candidates").json()
    job_candidate_id = candidates_before[0]["jobCandidateId"]

    review_response = client.post(
        f"/projects/project_2026_ai_team/candidates/{job_candidate_id}/compliance-review",
        json={"decision": "reject"},
    )

    assert review_response.status_code == 200
    assert review_response.json()["pipelineStatus"] == "rejected"


def test_compliance_review_can_approve_rejected_candidate_contact_source(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == "cand_lin_chen",
            )
        )
        assert link is not None
        link.pipeline_status = "rejected"
        session.commit()

    candidates_before = client.get("/projects/project_2026_ai_team/candidates").json()
    job_candidate_id = candidates_before[0]["jobCandidateId"]

    review_response = client.post(
        f"/projects/project_2026_ai_team/candidates/{job_candidate_id}/compliance-review",
        json={"decision": "approve"},
    )

    assert review_response.status_code == 200
    assert review_response.json()["pipelineStatus"] == "pending_outreach"


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


def test_outreach_real_send_uses_email_delivery_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}

    class FakeEmailDelivery:
        def send(
            self,
            *,
            to: str,
            subject: str,
            text_body: str,
            html_body: str | None = None,
            sender_email: str | None = None,
            approved: bool = False,
        ) -> dict[str, object]:
            sent.update(
                {
                    "to": to,
                    "subject": subject,
                    "text_body": text_body,
                    "html_body": html_body,
                    "sender_email": sender_email,
                    "approved": approved,
                }
            )
            return {"status": "sent", "provider": "mailtrap_smtp_email", "message_id": "mailtrap-msg-1"}

    class FakeRouter:
        def email_delivery(self) -> FakeEmailDelivery:
            return FakeEmailDelivery()

    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    monkeypatch.setattr("app.api.routers.outreach._email_delivery_active", lambda: True)
    monkeypatch.setattr("app.api.routers.outreach.get_router", lambda: FakeRouter())

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": False},
    )

    assert send_response.status_code == 200
    payload = send_response.json()
    assert payload["status"] == "sent"
    assert payload["deliveryMode"] == "real"
    assert payload["providerStatus"] == "mailtrap_smtp_email:sent"
    assert sent["to"] == "alex.chen@example.com"
    assert sent["approved"] is True
    assert sent["subject"] == draft_response.json()["subject"]
    assert sent["text_body"] == draft_response.json()["body"]


def test_outreach_real_send_uses_logged_in_email_as_sender(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth_headers(client, "talent.partner@hanno.ai")
    sent: dict[str, object] = {}

    class FakeEmailDelivery:
        def send(
            self,
            *,
            to: str,
            subject: str,
            text_body: str,
            html_body: str | None = None,
            sender_email: str | None = None,
            approved: bool = False,
        ) -> dict[str, object]:
            sent.update({"sender_email": sender_email, "approved": approved, "to": to})
            return {"status": "sent", "provider": "mailtrap_smtp_email", "message_id": "mailtrap-msg-2"}

    class FakeRouter:
        def email_delivery(self) -> FakeEmailDelivery:
            return FakeEmailDelivery()

    draft_response = client.post(
        "/outreach/draft",
        headers=headers,
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    monkeypatch.setattr("app.api.routers.outreach._email_delivery_active", lambda: True)
    monkeypatch.setattr("app.api.routers.outreach.get_router", lambda: FakeRouter())

    send_response = client.post(
        "/outreach/send",
        headers=headers,
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": False},
    )

    assert send_response.status_code == 200
    assert sent["sender_email"] == "talent.partner@hanno.ai"
    assert send_response.json()["senderEmail"] == "talent.partner@hanno.ai"


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


def test_segments_query_filters_source_platform_and_outreach_status(client: TestClient) -> None:
    source_response = client.post(
        "/segments/query",
        json={
            "projectId": "project_2026_ai_team",
            "criteria": {"sourcePlatform": "GitHub", "outreachStatus": "not_sent"},
        },
    )

    assert source_response.status_code == 200
    assert source_response.json()["total"] == 1
    assert source_response.json()["candidates"][0]["id"] == "cand_lin_chen"
    assert source_response.json()["candidates"][0]["outreachStatus"] == "not_sent"

    draft_response = client.post(
        "/outreach/draft",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "candidateId": "cand_lin_chen",
        },
    )
    assert draft_response.status_code == 200

    drafted_response = client.post(
        "/segments/query",
        json={
            "projectId": "project_2026_ai_team",
            "criteria": {"sourcePlatform": "GitHub", "outreachStatus": "drafted"},
        },
    )
    assert drafted_response.status_code == 200
    assert drafted_response.json()["total"] == 1
    assert drafted_response.json()["candidates"][0]["outreachStatus"] == "drafted"

    sent_response_before = client.post(
        "/segments/query",
        json={
            "projectId": "project_2026_ai_team",
            "criteria": {"sourcePlatform": "GitHub", "outreachStatus": "sent"},
        },
    )
    assert sent_response_before.status_code == 200
    assert sent_response_before.json()["total"] == 0

    send_response = client.post(
        "/outreach/send",
        json={"draftId": draft_response.json()["draftId"], "decision": "approve", "simulate": True},
    )
    assert send_response.status_code == 200

    sent_response_after = client.post(
        "/segments/query",
        json={
            "projectId": "project_2026_ai_team",
            "criteria": {"sourcePlatform": "GitHub", "outreachStatus": "sent"},
        },
    )
    assert sent_response_after.status_code == 200
    assert sent_response_after.json()["total"] == 1
    assert sent_response_after.json()["candidates"][0]["outreachStatus"] == "sent"


def test_weekly_report_can_be_saved_and_reloaded_as_latest(client: TestClient) -> None:
    empty_latest = client.get("/projects/project_2026_ai_team/reports/latest")

    assert empty_latest.status_code == 204
    assert not empty_latest.content

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


def test_jobs_match_returns_real_project_database_matches_without_warming_vector_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedEmbedding:
        def embed_texts(self, texts: list[str]):  # noqa: ANN201
            raise AssertionError("embedding provider should not be called for existing project jobs")

    class StubRouter:
        def embedding(self) -> UnexpectedEmbedding:
            return UnexpectedEmbedding()

    monkeypatch.setattr("app.api.main.get_router", lambda: StubRouter())

    response = client.post("/jobs/match", json={"query": "VLA / 具身智能算法工程师", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["source"] == "project_database"
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


def test_jobs_match_applies_top_k_to_real_project_database_matches(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedEmbedding:
        def embed_texts(self, texts: list[str]):  # noqa: ANN201
            raise AssertionError("embedding provider should not be called for existing project jobs")

    class StubRouter:
        def embedding(self) -> UnexpectedEmbedding:
            return UnexpectedEmbedding()

    monkeypatch.setattr("app.api.main.get_router", lambda: StubRouter())

    response = client.post("/jobs/match", json={"query": "VLA / 具身智能算法工程师", "top_k": 1})

    assert response.status_code == 200
    assert response.json()["source"] == "project_database"
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
            source_platform="GitHub",
        ),
        Candidate(
            id="cand_no_email",
            name="No Email",
            current_company="Unknown Lab",
            city="上海",
            email=None,
            source_platform="Paper",
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
