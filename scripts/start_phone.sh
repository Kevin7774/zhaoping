#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8020}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
PNPM_BIN="${PNPM_BIN:-}"
NPM_BIN="${NPM_BIN:-}"

bootstrap_node_path() {
  export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
  export PATH="$PNPM_HOME/bin:$PNPM_HOME:$HOME/.npm-global/bin:$PATH"

  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  fi
  if [[ -s "$HOME/.asdf/asdf.sh" ]]; then
    # shellcheck source=/dev/null
    . "$HOME/.asdf/asdf.sh" >/dev/null 2>&1 || true
  fi
}

frontend_command() {
  if [[ -n "$PNPM_BIN" ]]; then
    echo "$PNPM_BIN"
    return 0
  fi
  if command -v pnpm >/dev/null 2>&1; then
    command -v pnpm
    return 0
  fi
  if [[ -n "$NPM_BIN" ]]; then
    echo "$NPM_BIN"
    return 0
  fi
  if command -v npm >/dev/null 2>&1; then
    command -v npm
    return 0
  fi
  return 1
}

detect_lan_ip() {
  python3 - <<'PY'
import socket

ip = ""
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
except OSError:
    pass

if ip and not ip.startswith("127."):
    print(ip)
PY
}

assert_port_free() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        raise SystemExit(1)
PY
}

bootstrap_node_path
frontend_bin="$(frontend_command || true)"
if [[ -z "$frontend_bin" ]]; then
  echo "[phone] missing frontend package manager: install pnpm or npm, or set PNPM_BIN/NPM_BIN" >&2
  exit 1
fi

if [[ -x "$PYTHON_BIN" ]]; then
  backend_python="$PYTHON_BIN"
else
  backend_python="python3"
fi

if ! assert_port_free "$HOST" "$PORT"; then
  echo "[phone] port is already in use or unavailable for binding: http://${HOST}:${PORT}" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[phone] building production frontend..."
if [[ "$(basename "$frontend_bin")" == "pnpm" ]]; then
  VITE_API_BASE="" "$frontend_bin" --dir "$ROOT_DIR/frontend" build
else
  VITE_API_BASE="" "$frontend_bin" --prefix "$ROOT_DIR/frontend" run build
fi

public_host="$PUBLIC_HOST"
if [[ -z "$public_host" ]]; then
  public_host="$(detect_lan_ip)"
fi
if [[ -z "$public_host" ]]; then
  public_host="127.0.0.1"
fi

cat <<EOF

[phone] production site is starting
[phone] local: http://127.0.0.1:${PORT}
[phone] phone: http://${public_host}:${PORT}
[phone] press Ctrl-C to stop

EOF

"$backend_python" -m uvicorn app.api.main:app --host "$HOST" --port "$PORT"
