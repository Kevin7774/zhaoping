from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ProjectBase


class Job(ProjectBase):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sourcing", index=True)
    seniority: Mapped[str | None] = mapped_column(String(64))
    responsibilities: Mapped[list[str] | None] = mapped_column(JSON)
    must_have_skills: Mapped[list[str] | None] = mapped_column(JSON)
    nice_to_have_skills: Mapped[list[str] | None] = mapped_column(JSON)
    target_companies: Mapped[list[str] | None] = mapped_column(JSON)
    exclusion_signals: Mapped[list[str] | None] = mapped_column(JSON)
    interview_questions: Mapped[list[str] | None] = mapped_column(JSON)
    scoring_rubric: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    search_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    project: Mapped["Project"] = relationship(back_populates="jobs")
    candidate_links: Mapped[list["JobCandidate"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("headcount >= 0", name="ck_jobs_headcount_non_negative"),
    )
