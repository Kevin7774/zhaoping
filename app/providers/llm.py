from __future__ import annotations

import os
from typing import Any

from app.providers.common import RetryPolicy, call_with_retries


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
        def request():
            result = requests.post(
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
            if result.status_code == 429 or result.status_code >= 500:
                result.raise_for_status()
            return result

        response = call_with_retries(
            request,
            provider="Anthropic-compatible LLM",
            policy=RetryPolicy(attempts=2),
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


class OpenRouterChatLLMProvider:
    def __init__(
        self,
        base_url: str,
        api_key_env: str,
        model: str,
        timeout_seconds: int = 60,
        app_referer: str | None = None,
        app_title: str | None = None,
        models: list[str] | None = None,
        plugins: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.app_referer = app_referer
        self.app_title = app_title
        self.models = models or []
        self.plugins = plugins or []
        self.tools = tools or []

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
        response_format: dict[str, Any] | None = None,
        plugins: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        import requests

        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if model:
            payload["model"] = model
        elif self.models:
            payload["models"] = self.models
        else:
            payload["model"] = self.model
        if response_format:
            payload["response_format"] = response_format

        request_plugins = plugins if plugins is not None else self.plugins
        request_tools = tools if tools is not None else self.tools
        if request_plugins:
            payload["plugins"] = request_plugins
        if request_tools:
            payload["tools"] = request_tools

        def request():
            result = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            if result.status_code == 429 or result.status_code >= 500:
                result.raise_for_status()
            return result

        response = call_with_retries(
            request,
            provider="OpenRouter LLM",
            policy=RetryPolicy(attempts=2),
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OpenRouter API request failed: {response.status_code} {response.text[:500]}") from exc
        return response.json()

    def text(self, prompt: str, max_tokens: int = 64) -> str:
        data = self.message(prompt, max_tokens=max_tokens)
        choices = data.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content)

    def list_models(self) -> list[dict[str, Any]]:
        import requests

        def request():
            result = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            if result.status_code == 429 or result.status_code >= 500:
                result.raise_for_status()
            return result

        response = call_with_retries(
            request,
            provider="OpenRouter models",
            policy=RetryPolicy(attempts=2),
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OpenRouter models request failed: {response.status_code} {response.text[:500]}") from exc
        return response.json().get("data", [])

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        if self.app_referer:
            headers["HTTP-Referer"] = self.app_referer
        if self.app_title:
            headers["X-Title"] = self.app_title
        return headers

    def _api_key(self) -> str:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")
        return api_key
