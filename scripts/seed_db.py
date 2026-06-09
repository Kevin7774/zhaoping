from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db.session import make_project_session_factory, project_database_url
from app.models import Candidate, Job, JobCandidate, Project

SEED_PROJECT_ID = "project_2026_ai_team"

SEED_JOBS = (
    {
        "id": "job_vla_algorithm",
        "project_id": SEED_PROJECT_ID,
        "title": "VLA / 具身智能算法工程师",
        "headcount": 2,
        "status": "processing",
    },
    {
        "id": "job_robot_data_platform",
        "project_id": SEED_PROJECT_ID,
        "title": "机器人数据平台工程师",
        "headcount": 1,
        "status": "offer",
    },
    {
        "id": "job_embodied_agent_infra",
        "project_id": SEED_PROJECT_ID,
        "title": "具身智能 Agent 工程师",
        "headcount": 2,
        "status": "sourcing",
    },
)

SEED_CANDIDATES = (
    {
        "id": "cand_lin_chen",
        "name": "Alex Chen",
        "current_company": "Embodied AI Lab",
        "city": "深圳",
        "email": "alex.chen@example.com",
    },
    {
        "id": "cand_zhou_han",
        "name": "Zhou Han",
        "current_company": "Robot Foundation Team",
        "city": "上海",
        "email": "zhou.han@example.com",
    },
    {
        "id": "cand_maya_li",
        "name": "Maya Li",
        "current_company": "Autonomy Stack",
        "city": "北京",
        "email": None,
    },
    {
        "id": "cand_wang_ke",
        "name": "Wang Ke",
        "current_company": "Autonomous Driving Data",
        "city": "上海",
        "email": "wang.ke@example.com",
    },
    {
        "id": "cand_sara_qi",
        "name": "Sara Qi",
        "current_company": None,
        "city": "杭州",
        "email": "sara.qi@example.com",
    },
)

SEED_MATCHES = (
    {
        "job_id": "job_vla_algorithm",
        "candidate_id": "cand_lin_chen",
        "match_score": 92,
        "pipeline_status": "processing",
    },
    {
        "job_id": "job_vla_algorithm",
        "candidate_id": "cand_zhou_han",
        "match_score": 88,
        "pipeline_status": "awaiting_human",
    },
    {
        "job_id": "job_robot_data_platform",
        "candidate_id": "cand_wang_ke",
        "match_score": 84,
        "pipeline_status": "done",
    },
    {
        "job_id": "job_robot_data_platform",
        "candidate_id": "cand_sara_qi",
        "match_score": 79,
        "pipeline_status": "processing",
    },
    {
        "job_id": "job_embodied_agent_infra",
        "candidate_id": "cand_maya_li",
        "match_score": 76,
        "pipeline_status": "screening",
    },
)


def seed_project_mock_data(database_url: str | None = None) -> dict[str, object]:
    session_factory = make_project_session_factory(database_url)
    with session_factory() as session:
        _clear_seed_data(session)
        session.add(
            Project(
                id=SEED_PROJECT_ID,
                name="2026 AI 团队招聘",
                status="active",
                created_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
            )
        )
        session.add_all(Job(**job) for job in SEED_JOBS)
        session.add_all(Candidate(**candidate) for candidate in SEED_CANDIDATES)
        session.flush()
        session.add_all(JobCandidate(**match) for match in SEED_MATCHES)
        session.commit()
    return {
        "project_id": SEED_PROJECT_ID,
        "jobs": len(SEED_JOBS),
        "candidates": len(SEED_CANDIDATES),
        "matches": len(SEED_MATCHES),
    }


def _clear_seed_data(session: Session) -> None:
    seed_job_ids = {job["id"] for job in SEED_JOBS}
    existing_job_ids = set(session.scalars(select(Job.id).where(Job.project_id == SEED_PROJECT_ID)).all())
    job_ids = seed_job_ids | existing_job_ids
    candidate_ids = {candidate["id"] for candidate in SEED_CANDIDATES}

    if job_ids:
        session.execute(delete(JobCandidate).where(JobCandidate.job_id.in_(job_ids)))
    session.execute(delete(Job).where(or_(Job.project_id == SEED_PROJECT_ID, Job.id.in_(seed_job_ids))))
    session.execute(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
    session.execute(delete(Project).where(Project.id == SEED_PROJECT_ID))
    session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local project/job/candidate mock data.")
    parser.add_argument(
        "--database-url",
        default=None,
        help=f"SQLAlchemy database URL. Defaults to PROJECT_DATABASE_URL/DATABASE_URL or {project_database_url()}.",
    )
    args = parser.parse_args()

    summary = seed_project_mock_data(args.database_url)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
