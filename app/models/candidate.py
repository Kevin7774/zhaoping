from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ProjectBase


class Candidate(ProjectBase):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    current_company: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(256))

    job_links: Mapped[list["JobCandidate"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class JobCandidate(ProjectBase):
    __tablename__ = "job_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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

    job: Mapped["Job"] = relationship(back_populates="candidate_links")
    candidate: Mapped[Candidate] = relationship(back_populates="job_links")

    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_job_candidates_match_score_range"),
        UniqueConstraint("job_id", "candidate_id", name="uq_job_candidates_job_candidate"),
    )
