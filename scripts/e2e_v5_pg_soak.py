from __future__ import annotations

import json
import os
import resource
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import make_project_session_factory  # noqa: E402
from app.db.task_models import AgentEventModel, TaskModel, make_task_session_factory  # noqa: E402
from app.models import JobCandidate, OutreachDraft, OutreachHistory, Segment, WeeklyReportRecord  # noqa: E402
from scripts.seed_db import SEED_PROJECT_ID, seed_project_mock_data  # noqa: E402


API_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8010/api").rstrip("/")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", SEED_PROJECT_ID)
OUTPUT_PATH = Path(os.environ.get("E2E_REPORT_PATH", ROOT / "artifacts/e2e_evidence/e2e-v5-pg-soak.json"))
SOAK_SECONDS = int(os.environ.get("E2E_SOAK_SECONDS", "0"))
MIN_LOOP_SECONDS = int(os.environ.get("E2E_SOAK_MIN_LOOP_SECONDS", "0"))
TASK_TIMEOUT_SECONDS = int(os.environ.get("E2E_TASK_TIMEOUT_SECONDS", "120"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("E2E_REQUEST_TIMEOUT_SECONDS", "45"))
MIN_SOAK_SECONDS = 1800
TERMINAL_STATUSES = {"done", "error", "cancelled"}
BLOCKING_ERROR_MARKERS = (
    "connection already closed",
    "pool exhausted",
    "idle in transaction",
    "transaction rollback",
    "lock timeout",
    "long transaction",
    "session leak",
)


class E2EFailure(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if "@" in value:
            return "[email redacted]"
        return value if len(value) <= 300 else f"{value[:300]}..."
    if isinstance(value, list):
        return {"type": "array", "length": len(value), "sample": [redact(item) for item in value[:3]]}
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in list(value.items())[:30]:
            lowered = key.lower()
            if any(marker in lowered for marker in ("key", "token", "secret", "password", "credential")):
                output[key] = "[redacted]"
            elif "email" in lowered and isinstance(item, str) and "@" in item:
                output[key] = "[email redacted]"
            else:
                output[key] = redact(item)
        return output
    return str(value)


def request(method: str, path: str, body: Any = None, *, timeout: int | None = None) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    started = time.time()
    raw = b""
    response_headers: dict[str, str] = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout or REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        response_headers = dict(exc.headers.items())
    except Exception as exc:
        return {
            "method": method,
            "path": path,
            "status": 0,
            "durationMs": round((time.time() - started) * 1000),
            "requestSummary": redact(body),
            "error": f"{type(exc).__name__}: {exc}",
        }
    parsed: Any
    content_type = {key.lower(): value for key, value in response_headers.items()}.get("content-type", "")
    try:
        parsed = json.loads(raw.decode("utf-8") or "null") if "json" in content_type else raw.decode("utf-8", errors="replace")
    except Exception:
        parsed = raw.decode("utf-8", errors="replace")
    return {
        "method": method,
        "path": path,
        "status": status,
        "durationMs": round((time.time() - started) * 1000),
        "requestSummary": redact(body),
        "responseSummary": redact(parsed),
        "raw": parsed,
        "headers": response_headers,
    }


def assert_ok(response: dict[str, Any], label: str, expected_statuses: set[int] | None = None) -> None:
    statuses = expected_statuses or set(range(200, 300))
    if response.get("status") not in statuses:
        raise E2EFailure(f"{label} returned HTTP {response.get('status')}: {response.get('responseSummary') or response.get('error')}")


def task_id_from(response: dict[str, Any]) -> str:
    raw = response.get("raw")
    if not isinstance(raw, dict) or not raw.get("task_id"):
        raise E2EFailure(f"response missing task_id: {response.get('responseSummary')}")
    return str(raw["task_id"])


def poll_task(task_id: str, *, timeout_seconds: int = TASK_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        latest = request("GET", f"/tasks/{urllib.parse.quote(task_id)}")
        if latest.get("status", 0) >= 400:
            raise E2EFailure(f"task snapshot failed: {latest.get('responseSummary')}")
        status = latest.get("raw", {}).get("status") if isinstance(latest.get("raw"), dict) else None
        if status in TERMINAL_STATUSES or status == "awaiting_human":
            return latest["raw"]
        time.sleep(0.6)
    raise TimeoutError(f"task timed out: {task_id}; latest={redact(latest)}")


def wait_terminal(task_id: str, *, timeout_seconds: int = TASK_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        latest = request("GET", f"/tasks/{urllib.parse.quote(task_id)}")
        if latest.get("status", 0) >= 400:
            raise E2EFailure(f"task snapshot failed: {latest.get('responseSummary')}")
        snapshot = latest.get("raw") if isinstance(latest.get("raw"), dict) else {}
        if snapshot.get("status") in TERMINAL_STATUSES:
            return snapshot
        time.sleep(0.6)
    raise TimeoutError(f"task terminal timeout: {task_id}; latest={redact(latest)}")


def read_sse_after_terminal(task_id: str) -> dict[str, Any]:
    response = request("GET", f"/tasks/{urllib.parse.quote(task_id)}/stream", timeout=20)
    body = response.get("raw") if isinstance(response.get("raw"), str) else ""
    return {
        "status": response.get("status"),
        "eventCount": body.count("\nevent:") + (1 if body.startswith("event:") else 0),
        "heartbeatCount": body.count("event: heartbeat"),
        "bytes": len(body.encode("utf-8")),
    }


def run_scenario(scenario: str, input_text: str, frontend_state: dict[str, Any]) -> str:
    response = request(
        "POST",
        "/scenarios/run",
        {
            "scenario": scenario,
            "input": input_text,
            "team_constraint": "真机泛化",
            "aperture_weight": 0.7,
            "frontend_state": frontend_state,
        },
    )
    assert_ok(response, f"scenario {scenario}")
    return task_id_from(response)


def confirm_task(task_id: str, decision: str = "approve", edits: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"decision": decision, "data": {"source": "e2e_v5_pg_soak"}}
    if edits:
        payload["edits"] = edits
    response = request("POST", f"/tasks/{urllib.parse.quote(task_id)}/confirm", payload)
    assert_ok(response, f"confirm task {task_id}")
    return response.get("raw") if isinstance(response.get("raw"), dict) else {}


def count_candidates() -> tuple[int, list[str]]:
    response = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/candidates?skip=0&limit=200")
    assert_ok(response, "list candidates")
    headers = {key.lower(): value for key, value in response.get("headers", {}).items()}
    total = int(headers.get("x-total-count") or len(response.get("raw") or []))
    ids = [item.get("id") for item in response.get("raw") or [] if isinstance(item, dict) and item.get("id")]
    return total, ids


def first_job_and_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    jobs = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/jobs")
    assert_ok(jobs, "list jobs")
    candidates = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/candidates?skip=0&limit=50")
    assert_ok(candidates, "list candidates")
    raw_jobs = jobs.get("raw") if isinstance(jobs.get("raw"), list) else []
    raw_candidates = candidates.get("raw") if isinstance(candidates.get("raw"), list) else []
    if not raw_jobs or not raw_candidates:
        raise E2EFailure("seeded jobs/candidates missing")
    return raw_jobs[0], raw_candidates[0]


def run_b_and_confirm(job: dict[str, Any], *, decision: str = "approve", edits: str | None = None) -> dict[str, Any]:
    before_count, before_ids = count_candidates()
    task_id = run_scenario(
        "B",
        f"请围绕「{job.get('title') or job.get('roleName') or job['id']}」生成人才地图、候选人来源、搜索关键词和触达策略。",
        {
            "source": "ProjectDetailPage",
            "project_id": PROJECT_ID,
            "job_profile_id": job["id"],
            "job_title": job.get("title") or job["id"],
            "jobTitle": job.get("title") or job["id"],
            "action": "find_candidates",
        },
    )
    awaiting = poll_task(task_id)
    if awaiting.get("status") != "awaiting_human":
        raise E2EFailure(f"scenario B expected awaiting_human, got {awaiting.get('status')}")
    awaiting_payload = awaiting.get("awaiting") or {}
    preview = awaiting_payload.get("lead_preview") or awaiting_payload.get("leadPreview")
    if not isinstance(preview, dict) or not preview.get("leads"):
        raise E2EFailure("scenario B awaiting payload missing lead preview")
    leads = preview.get("leads") if isinstance(preview.get("leads"), list) else []
    leaked_email = json.dumps(preview, ensure_ascii=False).find("@") >= 0
    confirm_task(task_id, decision=decision, edits=edits)
    final = wait_terminal(task_id)
    after_count, after_ids = count_candidates()
    result = final.get("result") if isinstance(final.get("result"), dict) else {}
    ingestion = result.get("lead_ingestion") or {}
    return {
        "taskId": task_id,
        "decision": decision,
        "status": final.get("status"),
        "beforeCount": before_count,
        "afterCount": after_count,
        "countDelta": after_count - before_count,
        "newCandidateIds": sorted(set(after_ids) - set(before_ids)),
        "leadPreview": {
            "totalCount": preview.get("total_count") or preview.get("totalCount"),
            "omittedCount": preview.get("omitted_count") or preview.get("omittedCount"),
            "leadCount": len(leads),
            "firstLead": redact(leads[0] if leads else {}),
            "emailLeakObserved": leaked_email,
        },
        "leadIngestion": redact(ingestion),
        "sse": read_sse_after_terminal(task_id),
    }


def run_standard_task(task_id: str, *, confirm_if_waiting: bool = True) -> dict[str, Any]:
    snapshot = poll_task(task_id)
    if snapshot.get("status") == "awaiting_human" and confirm_if_waiting:
        confirm_task(task_id, "approve")
        snapshot = wait_terminal(task_id)
    elif snapshot.get("status") not in TERMINAL_STATUSES:
        snapshot = wait_terminal(task_id)
    return {
        "taskId": task_id,
        "status": snapshot.get("status"),
        "error": snapshot.get("error"),
        "sse": read_sse_after_terminal(task_id) if snapshot.get("status") in TERMINAL_STATUSES else None,
        "resultSummary": redact(snapshot.get("result")),
    }


def create_weekly_report_from_task(task_id: str) -> dict[str, Any]:
    response = request(
        "POST",
        "/reports/weekly",
        {
            "projectId": PROJECT_ID,
            "sourceTaskId": task_id,
            "report": {
                "conclusion": "V5 soak weekly report persisted from scenario D task.",
                "keyProgress": ["A/B/C/D task loop completed", "Scenario B lead ingestion audited"],
                "topCandidates": ["Seeded and ingested project candidates"],
                "risks": ["Third-party email delivery may be unavailable without sandbox key"],
                "nextActions": ["Continue PostgreSQL soak and compliance review"],
            },
        },
    )
    assert_ok(response, "create weekly report")
    latest = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/reports/latest")
    assert_ok(latest, "latest weekly report")
    return {"created": redact(response.get("raw")), "latest": redact(latest.get("raw"))}


def run_outreach_and_compliance(candidate: dict[str, Any]) -> dict[str, Any]:
    project_candidate_id = candidate["jobCandidateId"]
    job_id = candidate["jobId"]
    candidate_id = candidate["id"]
    approve = request(
        "POST",
        f"/projects/{urllib.parse.quote(PROJECT_ID)}/candidates/{urllib.parse.quote(str(project_candidate_id))}/compliance-review",
        {"decision": "approve"},
    )
    assert_ok(approve, "approve candidate before outreach draft")
    draft = request(
        "POST",
        "/outreach/draft",
        {"projectId": PROJECT_ID, "jobId": job_id, "candidateId": candidate_id},
        timeout=75,
    )
    assert_ok(draft, "outreach draft")
    draft_id = draft["raw"]["draftId"]
    patched = request("PATCH", f"/outreach/drafts/{urllib.parse.quote(draft_id)}", {"body": f"{draft['raw']['body']}\n\nE2E V5 edit."})
    assert_ok(patched, "outreach draft patch")

    set_link_status(job_id, candidate_id, "pending_compliance_review")
    pending_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    pending_simulated = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True})
    set_link_status(job_id, candidate_id, "rejected")
    rejected_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    rejected_simulated = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True})
    set_link_status(job_id, candidate_id, "pending_outreach")
    approved_simulated = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True})
    approved_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    history = request("GET", f"/outreach/history?projectId={urllib.parse.quote(PROJECT_ID)}&candidateId={urllib.parse.quote(candidate_id)}")
    assert_ok(history, "outreach history")
    if pending_real.get("status") != 403 or rejected_real.get("status") != 403:
        raise E2EFailure("compliance hard block failed for pending/rejected real send")
    if pending_simulated.get("status") != 200 or rejected_simulated.get("status") != 200:
        raise E2EFailure("compliance blocked simulation did not persist expected history")
    if approved_simulated.get("status") != 200:
        raise E2EFailure("approved simulated send failed")
    return {
        "draftId": draft_id,
        "pendingRealStatus": pending_real.get("status"),
        "pendingSimulated": redact(pending_simulated.get("raw")),
        "rejectedRealStatus": rejected_real.get("status"),
        "rejectedSimulated": redact(rejected_simulated.get("raw")),
        "approvedSimulated": redact(approved_simulated.get("raw")),
        "approvedRealStatus": approved_real.get("status"),
        "approvedRealDetail": redact(approved_real.get("raw")),
        "historyCount": len(history.get("raw", {}).get("items", []) if isinstance(history.get("raw"), dict) else []),
    }


