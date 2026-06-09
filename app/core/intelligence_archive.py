from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

ARCHIVE_PATH_ENV = "INTELLIGENCE_ARCHIVE_PATH"
DEFAULT_ARCHIVE_PATH = Path("data/intelligence_archive.jsonl")


class IntelligenceArchive:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get(ARCHIVE_PATH_ENV, DEFAULT_ARCHIVE_PATH))

    def append(self, artifact_type: str, artifact: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "archive_id": self._archive_id(artifact_type, artifact),
            "artifact_type": artifact_type,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "artifact": artifact,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
        return {
            "archive_id": envelope["archive_id"],
            "artifact_type": artifact_type,
            "archive_path": str(self.path),
            "archived_at": envelope["archived_at"],
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        normalized_limit = max(1, min(int(limit), 100))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in reversed(lines[-normalized_limit:]):
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    def diff_latest(self, artifact_type: str | None = None, watchlist_name: str | None = None) -> dict[str, Any]:
        records = [
            record
            for record in self.recent(limit=100)
            if artifact_type is None or record.get("artifact_type") == artifact_type
        ]
        if watchlist_name:
            records = [
                record
                for record in records
                if (record.get("artifact") or {}).get("watchlist_item", {}).get("name") == watchlist_name
            ]
        if len(records) < 2:
            return {
                "status": "insufficient_history",
                "artifact_type": artifact_type,
                "watchlist_name": watchlist_name,
                "message": "Need at least two archived artifacts to compute a diff.",
                "records_considered": len(records),
            }

        current, previous = records[0], records[1]
        current_summary = self._artifact_summary(current["artifact"])
        previous_summary = self._artifact_summary(previous["artifact"])
        diff = {
            "status": "ready",
            "artifact_type": artifact_type or "any",
            "watchlist_name": watchlist_name,
            "current_archive_id": current["archive_id"],
            "previous_archive_id": previous["archive_id"],
            "current_archived_at": current["archived_at"],
            "previous_archived_at": previous["archived_at"],
            "query": current["artifact"].get("query"),
            "claim": current["artifact"].get("claim"),
            "source_changes": self._set_change(previous_summary["source_keys"], current_summary["source_keys"]),
            "risk_changes": self._set_change(previous_summary["risks"], current_summary["risks"]),
            "gap_changes": self._set_change(previous_summary["gaps"], current_summary["gaps"]),
            "status_change": {
                "previous": previous_summary["status"],
                "current": current_summary["status"],
                "changed": previous_summary["status"] != current_summary["status"],
            },
            "source_tier_count_change": self._dict_change(
                previous_summary["source_tier_counts"],
                current_summary["source_tier_counts"],
            ),
        }
        diff["changed"] = any(
            [
                diff["source_changes"]["added"],
                diff["source_changes"]["removed"],
                diff["risk_changes"]["added"],
                diff["risk_changes"]["removed"],
                diff["gap_changes"]["added"],
                diff["gap_changes"]["removed"],
                diff["status_change"]["changed"],
                diff["source_tier_count_change"]["changed"],
            ]
        )
        return diff

    @staticmethod
    def _archive_id(artifact_type: str, artifact: dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "artifact_type": artifact_type,
                "query": artifact.get("query"),
                "claim": artifact.get("claim"),
                "artifact": artifact,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"intel_{digest}"

    @staticmethod
    def _artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
        if "priority_evidence" in artifact:
            source_keys = {
                str(item.get("source_key"))
                for item in artifact.get("priority_evidence", [])
                if item.get("source_key")
            }
            risks = {
                str(item.get("risk"))
                for item in artifact.get("risk_register", [])
                if item.get("risk")
            }
            gaps = {str(item) for item in artifact.get("intelligence_gaps", [])}
            executive_summary = artifact.get("executive_summary", {})
            return {
                "source_keys": source_keys,
                "risks": risks,
                "gaps": gaps,
                "status": executive_summary.get("status"),
                "source_tier_counts": executive_summary.get("source_tier_counts", {}),
            }

        records = artifact.get("records", [])
        source_keys = {
            str(item.get("source_key"))
            for item in records
            if item.get("source_key")
        }
        return {
            "source_keys": source_keys,
            "risks": set(),
            "gaps": set(),
            "status": (artifact.get("review") or {}).get("cross_check_status"),
            "source_tier_counts": (artifact.get("review") or {}).get("source_tier_counts", {}),
        }

    @staticmethod
    def _set_change(previous: set[str], current: set[str]) -> dict[str, list[str]]:
        return {
            "added": sorted(current - previous),
            "removed": sorted(previous - current),
            "unchanged": sorted(current & previous),
        }

    @staticmethod
    def _dict_change(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        keys = sorted(set(previous) | set(current))
        deltas = {
            key: {
                "previous": previous.get(key, 0),
                "current": current.get(key, 0),
                "delta": int(current.get(key, 0)) - int(previous.get(key, 0)),
            }
            for key in keys
            if previous.get(key, 0) != current.get(key, 0)
        }
        return {
            "changed": bool(deltas),
            "deltas": deltas,
        }
