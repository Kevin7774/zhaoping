from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import ProjectBase


def project_database_url() -> str:
    return os.environ.get("PROJECT_DATABASE_URL") or os.environ.get("DATABASE_URL") or "sqlite:///data/projects.sqlite3"


def make_project_engine(database_url: str | None = None):
    url = database_url or project_database_url()
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, future=True, connect_args={"check_same_thread": False})
    return create_engine(url, future=True, pool_pre_ping=True)


def create_project_tables(database_url: str | None = None) -> None:
    engine = make_project_engine(database_url)
    ProjectBase.metadata.create_all(engine)
    ensure_project_schema(engine)
    engine.dispose()


def make_project_session_factory(database_url: str | None = None):
    engine = make_project_engine(database_url)
    ProjectBase.metadata.create_all(engine)
    ensure_project_schema(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def ensure_project_schema(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "candidates" in table_names:
        _ensure_columns(
            engine,
            "candidates",
            {
                "title": "VARCHAR(128)",
                "location": "VARCHAR(128)",
                "github_url": "VARCHAR(512)",
                "linkedin_url": "VARCHAR(512)",
                "homepage_url": "VARCHAR(512)",
                "source_platform": "VARCHAR(64)",
                "source_url": "VARCHAR(512)",
                "evidence": "JSON",
                "skills": "JSON",
                "created_from_task_id": "VARCHAR(64)",
                "raw_payload": "JSON",
            },
        )
    if "job_candidates" in table_names:
        _ensure_columns(
            engine,
            "job_candidates",
            {
                "project_id": "VARCHAR(64)",
                "evidence": "JSON",
                "source_task_id": "VARCHAR(64)",
            },
        )
    if "outreach_drafts" in table_names:
        _ensure_columns(
            engine,
            "outreach_drafts",
            {
                "strategy_tag": "VARCHAR(64)",
            },
        )
    if "outreach_history" in table_names:
        _ensure_columns(
            engine,
            "outreach_history",
            {
                "strategy_tag": "VARCHAR(64)",
            },
        )


def _ensure_columns(engine, table_name: str, column_defs: dict[str, str]) -> None:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing = [(column, ddl) for column, ddl in column_defs.items() if column not in existing_columns]
    if not missing:
        return
    with engine.begin() as connection:
        for column, ddl in missing:
            if engine.dialect.name == "postgresql":
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column} {ddl}"))
            else:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl}"))


@lru_cache(maxsize=1)
def project_session_factory():
    return make_project_session_factory()


def get_project_session() -> Iterator[Session]:
    with project_session_factory()() as session:
        yield session
