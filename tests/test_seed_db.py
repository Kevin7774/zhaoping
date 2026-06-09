from __future__ import annotations

from sqlalchemy import func, select

from app.db import session as db_session
from app.db.session import get_project_session, make_project_session_factory
from app.models import Candidate, Job, JobCandidate, Project
from scripts.seed_db import SEED_PROJECT_ID, seed_project_mock_data


def test_seed_project_mock_data_is_idempotent(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'projects.sqlite3'}"

    first_summary = seed_project_mock_data(database_url)
    second_summary = seed_project_mock_data(database_url)

    assert first_summary == {
        "project_id": SEED_PROJECT_ID,
        "jobs": 3,
        "candidates": 5,
        "matches": 5,
    }
    assert second_summary == first_summary

    session_factory = make_project_session_factory(database_url)
    with session_factory() as session:
        project = session.get(Project, SEED_PROJECT_ID)
        assert project is not None
        assert project.name == "2026 AI 团队招聘"
        assert session.scalar(select(func.count(Job.id))) == 3
        assert session.scalar(select(func.count(Candidate.id))) == 5
        assert session.scalar(select(func.count(JobCandidate.id))) == 5
        assert session.get(Candidate, "cand_maya_li").email is None


def test_default_project_session_dependency_yields_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_DATABASE_URL", f"sqlite:///{tmp_path / 'default.sqlite3'}")
    db_session.project_session_factory.cache_clear()

    generator = get_project_session()
    try:
        session = next(generator)
        assert session.bind is not None
    finally:
        generator.close()
        db_session.project_session_factory.cache_clear()
