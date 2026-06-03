from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.orchestrator import get_meta, start_task, task_store
from app.core.router import get_router
from app.rag.ingest_worker import process_and_vectorize_resume

app = FastAPI(title="Robot Talent Agent MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    file_path: str
    candidate_id: str
    write_database: bool = False


class MatchRequest(BaseModel):
    query: str
    top_k: int = 5


class RunRequest(BaseModel):
    scenario: Literal["A", "B", "C", "D"]
    input: str


class ConfirmRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edits: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/scenarios/meta")
def scenarios_meta() -> dict:
    """Dynamic protocol: agents + scenario step plans for the frontend to render."""
    return get_meta()


@app.post("/scenarios/run")
def scenarios_run(request: RunRequest) -> dict:
    if not request.input.strip():
        raise HTTPException(status_code=422, detail="input must not be empty")
    task = start_task(request.scenario, request.input.strip())
    return {"task_id": task.task_id, "scenario": task.scenario, "status": task.status}


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.post("/tasks/{task_id}/confirm")
def confirm_task(task_id: str, request: ConfirmRequest) -> dict:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if task.status != "awaiting_human":
        raise HTTPException(status_code=409, detail=f"Task is not awaiting human input (status={task.status})")
    ok = task_store.confirm(task_id, request.decision, request.edits)
    if not ok:
        raise HTTPException(status_code=409, detail="Task could not accept confirmation")
    return task_store.snapshot(task_id)


@app.post("/resumes/ingest")
def ingest_resume(request: IngestRequest) -> dict:
    if not Path(request.file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    markdown = process_and_vectorize_resume(
        file_path=request.file_path,
        candidate_id=request.candidate_id,
        write_database=request.write_database,
    )
    return {
        "candidate_id": request.candidate_id,
        "markdown_preview": markdown[:500],
    }


@app.post("/jobs/match")
def match_candidates(request: MatchRequest) -> dict:
    router = get_router()
    embedding = router.embedding().embed_texts([request.query])
    results = router.vector_store().search(embedding[0].tolist(), top_k=request.top_k)
    return {"results": results}


@app.get("/review/feedback")
def feedback_placeholder() -> dict:
    return {"status": "pending_implementation"}
