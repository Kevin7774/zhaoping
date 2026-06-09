from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
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
    engine.dispose()


def make_project_session_factory(database_url: str | None = None):
    engine = make_project_engine(database_url)
    ProjectBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@lru_cache(maxsize=1)
def project_session_factory():
    return make_project_session_factory()


def get_project_session() -> Iterator[Session]:
    with project_session_factory()() as session:
        yield session
