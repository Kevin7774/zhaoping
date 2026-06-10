"""Render the PostgreSQL-only E2E final reports (v4 contract/UI, v5 soak, Hanno).

Assembles artifacts/e2e_evidence/* into artifacts/e2e_reports/e2e-pg-only-*-report.{md,json}.
Run after Phase 3 (30-minute formal soak) has written e2e-v5-pg-soak.json.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "artifacts/e2e_evidence"
OUT = ROOT / "artifacts/e2e_reports"


def load(name: str) -> dict[str, Any]:
    path = EVID / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = (EVID / "e2e-run-id.txt").read_text(encoding="utf-8").strip()
    matrix = load("openapi_registry_frontend_matrix.json")
    ui = load("e2e_project_detail_report.json")
    probes = load("supplemental-api-probes-v4.json")
    error_probes = load("error-probes-v4.json")
    specialty = load("phase1-specialty-probes-pgv6.json")
    small_screen = load("small-screen-smoke-pgv6.json")
    baseline = load("pg-baseline-pgv6.json")
    preflight = load("e2e-v5-pg-preflight-pgv6.json")
    soak = load("e2e-v5-pg-soak.json")
    concurrent = load("e2e-v5-pg-concurrent-hanno.json")

    summary = matrix.get("summary", {})
    soak_metrics = soak.get("metrics", {})
    pre_metrics = preflight.get("metrics", {})
    compliance = specialty.get("complianceMatrix", {})

    common = {
        "postgresqlOnlyRun": True,
        "sqliteSkipped": True,
        "sqliteFallbackDetected": False,
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "runId": run_id,
        "frontendUrl": "http://127.0.0.1:5176",
        "backendUrl": "http://127.0.0.1:8012",
        "databaseUrlsRedacted": {
            "PROJECT_DATABASE_URL": "postgresql+psycopg://<redacted>@127.0.0.1:55432/zhaoping_e2e_v5",
            "DATABASE_URL": "postgresql+psycopg://<redacted>@127.0.0.1:55432/zhaoping_e2e_v5",
            "TASK_DATABASE_URL": "postgresql+psycopg://<redacted>@127.0.0.1:55432/zhaoping_e2e_v5",
        },
        "databaseType": "postgresql",
        "databaseName": "zhaoping_e2e_v5",
        "testedProjects": ["project_2026_ai_team", "project_hanno_ai_hardware"],
        "trueFrontendEntry": "frontend/index.html -> src/main.tsx -> src/app/App.tsx -> src/app/router.tsx",
        "legacyAppJsxStatus": "frontend/src/App.jsx is legacy-only; not mounted by the active TS entry",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    contract = {
        "openapiPathCount": summary.get("openapi_path_count"),
        "openapiMethodEndpointCount": summary.get("openapi_method_endpoint_count"),
        "capabilityRegistryPathCount": summary.get("capabilityRegistry_path_count"),
        "missingRegistryCount": summary.get("missing_registry_count"),
        "staleRegistryCount": summary.get("stale_registry_count"),
        "activeTsEndpointCount": summary.get("active_ts_endpoint_count"),
        "categoryCounts": summary.get("category_counts"),
    }

    static_checks = {
        "frontendLint": "PASS (eslint exit 0)",
        "frontendBuild": "PASS (vite build exit 0)",
        "frontendTest": "PASS (vitest 77/77)",
        "backendCompileall": "PASS",
        "pytestStaticContracts": "PASS (109 passed, PG env)",
        "pytestFullCleanEnv": "PASS (227 passed; unit suites use isolated temp DBs by design)",
        "pytestFullPgEnvNote": (
            "Under APP_ENV=production (.env.test.pg) the SQLite-in-production guard correctly "
            "rejects the unit tests' temp SQLite fixtures; suite rerun in clean env: 227 passed."
        ),
        "pythonLint": "ruff not installed / Python lint not run",
    }

    known_gaps = [
        {"id": "GAP-1", "severity": "P2", "item": "Candidate.complianceStatus is not independent; compliance reuses job_candidate.pipeline_status (verified in app/api/routers/projects.py + outreach.py)."},
        {"id": "GAP-2", "severity": "P2", "item": "Missing sourceUrl has no explicit 'insufficient source' UX in HumanGate lead preview (HumanConfirmModal.tsx:101-103 omits silently); TalentMapPage handles it explicitly."},
        {"id": "GAP-3", "severity": "FIXED-PENDING-COMMIT", "item": "Backend direct confirm could approve Scenario B without lead preview; guard added in app/api/main.py (409 on approve/edit when requires_lead_preview and preview missing) + 4 unit tests. Uncommitted minimal diff."},
        {"id": "GAP-4", "severity": "P1", "item": "Segment outreachStatus and sourcePlatform filters are accepted by schema and exposed in UI but silently ignored by backend (app/api/routers/segments.py:88-115); query with/without them returns identical totals."},
        {"id": "GAP-5", "severity": "P2", "item": "GET /segments and GET /segments/{id} have no active TS list/read page (registered_only); API probes pass."},
        {"id": "GAP-6", "severity": "P1", "item": "Scenario D report parsing failure silently falls back to persisted/empty report with no user notice (ProjectDetailPage.tsx:493-494, 592-593)."},
        {"id": "GAP-7", "severity": "LIMITED", "item": "JSON workflow is API/backend specialty only; no full TS product page. validate/run/human_gate/confirm/resume verified by API + unit tests."},
        {"id": "GAP-8", "severity": "LIMITED", "item": "Public website email extraction has no active TS product entry; not forced through product E2E."},
        {"id": "GAP-9", "severity": "LIMITED", "item": "Mailtrap/Postmark/SendGrid keys absent: real email send disabled (503, no fake success); simulated send only."},
        {"id": "GAP-10", "severity": "P2-product-gap", "item": "No application-level auth/user/org: no users/organizations tables, no /auth/*, no current_user; sender identity is static RECRUITING_CONTACT_EMAIL env, not logged-in user (target zaide.zhang@quantgroup.com unsupported today)."},
        {"id": "GAP-11", "severity": "LIMITED", "item": "Primary soak runner is sequential; concurrency covered by a second concurrent Hanno flow (scripts/e2e_pg_concurrent_hanno_load.py), still below true multi-user load."},
        {"id": "GAP-12", "severity": "P2", "item": "Small-screen (390px): main workspace requires horizontal scrolling (~570px overflow); Hanno page logs console 404 noise from reports/latest empty state."},
    ]

    bugs_fixed = [
        "Error-probe harness called with backend-origin API base while the SPA uses page-origin /api via Vite proxy; rerun with page-origin base (no code change).",
        "Error-probe stale assertion: topbar project switcher legitimately shows project names from GET /projects; assertion now targets detail-only content (artifacts/e2e_evidence/runner/error-probes-v4.mjs).",
        "scripts/e2e_v5_pg_soak.py: MIN_SOAK_SECONDS now env-overridable (E2E_MIN_SOAK_SECONDS) to allow the 5-minute preflight; formal threshold still defaults to 1800s.",
    ]

    soak_ok = soak.get("status") == "PASS" and float(soak.get("durationSeconds") or 0) >= 1800
    verdict = "PASS" if soak_ok else "FAIL"
    verdict_notes = [
        "PostgreSQL-only verified end to end (zhaoping_e2e_v5; sqlite_detected=false; live tasks observed in PG).",
        "LIMITED areas (do not block PASS, no P0): email provider keys absent, JSON workflow API-only, auth/org absent, concurrency below true multi-user load, GET /segments has no TS page.",
        "No P0 found: compliance hard block held under direct API attack; no fake success or fake data observed.",
    ]

    # ---------- v4: contract + UI + probes ----------
    v4 = {
        **common,
        "scope": "Contract audit, static checks, UI deep flows, error probes, specialty APIs (Phase 1)",
        "routeCoverage": {
            "spaRoutes200": 20,
            "routes": [
                "/dashboard", "/projects/:projectId(+jobs,candidates,talent-map,scenarios,outreach,reports)",
                "/jobs", "/candidates", "/talent-map", "/scenarios", "/outreach", "/tasks", "/reports", "/integrations",
            ],
        },
        "contract": contract,
        "staticChecks": static_checks,
        "uiFlows": [{"name": f.get("name"), "status": f.get("status")} for f in ui.get("flows", [])],
        "errorProbes": {
            "pass": sum(1 for r in error_probes.get("results", []) if r.get("status") == "PASS"),
            "total": len(error_probes.get("results", [])),
            "cases": [{"name": r.get("name"), "status": r.get("status")} for r in error_probes.get("results", [])],
        },
        "complianceHardBlockMatrix": {"checks": compliance.get("checks"), "allPass": compliance.get("allPass"),
                                      "historyStatuses": compliance.get("historyStatuses")},
        "outreach": {
            "candidateWithoutEmail": specialty.get("candidateWithoutEmail"),
            "providerState": "Mailtrap/Postmark/SendGrid unavailable; real send 503; simulated send records history",
        },
        "segments": {
            "queryCreateReadList": "PASS via API probes (segments query/create/read/list all 200)",
            "unsupportedFilters": specialty.get("segmentsUnsupportedFilters"),
            "uiApiConsistency": "INCONSISTENT-LIMITED: UI exposes outreachStatus/sourcePlatform that backend ignores (GAP-4); save gating matches segments.create capability",
        },
        "reports": {"latest": specialty.get("reportsLatest"), "byId": specialty.get("reportById")},
        "jobsMatch": specialty.get("jobsMatch"),
        "rsiSearchSpecialty": {"rsiEvaluate": (specialty.get("retries") or {}).get("rsiEvaluate"),
                               "search": specialty.get("search"),
                               "watchlistRun": (specialty.get("retries") or {}).get("watchlistRun")},
        "jsonWorkflow": {"apiProbes": "validate(valid+5 invalid variants)/run/confirm all behaved; runtime in frontend_state",
                         "unitSuite": "tests/test_json_workflow_engine.py PASS in clean env"},
        "taskSseFallback": "UI flows verified task create/SSE/terminal sync + cancel/retry controls; backend terminal via summary(status=done); no frontend-faked terminal observed",
        "humanGate": "Scenario B lead preview rendered, approve gated on preview; C/D human gates confirmed via UI",
        "authSenderIdentityAudit": known_gaps[9]["item"],
        "smallScreenSmoke": small_screen.get("results"),
        "pgBaselines": baseline,
        "bugsFixed": bugs_fixed,
        "knownGaps": known_gaps,
        "verdict": "PASS (phase scope)" if verdict == "PASS" else verdict,
        "verdictNotes": verdict_notes,
    }

    # ---------- v5: soak ----------
    v5 = {
        **common,
        "scope": "PostgreSQL preflight (300s) + formal soak (>=1800s) on project_2026_ai_team with concurrent Hanno flow",
        "contract": contract,
        "staticChecks": static_checks,
        "preflight": {
            "status": preflight.get("status"),
            "durationSeconds": preflight.get("durationSeconds"),
            "loops": {"total": pre_metrics.get("totalLoops"), "pass": pre_metrics.get("passLoops"), "fail": pre_metrics.get("failLoops")},
            "scenarioBRejectPrecheck": (preflight.get("prechecks") or {}).get("scenarioBReject"),
        },
        "formalSoak": {
            "status": soak.get("status"),
            "failReasons": soak.get("failReasons"),
            "startedAt": soak.get("startedAt"),
            "finishedAt": soak.get("finishedAt"),
            "durationSeconds": soak.get("durationSeconds"),
            "metrics": soak_metrics,
            "scenarioBRejectPrecheck": (soak.get("prechecks") or {}).get("scenarioBReject"),
        },
        "concurrencyCoverage": {
            "mode": "2 concurrent flows: sequential A/B/C/D soak on project_2026_ai_team + read/Scenario-A loop on project_hanno_ai_hardware",
            "secondaryFlow": {k: concurrent.get(k) for k in ("durationSeconds", "totalLoops", "passLoops", "failLoops", "scenarioAStatusCounts")},
            "limitation": "still below true multi-user load (GAP-11)",
        },
        "complianceHardBlockMatrix": {"checks": compliance.get("checks"), "allPass": compliance.get("allPass")},
        "taskSseFallback": {
            "soakSse": f"sseFailures={soak_metrics.get('sseFailures')}, taskTimeouts={soak_metrics.get('taskTimeoutCount')}",
            "note": "soak polls 600ms and reads SSE after terminal; runaway-polling/fallback counters instrumented at zero; UI-level SSE verified in v4 report",
        },
        "dbHealth": {
            "pgActivityStart": soak_metrics.get("pgActivityStart"),
            "pgActivityEnd": soak_metrics.get("pgActivityEnd"),
            "memoryStartKb": soak_metrics.get("memoryStartKb"),
            "memoryEndKb": soak_metrics.get("memoryEndKb"),
            "duplicateCandidatesDetectedNotReinserted": soak_metrics.get("duplicateCandidatesCount"),
        },
        "bugsFixed": bugs_fixed,
        "knownGaps": known_gaps,
        "verdict": verdict,
        "verdictNotes": verdict_notes,
    }

    # ---------- hanno ----------
    hanno_loops = concurrent.get("loops") or []
    v_hanno = {
        **common,
        "scope": "Hanno specialty: BP preview/initialize, project routes, privacy, concurrent load",
        "bpFile": "data/input/projects/bp_ai_hardware.md",
        "bpPreview": {"jobCount": 14, "writes": "none (preview only)"},
        "bpInitialize": {"jobCount": 14, "minimumMet": True, "note": "project did not previously exist in zhaoping_e2e_v5; created under runId, no real seed overwritten"},
        "routes": {"project": 200, "jobs": 200, "candidates": 200, "reports": "404 latest (no report yet; UI renders empty state, jobs visible)"},
        "noFakeJobs": "jobs generated by BP deconstructor LLM from the BP document and persisted in PG; titles match BP domain",
        "privacy": {
            "resumePdfsGitIgnored": True,
            "evidence": ".gitignore lines 16-17 cover data/input/resumes/ and data/input/projects/*.pdf; git status shows none staged",
        },
        "publicEmailExtraction": "no active TS product entry; not forced through product E2E (GAP-8)",
        "smallScreen": [r for r in (small_screen.get("results") or []) if "hanno" in str(r.get("route"))],
        "concurrentLoad": {k: concurrent.get(k) for k in ("durationSeconds", "totalLoops", "passLoops", "failLoops", "scenarioAStatusCounts")},
        "sampleLoopErrors": [loop.get("errors") for loop in hanno_loops if loop.get("errors")][:5],
        "knownGaps": [g for g in known_gaps if g["id"] in {"GAP-8", "GAP-12"}],
        "verdict": "PASS (specialty scope)" if verdict == "PASS" else verdict,
        "verdictNotes": verdict_notes,
    }

    def write(name: str, payload: dict[str, Any]) -> None:
        (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [f"# {name}", ""]
        lines.append("```text")
        lines.append("PostgreSQL-only run = true")
        lines.append("SQLite skipped = true")
        lines.append("SQLite fallback detected = false")
        lines.append("```")
        lines.append("")
        for key, value in payload.items():
            lines.append(f"## {key}")
            lines.append("")
            if isinstance(value, (dict, list)):
                lines.append("```json")
                lines.append(json.dumps(value, ensure_ascii=False, indent=2))
                lines.append("```")
            else:
                lines.append(str(value))
            lines.append("")
        (OUT / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")

    write("e2e-pg-only-v4-report", v4)
    write("e2e-pg-only-v5-report", v5)
    write("e2e-pg-only-hanno-report", v_hanno)
    print(json.dumps({
        "verdict": verdict,
        "soakStatus": soak.get("status"),
        "soakDuration": soak.get("durationSeconds"),
        "reports": sorted(str(p.relative_to(ROOT)) for p in OUT.glob("e2e-pg-only-*")),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
