#!/usr/bin/env python3
"""Manual-test monitor: streams PG row audits, HTTP anomalies and data/ file
changes into one human-readable log. Dev tooling only.

Usage: .venv/bin/python scripts/manual_test_watcher.py <out_dir>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DSN = "postgresql://zhaoping:123123@127.0.0.1:55432/zhaoping"
ACCESS_LOG = ROOT / "data" / "runtime" / "manual_test_access.jsonl"
WATCH_DIRS = [ROOT / "data" / "uploads", ROOT / "data" / "workflow_artifacts", ROOT / "data" / "input"]
WATCH_FILES = [ROOT / "data" / "projects.sqlite3", ROOT / "data" / "tasks.sqlite3",
               ROOT / "data" / "intelligence_archive.jsonl"]
SLOW_MS = 2000
NOISY_TABLES = {"agent_events"}  # summarized, not dumped in full

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "manual_test"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MON = OUT_DIR / "monitor.log"


def log(line: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    with MON.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def fmt_val(v, limit=160):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s) - limit} chars)"


def describe_audit(table, op, pk, old, new):
    if op == "UPDATE" and old and new:
        diffs = []
        for k in sorted(set(old) | set(new)):
            if old.get(k) != new.get(k):
                diffs.append(f"{k}: {fmt_val(old.get(k), 60)} -> {fmt_val(new.get(k), 60)}")
        body = "; ".join(diffs) if diffs else "(no-op update)"
        return f"DB UPDATE {table}#{pk} | {body}"
    if op == "INSERT":
        if table in NOISY_TABLES:
            keys = ("event_type", "task_id", "status", "name", "title")
            brief = {k: new.get(k) for k in keys if new and new.get(k) is not None}
            return f"DB INSERT {table}#{pk} | {fmt_val(brief)}"
        return f"DB INSERT {table}#{pk} | {fmt_val(new, 400)}"
    if op == "DELETE":
        return f"DB DELETE {table}#{pk} | was {fmt_val(old, 200)}"
    return f"DB {op} {table}#{pk}"


def main() -> None:
    log(f"=== watcher started pid={Path('/proc/self').resolve().name} ===")
    last_audit_id = 0
    access_pos = ACCESS_LOG.stat().st_size if ACCESS_LOG.exists() else 0
    fs_state: dict[str, float] = {}

    def snapshot_fs():
        snap = {}
        for d in WATCH_DIRS:
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file():
                        try:
                            snap[str(p)] = p.stat().st_mtime
                        except OSError:
                            pass
        for f in WATCH_FILES:
            if f.exists():
                snap[str(f)] = f.stat().st_mtime
        return snap

    fs_state = snapshot_fs()
    conn = None
    while True:
        # --- DB audit ---
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(DSN, autocommit=True)
                last_audit_id = conn.execute(
                    "select coalesce(max(audit_id),%s) from monitor.row_audit", (last_audit_id,)
                ).fetchone()[0] if last_audit_id == 0 else last_audit_id
            rows = conn.execute(
                "select audit_id, table_name, op, row_pk, old_row, new_row"
                " from monitor.row_audit where audit_id > %s order by audit_id limit 500",
                (last_audit_id,),
            ).fetchall()
            for aid, table, op, pk, old, new in rows:
                last_audit_id = aid
                log(describe_audit(table, op, pk, old, new))
        except Exception as exc:  # keep the watcher alive across PG restarts
            log(f"!! watcher PG error: {exc}")
            conn = None
            time.sleep(3)

        # --- HTTP anomalies (full trail stays in manual_test_access.jsonl) ---
        try:
            if ACCESS_LOG.exists():
                size = ACCESS_LOG.stat().st_size
                if size < access_pos:
                    access_pos = 0  # truncated/rotated
                if size > access_pos:
                    with ACCESS_LOG.open("r", encoding="utf-8") as fh:
                        fh.seek(access_pos)
                        chunk = fh.read()
                        access_pos = fh.tell()
                    for ln in chunk.splitlines():
                        try:
                            e = json.loads(ln)
                        except json.JSONDecodeError:
                            continue
                        flag = None
                        if e.get("status", 0) >= 500:
                            flag = "HTTP 5xx"
                        elif e.get("status", 0) >= 400:
                            flag = "HTTP 4xx"
                        elif e.get("ms", 0) >= SLOW_MS:
                            flag = "HTTP slow"
                        if flag:
                            q = ("?" + e["query"]) if e.get("query") else ""
                            detail = f" | body: {fmt_val(e['error_body'], 400)}" if e.get("error_body") else ""
                            log(f"!! {flag}: {e['method']} {e['path']}{q} -> {e['status']} ({e['ms']}ms){detail}")
        except OSError:
            pass

        # --- filesystem ---
        try:
            snap = snapshot_fs()
            for p, mt in snap.items():
                if p not in fs_state:
                    log(f"FS new file: {Path(p).relative_to(ROOT)}")
                elif mt != fs_state[p]:
                    log(f"FS modified: {Path(p).relative_to(ROOT)}")
            for p in fs_state:
                if p not in snap:
                    log(f"FS deleted: {Path(p).relative_to(ROOT)}")
            fs_state = snap
        except OSError:
            pass

        time.sleep(1.0)


if __name__ == "__main__":
    main()
