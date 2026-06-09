from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


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


def truncate_text(value: Any, max_chars: int) -> str:
    text = value if isinstance(value, str) else render_value(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...[truncated]"


def retry_prompt(schema: dict[str, Any], last_output: str, validation_error: str) -> str:
    return (
        "你是一个数据修正助手。上一次你的输出未通过 Pydantic 校验。\n\n"
        f"【期待的 Schema】：\n{truncate_text(schema, 4000)}\n\n"
        f"【你上一次的错误输出】：\n{truncate_text(last_output, 4000)}\n\n"
        f"【校验失败原因】：\n{truncate_text(validation_error, 2000)}\n\n"
        "请重新调整你的输出。只输出符合 Schema 的合法 JSON，不要输出解释、Markdown 或额外文本。"
    )
