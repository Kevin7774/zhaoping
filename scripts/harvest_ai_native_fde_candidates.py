#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Mapping

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.candidate_lead_ingestion import extract_candidate_leads, ingest_candidate_leads
from app.core.router import get_router
from app.db.session import project_session_factory
from app.models import Candidate, Job, JobCandidate


DEFAULT_QUERIES = (
    "agentic workflow RAG MCP fullstack",
    "tool calling agent workflow RAG fullstack",
    "MCP server AI agent workflow TypeScript",
    "AI coding agent workflow SaaS fullstack",
    "langchain agentic workflow fullstack",
    "openai agents SDK MCP RAG",
    "multi agent workflow builder Next.js RAG",
    "LLM tool calling workflow production app",
)

PROVIDER_PLAN = (
    ("github_candidates", DEFAULT_QUERIES, 6),
    (
        "github_repositories",
        tuple(f"{query} language:TypeScript" for query in DEFAULT_QUERIES[:5]),
        6,
    ),
    (
        "github_repositories",
        tuple(f"{query} language:Python" for query in DEFAULT_QUERIES[1:6]),
        6,
    ),
    ("github_users", tuple(f"{query} type:user" for query in DEFAULT_QUERIES[:5]), 5),
    ("openalex_authors_search", ("AI agents software engineering", "agentic workflow LLM tools"), 5),
    ("semantic_scholar_authors_search", ("AI agents software engineering", "LLM tool use agents"), 5),
    ("agent_reach_social_search", ("AI Native FDE Agentic Builder", "MCP RAG fullstack engineer"), 5),
)

BAD_NAME_PATTERNS = re.compile(
    r"\b(jobs?|hiring|recruitment|paper|dataset|benchmark|conference|workshop|survey|repository|topic)\b",
    re.IGNORECASE,
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def lead_key(lead: Mapping[str, Any]) -> str:
    for key in ("github_url", "linkedin_url", "homepage_url", "source_url"):
        value = str(lead.get(key) or "").strip().rstrip("/").casefold()
        if value:
            return f"{key}:{value}"
    name = str(lead.get("name") or "").strip().casefold()
    platform = str(lead.get("source_platform") or "").strip().casefold()
    return f"name:{name}:{platform}"


def usable_lead(lead: Mapping[str, Any]) -> bool:
    name = str(lead.get("name") or "").strip()
    source_platform = str(lead.get("source_platform") or "").strip()
    source_url = str(lead.get("source_url") or lead.get("github_url") or lead.get("linkedin_url") or "").strip()
    if not name or not source_platform or not source_url:
        return False
    if BAD_NAME_PATTERNS.search(name):
        return False
    if "github.com/topics/" in source_url.casefold():
        return False
    raw = lead.get("raw_payload") if isinstance(lead.get("raw_payload"), dict) else {}
    if str(raw.get("account_type") or "").casefold() not in {"", "user"}:
        return False
    if str(raw.get("owner_type") or "").casefold() == "organization":
        return False
    return True


def existing_candidates(project_id: str, job_id: str) -> list[dict[str, Any]]:
    with project_session_factory()() as session:
        rows = session.execute(
            select(JobCandidate, Candidate)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .where(JobCandidate.project_id == project_id, JobCandidate.job_id == job_id)
            .order_by(JobCandidate.match_score.desc(), Candidate.name.asc())
        ).all()
    return [candidate_record(link, candidate) for link, candidate in rows]


def candidate_record(link: JobCandidate, candidate: Candidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "job_candidate_id": link.id,
        "name": candidate.name,
        "title": candidate.title,
        "current_company": candidate.current_company,
        "location": candidate.location or candidate.city,
        "source_platform": candidate.source_platform,
        "source_url": candidate.source_url,
        "github_url": candidate.github_url,
        "linkedin_url": candidate.linkedin_url,
        "homepage_url": candidate.homepage_url,
        "skills": candidate.skills or [],
        "match_score": link.match_score,
        "pipeline_status": link.pipeline_status,
        "source_task_id": link.source_task_id,
    }


def find_job(project_id: str, requested_job_id: str | None) -> Job:
    with project_session_factory()() as session:
        if requested_job_id:
            job = session.get(Job, requested_job_id)
            if job is None or job.project_id != project_id:
                raise SystemExit(f"job not found for project: {requested_job_id}")
            return job
        jobs = session.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.id.asc())).all()
        if not jobs:
            raise SystemExit(f"project has no jobs: {project_id}")
        preferred = [
            job
            for job in jobs
            if "FDE" in job.title or "Agentic" in job.title or "全栈" in job.title or "AI Native" in job.title
        ]
        return preferred[0] if preferred else jobs[0]


def _progress(started_at: float, message: str) -> None:
    elapsed = time.monotonic() - started_at
    print(f"[harvest +{elapsed:7.1f}s] {message}", file=sys.stderr, flush=True)


