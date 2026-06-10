from __future__ import annotations

import time
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.main as api_main
import app.core.orchestrator as orchestrator
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
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as session:
        seed_minimal_project(session)
    try:
        yield factory
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


@pytest.fixture()
def isolated_task_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("TASK_DATABASE_URL", f"sqlite:///{tmp_path / 'tasks.sqlite3'}")
    store = orchestrator.DBTaskStore()
    monkeypatch.setattr(orchestrator, "task_store", store)
    monkeypatch.setattr(api_main, "task_store", store)
    return store


def seed_minimal_project(session: Session) -> None:
    session.add(Project(id="project_2026_ai_team", name="2026 AI 团队招聘", status="active"))
    session.add(
        Job(
            id="job_vla_algorithm",
            project_id="project_2026_ai_team",
            title="VLA / 具身智能算法工程师",
            headcount=2,
            status="processing",
        )
    )
    session.add(Candidate(id="cand_existing", name="Existing Lead", current_company="Existing Robotics", city="上海"))
    session.add(
        JobCandidate(
            job_id="job_vla_algorithm",
            candidate_id="cand_existing",
            match_score=80,
            pipeline_status="processing",
        )
    )
    session.commit()


def github_lead() -> dict:
    return {
        "name": "Alice Wang",
        "current_company": "Open Robotics",
        "title": "Robotics ML Engineer",
        "location": "Shenzhen",
        "email": "alice@example.com",
        "github_url": "https://github.com/alicewang",
        "source_platform": "github_repositories",
        "source_url": "https://github.com/alicewang/robot-vla",
        "evidence": ["Maintains robot-vla with diffusion policy and VLA examples."],
        "skills": ["robotics", "VLA", "diffusion policy"],
        "matched_keywords": ["robotics", "VLA"],
        "confidence": 0.91,
        "raw_payload": {"id": 123, "title": "robot-vla"},
    }


def test_candidate_lead_normalization_accepts_structured_lead() -> None:
    from app.core.candidate_lead_ingestion import normalize_candidate_lead

    normalized = normalize_candidate_lead(github_lead())

    assert normalized.accepted is True
    assert normalized.lead is not None
    assert normalized.lead.name == "Alice Wang"
    assert normalized.lead.source_platform == "github_repositories"
    assert normalized.lead.source_url == "https://github.com/alicewang/robot-vla"
    assert normalized.lead.skills == ["robotics", "VLA", "diffusion policy"]


def test_candidate_lead_normalization_rejects_missing_required_source() -> None:
    from app.core.candidate_lead_ingestion import normalize_candidate_lead

    normalized = normalize_candidate_lead({"name": "No Source"})

    assert normalized.accepted is False
    assert "source_platform is required" in normalized.reasons
    assert "source_url or evidence is required" in normalized.reasons


def test_ingestion_inserts_candidate_and_job_link(session_factory: sessionmaker[Session]) -> None:
    from app.core.candidate_lead_ingestion import ingest_candidate_leads

    with session_factory() as session:
        result = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_B_1",
            raw_leads=[github_lead()],
        )

    assert result["found"] == 1
    assert result["normalized"] == 1
    assert result["inserted_candidates"] == 1
    assert result["linked_job_candidates"] == 1
    assert result["compliance_review_required"] == 1
    assert result["rejected"] == 0

    with session_factory() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.email == "alice@example.com"))
        assert candidate is not None
        assert candidate.source_platform == "github_repositories"
        assert candidate.source_url == "https://github.com/alicewang/robot-vla"
        assert candidate.created_from_task_id == "task_B_1"
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == candidate.id,
            )
        )
        assert link is not None
        assert link.project_id == "project_2026_ai_team"
        assert link.pipeline_status == "pending_compliance_review"
        assert link.source_task_id == "task_B_1"


def test_ingestion_marks_obfuscated_contact_for_compliance_review(session_factory: sessionmaker[Session]) -> None:
    from app.core.candidate_lead_ingestion import ingest_candidate_leads

    lead = {
        **github_lead(),
        "email": "alice@example.com",
        "contact_source": "cloudflare_email_decode",
        "raw_payload": {
            "contact_source": "cloudflare_email_decode",
            "source_markup": '<a class="__cf_email__" data-cfemail="...">[email protected]</a>',
        },
    }

    with session_factory() as session:
        result = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_B_risky",
            raw_leads=[lead],
        )

    assert result["compliance_review_required"] == 1
    with session_factory() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.email == "alice@example.com"))
        assert candidate is not None
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == candidate.id,
            )
        )
        assert link is not None
        assert link.pipeline_status == "pending_compliance_review"


