"""Concurrent secondary load for the PG formal soak.

Runs read traffic plus Scenario A task cycles against project_hanno_ai_hardware
while scripts/e2e_v5_pg_soak.py exercises project_2026_ai_team, providing
two genuinely concurrent flows without disturbing the soak's candidate-count
assertions on the regression project.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8012").rstrip("/")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", "project_hanno_ai_hardware")
DURATION_SECONDS = int(os.environ.get("E2E_CONCURRENT_SECONDS", "1500"))
OUTPUT_PATH = Path(os.environ.get(
    "E2E_REPORT_PATH",
    "artifacts/e2e_evidence/e2e-v5-pg-concurrent-hanno.json",
))
TERMINAL = {"done", "error", "cancelled"}


def request(method: str, path: str, body: Any = None, *, timeout: int = 60) -> tuple[int, Any]:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"null")
        except Exception:  # noqa: BLE001
            return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    started = time.time()
    deadline = started + DURATION_SECONDS
    loops: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    while time.time() < deadline:
        loop_started = time.time()
        loop: dict[str, Any] = {"errors": []}
        for label, path in (
            ("project", f"/projects/{PROJECT_ID}"),
            ("jobs", f"/projects/{PROJECT_ID}/jobs"),
            ("candidates", f"/projects/{PROJECT_ID}/candidates?skip=0&limit=50"),
            ("integrations", "/integrations/status"),
        ):
            status, _ = request("GET", path)
            loop[label] = status
            if status != 200:
                loop["errors"].append(f"{label}:{status}")
        jobs_status, jobs_body = request("GET", f"/projects/{PROJECT_ID}/jobs")
        job = (jobs_body or [{}])[0] if jobs_status == 200 and isinstance(jobs_body, list) and jobs_body else {}
        if job.get("id"):
            status, body = request(
                "POST",
                "/scenarios/run",
                {
                    "scenario": "A",
                    "input": f"请对「{job.get('title') or job['id']}」岗位进行岗位画像与搜索策略分析。",
                    "team_constraint": "真机泛化",
                    "aperture_weight": 0.7,
                    "frontend_state": {
                        "source": "ProjectDetailPage",
                        "project_id": PROJECT_ID,
                        "job_profile_id": job["id"],
                        "action": "job_analysis",
                    },
                },
            )
            if status == 200 and isinstance(body, dict) and body.get("task_id"):
                task_id = body["task_id"]
                task_deadline = time.time() + 120
                final_status = None
                while time.time() < task_deadline:
                    s, snap = request("GET", f"/tasks/{task_id}")
                    if s == 200 and isinstance(snap, dict):
                        if snap.get("status") == "awaiting_human":
                            request("POST", f"/tasks/{task_id}/confirm", {"decision": "approve"})
                        elif snap.get("status") in TERMINAL:
                            final_status = snap.get("status")
                            break
                    time.sleep(0.8)
                loop["scenarioATask"] = task_id
                loop["scenarioAStatus"] = final_status or "timeout"
                status_counts[loop["scenarioAStatus"]] = status_counts.get(loop["scenarioAStatus"], 0) + 1
                if final_status != "done":
                    loop["errors"].append(f"scenarioA:{loop['scenarioAStatus']}")
            else:
                loop["errors"].append(f"scenarioARun:{status}")
        loop["durationSeconds"] = round(time.time() - loop_started, 3)
        loop["ok"] = not loop["errors"]
        loops.append(loop)

    durations = [loop["durationSeconds"] for loop in loops]
    report = {
        "startedAt": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "durationSeconds": round(time.time() - started, 3),
        "projectId": PROJECT_ID,
        "totalLoops": len(loops),
        "passLoops": sum(1 for loop in loops if loop["ok"]),
        "failLoops": sum(1 for loop in loops if not loop["ok"]),
        "scenarioAStatusCounts": status_counts,
        "averageLoopSeconds": round(statistics.mean(durations), 3) if durations else 0,
        "maxLoopSeconds": max(durations) if durations else 0,
        "loops": loops,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("durationSeconds", "totalLoops", "passLoops", "failLoops", "scenarioAStatusCounts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
