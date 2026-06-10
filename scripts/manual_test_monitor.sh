#!/usr/bin/env bash
# 人工测试监控：一键启停。
#   start   安装/刷新 PG 审计触发器 + 启动 watcher（已在跑则跳过）
#   stop    停止 watcher（触发器保留）
#   status  显示三层监控状态
#   tail    实时跟踪 monitor.log
#   uninstall  停止 watcher 并移除 PG 触发器与 monitor schema
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT_DIR/.venv/bin/python"
OUT_DIR="$ROOT_DIR/artifacts/manual_test_20260610"
PID_FILE="$OUT_DIR/watcher.pid"
DSN="postgresql://zhaoping:123123@127.0.0.1:55432/zhaoping"

watcher_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid; pid=$(cat "$PID_FILE")
  kill -0 "$pid" 2>/dev/null && echo "$pid" || return 1
}

install_triggers() {
  "$PY" - <<EOF
import psycopg
conn = psycopg.connect("$DSN", autocommit=True)
cur = conn.cursor()
cur.execute("""
CREATE SCHEMA IF NOT EXISTS monitor;
CREATE TABLE IF NOT EXISTS monitor.row_audit (
    audit_id   bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT clock_timestamp(),
    table_name text NOT NULL,
    op         text NOT NULL,
    row_pk     text,
    old_row    jsonb,
    new_row    jsonb
);
CREATE OR REPLACE FUNCTION monitor.audit_row() RETURNS trigger AS \$\$
DECLARE
    j  jsonb;
    pk text;
BEGIN
    IF TG_OP = 'DELETE' THEN j := to_jsonb(OLD); ELSE j := to_jsonb(NEW); END IF;
    pk := coalesce(j ->> 'id', j ->> 'task_id');
    INSERT INTO monitor.row_audit(table_name, op, row_pk, old_row, new_row)
    VALUES (TG_TABLE_NAME, TG_OP, pk,
        CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN to_jsonb(NEW) END);
    RETURN NULL;
END;
\$\$ LANGUAGE plpgsql;
""")
tables = [r[0] for r in cur.execute(
    "select table_name from information_schema.tables"
    " where table_schema='public' and table_type='BASE TABLE'").fetchall()]
for t in tables:
    cur.execute(f'DROP TRIGGER IF EXISTS zz_monitor_audit ON public."{t}"')
    cur.execute(f'CREATE TRIGGER zz_monitor_audit AFTER INSERT OR UPDATE OR DELETE'
                f' ON public."{t}" FOR EACH ROW EXECUTE FUNCTION monitor.audit_row()')
print(f"audit triggers installed on {len(tables)} tables")
EOF
}

case "${1:-status}" in
  start)
    mkdir -p "$OUT_DIR"
    install_triggers
    if pid=$(watcher_pid); then
      echo "watcher already running (pid $pid)"
    else
      setsid nohup "$PY" "$ROOT_DIR/scripts/manual_test_watcher.py" "$OUT_DIR" \
        > "$OUT_DIR/watcher.out" 2>&1 < /dev/null &
      echo $! > "$PID_FILE"
      disown
      sleep 1
      echo "watcher started (pid $(cat "$PID_FILE")) -> $OUT_DIR/monitor.log"
    fi
    ;;
  stop)
    if pid=$(watcher_pid); then
      kill "$pid" && rm -f "$PID_FILE"
      echo "watcher stopped"
    else
      echo "watcher not running"
    fi
    ;;
  status)
    if pid=$(watcher_pid); then echo "watcher: running (pid $pid)"; else echo "watcher: NOT running"; fi
    "$PY" -c "
import psycopg
c = psycopg.connect('$DSN')
n = c.execute(\"select count(*) from information_schema.triggers where trigger_name='zz_monitor_audit'\").fetchone()[0]
m = c.execute('select count(*) from monitor.row_audit').fetchone()[0]
print(f'pg triggers: {n} (audit rows: {m})')
" 2>/dev/null || echo "pg triggers: unreachable"
    f="$ROOT_DIR/data/runtime/manual_test_access.jsonl"
    if [[ -f "$f" ]]; then
      echo "access log: $(wc -l < "$f") requests, last: $(tail -1 "$f" | cut -c1-120)"
    else
      echo "access log: no file yet (middleware writes on first request)"
    fi
    ;;
  tail)
    tail -f "$OUT_DIR/monitor.log"
    ;;
  uninstall)
    "$0" stop || true
    "$PY" - <<EOF
import psycopg
conn = psycopg.connect("$DSN", autocommit=True)
cur = conn.cursor()
tables = [r[0] for r in cur.execute(
    "select table_name from information_schema.tables"
    " where table_schema='public' and table_type='BASE TABLE'").fetchall()]
for t in tables:
    cur.execute(f'DROP TRIGGER IF EXISTS zz_monitor_audit ON public."{t}"')
cur.execute("DROP SCHEMA IF EXISTS monitor CASCADE")
print("triggers and monitor schema removed")
EOF
    ;;
  *)
    echo "usage: $0 {start|stop|status|tail|uninstall}"; exit 1 ;;
esac
