from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.db.schema import candidate_profile


class CandidateRepository:
    def __init__(self, engine) -> None:
        self.engine = engine

    def upsert_candidate_profile(self, profile: dict[str, Any]) -> None:
        statement = insert(candidate_profile).values(**profile)
        statement = statement.on_conflict_do_update(
            index_elements=[candidate_profile.c.candidate_id],
            set_={
                key: statement.excluded[key]
                for key in profile
                if key != "candidate_id"
            },
        )
        with self.engine.begin() as connection:
            connection.execute(statement)


class PostgresDatabaseProvider:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine = None

    def candidate_repository(self) -> CandidateRepository:
        return CandidateRepository(self._get_engine())

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine

            self._engine = create_engine(self.database_url)
        return self._engine