def test_ingestion_marks_public_web_email_for_compliance_review(session_factory: sessionmaker[Session]) -> None:
    from app.core.candidate_lead_ingestion import ingest_candidate_leads

    with session_factory() as session:
        result = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_public_email",
            raw_leads=[
                {
                    "name": "Public Web Candidate",
                    "email": "public@example.com",
                    "source_platform": "public_web",
                    "source_url": "https://example.com/profile/public-web-candidate",
                    "evidence": ["Public profile lists the contact email."],
                    "extraction_method": "public_profile_scrape",
                }
            ],
        )

    assert result["compliance_review_required"] == 1
    with session_factory() as session:
        link = session.scalar(select(JobCandidate).where(JobCandidate.source_task_id == "task_public_email"))
        assert link is not None
        assert link.pipeline_status == "pending_compliance_review"


def test_ingestion_deduplicates_existing_candidate_and_repeated_run(session_factory: sessionmaker[Session]) -> None:
    from app.core.candidate_lead_ingestion import ingest_candidate_leads

    with session_factory() as session:
        first = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_B_1",
            raw_leads=[github_lead()],
        )
        second = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_B_2",
            raw_leads=[github_lead()],
        )

    assert first["inserted_candidates"] == 1
    assert second["inserted_candidates"] == 0
    assert second["linked_job_candidates"] == 0
    assert second["duplicates"] == 1

    with session_factory() as session:
        assert session.scalar(select(func.count(Candidate.id))) == 2
        assert session.scalar(select(func.count(JobCandidate.id))) == 2


def test_ingestion_rejects_invalid_leads_with_reasons(session_factory: sessionmaker[Session]) -> None:
    from app.core.candidate_lead_ingestion import ingest_candidate_leads

    with session_factory() as session:
        result = ingest_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            source_task_id="task_B_1",
            raw_leads=[{"name": "Broken"}],
        )

    assert result["found"] == 1
    assert result["normalized"] == 0
    assert result["rejected"] == 1
    assert result["rejected_reasons"]["source_platform is required"] == 1
    assert result["rejected_reasons"]["source_url or evidence is required"] == 1


def test_extract_candidate_leads_from_search_and_structured_outputs() -> None:
    from app.core.candidate_lead_ingestion import extract_candidate_leads

    payload = {
        "candidate_leads": [github_lead()],
        "搜索证据": {
            "实时检索": {
                "results": [
                    {
                        "source_key": "github_repositories",
                        "title": "robot-vla",
                        "url": "https://github.com/bob/robot-vla",
                        "snippet": "Bob builds robotics VLA systems.",
                        "owner_login": "bob",
                        "owner_type": "User",
                        "company": "Robot Lab",
                        "topics": ["robotics", "VLA"],
                    },
                    {
                        "source_key": "agent_reach_social_search",
                        "title": "Ada Lovelace",
                        "url": "https://www.linkedin.com/in/ada-robotics",
                        "snippet": "Robotics lead at Physical Intelligence.",
                        "job_title": "Robotics Lead",
                        "company": "Physical Intelligence",
                        "location": "San Francisco",
                        "skills": ["robot learning", "manipulation"],
                        "rank": 2,
                    },
                ]
            }
        },
    }

    leads = extract_candidate_leads(payload)

    assert len(leads) == 3
    assert leads[0]["name"] == "Alice Wang"
    assert leads[1]["name"] == "bob"
    assert leads[1]["github_url"] == "https://github.com/bob"
    assert leads[2]["name"] == "Ada Lovelace"
    assert leads[2]["title"] == "Robotics Lead"
    assert leads[2]["current_company"] == "Physical Intelligence"
    assert leads[2]["linkedin_url"] == "https://www.linkedin.com/in/ada-robotics"


