#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8020}"
HOST="${HOST:-0.0.0.0}"
BUILD_FRONTEND="${BUILD_FRONTEND:-1}"
RUNTIME_DIR="$ROOT_DIR/data/runtime"
SERVER_LOG="$RUNTIME_DIR/phone_server.log"
SERVER_PID="$RUNTIME_DIR/phone_server.pid"
CLOUDFLARED_LOG="$RUNTIME_DIR/cloudflared.log"
CLOUDFLARED_PID="$RUNTIME_DIR/cloudflared.pid"
CLOUDFLARE_URL_FILE="$RUNTIME_DIR/cloudflare_url.txt"
CLOUDFLARE_LOCK="$RUNTIME_DIR/public_cloudflare.lock"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$HOME/.local/bin/cloudflared}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
FORCE_TUNNEL_RESTART="${FORCE_TUNNEL_RESTART:-0}"
PUBLIC_HEALTH_TIMEOUT="${PUBLIC_HEALTH_TIMEOUT:-8}"

mkdir -p "$RUNTIME_DIR"
exec 9>"$CLOUDFLARE_LOCK"
flock 9

server_healthy() {
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1
}

public_url_healthy() {
  local url="${1:-}"
  [[ -n "$url" ]] && curl -fsS --max-time "$PUBLIC_HEALTH_TIMEOUT" "${url}/health" >/dev/null 2>&1
}

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_file() {
  local file="$1"
  [[ -s "$file" ]] && cat "$file" || true
}

run_detached() {
  setsid -f bash -c 'exec 9>&-; exec "$@"' _ "$@"
}

ensure_cloudflared() {
  if [[ -x "$CLOUDFLARED_BIN" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$CLOUDFLARED_BIN")"
  curl -L --fail --show-error --output "$CLOUDFLARED_BIN" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CLOUDFLARED_BIN"
}

start_server() {
  if server_healthy; then
    local existing_pid
    existing_pid="$(pgrep -f "uvicorn app.api.main:app --host ${HOST} --port ${PORT}" | head -1 || true)"
    [[ -n "$existing_pid" ]] && echo "$existing_pid" > "$SERVER_PID"
    return 0
  fi

  if [[ "$BUILD_FRONTEND" != "0" ]]; then
    VITE_API_BASE="" pnpm --dir frontend build
  fi

  : > "$SERVER_LOG"
  run_detached "$PYTHON_BIN" -m uvicorn app.api.main:app --host "$HOST" --port "$PORT" \
    > "$SERVER_LOG" 2>&1

  for _ in $(seq 1 80); do
    local pid
    pid="$(pgrep -f "uvicorn app.api.main:app --host ${HOST} --port ${PORT}" | head -1 || true)"
    [[ -n "$pid" ]] && echo "$pid" > "$SERVER_PID"
    if server_healthy; then
      return 0
    fi
    sleep 0.5
  done

  echo "[public] backend did not become healthy" >&2
  tail -80 "$SERVER_LOG" >&2 || true
  exit 1
}

existing_tunnel_url() {
  rg -o 'https://[-a-z0-9]+\.trycloudflare\.com' "$CLOUDFLARED_LOG" 2>/dev/null | tail -1 || true
}

stop_pid() {
  local pid="${1:-}"
  if ! pid_alive "$pid"; then
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do
    if ! pid_alive "$pid"; then
      return 0
    fi
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
}

start_tunnel() {
  ensure_cloudflared

  local tunnel_pid url
  tunnel_pid="$(pid_from_file "$CLOUDFLARED_PID")"
  url="$(existing_tunnel_url)"
  if pid_alive "$tunnel_pid" && [[ -n "$url" ]] && [[ "$FORCE_TUNNEL_RESTART" != "1" ]] && public_url_healthy "$url"; then
    echo "$url" > "$CLOUDFLARE_URL_FILE"
    return 0
  fi

  stop_pid "$tunnel_pid"

  rm -f "$CLOUDFLARED_LOG" "$CLOUDFLARED_PID" "$CLOUDFLARE_URL_FILE"
  run_detached "$CLOUDFLARED_BIN" tunnel \
    --url "http://127.0.0.1:${PORT}" \
    --edge-ip-version 4 \
    --protocol http2 \
    --no-autoupdate \
    --logfile "$CLOUDFLARED_LOG" \
    --pidfile "$CLOUDFLARED_PID" \
    >/dev/null 2>&1

  for _ in $(seq 1 100); do
    url="$(existing_tunnel_url)"
    tunnel_pid="$(pid_from_file "$CLOUDFLARED_PID")"
    if pid_alive "$tunnel_pid" && [[ -n "$url" ]]; then
      echo "$url" > "$CLOUDFLARE_URL_FILE"
      return 0
    fi
    sleep 0.5
  done

  echo "[public] cloudflared did not publish a URL" >&2
  tail -100 "$CLOUDFLARED_LOG" >&2 || true
  exit 1
}

start_server
start_tunnel

url="$(cat "$CLOUDFLARE_URL_FILE")"
cat <<EOF
[public] backend: http://127.0.0.1:${PORT}
[public] cloudflare: ${url}
[public] backend pid: $(pid_from_file "$SERVER_PID")
[public] tunnel pid:  $(pid_from_file "$CLOUDFLARED_PID")
EOF
