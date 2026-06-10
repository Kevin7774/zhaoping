from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_start_script_delegates_to_dev_script_with_safe_process_cleanup() -> None:
    script = ROOT / "start.sh"

    assert script.exists()
    assert os.access(script, os.X_OK)

    content = script.read_text(encoding="utf-8")
    assert "KILL_OLD_DEV=\"${KILL_OLD_DEV:-1}\"" in content
    assert "exec \"$ROOT_DIR/scripts/start_dev.sh\"" in content


def test_dev_script_loads_env_and_can_release_known_dev_ports() -> None:
    content = (ROOT / "scripts" / "start_dev.sh").read_text(encoding="utf-8")

    assert "LOAD_ENV_FILE=\"${LOAD_ENV_FILE:-1}\"" in content
    assert "load_env_file" in content
    assert "KILL_OLD_DEV=\"${KILL_OLD_DEV:-0}\"" in content
    assert "free_port_or_exit" in content
    assert "kill_known_dev_processes_on_port" in content
    assert 'kill_known_dev_processes_on_port "backend" "$BACKEND_PORT"' in content
    assert 'kill_known_dev_processes_on_port "frontend" "$FRONTEND_PORT"' in content
    assert "assert_port_free \"$BACKEND_HOST\" \"$BACKEND_PORT\"" not in content
    assert "assert_port_free \"$FRONTEND_HOST\" \"$FRONTEND_PORT\"" not in content
