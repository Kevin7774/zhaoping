from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any


class DisabledProvider:
    def __init__(self, service_type: str, service_name: str) -> None:
        self.service_type = service_type
        self.service_name = service_name

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            f"Service '{self.service_name}' for type '{self.service_type}' is disabled. "
            "Configure a concrete provider in config/services.toml before use."
        )


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.35
    max_delay_seconds: float = 3.0
    jitter_seconds: float = 0.08


def friendly_error(exc: Exception, *, provider: str | None = None) -> str:
    label = f"{provider} 调用失败" if provider else "外部能力调用失败"
    message = str(exc).strip() or exc.__class__.__name__
    if "Missing required environment variable" in message:
        return f"{label}：缺少必要环境变量。{message}"
    if "timed out" in message.lower() or "timeout" in message.lower():
        return f"{label}：请求超时，请稍后重试或降低检索范围。"
    if "429" in message:
        return f"{label}：服务限流，请稍后重试。"
    if "401" in message or "403" in message:
        return f"{label}：凭证无效或权限不足。"
    return f"{label}：{message[:500]}"


def call_with_retries(
    fn,
    *,
    provider: str,
    policy: RetryPolicy | None = None,
):
    active_policy = policy or RetryPolicy()
    attempts = max(1, int(active_policy.attempts))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider errors are normalized here.
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(
                active_policy.max_delay_seconds,
                active_policy.base_delay_seconds * (2 ** (attempt - 1)),
            )
            if active_policy.jitter_seconds > 0:
                delay += random.uniform(0, active_policy.jitter_seconds)
            time.sleep(delay)
    assert last_error is not None
    raise RuntimeError(friendly_error(last_error, provider=provider)) from last_error
