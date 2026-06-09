from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ProjectBase


class Candidate(ProjectBase):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128))
    current_company: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(256))
    github_url: Mapped[str | None] = mapped_column(String(512))
    linkedin_url: Mapped[str | None] = mapped_column(String(512))
    homepage_url: Mapped[str | None] = mapped_column(String(512))
    source_platform: Mapped[str | None] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(String(512))
    evidence: Mapped[list[str] | None] = mapped_column(JSON)
    skills: Mapped[list[str] | None] = mapped_column(JSON)
    created_from_task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    job_links: Mapped[list["JobCandidate"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class JobCandidate(ProjectBase):
    __tablename__ = "job_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pipeline_status: Mapped[str] = mapped_column(String(32), nullable=False, default="sourced", index=True)
    evidence: Mapped[list[str] | None] = mapped_column(JSON)
    source_task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    job: Mapped["Job"] = relationship(back_populates="candidate_links")
    candidate: Mapped[Candidate] = relationship(back_populates="job_links")

    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_job_candidates_match_score_range"),
        UniqueConstraint("job_id", "candidate_id", name="uq_job_candidates_job_candidate"),
    )
