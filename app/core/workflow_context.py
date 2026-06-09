from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|token|secret|authorization|bearer)\b\s*[:=]\s*([^\s,;}\]]+)",
    re.IGNORECASE,
)
SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|ghp|gho|ghu|ghs|xox[baprs])[-_][A-Za-z0-9_-]{6,}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PROVIDER_INTERNAL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Provider|Client|Adapter)\b")
DEFAULT_PROMPT_CONTEXT_BUDGET_CHARS = 4000


def normalize_context_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): normalize_context_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_context_value(child) for child in value]
    try:
        json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)
    return value


def render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(normalize_context_value(value), ensure_ascii=False, indent=2, default=str)


def render_template(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"Missing template variable: {key}")
        return render_value(context[key])

    return PLACEHOLDER_RE.sub(replace, template)


def find_placeholders(template: str | None) -> list[str]:
    if not template:
        return []
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(template)))


def build_prompt_context(
    step_prompt: str,
    raw_context: dict[str, Any],
    max_chars: int = DEFAULT_PROMPT_CONTEXT_BUDGET_CHARS,
) -> dict[str, Any]:
    used_keys = find_placeholders(step_prompt)
    if not used_keys:
        return {}
    budget_per_key = max(max_chars // len(used_keys), 1)
    safe_context: dict[str, Any] = {}
    for key in used_keys:
        if key in raw_context:
            safe_context[key] = _budget_context_value(raw_context[key], budget_per_key)
    return safe_context


def _budget_context_value(value: Any, max_chars: int) -> Any:
    normalized = normalize_context_value(value)
    if len(render_value(normalized)) <= max_chars:
        return normalized
    if isinstance(normalized, list):
        return _budget_context_list(normalized, max_chars)
    return truncate_text(normalized, max_chars)


def _budget_context_list(values: list[Any], max_chars: int) -> Any:
    selected = values[:3]
    while len(selected) > 1 and len(render_value(selected)) > max_chars:
        selected = selected[:-1]
    if selected and len(render_value(selected)) > max_chars:
        return [truncate_text(selected[0], max_chars)]
    return selected


def truncate_text(value: Any, max_chars: int) -> str:
    text = value if isinstance(value, str) else render_value(value)
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    return text[: max_chars - 20] + "\n...[truncated]"


def sanitize_failure_text(value: Any) -> str:
    text = value if isinstance(value, str) else render_value(value)
    text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    text = SECRET_TOKEN_RE.sub("[redacted]", text)
    text = EMAIL_RE.sub("[redacted-email]", text)
    text = PROVIDER_INTERNAL_RE.sub("[provider-internal]", text)
    return text


def retry_prompt(schema: dict[str, Any], last_output: str, validation_error: str) -> str:
    safe_last_output = sanitize_failure_text(last_output)
    safe_validation_error = sanitize_failure_text(validation_error)
    return (
        "你是一个数据修正助手。上一次你的输出未通过 Pydantic 校验。\n\n"
        f"【期待的 Schema】：\n{truncate_text(schema, 4000)}\n\n"
        f"【你上一次的错误输出】：\n{truncate_text(safe_last_output, 4000)}\n\n"
        f"【校验失败原因】：\n{truncate_text(safe_validation_error, 2000)}\n\n"
        "请重新调整你的输出。只输出符合 Schema 的合法 JSON，不要输出解释、Markdown 或额外文本。"
    )