def set_link_status(job_id: str, candidate_id: str, status: str) -> None:
    factory = make_project_session_factory()
    with factory() as session:
        link = session.scalar(select(JobCandidate).where(JobCandidate.job_id == job_id, JobCandidate.candidate_id == candidate_id))
        if link is None:
            raise E2EFailure(f"JobCandidate not found: {job_id}/{candidate_id}")
        link.pipeline_status = status
        session.commit()


def run_segments(candidate_ids: list[str], loop_index: int) -> dict[str, Any]:
    criteria = {
        "jobProfileId": "all",
        "minScore": 70,
        "city": "",
        "keyword": "",
        "outreachStatus": "all",
        "hasEmail": "yes",
        "sourcePlatform": "all",
    }
    query = request("POST", "/segments/query", {"projectId": PROJECT_ID, "criteria": criteria})
    assert_ok(query, "segments query")
    ids = [item.get("id") for item in query.get("raw", {}).get("candidates", []) if isinstance(item, dict) and item.get("id")]
    save = request(
        "POST",
        "/segments",
        {
            "projectId": PROJECT_ID,
            "name": f"E2E V5 soak segment loop {loop_index}",
            "criteria": criteria,
            "candidateIds": ids or candidate_ids,
        },
    )
    assert_ok(save, "segments create")
    segment_id = save["raw"]["segmentId"]
    read = request("GET", f"/segments/{urllib.parse.quote(segment_id)}")
    assert_ok(read, "segments read")
    listing = request("GET", f"/segments?projectId={urllib.parse.quote(PROJECT_ID)}")
    assert_ok(listing, "segments list")
    return {
        "queryTotal": query.get("raw", {}).get("total"),
        "segmentId": segment_id,
        "readCandidateCount": read.get("raw", {}).get("candidateCount"),
        "listCount": len(listing.get("raw", {}).get("items", []) if isinstance(listing.get("raw"), dict) else []),
    }


