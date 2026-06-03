from __future__ import annotations

import os

from sqlalchemy import create_engine

from app.db.schema import create_all


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Missing DATABASE_URL, e.g. postgresql+psycopg://user:pass@localhost:5432/robot_agent")

    engine = create_engine(database_url)
    create_all(engine)
    print("MVP PostgreSQL tables created.")


if __name__ == "__main__":
    main()
