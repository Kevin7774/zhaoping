from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
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

    project: Mapped["Project"] = relationship(back_populates="jobs")
    candidate_links: Mapped[list["JobCandidate"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("headcount >= 0", name="ck_jobs_headcount_non_negative"),
    )