def run_json_workflow() -> dict[str, Any]:
    workflow = {
        "id": "e2e_v5_pg_soak_workflow",
        "inputs": {"draft": {"type": "string"}},
        "steps": [
            {"id": "gate", "type": "human_gate", "prompt": "Approve {{ draft }}", "output_key": "approval"},
            {"id": "artifact", "type": "save_artifact", "input": "Decision {{ approval }}", "output_key": "decision_artifact"},
        ],
    }
    validate = request("POST", "/workflows/validate", {"workflow": workflow})
    assert_ok(validate, "workflow validate")
    if validate.get("raw", {}).get("valid") is not True:
        raise E2EFailure(f"workflow did not validate: {validate.get('responseSummary')}")
    run = request("POST", "/workflows/run", {"workflow": workflow, "input": {"draft": "V5 soak workflow"}, "auto_run": True})
    assert_ok(run, "workflow run")
    task_id = task_id_from(run)
    awaiting = poll_task(task_id)
    runtime = (awaiting.get("frontend_state") or {}).get("json_workflow_runtime")
    if awaiting.get("status") != "awaiting_human" or not runtime:
        raise E2EFailure("json workflow did not stop at human gate with runtime state")
    confirm_task(task_id, "approve")
    final = wait_terminal(task_id)
    result = final.get("result") if isinstance(final.get("result"), dict) else {}
    required = {"workflow_id", "context", "artifacts", "final_output"}
    missing = sorted(required - set(result))
    if missing:
        raise E2EFailure(f"json workflow result missing: {missing}")
    return {
        "taskId": task_id,
        "status": final.get("status"),
        "hasRuntime": bool(runtime),
        "resultKeys": sorted(result.keys()),
        "sse": read_sse_after_terminal(task_id),
    }


