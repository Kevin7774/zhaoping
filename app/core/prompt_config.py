from __future__ import annotations

import json
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_system_prompt(name: str, *, default: str = "") -> str:
    """Load a small prompt config without adding a YAML runtime dependency."""

    for suffix in (".yaml", ".yml", ".json"):
        path = PROMPT_DIR / f"{name}{suffix}"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if suffix == ".json":
            payload = json.loads(text)
            return str(payload.get("system_prompt") or default).strip()
        return _parse_yaml_system_prompt(text) or default
    return default


def _parse_yaml_system_prompt(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in {"system_prompt: |", "system_prompt: |-", "system_prompt: |+"}:
            block: list[str] = []
            for raw_line in lines[index + 1 :]:
                if raw_line and not raw_line.startswith((" ", "\t")):
                    break
                block.append(raw_line[2:] if raw_line.startswith("  ") else raw_line.lstrip("\t"))
            return "\n".join(block).strip()
        if stripped.startswith("system_prompt:"):
            value = stripped.split(":", 1)[1].strip()
            return value.strip("'\"")
    return ""
