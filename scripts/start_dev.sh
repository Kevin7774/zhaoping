#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOAD_ENV_FILE="${LOAD_ENV_FILE:-1}"

load_env_file() {
  if [[ "$LOAD_ENV_FILE" == "1" && -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    . "$ROOT_DIR/.env"
    set +a
  fi
}

load_env_file

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
KILL_OLD_DEV="${KILL_OLD_DEV:-0}"
CONDA_ENV="${CONDA_ENV:-robot_agent}"
CONDA_BIN="${CONDA_BIN:-}"
if [[ -z "${USE_CONDA:-}" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    USE_CONDA="0"
  else
    USE_CONDA="1"
  fi
fi
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
BACKEND_RELOAD="${BACKEND_RELOAD:-1}"
PNPM_BIN="${PNPM_BIN:-}"
NPM_BIN="${NPM_BIN:-}"
DEFAULT_PROJECT_ID="${DEFAULT_PROJECT_ID:-project_2026_ai_team}"
CHECK_DEFAULT_PROJECT="${CHECK_DEFAULT_PROJECT:-1}"

pids=()
cleaning_up=0

cleanup() {
  local exit_code=$?
  if [[ "$cleaning_up" == "1" ]]; then
    exit "$exit_code"
  fi
  cleaning_up=1
  trap - EXIT INT TERM
  if ((${#pids[@]} > 0)); then
    echo
    echo "[dev] stopping services..."
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
      fi
    done
    wait "${pids[@]}" 2>/dev/null || true
  fi
  if [[ "${KILL_OLD_DEV:-0}" == "1" ]]; then
    kill_known_dev_processes_on_port "backend" "$BACKEND_PORT"
    kill_known_dev_processes_on_port "frontend" "$FRONTEND_PORT"
  fi
  exit "$exit_code"
}
require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[dev] missing required command: $1" >&2
    exit 1
  fi
}

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

bootstrap_conda_path() {
  local candidates=(
    "$HOME/miniconda3/condabin"
    "$HOME/miniconda3/bin"
    "$HOME/anaconda3/condabin"
    "$HOME/anaconda3/bin"
    "$HOME/mambaforge/condabin"
    "$HOME/mambaforge/bin"
    "/opt/conda/condabin"
    "/opt/conda/bin"
  )
  local dir
  for dir in "${candidates[@]}"; do
    if [[ -d "$dir" ]]; then
      export PATH="$dir:$PATH"
    fi
  done
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

conda_command() {
  local candidates=()
  if [[ -n "$CONDA_BIN" ]]; then
    candidates+=("$CONDA_BIN")
  fi
  candidates+=(
    "$HOME/miniconda3/bin/conda"
    "$HOME/miniconda3/condabin/conda"
  )
  if command -v conda >/dev/null 2>&1; then
    candidates+=("$(command -v conda)")
  fi
  candidates+=(
    "$HOME/anaconda3/bin/conda"
    "$HOME/anaconda3/condabin/conda"
    "$HOME/mambaforge/bin/conda"
    "$HOME/mambaforge/condabin/conda"
    "/opt/conda/bin/conda"
    "/opt/conda/condabin/conda"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

is_wildcard_host() {
  [[ "$1" == "0.0.0.0" || "$1" == "::" ]]
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

access_host_for() {
  local host="$1"
  if is_wildcard_host "$host"; then
    echo "127.0.0.1"
  else
    echo "$host"
  fi
}

public_host_for() {
  local host="$1"
  if [[ -n "$PUBLIC_HOST" ]]; then
    echo "$PUBLIC_HOST"
  elif is_wildcard_host "$host"; then
    detect_lan_ip
  else
    echo "$host"
  fi
}

build_urls() {
  BACKEND_ACCESS_HOST="$(access_host_for "$BACKEND_HOST")"
  FRONTEND_ACCESS_HOST="$(access_host_for "$FRONTEND_HOST")"
  FRONTEND_PUBLIC_HOST="$(public_host_for "$FRONTEND_HOST")"

  if [[ -z "$FRONTEND_PUBLIC_HOST" ]]; then
    FRONTEND_PUBLIC_HOST="$FRONTEND_ACCESS_HOST"
  fi

  BACKEND_URL="http://${BACKEND_ACCESS_HOST}:${BACKEND_PORT}"
  BACKEND_BIND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
  FRONTEND_LOCAL_URL="http://${FRONTEND_ACCESS_HOST}:${FRONTEND_PORT}"
  FRONTEND_PUBLIC_URL="http://${FRONTEND_PUBLIC_HOST}:${FRONTEND_PORT}"
  FRONTEND_BIND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
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

pids_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$port" 2>/dev/null | sed -nE 's/.*pid=([0-9]+).*/\1/p' | sort -u
    return 0
  fi
}

process_cwd() {
  local pid="$1"
  readlink "/proc/$pid/cwd" 2>/dev/null || true
}

process_args() {
  local pid="$1"
  ps -p "$pid" -o args= 2>/dev/null || true
}

is_known_dev_process() {
  local pid="$1"
  local args
  local cwd
  args="$(process_args "$pid")"
  cwd="$(process_cwd "$pid")"

  if [[ "$args" == *"app.api.main:app"* ]]; then
    return 0
  fi

  if [[ "$cwd" == "$ROOT_DIR"* ]] && [[ "$args" == *"vite"* || "$args" == *"pnpm"* || "$args" == *"npm"* || "$args" == *"node"* ]]; then
    return 0
  fi

  return 1
}

wait_for_pid_exit() {
  local pid="$1"
  for _ in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

kill_known_dev_processes_on_port() {
  local role="$1"
  local port="$2"
  local pid
  local args
  local port_pids=()
  mapfile -t port_pids < <(pids_on_port "$port")
  if ((${#port_pids[@]} == 0)); then
    return 0
  fi

  for pid in "${port_pids[@]}"; do
    if [[ -z "$pid" ]]; then
      continue
    fi
    if ! is_known_dev_process "$pid"; then
      args="$(process_args "$pid")"
      echo "[dev] ${role} port ${port} is used by an unknown process; not killing pid=${pid}: ${args}" >&2
      continue
    fi

    args="$(process_args "$pid")"
    echo "[dev] stopping old ${role} process on port ${port}: pid=${pid} ${args}"
    kill "$pid" 2>/dev/null || true
    if ! wait_for_pid_exit "$pid"; then
      echo "[dev] old ${role} process did not stop after SIGTERM; sending SIGKILL: pid=${pid}" >&2
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

free_port_or_exit() {
  local role="$1"
  local host="$2"
  local port="$3"
  local bind_url="$4"

  if assert_port_free "$host" "$port"; then
    return 0
  fi

  if [[ "$KILL_OLD_DEV" == "1" ]]; then
    kill_known_dev_processes_on_port "$role" "$port"
  fi

  if assert_port_free "$host" "$port"; then
    return 0
  fi

  echo "[dev] ${role} port is already in use or unavailable for binding: ${bind_url}" >&2
  if [[ "$KILL_OLD_DEV" != "1" ]]; then
    echo "[dev] re-run with KILL_OLD_DEV=1 or use ./start.sh to stop known old dev processes first." >&2
  fi
  exit 1
}

wait_for_backend() {
  for _ in $(seq 1 60); do
    if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pids[0]}" 2>/dev/null; then
      echo "[dev] backend process exited before health check passed" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "[dev] backend health check timed out: ${BACKEND_URL}/health" >&2
  return 1
}

seed_database_command() {
  if [[ "${USE_CONDA}" == "0" ]]; then
    local python_cmd
    if [[ -x "$PYTHON_BIN" ]]; then
      python_cmd="$PYTHON_BIN"
    else
      python_cmd="python3"
    fi
    echo "set -a; source .env; set +a; ${python_cmd} scripts/seed_db.py"
  else
    echo "set -a; source .env; set +a; ${conda_bin:-conda} run --no-capture-output -n ${CONDA_ENV} python scripts/seed_db.py"
  fi
}

check_default_project() {
  if [[ "$CHECK_DEFAULT_PROJECT" != "1" || -z "$DEFAULT_PROJECT_ID" ]]; then
    return 0
  fi

  local status
  status="$(curl -sS -o /dev/null -w "%{http_code}" "${BACKEND_URL}/projects/${DEFAULT_PROJECT_ID}" || true)"
  if [[ "$status" == "404" ]]; then
    cat <<EOF
[dev] warning: default project not found: ${DEFAULT_PROJECT_ID}
[dev] frontend pages will keep returning 404 until the project database is initialized.
[dev] seed local demo data, if this is your dev database:
[dev]   $(seed_database_command)
[dev] set CHECK_DEFAULT_PROJECT=0 to skip this check.

EOF
  elif [[ "$status" != "200" ]]; then
    echo "[dev] warning: default project check returned HTTP ${status}: ${BACKEND_URL}/projects/${DEFAULT_PROJECT_ID}" >&2
    echo
  fi
}

wait_for_frontend() {
  for _ in $(seq 1 60); do
    if curl -fsS "${FRONTEND_LOCAL_URL}" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${pids[1]}" 2>/dev/null; then
      echo "[dev] frontend process exited before readiness check passed" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "[dev] frontend readiness check timed out: ${FRONTEND_LOCAL_URL}" >&2
  return 1
}

print_urls() {
  cat <<EOF

[dev] services are running
[dev] frontend local: ${FRONTEND_LOCAL_URL}
[dev] frontend phone: ${FRONTEND_PUBLIC_URL}
[dev] backend health: ${BACKEND_URL}/health
[dev] backend bind:   ${BACKEND_BIND_URL}
[dev] frontend bind:  ${FRONTEND_BIND_URL}
[dev] press Ctrl-C to stop both services

EOF

  if [[ "$FRONTEND_PUBLIC_HOST" == "127.0.0.1" || "$FRONTEND_PUBLIC_HOST" == "localhost" ]]; then
    echo "[dev] warning: no LAN IP was detected. Set PUBLIC_HOST=<your-computer-ip> and restart if your phone cannot open the site."
    echo
  fi
}

trap cleanup EXIT INT TERM

require_command python3
require_command curl
bootstrap_node_path
bootstrap_conda_path
build_urls

if [[ "${USE_CONDA}" != "0" ]]; then
  conda_bin="$(conda_command || true)"
  if [[ -z "$conda_bin" ]]; then
    echo "[dev] missing required command: conda. Set CONDA_BIN=/path/to/conda or USE_CONDA=0." >&2
    exit 1
  fi
fi

frontend_bin="$(frontend_command || true)"
if [[ -z "$frontend_bin" ]]; then
  echo "[dev] missing frontend package manager: install pnpm or npm, or set PNPM_BIN/NPM_BIN" >&2
  exit 1
fi

free_port_or_exit "backend" "$BACKEND_HOST" "$BACKEND_PORT" "$BACKEND_BIND_URL"
free_port_or_exit "frontend" "$FRONTEND_HOST" "$FRONTEND_PORT" "$FRONTEND_BIND_URL"

cd "$ROOT_DIR"

backend_args=(app.api.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
if [[ "${BACKEND_RELOAD}" == "1" ]]; then
  backend_args+=(--reload --reload-dir "$ROOT_DIR/app" --reload-dir "$ROOT_DIR/config")
fi

if [[ "${USE_CONDA}" == "0" ]]; then
  if [[ -x "$PYTHON_BIN" ]]; then
    backend_python="$PYTHON_BIN"
  else
    backend_python="python3"
  fi
  backend_cmd=("$backend_python" -m uvicorn "${backend_args[@]}")
else
  backend_cmd=("$conda_bin" run --no-capture-output -n "$CONDA_ENV" uvicorn "${backend_args[@]}")
fi

echo "[dev] starting backend: ${BACKEND_BIND_URL}"
"${backend_cmd[@]}" &
pids+=("$!")

wait_for_backend
check_default_project

echo "[dev] starting frontend: ${FRONTEND_BIND_URL}"
if [[ "$(basename "$frontend_bin")" == "pnpm" ]]; then
  VITE_API_TARGET="$BACKEND_URL" "$frontend_bin" --dir "$ROOT_DIR/frontend" dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
else
  VITE_API_TARGET="$BACKEND_URL" "$frontend_bin" --prefix "$ROOT_DIR/frontend" run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
fi
pids+=("$!")

wait_for_frontend
print_urls

wait -n "${pids[@]}"
