from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.intelligence_archive import IntelligenceArchive
from app.core.router import get_router


def run_watchlist(config_path: str | Path) -> dict[str, Any]:
    config = _load_watchlist_config(config_path)
    settings = config.get("watchlist", {})
    items = config.get("items", [])
    if not items:
        raise ValueError("Watchlist config must contain at least one [[items]] entry.")

    limit = _normalized_limit(settings.get("limit", 10))
    service_name = settings.get("service")
    archive_enabled = bool(settings.get("archive", True))
    provider = get_router().search(str(service_name)) if service_name else get_router().search()
    if not hasattr(provider, "brief"):
        raise ValueError("Selected search service does not support intelligence briefs.")

    archive = IntelligenceArchive()
    results = []
    for item in items[:20]:
        name = str(item.get("name") or item.get("query") or "").strip()
        query = str(item.get("query") or "").strip()
        if not query:
            raise ValueError(f"Watchlist item '{name or '<unnamed>'}' missing query.")
        claim = str(item["claim"]).strip() if item.get("claim") else None
        tags = [str(tag) for tag in item.get("tags", [])]
        brief = provider.brief(query, limit=limit, claim=claim)
        brief["watchlist_item"] = {
            "name": name or query,
            "tags": tags,
        }
        archive_result = archive.append("brief", brief) if archive_enabled else None
        diff_result = (
            archive.diff_latest(artifact_type="brief", watchlist_name=name or query)
            if archive_enabled
            else None
        )
        results.append(
            {
                "name": name or query,
                "query": query,
                "claim": claim,
                "tags": tags,
                "status": brief["executive_summary"]["status"],
                "record_count": brief["evidence_review"]["record_count"],
                "top_source_keys": [
                    evidence["source_key"]
                    for evidence in brief["priority_evidence"][:5]
                ],
                "archive": archive_result,
                "diff": diff_result,
            }
        )

    return {
        "config_path": str(config_path),
        "item_count": len(results),
        "archived": archive_enabled,
        "results": results,
    }


def render_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Intelligence Watchlist Report",
        "",
        f"- Config: `{result['config_path']}`",
        f"- Items: {result['item_count']}",
        f"- Archived: {result['archived']}",
        "",
    ]
    for item in result["results"]:
        diff = item.get("diff") or {}
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- Query: `{item['query']}`",
                f"- Claim: {item['claim'] or 'N/A'}",
                f"- Tags: {', '.join(item['tags']) if item['tags'] else 'N/A'}",
                f"- Status: `{item['status']}`",
                f"- Record count: {item['record_count']}",
                f"- Top sources: {', '.join(item['top_source_keys']) if item['top_source_keys'] else 'N/A'}",
                f"- Archive ID: `{(item.get('archive') or {}).get('archive_id', 'not_archived')}`",
                f"- Diff status: `{diff.get('status', 'not_available')}`",
            ]
        )
        if diff.get("status") == "ready":
            lines.extend(
                [
                    f"- Changed: {diff.get('changed')}",
                    f"- Added sources: {', '.join(diff['source_changes']['added']) or 'None'}",
                    f"- Removed sources: {', '.join(diff['source_changes']['removed']) or 'None'}",
                    f"- Added risks: {', '.join(diff['risk_changes']['added']) or 'None'}",
                    f"- Removed risks: {', '.join(diff['risk_changes']['removed']) or 'None'}",
                    f"- Status change: `{diff['status_change']['previous']}` -> `{diff['status_change']['current']}`",
                ]
            )
        elif diff.get("status") == "insufficient_history":
            lines.append(f"- Diff note: {diff.get('message')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_watchlist_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Watchlist config does not exist: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _normalized_limit(limit: object) -> int:
    return max(1, min(int(limit), 50))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configured intelligence watchlist briefs.")
    parser.add_argument(
        "--config",
        default="config/watchlist.example.toml",
        help="Path to watchlist TOML config.",
    )
    parser.add_argument(
        "--report",
        help="Optional Markdown report output path.",
    )
    args = parser.parse_args()

    result = run_watchlist(args.config)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_markdown_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