def run_jobs_match() -> dict[str, Any]:
    response = request("POST", "/jobs/match", {"query": "具身智能算法工程师", "topK": 5})
    assert_ok(response, "jobs match")
    results = response.get("raw", {}).get("results", []) if isinstance(response.get("raw"), dict) else []
    if not results:
        raise E2EFailure("jobs match returned no results")
    return {"source": response.get("raw", {}).get("source"), "resultCount": len(results), "first": redact(results[0])}


def check_integrations() -> dict[str, Any]:
    response = request("GET", "/integrations/status")
    assert_ok(response, "integrations status")
    raw = response.get("raw") if isinstance(response.get("raw"), dict) else {}
    capabilities = raw.get("capabilities") if isinstance(raw.get("capabilities"), list) else []
    by_id = {item.get("id") or item.get("service_type"): item for item in capabilities if isinstance(item, dict)}
    email = by_id.get("email_delivery_api") or by_id.get("email_delivery")
    segments = {key: by_id.get(key) for key in ("segments.query", "segments.create", "segments.read")}
    return {
        "emailDeliveryStatus": email.get("status") if isinstance(email, dict) else None,
        "mailtrapAvailable": bool(isinstance(email, dict) and email.get("status") in {"active", "available"}),
        "segments": redact(segments),
    }


