from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import project_session_factory
from app.models import CandidateSearchSchedule, Job


class CandidateSearchScheduler(threading.Thread):
    """Persistent poller that starts scheduled scenario B sourcing tasks."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | Callable[[], sessionmaker[Session]] | None = None,
        poll_interval_seconds: float | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._session_factory = session_factory or project_session_factory
        self._poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else _poll_interval_seconds()
        self._stop_event = threading.Event()
        self._started_once = False
        self._lock = threading.Lock()

    def start_once(self) -> None:
        with self._lock:
            if self._started_once:
                return
            self._started_once = True
            self.start()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_due_once()
            except Exception:
                # Scheduling must not take down the API process. Individual task
                # failures are visible on the spawned task itself.
                pass
            self._stop_event.wait(self._poll_interval_seconds)

    def run_due_once(self, now: datetime | None = None) -> int:
        now = _utc(now or datetime.now(timezone.utc))
        launched = 0
        factory = self._resolve_session_factory()
        with factory() as session:
            self._sync_last_statuses(session)
            rows = session.execute(
                select(CandidateSearchSchedule, Job)
                .join(Job, Job.id == CandidateSearchSchedule.job_id)
                .where(CandidateSearchSchedule.enabled.is_(True))
                .order_by(CandidateSearchSchedule.id)
            ).all()
            for schedule, job in rows:
                if schedule.next_run_at is None or _utc(schedule.next_run_at) > now:
                    continue
                if _last_task_is_active(schedule.last_task_id):
                    continue
                task = _start_candidate_search_task(schedule, job)
                schedule.last_task_id = task.task_id
                schedule.last_status = task.status
                schedule.last_run_at = now
                schedule.last_error = None
                schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
                schedule.updated_at = now
                launched += 1
            session.commit()
        return launched

    def _resolve_session_factory(self) -> sessionmaker[Session]:
        if callable(self._session_factory) and not isinstance(self._session_factory, sessionmaker):
            return self._session_factory()
        return self._session_factory  # type: ignore[return-value]

    def _sync_last_statuses(self, session: Session) -> None:
        for schedule in session.scalars(
            select(CandidateSearchSchedule).where(CandidateSearchSchedule.last_task_id.is_not(None))
        ):
            snapshot = _task_snapshot(schedule.last_task_id)
            if snapshot is None:
                continue
            schedule.last_status = snapshot.get("status") or schedule.last_status


def candidate_search_scheduler_enabled() -> bool:
    return os.environ.get("CANDIDATE_SEARCH_SCHEDULER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _poll_interval_seconds() -> float:
    raw = os.environ.get("CANDIDATE_SEARCH_SCHEDULER_POLL_SECONDS")
    if raw is None:
        return 60.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _start_candidate_search_task(schedule: CandidateSearchSchedule, job: Job):
    from app.core import orchestrator

    return orchestrator.start_task(
        "B",
        f"请围绕「{job.title}」自动搜索候选人，重点关注 GitHub、技术项目、实验室、公司页面和候选人证据。",
        team_constraint="真机泛化",
        aperture_weight=0.7,
        frontend_state={
            "source": "CandidateSearchScheduler",
            "project_id": schedule.project_id,
            "job_profile_id": schedule.job_id,
            "job_title": job.title,
            "jobTitle": job.title,
            "action": "find_candidates",
            "schedule_id": schedule.id,
            "auto_confirm_human_gate": True,
        },
    )


def _last_task_is_active(task_id: str | None) -> bool:
    if not task_id:
        return False
    snapshot = _task_snapshot(task_id)
    if snapshot is None:
        return False
    return snapshot.get("status") in {"processing", "awaiting_human"}


def _task_snapshot(task_id: str | None) -> dict | None:
    if not task_id:
        return None
    from app.core import orchestrator

    return orchestrator.task_store.snapshot(task_id)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
