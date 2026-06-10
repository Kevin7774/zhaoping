from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routers.projects as projects_router
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


class FakeProjectInitLLM:
    def __init__(self, role_count: int = 14) -> None:
        self.prompts: list[str] = []
        self.role_count = role_count

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        roles = []
        for index in range(self.role_count):
            roles.append(
                {
                    "role_id": f"hanno_role_{index:02d}",
                    "title": f"汉诺云智边缘 AI 岗位 {index}",
                    "seniority": "Senior",
                    "responsibilities": [f"负责边缘 AI 交付链路 {index}"],
                    "must_have_skills": ["Edge AI", "PostgreSQL", "FastAPI"],
                    "nice_to_have_skills": ["Docling", "SSE"],
                    "target_companies": ["边缘计算公司", "智能硬件厂商"],
                    "exclusion_signals": ["仅做 Demo 无交付经验"],
                    "interview_questions": ["请拆解一次现场边缘盒子部署故障。"],
                    "scoring_rubric": {"edge_delivery": 40, "ai_engineering": 35, "safety": 25},
                    "search_strategy": {
                        "community": '"edge ai" AND FastAPI',
                        "academic": '"edge computing" AND "AI"',
                        "industry": "智能硬件 AND 边缘计算",
                    },
                }
            )
        return json.dumps({
            "industry_reading": "汉诺云智面向边缘计算与 AI 交付。",
            "technical_assumptions": ["需要覆盖云边协同、硬件交付和 AI 应用工程。"],
            "roles": roles,
            "coverage_gaps": [],
        }, ensure_ascii=False)


class FakeProjectInitRouter:
    def __init__(self, llm: FakeProjectInitLLM) -> None:
        self.llm_provider = llm

    def llm(self, service_name: str | None = None) -> FakeProjectInitLLM:
        return self.llm_provider


class SequenceProjectInitLLM(FakeProjectInitLLM):
    def __init__(self, outputs: list[str]) -> None:
        super().__init__(role_count=1)
        self.outputs = outputs

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self.outputs.pop(0)


class MessagesProjectInitLLM(FakeProjectInitLLM):
    def __init__(self, role_count: int = 14) -> None:
        super().__init__(role_count=role_count)
        self.messages_calls: list[dict] = []

    def messages(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0,
        response_format: dict | None = None,
    ) -> dict:
        self.messages_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        return {"choices": [{"message": {"content": self.text(messages[0]["content"], max_tokens=max_tokens)}}]}


class SlowProjectInitLLM(MessagesProjectInitLLM):
    def messages(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0,
        response_format: dict | None = None,
    ) -> dict:
        self.messages_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        time.sleep(0.2)
        return {"choices": [{"message": {"content": self.text(messages[0]["content"], max_tokens=max_tokens)}}]}


def test_list_projects_returns_project_stats(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_hanno_ai_hardware",
                name="汉诺云智招聘",
                status="active",
                created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            )
        )
        session.add(
            Job(
                id="job_hanno_edge",
                project_id="project_hanno_ai_hardware",
                title="边缘 AI 架构师",
                headcount=1,
                status="sourcing",
            )
        )
        session.commit()

    response = client.get("/projects")

    assert response.status_code == 200
    payload = response.json()
    assert [project["id"] for project in payload] == ["project_hanno_ai_hardware", "project_2026_ai_team"]
    assert payload[0]["openJobs"] == 1
    assert payload[0]["totalCandidates"] == 0
    assert payload[1]["openJobs"] == 2


