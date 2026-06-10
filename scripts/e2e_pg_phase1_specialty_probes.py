"""Phase 1 PostgreSQL smoke: specialty API probes and compliance hard-block matrix.

Runs against a live PG-only backend (E2E_API_BASE) and records evidence JSON.
Uses the project DB session directly only to flip job_candidate.pipeline_status,
the same technique as scripts/e2e_v5_pg_soak.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.session import make_project_session_factory  # noqa: E402
from app.models import JobCandidate  # noqa: E402

API_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8012").rstrip("/")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", "project_2026_ai_team")
RUN_ID = os.environ.get("E2E_RUN_ID", "unknown-run")
OUTPUT_PATH = ROOT / "artifacts/e2e_evidence/phase1-specialty-probes-pgv6.json"


def request(method: str, path: str, body: Any = None, *, timeout: int = 90) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except Exception as exc:  # noqa: BLE001
        return {"method": method, "path": path, "status": 0, "error": f"{type(exc).__name__}: {exc}"}
    try:
        parsed = json.loads(raw.decode("utf-8") or "null")
    except Exception:  # noqa: BLE001
        parsed = raw.decode("utf-8", errors="replace")[:400]
    return {
        "method": method,
        "path": path,
        "status": status,
        "durationMs": round((time.time() - started) * 1000),
        "body": parsed,
    }


def brief(resp: dict[str, Any], *keys: str) -> dict[str, Any]:
    body = resp.get("body")
    summary: dict[str, Any] = {"status": resp.get("status"), "durationMs": resp.get("durationMs")}
    if resp.get("error"):
        summary["error"] = resp["error"]
    if isinstance(body, dict):
        if keys:
            summary["body"] = {key: body.get(key) for key in keys if key in body}
        else:
            summary["bodyKeys"] = sorted(body)[:15]
        if "detail" in body:
            summary["detail"] = str(body["detail"])[:200]
    return summary


def set_link_status(job_id: str, candidate_id: str, status: str) -> None:
    factory = make_project_session_factory()
    with factory() as session:
        link = session.scalar(
            select(JobCandidate).where(JobCandidate.job_id == job_id, JobCandidate.candidate_id == candidate_id)
        )
        if link is None:
            raise RuntimeError(f"JobCandidate not found: {job_id}/{candidate_id}")
        link.pipeline_status = status
        session.commit()


def main() -> None:
    evidence: dict[str, Any] = {
        "runId": RUN_ID,
        "apiBase": API_BASE,
        "projectId": PROJECT_ID,
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }

    candidates = request("GET", f"/projects/{PROJECT_ID}/candidates?skip=0&limit=200")
    assert candidates["status"] == 200, candidates
    rows = candidates["body"]
    with_email = next((c for c in rows if c.get("email")), None)
    without_email = next((c for c in rows if not c.get("email")), None)
    assert with_email, "no candidate with email available"
    job_id = with_email["jobId"]
    candidate_id = with_email["id"]
    job_candidate_id = with_email["jobCandidateId"]

    # --- compliance hard-block matrix (direct API) ---
    matrix: dict[str, Any] = {}
    approve = request(
        "POST",
        f"/projects/{PROJECT_ID}/candidates/{job_candidate_id}/compliance-review",
        {"decision": "approve"},
    )
    matrix["complianceApprove"] = brief(approve, "pipelineStatus", "complianceStatus")
    draft = request("POST", "/outreach/draft", {"projectId": PROJECT_ID, "jobId": job_id, "candidateId": candidate_id})
    assert draft["status"] == 200, draft
    draft_id = draft["body"]["draftId"]
    matrix["approvedDraft"] = brief(draft, "draftId", "status")

    set_link_status(job_id, candidate_id, "pending_compliance_review")
    matrix["pendingDraft"] = brief(
        request("POST", "/outreach/draft", {"projectId": PROJECT_ID, "jobId": job_id, "candidateId": candidate_id})
    )
    matrix["pendingSendReal"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    )
    matrix["pendingSendSimulate"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True}),
        "status", "deliveryMode", "providerStatus",
    )

    set_link_status(job_id, candidate_id, "rejected")
    matrix["rejectedDraft"] = brief(
        request("POST", "/outreach/draft", {"projectId": PROJECT_ID, "jobId": job_id, "candidateId": candidate_id})
    )
    matrix["rejectedSendReal"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    )
    matrix["rejectedSendSimulate"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True}),
        "status", "deliveryMode", "providerStatus",
    )

    set_link_status(job_id, candidate_id, "pending_outreach")
    matrix["approvedSendSimulate"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True}),
        "status", "deliveryMode", "providerStatus",
    )
    matrix["approvedSendRealProviderMissing"] = brief(
        request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
    )
    history = request(
        "GET",
        f"/outreach/history?projectId={urllib.parse.quote(PROJECT_ID)}&candidateId={urllib.parse.quote(candidate_id)}",
    )
    matrix["history"] = brief(history, "total")
    if isinstance(history.get("body"), dict):
        matrix["historyStatuses"] = [item.get("status") for item in history["body"].get("items", [])][:10]

    checks = {
        "pendingDraftBlocked": matrix["pendingDraft"]["status"] in (403, 409),
        "pendingSendReal403": matrix["pendingSendReal"]["status"] == 403,
        "pendingSendSimulateBlockedSimulation": matrix["pendingSendSimulate"]["status"] == 200
        and matrix["pendingSendSimulate"].get("body", {}).get("status") == "blocked_simulation",
        "rejectedDraftBlocked": matrix["rejectedDraft"]["status"] in (403, 409),
        "rejectedSendReal403": matrix["rejectedSendReal"]["status"] == 403,
        "rejectedSendSimulateBlockedSimulation": matrix["rejectedSendSimulate"]["status"] == 200
        and matrix["rejectedSendSimulate"].get("body", {}).get("status") == "blocked_simulation",
        "approvedSendSimulateOk": matrix["approvedSendSimulate"]["status"] == 200
        and matrix["approvedSendSimulate"].get("body", {}).get("deliveryMode") == "simulated",
        "approvedRealProviderMissingNoFakeSuccess": matrix["approvedSendRealProviderMissing"]["status"] in (502, 503),
    }
    matrix["checks"] = checks
    matrix["allPass"] = all(checks.values())
    evidence["complianceMatrix"] = matrix

    # --- candidate without email disables outreach ---
    if without_email is not None:
        no_email_draft = request(
            "POST",
            "/outreach/draft",
            {"projectId": PROJECT_ID, "jobId": without_email["jobId"], "candidateId": without_email["id"]},
        )
        no_email_send = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "reject", "simulate": True})
        evidence["candidateWithoutEmail"] = {
            "candidateHasEmail": False,
            "draft": brief(no_email_draft),
            "rejectDecisionSend": brief(no_email_send),
        }
    else:
        evidence["candidateWithoutEmail"] = {"skipped": "all candidates currently have emails"}

    # --- jobs match / RSI / search specialties ---
    jobs_match = request("POST", "/jobs/match", {"query": "具身智能算法工程师", "topK": 5})
    evidence["jobsMatch"] = brief(jobs_match, "source")
    if isinstance(jobs_match.get("body"), dict):
        evidence["jobsMatch"]["resultCount"] = len(jobs_match["body"].get("results") or [])

    evidence["rsiEvaluate"] = brief(
        request("POST", "/rsi/evaluate", {"mode": "offline"}, timeout=120),
        "suite", "mode", "passRate", "threshold", "passed",
    )

    search_query = "embodied intelligence robotics engineer hiring signals"
    evidence["search"] = {
        "plan": brief(request("POST", "/search/plan", {"query": search_query, "limit": 2})),
        "run": brief(request("POST", "/search/run", {"query": search_query, "limit": 2}, timeout=120)),
        "evidence": brief(request("POST", "/search/evidence", {"query": search_query, "limit": 2}, timeout=120)),
        "brief": brief(request("POST", "/search/brief", {"query": search_query, "limit": 2}, timeout=180)),
        "archive": brief(request("POST", "/search/archive", {"query": search_query, "limit": 2}, timeout=180)),
        "archiveRecent": brief(request("GET", "/search/archive/recent")),
        "archiveDiff": brief(request("GET", "/search/archive/diff")),
        "watchlistRun": brief(
            request("POST", "/search/watchlist/run", {"items": [{"query": search_query, "limit": 2}], "archive": False}, timeout=180)
        ),
    }

    # --- task artifacts + probe feedback ---
    workflow = {
        "id": f"phase1_artifacts_{RUN_ID.replace('-', '_')}",
        "inputs": {"draft": {"type": "string"}},
        "steps": [
            {"id": "artifact", "type": "save_artifact", "input": "Phase1 {{ draft }}", "output_key": "phase1_artifact"},
        ],
    }
    run = request("POST", "/workflows/run", {"workflow": workflow, "input": {"draft": "specialty probes"}, "auto_run": True})
    evidence["workflowRun"] = brief(run, "task_id", "status")
    artifacts_result: dict[str, Any] | None = None
    if isinstance(run.get("body"), dict) and run["body"].get("task_id"):
        task_id = run["body"]["task_id"]
        deadline = time.time() + 60
        while time.time() < deadline:
            snapshot = request("GET", f"/tasks/{task_id}")
            if isinstance(snapshot.get("body"), dict) and snapshot["body"].get("status") in {"done", "error", "cancelled"}:
                break
            time.sleep(0.6)
        artifacts_result = request("GET", f"/tasks/{task_id}/artifacts")
        evidence["taskArtifacts"] = brief(artifacts_result, "items", "total")
        if isinstance(artifacts_result.get("body"), dict):
            evidence["taskArtifacts"]["itemCount"] = len(artifacts_result["body"].get("items") or [])
        evidence["probeFeedbackUnknownProbe"] = brief(
            request("POST", f"/tasks/{task_id}/probe-feedback", {"probe_id": "nonexistent_probe", "answered": True})
        )

    # --- segment unsupported-filter silent-ignore evidence ---
    base_criteria = {"jobProfileId": "all", "minScore": 0, "city": "", "keyword": "", "hasEmail": "all"}
    q_all = request("POST", "/segments/query", {"projectId": PROJECT_ID, "criteria": {**base_criteria, "outreachStatus": "all", "sourcePlatform": "all"}})
    q_filtered = request(
        "POST",
        "/segments/query",
        {"projectId": PROJECT_ID, "criteria": {**base_criteria, "outreachStatus": "not_sent", "sourcePlatform": "github"}},
    )
    total_all = q_all.get("body", {}).get("total") if isinstance(q_all.get("body"), dict) else None
    total_filtered = q_filtered.get("body", {}).get("total") if isinstance(q_filtered.get("body"), dict) else None
    evidence["segmentsUnsupportedFilters"] = {
        "totalWithAll": total_all,
        "totalWithUnsupportedFilters": total_filtered,
        "silentlyIgnored": total_all == total_filtered,
        "note": "outreachStatus/sourcePlatform are accepted by schema but not applied as filters (known gap)",
    }

    # --- reports read round trip ---
    latest = request("GET", f"/projects/{PROJECT_ID}/reports/latest")
    evidence["reportsLatest"] = brief(latest, "reportId")
    if isinstance(latest.get("body"), dict) and latest["body"].get("reportId"):
        evidence["reportById"] = brief(
            request("GET", f"/reports/{latest['body']['reportId']}"), "reportId", "projectId"
        )

    evidence["finishedAt"] = datetime.now(timezone.utc).isoformat()
    OUTPUT_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "complianceMatrixAllPass": matrix["allPass"],
        "checks": checks,
        "jobsMatch": evidence["jobsMatch"],
        "segmentsSilentlyIgnored": evidence["segmentsUnsupportedFilters"]["silentlyIgnored"],
        "report": str(OUTPUT_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
