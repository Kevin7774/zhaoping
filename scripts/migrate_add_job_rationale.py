"""Add jobs.rationale (JSON, nullable) to an existing database.

Reads PROJECT_DATABASE_URL / DATABASE_URL from the environment (load your env file first):

    set -a && . .env.test.pg && set +a && .venv/bin/python scripts/migrate_add_job_rationale.py

Idempotent: skips when the column already exists. New databases created via
metadata (create_db.py, unit-test fixtures) get the column automatically.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, text  # noqa: E402


def main() -> None:
    url = os.environ.get("PROJECT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("PROJECT_DATABASE_URL / DATABASE_URL is not set")
    engine = create_engine(url, future=True)
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    if "rationale" in columns:
        print("jobs.rationale already exists; nothing to do")
        return
    column_type = "JSONB" if engine.dialect.name == "postgresql" else "JSON"
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE jobs ADD COLUMN rationale {column_type}"))
    print(f"added jobs.rationale ({column_type}) on {engine.dialect.name}")


if __name__ == "__main__":
    main()
