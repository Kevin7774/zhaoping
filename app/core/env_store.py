from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from app.core.config import ENV_PATH_ENV, AppConfig, load_app_config

ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
ENV_LINE_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
DEFAULT_ENV_PATH = Path(".env")
DEFAULT_ENV_EXAMPLE_PATH = Path(".env.example")


def allowed_env_keys(config: AppConfig | None = None, env_example_path: Path | None = None) -> set[str]:
    keys: set[str] = set()
    example_path = env_example_path or DEFAULT_ENV_EXAMPLE_PATH
    if example_path.exists():
        for line in example_path.read_text(encoding="utf-8").splitlines():
            match = ENV_LINE_PATTERN.match(line.strip())
            if match and ENV_KEY_PATTERN.match(match.group(1)):
                keys.add(match.group(1))

    active_config = config or load_app_config()
    for service in active_config.services.values():
        for field_name, env_name in (service.model_extra or {}).items():
            if field_name.endswith("_env") and isinstance(env_name, str) and ENV_KEY_PATTERN.match(env_name):
                keys.add(env_name)
    return keys


def save_env_values(
    values: dict[str, str],
    *,
    env_path: Path | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    normalized = {str(key).strip(): str(value) for key, value in values.items()}
    if not normalized:
        raise ValueError("No environment values provided.")

    allowed = allowed_env_keys(config)
    invalid = [
        key
        for key in normalized
        if not ENV_KEY_PATTERN.match(key) or key not in allowed
    ]
    if invalid:
        raise ValueError(f"Unsupported environment variable(s): {', '.join(sorted(invalid))}")

    path = env_path or Path(os.environ.get(ENV_PATH_ENV) or DEFAULT_ENV_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    original_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    updated: set[str] = set()
    output_lines: list[str] = []
    for line in original_lines:
        match = ENV_LINE_PATTERN.match(line)
        if not match:
            output_lines.append(line)
            continue
        key = match.group(1)
        if key in normalized:
            output_lines.append(f"{key}={_format_env_value(normalized[key])}")
            updated.add(key)
        else:
            output_lines.append(line)

    for key in sorted(set(normalized) - updated):
        output_lines.append(f"{key}={_format_env_value(normalized[key])}")

    path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")
    for key, value in normalized.items():
        os.environ[key] = value

    return {
        "env_path": str(path),
        "updated": sorted(normalized),
    }


def _format_env_value(value: str) -> str:
    if value == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,~^{}\\-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
