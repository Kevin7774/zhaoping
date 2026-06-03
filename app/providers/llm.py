from __future__ import annotations

import os
from typing import Any


class AnthropicCompatibleLLMProvider:
    def __init__(
        self,
        base_url: str,
        api_key_env: str,
        model: str,
        anthropic_version: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.anthropic_version = anthropic_version
        self.timeout_seconds = timeout_seconds

    def message(self, prompt: str, max_tokens: int = 64, temperature: float = 0) -> dict[str, Any]:
        return self.messages(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 256,
        temperature: float = 0,
        model: str | None = None,
    ) -> dict[str, Any]:
        import requests

        api_key = self._api_key()
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": self.anthropic_version,
                "content-type": "application/json",
            },
            json={
                "model": model or self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Anthropic-compatible API request failed: {response.status_code} {response.text[:500]}") from exc
        return response.json()

    def text(self, prompt: str, max_tokens: int = 64) -> str:
        data = self.message(prompt, max_tokens=max_tokens)
        chunks = data.get("content", [])
        return "".join(chunk.get("text", "") for chunk in chunks if chunk.get("type") == "text")

    def _api_key(self) -> str:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")
        return api_key
