from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.db.session import get_project_session, make_project_session_factory
from app.db import task_models
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


def test_sqlite_is_rejected_in_production_for_project_and_task_databases(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    sqlite_url = f"sqlite:///{tmp_path / 'prod.sqlite3'}"

    try:
        with pytest.raises(RuntimeError, match="SQLite is not allowed"):
            db_session.make_project_engine(sqlite_url)
        with pytest.raises(RuntimeError, match="SQLite is not allowed"):
            task_models.make_task_engine(sqlite_url)
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)


def test_postgres_engines_use_explicit_connection_pool(monkeypatch) -> None:
    project_calls = {}
    task_calls = {}

    def fake_project_create_engine(url, **kwargs):  # noqa: ANN001
        project_calls["url"] = url
        project_calls["kwargs"] = kwargs
        return object()

    def fake_task_create_engine(url, **kwargs):  # noqa: ANN001
        task_calls["url"] = url
        task_calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(db_session, "create_engine", fake_project_create_engine)
    monkeypatch.setattr(task_models, "create_engine", fake_task_create_engine)

    db_session.make_project_engine("postgresql+psycopg://user:pass@localhost:5432/zhaoping")
    task_models.make_task_engine("postgresql+psycopg://user:pass@localhost:5432/zhaoping_tasks")

    assert project_calls["kwargs"]["pool_pre_ping"] is True
    assert project_calls["kwargs"]["pool_size"] >= 5
    assert project_calls["kwargs"]["max_overflow"] >= 10
    assert task_calls["kwargs"]["pool_pre_ping"] is True
    assert task_calls["kwargs"]["pool_size"] >= 5