def test_candidate_lead_preview_redacts_email_and_reports_ingestion_action(
    session_factory: sessionmaker[Session],
) -> None:
    from app.core.candidate_lead_ingestion import preview_candidate_leads

    lead = {
        **github_lead(),
        "source_platform": "public_web",
        "source_url": "https://example.com/profiles/alice-wang",
        "contact_source": "public_profile_scrape",
    }

    with session_factory() as session:
        preview = preview_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            raw_leads=[lead],
            limit=5,
        )

    assert preview["total_count"] == 1
    assert preview["omitted_count"] == 0
    assert preview["leads"][0] == {
        "name": "Alice Wang",
        "source_platform": "public_web",
        "source_url": "https://example.com/profiles/alice-wang",
        "evidence_summary": "Maintains robot-vla with diffusion policy and VLA examples.",
        "confidence": 0.91,
        "matched_job": "VLA / 具身智能算法工程师",
        "compliance_status": "pending_compliance_review",
        "ingestion_action": "insert",
        "email": "[redacted]",
    }
    assert "alice@example.com" not in str(preview)

    with session_factory() as session:
        assert session.scalar(select(func.count(Candidate.id))) == 1
        assert session.scalar(select(func.count(JobCandidate.id))) == 1


def test_candidate_lead_preview_keeps_github_score_and_repository_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    from app.core.candidate_lead_ingestion import preview_candidate_leads

    lead = {
        **github_lead(),
        "source_platform": "github_candidates",
        "source_url": "https://github.com/alice-robotics",
        "github_score": 91,
        "representative_repositories": [
            {
                "full_name": "alice-robotics/agentic-rag-robot",
                "url": "https://github.com/alice-robotics/agentic-rag-robot",
                "language": "TypeScript",
                "stars": 860,
                "forks": 74,
                "topics": ["agentic-workflow", "rag", "mcp"],
            }
        ],
        "repository_evidence": [
            {
                "source": "code",
                "title": "alice-robotics/agentic-rag-robot:src/workflow.ts",
                "url": "https://github.com/alice-robotics/agentic-rag-robot/blob/main/src/workflow.ts",
                "snippet": "createAgenticWorkflow({ mcp, rag, fullstack })",
            }
        ],
        "recent_activity": {"recent_repository_count": 2, "latest_repository_pushed_at": "2026-06-01T12:00:00Z"},
        "scoring_signals": {"total_stars": 980, "matched_keyword_count": 4},
    }

    with session_factory() as session:
        preview = preview_candidate_leads(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            raw_leads=[lead],
            limit=5,
        )

    item = preview["leads"][0]
    assert item["github_score"] == 91
    assert item["representative_repositories"][0]["full_name"] == "alice-robotics/agentic-rag-robot"
    assert item["repository_evidence"][0]["source"] == "code"
    assert item["recent_activity"]["recent_repository_count"] == 2
    assert item["scoring_signals"]["total_stars"] == 980
    assert item["email"] == "[redacted]"
    assert "alice@example.com" not in str(preview)


def test_scenario_b_awaiting_payload_contains_lead_preview(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator.AgentRunner, "STEP_DELAY_SECONDS", 0)
    monkeypatch.setattr(orchestrator, "_source_intelligence_with_audit", fake_source_intelligence)
    monkeypatch.setattr(orchestrator, "project_session_factory", lambda: session_factory)

    task_id = start_scenario_b(client)
    awaiting = wait_for_status(client, task_id, "awaiting_human")

    payload = awaiting["awaiting"]
    assert payload["requires_lead_preview"] is True
    assert payload["lead_preview"]["total_count"] == 2
    assert payload["lead_preview"]["omitted_count"] == 0
    assert len(payload["lead_preview"]["leads"]) == 2
    first = payload["lead_preview"]["leads"][0]
    assert first["name"] == "alicewang"
    assert first["source_platform"] == "github_repositories"
    assert first["source_url"] == "https://github.com/alicewang/robot-vla"
    assert first["evidence_summary"] == "robot-vla; Alice Wang maintains robot-vla with diffusion policy examples."
    assert first["confidence"] == 0.86
    assert first["matched_job"] == "VLA / 具身智能算法工程师"
    assert first["compliance_status"] == "clear"
    assert first["ingestion_action"] == "insert"
    assert payload["lead_preview"]["search_trace"] == {
        "query": "robotics VLA",
        "services": ["github_repositories"],
        "result_count": 2,
        "errors": [],
        "research_layers": [
            {
                "id": "people_network",
                "name_zh": "人才网络",
                "purpose": "从人员库、作者网络和开源/社媒身份定位可触达候选人。",
                "services": ["github_repositories"],
                "result_count": 2,
                "error_count": 0,
            }
        ],
    }


