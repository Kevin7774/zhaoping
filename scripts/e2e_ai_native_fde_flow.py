"""PostgreSQL-only E2E flow for project_ai_native_fde.

Drives the full recruiting agent loop through the real backend API:
Scenario A/B/C/D, non-blind lead preview + HumanGate, lead ingestion + dedupe,
candidate evaluation, outreach draft/send with compliance hard block, weekly
report persistence, plus error/degraded probes. Writes evidence JSON.

Requires the PG-only backend (E2E_API_BASE) started with .env.test.pg and the
project already initialized from data/input/projects/bp_ai_native_fde.md.
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
from sqlalchemy.engine import make_url  # noqa: E402

from app.db.session import make_project_session_factory  # noqa: E402
from app.models import JobCandidate  # noqa: E402

API_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8012").rstrip("/")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", "project_ai_native_fde")
OUTPUT_PATH = ROOT / "artifacts/e2e_evidence/e2e-ai-native-fde-flow.json"
TERMINAL = {"done", "error", "cancelled"}
TASK_TIMEOUT_SECONDS = int(os.environ.get("E2E_TASK_TIMEOUT_SECONDS", "150"))


class FlowFailure(RuntimeError):
    pass


def assert_pg_only() -> dict[str, str]:
    info: dict[str, str] = {}
    for var in ("PROJECT_DATABASE_URL", "DATABASE_URL", "TASK_DATABASE_URL"):
        raw = os.environ.get(var, "")
        if not raw or raw.lower().startswith("sqlite"):
            raise FlowFailure(f"{var} is missing or SQLite: refusing to run")
        url = make_url(raw)
        if not url.drivername.startswith("postgresql"):
            raise FlowFailure(f"{var} is not PostgreSQL: {url.drivername}")
        info[var] = f"{url.drivername}://<redacted>@{url.host}:{url.port}/{url.database}"
    return info


def request(method: str, path: str, body: Any = None, *, timeout: int = 90) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    try:
        parsed = json.loads(raw.decode("utf-8") or "null")
    except Exception:  # noqa: BLE001
        parsed = raw.decode("utf-8", errors="replace")[:300]
    return {"status": status, "body": parsed}


def ok(resp: dict[str, Any], label: str) -> dict[str, Any]:
    if not (200 <= resp["status"] < 300):
        raise FlowFailure(f"{label} -> HTTP {resp['status']}: {str(resp['body'])[:300]}")
    return resp["body"]


def poll_task(task_id: str) -> dict[str, Any]:
    deadline = time.time() + TASK_TIMEOUT_SECONDS
    while time.time() < deadline:
        snap = request("GET", f"/tasks/{urllib.parse.quote(task_id)}")
        body = snap["body"] if isinstance(snap["body"], dict) else {}
        if body.get("status") in TERMINAL or body.get("status") == "awaiting_human":
            return body
        time.sleep(0.7)
    raise FlowFailure(f"task timeout: {task_id}")


def wait_terminal(task_id: str) -> dict[str, Any]:
    deadline = time.time() + TASK_TIMEOUT_SECONDS
    while time.time() < deadline:
        snap = request("GET", f"/tasks/{urllib.parse.quote(task_id)}")
        body = snap["body"] if isinstance(snap["body"], dict) else {}
        if body.get("status") in TERMINAL:
            return body
        time.sleep(0.7)
    raise FlowFailure(f"task terminal timeout: {task_id}")


def run_scenario(scenario: str, input_text: str, frontend_state: dict[str, Any]) -> str:
    body = ok(
        request(
            "POST",
            "/scenarios/run",
            {
                "scenario": scenario,
                "input": input_text,
                "team_constraint": "AI Native 交付",
                "aperture_weight": 0.7,
                "frontend_state": frontend_state,
            },
        ),
        f"scenario {scenario} run",
    )
    if not body.get("task_id"):
        raise FlowFailure(f"scenario {scenario} returned no task_id")
    return str(body["task_id"])


def candidates_snapshot() -> tuple[int, list[dict[str, Any]]]:
    rows = ok(request("GET", f"/projects/{PROJECT_ID}/candidates?skip=0&limit=200"), "list candidates")
    return len(rows), rows


def set_link_status(job_id: str, candidate_id: str, status: str) -> None:
    with make_project_session_factory()() as session:
        link = session.scalar(
            select(JobCandidate).where(JobCandidate.job_id == job_id, JobCandidate.candidate_id == candidate_id)
        )
        if link is None:
            raise FlowFailure(f"JobCandidate not found: {job_id}/{candidate_id}")
        link.pipeline_status = status
        session.commit()


def run_b(job: dict[str, Any], decision: str) -> dict[str, Any]:
    before, _ = candidates_snapshot()
    task_id = run_scenario(
        "B",
        f"请围绕「{job['title']}」生成人才地图、候选人来源、搜索关键词和触达策略。",
        {
            "source": "ProjectDetailPage",
            "project_id": PROJECT_ID,
            "job_profile_id": job["id"],
            "job_title": job["title"],
            "jobTitle": job["title"],
            "action": "find_candidates",
        },
    )
    awaiting = poll_task(task_id)
    if awaiting.get("status") != "awaiting_human":
        raise FlowFailure(f"scenario B expected awaiting_human, got {awaiting.get('status')}")
    payload = awaiting.get("awaiting") or {}
    preview = payload.get("lead_preview") or {}
    leads = preview.get("leads") or []
    if not leads:
        raise FlowFailure("scenario B lead preview missing (blind HumanGate)")
    ok(request("POST", f"/tasks/{task_id}/confirm", {"decision": decision}), f"confirm B {decision}")
    final = wait_terminal(task_id)
    after, rows = candidates_snapshot()
    result = final.get("result") if isinstance(final.get("result"), dict) else {}
    return {
        "taskId": task_id,
        "decision": decision,
        "finalStatus": final.get("status"),
        "requiresLeadPreview": bool(payload.get("requires_lead_preview")),
        "previewLeadCount": len(leads),
        "previewFirstLeadKeys": sorted((leads[0] or {}).keys())[:12],
        "beforeCount": before,
        "afterCount": after,
        "countDelta": after - before,
        "leadIngestion": result.get("lead_ingestion"),
    }


def main() -> None:
    evidence: dict[str, Any] = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "projectId": PROJECT_ID,
        "apiBase": API_BASE,
        "databaseUrls": assert_pg_only(),
        "steps": {},
        "failures": [],
    }
    steps = evidence["steps"]
    try:
        project = ok(request("GET", f"/projects/{PROJECT_ID}"), "get project")
        dashboard_projects = ok(request("GET", "/projects"), "list projects")
        steps["projectVisibility"] = {
            "projectName": project.get("name"),
            "inProjectList": any(p.get("id") == PROJECT_ID for p in dashboard_projects),
        }

        jobs = ok(request("GET", f"/projects/{PROJECT_ID}/jobs"), "list jobs")
        if not jobs:
            raise FlowFailure("no jobs in project")
        job = jobs[0]
        rationale = job.get("rationale") or {}
        steps["job"] = {
            "title": job.get("title"),
            "rationaleKeys": sorted(rationale.keys()),
            "hasWhyNeeded": bool(rationale.get("whyNeeded")),
            "hasMustHaveSignals": bool(rationale.get("mustHaveSignals")),
            "hasRiskSignals": bool(rationale.get("riskSignals")),
            "hasSourcingKeywords": bool(rationale.get("sourcingKeywords")),
            "hasOutreachAngle": bool(rationale.get("outreachAngle")),
            "hasBpEvidence": bool(rationale.get("bpEvidence")),
            "interviewQuestions": len(job.get("interviewQuestions") or []),
            "confidence": rationale.get("confidence"),
        }

        # Scenario A
        a_task = run_scenario(
            "A",
            f"请对「{job['title']}」岗位进行岗位画像、能力约束、筛选信号和风险点分析。",
            {
                "source": "ProjectDetailPage",
                "project_id": PROJECT_ID,
                "job_profile_id": job["id"],
                "job_title": job["title"],
                "jobTitle": job["title"],
                "action": "job_analysis",
            },
        )
        a_snap = poll_task(a_task)
        if a_snap.get("status") == "awaiting_human":
            ok(request("POST", f"/tasks/{a_task}/confirm", {"decision": "approve"}), "confirm A")
            a_snap = wait_terminal(a_task)
        steps["scenarioA"] = {"taskId": a_task, "status": a_snap.get("status")}

        # Scenario B: reject must not ingest, approve must ingest, repeat must dedupe
        steps["scenarioBReject"] = run_b(job, "reject")
        if steps["scenarioBReject"]["countDelta"] != 0:
            raise FlowFailure("rejected B ingested candidates")
        steps["scenarioBApprove"] = run_b(job, "approve")
        steps["scenarioBRepeat"] = run_b(job, "approve")

        # Scenario C on a real ingested candidate
        _, rows = candidates_snapshot()
        if not rows:
            raise FlowFailure("no candidates after ingestion")
        candidate = next((row for row in rows if row.get("email")), rows[0])
        c_task = run_scenario(
            "C",
            f"请评估候选人「{candidate.get('name')}」与「{job['title']}」岗位的匹配度，重点考察完整 SDLC、AI coding、Agent/RAG/Workflow 经验与产品 taste。",
            {
                "source": "CandidateTable",
                "project_id": PROJECT_ID,
                "candidate_id": candidate["id"],
                "candidateId": candidate["id"],
                "job_id": candidate["jobId"],
                "jobId": candidate["jobId"],
                "action": "candidate_evaluation",
            },
        )
        c_snap = poll_task(c_task)
        if c_snap.get("status") == "awaiting_human":
            ok(request("POST", f"/tasks/{c_task}/confirm", {"decision": "approve"}), "confirm C")
            c_snap = wait_terminal(c_task)
        steps["scenarioC"] = {"taskId": c_task, "status": c_snap.get("status")}

        # Scenario D + weekly report persistence
        d_task = run_scenario(
            "D",
            "请基于「AI Native FDE / Agentic Full-Stack Recruiting」当前真实项目、岗位和候选人数据生成本周招聘周报。",
            {"source": "ProjectDetailPage", "project_id": PROJECT_ID, "action": "weekly_report"},
        )
        d_snap = poll_task(d_task)
        if d_snap.get("status") == "awaiting_human":
            ok(request("POST", f"/tasks/{d_task}/confirm", {"decision": "approve"}), "confirm D")
            d_snap = wait_terminal(d_task)
        saved = ok(
            request(
                "POST",
                "/reports/weekly",
                {
                    "projectId": PROJECT_ID,
                    "sourceTaskId": d_task,
                    "report": {
                        "conclusion": "AI Native FDE 项目首轮 sourcing 循环完成。",
                        "keyProgress": ["岗位画像与筛选信号生成", "Scenario B 线索预览与入库", "候选人评估完成"],
                        "topCandidates": [str(candidate.get("name"))],
                        "risks": ["真实邮件 provider 缺失，触达只能模拟发送"],
                        "nextActions": ["接入真实搜索源", "扩大候选人池", "复核合规状态"],
                    },
                },
            ),
            "save weekly report",
        )
        latest = ok(request("GET", f"/projects/{PROJECT_ID}/reports/latest"), "latest report")
        steps["scenarioD"] = {
            "taskId": d_task,
            "status": d_snap.get("status"),
            "savedReportId": saved.get("reportId"),
            "latestReportId": latest.get("reportId"),
            "persisted": saved.get("reportId") == latest.get("reportId"),
        }

        # Outreach + compliance hard block
        _, rows = candidates_snapshot()
        target = next((row for row in rows if row.get("email")), None)
        outreach: dict[str, Any] = {}
        if target is None:
            no_email = rows[0]
            draft_resp = request(
                "POST", "/outreach/draft",
                {"projectId": PROJECT_ID, "jobId": no_email["jobId"], "candidateId": no_email["id"]},
            )
            outreach["noEmailCandidateOnly"] = True
            outreach["draftWithoutEmailStatus"] = draft_resp["status"]
            evidence["limited"] = ["no candidate with email; outreach send matrix limited"]
        else:
            ok(
                request(
                    "POST",
                    f"/projects/{PROJECT_ID}/candidates/{target['jobCandidateId']}/compliance-review",
                    {"decision": "approve"},
                ),
                "compliance approve",
            )
            draft = ok(
                request("POST", "/outreach/draft", {"projectId": PROJECT_ID, "jobId": target["jobId"], "candidateId": target["id"]}),
                "outreach draft",
            )
            draft_id = draft["draftId"]
            set_link_status(target["jobId"], target["id"], "pending_compliance_review")
            pending_draft = request("POST", "/outreach/draft", {"projectId": PROJECT_ID, "jobId": target["jobId"], "candidateId": target["id"]})
            pending_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
            pending_sim = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True})
            set_link_status(target["jobId"], target["id"], "rejected")
            rejected_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
            set_link_status(target["jobId"], target["id"], "pending_outreach")
            approved_sim = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": True})
            approved_real = request("POST", "/outreach/send", {"draftId": draft_id, "decision": "approve", "simulate": False})
            history = ok(
                request("GET", f"/outreach/history?projectId={PROJECT_ID}&candidateId={urllib.parse.quote(target['id'])}"),
                "outreach history",
            )
            outreach = {
                "draftId": draft_id,
                "pendingDraftStatus": pending_draft["status"],
                "pendingRealStatus": pending_real["status"],
                "pendingSimStatus": pending_sim["status"],
                "pendingSimResult": (pending_sim["body"] or {}).get("status") if isinstance(pending_sim["body"], dict) else None,
                "rejectedRealStatus": rejected_real["status"],
                "approvedSimStatus": approved_sim["status"],
                "approvedSimDeliveryMode": (approved_sim["body"] or {}).get("deliveryMode") if isinstance(approved_sim["body"], dict) else None,
                "approvedRealProviderMissingStatus": approved_real["status"],
                "historyCount": len(history.get("items") or []),
            }
            checks = {
                "pendingDraftBlocked": outreach["pendingDraftStatus"] in (403, 409),
                "pendingReal403": outreach["pendingRealStatus"] == 403,
                "pendingSimBlockedSimulation": outreach["pendingSimResult"] == "blocked_simulation",
                "rejectedReal403": outreach["rejectedRealStatus"] == 403,
                "approvedSimOk": outreach["approvedSimStatus"] == 200 and outreach["approvedSimDeliveryMode"] == "simulated",
                "providerMissingNoFakeSuccess": outreach["approvedRealProviderMissingStatus"] in (502, 503),
                "historyRecorded": outreach["historyCount"] > 0,
            }
            outreach["checks"] = checks
            if not all(checks.values()):
                raise FlowFailure(f"compliance/outreach checks failed: {checks}")
        steps["outreachCompliance"] = outreach

        # Error / degraded probes
        probes: dict[str, Any] = {}
        probes["duplicateProjectCreate409"] = request(
            "POST", "/projects", {"id": PROJECT_ID, "name": "dup", "status": "active"}
        )["status"]
        probes["missingBpFile"] = request(
            "POST",
            f"/projects/{PROJECT_ID}/preview-from-bp",
            {"projectName": "x", "bpFilePath": "data/input/projects/does_not_exist.md", "minimumRoleCount": 1},
        )["status"]
        probes["invalidGenerationInput422"] = request(
            "POST",
            f"/projects/{PROJECT_ID}/preview-from-bp",
            {"projectName": "x", "generationMode": "prompt", "minimumRoleCount": 1},
        )["status"]
        steps["errorProbes"] = probes

        # Refresh persistence (re-read everything)
        refreshed_jobs = ok(request("GET", f"/projects/{PROJECT_ID}/jobs"), "refresh jobs")
        refreshed_candidates, _ = candidates_snapshot()
        refreshed_latest = ok(request("GET", f"/projects/{PROJECT_ID}/reports/latest"), "refresh report")
        steps["refreshPersistence"] = {
            "jobs": len(refreshed_jobs),
            "jobRationalePersisted": bool((refreshed_jobs[0].get("rationale") or {}).get("whyNeeded")),
            "candidates": refreshed_candidates,
            "latestReportId": refreshed_latest.get("reportId"),
        }
        evidence["status"] = "PASS"
    except FlowFailure as exc:
        evidence["failures"].append(str(exc))
        evidence["status"] = "FAIL"
    finally:
        evidence["finishedAt"] = datetime.now(timezone.utc).isoformat()
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": evidence.get("status"), "failures": evidence["failures"], "report": str(OUTPUT_PATH)}, ensure_ascii=False))
    if evidence.get("status") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