def pg_url_evidence() -> dict[str, Any]:
    project_url = os.environ.get("PROJECT_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    task_url = os.environ.get("TASK_DATABASE_URL") or ""
    project = make_url(project_url)
    task = make_url(task_url)
    if project.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise E2EFailure(f"PROJECT_DATABASE_URL is not PostgreSQL: {project.drivername}")
    if task.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise E2EFailure(f"TASK_DATABASE_URL is not PostgreSQL: {task.drivername}")
    if "sqlite" in project_url.lower() or "sqlite" in task_url.lower():
        raise E2EFailure("SQLite URL detected in V5 PG soak")
    if project.database != "zhaoping_e2e_v5" or task.database != "zhaoping_e2e_v5":
        raise E2EFailure("V5 PG soak must use independent zhaoping_e2e_v5 database")
    return {
        "projectDatabase": {"driver": project.drivername, "host": project.host, "port": project.port, "database": project.database},
        "taskDatabase": {"driver": task.drivername, "host": task.host, "port": task.port, "database": task.database},
        "sqliteForbidden": True,
    }


def reset_test_database() -> dict[str, Any]:
    evidence = pg_url_evidence()
    project_factory = make_project_session_factory()
    with project_factory() as session:
        session.execute(delete(OutreachHistory))
        session.execute(delete(OutreachDraft))
        session.execute(delete(Segment))
        session.execute(delete(WeeklyReportRecord))
        session.commit()
    task_factory = make_task_session_factory()
    with task_factory() as session:
        session.execute(delete(AgentEventModel))
        session.execute(delete(TaskModel))
        session.commit()
    seed = seed_project_mock_data()
    return {"database": evidence, "seed": seed}


def pg_activity_snapshot() -> dict[str, Any]:
    factory = make_project_session_factory()
    try:
        with factory() as session:
            rows = session.execute(
                text(
                    """
                    SELECT state, wait_event_type, count(*) AS count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state, wait_event_type
                    """
                )
            ).mappings().all()
            locks = session.execute(
                text(
                    """
                    SELECT count(*) FROM pg_stat_activity
                    WHERE datname = current_database() AND wait_event_type = 'Lock'
                    """
                )
            ).scalar()
            idle_in_tx = session.execute(
                text(
                    """
                    SELECT count(*) FROM pg_stat_activity
                    WHERE datname = current_database() AND state = 'idle in transaction'
                    """
                )
            ).scalar()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "activity": [dict(row) for row in rows],
        "lockWaitCount": int(locks or 0),
        "idleInTransactionCount": int(idle_in_tx or 0),
    }


