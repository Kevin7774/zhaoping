from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.main import app

REGISTRY_PATH = ROOT / "frontend/src/capabilities/capabilityRegistry.js"
ACTIVE_API_PATH = ROOT / "frontend/src/features/projects/api.ts"
ACTIVE_TS_SOURCE_GLOBS = (
    "frontend/src/app/**/*.tsx",
    "frontend/src/pages/**/*.tsx",
    "frontend/src/features/**/*.tsx",
)
OUTPUT_PATH = ROOT / "artifacts/e2e_evidence/openapi_registry_frontend_matrix.json"

PARAM_NAMES = {
    "projectId": "project_id",
    "jobId": "job_id",
    "taskId": "task_id",
    "draftId": "draft_id",
    "segmentId": "segment_id",
    "reportId": "report_id",
    "jobCandidateId": "job_candidate_id",
    "nodeId": "node_id",
}

LOW_RISK_SYSTEM_PREFIXES = (
    "/health",
    "/integrations/status",
    "/scenarios/meta",
    "/tasks/",
    "/workflow/meta",
    "/workflows/validate",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def openapi_endpoints() -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            if method.lower() == "parameters":
                continue
            endpoints.append({"method": method.upper(), "path": path})
    return sorted(endpoints, key=lambda item: (item["path"], item["method"]))


def registry_paths(source: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(
            r"^\s*'([^']+)':\s*'(?:productized|system|closed)'",
            source,
            flags=re.MULTILINE,
        )
    }


def function_blocks(source: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(r"export\s+(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(")
    for match in pattern.finditer(source):
        name = match.group(1)
        paren_depth = 0
        signature_end = -1
        for index in range(match.end() - 1, len(source)):
            char = source[index]
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    signature_end = index
                    break
        if signature_end < 0:
            continue
        brace_start = source.find("{", signature_end)
        if brace_start < 0:
            continue
        depth = 0
        for index in range(brace_start, len(source)):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks[name] = source[brace_start : index + 1]
                    break
    return blocks


def normalize_path(raw_path: str) -> str:
    normalized = raw_path
    for camel, snake in PARAM_NAMES.items():
        normalized = re.sub(
            r"\$\{encodeURIComponent\(String\(" + re.escape(camel) + r"\)\)\}",
            "{" + snake + "}",
            normalized,
        )
        normalized = re.sub(
            r"\$\{encodeURIComponent\(" + re.escape(camel) + r"\)\}",
            "{" + snake + "}",
            normalized,
        )
        normalized = re.sub(r"\$\{" + re.escape(camel) + r"\}", "{" + snake + "}", normalized)
    normalized = re.sub(r"\?.*$", "", normalized)
    return normalized


def wrapper_endpoint_map(source: str) -> dict[str, set[tuple[str, str]]]:
    wrappers: dict[str, set[tuple[str, str]]] = {}
    for name, block in function_blocks(source).items():
        for match in re.finditer(r"apiClient\s*\.\s*(getWithMeta|get|post|put|patch|delete|request)\b", block):
            method_name = match.group(1)
            path_match = re.search(r"([`\"])(/[^`\"]+)\1", block[match.end() : match.end() + 700])
            if not path_match:
                continue
            raw_path = path_match.group(2)
            method = {
                "getWithMeta": "GET",
                "get": "GET",
                "post": "POST",
                "put": "PUT",
                "patch": "PATCH",
                "delete": "DELETE",
                "request": "UNKNOWN",
            }[method_name]
            wrappers.setdefault(name, set()).add((method, normalize_path(raw_path)))
        for match in re.finditer(
            r"\brequest\s*\(\s*([`\"])(/[^`\"]+)\1\s*,\s*\{[^}]*method:\s*['\"]([A-Z]+)['\"]",
            block,
            flags=re.DOTALL,
        ):
            _, raw_path, method = match.groups()
            wrappers.setdefault(name, set()).add((method, normalize_path(raw_path)))
    return wrappers


def active_ts_uses(wrapper_names: set[str]) -> set[str]:
    used: set[str] = set()
    sources = []
    for glob in ACTIVE_TS_SOURCE_GLOBS:
        sources.extend(ROOT.glob(glob))
    for path in sources:
        source = read(path)
        for name in wrapper_names:
            if re.search(r"\b" + re.escape(name) + r"\b", source):
                used.add(name)
    return used


def invert_wrappers(wrappers: dict[str, set[tuple[str, str]]], used_names: set[str]) -> dict[tuple[str, str], set[str]]:
    inverted: dict[tuple[str, str], set[str]] = {}
    for name, endpoints in wrappers.items():
        for endpoint in endpoints:
            if endpoint[0] == "UNKNOWN":
                continue
            inverted.setdefault(endpoint, set()).add(name if name in used_names else f"{name} (wrapper)")
    return inverted


def category_for(
    openapi_exists: bool,
    registry_exists: bool,
    active_wrapper: bool,
    active_page: bool,
) -> str:
    if not openapi_exists and registry_exists:
        return "stale_registry"
    if openapi_exists and not registry_exists:
        return "missing_registry"
    if active_page:
        return "active_ts_productized"
    if active_wrapper:
        return "active_ts_wrapper_only"
    if registry_exists:
        return "registered_only"
    return "backend_only"


def risk_for(path: str, category: str) -> str:
    if category in {"missing_registry", "stale_registry"}:
        return "P0"
    if category == "active_ts_productized":
        return "P1" if path.startswith("/outreach/send") else "P2"
    if category in {"registered_only", "backend_only"}:
        if any(path.startswith(prefix) for prefix in LOW_RISK_SYSTEM_PREFIXES):
            return "P2"
        return "P1"
    return "P2"


def summarize_endpoint_names(endpoint_map: dict[tuple[str, str], set[str]], endpoint: tuple[str, str]) -> list[str]:
    return sorted(endpoint_map.get(endpoint, set()))


def main() -> None:
    registry_source = read(REGISTRY_PATH)
    active_source = read(ACTIVE_API_PATH)

    openapi = openapi_endpoints()
    openapi_keys = {(item["method"], item["path"]) for item in openapi}
    openapi_paths = {item["path"] for item in openapi}
    registered_paths = registry_paths(registry_source)

    active_wrappers = wrapper_endpoint_map(active_source)
    active_used_names = active_ts_uses(set(active_wrappers))
    active_endpoint_names = invert_wrappers(active_wrappers, active_used_names)
    active_wrapper_endpoint_names = invert_wrappers(active_wrappers, set(active_wrappers))
    active_endpoint_names.setdefault(("GET", "/health"), set()).add("MainLayout.fetchHealth")
    active_wrapper_endpoint_names.setdefault(("GET", "/health"), set()).add("MainLayout.fetchHealth")
    active_endpoint_names.setdefault(("GET", "/tasks/{task_id}/stream"), set()).add("useTaskStream/taskStreamUrl")
    active_wrapper_endpoint_names.setdefault(("GET", "/tasks/{task_id}/stream"), set()).add("useTaskStream/taskStreamUrl")

    matrix: list[dict[str, Any]] = []
    for item in openapi:
        endpoint = (item["method"], item["path"])
        active_wrapper_names = summarize_endpoint_names(active_wrapper_endpoint_names, endpoint)
        active_page_names = [
            name
            for name in summarize_endpoint_names(active_endpoint_names, endpoint)
            if not name.endswith(" (wrapper)")
        ]
        category = category_for(
            openapi_exists=True,
            registry_exists=item["path"] in registered_paths,
            active_wrapper=bool(active_wrapper_names),
            active_page=bool(active_page_names),
        )
        matrix.append(
            {
                "method": item["method"],
                "path": item["path"],
                "openapi_exists": True,
                "capabilityRegistry_exists": item["path"] in registered_paths,
                "active_ts_wrapper_exists": bool(active_wrapper_names),
                "active_ts_wrappers": active_wrapper_names,
                "active_ts_page_uses": bool(active_page_names),
                "active_ts_page_functions": active_page_names,
                "category": category,
                "risk": risk_for(item["path"], category),
            }
        )

    stale_registry = sorted(registered_paths - openapi_paths)
    for path in stale_registry:
        category = "stale_registry"
        matrix.append(
            {
                "method": "*",
                "path": path,
                "openapi_exists": False,
                "capabilityRegistry_exists": True,
                "active_ts_wrapper_exists": False,
                "active_ts_wrappers": [],
                "active_ts_page_uses": False,
                "active_ts_page_functions": [],
                "category": category,
                "risk": risk_for(path, category),
            }
        )

    category_counts = Counter(item["category"] for item in matrix if item["openapi_exists"])
    summary = {
        "openapi_path_count": len(openapi_paths),
        "openapi_method_endpoint_count": len(openapi),
        "capabilityRegistry_path_count": len(registered_paths),
        "active_ts_endpoint_count": sum(1 for item in matrix if item["openapi_exists"] and item["active_ts_page_uses"]),
        "active_ts_wrapper_endpoint_count": sum(1 for item in matrix if item["openapi_exists"] and item["active_ts_wrapper_exists"]),
        "backend_only_endpoint_count": sum(
            1
            for item in matrix
            if item["openapi_exists"] and not item["active_ts_wrapper_exists"]
        ),
        "registered_but_no_client_wrapper_count": sum(
            1
            for item in matrix
            if item["openapi_exists"]
            and item["capabilityRegistry_exists"]
            and not item["active_ts_wrapper_exists"]
        ),
        "missing_registry_count": sum(1 for item in matrix if item["category"] == "missing_registry"),
        "stale_registry_count": len(stale_registry),
        "category_counts": dict(sorted(category_counts.items())),
        "compliance_review": next(
            item
            for item in matrix
            if item["path"] == "/projects/{project_id}/candidates/{job_candidate_id}/compliance-review"
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"summary": summary, "matrix": matrix}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"matrix written: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