def test_create_project_creates_empty_isolated_project(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={"id": "project_new_market", "name": "新市场招聘项目", "status": "active"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "project_new_market"
    assert response.json()["openJobs"] == 0
    assert client.get("/projects/project_new_market/jobs").json() == []
    assert client.get("/projects/project_new_market/candidates").json() == []


def test_create_project_rejects_duplicate_project_id(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={"id": "project_2026_ai_team", "name": "重复项目", "status": "active"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Project already exists: project_2026_ai_team"


def test_preview_project_from_bp_uses_json_mode_and_does_not_persist_jobs(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = MessagesProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 14
    assert response.json()["jobs"][0]["title"] == "汉诺云智边缘 AI 岗位 0"
    assert llm.messages_calls[0]["response_format"] == {"type": "json_object"}
    with session_factory() as session:
        assert session.get(Project, "project_hanno_ai_hardware") is None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 0


def test_preview_project_roles_from_prompt_without_bp_file(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = MessagesProjectInitLLM(role_count=4)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)

    response = client.post(
        "/projects/project_prompt_generated/preview-from-bp",
        json={
            "projectName": "提示词生成项目",
            "generationMode": "prompt",
            "projectPrompt": "我要搭建一个面向工业质检的边缘 AI 招聘项目，需要算法、硬件、交付和行业研究岗位。",
            "industryResearchPrompt": "重点拆解工业质检、边缘盒子、现场交付和数据闭环。",
            "minimumRoleCount": 4,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 4
    assert payload["generationMode"] == "prompt"
    assert payload["researchTrace"][0]["stage"] == "项目输入"
    assert "用户项目提示" in payload["researchTrace"][0]["summary"]
    assert "project_prompt:" in llm.prompts[0]
    assert "industry_research_prompt:" in llm.prompts[0]
    assert "bp_markdown:" not in llm.prompts[0]
    with session_factory() as session:
        assert session.get(Project, "project_prompt_generated") is None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_prompt_generated")) == 0


def test_preview_project_from_bp_falls_back_when_llm_times_out(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件、边缘计算、RAG 和私有化交付团队。", encoding="utf-8")
    llm = SlowProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "BP_DECONSTRUCTOR_CALL_TIMEOUT_SECONDS", 0.01, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 14
    assert payload["jobs"][0]["title"] == "行业研究与解决方案负责人"
    assert any("LLM" in item for item in payload["coverageGaps"])
    with session_factory() as session:
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 0


def test_initialize_project_from_bp_falls_back_and_persists_when_llm_times_out(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件、边缘计算、RAG 和私有化交付团队。", encoding="utf-8")
    llm = SlowProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)
    monkeypatch.setattr(projects_router, "BP_DECONSTRUCTOR_CALL_TIMEOUT_SECONDS", 0.01, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 14
    assert payload["jobs"][0]["title"] == "行业研究与解决方案负责人"
    with session_factory() as session:
        assert session.get(Project, "project_hanno_ai_hardware") is not None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 14


def test_initialize_project_from_bp_retries_once_when_llm_json_is_malformed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    valid_output = FakeProjectInitLLM(role_count=1).text("seed")
    llm = SequenceProjectInitLLM(
        [
            '{"industry_reading":"x","roles":[{"role_id":"broken","title":"Broken"}]',
            valid_output,
        ]
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 1
    assert len(llm.prompts) == 2
    assert "校验失败原因" in llm.prompts[1]
    assert "只输出符合 Schema 的合法 JSON" in llm.prompts[1]


def test_initialize_project_from_bp_allows_second_json_repair_retry(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = SequenceProjectInitLLM(
        [
            '{"industry_reading":"x","roles":[{"role_id":"broken","title":"Broken"}]',
            '{"industry_reading":"x","roles":[{"role_id":"still_broken","title":"Broken"}]',
            FakeProjectInitLLM(role_count=1).text("seed"),
        ]
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 1
    assert len(llm.prompts) == 3
    assert "输出紧凑 JSON" in llm.prompts[1]
    assert "输出紧凑 JSON" in llm.prompts[2]


def test_initialize_project_from_bp_retries_when_role_count_is_below_minimum(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = SequenceProjectInitLLM(
        [
            FakeProjectInitLLM(role_count=7).text("seed"),
            FakeProjectInitLLM(role_count=14).text("seed"),
        ]
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 14,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 14
    assert len(llm.prompts) == 2
    assert "至少输出 14 个 roles" in llm.prompts[1]


def test_initialize_project_from_bp_uses_v2_prompt_and_persists_full_job_matrix(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = FakeProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == "project_hanno_ai_hardware"
    assert payload["jobCount"] == 14
    assert payload["promptName"] == "bp_deconstructor_v2"
    assert "JSON-only" in llm.prompts[0]
    assert "不可编造" in llm.prompts[0]
    assert "must_have_skills" in llm.prompts[0]

    jobs_response = client.get("/projects/project_hanno_ai_hardware/jobs")

    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert len(jobs) == 14
    first_job = jobs[0]
    assert first_job["title"] == "汉诺云智边缘 AI 岗位 0"
    assert first_job["seniority"] == "Senior"
    assert first_job["responsibilities"] == ["负责边缘 AI 交付链路 0"]
    assert first_job["mustHaveSkills"] == ["Edge AI", "PostgreSQL", "FastAPI"]
    assert first_job["niceToHaveSkills"] == ["Docling", "SSE"]
    assert first_job["targetCompanies"] == ["边缘计算公司", "智能硬件厂商"]
    assert first_job["exclusionSignals"] == ["仅做 Demo 无交付经验"]
    assert first_job["interviewQuestions"] == ["请拆解一次现场边缘盒子部署故障。"]
    assert first_job["scoringRubric"] == {"edge_delivery": 40, "ai_engineering": 35, "safety": 25}
    assert first_job["searchStrategy"]["community"] == '"edge ai" AND FastAPI'

    with session_factory() as session:
        project = session.get(Project, "project_hanno_ai_hardware")
        stored_jobs = session.query(Job).filter(Job.project_id == "project_hanno_ai_hardware").all()
    assert project is not None
    assert len(stored_jobs) == 14


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
