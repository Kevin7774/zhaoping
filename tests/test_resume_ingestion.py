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


class FakeMetadataDocumentParser(FakeDocumentParser):
    last_metadata = {
        "parser": "docling",
        "provider": "docling",
        "confidence": 0.93,
        "degraded_reason": None,
    }


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


class FakeMetadataRouter(FakeRouter):
    def __init__(self, llm_output: dict) -> None:
        super().__init__(llm_output)
        self.parser = FakeMetadataDocumentParser()


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


def test_auto_document_parser_blocks_pdftotext_fallback_by_default_for_pdf(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import document

    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.5\n")

    def fail_docling(self, file_path: str) -> str:  # noqa: ANN001
        raise RuntimeError("docling unavailable")

    monkeypatch.setattr(document.DoclingDocumentParser, "parse", fail_docling)
    monkeypatch.delenv("ZHAOPING_ALLOW_PDF_TEXT_FALLBACK", raising=False)

    with pytest.raises(RuntimeError, match="Refusing low-quality pdftotext fallback"):
        document.AutoDocumentParser().parse(str(pdf_path))


def test_auto_document_parser_allows_pdftotext_only_when_explicitly_enabled(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import document

    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.5\n")

    def fail_docling(self, file_path: str) -> str:  # noqa: ANN001
        raise RuntimeError("docling unavailable")

    class Result:
        returncode = 0
        stdout = "张载德\nAI 全栈工程师\n"
        stderr = ""

    def fake_run(args, *, check: bool, capture_output: bool, text: bool):  # noqa: ANN001
        assert args == ["pdftotext", "-layout", str(pdf_path), "-"]
        assert check is False
        assert capture_output is True
        assert text is True
        return Result()

    monkeypatch.setenv("ZHAOPING_ALLOW_PDF_TEXT_FALLBACK", "1")
    monkeypatch.setattr(document.DoclingDocumentParser, "parse", fail_docling)
    monkeypatch.setattr(document.shutil, "which", lambda command: "/usr/bin/pdftotext" if command == "pdftotext" else None)
    monkeypatch.setattr(document.subprocess, "run", fake_run)
    assert document.AutoDocumentParser().parse(str(pdf_path)) == "张载德\nAI 全栈工程师\n"


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
    assert "极其严厉的数据清洗与结构化抽取 Agent" in router.llm_provider.prompts[0]
    assert "confidence_score" in router.llm_provider.prompts[0]


def test_extract_resume_lead_uses_source_filename_when_heading_is_generic(tmp_path) -> None:
    from app.core.resume_ingestion import extract_resume_lead

    path = tmp_path / "简历张载德.pdf"
    markdown = "## 个⼈总结\n\n长期构建 AI-native 产品、Agent 工作流与开发者工具系统。"

    lead = extract_resume_lead(markdown, source_file=str(path), router=FakeRouter({"name": "个⼈总结"}))

    assert lead["name"] == "张载德"
    assert lead["raw_payload"]["source_filename"] == "简历张载德.pdf"


def test_extract_resume_lead_reads_name_label_from_resume_lines(tmp_path) -> None:
    from app.core.resume_ingestion import extract_resume_lead

    path = tmp_path / "1337_【AI全栈工程师】代先生_一年以内.pdf"
    markdown = "姓名 ：\n\n代宁\n\n年龄 ：\n\n22\n\n邮箱 ：\n\n15229216182@163.com"

    lead = extract_resume_lead(markdown, source_file=str(path), router=FakeRouter({"name": "姓名 ："}))

    assert lead["name"] == "代宁"
    assert lead["email"] == "15229216182@163.com"


def test_prepare_resume_lead_records_parser_metadata(tmp_path) -> None:
    from app.core.resume_ingestion import prepare_resume_lead

    path = resume_file(tmp_path)
    router = FakeMetadataRouter(llm_resume_output())

    _markdown, lead = prepare_resume_lead(str(path), router=router)

    assert lead["parser"] == "docling"
    assert lead["provider"] == "docling"
    assert lead["parser_confidence"] == pytest.approx(0.93)
    assert lead["confidence"] == pytest.approx(0.91)
    assert lead["raw_payload"]["parser"] == "docling"
    assert lead["raw_payload"]["provider"] == "docling"
    assert lead["raw_payload"]["parser_confidence"] == pytest.approx(0.93)
    assert lead["raw_payload"]["degraded_reason"] is None


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


def test_resume_import_task_does_not_hold_project_session_while_parsing_or_calling_llm(
    session_factory: sessionmaker[Session],
    isolated_task_store,
    tmp_path,
) -> None:
    from app.core.resume_ingestion import run_resume_import_task

    tracker = {"session_open": False}
    path = resume_file(tmp_path)

    class GuardedParser(FakeDocumentParser):
        def parse(self, file_path: str) -> str:
            assert tracker["session_open"] is False
            return super().parse(file_path)

    class GuardedLLM(FakeLLM):
        def text(self, prompt: str, max_tokens: int = 1024) -> str:
            assert tracker["session_open"] is False
            return super().text(prompt, max_tokens=max_tokens)

    class GuardedRouter(FakeRouter):
        def __init__(self) -> None:
            self.parser = GuardedParser()
            self.llm_provider = GuardedLLM(llm_resume_output())

    class GuardedSessionContext:
        def __init__(self) -> None:
            self._session_context = session_factory()

        def __enter__(self) -> Session:
            tracker["session_open"] = True
            return self._session_context.__enter__()

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            try:
                return self._session_context.__exit__(exc_type, exc, traceback)
            finally:
                tracker["session_open"] = False

    task = isolated_task_store.create("RESUME_IMPORT", "导入简历：lin-chen-resume.md")
    snapshot = run_resume_import_task(
        task.task_id,
        project_id="project_2026_ai_team",
        job_id="job_vla_algorithm",
        file_path=str(path),
        task_store=isolated_task_store,
        session_factory=lambda: GuardedSessionContext(),
        router=GuardedRouter(),
    )

    assert snapshot is not None
    assert snapshot["status"] == "done"


def test_resume_import_task_type_uses_task_store_without_scenario_plan(isolated_task_store) -> None:
    task = isolated_task_store.create("RESUME_IMPORT", "导入简历：lin-chen-resume.md")

    snapshot = isolated_task_store.snapshot(task.task_id)

    assert snapshot is not None
    assert snapshot["scenario_id"] == "RESUME_IMPORT"
    assert snapshot["total_steps"] == 0
    assert snapshot["status"] == "processing"
