from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from queue import Empty
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.api.routers.projects import router as projects_router
from app.core.env_store import save_env_values
from app.core.intelligence_archive import IntelligenceArchive
from app.core.integration_status import get_integration_status
from app.core.orchestrator import (
    cancel_task,
    create_workflow_session,
    get_meta,
    get_workflow_meta,
    retry_task,
    retry_workflow_node,
    run_workflow_node,
    skip_workflow_node,
    start_task,
    task_store,
)
from app.core.router import get_router
from app.core.workflow_dsl import WorkflowDefinition, WorkflowValidationException
from app.core.workflow_runner import WorkflowTaskRunner
from app.rag.ingest_worker import process_and_vectorize_resume
from app.schemas.workflows import (
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowValidateRequest,
    WorkflowValidateResponse,
)

app = FastAPI(title="Robot Talent Agent MVP")
FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
FRONTEND_INDEX_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Has-More"],
)

app.include_router(projects_router)


@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    """Support the frontend's /api prefix outside the Vite dev proxy."""

    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


class IngestRequest(BaseModel):
    file_path: str
    candidate_id: str
    write_database: bool = False


class MatchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    service: Optional[str] = None


class SearchEvidenceRequest(SearchRequest):
    claim: Optional[str] = None


class SearchArchiveRequest(SearchEvidenceRequest):
    artifact_type: Literal["evidence", "brief"] = "brief"


class WatchlistItem(BaseModel):
    name: str
    query: str
    claim: Optional[str] = None
    tags: list[str] = []


class SearchWatchlistRequest(BaseModel):
    items: list[WatchlistItem]
    limit: int = 10
    service: Optional[str] = None
    archive: bool = True


class RunRequest(BaseModel):
    scenario: str
    input: str
    team_constraint: str = "真机泛化"
    aperture_weight: float = 0.7
    frontend_state: dict[str, Any] = Field(default_factory=dict)


class WorkflowSessionRequest(RunRequest):
    pass


class AtomicNodeRunRequest(BaseModel):
    decision: Optional[Literal["approve", "edit", "reject"]] = None
    edits: Optional[str] = None


class AtomicNodeSkipRequest(BaseModel):
    reason: Optional[str] = None


class ConfirmRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edits: Optional[str] = None
    action: Optional[Literal["approve", "edit", "reject"]] = None
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_action_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "decision" not in normalized and "action" in normalized:
            normalized["decision"] = normalized["action"]
        if "edits" not in normalized and isinstance(normalized.get("data"), dict):
            data = normalized["data"]
            edits = data.get("draft") or data.get("body") or data.get("edits")
            if edits is not None:
                normalized["edits"] = edits if isinstance(edits, str) else json.dumps(edits, ensure_ascii=False)
        return normalized


class ProbeFeedbackRequest(BaseModel):
    probe_id: str
    answered: bool
    note: Optional[str] = None


class RSIEvaluateRequest(BaseModel):
    suite: str = "candidate_evaluation_core"
    threshold: Optional[float] = None
    service: Optional[str] = None
    cases: Optional[list[dict[str, Any]]] = None
    mode: Literal["local", "full"] = "local"
    allow_live: bool = False
    max_live_results: int = 1
    search_service: Optional[str] = None
    llm_service: Optional[str] = "openrouter_evidence_judge"


