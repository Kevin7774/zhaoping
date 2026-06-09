from __future__ import annotations

import json
from pathlib import Path
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


class FakeDocumentParser:
    def parse(self, file_path: str) -> str:
        return Path(file_path).read_text(encoding="utf-8")


class FakeLLM:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.prompts: list[str] = []

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.output, ensure_ascii=False)


class FakeRouter:
    def __init__(self, llm_output: dict) -> None:
        self.parser = FakeDocumentParser()
        self.llm_provider = FakeLLM(llm_output)

    def document_parser(self, service_name: str | None = None) -> FakeDocumentParser:
        return self.parser

    def llm(self, service_name: str | None = None) -> FakeLLM:
        return self.llm_provider


@pytest.fixture()
def session_factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    factory = make_project_session_factory(f"sqlite:///{tmp_path / 'projects.sqlite3'}")
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


def resume_file(tmp_path) -> Path:
    path = tmp_path / "lin-chen-resume.md"
    path.write_text(
        "# Lin Chen\n\n"
        "Email: lin.chen@example.com\n\n"
        "Current company: Embodied AI Lab\n\n"
        "Built VLA policy evaluation and Diffusion Policy data pipelines for real robots.",
        encoding="utf-8",
    )
    return path


def llm_resume_output() -> dict:
    return {
        "name": "Lin Chen",
        "current_company": "Embodied AI Lab",
        "title": "VLA Algorithm Engineer",
        "location": "深圳",
        "email": "lin.chen@example.com",
        "skills": ["VLA", "Diffusion Policy", "real robot evaluation"],
        "evidence": ["Built VLA policy evaluation and Diffusion Policy data pipelines for real robots."],
        "confidence": 0.91,
    }


def test_extract_resume_lead_validates_llm_json_and_preserves_source_file(tmp_path) -> None:
    from app.core.resume_ingestion import extract_resume_lead

    path = resume_file(tmp_path)
    router = FakeRouter(llm_resume_output())

    lead = extract_resume_lead(path.read_text(encoding="utf-8"), source_file=str(path), router=router)

    assert lead["name"] == "Lin Chen"
    assert lead["source_platform"] == "resume_file"
    assert lead["email"] == "lin.chen@example.com"
    assert lead["raw_payload"]["source_file"] == str(path)
    assert lead["raw_payload"]["source_filename"] == "lin-chen-resume.md"
    assert "只输出合法 JSON" in router.llm_provider.prompts[0]


def test_import_resume_to_project_reuses_candidate_lead_ingestion(
    session_factory: sessionmaker[Session],
    tmp_path,
) -> None:
    from app.core.resume_ingestion import import_resume_to_project

    path = resume_file(tmp_path)
    router = FakeRouter(llm_resume_output())
    with session_factory() as session:
        result = import_resume_to_project(
            session,
            project_id="project_2026_ai_team",
            job_id="job_vla_algorithm",
            file_path=str(path),
            source_task_id="task_resume_1",
            router=router,
        )

    assert result["found"] == 1
    assert result["inserted_candidates"] == 1
    assert result["linked_job_candidates"] == 1
    assert result["rejected"] == 0
    assert result["markdown_preview"].startswith("# Lin Chen")

    with session_factory() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.email == "lin.chen@example.com"))
        assert candidate is not None
        assert candidate.source_platform == "resume_file"
        assert candidate.raw_payload["source_file"] == str(path)
        assert candidate.created_from_task_id == "task_resume_1"
        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == "job_vla_algorithm",
                JobCandidate.candidate_id == candidate.id,
            )
        )
        assert link is not None
        assert link.project_id == "project_2026_ai_team"
        assert link.pipeline_status == "sourced"


def test_local_resume_import_api_creates_task_and_project_candidate(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from app.core import resume_ingestion

    path = resume_file(tmp_path)
    monkeypatch.setattr(resume_ingestion, "get_router", lambda: FakeRouter(llm_resume_output()))
    monkeypatch.setattr(resume_ingestion, "project_session_factory", lambda: session_factory)

    response = client.post(
        "/resumes/local-import",
        json={
            "projectId": "project_2026_ai_team",
            "jobId": "job_vla_algorithm",
            "filePath": str(path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"] == "RESUME_IMPORT"
    assert payload["status"] == "done"
    snapshot = client.get(f"/tasks/{payload['taskId']}").json()
    assert snapshot["result"]["inserted_candidates"] == 1

    candidates = client.get("/projects/project_2026_ai_team/candidates")
    assert candidates.headers["x-total-count"] == "1"
    assert candidates.json()[0]["email"] == "lin.chen@example.com"


def test_project_resume_upload_saves_file_creates_task_and_project_candidate(
    client: TestClient,
    session_factory: sessionmaker[Session],
    isolated_task_store,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from app.core import resume_ingestion

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(resume_ingestion, "get_router", lambda: FakeRouter(llm_resume_output()))
    monkeypatch.setattr(resume_ingestion, "project_session_factory", lambda: session_factory)

    response = client.post(
        "/projects/project_2026_ai_team/jobs/job_vla_algorithm/upload-resumes",
        files={"file": ("lin-chen-resume.md", resume_file(tmp_path).read_bytes(), "text/markdown")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"] == "RESUME_IMPORT"
    assert payload["taskId"]
    saved_files = list((tmp_path / "data" / "uploads" / "project_2026_ai_team" / "job_vla_algorithm").glob("*.md"))
    assert len(saved_files) == 1
    assert saved_files[0].read_text(encoding="utf-8").startswith("# Lin Chen")

    snapshot = client.get(f"/tasks/{payload['taskId']}").json()
    assert snapshot["status"] == "done"
    assert snapshot["result"]["file_path"] == str(saved_files[0])
    candidates = client.get("/projects/project_2026_ai_team/candidates")
    assert candidates.headers["x-total-count"] == "1"
    assert candidates.json()[0]["sourcePlatform"] == "resume_file"


def test_resume_import_task_type_uses_task_store_without_scenario_plan(isolated_task_store) -> None:
    task = isolated_task_store.create("RESUME_IMPORT", "导入简历：lin-chen-resume.md")

    snapshot = isolated_task_store.snapshot(task.task_id)

    assert snapshot is not None
    assert snapshot["scenario_id"] == "RESUME_IMPORT"
    assert snapshot["total_steps"] == 0
    assert snapshot["status"] == "processing"