def _interleaved_work_items() -> list[tuple[str, str, int]]:
    """Round-robin across providers so the target is filled from mixed sources,
    not exhausted by whichever provider happens to be first in the plan."""

    items: list[tuple[str, str, int]] = []
    max_queries = max(len(queries) for _, queries, _ in PROVIDER_PLAN)
    for index in range(max_queries):
        for service, queries, limit in PROVIDER_PLAN:
            if index < len(queries):
                items.append((service, queries[index], limit))
    return items


def run_provider_searches(
    target: int,
    max_seconds: float = 600.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    router = get_router()
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    traces: list[dict[str, Any]] = []
    providers: dict[str, Any] = {}
    started_at = time.monotonic()
    work_items = _interleaved_work_items()
    _progress(started_at, f"sweep start: {len(work_items)} queries across {len({s for s, _, _ in PROVIDER_PLAN})} providers, target={target}, deadline={max_seconds:g}s")

    for item_index, (service, query, limit) in enumerate(work_items):
        if len(selected) >= target:
            _progress(started_at, f"target reached ({len(selected)}/{target}), stopping sweep")
            break
        if time.monotonic() - started_at >= max_seconds:
            remaining = len(work_items) - item_index
            traces.append({"status": "deferred_deadline", "deferred_queries": remaining, "max_seconds": max_seconds})
            _progress(started_at, f"deadline {max_seconds:g}s reached, {remaining} queries deferred")
            break

        if service not in providers:
            try:
                providers[service] = router.search(service)
            except Exception as exc:  # noqa: BLE001
                providers[service] = None
                traces.append({"service": service, "status": "provider_unavailable", "error": str(exc)})
                _progress(started_at, f"{service} unavailable: {exc}")
        provider = providers[service]
        if provider is None:
            continue

        trace: dict[str, Any] = {"service": service, "query": query, "limit": limit, "status": "started"}
        started = time.monotonic()
        try:
            results = provider.search(query, limit=limit)
            trace["status"] = "retrieved"
            trace["result_count"] = len(results)
            leads = extract_candidate_leads({"搜索证据": {"实时检索": {"results": results}}})
            trace["lead_count"] = len(leads)
            added = 0
            for lead in leads:
                if not usable_lead(lead):
                    continue
                key = lead_key(lead)
                if key in seen:
                    continue
                seen.add(key)
                lead["matched_keywords"] = list(dict.fromkeys([*lead.get("matched_keywords", []), *query.split()]))
                if not lead.get("skills"):
                    lead["skills"] = [item for item in query.split() if len(item) > 2][:8]
                selected.append(lead)
                added += 1
                if len(selected) >= target:
                    break
            trace["selected_count"] = added
        except Exception as exc:  # noqa: BLE001
            trace["status"] = "error"
            trace["error"] = str(exc)
        finally:
            trace["elapsed_seconds"] = round(time.monotonic() - started, 2)
            traces.append(trace)
            _progress(
                started_at,
                f"{service} query={query[:48]!r} status={trace['status']} "
                f"results={trace.get('result_count', 0)} leads={trace.get('lead_count', 0)} "
                f"selected={len(selected)}/{target} ({trace['elapsed_seconds']}s)",
            )
    return selected[:target], traces


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest real AI Native FDE candidates through zhaoping search providers.")
    parser.add_argument("--project-id", default=os.environ.get("GOAL_PROJECT_ID") or os.environ.get("E2E_PROJECT_ID"), required=False)
    parser.add_argument("--job-id", default=os.environ.get("GOAL_JOB_ID") or os.environ.get("E2E_JOB_ID"))
    parser.add_argument("--target", type=int, default=int(os.environ.get("GOAL_TARGET_CANDIDATES", "20")))
    parser.add_argument("--report-path", default=os.environ.get("GOAL_HARVEST_REPORT_PATH", "artifacts/e2e_evidence/goal-ai-native-fde-harvest.json"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ.get("GOAL_HARVEST_MAX_SECONDS", "600")),
        help="overall sweep deadline; remaining queries are recorded as deferred_deadline",
    )
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    if not args.project_id:
        raise SystemExit("--project-id or GOAL_PROJECT_ID/E2E_PROJECT_ID is required")

    job = find_job(args.project_id, args.job_id)
    before = existing_candidates(args.project_id, job.id)
    need = max(0, args.target - len(before))
    task_id = f"manual_system_harvest_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    selected, traces = ([], []) if need == 0 else run_provider_searches(args.target + 12, max_seconds=args.max_seconds)

    with project_session_factory()() as session:
        ingestion = ingest_candidate_leads(
            session,
            project_id=args.project_id,
            job_id=job.id,
            source_task_id=task_id,
            raw_leads=selected,
        )
    after = existing_candidates(args.project_id, job.id)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": args.project_id,
        "job_id": job.id,
        "job_title": job.title,
        "target": args.target,
        "before_count": len(before),
        "selected_leads": len(selected),
        "ingestion": ingestion,
        "after_count": len(after),
        "provider_traces": traces,
        "final_candidates": after[: args.target],
        "status": "PASS" if len(after) >= args.target else "LIMITED",
    }
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_path": str(report_path), "project_id": args.project_id, "job_id": job.id, "after_count": len(after)}, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
