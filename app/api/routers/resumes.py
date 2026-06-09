from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy.orm import Session

import app.core.orchestrator as orchestrator
import app.core.resume_ingestion as resume_ingestion
from app.db.session import get_project_session
from app.models import Job, Project
from app.schemas.common import CamelModel


router = APIRouter(tags=["resumes"])


class LocalResumeImportRequest(CamelModel):
    project_id: str = Field(min_length=1, max_length=64)
    job_id: str = Field(min_length=1, max_length=64)
    file_path: str = Field(min_length=1)


class LocalResumeImportResponse(CamelModel):
    task_id: str
    scenario: str
    status: str


@router.post("/resumes/local-import", response_model=LocalResumeImportResponse)
def local_resume_import(request: LocalResumeImportRequest) -> LocalResumeImportResponse:
    if not Path(request.file_path).is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    snapshot = resume_ingestion.start_resume_import_task(
        project_id=request.project_id,
        job_id=request.job_id,
        file_path=request.file_path,
        task_store=orchestrator.task_store,
    )
    return LocalResumeImportResponse(
        task_id=snapshot["task_id"],
        scenario=snapshot["scenario_id"],
        status=snapshot["status"],
    )


@router.post("/projects/{project_id}/jobs/{job_id}/upload-resumes", response_model=LocalResumeImportResponse)
async def upload_project_resume(
    project_id: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_project_session),
) -> LocalResumeImportResponse:
    _require_project_job(session, project_id, job_id)
    saved_path = await _save_upload(project_id, job_id, file)
    snapshot = resume_ingestion.create_resume_import_task(
        project_id=project_id,
        job_id=job_id,
        file_path=str(saved_path),
        task_store=orchestrator.task_store,
    )
    background_tasks.add_task(
        resume_ingestion.run_resume_import_task,
        snapshot["task_id"],
        project_id=project_id,
        job_id=job_id,
        file_path=str(saved_path),
        task_store=orchestrator.task_store,
    )
    return LocalResumeImportResponse(
        task_id=snapshot["task_id"],
        scenario=snapshot["scenario_id"],
        status=snapshot["status"],
    )


def _require_project_job(session: Session, project_id: str, job_id: str) -> None:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    job = session.get(Job, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Job not found in project: {job_id}")


async def _save_upload(project_id: str, job_id: str, file: UploadFile) -> Path:
    filename = _safe_upload_filename(file.filename or "resume")
    upload_dir = Path("data") / "uploads" / project_id / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = (upload_dir / f"{uuid4().hex[:12]}-{filename}").resolve()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded resume file is empty")
    saved_path.write_bytes(content)
    return saved_path


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "resume"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return cleaned[:120] or "resume"