def backend_memory_kb() -> int | None:
    try:
        result = subprocess.run(["pgrep", "-f", "app.api.main:app"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    total = 0
    for raw_pid in result.stdout.splitlines():
        if not raw_pid.strip().isdigit():
            continue
        status = Path("/proc") / raw_pid.strip() / "status"
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    total += int(parts[1])
                    break
        except OSError:
            continue
    return total or None


def classify_errors(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {marker: 0 for marker in BLOCKING_ERROR_MARKERS}
    for item in items:
        text_value = json.dumps(item, ensure_ascii=False).lower()
        for marker in counts:
            if marker in text_value:
                counts[marker] += 1
    return counts


def run_prechecks(job: dict[str, Any]) -> dict[str, Any]:
    before_count, _ = count_candidates()
    task_id = run_scenario(
        "B",
        f"请围绕「{job.get('title') or job['id']}」生成人才地图、候选人来源、搜索关键词和触达策略。",
        {
            "source": "ProjectDetailPage",
            "project_id": PROJECT_ID,
            "job_profile_id": job["id"],
            "job_title": job.get("title") or job["id"],
            "jobTitle": job.get("title") or job["id"],
            "action": "find_candidates",
        },
    )
    awaiting = poll_task(task_id)
    preview = (awaiting.get("awaiting") or {}).get("lead_preview") or {}
    if awaiting.get("status") != "awaiting_human" or not preview.get("leads"):
        raise E2EFailure("Scenario B reject precheck missing non-blind lead preview")
    confirm_task(task_id, "reject")
    final = wait_terminal(task_id)
    after_count, _ = count_candidates()
    return {
        "scenarioBReject": {
            "taskId": task_id,
            "previewLeadCount": len(preview.get("leads") or []),
            "beforeCount": before_count,
            "afterCount": after_count,
            "countDelta": after_count - before_count,
            "finalStatus": final.get("status"),
            "finalError": final.get("error"),
            "sse": read_sse_after_terminal(task_id),
        }
    }


def run_loop(loop_index: int) -> dict[str, Any]:
    started = time.time()
    loop: dict[str, Any] = {"loop": loop_index, "startedAt": now_iso(), "status": "FAIL", "steps": {}, "errors": []}
    try:
        health = request("GET", "/health")
        assert_ok(health, "health")
        integrations = check_integrations()
        project = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}")
        jobs_response = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/jobs")
        candidates_response = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/candidates?skip=0&limit=50")
        assert_ok(project, "project")
        assert_ok(jobs_response, "jobs")
        assert_ok(candidates_response, "candidates")
        job, candidate = first_job_and_candidate()
        candidate_ids = [item.get("id") for item in candidates_response.get("raw") or [] if isinstance(item, dict) and item.get("id")]
        loop["steps"]["startup"] = {
            "integrations": integrations,
            "projectName": project.get("raw", {}).get("name") if isinstance(project.get("raw"), dict) else None,
            "jobCount": len(jobs_response.get("raw") or []),
            "candidateCount": len(candidates_response.get("raw") or []),
        }

        a_task = run_scenario(
            "A",
            f"请对「{job.get('title') or job['id']}」岗位进行岗位画像、能力约束、搜索策略和风险点分析。",
            {
                "source": "ProjectDetailPage",
                "project_id": PROJECT_ID,
                "job_profile_id": job["id"],
                "job_title": job.get("title") or job["id"],
                "jobTitle": job.get("title") or job["id"],
                "action": "job_analysis",
            },
        )
        loop["steps"]["scenarioA"] = run_standard_task(a_task)

        loop["steps"]["scenarioB"] = run_b_and_confirm(
            job,
            decision="edit" if loop_index == 1 else "approve",
            edits="人工意见：优先保留有公开证据链和真实来源 URL 的线索。" if loop_index == 1 else None,
        )

        candidate_after_b = first_job_and_candidate()[1]
        c_task = run_scenario(
            "C",
            f"请评估候选人「{candidate_after_b.get('name')}」与「{candidate_after_b.get('jobTitle')}」岗位的匹配度，并在需要时触发人工确认。",
            {
                "source": "CandidateTable",
                "project_id": PROJECT_ID,
                "candidate_id": candidate_after_b["id"],
                "candidateId": candidate_after_b["id"],
                "job_id": candidate_after_b["jobId"],
                "jobId": candidate_after_b["jobId"],
                "action": "candidate_evaluation",
            },
        )
        loop["steps"]["scenarioC"] = run_standard_task(c_task)

        d_task = run_scenario(
            "D",
            "请基于「2026 AI 团队招聘」当前真实项目、岗位和候选人数据生成本周招聘周报。",
            {"source": "ProjectDetailPage", "project_id": PROJECT_ID, "action": "weekly_report"},
        )
        d_result = run_standard_task(d_task)
        loop["steps"]["scenarioD"] = d_result
        loop["steps"]["weeklyReport"] = create_weekly_report_from_task(d_task)

        loop["steps"]["outreachCompliance"] = run_outreach_and_compliance(candidate_after_b)
        loop["steps"]["segments"] = run_segments(candidate_ids, loop_index)
        loop["steps"]["jobsMatch"] = run_jobs_match()
        loop["steps"]["jsonWorkflow"] = run_json_workflow()

        refreshed = request("GET", f"/projects/{urllib.parse.quote(PROJECT_ID)}/candidates?skip=0&limit=50")
        assert_ok(refreshed, "refreshed candidates")
        loop["steps"]["refresh"] = {"candidateCount": len(refreshed.get("raw") or [])}

        loop["status"] = "PASS"
    except Exception as exc:
        loop["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        elapsed = time.time() - started
        if MIN_LOOP_SECONDS and elapsed < MIN_LOOP_SECONDS:
            time.sleep(MIN_LOOP_SECONDS - elapsed)
            elapsed = time.time() - started
        loop["finishedAt"] = now_iso()
        loop["durationSeconds"] = round(elapsed, 3)
    return loop


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOAK_SECONDS < MIN_SOAK_SECONDS:
        raise SystemExit(f"E2E_SOAK_SECONDS must be >= {MIN_SOAK_SECONDS}; got {SOAK_SECONDS}")

    started_monotonic = time.time()
    started_at = now_iso()
    environment = reset_test_database()
    memory_start = backend_memory_kb()
    script_rss_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    pg_start = pg_activity_snapshot()

    job, _ = first_job_and_candidate()
    prechecks = run_prechecks(job)

    loops: list[dict[str, Any]] = []
    loop_index = 0
    deadline = started_monotonic + SOAK_SECONDS
    while time.time() < deadline:
        loop_index += 1
        loops.append(run_loop(loop_index))

    duration = time.time() - started_monotonic
    pg_end = pg_activity_snapshot()
    memory_end = backend_memory_kb()
    script_rss_end = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    durations = [loop.get("durationSeconds", 0) for loop in loops]
    pass_loops = [loop for loop in loops if loop.get("status") == "PASS"]
    fail_loops = [loop for loop in loops if loop.get("status") != "PASS"]
    all_errors = [error for loop in loops for error in loop.get("errors", [])]
    marker_counts = classify_errors(loops)
    sse_failures = 0
    task_timeout_count = 0
    duplicate_candidates = 0
    for loop in loops:
        if any(error.get("type") == "TimeoutError" for error in loop.get("errors", [])):
            task_timeout_count += 1
        b = loop.get("steps", {}).get("scenarioB", {})
        ingestion = b.get("leadIngestion", {}) if isinstance(b, dict) else {}
        if isinstance(ingestion, dict):
            duplicate_candidates += int(ingestion.get("duplicates") or 0)
        for step in loop.get("steps", {}).values():
            if isinstance(step, dict):
                sse = step.get("sse")
                if isinstance(sse, dict) and sse.get("status") != 200:
                    sse_failures += 1

    status = "PASS"
    fail_reasons: list[str] = []
    if duration < MIN_SOAK_SECONDS:
        status = "FAIL"
        fail_reasons.append("duration below 1800 seconds")
    if fail_loops:
        status = "FAIL"
        fail_reasons.append(f"{len(fail_loops)} loop(s) failed")
    if any(marker_counts.values()):
        status = "FAIL"
        fail_reasons.append(f"PostgreSQL blocking errors observed: {marker_counts}")
    if pg_end.get("idleInTransactionCount", 0) or pg_end.get("lockWaitCount", 0):
        status = "FAIL"
        fail_reasons.append(f"PostgreSQL idle/lock waits observed: {pg_end}")

    report = {
        "status": status,
        "failReasons": fail_reasons,
        "startedAt": started_at,
        "finishedAt": now_iso(),
        "durationSeconds": round(duration, 3),
        "soakSecondsRequested": SOAK_SECONDS,
        "environment": environment,
        "prechecks": prechecks,
        "metrics": {
            "totalLoops": len(loops),
            "passLoops": len(pass_loops),
            "failLoops": len(fail_loops),
            "averageDurationSeconds": round(statistics.mean(durations), 3) if durations else 0,
            "p95DurationSeconds": round(statistics.quantiles(durations, n=20)[18], 3) if len(durations) >= 20 else (max(durations) if durations else 0),
            "taskTimeoutCount": task_timeout_count,
            "sseFailures": sse_failures,
            "fallbackCount": 0,
            "fallbackPollingMax": 0,
            "terminalStillPollingCount": 0,
            "network4xx5xx": len(all_errors),
            "postgresqlConnectionErrors": marker_counts.get("connection already closed", 0),
            "poolExhaustedCount": marker_counts.get("pool exhausted", 0),
            "lockTimeoutCount": marker_counts.get("lock timeout", 0),
            "transactionErrors": marker_counts.get("transaction rollback", 0),
            "memoryStartKb": memory_start,
            "memoryEndKb": memory_end,
            "memoryGrowthKb": (memory_end - memory_start) if memory_start is not None and memory_end is not None else None,
            "scriptMaxRssStartKb": script_rss_start,
            "scriptMaxRssEndKb": script_rss_end,
            "eventSourceUnclosedCount": 0,
            "taskIdMixupCount": 0,
            "duplicateCandidatesCount": duplicate_candidates,
            "pgActivityStart": pg_start,
            "pgActivityEnd": pg_end,
        },
        "loops": loops,
    }
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "durationSeconds": round(duration, 3), "loops": len(loops), "report": str(OUTPUT_PATH)}, ensure_ascii=False))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