class EnvSaveRequest(BaseModel):
    values: dict[str, str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/scenarios/meta")
def scenarios_meta() -> dict:
    """Dynamic protocol: agents + scenario step plans for the frontend to render."""
    return get_meta()


@app.get("/workflow/meta")
def workflow_meta() -> dict:
    """Atomic workflow protocol: scenarios plus individually controllable nodes."""

    return get_workflow_meta()


@app.get("/integrations/status")
def integrations_status() -> dict:
    """Safe service/API-key status for the frontend. Secret values are never returned."""
    return get_integration_status()


@app.post("/integrations/env")
def integrations_env_save(request: EnvSaveRequest, http_request: Request) -> dict:
    """Save allowlisted local environment variables without returning secret values."""

    if not _is_local_env_save_request(http_request):
        raise HTTPException(status_code=403, detail="Environment saving is restricted to local requests.")
    try:
        result = save_env_values(request.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "status": "saved",
        "env_path": result["env_path"],
        "updated": result["updated"],
    }


@app.post("/rsi/evaluate")
def rsi_evaluate(request: RSIEvaluateRequest) -> dict:
    router = get_router()
    provider = _resolve_evaluation_provider(request.service, router=router)
    if not hasattr(provider, "evaluate"):
        raise HTTPException(status_code=422, detail="Selected evaluation service does not support RSI evaluation")
    try:
        return provider.evaluate(
            suite=request.suite,
            cases=request.cases,
            threshold=request.threshold,
            mode=request.mode,
            allow_live=request.allow_live,
            max_live_results=request.max_live_results,
            router=router,
            search_service=request.search_service,
            llm_service=request.llm_service,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/search/plan")
def search_plan(request: SearchRequest) -> dict:
    query = _normalized_query(request.query)
    limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    if not hasattr(provider, "plan"):
        raise HTTPException(status_code=422, detail="Selected search service does not support planning")
    try:
        return provider.plan(query, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/search/run")
def search_run(request: SearchRequest) -> dict:
    query = _normalized_query(request.query)
    limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    try:
        results = provider.search(query, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "query": query,
        "service": request.service,
        "limit": limit,
        "results": results,
    }


@app.post("/search/evidence")
def search_evidence(request: SearchEvidenceRequest) -> dict:
    query = _normalized_query(request.query)
    limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    if not hasattr(provider, "evidence"):
        raise HTTPException(status_code=422, detail="Selected search service does not support evidence records")
    try:
        return provider.evidence(query, limit=limit, claim=request.claim.strip() if request.claim else None)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/search/brief")
def search_brief(request: SearchEvidenceRequest) -> dict:
    query = _normalized_query(request.query)
    limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    if not hasattr(provider, "brief"):
        raise HTTPException(status_code=422, detail="Selected search service does not support intelligence briefs")
    try:
        return provider.brief(query, limit=limit, claim=request.claim.strip() if request.claim else None)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/search/archive")
def search_archive(request: SearchArchiveRequest) -> dict:
    query = _normalized_query(request.query)
    limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    claim = request.claim.strip() if request.claim else None
    try:
        if request.artifact_type == "evidence":
            if not hasattr(provider, "evidence"):
                raise HTTPException(status_code=422, detail="Selected search service does not support evidence records")
            artifact = provider.evidence(query, limit=limit, claim=claim)
        else:
            if not hasattr(provider, "brief"):
                raise HTTPException(status_code=422, detail="Selected search service does not support intelligence briefs")
            artifact = provider.brief(query, limit=limit, claim=claim)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    archive_result = IntelligenceArchive().append(request.artifact_type, artifact)
    return {
        **archive_result,
        "query": query,
        "claim": claim,
    }


@app.get("/search/archive/recent")
def search_archive_recent(limit: int = 20) -> dict:
    normalized_limit = _normalized_limit(limit)
    return {
        "limit": normalized_limit,
        "records": IntelligenceArchive().recent(limit=normalized_limit),
    }


@app.get("/search/archive/diff")
def search_archive_diff(
    artifact_type: Optional[Literal["evidence", "brief"]] = None,
    watchlist_name: Optional[str] = None,
) -> dict:
    return IntelligenceArchive().diff_latest(
        artifact_type=artifact_type,
        watchlist_name=watchlist_name.strip() if watchlist_name else None,
    )


@app.post("/search/watchlist/run")
def search_watchlist_run(request: SearchWatchlistRequest) -> dict:
    if not request.items:
        raise HTTPException(status_code=422, detail="items must not be empty")
    normalized_limit = _normalized_limit(request.limit)
    provider = _resolve_search_provider(request.service)
    if not hasattr(provider, "brief"):
        raise HTTPException(status_code=422, detail="Selected search service does not support intelligence briefs")

    archive = IntelligenceArchive()
    results = []
    for item in request.items[:20]:
        query = _normalized_query(item.query)
        claim = item.claim.strip() if item.claim else None
        try:
            brief = provider.brief(query, limit=normalized_limit, claim=claim)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        brief["watchlist_item"] = {
            "name": item.name.strip() or query,
            "tags": item.tags,
        }
        archive_result = archive.append("brief", brief) if request.archive else None
        results.append(
            {
                "name": item.name.strip() or query,
                "query": query,
                "claim": claim,
                "tags": item.tags,
                "status": brief["executive_summary"]["status"],
                "record_count": brief["evidence_review"]["record_count"],
                "top_source_keys": [
                    evidence["source_key"]
                    for evidence in brief["priority_evidence"][:5]
                ],
                "archive": archive_result,
            }
        )

    return {
        "item_count": len(results),
        "archived": request.archive,
        "results": results,
    }


@app.post("/scenarios/run")
def scenarios_run(request: RunRequest) -> dict:
    if not request.input.strip():
        raise HTTPException(status_code=422, detail="input must not be empty")
    scenario = request.scenario.strip()
    if not scenario:
        raise HTTPException(status_code=422, detail="scenario must not be empty")
    try:
        task = start_task(
            scenario,
            request.input.strip(),
            team_constraint=(request.team_constraint or "真机泛化").strip() or "真机泛化",
            aperture_weight=max(0.0, min(float(request.aperture_weight), 1.0)),
            frontend_state=request.frontend_state,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown scenario: {scenario}") from exc
    return {"task_id": task.task_id, "scenario": task.scenario, "status": task.status}


@app.post("/workflows/validate", response_model=WorkflowValidateResponse)
def workflows_validate(request: WorkflowValidateRequest) -> WorkflowValidateResponse:
    try:
        workflow = WorkflowDefinition.model_validate(request.workflow)
    except WorkflowValidationException as exc:
        return WorkflowValidateResponse(valid=False, errors=[{"message": str(exc)}])
    except Exception as exc:
        return WorkflowValidateResponse(valid=False, errors=[{"message": str(exc)}])
    return WorkflowValidateResponse(
        valid=True,
        workflow_id=workflow.id,
        step_count=len(workflow.steps),
        dependencies=workflow.dependency_summary(),
    )


@app.post("/workflows/run", response_model=WorkflowRunResponse)
def workflows_run(request: WorkflowRunRequest) -> WorkflowRunResponse:
    try:
        workflow = WorkflowDefinition.model_validate(request.workflow)
    except WorkflowValidationException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task_id = WorkflowTaskRunner().start(
        workflow,
        request.input,
        auto_run=request.auto_run,
        conversation_id=request.conversation_id,
    )
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=500, detail="JSON workflow task creation failed")
    return WorkflowRunResponse(task_id=task_id, workflow_id=workflow.id, status=snapshot["status"])


@app.post("/workflow/sessions")
def workflow_session_create(request: WorkflowSessionRequest) -> dict:
    if not request.input.strip():
        raise HTTPException(status_code=422, detail="input must not be empty")
    scenario = request.scenario.strip()
    if not scenario:
        raise HTTPException(status_code=422, detail="scenario must not be empty")
    try:
        return create_workflow_session(
            scenario,
            request.input.strip(),
            team_constraint=(request.team_constraint or "真机泛化").strip() or "真机泛化",
            aperture_weight=max(0.0, min(float(request.aperture_weight), 1.0)),
            frontend_state=request.frontend_state,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown scenario: {scenario}") from exc


@app.post("/workflow/sessions/{task_id}/nodes/{node_id}/run")
def workflow_node_run(task_id: str, node_id: str, request: AtomicNodeRunRequest | None = None) -> dict:
    try:
        snapshot = run_workflow_node(
            task_id,
            node_id,
            decision=request.decision if request else None,
            edits=(request.edits.strip() if request and request.edits else None),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.post("/workflow/sessions/{task_id}/nodes/{node_id}/retry")
def workflow_node_retry(task_id: str, node_id: str, request: AtomicNodeRunRequest | None = None) -> dict:
    try:
        snapshot = retry_workflow_node(
            task_id,
            node_id,
            decision=request.decision if request else None,
            edits=(request.edits.strip() if request and request.edits else None),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.post("/workflow/sessions/{task_id}/nodes/{node_id}/skip")
def workflow_node_skip(task_id: str, node_id: str, request: AtomicNodeSkipRequest | None = None) -> dict:
    try:
        snapshot = skip_workflow_node(
            task_id,
            node_id,
            reason=(request.reason.strip() if request and request.reason else "用户跳过原子节点"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    snapshot = task_store.snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, request: Request):
    if task_store.snapshot(task_id) is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    queue = task_store.subscribe(task_id)

    async def event_generator():
        last_id = 0
        try:
            for event in task_store.events_after(task_id, after_id=0):
                last_id = max(last_id, int(event["id"]))
                yield _format_sse(event)
            snapshot = task_store.snapshot(task_id)
            if snapshot and snapshot["status"] in {"done", "error", "cancelled"}:
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(queue.get, True, 5)
                except Empty:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue
                event_id = int(event["id"])
                if event_id <= last_id:
                    continue
                last_id = event_id
                yield _format_sse(event)
                if event.get("status") in {"done", "error", "cancelled"}:
                    break
        finally:
            task_store.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/tasks/{task_id}/cancel")
def cancel_task_route(task_id: str) -> dict:
    snapshot = cancel_task(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return snapshot


@app.post("/tasks/{task_id}/retry")
def retry_task_route(task_id: str) -> dict:
    task = retry_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return {"task_id": task.task_id, "scenario": task.scenario, "status": task.status}


@app.post("/tasks/{task_id}/confirm")
def confirm_task(task_id: str, request: ConfirmRequest) -> dict:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if task.status != "awaiting_human":
        raise HTTPException(status_code=409, detail=f"Task is not awaiting human input (status={task.status})")
    runtime = (task.frontend_state or {}).get("json_workflow_runtime")
    if runtime:
        return WorkflowTaskRunner().resume(
            task_id,
            request.decision,
            {"edits": request.edits, "data": request.data},
        )
    ok = task_store.confirm(task_id, request.decision, request.edits)
    if not ok:
        raise HTTPException(status_code=409, detail="Task could not accept confirmation")
    return task_store.snapshot(task_id)


@app.post("/tasks/{task_id}/probe-feedback")
def probe_feedback(task_id: str, request: ProbeFeedbackRequest) -> dict:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if not request.probe_id.strip():
        raise HTTPException(status_code=422, detail="probe_id must not be empty")
    result = task_store.record_probe_feedback(
        task_id,
        {
            "probe_id": request.probe_id.strip(),
            "answered": request.answered,
            "note": request.note.strip() if request.note else None,
        },
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if result["status"] == "not_ready":
        raise HTTPException(status_code=409, detail="Task result is not ready for probe feedback")
    return result


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


def _normalized_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="query must not be empty")
    return normalized


def _normalized_limit(limit: int) -> int:
    return max(1, min(int(limit), 50))


def _is_local_env_save_request(request: Request) -> bool:
    if os.environ.get("ALLOW_REMOTE_ENV_SAVE", "").lower() in {"1", "true", "yes"}:
        return True
    client_host = request.client.host if request.client else ""
    return client_host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _resolve_search_provider(service_name: str | None):
    normalized_service = service_name.strip() if service_name else None
    try:
        return get_router().search(normalized_service or None)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve_evaluation_provider(service_name: str | None, router=None):
    normalized_service = service_name.strip() if service_name else None
    try:
        return (router or get_router()).evaluation(normalized_service or None)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _format_sse(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str) -> FileResponse:
    """Serve the production frontend bundle when frontend/dist exists."""
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found. Run `pnpm --dir frontend build` first.")

    root = FRONTEND_DIST_DIR.resolve()
    requested = (FRONTEND_DIST_DIR / full_path).resolve()
    if (requested == root or root in requested.parents) and requested.is_file():
        if requested == FRONTEND_INDEX.resolve() or requested.suffix == ".html":
            return FileResponse(requested, headers=FRONTEND_INDEX_HEADERS)
        return FileResponse(requested)
    return FileResponse(FRONTEND_INDEX, headers=FRONTEND_INDEX_HEADERS)
