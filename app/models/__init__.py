from __future__ import annotations

from app.models.base import ProjectBase
from app.models.candidate import Candidate, CandidateSearchSchedule, JobCandidate
from app.models.job import Job
from app.models.outreach import OutreachDraft, OutreachHistory
from app.models.project import Project
from app.models.report import WeeklyReportRecord
from app.models.segment import Segment

__all__ = [
    "Candidate",
    "CandidateSearchSchedule",
    "Job",
    "JobCandidate",
    "OutreachDraft",
    "OutreachHistory",
    "Project",
    "ProjectBase",
    "Segment",
    "WeeklyReportRecord",
]