def test_recruiting_live_search_services_cover_top_down_people_and_social_sources() -> None:
    assert "github_candidates" in orchestrator.LIVE_RECRUITING_SEARCH_SERVICES
    assert "github_users" in orchestrator.LIVE_RECRUITING_SEARCH_SERVICES
    assert "agent_reach_social_search" in orchestrator.LIVE_RECRUITING_SEARCH_SERVICES
    assert "semantic_scholar_authors_search" in orchestrator.LIVE_RECRUITING_SEARCH_SERVICES


def test_scenario_b_reject_does_not_ingest_candidate_leads(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator.AgentRunner, "STEP_DELAY_SECONDS", 0)
    monkeypatch.setattr(orchestrator, "_source_intelligence_with_audit", fake_source_intelligence)
    monkeypatch.setattr(orchestrator, "project_session_factory", lambda: session_factory)

    before = client.get("/projects/project_2026_ai_team/candidates")
    assert before.headers["x-total-count"] == "1"

    task_id = start_scenario_b(client)
    wait_for_status(client, task_id, "awaiting_human")
    reject = client.post(f"/tasks/{task_id}/confirm", json={"decision": "reject", "edits": "线索来源不足"})
    assert reject.status_code == 200
    final = wait_for_status(client, task_id, "error")
    assert "人工拒绝" in final["error"]

    after = client.get("/projects/project_2026_ai_team/candidates")
    assert after.headers["x-total-count"] == "1"


def test_scenario_b_result_contains_lead_ingestion_and_increases_candidate_count(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator.AgentRunner, "STEP_DELAY_SECONDS", 0)
    monkeypatch.setattr(orchestrator, "_source_intelligence_with_audit", fake_source_intelligence)
    monkeypatch.setattr(orchestrator, "project_session_factory", lambda: session_factory)

    before = client.get("/projects/project_2026_ai_team/candidates")
    assert before.headers["x-total-count"] == "1"

    task_id = start_scenario_b(client)
    awaiting = wait_for_status(client, task_id, "awaiting_human")
    assert awaiting["awaiting"]
    confirm = client.post(f"/tasks/{task_id}/confirm", json={"decision": "approve", "edits": ""})
    assert confirm.status_code == 200
    done = wait_for_status(client, task_id, "done")

    ingestion = done["result"]["lead_ingestion"]
    assert ingestion["found"] == 2
    assert ingestion["inserted_candidates"] == 2
    assert ingestion["linked_job_candidates"] == 2
    assert ingestion["source_task_id"] == task_id

    after = client.get("/projects/project_2026_ai_team/candidates")
    assert after.headers["x-total-count"] == "3"

    task_id_2 = start_scenario_b(client)
    wait_for_status(client, task_id_2, "awaiting_human")
    confirm_2 = client.post(f"/tasks/{task_id_2}/confirm", json={"decision": "approve", "edits": ""})
    assert confirm_2.status_code == 200
    done_2 = wait_for_status(client, task_id_2, "done")

    assert done_2["result"]["lead_ingestion"]["inserted_candidates"] == 0
    assert done_2["result"]["lead_ingestion"]["duplicates"] == 2
    after_second = client.get("/projects/project_2026_ai_team/candidates")
    assert after_second.headers["x-total-count"] == "3"


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
                    "topics": ["robotics", "VLA", "diffusion-policy"],
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
            "research_layers": [
                {
                    "id": "people_network",
                    "name_zh": "人才网络",
                    "purpose": "从人员库、作者网络和开源/社媒身份定位可触达候选人。",
                    "services": ["github_repositories"],
                    "result_count": 2,
                    "error_count": 0,
                }
            ],
        },
        "检索说明": "test",
    }


def start_scenario_b(client: TestClient) -> str:
    response = client.post(
        "/scenarios/run",
        json={
            "scenario": "B",
            "input": "请为 VLA / 具身智能算法工程师找候选人",
            "frontend_state": {
                "project_id": "project_2026_ai_team",
                "job_profile_id": "job_vla_algorithm",
                "job_title": "VLA / 具身智能算法工程师",
                "action": "find_candidates",
            },
        },
    )
    assert response.status_code == 200
    return response.json()["task_id"]


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
