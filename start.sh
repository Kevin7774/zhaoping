#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export LOAD_ENV_FILE="${LOAD_ENV_FILE:-1}"
export KILL_OLD_DEV="${KILL_OLD_DEV:-1}"

exec "$ROOT_DIR/scripts/start_dev.sh" "$@"
