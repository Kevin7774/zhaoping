#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="$ROOT_DIR/data/runtime"
WATCH_LOG="$RUNTIME_DIR/public_watch.log"
WATCH_PID="$RUNTIME_DIR/public_watch.pid"
CLOUDFLARE_URL_FILE="$RUNTIME_DIR/cloudflare_url.txt"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-10}"
PORT="${PORT:-8020}"
PUBLIC_HEALTH_TIMEOUT="${PUBLIC_HEALTH_TIMEOUT:-8}"

mkdir -p "$RUNTIME_DIR"
echo "$$" > "$WATCH_PID"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$WATCH_LOG"
}

server_healthy() {
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1
}

tunnel_alive() {
  local pid=""
  [[ -s "$RUNTIME_DIR/cloudflared.pid" ]] && pid="$(cat "$RUNTIME_DIR/cloudflared.pid")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

public_healthy() {
  local url=""
  [[ -s "$CLOUDFLARE_URL_FILE" ]] && url="$(cat "$CLOUDFLARE_URL_FILE")"
  [[ -n "$url" ]] && curl -fsS --max-time "$PUBLIC_HEALTH_TIMEOUT" "${url}/health" >/dev/null 2>&1
}

log "watcher started"

while true; do
  restart_reason=""
  force_tunnel=0
  if ! server_healthy; then
    restart_reason="backend unhealthy"
  elif ! tunnel_alive; then
    restart_reason="tunnel process missing"
    force_tunnel=1
  elif ! public_healthy; then
    restart_reason="public URL unhealthy"
    force_tunnel=1
  fi

  if [[ -n "$restart_reason" ]]; then
    log "service unhealthy (${restart_reason}); restarting public cloudflare stack"
    build_frontend=0
    [[ -s "$ROOT_DIR/frontend/dist/index.html" ]] || build_frontend=1
    FORCE_TUNNEL_RESTART="$force_tunnel" BUILD_FRONTEND="$build_frontend" PORT="$PORT" ./scripts/start_public_cloudflare.sh >> "$WATCH_LOG" 2>&1 || true
  fi
  sleep "$INTERVAL_SECONDS"
done
