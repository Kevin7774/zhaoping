from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
API_BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8011/api").rstrip("/")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", "project_2026_ai_team")
OUTPUT_PATH = ROOT / "artifacts/e2e_evidence/supplemental-api-probes-v4.json"
UI_REPORT_PATH = ROOT / "artifacts/e2e_evidence/e2e_project_detail_report.json"


def redact(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if "@" in value:
            return "[email redacted]"
        return value if len(value) <= 240 else f"{value[:240]}..."
    if isinstance(value, list):
        return {"type": "array", "length": len(value), "sample": [redact(item) for item in value[:2]]}
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            if any(token in key.lower() for token in ("key", "token", "secret", "password", "credential")):
                output[key] = "[redacted]"
            elif "email" in key.lower() and isinstance(item, str):
                output[key] = "[email redacted]"
            else:
                output[key] = redact(item)
        return output
    return str(value)


def request(method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    data = None
    request_headers = dict(headers or {})
    if body is not None and not isinstance(body, bytes):
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, bytes):
        data = body
    req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        response_headers = dict(exc.headers.items())
    lower_headers = {key.lower(): value for key, value in response_headers.items()}
    content_type = lower_headers.get("content-type", "")
    parsed: Any
    if "application/json" in content_type:
        parsed = json.loads(raw.decode("utf-8") or "null")
    else:
        parsed = raw.decode("utf-8", errors="replace")
    return {
        "method": method,
        "path": path,
        "status": status,
        "durationMs": round((time.time() - started) * 1000),
        "requestSummary": redact(body),
        "responseSummary": redact(parsed),
        "headers": {
            key: lower_headers.get(key.lower())
            for key in ("X-Total-Count", "X-Has-More", "Content-Type")
            if lower_headers.get(key.lower()) is not None
        },
        "raw": parsed,
    }


def multipart_upload(path: str, file_path: Path, field_name = "file") -> dict[str, Any]:
    boundary = f"----zhaoping-e2e-{uuid4().hex}"
    mime = mimetypes.guess_type(file_path.name)[0] or "text/plain"
    content = file_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    result = request("POST", path, body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    result["requestSummary"] = {"file": file_path.name, "size": len(content)}
    return result


def poll_task(task_id: str, timeout_seconds: float = 30.0) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    latest = None
    while time.time() < deadline:
        latest = request("GET", f"/tasks/{task_id}")
        status = latest.get("raw", {}).get("status") if isinstance(latest.get("raw"), dict) else None
        if status in {"done", "error", "cancelled", "awaiting_human"}:
            return latest
        time.sleep(0.4)
    return latest


def invalid_workflows(valid: dict[str, Any]) -> dict[str, dict[str, Any]]:
    duplicate_step = json.loads(json.dumps(valid))
    duplicate_step["steps"][1]["id"] = duplicate_step["steps"][0]["id"]

    unresolved = json.loads(json.dumps(valid))
    unresolved["steps"][0]["input"] = "{{ missing_query }}"

    future_dependency = json.loads(json.dumps(valid))
    future_dependency["steps"][0]["input"] = "{{ summary }}"

    duplicate_output = json.loads(json.dumps(valid))
    duplicate_output["steps"][1]["output_key"] = duplicate_output["steps"][0]["output_key"]

    invalid_limit = json.loads(json.dumps(valid))
    invalid_limit["steps"][0]["limit"] = 0

    invalid_retries = json.loads(json.dumps(valid))
    invalid_retries["steps"][1]["max_retries"] = -1

    missing_required = json.loads(json.dumps(valid))
    missing_required["steps"][1].pop("prompt", None)

    unsupported_type = json.loads(json.dumps(valid))
    unsupported_type["steps"][1]["type"] = "unsupported_step"

    return {
        "duplicate_step_id": duplicate_step,
        "unresolved_placeholder": unresolved,
        "future_dependency": future_dependency,
        "duplicate_output_key": duplicate_output,
        "invalid_limit": invalid_limit,
        "invalid_max_retries": invalid_retries,
        "missing_required_field": missing_required,
        "unsupported_step_type": unsupported_type,
    }


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    probes: list[dict[str, Any]] = []
    created: dict[str, list[str]] = {"taskIds": [], "segmentIds": [], "scheduleJobIds": [], "reportIds": []}
    cleanup: dict[str, list[str]] = {"scheduleDisabledJobIds": []}

    before_candidates = request("GET", f"/projects/{PROJECT_ID}/candidates?skip=0&limit=50")
    probes.extend(
        [
            request("GET", "/health"),
            request("GET", "/integrations/status"),
            request("GET", f"/projects/{PROJECT_ID}"),
            request("GET", f"/projects/{PROJECT_ID}/jobs"),
            before_candidates,
            request("GET", f"/projects/{PROJECT_ID}/candidate-search-schedules"),
            request("GET", "/scenarios/meta"),
        ]
    )

    candidates = before_candidates["raw"] if isinstance(before_candidates["raw"], list) else []
    jobs = probes[3]["raw"] if isinstance(probes[3]["raw"], list) else []
    first_job_id = jobs[0]["id"] if jobs else "job_vla_algorithm"
    first_job_candidate_id = candidates[0]["jobCandidateId"] if candidates else 1

    schedule_update = request(
        "PUT",
        f"/projects/{PROJECT_ID}/jobs/{first_job_id}/candidate-search-schedule",
        {"enabled": True, "intervalMinutes": 360},
    )
    probes.append(schedule_update)
    if schedule_update["status"] < 400:
        created["scheduleJobIds"].append(first_job_id)
        disabled = request(
            "PUT",
            f"/projects/{PROJECT_ID}/jobs/{first_job_id}/candidate-search-schedule",
            {"enabled": False, "intervalMinutes": 360},
        )
        probes.append(disabled)
        if disabled["status"] < 400:
            cleanup["scheduleDisabledJobIds"].append(first_job_id)

    compliance = request(
        "POST",
        f"/projects/{PROJECT_ID}/candidates/{first_job_candidate_id}/compliance-review",
        {"decision": "approve"},
    )
    probes.append(compliance)

    sample_resume = ROOT / "artifacts/e2e_evidence/sample-resume-v4.txt"
    sample_resume.write_text(
        "E2E Resume Candidate\n\nWorked on VLA robot policy evaluation, data pipelines, and safe deployment.\n",
        encoding="utf-8",
    )
    upload = multipart_upload(f"/projects/{PROJECT_ID}/jobs/{first_job_id}/upload-resumes", sample_resume)
    probes.append(upload)
    upload_task_id = upload.get("raw", {}).get("taskId") if isinstance(upload.get("raw"), dict) else None
    if upload_task_id:
        created["taskIds"].append(upload_task_id)
        upload_task = poll_task(upload_task_id)
        if upload_task:
            upload_task["label"] = "upload_resume_task_snapshot"
            probes.append(upload_task)

    segment_query_body = {
        "projectId": PROJECT_ID,
        "criteria": {
            "jobProfileId": "all",
            "minScore": 70,
            "city": "",
            "keyword": "",
            "outreachStatus": "all",
            "hasEmail": "yes",
            "sourcePlatform": "all",
        },
    }
    segment_query = request("POST", "/segments/query", segment_query_body)
    probes.append(segment_query)
    segment_candidate_ids = [
        item["id"]
        for item in segment_query.get("raw", {}).get("candidates", [])
        if isinstance(item, dict) and item.get("id")
    ]
    segment_save = request(
        "POST",
        "/segments",
        {
            "projectId": PROJECT_ID,
            "name": "E2E v4 API probe segment",
            "criteria": segment_query_body["criteria"],
            "candidateIds": segment_candidate_ids,
        },
    )
    probes.append(segment_save)
    segment_id = segment_save.get("raw", {}).get("segmentId") if isinstance(segment_save.get("raw"), dict) else None
    if segment_id:
        created["segmentIds"].append(segment_id)
        probes.append(request("GET", f"/segments/{segment_id}"))
    probes.append(request("GET", f"/segments?projectId={urllib.parse.quote(PROJECT_ID)}"))

    latest_report = request("GET", f"/projects/{PROJECT_ID}/reports/latest")
    probes.append(latest_report)
    latest_report_id = latest_report.get("raw", {}).get("reportId") if isinstance(latest_report.get("raw"), dict) else None
    if latest_report_id:
        probes.append(request("GET", f"/reports/{latest_report_id}"))

    valid_workflow = {
        "id": "e2e_v4_validate_all_step_types",
        "inputs": {"query": {"type": "string"}, "draft": {"type": "string"}},
        "steps": [
            {"id": "search", "type": "search", "input": "{{ query }}", "limit": 2, "output_type": "artifact", "output_key": "search_results"},
            {"id": "summary", "type": "llm_prompt", "prompt": "Summarize {{ search_results }}", "output_key": "summary"},
            {
                "id": "extract",
                "type": "structured_extract",
                "input": "{{ summary }}",
                "schema": {"type": "object", "properties": {"title": {"type": "string"}}},
                "output_key": "extraction",
                "max_retries": 1,
            },
            {"id": "artifact", "type": "save_artifact", "input": "{{ extraction }}", "output_key": "artifact_ref"},
            {"id": "gate", "type": "human_gate", "prompt": "Approve {{ draft }}", "output_key": "approval"},
        ],
    }
    probes.append(request("POST", "/workflows/validate", {"workflow": valid_workflow}))
    for label, workflow in invalid_workflows(valid_workflow).items():
        result = request("POST", "/workflows/validate", {"workflow": workflow})
        result["label"] = f"invalid_workflow_{label}"
        probes.append(result)

    run_workflow = {
        "id": "e2e_v4_human_gate_runtime",
        "inputs": {"draft": {"type": "string"}},
        "steps": [
            {"id": "gate", "type": "human_gate", "prompt": "Approve {{ draft }}", "output_key": "approval"},
            {"id": "artifact", "type": "save_artifact", "input": "Decision {{ approval }}", "output_key": "decision_artifact"},
        ],
    }
    workflow_run = request(
        "POST",
        "/workflows/run",
        {"workflow": run_workflow, "input": {"draft": "E2E JSON workflow approval"}, "auto_run": True},
    )
    probes.append(workflow_run)
    workflow_task_id = workflow_run.get("raw", {}).get("task_id") if isinstance(workflow_run.get("raw"), dict) else None
    if workflow_task_id:
        created["taskIds"].append(workflow_task_id)
        awaiting = poll_task(workflow_task_id, timeout_seconds=10)
        if awaiting:
            awaiting["label"] = "json_workflow_awaiting_snapshot"
            probes.append(awaiting)
        confirm = request("POST", f"/tasks/{workflow_task_id}/confirm", {"decision": "approve", "data": {"note": "ok"}})
        probes.append(confirm)
        final = poll_task(workflow_task_id, timeout_seconds=20)
        if final:
            final["label"] = "json_workflow_final_snapshot"
            probes.append(final)

    ui_report = json.loads(UI_REPORT_PATH.read_text(encoding="utf-8")) if UI_REPORT_PATH.exists() else {}
    b_task_id = next((flow.get("taskId") for flow in ui_report.get("flows", []) if flow.get("name", "").startswith("找候选人")), None)
    b_snapshot = request("GET", f"/tasks/{b_task_id}") if b_task_id else None
    if b_snapshot:
        b_snapshot["label"] = "scenario_b_snapshot"
        probes.append(b_snapshot)

    after_candidates = request("GET", f"/projects/{PROJECT_ID}/candidates?skip=0&limit=50")
    probes.append(after_candidates)

    b_raw = b_snapshot.get("raw") if b_snapshot else None
    b_result = b_raw.get("result") if isinstance(b_raw, dict) else None
    output = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apiBase": API_BASE,
        "projectId": PROJECT_ID,
        "beforeCandidateTotal": before_candidates["headers"].get("X-Total-Count"),
        "afterCandidateTotal": after_candidates["headers"].get("X-Total-Count"),
        "scenarioBTaskId": b_task_id,
        "scenarioBLeadIngestion": b_result.get("lead_ingestion") if isinstance(b_result, dict) else None,
        "created": created,
        "cleanup": cleanup,
        "probes": [{key: value for key, value in probe.items() if key != "raw"} for probe in probes],
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("apiBase", "beforeCandidateTotal", "afterCandidateTotal", "scenarioBTaskId", "scenarioBLeadIngestion", "created", "cleanup")}, ensure_ascii=False, indent=2))
    print(f"written: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
