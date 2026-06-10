from __future__ import annotations

import csv
import re
import importlib.util
import io
import json
import os
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from html import unescape
from hashlib import sha256
from typing import Any
from xml.etree import ElementTree
from urllib.parse import urljoin
from urllib.parse import quote_plus


class SearchProviderProtocol:
    def search(self, query: str, limit: int = 5) -> list[dict]:
        raise NotImplementedError


class SearchSourceCatalogProvider:
    def __init__(self, data_sources: dict[str, dict[str, Any]]) -> None:
        self.data_sources = data_sources

    def search(self, query: str, limit: int = 5) -> list[dict]:
        scored = [
            (self._score_source(query, source), source_key, source)
            for source_key, source in self.data_sources.items()
        ]
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        return [
            self._to_result(source_key, source, score)
            for score, source_key, source in ranked
            if score > 0
        ][:limit]

    def list_sources(self) -> list[dict]:
        return [
            self._to_result(source_key, source, score=0)
            for source_key, source in self.data_sources.items()
        ]

    def plan(self, query: str, limit: int = 8) -> dict:
        return {
            "query": query,
            "recommended_sources": self.search(query, limit=limit),
            "guardrails": [
                "优先使用官方 API、授权账号、公开网页、公开论文/披露文件或人工导出。",
                "不绕过登录、付费墙、robots.txt、平台反爬或访问控制。",
                "候选人个人信息只采集公开且与招聘评估相关的职业线索，并记录来源。",
            ],
        }

    def _score_source(self, query: str, source: dict[str, Any]) -> int:
        normalized_query = query.casefold()
        haystack_parts = [
            str(source.get("name_zh", "")),
            str(source.get("purpose", "")),
            " ".join(str(item) for item in source.get("source_names", [])),
            " ".join(str(item) for item in source.get("talent_signals", [])),
            " ".join(str(item) for item in source.get("suggested_queries", [])),
        ]
        haystack = " ".join(haystack_parts).casefold()

        score = 0
        for token in self._tokens(normalized_query):
            if token in haystack:
                score += 1
        if normalized_query and normalized_query in haystack:
            score += 3
        return score

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return [
            token.strip(" ,，/|:：()（）[]【】")
            for token in query.replace("/", " ").replace("-", " ").split()
            if token.strip(" ,，/|:：()（）[]【】")
        ]

    @staticmethod
    def _to_result(source_key: str, source: dict[str, Any], score: int) -> dict:
        return {
            "source_key": source_key,
            "name_zh": source["name_zh"],
            "source_names": source["source_names"],
            "purpose": source["purpose"],
            "talent_signals": source["talent_signals"],
            "suggested_queries": source["suggested_queries"],
            "access_pattern": source["access_pattern"],
            "risk_level": source["risk_level"],
            "freshness": source["freshness"],
            "source_type": source.get("source_type", "source_catalog"),
            "score": score,
        }


class ExternalSearchToolProvider:
    """Configured adapter for external search/scraping/browser tools.

    These tools often need local installation, browser login state, or human
    supervision. By default the provider returns an actionable retrieval plan
    instead of silently launching browsers or logged-in sessions.
    """

    def __init__(
        self,
        service_name: str,
        tool_name: str,
        source_key: str,
        name_zh: str,
        source_type: str,
        project_url: str,
        purpose: str,
        access_pattern: str,
        risk_level: str,
        freshness: str,
        supported_platforms: list[str] | None = None,
        install_hint: str | None = None,
        setup_steps: list[str] | None = None,
        guardrails: list[str] | None = None,
        required_command: str | None = None,
        required_python_module: str | None = None,
        required_skill_path: str | None = None,
        command_args: list[str] | None = None,
        execute_enabled: bool = False,
        manual_setup_required: bool = True,
        timeout_seconds: int = 60,
    ) -> None:
        self.service_name = service_name
        self.tool_name = tool_name
        self.source_key = source_key
        self.name_zh = name_zh
        self.source_type = source_type
        self.project_url = project_url
        self.purpose = purpose
        self.access_pattern = access_pattern
        self.risk_level = risk_level
        self.freshness = freshness
        self.supported_platforms = supported_platforms or []
        self.install_hint = install_hint
        self.setup_steps = setup_steps or []
        self.guardrails = guardrails or []
        self.required_command = required_command
        self.required_python_module = required_python_module
        self.required_skill_path = required_skill_path
        self.command_args = command_args or []
        self.execute_enabled = execute_enabled
        self.manual_setup_required = manual_setup_required
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if self.execute_enabled:
            return self._execute(query=query, limit=limit)
        return [self._planned_result(query=query, rank=1)]

    def plan(self, query: str, limit: int = 5) -> dict:
        return {
            "query": query,
            "mode": "external_search_tool_plan",
            "service": self.service_name,
            "tool_name": self.tool_name,
            "recommended_sources": self.search(query, limit=limit),
            "setup": {
                "install_hint": self.install_hint,
                "setup_steps": self.setup_steps,
                "runtime_requirements": self._runtime_requirements(),
                "manual_setup_required": self.manual_setup_required,
                "execute_enabled": self.execute_enabled,
            },
            "guardrails": self._guardrails(),
        }

    def source_metadata(self) -> dict[str, str]:
        return {
            "source_key": self.source_key,
            "name_zh": self.name_zh,
            "source_type": self.source_type,
        }

    def _planned_result(self, query: str, rank: int) -> dict:
        runtime_requirements = self._runtime_requirements()
        missing = [item for item in runtime_requirements if not item["present"]]
        if missing:
            retrieval_status = "setup_required"
        elif self.manual_setup_required:
            retrieval_status = "manual_required"
        else:
            retrieval_status = "planned_external_tool"

        return {
            "source_key": self.source_key,
            "name_zh": self.name_zh,
            "source_type": self.source_type,
            "query": query,
            "rank": rank,
            "title": f"{self.name_zh} 外部搜索入口",
            "url": self.project_url,
            "snippet": self.purpose,
            "published_at": None,
            "retrieval_status": retrieval_status,
            "tool_name": self.tool_name,
            "supported_platforms": self.supported_platforms,
            "install_hint": self.install_hint,
            "setup_steps": self.setup_steps,
            "runtime_requirements": runtime_requirements,
            "manual_setup_required": self.manual_setup_required,
            "execute_enabled": self.execute_enabled,
            "command_preview": self._command_preview(query, limit=1),
            "access_pattern": self.access_pattern,
            "risk_level": self.risk_level,
            "freshness": self.freshness,
            "guardrails": self._guardrails(),
        }

    def _execute(self, query: str, limit: int) -> list[dict]:
        if not self.required_command:
            raise RuntimeError(f"External tool '{self.tool_name}' has no executable command configured.")
        if not shutil.which(self.required_command):
            raise RuntimeError(f"Missing required external command: {self.required_command}")
        if self.required_python_module and importlib.util.find_spec(self.required_python_module) is None:
            raise RuntimeError(f"Missing required Python module: {self.required_python_module}")
        if self.required_skill_path and not os.path.exists(os.path.expanduser(self.required_skill_path)):
            raise RuntimeError(f"Missing required skill path: {self.required_skill_path}")
        if not self.command_args:
            raise RuntimeError(f"External tool '{self.tool_name}' has no command_args configured.")

        args = [self.required_command, *self._render_command_args(query=query, limit=limit)]
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"{self.tool_name} command failed with exit code {completed.returncode}: {message[:300]}")
        return self._results_from_output(query=query, output=completed.stdout, limit=limit)

    def _results_from_output(self, query: str, output: str, limit: int) -> list[dict]:
        normalized_limit = max(1, int(limit))
        payload: Any
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return [
                {
                    **self._planned_result(query=query, rank=1),
                    "title": f"{self.name_zh} 命令输出",
                    "snippet": output.strip()[:1000],
                    "retrieval_status": "retrieved",
                }
            ]

        items = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            items = [payload]
        results = []
        for rank, item in enumerate(items[:normalized_limit], start=1):
            if not isinstance(item, dict):
                item = {"snippet": str(item)}
            results.append(
                {
                    **self._planned_result(query=query, rank=rank),
                    "title": str(item.get("title") or item.get("name") or self.name_zh),
                    "url": str(item.get("url") or item.get("link") or self.project_url),
                    "snippet": str(item.get("snippet") or item.get("description") or item.get("text") or "")[:1000],
                    "published_at": item.get("published_at") or item.get("created_at") or item.get("updated_at"),
                    "retrieval_status": "retrieved",
                    "raw": item,
                }
            )
        return results

    def _runtime_requirements(self) -> list[dict[str, Any]]:
        requirements: list[dict[str, Any]] = []
        if self.required_command:
            requirements.append(
                {
                    "type": "command",
                    "name": self.required_command,
                    "present": bool(shutil.which(self.required_command)),
                }
            )
        if self.required_python_module:
            requirements.append(
                {
                    "type": "python_module",
                    "name": self.required_python_module,
                    "present": importlib.util.find_spec(self.required_python_module) is not None,
                }
            )
        if self.required_skill_path:
            expanded_path = os.path.expanduser(self.required_skill_path)
            requirements.append(
                {
                    "type": "skill_path",
                    "name": self.required_skill_path,
                    "present": os.path.exists(expanded_path),
                }
            )
        return requirements

    def _command_preview(self, query: str, limit: int) -> list[str]:
        if not self.required_command or not self.command_args:
            return []
        return [self.required_command, *self._render_command_args(query=query, limit=limit)]

    def _render_command_args(self, query: str, limit: int) -> list[str]:
        return [
            str(arg).replace("{query}", query).replace("{limit}", str(limit))
            for arg in self.command_args
        ]

    def _guardrails(self) -> list[str]:
        default_guardrails = [
            "只使用公开页面、官方 API、授权账号、用户提供材料或人工确认过的登录态。",
            "不绕过访问控制、付费墙、平台条款、robots.txt 或明确反爬限制。",
            "涉及候选人或个人账号时，只保留公开职业信息和岗位相关能力证据。",
        ]
        return self.guardrails or default_guardrails


class AgentReachSocialSearchProvider:
    """Executable fan-out provider for Chinese/social platforms via local CLIs."""

    def __init__(
        self,
        service_name: str = "agent_reach_social_search",
        platform_commands: dict[str, dict[str, Any]] | None = None,
        supported_platforms: list[str] | None = None,
        required_commands: list[str] | None = None,
        project_url: str = "https://github.com/Panniantong/Agent-Reach",
        timeout_seconds: int = 60,
        risk_level: str = "high",
        freshness: str = "daily",
    ) -> None:
        self.service_name = service_name
        self.platform_commands = platform_commands or {}
        self.supported_platforms = supported_platforms or list(self.platform_commands)
        self.required_commands = required_commands or []
        self.project_url = project_url
        self.timeout_seconds = timeout_seconds
        self.risk_level = risk_level
        self.freshness = freshness

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 20))
        results: list[dict[str, Any]] = []
        rank = 1
        for platform, settings in self.platform_commands.items():
            command = str(settings.get("command") or "")
            args_template = [str(item) for item in settings.get("args", [])]
            name_zh = str(settings.get("name_zh") or platform)
            if not command or not args_template:
                results.append(self._status_result(query, rank, platform, name_zh, "config_error", "Missing command config."))
                rank += 1
                continue
            if not shutil.which(command):
                results.append(self._status_result(query, rank, platform, name_zh, "setup_required", f"Missing command: {command}"))
                rank += 1
                continue

            args = [command, *self._render_args(args_template, query=query, limit=normalized_limit)]
            try:
                completed = subprocess.run(
                    args,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                results.append(self._status_result(query, rank, platform, name_zh, "error", f"Timed out after {self.timeout_seconds}s"))
                rank += 1
                continue
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "").strip()[:300]
                results.append(self._status_result(query, rank, platform, name_zh, "error", message))
                rank += 1
                continue

            items = self._items_from_output(completed.stdout)
            if not items:
                results.append(self._status_result(query, rank, platform, name_zh, "empty", "No results returned."))
                rank += 1
                continue
            for item in items[:normalized_limit]:
                results.append(self._to_result(query=query, rank=rank, platform=platform, name_zh=name_zh, item=item))
                rank += 1
        return results

    def plan(self, query: str, limit: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "mode": "agent_reach_social_search",
            "service": self.service_name,
            "supported_platforms": self.supported_platforms,
            "runtime_requirements": self._runtime_requirements(),
            "command_previews": {
                platform: [
                    str(settings.get("command")),
                    *self._render_args([str(item) for item in settings.get("args", [])], query=query, limit=max(1, int(limit))),
                ]
                for platform, settings in self.platform_commands.items()
            },
            "guardrails": self._guardrails(),
        }

    def source_metadata(self) -> dict[str, str]:
        return {
            "source_key": self.service_name,
            "name_zh": "Agent-Reach 社媒搜索",
            "source_type": "social_platform_search",
        }

    @staticmethod
    def _render_args(args: list[str], *, query: str, limit: int) -> list[str]:
        values = {
            "query": query,
            "query_json": json.dumps(query, ensure_ascii=False),
            "query_mcporter": query.replace("\\", "\\\\").replace('"', '\\"'),
            "query_url": quote_plus(query),
            "limit": str(limit),
        }
        rendered = []
        for arg in args:
            value = arg
            for key, replacement in values.items():
                value = value.replace("{" + key + "}", replacement)
            rendered.append(value)
        return rendered

    @classmethod
    def _items_from_output(cls, output: str) -> list[dict[str, Any]]:
        text = output.strip()
        if not text:
            return []
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError:
            parsed = cls._item_from_text_search_output(text)
            if parsed:
                return [parsed]
            return [{"text": text}]
        return cls._items_from_payload(payload)

    @staticmethod
    def _item_from_text_search_output(text: str) -> dict[str, Any] | None:
        item: dict[str, Any] = {}
        highlights: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("Title:"):
                item["title"] = line.removeprefix("Title:").strip()
            elif line.startswith("URL:"):
                item["url"] = line.removeprefix("URL:").strip()
            elif line.startswith("Published:"):
                item["published_at"] = line.removeprefix("Published:").strip()
            elif line and not line.startswith(("Author:", "Highlights:", "[...]")):
                highlights.append(line)
        if not item:
            return None
        if highlights:
            item["snippet"] = "\n".join(highlights[:12])
        return item

    @classmethod
    def _items_from_payload(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item if isinstance(item, dict) else {"text": str(item)} for item in payload]
        if not isinstance(payload, dict):
            return [{"text": str(payload)}]
        for key in ("results", "data", "items", "feeds", "notes", "list", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item if isinstance(item, dict) else {"text": str(item)} for item in value]
            if isinstance(value, dict):
                nested = cls._items_from_payload(value)
                if nested:
                    return nested
        return [payload]

    def _to_result(self, *, query: str, rank: int, platform: str, name_zh: str, item: dict[str, Any]) -> dict[str, Any]:
        title = (
            item.get("title")
            or item.get("name")
            or item.get("desc")
            or item.get("text")
            or item.get("content")
            or f"{name_zh} result"
        )
        url = item.get("url") or item.get("link") or item.get("href") or item.get("share_url") or ""
        snippet = item.get("snippet") or item.get("description") or item.get("text") or item.get("content") or ""
        return {
            "source_key": self.service_name,
            "name_zh": "Agent-Reach 社媒搜索",
            "source_type": "social_platform_search",
            "query": query,
            "rank": rank,
            "platform": platform,
            "platform_name_zh": name_zh,
            "title": str(title)[:300],
            "url": str(url),
            "snippet": str(snippet)[:1000],
            "published_at": item.get("published_at") or item.get("created_at") or item.get("time") or item.get("date"),
            "retrieval_status": "retrieved",
            "risk_level": self.risk_level,
            "freshness": self.freshness,
            "raw": item,
        }

    def _status_result(self, query: str, rank: int, platform: str, name_zh: str, status: str, message: str) -> dict[str, Any]:
        return {
            "source_key": self.service_name,
            "name_zh": "Agent-Reach 社媒搜索",
            "source_type": "social_platform_search",
            "query": query,
            "rank": rank,
            "platform": platform,
            "platform_name_zh": name_zh,
            "title": f"{name_zh} {status}",
            "url": self.project_url,
            "snippet": message,
            "published_at": None,
            "retrieval_status": status,
            "error": message if status in {"setup_required", "config_error", "error"} else None,
            "risk_level": self.risk_level,
            "freshness": self.freshness,
        }

    def _runtime_requirements(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "command",
                "name": command,
                "present": bool(shutil.which(command)),
            }
            for command in self.required_commands
        ]

    @staticmethod
    def _guardrails() -> list[str]:
        return [
            "只使用公开页面、官方 API、授权账号、用户提供材料或人工确认过的登录态。",
            "不绕过登录、付费墙、robots.txt、访问控制、平台条款或明确反爬限制。",
            "社媒内容只能作为候选线索；关键结论必须回看原文并交叉验证。",
            "候选人相关信息仅限公开职业信息和岗位相关能力证据。",
        ]


class BraveWebSearchProvider:
    def __init__(
        self,
        api_key_env: str,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
        country: str = "US",
        search_lang: str = "en",
        ui_lang: str = "en-US",
        safesearch: str = "moderate",
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key_env = api_key_env
        self.endpoint = endpoint
        self.country = country
        self.search_lang = search_lang
        self.ui_lang = ui_lang
        self.safesearch = safesearch
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 20))
        params = {
            "q": query,
            "count": normalized_limit,
            "country": self.country,
            "search_lang": self.search_lang,
            "ui_lang": self.ui_lang,
            "safesearch": self.safesearch,
            "spellcheck": "1",
            "result_filter": "web",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

        import requests

        response = requests.get(
            self.endpoint,
            params=params,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Brave Search request failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        web_results = (payload.get("web") or {}).get("results") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(web_results[:normalized_limit], start=1)
        ]

    def plan(self, query: str, limit: int = 5) -> dict:
        return {
            "query": query,
            "recommended_sources": self.search(query, limit=limit),
            "evidence_record_defaults": {
                "source_type": "open_web",
                "source_key": "brave_web_search",
                "validation_status": "single_source",
            },
            "guardrails": [
                "将 Brave 返回结果作为开放网页证据候选，写入 evidence 前必须保留 URL、标题、摘要和检索时间。",
                "能力结论不得仅由单次 Brave 搜索决定，至少再结合学术、产业、开源或人工反馈来源交叉验证。",
                "不要采集候选人非公开个人信息，不绕过登录、付费墙或访问控制。",
            ],
        }

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        return {
            "source_key": "brave_web_search",
            "name_zh": "Brave Search",
            "source_type": "open_web",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "snippet": item.get("description", ""),
            "published_at": item.get("page_age") or item.get("age"),
            "language": item.get("language"),
            "family_friendly": item.get("family_friendly"),
        }


class _GitHubAPIClient:
    def __init__(
        self,
        *,
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
        api_version: str = "2022-11-28",
    ) -> None:
        self.token_env = token_env
        self.timeout_seconds = timeout_seconds
        self.api_version = api_version
        self.last_rate_limit: dict[str, Any] = {}

    def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str = "application/vnd.github+json",
        error_context: str = "GitHub API request",
    ) -> Any:
        headers = self.headers(accept=accept)

        import requests

        response = requests.get(
            endpoint,
            params=params or {},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        self._record_rate_limit(response)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"{error_context} failed: {response.status_code} {response.text[:300]}") from exc
        return response.json()

    def headers(self, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": self.api_version,
        }
        if self.token_env:
            token = os.environ.get(self.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _record_rate_limit(self, response: Any) -> None:
        headers = getattr(response, "headers", {}) or {}
        remaining = headers.get("X-RateLimit-Remaining")
        resource = headers.get("X-RateLimit-Resource") or "core"
        if remaining is None:
            return
        self.last_rate_limit = {
            "resource": resource,
            "limit": _safe_int(headers.get("X-RateLimit-Limit")),
            "remaining": _safe_int(remaining),
            "reset": _safe_int(headers.get("X-RateLimit-Reset")),
        }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _github_limit(limit: int, *, max_limit: int = 100) -> int:
    return max(1, min(int(limit), max_limit))


def _github_profile_url(login: str | None) -> str | None:
    return f"https://github.com/{login}" if login else None


def _github_query_tokens(query: str) -> list[str]:
    ignored = {
        "and",
        "or",
        "not",
        "in",
        "is",
        "user",
        "org",
        "repo",
        "language",
        "topic",
        "stars",
        "forks",
        "pushed",
        "created",
        "updated",
    }
    tokens = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", query.casefold()):
        if len(token) < 2 or token in ignored:
            continue
        tokens.append(token)
    return _unique_ordered(tokens)


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _github_text_fragment(item: dict[str, Any]) -> str:
    text_matches = item.get("text_matches")
    if isinstance(text_matches, list):
        fragments = [
            str(match.get("fragment", "")).strip()
            for match in text_matches
            if isinstance(match, dict) and str(match.get("fragment", "")).strip()
        ]
        if fragments:
            return " ".join(fragments)[:700]
    return str(item.get("description") or item.get("name") or item.get("path") or "")[:700]


def _github_repository_summary(item: dict[str, Any]) -> dict[str, Any]:
    topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    return {
        "full_name": item.get("full_name") or item.get("name") or "",
        "url": item.get("html_url") or "",
        "description": item.get("description") or "",
        "language": item.get("language"),
        "stars": _safe_int(item.get("stargazers_count")),
        "forks": _safe_int(item.get("forks_count")),
        "topics": [str(topic) for topic in topics[:12]],
        "pushed_at": item.get("pushed_at"),
        "updated_at": item.get("updated_at"),
        "owner_login": owner.get("login"),
        "owner_type": owner.get("type"),
    }


def _github_repository_key(repo: dict[str, Any]) -> tuple[str, str]:
    return (str(repo.get("full_name") or ""), str(repo.get("url") or ""))


def _github_code_hit_summary(item: dict[str, Any]) -> dict[str, Any]:
    repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
    owner = repository.get("owner") if isinstance(repository.get("owner"), dict) else {}
    return {
        "source": "code",
        "repository_full_name": repository.get("full_name") or "",
        "repository_url": repository.get("html_url") or "",
        "owner_login": owner.get("login"),
        "path": item.get("path") or item.get("name") or "",
        "url": item.get("html_url") or "",
        "fragment": _github_text_fragment(item),
    }


def _parse_github_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _recent_repo_count(repositories: list[dict[str, Any]], *, days: int = 180) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for repo in repositories:
        updated = _parse_github_datetime(repo.get("pushed_at") or repo.get("updated_at"))
        if updated and (now - updated).days <= days:
            count += 1
    return count


def _github_candidate_score(
    *,
    query_tokens: list[str],
    profile: dict[str, Any],
    repositories: list[dict[str, Any]],
    code_hits: list[dict[str, Any]],
) -> tuple[int, list[str], dict[str, Any]]:
    haystack = " ".join(
        [
            str(profile.get("login") or ""),
            str(profile.get("name") or ""),
            str(profile.get("company") or ""),
            str(profile.get("bio") or ""),
            " ".join(str(repo.get("full_name") or "") for repo in repositories),
            " ".join(str(repo.get("description") or "") for repo in repositories),
            " ".join(" ".join(str(topic) for topic in repo.get("topics") or []) for repo in repositories),
            " ".join(str(hit.get("fragment") or "") for hit in code_hits),
        ]
    ).casefold()
    matched_keywords = [token for token in query_tokens if token in haystack]
    stars = sum(_safe_int(repo.get("stars")) for repo in repositories)
    forks = sum(_safe_int(repo.get("forks")) for repo in repositories)
    recent_count = _recent_repo_count(repositories)
    code_hit_count = len(code_hits)
    public_repos = _safe_int(profile.get("public_repos"))
    followers = _safe_int(profile.get("followers"))

    score = 42
    score += min(24, len(matched_keywords) * 6)
    score += min(14, stars // 60)
    score += min(8, forks // 20)
    score += min(8, recent_count * 4)
    score += min(6, code_hit_count * 3)
    score += 4 if public_repos >= 5 else 0
    score += 4 if followers >= 25 else 0
    bounded = max(40, min(98, score))
    signals = {
        "matched_keyword_count": len(matched_keywords),
        "total_stars": stars,
        "total_forks": forks,
        "recent_repository_count": recent_count,
        "code_hit_count": code_hit_count,
        "public_repos": public_repos,
        "followers": followers,
    }
    return bounded, matched_keywords, signals


def _github_skills(matched_keywords: list[str], repositories: list[dict[str, Any]]) -> list[str]:
    values = list(matched_keywords)
    for repo in repositories:
        language = repo.get("language")
        if language:
            values.append(str(language))
        values.extend(str(topic) for topic in repo.get("topics") or [])
    return _unique_ordered(values)[:18]


def _merge_github_repositories(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for repo in repositories:
        key = _github_repository_key(repo)
        if not any(key):
            continue
        existing = merged.get(key)
        if existing is None or _safe_int(repo.get("stars")) > _safe_int(existing.get("stars")):
            merged[key] = repo
    return sorted(
        merged.values(),
        key=lambda item: (
            -_safe_int(item.get("stars")),
            str(item.get("pushed_at") or item.get("updated_at") or ""),
            str(item.get("full_name") or ""),
        ),
    )


class GitHubUserSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.github.com/search/users",
        user_endpoint_template: str = "https://api.github.com/users/{login}",
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.user_endpoint_template = user_endpoint_template
        self._client = _GitHubAPIClient(token_env=token_env, timeout_seconds=timeout_seconds)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = _github_limit(limit)
        payload = self._client.get_json(
            self.endpoint,
            params={
                "q": query,
                "per_page": normalized_limit,
                "page": 1,
                "sort": "followers",
                "order": "desc",
            },
            error_context="GitHub user search",
        )
        items = (payload.get("items") or [])[:normalized_limit]
        results = []
        for rank, item in enumerate(items, start=1):
            login = item.get("login")
            profile = self._fetch_user(str(login)) if login else {}
            results.append(self._to_result(query=query, rank=rank, item=item, profile=profile))
        return results

    def _fetch_user(self, login: str) -> dict[str, Any]:
        endpoint = self.user_endpoint_template.format(login=quote_plus(login))
        return self._client.get_json(endpoint, error_context=f"GitHub user profile {login}")

    def _to_result(self, query: str, rank: int, item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        login = str(profile.get("login") or item.get("login") or "")
        html_url = profile.get("html_url") or item.get("html_url") or _github_profile_url(login)
        query_tokens = _github_query_tokens(query)
        score, matched_keywords, signals = _github_candidate_score(
            query_tokens=query_tokens,
            profile=profile or {"login": login},
            repositories=[],
            code_hits=[],
        )
        bio = str(profile.get("bio") or "")
        evidence = [
            f"GitHub profile {login}: public repos={_safe_int(profile.get('public_repos'))}, followers={_safe_int(profile.get('followers'))}.",
        ]
        if bio:
            evidence.append(bio)
        return {
            "source_key": "github_users",
            "name_zh": "GitHub 用户搜索",
            "source_type": "developer_profile",
            "source_platform": "github_users",
            "query": query,
            "rank": rank,
            "title": profile.get("name") or login,
            "url": html_url,
            "source_url": html_url,
            "github_url": html_url,
            "name": profile.get("name") or login,
            "current_company": profile.get("company"),
            "location": profile.get("location"),
            "email": profile.get("email"),
            "homepage_url": profile.get("blog"),
            "snippet": bio,
            "evidence": evidence,
            "skills": matched_keywords,
            "matched_keywords": matched_keywords,
            "confidence": round(score / 100, 2),
            "github_score": score,
            "scoring_signals": signals,
            "followers": _safe_int(profile.get("followers")),
            "public_repos": _safe_int(profile.get("public_repos")),
            "updated_at": profile.get("updated_at"),
            "rate_limit": dict(self._client.last_rate_limit),
        }


class GitHubRepositorySearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.github.com/search/repositories",
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.token_env = token_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token_env:
            token = os.environ.get(self.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "q": query,
                "per_page": normalized_limit,
                "page": 1,
                "sort": "stars",
                "order": "desc",
            },
            headers=headers,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"GitHub repository search failed: {response.status_code} {response.text[:300]}") from exc

        items = (response.json().get("items") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        owner = item.get("owner") or {}
        topics = item.get("topics") or []
        return {
            "source_key": "github_repositories",
            "name_zh": "GitHub 代码仓库",
            "source_type": "code_repository",
            "query": query,
            "rank": rank,
            "title": item.get("full_name") or item.get("name", ""),
            "url": item.get("html_url", ""),
            "snippet": item.get("description", "") or "",
            "published_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "pushed_at": item.get("pushed_at"),
            "owner_login": owner.get("login"),
            "owner_type": owner.get("type"),
            "language": item.get("language"),
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "open_issues": item.get("open_issues_count"),
            "license": (item.get("license") or {}).get("spdx_id"),
            "topics": topics[:12],
        }


class GitHubCodeSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.github.com/search/code",
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self._client = _GitHubAPIClient(token_env=token_env, timeout_seconds=timeout_seconds)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = _github_limit(limit)
        payload = self._client.get_json(
            self.endpoint,
            params={"q": query, "per_page": normalized_limit, "page": 1},
            accept="application/vnd.github.text-match+json",
            error_context="GitHub code search",
        )
        items = (payload.get("items") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    def _to_result(self, query: str, rank: int, item: dict[str, Any]) -> dict[str, Any]:
        hit = _github_code_hit_summary(item)
        owner_login = hit.get("owner_login")
        github_url = _github_profile_url(str(owner_login)) if owner_login else None
        title = f"{hit.get('repository_full_name')}:{hit.get('path')}"
        matched_keywords = [
            token
            for token in _github_query_tokens(query)
            if token in " ".join([str(hit.get("fragment") or ""), title]).casefold()
        ]
        return {
            "source_key": "github_code",
            "name_zh": "GitHub 代码搜索",
            "source_type": "code_search",
            "source_platform": "github_code",
            "query": query,
            "rank": rank,
            "title": title,
            "url": hit.get("url"),
            "source_url": hit.get("url"),
            "github_url": github_url,
            "owner_login": owner_login,
            "repository_full_name": hit.get("repository_full_name"),
            "repository_url": hit.get("repository_url"),
            "path": hit.get("path"),
            "snippet": hit.get("fragment"),
            "evidence": [f"Code match in {title}: {hit.get('fragment')}".strip()],
            "skills": matched_keywords,
            "matched_keywords": matched_keywords,
            "confidence": max(0.58, min(0.86, round(0.76 - (rank - 1) * 0.04, 2))),
            "rate_limit": dict(self._client.last_rate_limit),
        }


class GitHubTopicSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.github.com/search/topics",
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self._client = _GitHubAPIClient(token_env=token_env, timeout_seconds=timeout_seconds)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = _github_limit(limit)
        payload = self._client.get_json(
            self.endpoint,
            params={"q": query, "per_page": normalized_limit, "page": 1},
            error_context="GitHub topic search",
        )
        items = (payload.get("items") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    def _to_result(self, query: str, rank: int, item: dict[str, Any]) -> dict[str, Any]:
        name = str(item.get("name") or "")
        title = item.get("display_name") or name
        url = item.get("html_url") or (f"https://github.com/topics/{name}" if name else "")
        snippet = item.get("short_description") or item.get("description") or ""
        return {
            "source_key": "github_topics",
            "name_zh": "GitHub Topic 搜索",
            "source_type": "code_topic",
            "query": query,
            "rank": rank,
            "title": title,
            "url": url,
            "snippet": snippet,
            "topic": name,
            "created_by": item.get("created_by"),
            "featured": item.get("featured"),
            "curated": item.get("curated"),
            "confidence": max(0.5, min(0.8, round(0.72 - (rank - 1) * 0.03, 2))),
            "rate_limit": dict(self._client.last_rate_limit),
        }


class GitHubCandidateSearchProvider:
    def __init__(
        self,
        users_endpoint: str = "https://api.github.com/search/users",
        repositories_endpoint: str = "https://api.github.com/search/repositories",
        code_endpoint: str = "https://api.github.com/search/code",
        user_endpoint_template: str = "https://api.github.com/users/{login}",
        user_repos_endpoint_template: str = "https://api.github.com/users/{login}/repos",
        rate_limit_endpoint: str = "https://api.github.com/rate_limit",
        token_env: str | None = "GITHUB_TOKEN",
        timeout_seconds: int = 20,
        enrichment_repo_limit: int = 8,
    ) -> None:
        self.users_endpoint = users_endpoint
        self.repositories_endpoint = repositories_endpoint
        self.code_endpoint = code_endpoint
        self.user_endpoint_template = user_endpoint_template
        self.user_repos_endpoint_template = user_repos_endpoint_template
        self.rate_limit_endpoint = rate_limit_endpoint
        self.enrichment_repo_limit = max(1, min(int(enrichment_repo_limit), 30))
        self._client = _GitHubAPIClient(token_env=token_env, timeout_seconds=timeout_seconds)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = _github_limit(limit, max_limit=20)
        candidates: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        def ensure_candidate(login: str | None) -> dict[str, Any] | None:
            if not login:
                return None
            normalized = str(login).strip()
            if not normalized:
                return None
            key = normalized.casefold()
            if key not in candidates:
                candidates[key] = {
                    "login": normalized,
                    "user_item": {},
                    "repositories": [],
                    "code_hits": [],
                    "source_hits": [],
                }
                order.append(key)
            return candidates[key]

        for item in self._search_users(query, normalized_limit):
            candidate = ensure_candidate(item.get("login"))
            if candidate is None:
                continue
            candidate["user_item"] = item
            candidate["source_hits"].append({"source": "user", "url": item.get("html_url")})

        for item in self._search_repositories(query, normalized_limit):
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            candidate = ensure_candidate(owner.get("login"))
            if candidate is None:
                continue
            repo_summary = _github_repository_summary(item)
            candidate["repositories"].append(repo_summary)
            candidate["source_hits"].append(
                {
                    "source": "repository",
                    "url": repo_summary.get("url"),
                    "title": repo_summary.get("full_name"),
                    "snippet": repo_summary.get("description"),
                }
            )

        for item in self._search_code(query, normalized_limit):
            hit = _github_code_hit_summary(item)
            candidate = ensure_candidate(hit.get("owner_login"))
            if candidate is None:
                continue
            candidate["code_hits"].append(hit)
            candidate["source_hits"].append(
                {
                    "source": "code",
                    "url": hit.get("url"),
                    "title": f"{hit.get('repository_full_name')}:{hit.get('path')}",
                    "snippet": hit.get("fragment"),
                }
            )

        results = []
        query_tokens = _github_query_tokens(query)
        for key in order:
            candidate = candidates[key]
            login = str(candidate["login"])
            profile = self._fetch_user(login)
            repos = [
                *candidate["repositories"],
                *[_github_repository_summary(repo) for repo in self._fetch_user_repos(login)],
            ]
            merged_repos = _merge_github_repositories(repos)
            result = self._to_candidate_result(
                query=query,
                query_tokens=query_tokens,
                profile=profile or candidate.get("user_item") or {"login": login},
                repositories=merged_repos,
                code_hits=candidate["code_hits"],
                source_hits=candidate["source_hits"],
            )
            results.append(result)

        return sorted(results, key=lambda item: (-int(item.get("github_score") or 0), str(item.get("github_url") or "")))[:normalized_limit]

    def rate_limit_status(self) -> dict[str, Any]:
        return self._client.get_json(self.rate_limit_endpoint, error_context="GitHub rate limit status")

    def _search_users(self, query: str, limit: int) -> list[dict[str, Any]]:
        payload = self._client.get_json(
            self.users_endpoint,
            params={"q": query, "per_page": limit, "page": 1, "sort": "followers", "order": "desc"},
            error_context="GitHub candidate user search",
        )
        return list((payload.get("items") or [])[:limit])

    def _search_repositories(self, query: str, limit: int) -> list[dict[str, Any]]:
        payload = self._client.get_json(
            self.repositories_endpoint,
            params={"q": query, "per_page": limit, "page": 1, "sort": "stars", "order": "desc"},
            error_context="GitHub candidate repository search",
        )
        return list((payload.get("items") or [])[:limit])

    def _search_code(self, query: str, limit: int) -> list[dict[str, Any]]:
        payload = self._client.get_json(
            self.code_endpoint,
            params={"q": query, "per_page": limit, "page": 1},
            accept="application/vnd.github.text-match+json",
            error_context="GitHub candidate code search",
        )
        return list((payload.get("items") or [])[:limit])

    def _fetch_user(self, login: str) -> dict[str, Any]:
        endpoint = self.user_endpoint_template.format(login=quote_plus(login))
        return self._client.get_json(endpoint, error_context=f"GitHub candidate profile {login}")

    def _fetch_user_repos(self, login: str) -> list[dict[str, Any]]:
        endpoint = self.user_repos_endpoint_template.format(login=quote_plus(login))
        payload = self._client.get_json(
            endpoint,
            params={"per_page": self.enrichment_repo_limit, "sort": "updated", "direction": "desc"},
            error_context=f"GitHub candidate repositories {login}",
        )
        return payload if isinstance(payload, list) else []

    def _to_candidate_result(
        self,
        *,
        query: str,
        query_tokens: list[str],
        profile: dict[str, Any],
        repositories: list[dict[str, Any]],
        code_hits: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        login = str(profile.get("login") or "")
        github_url = profile.get("html_url") or _github_profile_url(login)
        score, matched_keywords, signals = _github_candidate_score(
            query_tokens=query_tokens,
            profile=profile,
            repositories=repositories,
            code_hits=code_hits,
        )
        representative_repositories = repositories[:5]
        repository_evidence = [
            {
                "source": hit.get("source") or "repository",
                "title": hit.get("title"),
                "url": hit.get("url"),
                "snippet": hit.get("snippet"),
            }
            for hit in source_hits
            if hit.get("source") in {"repository", "code"} and (hit.get("url") or hit.get("snippet"))
        ][:8]
        for repo in representative_repositories:
            repository_evidence.append(
                {
                    "source": "repository",
                    "title": repo.get("full_name"),
                    "url": repo.get("url"),
                    "snippet": repo.get("description"),
                }
            )
        evidence = [
            f"GitHub profile {login}: score={score}, public repos={_safe_int(profile.get('public_repos'))}, followers={_safe_int(profile.get('followers'))}.",
        ]
        bio = str(profile.get("bio") or "").strip()
        if bio:
            evidence.append(bio)
        for repo in representative_repositories[:3]:
            repo_line = (
                f"{repo.get('full_name')} ({repo.get('language') or 'unknown'}): "
                f"{_safe_int(repo.get('stars'))} stars, {_safe_int(repo.get('forks'))} forks. "
                f"{repo.get('description') or ''}"
            ).strip()
            evidence.append(repo_line)
        for hit in code_hits[:2]:
            evidence.append(f"Code evidence {hit.get('repository_full_name')}:{hit.get('path')} - {hit.get('fragment')}")

        return {
            "source_key": "github_candidates",
            "name_zh": "GitHub 候选人搜索",
            "source_type": "developer_profile",
            "source_platform": "github_candidates",
            "query": query,
            "title": profile.get("name") or login,
            "url": github_url,
            "source_url": github_url,
            "github_url": github_url,
            "name": profile.get("name") or login,
            "current_company": profile.get("company"),
            "location": profile.get("location"),
            "email": profile.get("email"),
            "homepage_url": profile.get("blog"),
            "snippet": bio or (repository_evidence[0].get("snippet") if repository_evidence else ""),
            "published_at": profile.get("created_at"),
            "updated_at": profile.get("updated_at"),
            "evidence": _unique_ordered([str(item) for item in evidence if item])[:10],
            "skills": _github_skills(matched_keywords, representative_repositories),
            "matched_keywords": matched_keywords,
            "confidence": round(score / 100, 2),
            "github_score": score,
            "scoring_signals": signals,
            "representative_repositories": representative_repositories,
            "repository_evidence": repository_evidence[:10],
            "recent_activity": {
                "recent_repository_count": signals["recent_repository_count"],
                "latest_repository_pushed_at": next(
                    (repo.get("pushed_at") for repo in representative_repositories if repo.get("pushed_at")),
                    None,
                ),
            },
            "followers": _safe_int(profile.get("followers")),
            "public_repos": _safe_int(profile.get("public_repos")),
            "rate_limit": dict(self._client.last_rate_limit),
            "raw_payload": {
                "profile": {
                    "login": login,
                    "html_url": github_url,
                    "company": profile.get("company"),
                    "location": profile.get("location"),
                    "public_repos": profile.get("public_repos"),
                    "followers": profile.get("followers"),
                },
                "representative_repositories": representative_repositories,
                "repository_evidence": repository_evidence[:10],
                "scoring_signals": signals,
            },
        }


class HuggingFaceModelSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://huggingface.co/api/models",
        token_env: str | None = "HF_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.token_env = token_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        headers = {"Accept": "application/json"}
        if self.token_env:
            token = os.environ.get(self.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search": query,
                "limit": normalized_limit,
                "sort": "downloads",
                "direction": -1,
                "full": "true",
            },
            headers=headers,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Hugging Face model search failed: {response.status_code} {response.text[:300]}") from exc

        models = response.json() or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(models[:normalized_limit], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        model_id = item.get("modelId") or item.get("id") or ""
        tags = item.get("tags") or []
        return {
            "source_key": "huggingface_models",
            "name_zh": "Hugging Face 模型库",
            "source_type": "model_repository",
            "query": query,
            "rank": rank,
            "title": model_id,
            "url": f"https://huggingface.co/{model_id}" if model_id else "",
            "snippet": item.get("pipeline_tag") or "",
            "published_at": item.get("createdAt"),
            "last_modified": item.get("lastModified"),
            "author": item.get("author"),
            "downloads": item.get("downloads"),
            "likes": item.get("likes"),
            "pipeline_tag": item.get("pipeline_tag"),
            "library_name": item.get("library_name"),
            "tags": tags[:16],
        }


class PeopleDataLabsPeopleSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.peopledatalabs.com/v5/person/search",
        api_key_env: str = "PDL_API_KEY",
        dataset: str = "all",
        data_include: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.dataset = dataset
        self.data_include = data_include
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 100))
        params: dict[str, Any] = {
            "query": json.dumps(
                {
                    "query": {
                        "simple_query_string": {
                            "query": query,
                            "fields": [
                                "full_name",
                                "job_title",
                                "job_company_name",
                                "experience.company.name",
                                "education.school.name",
                                "skills",
                                "profiles.url",
                            ],
                            "default_operator": "and",
                        }
                    }
                }
            ),
            "size": normalized_limit,
            "dataset": self.dataset,
            "titlecase": "true",
        }
        if self.data_include:
            params["data_include"] = self.data_include

        import requests

        response = requests.get(
            self.endpoint,
            headers={"Content-Type": "application/json", "X-api-key": api_key},
            params=params,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"People Data Labs people search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        if int(payload.get("status", 200)) >= 400:
            raise RuntimeError(f"People Data Labs people search failed: {payload}")
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate((payload.get("data") or [])[:normalized_limit], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        full_name = str(item.get("full_name") or item.get("name") or "")
        job_title = item.get("job_title") or item.get("title")
        company = item.get("job_company_name") or item.get("company")
        linkedin_url = item.get("linkedin_url") or item.get("linkedin_profile_url")
        github_url = item.get("github_url")
        twitter_url = item.get("twitter_url")
        profiles = item.get("profiles") or []
        social_links = {
            "linkedin": linkedin_url,
            "github": github_url,
            "x": twitter_url,
        }
        if isinstance(profiles, list):
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                network = str(profile.get("network") or profile.get("type") or "").casefold()
                url = profile.get("url")
                if not url:
                    continue
                if "linkedin" in network and not social_links.get("linkedin"):
                    social_links["linkedin"] = url
                elif "github" in network and not social_links.get("github"):
                    social_links["github"] = url
                elif ("twitter" in network or network == "x") and not social_links.get("x"):
                    social_links["x"] = url
        social_links = {key: value for key, value in social_links.items() if value}

        emails = PeopleDataLabsPeopleSearchProvider._contact_values(item.get("emails"))
        phones = PeopleDataLabsPeopleSearchProvider._contact_values(item.get("phone_numbers") or item.get("phones"))
        snippet_parts = [part for part in (job_title, company, item.get("location_name") or item.get("location")) if part]
        return {
            "source_key": "pdl_people_search",
            "name_zh": "People Data Labs 人员补全",
            "source_type": "identity_enrichment",
            "query": query,
            "rank": rank,
            "title": full_name,
            "url": social_links.get("linkedin") or social_links.get("github") or "",
            "snippet": " · ".join(str(part) for part in snippet_parts),
            "published_at": item.get("last_updated") or item.get("updated_at"),
            "pdl_id": item.get("id"),
            "job_title": job_title,
            "company": company,
            "location": item.get("location_name") or item.get("location"),
            "social_links": social_links,
            "public_contacts": {
                "emails": emails[:5],
                "phones": phones[:3],
            },
            "experience": item.get("experience") or [],
            "education": item.get("education") or [],
            "skills": (item.get("skills") or [])[:16] if isinstance(item.get("skills"), list) else [],
        }

    @staticmethod
    def _contact_values(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        values = []
        for item in raw:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                value = item.get("address") or item.get("email") or item.get("number")
                if value:
                    values.append(str(value))
        return values


class XRecentPostsSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.x.com/2/tweets/search/recent",
        bearer_token_env: str = "X_BEARER_TOKEN",
        sort_order: str = "recency",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.bearer_token_env = bearer_token_env
        self.sort_order = sort_order
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        bearer_token = os.environ.get(self.bearer_token_env)
        if not bearer_token:
            raise RuntimeError(f"Missing required environment variable: {self.bearer_token_env}")

        request_limit = max(10, min(int(limit), 100))
        import requests

        response = requests.get(
            self.endpoint,
            params={
                "query": query,
                "max_results": request_limit,
                "sort_order": self.sort_order,
                "tweet.fields": "author_id,created_at,public_metrics,entities,lang,conversation_id,referenced_tweets",
                "user.fields": "id,username,name,description,public_metrics,verified,verified_type,url",
                "expansions": "author_id",
            },
            headers={"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"X recent posts search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        users = {
            str(user.get("id")): user
            for user in ((payload.get("includes") or {}).get("users") or [])
            if isinstance(user, dict)
        }
        return [
            self._to_result(query=query, rank=rank, post=post, author=users.get(str(post.get("author_id")), {}))
            for rank, post in enumerate((payload.get("data") or [])[: max(1, int(limit))], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, post: dict[str, Any], author: dict[str, Any]) -> dict:
        post_id = str(post.get("id") or "")
        username = str(author.get("username") or "")
        if username and post_id:
            url = f"https://x.com/{username}/status/{post_id}"
        elif post_id:
            url = f"https://x.com/i/web/status/{post_id}"
        else:
            url = ""
        metrics = post.get("public_metrics") or {}
        author_metrics = author.get("public_metrics") or {}
        return {
            "source_key": "x_recent_posts_search",
            "name_zh": "X recent posts 搜索",
            "source_type": "social_platform_search",
            "query": query,
            "rank": rank,
            "title": (post.get("text") or "")[:100],
            "url": url,
            "snippet": post.get("text") or "",
            "published_at": post.get("created_at"),
            "post_id": post_id,
            "author_id": post.get("author_id"),
            "author_username": username or None,
            "author_name": author.get("name"),
            "author_followers": author_metrics.get("followers_count"),
            "lang": post.get("lang"),
            "public_metrics": metrics,
        }


class CrustdataSignalSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.crustdata.com/web/search/live",
        api_key_env: str = "CRUSTDATA_API_KEY",
        api_version: str = "2025-11-01",
        sources: list[str] | None = None,
        location: str = "US",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.api_version = api_version
        self.sources = sources or ["web", "news", "social"]
        self.location = location
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 20))
        import requests

        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "x-api-version": self.api_version,
            },
            json={
                "query": query,
                "sources": self.sources,
                "location": self.location,
                "limit": normalized_limit,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Crustdata signal search failed: {response.status_code} {response.text[:300]}") from exc

        results = response.json().get("results") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(results[:normalized_limit], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        return {
            "source_key": "crustdata_signal_search",
            "name_zh": "Crustdata 实时信号",
            "source_type": "market_signal",
            "query": query,
            "rank": item.get("position") or rank,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "published_at": item.get("published_at") or item.get("date"),
            "signal_source": item.get("source"),
            "raw": item,
        }


class CompaniesHouseCompanySearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.company-information.service.gov.uk/search/companies",
        api_key_env: str = "COMPANIES_HOUSE_API_KEY",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "q": query,
                "items_per_page": normalized_limit,
                "start_index": 0,
            },
            auth=(api_key, ""),
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Companies House search failed: {response.status_code} {response.text[:300]}") from exc

        items = (response.json().get("items") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        company_number = str(item.get("company_number") or "")
        address = item.get("address") or {}
        address_parts = [
            address.get("premises"),
            address.get("address_line_1"),
            address.get("locality"),
            address.get("region"),
            address.get("postal_code"),
            address.get("country"),
        ]
        return {
            "source_key": "companies_house_search",
            "name_zh": "Companies House 公司注册",
            "source_type": "company_registry",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": f"https://find-and-update.company-information.service.gov.uk/company/{company_number}" if company_number else "",
            "snippet": item.get("description", "") or item.get("company_status", "") or "",
            "published_at": item.get("date_of_creation"),
            "company_number": company_number,
            "company_status": item.get("company_status"),
            "company_type": item.get("company_type"),
            "date_of_creation": item.get("date_of_creation"),
            "address_snippet": item.get("address_snippet") or ", ".join(str(part) for part in address_parts if part),
            "matches": item.get("matches", {}),
        }


class CourtListenerSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://www.courtlistener.com/api/rest/v4/search/",
        token_env: str | None = "COURTLISTENER_TOKEN",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.token_env = token_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        headers = {"Accept": "application/json"}
        if self.token_env:
            token = os.environ.get(self.token_env)
            if token:
                headers["Authorization"] = f"Token {token}"

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "q": query,
                "type": "o",
                "page_size": normalized_limit,
            },
            headers=headers,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"CourtListener search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        results = payload.get("results") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(results[:normalized_limit], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        absolute_url = item.get("absolute_url") or item.get("cluster", "")
        url = absolute_url
        if isinstance(absolute_url, str) and absolute_url.startswith("/"):
            url = f"https://www.courtlistener.com{absolute_url}"
        return {
            "source_key": "courtlistener_search",
            "name_zh": "CourtListener 司法检索",
            "source_type": "litigation",
            "query": query,
            "rank": rank,
            "title": item.get("caseName") or item.get("caseNameFull") or item.get("caption", ""),
            "url": url or "",
            "snippet": item.get("snippet") or item.get("suitNature") or "",
            "published_at": item.get("dateFiled") or item.get("dateArgued") or item.get("dateReargued"),
            "court": item.get("court"),
            "court_id": item.get("court_id"),
            "docket_number": item.get("docketNumber"),
            "citation": item.get("citation"),
            "status": item.get("status"),
            "judge": item.get("judge"),
        }


class OpenAlexWorksSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.openalex.org/works",
        mailto: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.mailto = mailto
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 25))
        params = {
            "search": query,
            "per-page": normalized_limit,
            "sort": "relevance_score:desc",
        }
        if self.mailto:
            params["mailto"] = self.mailto

        import requests

        response = requests.get(
            self.endpoint,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OpenAlex request failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(response.json().get("results") or [], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        primary_location = item.get("primary_location") or {}
        landing_page_url = primary_location.get("landing_page_url")
        doi = item.get("doi")
        authorships = item.get("authorships") or []
        authors = [
            str((authorship.get("author") or {}).get("display_name"))
            for authorship in authorships
            if (authorship.get("author") or {}).get("display_name")
        ]
        institutions = [
            str(institution.get("display_name"))
            for authorship in authorships
            for institution in authorship.get("institutions", [])
            if isinstance(institution, dict) and institution.get("display_name")
        ]
        concepts = [
            str(topic.get("display_name"))
            for topic in item.get("concepts") or item.get("topics") or []
            if topic.get("display_name")
        ]
        return {
            "source_key": "openalex_works_search",
            "name_zh": "OpenAlex 学术作品",
            "source_type": "academic",
            "query": query,
            "rank": rank,
            "title": item.get("display_name", ""),
            "url": landing_page_url or doi or item.get("id", ""),
            "openalex_id": item.get("id"),
            "doi": doi,
            "snippet": item.get("abstract", "") or "",
            "published_at": item.get("publication_date") or item.get("publication_year"),
            "publication_year": item.get("publication_year"),
            "cited_by_count": item.get("cited_by_count"),
            "authors": authors[:8],
            "institutions": institutions[:8],
            "concepts": concepts[:8],
        }


class OpenAlexAuthorsSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.openalex.org/authors",
        mailto: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.mailto = mailto
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 25))
        params = {
            "search": query,
            "per-page": normalized_limit,
            "sort": "cited_by_count:desc",
        }
        if self.mailto:
            params["mailto"] = self.mailto

        import requests

        response = requests.get(
            self.endpoint,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OpenAlex authors request failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(response.json().get("results") or [], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        institutions = [
            str(institution.get("display_name"))
            for institution in item.get("last_known_institutions") or []
            if isinstance(institution, dict) and institution.get("display_name")
        ]
        topics = [
            str(topic.get("display_name"))
            for topic in item.get("topics") or []
            if isinstance(topic, dict) and topic.get("display_name")
        ]
        title = item.get("display_name", "")
        snippet_parts = []
        if institutions:
            snippet_parts.append(f"机构: {', '.join(institutions[:3])}")
        if topics:
            snippet_parts.append(f"方向: {', '.join(topics[:5])}")
        return {
            "source_key": "openalex_authors_search",
            "name_zh": "OpenAlex 作者搜索",
            "source_type": "academic_author",
            "query": query,
            "rank": rank,
            "title": title,
            "url": item.get("id", ""),
            "openalex_id": item.get("id"),
            "snippet": "；".join(snippet_parts),
            "published_at": None,
            "works_count": item.get("works_count"),
            "cited_by_count": item.get("cited_by_count"),
            "institutions": institutions[:8],
            "topics": topics[:8],
        }


class OpenAlexInstitutionsSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.openalex.org/institutions",
        mailto: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.mailto = mailto
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 25))
        params = {
            "search": query,
            "per-page": normalized_limit,
            "sort": "works_count:desc",
        }
        if self.mailto:
            params["mailto"] = self.mailto

        import requests

        response = requests.get(
            self.endpoint,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OpenAlex institutions request failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(response.json().get("results") or [], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        title = item.get("display_name", "")
        url = item.get("homepage_url") or item.get("id", "")
        country_code = item.get("country_code")
        return {
            "source_key": "openalex_institutions_search",
            "name_zh": "OpenAlex 机构搜索",
            "source_type": "academic_institution",
            "query": query,
            "rank": rank,
            "title": title,
            "url": url,
            "openalex_id": item.get("id"),
            "snippet": f"{country_code or ''} works={item.get('works_count') or 0} cited_by={item.get('cited_by_count') or 0}".strip(),
            "published_at": None,
            "country_code": country_code,
            "works_count": item.get("works_count"),
            "cited_by_count": item.get("cited_by_count"),
        }


class SemanticScholarPaperSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.semanticscholar.org/graph/v1/paper/search",
        fields: str = "title,year,authors,url,abstract,citationCount,venue,publicationTypes,externalIds,openAccessPdf",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.fields = fields
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "query": query,
                "limit": normalized_limit,
                "fields": self.fields,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Semantic Scholar paper search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(response.json().get("data") or [], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        authors = [
            str(author.get("name"))
            for author in item.get("authors") or []
            if isinstance(author, dict) and author.get("name")
        ]
        return {
            "source_key": "semantic_scholar_papers_search",
            "name_zh": "Semantic Scholar 论文搜索",
            "source_type": "academic",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("url") or (
                f"https://www.semanticscholar.org/paper/{item.get('paperId')}" if item.get("paperId") else ""
            ),
            "semantic_scholar_id": item.get("paperId"),
            "snippet": item.get("abstract") or "",
            "published_at": item.get("year"),
            "publication_year": item.get("year"),
            "venue": item.get("venue"),
            "cited_by_count": item.get("citationCount"),
            "authors": authors[:8],
        }


class SemanticScholarAuthorSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.semanticscholar.org/graph/v1/author/search",
        fields: str = "name,url,paperCount,citationCount,hIndex,aliases,affiliations",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.fields = fields
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "query": query,
                "limit": normalized_limit,
                "fields": self.fields,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Semantic Scholar author search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(response.json().get("data") or [], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        author_id = item.get("authorId")
        affiliations = item.get("affiliations") or []
        return {
            "source_key": "semantic_scholar_authors_search",
            "name_zh": "Semantic Scholar 作者搜索",
            "source_type": "academic_author",
            "query": query,
            "rank": rank,
            "title": item.get("name", ""),
            "url": item.get("url") or (f"https://www.semanticscholar.org/author/{author_id}" if author_id else ""),
            "semantic_scholar_id": author_id,
            "snippet": ", ".join(str(affiliation) for affiliation in affiliations),
            "published_at": None,
            "paper_count": item.get("paperCount"),
            "citation_count": item.get("citationCount"),
            "h_index": item.get("hIndex"),
            "aliases": item.get("aliases") or [],
            "affiliations": affiliations,
        }


class EducationCompetitionMonitorProvider:
    def __init__(self, targets: list[dict[str, Any]] | None = None) -> None:
        self.targets = targets or []

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, int(limit))
        scored = [
            (self._score_target(query, target), index, target)
            for index, target in enumerate(self.targets)
        ]
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        return [
            self._to_result(query=query, rank=rank, score=score, target=target)
            for rank, (score, _, target) in enumerate(ranked[:normalized_limit], start=1)
        ]

    @staticmethod
    def _score_target(query: str, target: dict[str, Any]) -> int:
        tokens = SearchSourceCatalogProvider._tokens(query.casefold())
        haystack = " ".join(
            [
                str(target.get("name", "")),
                str(target.get("category", "")),
                str(target.get("url", "")),
                str(target.get("purpose", "")),
                " ".join(str(item) for item in target.get("keywords", [])),
            ]
        ).casefold()
        return sum(1 for token in tokens if token and token in haystack)

    @staticmethod
    def _to_result(query: str, rank: int, score: int, target: dict[str, Any]) -> dict[str, Any]:
        category = str(target.get("category") or "public_web")
        return {
            "source_key": "education_competition_monitor",
            "name_zh": "学校/竞赛监控",
            "source_type": category,
            "query": query,
            "rank": rank,
            "title": str(target.get("name") or target.get("url") or ""),
            "url": str(target.get("url") or ""),
            "snippet": str(target.get("purpose") or ""),
            "published_at": None,
            "retrieval_status": "monitor_target",
            "score": score,
            "keywords": target.get("keywords") or [],
            "next_actions": ["snapshot_recommended", "human_review", "evidence_archive"],
        }


class SECEdgarCompanyFilingsProvider:
    def __init__(
        self,
        company_tickers_url: str = "https://www.sec.gov/files/company_tickers.json",
        submissions_url_template: str = "https://data.sec.gov/submissions/CIK{cik}.json",
        archives_url_template: str = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_document}",
        user_agent: str = "zhaoping-agent/0.1 research contact@example.invalid",
        timeout_seconds: int = 20,
    ) -> None:
        self.company_tickers_url = company_tickers_url
        self.submissions_url_template = submissions_url_template
        self.archives_url_template = archives_url_template
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 40))
        company = self._match_company(query)
        if company is None:
            return []

        cik = str(company["cik_str"]).zfill(10)
        payload = self._get_json(self.submissions_url_template.format(cik=cik))
        recent = payload.get("filings", {}).get("recent", {})
        filings = self._recent_filings(recent, normalized_limit)
        return [
            self._to_result(
                query=query,
                rank=rank,
                cik=cik,
                ticker=str(company.get("ticker", "")),
                company_name=str(company.get("title", "")),
                filing=filing,
            )
            for rank, filing in enumerate(filings, start=1)
        ]

    def _match_company(self, query: str) -> dict[str, Any] | None:
        companies = self._get_json(self.company_tickers_url)
        return self._match_company_from_payload(query=query, companies=companies)

    @staticmethod
    def _match_company_from_payload(query: str, companies: Any) -> dict[str, Any] | None:
        query_tokens = {token.casefold() for token in SearchSourceCatalogProvider._tokens(query)}
        normalized_query = query.casefold()
        candidates = companies.values() if isinstance(companies, dict) else companies
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for company in candidates:
            ticker = str(company.get("ticker", "")).casefold()
            title = str(company.get("title", "")).casefold()
            score = 0
            if ticker and ticker in query_tokens:
                score += 10
            if ticker and ticker in normalized_query:
                score += 5
            if title and title in normalized_query:
                score += 8
            score += sum(1 for token in query_tokens if len(token) > 2 and token in title)
            if score > 0:
                scored.append((score, ticker, company))
        if not scored:
            return None
        return sorted(scored, key=lambda item: (-item[0], item[1]))[0][2]

    def _get_json(self, url: str) -> Any:
        import requests

        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SEC EDGAR request failed: {response.status_code} {response.text[:300]}") from exc
        return response.json()

    @staticmethod
    def _recent_filings(recent: dict[str, list[Any]], limit: int) -> list[dict[str, Any]]:
        forms = recent.get("form") or []
        filing_dates = recent.get("filingDate") or []
        report_dates = recent.get("reportDate") or []
        accession_numbers = recent.get("accessionNumber") or []
        primary_documents = recent.get("primaryDocument") or []
        descriptions = recent.get("primaryDocDescription") or []
        rows = []
        for index, form in enumerate(forms[:limit]):
            rows.append(
                {
                    "form": form,
                    "filing_date": filing_dates[index] if index < len(filing_dates) else None,
                    "report_date": report_dates[index] if index < len(report_dates) else None,
                    "accession_number": accession_numbers[index] if index < len(accession_numbers) else None,
                    "primary_document": primary_documents[index] if index < len(primary_documents) else None,
                    "description": descriptions[index] if index < len(descriptions) else None,
                }
            )
        return rows

    def _to_result(
        self,
        query: str,
        rank: int,
        cik: str,
        ticker: str,
        company_name: str,
        filing: dict[str, Any],
    ) -> dict:
        accession_number = str(filing.get("accession_number") or "")
        primary_document = str(filing.get("primary_document") or "")
        accession_no_dashes = accession_number.replace("-", "")
        url = ""
        if accession_no_dashes and primary_document:
            url = self.archives_url_template.format(
                cik=str(int(cik)),
                accession_no_dashes=accession_no_dashes,
                primary_document=primary_document,
            )
        form = str(filing.get("form") or "")
        return {
            "source_key": "sec_edgar_company_filings",
            "name_zh": "SEC EDGAR 公司披露",
            "source_type": "regulatory_filings",
            "query": query,
            "rank": rank,
            "title": f"{ticker} {form} {filing.get('filing_date')}".strip(),
            "url": url,
            "snippet": str(filing.get("description") or form),
            "published_at": filing.get("filing_date"),
            "report_date": filing.get("report_date"),
            "cik": cik,
            "ticker": ticker,
            "company_name": company_name,
            "form": form,
            "accession_number": accession_number,
            "primary_document": primary_document,
        }


class SECInsiderTransactionsProvider(SECEdgarCompanyFilingsProvider):
    ownership_forms = {"3", "3/A", "4", "4/A", "5", "5/A"}

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 40))
        company = self._match_company(query)
        if company is None:
            return []

        cik = str(company["cik_str"]).zfill(10)
        payload = self._get_json(self.submissions_url_template.format(cik=cik))
        recent = payload.get("filings", {}).get("recent", {})
        filings = [
            filing
            for filing in self._recent_filings(recent, limit=200)
            if str(filing.get("form") or "").upper() in self.ownership_forms
        ][:normalized_limit]
        return [
            self._to_result(
                query=query,
                rank=rank,
                cik=cik,
                ticker=str(company.get("ticker", "")),
                company_name=str(company.get("title", "")),
                filing=filing,
            )
            for rank, filing in enumerate(filings, start=1)
        ]

    def _to_result(
        self,
        query: str,
        rank: int,
        cik: str,
        ticker: str,
        company_name: str,
        filing: dict[str, Any],
    ) -> dict:
        result = super()._to_result(
            query=query,
            rank=rank,
            cik=cik,
            ticker=ticker,
            company_name=company_name,
            filing=filing,
        )
        form = str(filing.get("form") or "")
        result.update(
            {
                "source_key": "sec_insider_transactions",
                "name_zh": "SEC 内部人交易披露",
                "source_type": "insider_transactions",
                "title": f"{ticker} insider Form {form} {filing.get('filing_date')}".strip(),
                "snippet": str(filing.get("description") or f"SEC ownership disclosure Form {form}"),
                "ownership_form": form,
            }
        )
        return result


class SECOwnershipActivismProvider(SECEdgarCompanyFilingsProvider):
    ownership_forms = {
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
        "13F-HR",
        "13F-HR/A",
        "13F-NT",
        "13F-NT/A",
        "144",
        "144/A",
    }

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 40))
        company = self._match_company(query)
        if company is None:
            return []

        cik = str(company["cik_str"]).zfill(10)
        payload = self._get_json(self.submissions_url_template.format(cik=cik))
        recent = payload.get("filings", {}).get("recent", {})
        filings = [
            filing
            for filing in self._recent_filings(recent, limit=300)
            if str(filing.get("form") or "").upper() in self.ownership_forms
        ][:normalized_limit]
        return [
            self._to_result(
                query=query,
                rank=rank,
                cik=cik,
                ticker=str(company.get("ticker", "")),
                company_name=str(company.get("title", "")),
                filing=filing,
            )
            for rank, filing in enumerate(filings, start=1)
        ]

    def _to_result(
        self,
        query: str,
        rank: int,
        cik: str,
        ticker: str,
        company_name: str,
        filing: dict[str, Any],
    ) -> dict:
        result = super()._to_result(
            query=query,
            rank=rank,
            cik=cik,
            ticker=ticker,
            company_name=company_name,
            filing=filing,
        )
        form = str(filing.get("form") or "")
        result.update(
            {
                "source_key": "sec_ownership_activism",
                "name_zh": "SEC 重大持股与控制权披露",
                "source_type": "ownership_activism",
                "title": f"{ticker} ownership/control Form {form} {filing.get('filing_date')}".strip(),
                "snippet": str(filing.get("description") or f"SEC ownership/control disclosure Form {form}"),
                "ownership_form": form,
            }
        )
        return result


class SECCompanyFactsProvider:
    def __init__(
        self,
        company_tickers_url: str = "https://www.sec.gov/files/company_tickers.json",
        companyfacts_url_template: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        user_agent: str = "zhaoping-agent/0.1 research contact@example.invalid",
        timeout_seconds: int = 20,
    ) -> None:
        self.company_tickers_url = company_tickers_url
        self.companyfacts_url_template = companyfacts_url_template
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 40))
        company = self._match_company(query)
        if company is None:
            return []

        cik = str(company["cik_str"]).zfill(10)
        payload = self._get_json(self.companyfacts_url_template.format(cik=cik))
        facts = self._important_facts(payload, normalized_limit)
        return [
            self._to_result(
                query=query,
                rank=rank,
                cik=cik,
                ticker=str(company.get("ticker", "")),
                company_name=str(payload.get("entityName") or company.get("title", "")),
                fact=fact,
            )
            for rank, fact in enumerate(facts, start=1)
        ]

    def _match_company(self, query: str) -> dict[str, Any] | None:
        companies = self._get_json(self.company_tickers_url)
        return SECEdgarCompanyFilingsProvider._match_company_from_payload(query=query, companies=companies)

    def _get_json(self, url: str) -> Any:
        import requests

        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SEC Company Facts request failed: {response.status_code} {response.text[:300]}") from exc
        return response.json()

    @staticmethod
    def _important_facts(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        us_gaap = (payload.get("facts") or {}).get("us-gaap") or {}
        preferred_tags = [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "NetIncomeLoss",
            "Assets",
            "Liabilities",
            "CashAndCashEquivalentsAtCarryingValue",
            "OperatingIncomeLoss",
            "ResearchAndDevelopmentExpense",
            "EarningsPerShareDiluted",
        ]
        facts = []
        for tag in preferred_tags:
            concept = us_gaap.get(tag)
            if not concept:
                continue
            for unit, values in (concept.get("units") or {}).items():
                latest = SECCompanyFactsProvider._latest_fact(values)
                if latest:
                    facts.append(
                        {
                            "tag": tag,
                            "label": concept.get("label") or tag,
                            "description": concept.get("description"),
                            "unit": unit,
                            **latest,
                        }
                    )
                    break
            if len(facts) >= limit:
                break
        return facts[:limit]

    @staticmethod
    def _latest_fact(values: list[dict[str, Any]]) -> dict[str, Any] | None:
        clean = [value for value in values if value.get("val") is not None]
        if not clean:
            return None
        return sorted(
            clean,
            key=lambda value: (
                str(value.get("filed") or ""),
                str(value.get("end") or ""),
                str(value.get("fy") or ""),
                str(value.get("fp") or ""),
            ),
            reverse=True,
        )[0]

    @staticmethod
    def _to_result(
        query: str,
        rank: int,
        cik: str,
        ticker: str,
        company_name: str,
        fact: dict[str, Any],
    ) -> dict:
        tag = str(fact.get("tag") or "")
        return {
            "source_key": "sec_company_facts",
            "name_zh": "SEC Company Facts",
            "source_type": "financial_facts",
            "query": query,
            "rank": rank,
            "title": f"{ticker} {tag} {fact.get('fy', '')} {fact.get('fp', '')}".strip(),
            "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            "snippet": str(fact.get("label") or tag),
            "published_at": fact.get("filed"),
            "cik": cik,
            "ticker": ticker,
            "company_name": company_name,
            "tag": tag,
            "label": fact.get("label"),
            "description": fact.get("description"),
            "unit": fact.get("unit"),
            "value": fact.get("val"),
            "fiscal_year": fact.get("fy"),
            "fiscal_period": fact.get("fp"),
            "form": fact.get("form"),
            "end_date": fact.get("end"),
            "accession_number": fact.get("accn"),
        }


class SECInvestmentAdviserReportProvider:
    def __init__(
        self,
        report_url: str = "https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126.zip",
        landing_page_url: str = "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers",
        user_agent: str = "zhaoping-agent/0.1 research contact@example.invalid",
        timeout_seconds: int = 30,
    ) -> None:
        self.report_url = report_url
        self.landing_page_url = landing_page_url
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._rows_cache: list[dict[str, str]] | None = None

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        scored = [
            (self._score(query, row), row)
            for row in self._rows()
        ]
        ranked = sorted(
            ((score, row) for score, row in scored if score > 0),
            key=lambda item: (-item[0], self._field(item[1], "Primary Business Name", "Legal Name")),
        )
        return [
            self._to_result(query=query, rank=rank, score=score, row=row)
            for rank, (score, row) in enumerate(ranked[:normalized_limit], start=1)
        ]

    def _rows(self) -> list[dict[str, str]]:
        if self._rows_cache is not None:
            return self._rows_cache

        import requests

        response = requests.get(
            self.report_url,
            headers={
                "Accept": "application/zip,text/csv,*/*",
                "User-Agent": self.user_agent,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SEC investment adviser report download failed: {response.status_code} {response.text[:300]}") from exc

        raw = response.content
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise RuntimeError("SEC investment adviser report ZIP did not contain a CSV file.")
                text = archive.read(csv_names[0]).decode("utf-8-sig", errors="replace")
        else:
            text = raw.decode("utf-8-sig", errors="replace")

        self._rows_cache = [
            {str(key): str(value or "") for key, value in row.items()}
            for row in csv.DictReader(io.StringIO(text))
        ]
        return self._rows_cache

    @staticmethod
    def _score(query: str, row: dict[str, str]) -> int:
        clean_query = query.strip().casefold()
        tokens = SearchSourceCatalogProvider._tokens(clean_query)
        fields = [
            "Primary Business Name",
            "Legal Name",
            "Organization CRD#",
            "SEC#",
            "CIK#",
            "Main Office City",
            "Main Office State",
            "Website Address",
        ]
        haystack = " ".join(row.get(field, "") for field in fields).casefold()
        score = 0
        if clean_query and clean_query in haystack:
            score += 4
        for identifier in ("Organization CRD#", "SEC#", "CIK#"):
            if clean_query and clean_query == row.get(identifier, "").strip().casefold():
                score += 6
        for token in tokens:
            if token and token in haystack:
                score += 1
        return score

    @classmethod
    def _to_result(cls, query: str, rank: int, score: int, row: dict[str, str]) -> dict:
        crd = cls._field(row, "Organization CRD#")
        sec_number = cls._field(row, "SEC#")
        primary_name = cls._field(row, "Primary Business Name", "Legal Name")
        city = cls._field(row, "Main Office City")
        state = cls._field(row, "Main Office State")
        status = cls._field(row, "SEC Current Status")
        office = ", ".join(value for value in (city, state) if value)
        return {
            "source_key": "sec_investment_adviser_reports",
            "name_zh": "SEC 投顾/ERA Form ADV 数据",
            "source_type": "investment_adviser_registry",
            "query": query,
            "rank": rank,
            "score": score,
            "title": primary_name,
            "url": f"https://adviserinfo.sec.gov/firm/summary/{crd}" if crd else "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers",
            "snippet": f"{cls._field(row, 'Firm Type')} | {status} | {office}".strip(" |"),
            "published_at": cls._field(row, "Latest ADV Filing Date") or cls._field(row, "SEC Status Effective Date"),
            "crd_number": crd,
            "additional_crd_number": cls._field(row, "Additional CRD Number"),
            "sec_number": sec_number,
            "firm_type": cls._field(row, "Firm Type"),
            "cik": cls._field(row, "CIK#"),
            "primary_business_name": primary_name,
            "legal_name": cls._field(row, "Legal Name"),
            "sec_region": cls._field(row, "SEC Region"),
            "sec_current_status": status,
            "sec_status_effective_date": cls._field(row, "SEC Status Effective Date"),
            "latest_adv_filing_date": cls._field(row, "Latest ADV Filing Date"),
            "form_version": cls._field(row, "Form Version"),
            "main_office_street_1": cls._field(row, "Main Office Street Address 1"),
            "main_office_street_2": cls._field(row, "Main Office Street Address 2"),
            "main_office_city": city,
            "main_office_state": state,
            "main_office_country": cls._field(row, "Main Office Country"),
            "main_office_postal_code": cls._field(row, "Main Office Postal Code"),
            "telephone": cls._field(row, "Main Office Telephone Number"),
            "website": cls._field(row, "Website Address"),
            "office_count_other_than_principal": cls._field(row, "Total number of offices, other than your Principal Office and place of business"),
            "books_records_city": cls._field(row, "Location of Books and Records City"),
            "books_records_state": cls._field(row, "Location of Books and Records State"),
            "jurisdiction_notice_filed_effective_date": cls._field(row, "Jurisdiction Notice Filed-Effective Date"),
            "approx_private_fund_assets": cls._field(row, "1O - If yes, approx. amount of assets"),
            "disclosure_flag": cls._field(row, "11"),
        }

    @staticmethod
    def _field(row: dict[str, str], *names: str) -> str:
        for name in names:
            value = row.get(name, "")
            if value:
                return value.strip()
        return ""


class FDICBankFindInstitutionProvider:
    def __init__(
        self,
        endpoint: str = "https://api.fdic.gov/banks/institutions",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        fields = ",".join(
            [
                "NAME",
                "CERT",
                "ACTIVE",
                "CITY",
                "STALP",
                "STNAME",
                "ADDRESS",
                "ZIP",
                "WEBADDR",
                "PHONE",
                "REGAGNT",
                "INSAGNT",
                "CHARTAGNT",
                "BKCLASS",
                "ASSET",
                "DEPDOM",
                "NETINC",
                "ROA",
                "ROE",
                "REPDTE",
                "ESTYMD",
                "DATEUPDT",
                "OFFDOM",
                "OFFFOR",
                "ID",
            ]
        )

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "filters": self._filters(query),
                "fields": fields,
                "limit": normalized_limit,
                "format": "json",
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FDIC BankFind institutions request failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        items = payload.get("data") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items[:normalized_limit], start=1)
        ]

    @staticmethod
    def _filters(query: str) -> str:
        clean = query.strip().replace('"', '\\"')
        return f'NAME:"{clean}" OR WEBADDR:"{clean}" OR CITY:"{clean}"'

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        data = item.get("data") or item
        cert = data.get("CERT") or data.get("ID")
        active = data.get("ACTIVE")
        city_state = ", ".join(
            str(value)
            for value in (data.get("CITY"), data.get("STALP") or data.get("STNAME"))
            if value
        )
        return {
            "source_key": "fdic_bankfind_institutions",
            "name_zh": "FDIC BankFind 银行机构",
            "source_type": "financial_institution_registry",
            "query": query,
            "rank": rank,
            "title": data.get("NAME", ""),
            "url": f"https://banks.data.fdic.gov/bankfind-suite/bankfind/details/{cert}" if cert else "https://banks.data.fdic.gov/bankfind-suite/bankfind",
            "snippet": f"{city_state} | FDIC CERT {cert} | active={active}".strip(" |"),
            "published_at": data.get("REPDTE") or data.get("DATEUPDT"),
            "fdic_certificate": cert,
            "active": active,
            "city": data.get("CITY"),
            "state": data.get("STALP"),
            "state_name": data.get("STNAME"),
            "address": data.get("ADDRESS"),
            "zip_code": data.get("ZIP"),
            "website": data.get("WEBADDR"),
            "phone": data.get("PHONE"),
            "primary_regulator": data.get("REGAGNT"),
            "insurance_regulator": data.get("INSAGNT"),
            "charter_agency": data.get("CHARTAGNT"),
            "bank_class": data.get("BKCLASS"),
            "assets": data.get("ASSET"),
            "domestic_deposits": data.get("DEPDOM"),
            "net_income": data.get("NETINC"),
            "return_on_assets": data.get("ROA"),
            "return_on_equity": data.get("ROE"),
            "report_date": data.get("REPDTE"),
            "established_date": data.get("ESTYMD"),
            "updated_date": data.get("DATEUPDT"),
            "domestic_offices": data.get("OFFDOM"),
            "foreign_offices": data.get("OFFFOR"),
        }


class FederalRegisterDocumentSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://www.federalregister.gov/api/v1/documents.json",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        params = {
            "conditions[term]": query,
            "per_page": normalized_limit,
            "order": "newest",
            "fields[]": [
                "title",
                "abstract",
                "document_number",
                "type",
                "publication_date",
                "agency_names",
                "html_url",
                "pdf_url",
                "citation",
            ],
        }

        import requests

        response = requests.get(
            self.endpoint,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Federal Register search failed: {response.status_code} {response.text[:300]}") from exc

        results = (response.json().get("results") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(results, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        agency_names = item.get("agency_names") or []
        return {
            "source_key": "federal_register_documents",
            "name_zh": "Federal Register 监管文件",
            "source_type": "regulatory_policy",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("html_url") or item.get("pdf_url") or "",
            "snippet": item.get("abstract", "") or item.get("type", ""),
            "published_at": item.get("publication_date"),
            "document_number": item.get("document_number"),
            "document_type": item.get("type"),
            "citation": item.get("citation"),
            "agency_names": agency_names[:8],
            "pdf_url": item.get("pdf_url"),
        }


class CPSCRecallSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://www.saferproducts.gov/RestWebServices/Recall",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "ProductName": query,
                "format": "json",
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "zhaoping-agent/0.1 research contact@example.invalid",
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"CPSC recalls search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        recalls = payload if isinstance(payload, list) else payload.get("Recalls") or payload.get("recalls") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(recalls[:normalized_limit], start=1)
        ]

    @staticmethod
    def _items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _names(items: list[dict[str, Any]]) -> list[str]:
        names = []
        for item in items:
            name = item.get("Name") or item.get("name") or item.get("ProductName") or item.get("Title")
            if name:
                names.append(str(name))
        return names[:8]

    @staticmethod
    def _company_names(item: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for key in ("Manufacturers", "Importers", "Distributors", "Retailers"):
            for company in CPSCRecallSearchProvider._items(item.get(key)):
                name = company.get("Name") or company.get("CompanyName") or company.get("FirmName")
                if name:
                    names.append(str(name))
        return names[:12]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        products = CPSCRecallSearchProvider._items(item.get("Products"))
        hazards = CPSCRecallSearchProvider._items(item.get("Hazards"))
        remedies = CPSCRecallSearchProvider._items(item.get("Remedies"))
        recall_id = item.get("RecallID") or item.get("Id") or item.get("RecallNumber")
        url = item.get("URL") or item.get("Url") or item.get("RecallURL") or ""
        if not url and recall_id:
            url = f"https://www.cpsc.gov/Recalls/{recall_id}"
        return {
            "source_key": "cpsc_recalls",
            "name_zh": "CPSC 产品召回",
            "source_type": "product_safety_recall",
            "query": query,
            "rank": rank,
            "title": item.get("Title") or item.get("RecallTitle") or "",
            "url": url,
            "snippet": item.get("Description") or item.get("RecallDescription") or "",
            "published_at": item.get("RecallDate") or item.get("Date"),
            "recall_id": recall_id,
            "recall_number": item.get("RecallNumber"),
            "product_names": CPSCRecallSearchProvider._names(products),
            "hazards": CPSCRecallSearchProvider._names(hazards),
            "remedies": CPSCRecallSearchProvider._names(remedies),
            "companies": CPSCRecallSearchProvider._company_names(item),
            "consumer_contact": item.get("ConsumerContact"),
            "units": item.get("Units"),
        }


class FDAEnforcementRecallProvider:
    def __init__(
        self,
        endpoints: dict[str, str] | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoints = endpoints or {
            "device": "https://api.fda.gov/device/enforcement.json",
            "food": "https://api.fda.gov/food/enforcement.json",
            "drug": "https://api.fda.gov/drug/enforcement.json",
        }
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        per_endpoint_limit = max(1, min(normalized_limit, 50))
        search_query = self._search_query(query)
        results: list[dict] = []

        import requests

        for product_type, endpoint in self.endpoints.items():
            response = requests.get(
                endpoint,
                params={
                    "search": search_query,
                    "limit": per_endpoint_limit,
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            if response.status_code == 404:
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(f"FDA enforcement recall search failed: {response.status_code} {response.text[:300]}") from exc
            payload = response.json()
            for item in payload.get("results") or []:
                results.append(
                    self._to_result(
                        query=query,
                        rank=len(results) + 1,
                        product_type=product_type,
                        item=item,
                    )
                )
                if len(results) >= normalized_limit:
                    return results
        return results

    @staticmethod
    def _search_query(query: str) -> str:
        clean = " ".join(SearchSourceCatalogProvider._tokens(query)) or query.strip()
        if not clean:
            clean = "*"
        return f'recalling_firm:"{clean}" product_description:"{clean}" reason_for_recall:"{clean}"'

    @staticmethod
    def _to_result(query: str, rank: int, product_type: str, item: dict[str, Any]) -> dict:
        recall_number = item.get("recall_number") or item.get("event_id")
        return {
            "source_key": "fda_enforcement_recalls",
            "name_zh": "FDA Enforcement 召回",
            "source_type": "fda_enforcement_recall",
            "query": query,
            "rank": rank,
            "title": f"{item.get('recalling_firm', '')} {item.get('classification', '')} {item.get('product_description', '')}".strip(),
            "url": "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/enforcement-reports",
            "snippet": item.get("reason_for_recall") or item.get("product_description") or "",
            "published_at": item.get("report_date"),
            "product_type": product_type,
            "classification": item.get("classification"),
            "status": item.get("status"),
            "recalling_firm": item.get("recalling_firm"),
            "product_description": item.get("product_description"),
            "reason_for_recall": item.get("reason_for_recall"),
            "recall_number": recall_number,
            "event_id": item.get("event_id"),
            "recall_initiation_date": item.get("recall_initiation_date"),
            "distribution_pattern": item.get("distribution_pattern"),
            "product_quantity": item.get("product_quantity"),
            "voluntary_mandated": item.get("voluntary_mandated"),
            "firm_city": item.get("city"),
            "firm_state": item.get("state"),
            "firm_country": item.get("country"),
        }


class FDADevice510kClearanceProvider:
    def __init__(
        self,
        endpoint: str = "https://api.fda.gov/device/510k.json",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        search_query = self._search_query(query)

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search": search_query,
                "limit": normalized_limit,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FDA 510(k) clearance search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate((response.json().get("results") or [])[:normalized_limit], start=1)
        ]

    @staticmethod
    def _search_query(query: str) -> str:
        clean = " ".join(SearchSourceCatalogProvider._tokens(query)) or query.strip()
        if not clean:
            return "*"
        return f'device_name:"{clean}" applicant:"{clean}" product_code:"{clean}" k_number:"{clean}"'

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        openfda = item.get("openfda") or {}
        k_number = item.get("k_number") or ""
        device_name = item.get("device_name") or openfda.get("device_name") or ""
        applicant = item.get("applicant") or ""
        return {
            "source_key": "fda_device_510k",
            "name_zh": "FDA 510(k) 器械准入",
            "source_type": "fda_device_clearance",
            "query": query,
            "rank": rank,
            "title": f"{k_number} {device_name} {applicant}".strip(),
            "url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k_number}" if k_number else "https://www.fda.gov/medical-devices/device-approvals-denials-and-clearances/510k-clearances",
            "snippet": item.get("decision_description") or item.get("statement_or_summary") or "",
            "published_at": item.get("decision_date"),
            "k_number": k_number,
            "device_name": device_name,
            "applicant": applicant,
            "decision_date": item.get("decision_date"),
            "decision_code": item.get("decision_code"),
            "decision_description": item.get("decision_description"),
            "date_received": item.get("date_received"),
            "clearance_type": item.get("clearance_type"),
            "product_code": item.get("product_code"),
            "advisory_committee": item.get("advisory_committee"),
            "advisory_committee_description": item.get("advisory_committee_description"),
            "review_advisory_committee": item.get("review_advisory_committee"),
            "statement_or_summary": item.get("statement_or_summary"),
            "third_party_flag": item.get("third_party_flag"),
            "expedited_review_flag": item.get("expedited_review_flag"),
            "city": item.get("city"),
            "state": item.get("state"),
            "country_code": item.get("country_code"),
            "openfda_device_name": openfda.get("device_name"),
            "openfda_device_class": openfda.get("device_class"),
            "openfda_regulation_number": openfda.get("regulation_number"),
            "openfda_medical_specialty": openfda.get("medical_specialty_description"),
            "openfda_registration_numbers": openfda.get("registration_number", [])[:8]
            if isinstance(openfda.get("registration_number"), list)
            else [],
            "openfda_fei_numbers": openfda.get("fei_number", [])[:8]
            if isinstance(openfda.get("fei_number"), list)
            else [],
        }


class FDADeviceAdverseEventProvider:
    def __init__(
        self,
        endpoint: str = "https://api.fda.gov/device/event.json",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        search_query = self._search_query(query)

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search": search_query,
                "limit": normalized_limit,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FDA device adverse event search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate((response.json().get("results") or [])[:normalized_limit], start=1)
        ]

    @staticmethod
    def _search_query(query: str) -> str:
        clean = " ".join(SearchSourceCatalogProvider._tokens(query)) or query.strip()
        if not clean:
            return "*"
        return f'device.brand_name:"{clean}" device.generic_name:"{clean}" device.manufacturer_d_name:"{clean}" manufacturer_name:"{clean}"'

    @classmethod
    def _to_result(cls, query: str, rank: int, item: dict[str, Any]) -> dict:
        devices = item.get("device") or []
        first_device = devices[0] if devices else {}
        openfda = first_device.get("openfda") or {}
        report_number = item.get("report_number") or ""
        brand_name = first_device.get("brand_name") or ""
        generic_name = first_device.get("generic_name") or openfda.get("device_name") or ""
        manufacturer = first_device.get("manufacturer_d_name") or item.get("manufacturer_name") or ""
        event_type = item.get("event_type") or ""
        return {
            "source_key": "fda_device_events",
            "name_zh": "FDA MAUDE 器械不良事件",
            "source_type": "fda_device_adverse_event",
            "query": query,
            "rank": rank,
            "title": f"{event_type} {brand_name or generic_name} {report_number}".strip(),
            "url": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfmaude/search.cfm",
            "snippet": cls._snippet(item),
            "published_at": item.get("date_received") or item.get("date_of_event"),
            "report_number": report_number,
            "event_type": event_type,
            "date_received": item.get("date_received"),
            "date_of_event": item.get("date_of_event"),
            "date_report": item.get("date_report"),
            "date_added": item.get("date_added"),
            "type_of_report": item.get("type_of_report", []),
            "source_type_raw": item.get("source_type", []),
            "report_to_fda": item.get("report_to_fda"),
            "product_problem_flag": item.get("product_problem_flag"),
            "patient_sequence_number": cls._patient_value(item, "sequence_number_treatment"),
            "patient_sequence_number_outcome": cls._patient_value(item, "sequence_number_outcome"),
            "device_brand_name": brand_name,
            "device_generic_name": generic_name,
            "device_manufacturer": manufacturer,
            "device_product_code": first_device.get("device_report_product_code"),
            "device_operator": first_device.get("device_operator"),
            "model_number": first_device.get("model_number"),
            "catalog_number": first_device.get("catalog_number"),
            "lot_number": first_device.get("lot_number"),
            "udi_di": first_device.get("udi_di"),
            "udi_public": first_device.get("udi_public"),
            "pma_pmn_number": item.get("pma_pmn_number"),
            "openfda_device_name": openfda.get("device_name"),
            "openfda_device_class": openfda.get("device_class"),
            "openfda_regulation_number": openfda.get("regulation_number"),
            "openfda_medical_specialty": openfda.get("medical_specialty_description"),
        }

    @staticmethod
    def _snippet(item: dict[str, Any]) -> str:
        text_fields = []
        for text_item in item.get("mdr_text") or []:
            text = text_item.get("text") or text_item.get("patient_sequence_number")
            if text:
                text_fields.append(str(text))
        return " ".join(text_fields)[:500]

    @staticmethod
    def _patient_value(item: dict[str, Any], key: str) -> Any:
        patients = item.get("patient") or []
        if not patients:
            return None
        return patients[0].get(key)


class FDADeviceClassificationProvider:
    def __init__(
        self,
        endpoint: str = "https://api.fda.gov/device/classification.json",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        search_query = self._search_query(query)

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search": search_query,
                "limit": normalized_limit,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FDA device classification search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate((response.json().get("results") or [])[:normalized_limit], start=1)
        ]

    @staticmethod
    def _search_query(query: str) -> str:
        clean = " ".join(SearchSourceCatalogProvider._tokens(query)) or query.strip()
        if not clean:
            return "*"
        return f'product_code:"{clean}" device_name:"{clean}" medical_specialty:"{clean}" medical_specialty_description:"{clean}"'

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        openfda = item.get("openfda") or {}
        product_code = item.get("product_code") or ""
        device_name = item.get("device_name") or ""
        return {
            "source_key": "fda_device_classification",
            "name_zh": "FDA 器械分类与产品代码",
            "source_type": "fda_device_classification",
            "query": query,
            "rank": rank,
            "title": f"{product_code} {device_name}".strip(),
            "url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?ID={product_code}" if product_code else "https://www.fda.gov/medical-devices/classify-your-medical-device/product-classification",
            "snippet": item.get("definition") or item.get("medical_specialty_description") or "",
            "published_at": None,
            "product_code": product_code,
            "device_name": device_name,
            "device_class": item.get("device_class"),
            "regulation_number": item.get("regulation_number"),
            "medical_specialty": item.get("medical_specialty"),
            "medical_specialty_description": item.get("medical_specialty_description"),
            "review_panel": item.get("review_panel"),
            "review_code": item.get("review_code"),
            "submission_type_id": item.get("submission_type_id"),
            "third_party_flag": item.get("third_party_flag"),
            "life_sustain_support_flag": item.get("life_sustain_support_flag"),
            "implant_flag": item.get("implant_flag"),
            "gmp_exempt_flag": item.get("gmp_exempt_flag"),
            "summary_malfunction_reporting": item.get("summary_malfunction_reporting"),
            "unclassified_reason": item.get("unclassified_reason"),
            "definition": item.get("definition"),
            "openfda_k_numbers": openfda.get("k_number", [])[:8]
            if isinstance(openfda.get("k_number"), list)
            else [],
            "openfda_registration_numbers": openfda.get("registration_number", [])[:8]
            if isinstance(openfda.get("registration_number"), list)
            else [],
            "openfda_fei_numbers": openfda.get("fei_number", [])[:8]
            if isinstance(openfda.get("fei_number"), list)
            else [],
        }


class FDADeviceRegistrationListingProvider:
    def __init__(
        self,
        endpoint: str = "https://api.fda.gov/device/registrationlisting.json",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        search_query = self._search_query(query)

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search": search_query,
                "limit": normalized_limit,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FDA device registration listing search failed: {response.status_code} {response.text[:300]}") from exc

        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate((response.json().get("results") or [])[:normalized_limit], start=1)
        ]

    @staticmethod
    def _search_query(query: str) -> str:
        clean = " ".join(SearchSourceCatalogProvider._tokens(query)) or query.strip()
        if not clean:
            return "*"
        return f'products.product_code:"{clean}" products.openfda.device_name:"{clean}" registration.name:"{clean}" registration.owner_operator.firm_name:"{clean}"'

    @classmethod
    def _to_result(cls, query: str, rank: int, item: dict[str, Any]) -> dict:
        registration = item.get("registration") or {}
        owner_operator = registration.get("owner_operator") or {}
        contact_address = owner_operator.get("contact_address") or {}
        products = item.get("products") or []
        first_product = products[0] if products else {}
        openfda = first_product.get("openfda") or {}
        registration_number = registration.get("registration_number") or ""
        firm_name = registration.get("name") or owner_operator.get("firm_name") or ""
        product_codes = cls._values(products, "product_code")
        return {
            "source_key": "fda_device_registration_listing",
            "name_zh": "FDA 器械注册与列名",
            "source_type": "fda_device_registration_listing",
            "query": query,
            "rank": rank,
            "title": f"{registration_number} {firm_name}".strip(),
            "url": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRL/rl.cfm",
            "snippet": " | ".join(str(item) for item in item.get("establishment_type", [])[:3]),
            "published_at": registration.get("reg_expiry_date_year"),
            "registration_number": registration_number,
            "fei_number": registration.get("fei_number"),
            "registration_status_code": registration.get("status_code"),
            "registration_expiry_year": registration.get("reg_expiry_date_year"),
            "initial_importer_flag": registration.get("initial_importer_flag"),
            "firm_name": firm_name,
            "address_line_1": registration.get("address_line_1"),
            "city": registration.get("city"),
            "state_code": registration.get("state_code"),
            "country_code": registration.get("iso_country_code"),
            "zip_code": registration.get("zip_code"),
            "owner_operator_firm_name": owner_operator.get("firm_name"),
            "owner_operator_number": owner_operator.get("owner_operator_number"),
            "owner_operator_city": contact_address.get("city"),
            "owner_operator_state_code": contact_address.get("state_code"),
            "owner_operator_country_code": contact_address.get("iso_country_code"),
            "establishment_types": item.get("establishment_type", []),
            "proprietary_names": item.get("proprietary_name", [])[:8],
            "product_codes": product_codes[:12],
            "product_count": len(products),
            "pma_number": item.get("pma_number"),
            "k_number": item.get("k_number"),
            "first_product_code": first_product.get("product_code"),
            "first_product_created_date": first_product.get("created_date"),
            "first_product_exempt": first_product.get("exempt"),
            "openfda_device_name": openfda.get("device_name"),
            "openfda_device_class": openfda.get("device_class"),
            "openfda_regulation_number": openfda.get("regulation_number"),
            "openfda_medical_specialty": openfda.get("medical_specialty_description"),
        }

    @staticmethod
    def _values(items: list[dict[str, Any]], key: str) -> list[str]:
        values = []
        for item in items:
            value = item.get(key)
            if value not in (None, ""):
                values.append(str(value))
        return values


class CFPBConsumerComplaintProvider:
    def __init__(
        self,
        endpoint: str = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "search_term": query,
                "size": normalized_limit,
                "sort": "created_date_desc",
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"CFPB consumer complaint search failed: {response.status_code} {response.text[:300]}") from exc

        complaints = self._complaints(response.json())
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(complaints[:normalized_limit], start=1)
        ]

    @staticmethod
    def _complaints(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        hits = ((payload.get("hits") or {}).get("hits")) if isinstance(payload, dict) else None
        if isinstance(hits, list):
            return [
                (item.get("_source") or item)
                for item in hits
                if isinstance(item, dict)
            ]
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        company = item.get("company") or item.get("Company") or ""
        product = item.get("product") or item.get("Product") or ""
        issue = item.get("issue") or item.get("Issue") or ""
        complaint_id = item.get("complaint_id") or item.get("Complaint ID")
        return {
            "source_key": "cfpb_consumer_complaints",
            "name_zh": "CFPB 消费金融投诉",
            "source_type": "consumer_finance_complaint",
            "query": query,
            "rank": rank,
            "title": f"{company} {product} {issue}".strip(),
            "url": "https://www.consumerfinance.gov/data-research/consumer-complaints/",
            "snippet": item.get("consumer_complaint_narrative") or item.get("Consumer complaint narrative") or issue,
            "published_at": item.get("date_received") or item.get("Date received"),
            "complaint_id": complaint_id,
            "company": company,
            "product": product,
            "sub_product": item.get("sub_product") or item.get("Sub-product"),
            "issue": issue,
            "sub_issue": item.get("sub_issue") or item.get("Sub-issue"),
            "company_response": item.get("company_response") or item.get("Company response to consumer"),
            "company_public_response": item.get("company_public_response") or item.get("Company public response"),
            "timely_response": item.get("timely") or item.get("Timely response?"),
            "consumer_disputed": item.get("consumer_disputed") or item.get("Consumer disputed?"),
            "submitted_via": item.get("submitted_via") or item.get("Submitted via"),
            "date_sent_to_company": item.get("date_sent_to_company") or item.get("Date sent to company"),
            "state": item.get("state") or item.get("State"),
            "tags": item.get("tags") or item.get("Tags"),
        }


class NHTSARecallSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.nhtsa.gov/recalls/recallsByVehicle",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        vehicle = self._parse_vehicle(query)
        if vehicle is None:
            return []

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "make": vehicle["make"],
                "model": vehicle["model"],
                "modelYear": vehicle["model_year"],
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"NHTSA recall search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        recalls = payload.get("results") or payload.get("Results") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(recalls[:normalized_limit], start=1)
        ]

    @staticmethod
    def _parse_vehicle(query: str) -> dict[str, str] | None:
        tokens = SearchSourceCatalogProvider._tokens(query)
        model_year = ""
        words = []
        stopwords = {"recall", "recalls", "safety", "vehicle", "car", "truck", "nhtsa"}
        for token in tokens:
            if token.isdigit() and len(token) == 4 and not model_year:
                model_year = token
                continue
            if token.casefold() not in stopwords:
                words.append(token)
        if not model_year or len(words) < 2:
            return None
        return {
            "model_year": model_year,
            "make": words[0],
            "model": " ".join(words[1:]),
        }

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        campaign = item.get("NHTSACampaignNumber") or item.get("CampaignNumber") or item.get("nhtsaCampaignNumber")
        make = item.get("Make") or item.get("make") or ""
        model = item.get("Model") or item.get("model") or ""
        model_year = item.get("ModelYear") or item.get("modelYear") or ""
        component = item.get("Component") or item.get("component") or ""
        return {
            "source_key": "nhtsa_recalls",
            "name_zh": "NHTSA 车辆召回",
            "source_type": "vehicle_safety_recall",
            "query": query,
            "rank": rank,
            "title": f"{model_year} {make} {model} {component}".strip(),
            "url": "https://www.nhtsa.gov/recalls",
            "snippet": item.get("Summary") or item.get("summary") or item.get("Consequence") or "",
            "published_at": item.get("ReportReceivedDate") or item.get("reportReceivedDate"),
            "campaign_number": campaign,
            "manufacturer": item.get("Manufacturer") or item.get("manufacturer"),
            "make": make,
            "model": model,
            "model_year": model_year,
            "component": component,
            "summary": item.get("Summary") or item.get("summary"),
            "consequence": item.get("Consequence") or item.get("consequence"),
            "remedy": item.get("Remedy") or item.get("remedy"),
            "notes": item.get("Notes") or item.get("notes"),
        }


class EPAEchoFacilityComplianceProvider:
    def __init__(
        self,
        endpoint: str = "https://echodata.epa.gov/echo/echo_rest_services.get_facilities",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.qid_endpoint = endpoint.replace("get_facilities", "get_qid")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "p_fn": query,
                "output": "json",
                "responseset": normalized_limit,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"EPA ECHO facility compliance search failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        facilities = self._facilities(payload)
        if not facilities:
            qid = self._query_id(payload)
            if qid:
                qid_response = requests.get(
                    self.qid_endpoint,
                    params={
                        "qid": qid,
                        "output": "json",
                        "responseset": normalized_limit,
                    },
                    headers={"Accept": "application/json"},
                    timeout=self.timeout_seconds,
                )
                try:
                    qid_response.raise_for_status()
                except requests.HTTPError as exc:
                    raise RuntimeError(
                        f"EPA ECHO facility compliance qid lookup failed: {qid_response.status_code} {qid_response.text[:300]}"
                    ) from exc
                facilities = self._facilities(qid_response.json())
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(facilities[:normalized_limit], start=1)
        ]

    @staticmethod
    def _query_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        results = payload.get("Results") or payload.get("results") or payload
        if isinstance(results, dict):
            value = results.get("QueryID") or results.get("QueryId") or results.get("query_id")
            return str(value) if value not in (None, "") else None
        return None

    @staticmethod
    def _facilities(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("Results", "results", "Facilities", "facilities"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        results = payload.get("Results")
        if isinstance(results, dict):
            for key in ("Facility", "Facilities", "facilities", "rows"):
                value = results.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _first(item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in item and item.get(key) not in {None, ""}:
                return item.get(key)
        return None

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        registry_id = EPAEchoFacilityComplianceProvider._first(item, "REGISTRY_ID", "RegistryID", "registry_id", "RegistryId")
        name = EPAEchoFacilityComplianceProvider._first(item, "FAC_NAME", "FacName", "FacilityName", "facility_name", "FACILITY_NAME") or ""
        city = EPAEchoFacilityComplianceProvider._first(item, "FAC_CITY", "FacCity", "City", "city")
        state = EPAEchoFacilityComplianceProvider._first(item, "FAC_STATE", "FacState", "State", "state")
        return {
            "source_key": "epa_echo_facilities",
            "name_zh": "EPA ECHO 设施合规",
            "source_type": "environmental_compliance",
            "query": query,
            "rank": rank,
            "title": str(name),
            "url": f"https://echo.epa.gov/detailed-facility-report?fid={registry_id}" if registry_id else "https://echo.epa.gov/",
            "snippet": str(EPAEchoFacilityComplianceProvider._first(item, "FAC_ACTIVE_FLAG", "FacActiveFlag", "ACTIVE_FLAG", "AIR_FLAG") or ""),
            "published_at": EPAEchoFacilityComplianceProvider._first(item, "LAST_REFRESH_DATE", "last_refresh_date"),
            "registry_id": registry_id,
            "facility_name": name,
            "address": EPAEchoFacilityComplianceProvider._first(item, "FAC_STREET", "FacStreet", "Street", "address", "FAC_ADDRESS"),
            "city": city,
            "state": state,
            "zip": EPAEchoFacilityComplianceProvider._first(item, "FAC_ZIP", "FacZip", "Zip", "zip"),
            "county": EPAEchoFacilityComplianceProvider._first(item, "FAC_COUNTY", "FacCounty", "County", "county"),
            "latitude": EPAEchoFacilityComplianceProvider._first(item, "FAC_LAT", "FacLat", "Latitude", "latitude"),
            "longitude": EPAEchoFacilityComplianceProvider._first(item, "FAC_LONG", "FacLong", "Longitude", "longitude"),
            "program_system_ids": EPAEchoFacilityComplianceProvider._first(item, "PGM_SYS_ID", "ProgramSystemIDs", "program_system_ids"),
            "naics_codes": EPAEchoFacilityComplianceProvider._first(item, "NAICS_CODES", "FacNAICSCodes", "NaicsCodes", "naics_codes"),
            "sic_codes": EPAEchoFacilityComplianceProvider._first(item, "SIC_CODES", "FacSICCodes", "SicCodes", "sic_codes"),
            "compliance_status": EPAEchoFacilityComplianceProvider._first(
                item,
                "CWP_STATUS",
                "CAA_STATUS",
                "RCRA_STATUS",
                "FacComplianceStatus",
                "CAAComplianceStatus",
                "CWAComplianceStatus",
                "RCRAComplianceStatus",
                "compliance_status",
            ),
            "quarters_in_noncompliance": EPAEchoFacilityComplianceProvider._first(item, "QTRS_IN_NC", "FacQtrsWithNC", "quarters_in_noncompliance"),
            "formal_actions": EPAEchoFacilityComplianceProvider._first(item, "FORMAL_ACTION_COUNT", "FacFormalActionCount", "formal_actions"),
            "penalties": EPAEchoFacilityComplianceProvider._first(item, "PENALTY_COUNT", "FacPenaltyCount", "penalties"),
        }


class ClinicalTrialsStudySearchProvider:
    def __init__(
        self,
        endpoint: str = "https://clinicaltrials.gov/api/v2/studies",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "query.term": query,
                "pageSize": normalized_limit,
                "format": "json",
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"ClinicalTrials.gov search failed: {response.status_code} {response.text[:300]}") from exc

        studies = response.json().get("studies") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(studies[:normalized_limit], start=1)
        ]

    @staticmethod
    def _names(values: Any, *keys: str) -> list[str]:
        if not isinstance(values, list):
            return []
        names: list[str] = []
        for value in values:
            if isinstance(value, str):
                names.append(value)
                continue
            if not isinstance(value, dict):
                continue
            for key in keys:
                if value.get(key):
                    names.append(str(value[key]))
                    break
        return names[:12]

    @staticmethod
    def _locations(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        locations: list[str] = []
        for location in values:
            if not isinstance(location, dict):
                continue
            facility = location.get("facility") or ""
            city = location.get("city") or ""
            country = location.get("country") or ""
            label = ", ".join(part for part in (facility, city, country) if part)
            if label:
                locations.append(label)
        return locations[:8]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        protocol = item.get("protocolSection") or {}
        identification = protocol.get("identificationModule") or {}
        status = protocol.get("statusModule") or {}
        sponsor = protocol.get("sponsorCollaboratorsModule") or {}
        design = protocol.get("designModule") or {}
        conditions = protocol.get("conditionsModule") or {}
        arms = protocol.get("armsInterventionsModule") or {}
        outcomes = protocol.get("outcomesModule") or {}
        contacts = protocol.get("contactsLocationsModule") or {}

        nct_id = identification.get("nctId")
        lead_sponsor = sponsor.get("leadSponsor") or {}
        enrollment = design.get("enrollmentInfo") or {}
        phases = design.get("phases") or []
        primary_outcomes = ClinicalTrialsStudySearchProvider._names(outcomes.get("primaryOutcomes"), "measure")
        return {
            "source_key": "clinicaltrials_studies",
            "name_zh": "ClinicalTrials.gov 试验登记",
            "source_type": "clinical_trial_registry",
            "query": query,
            "rank": rank,
            "title": identification.get("briefTitle") or identification.get("officialTitle") or "",
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "https://clinicaltrials.gov/",
            "snippet": identification.get("officialTitle") or "",
            "published_at": status.get("studyFirstSubmitDate") or status.get("studyFirstPostDateStruct", {}).get("date"),
            "nct_id": nct_id,
            "brief_title": identification.get("briefTitle"),
            "official_title": identification.get("officialTitle"),
            "overall_status": status.get("overallStatus"),
            "start_date": (status.get("startDateStruct") or {}).get("date"),
            "completion_date": (status.get("completionDateStruct") or {}).get("date"),
            "primary_completion_date": (status.get("primaryCompletionDateStruct") or {}).get("date"),
            "lead_sponsor": lead_sponsor.get("name"),
            "lead_sponsor_class": lead_sponsor.get("class"),
            "collaborators": ClinicalTrialsStudySearchProvider._names(sponsor.get("collaborators"), "name"),
            "phases": phases[:8] if isinstance(phases, list) else [],
            "study_type": design.get("studyType"),
            "enrollment_count": enrollment.get("count"),
            "enrollment_type": enrollment.get("type"),
            "conditions": ClinicalTrialsStudySearchProvider._names(conditions.get("conditions")),
            "interventions": ClinicalTrialsStudySearchProvider._names(arms.get("interventions"), "name"),
            "primary_outcomes": primary_outcomes,
            "locations": ClinicalTrialsStudySearchProvider._locations(contacts.get("locations")),
        }


class CMSOpenPaymentsSearchProvider:
    def __init__(
        self,
        metastore_endpoint: str = "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items",
        datastore_endpoint_template: str = "https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0",
        timeout_seconds: int = 20,
        dataset_limit: int = 100,
    ) -> None:
        self.metastore_endpoint = metastore_endpoint
        self.datastore_endpoint_template = datastore_endpoint_template
        self.timeout_seconds = timeout_seconds
        self.dataset_limit = dataset_limit

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 30))
        datasets = self._latest_payment_datasets()
        per_dataset_limit = max(1, normalized_limit // max(1, len(datasets)))
        results: list[dict[str, Any]] = []

        import requests

        for payment_type, dataset in datasets:
            response = requests.get(
                self.datastore_endpoint_template.format(dataset_id=dataset["identifier"]),
                params={
                    "limit": per_dataset_limit,
                    "q": query,
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(
                    f"CMS Open Payments datastore query failed: {response.status_code} {response.text[:300]}"
                ) from exc

            rows = (response.json().get("results") or [])[:per_dataset_limit]
            results.extend(
                self._to_result(
                    query=query,
                    rank=len(results) + rank,
                    payment_type=payment_type,
                    dataset=dataset,
                    item=item,
                )
                for rank, item in enumerate(rows, start=1)
            )

        return results[:normalized_limit]

    def _latest_payment_datasets(self) -> list[tuple[str, dict[str, Any]]]:
        import requests

        response = requests.get(
            self.metastore_endpoint,
            params={"limit": self.dataset_limit, "offset": 0},
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"CMS Open Payments metastore query failed: {response.status_code} {response.text[:300]}"
            ) from exc

        selected: dict[str, dict[str, Any]] = {}
        for item in response.json():
            title = str(item.get("title", ""))
            description = str(item.get("description", ""))
            haystack = f"{title}\n{description}"
            year = self._year(haystack)
            payment_type = self._payment_type(haystack)
            identifier = item.get("identifier")
            if not year or not payment_type or not identifier:
                continue
            current = selected.get(payment_type)
            if current is None or int(year) > int(current["year"]):
                selected[payment_type] = {
                    "identifier": str(identifier),
                    "title": title,
                    "year": year,
                    "description": description,
                }

        return [
            (payment_type, selected[payment_type])
            for payment_type in ("general", "research", "ownership")
            if payment_type in selected
        ]

    @staticmethod
    def _year(text: str) -> str | None:
        import re

        match = re.search(r"\b(20\d{2})\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _payment_type(text: str) -> str | None:
        lowered = text.casefold()
        if "general payment data" in lowered:
            return "general"
        if "research payment data" in lowered:
            return "research"
        if "ownership payment data" in lowered:
            return "ownership"
        return None

    @classmethod
    def _to_result(
        cls,
        query: str,
        rank: int,
        payment_type: str,
        dataset: dict[str, Any],
        item: dict[str, Any],
    ) -> dict:
        manufacturer = cls._first(
            item,
            "applicable_manufacturer_or_applicable_gpo_making_payment_name",
            "submitting_applicable_manufacturer_or_applicable_gpo_name",
            "applicable_manufacturer_or_applicable_gpo_name",
        )
        recipient = cls._recipient_name(item)
        amount = cls._first(
            item,
            "total_amount_of_payment_usdollars",
            "total_amount_invested_usdollars",
            "dollar_amount_invested",
            "value_of_interest",
        )
        nature = cls._first(item, "nature_of_payment_or_transfer_of_value", "nature_of_ownership_or_investment_interest")
        product = cls._first(
            item,
            "name_of_drug_or_biological_or_device_or_medical_supply_1",
            "name_of_associated_covered_drug_or_biological1",
            "name_of_associated_covered_device_or_medical_supply1",
            "product_category_or_therapeutic_area_1",
        )
        payment_date = cls._first(item, "date_of_payment", "program_year")
        title = " ".join(part for part in [manufacturer, recipient, amount] if part)
        return {
            "source_key": "cms_openpayments",
            "name_zh": "CMS Open Payments 医疗付款",
            "source_type": "healthcare_payments",
            "query": query,
            "rank": rank,
            "title": title or str(dataset.get("title", "CMS Open Payments")),
            "url": f"https://openpaymentsdata.cms.gov/dataset/{dataset['identifier']}",
            "snippet": " | ".join(part for part in [nature, product] if part),
            "published_at": payment_date,
            "dataset_id": dataset["identifier"],
            "program_year": dataset.get("year") or cls._first(item, "program_year"),
            "payment_type": payment_type,
            "manufacturer_or_gpo": manufacturer,
            "covered_recipient": recipient,
            "covered_recipient_type": cls._first(item, "covered_recipient_type"),
            "covered_recipient_npi": cls._first(item, "covered_recipient_npi"),
            "teaching_hospital_name": cls._first(item, "teaching_hospital_name"),
            "recipient_state": cls._first(item, "recipient_state"),
            "recipient_country": cls._first(item, "recipient_country"),
            "total_amount_usd": amount,
            "nature_of_payment": nature,
            "form_of_payment": cls._first(item, "form_of_payment_or_transfer_of_value"),
            "related_product": product,
            "contextual_information": cls._first(item, "contextual_information"),
        }

    @classmethod
    def _recipient_name(cls, item: dict[str, Any]) -> str:
        hospital = cls._first(item, "teaching_hospital_name")
        if hospital:
            return hospital
        parts = [
            cls._first(item, "covered_recipient_first_name", "physician_profile_first_name"),
            cls._first(item, "covered_recipient_middle_name", "physician_profile_middle_name"),
            cls._first(item, "covered_recipient_last_name", "physician_profile_last_name"),
        ]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _first(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""


class CensusInternationalTradeProvider:
    def __init__(
        self,
        imports_endpoint: str = "https://api.census.gov/data/timeseries/intltrade/imports/hs",
        exports_endpoint: str = "https://api.census.gov/data/timeseries/intltrade/exports/hs",
        api_key_env: str = "CENSUS_API_KEY",
        timeout_seconds: int = 30,
    ) -> None:
        self.imports_endpoint = imports_endpoint
        self.exports_endpoint = exports_endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 100))
        endpoint = self.imports_endpoint if "export" not in query.casefold() and "出口" not in query else self.exports_endpoint
        params = {
            "get": "CTY_CODE,CTY_NAME,I_COMMODITY,I_COMMODITY_LDESC,GEN_VAL_MO,GEN_VAL_YR",
            "time": "latest",
            "COMM_LVL": "HS6",
            "key": api_key,
        }
        tokens = SearchSourceCatalogProvider._tokens(query)
        hs_code = self._first_hs_code(tokens)
        if hs_code:
            params["I_COMMODITY"] = hs_code

        import requests

        response = requests.get(
            endpoint,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Census international trade request failed: {response.status_code} {response.text[:300]}") from exc

        rows = response.json()
        if not rows:
            return []
        header = rows[0]
        results = [
            dict(zip(header, row))
            for row in rows[1 : normalized_limit + 1]
        ]
        return [
            self._to_result(query=query, rank=rank, endpoint=endpoint, item=item)
            for rank, item in enumerate(results, start=1)
        ]

    @staticmethod
    def _first_hs_code(tokens: list[str]) -> str | None:
        for token in tokens:
            digits = "".join(char for char in token if char.isdigit())
            if len(digits) in {2, 4, 6, 10}:
                return digits
        return None

    @staticmethod
    def _to_result(query: str, rank: int, endpoint: str, item: dict[str, Any]) -> dict:
        commodity = item.get("I_COMMODITY") or ""
        country = item.get("CTY_NAME") or ""
        return {
            "source_key": "census_international_trade",
            "name_zh": "US Census 国际贸易",
            "source_type": "trade_flows",
            "query": query,
            "rank": rank,
            "title": f"{country} {commodity}".strip(),
            "url": endpoint,
            "snippet": item.get("I_COMMODITY_LDESC", ""),
            "published_at": item.get("time"),
            "country_code": item.get("CTY_CODE"),
            "country_name": country,
            "commodity_code": commodity,
            "commodity_description": item.get("I_COMMODITY_LDESC"),
            "monthly_value": item.get("GEN_VAL_MO"),
            "year_to_date_value": item.get("GEN_VAL_YR"),
            "time": item.get("time"),
        }


class GDELTDocNewsSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.gdeltproject.org/api/v2/doc/doc",
        timespan: str = "7d",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.timespan = timespan
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 250))
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": normalized_limit,
            "timespan": self.timespan,
            "sort": "datedesc",
        }

        import requests

        response = None
        for attempt in range(2):
            response = requests.get(
                self.endpoint,
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 and attempt == 0:
                time.sleep(5.25)
                continue
            break
        if response is None:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 429:
                return []
            raise RuntimeError(f"GDELT DOC request failed: {response.status_code} {response.text[:300]}") from exc

        articles = response.json().get("articles") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(articles[:normalized_limit], start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        return {
            "source_key": "gdelt_doc_news",
            "name_zh": "GDELT 全球新闻",
            "source_type": "news_media",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("seendate", "") or item.get("title", ""),
            "published_at": item.get("seendate"),
            "domain": item.get("domain"),
            "source_country": item.get("sourcecountry"),
            "language": item.get("language"),
            "social_image": item.get("socialimage"),
        }


class GNewsFundingNewsProvider:
    def __init__(
        self,
        endpoint: str = "https://gnews.io/api/v4/search",
        api_key_env: str = "GNEWS_API_KEY",
        lang: str = "en",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.lang = lang
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 10))
        funding_query = f"({query}) AND (funding OR financing OR acquisition OR merger OR investment OR venture)"

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "q": funding_query,
                "max": normalized_limit,
                "lang": self.lang,
                "apikey": api_key,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"GNews funding search failed: {response.status_code} {response.text[:300]}") from exc

        articles = (response.json().get("articles") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(articles, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        source = item.get("source") or {}
        return {
            "source_key": "gnews_funding_news",
            "name_zh": "GNews 融资事件新闻",
            "source_type": "funding_news",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", "") or item.get("content", ""),
            "published_at": item.get("publishedAt"),
            "source_name": source.get("name"),
            "source_url": source.get("url"),
            "image": item.get("image"),
        }


class SECEnforcementSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://www.sec.gov/search",
        user_agent: str = "zhaoping-agent/0.1 research contact@example.invalid",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 50))

        import requests

        try:
            response = requests.get(
                self.endpoint,
                params={},
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            return []
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SEC enforcement search failed: {response.status_code} {response.text[:300]}") from exc

        content_type = response.headers.get("content-type", "") if hasattr(response, "headers") else ""
        if "json" not in content_type.casefold():
            return self._parse_litigation_releases(query=query, limit=normalized_limit, html=response.text)

        payload = response.json()
        hits = payload.get("hits") or payload.get("results") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(hits[:normalized_limit], start=1)
        ]

    @classmethod
    def _parse_litigation_releases(cls, query: str, limit: int, html: str) -> list[dict]:
        entries: list[dict[str, Any]] = []
        link_pattern = re.compile(
            r"<a[^>]+href=[\"'](?P<href>[^\"']*?/enforcement-litigation/litigation-releases/lr-\d+[^\"']*)[\"'][^>]*>(?P<title>.*?)</a>",
            re.IGNORECASE | re.DOTALL,
        )
        time_pattern = re.compile(
            r"<time[^>]+datetime=[\"'](?P<datetime>[^\"']+)[\"'][^>]*>(?P<label>.*?)</time>",
            re.IGNORECASE | re.DOTALL,
        )
        release_pattern = re.compile(r"Release\s+No\.?(?:</[^>]+>\s*<[^>]+>)?\s*(?P<release>LR-\s*\d+)", re.IGNORECASE | re.DOTALL)
        for match in link_pattern.finditer(html):
            before = html[max(0, match.start() - 1600) : match.start()]
            after = html[match.end() : match.end() + 1600]
            time_matches = list(time_pattern.finditer(before))
            published_at = None
            if time_matches:
                published_at = time_matches[-1].group("datetime").split("T", 1)[0]
            release_match = release_pattern.search(after)
            release_no = cls._clean_html(release_match.group("release")) if release_match else ""
            entries.append(
                {
                    "source_key": "sec_enforcement_search",
                    "name_zh": "SEC 执法/处罚搜索",
                    "source_type": "regulatory_enforcement",
                    "query": query,
                    "rank": len(entries) + 1,
                    "title": cls._clean_html(match.group("title")),
                    "url": urljoin("https://www.sec.gov", match.group("href")),
                    "snippet": release_no,
                    "published_at": published_at,
                    "release_no": release_no,
                    "category": "Litigation Release",
                    "agency": "SEC",
                }
            )
            if len(entries) >= limit:
                break
        tokens = [token.casefold() for token in SearchSourceCatalogProvider._tokens(query)]
        matched = [
            entry
            for entry in entries
            if tokens and any(token in f"{entry['title']} {entry['snippet']}".casefold() for token in tokens)
        ]
        return matched[:limit] or entries[:limit]

    @staticmethod
    def _clean_html(value: str) -> str:
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        source = item.get("_source") or item
        url = source.get("url") or source.get("path") or source.get("link") or ""
        if isinstance(url, str) and url.startswith("/"):
            url = f"https://www.sec.gov{url}"
        return {
            "source_key": "sec_enforcement_search",
            "name_zh": "SEC 执法/处罚搜索",
            "source_type": "regulatory_enforcement",
            "query": query,
            "rank": rank,
            "title": source.get("title") or source.get("headline") or "",
            "url": url,
            "snippet": source.get("description") or source.get("summary") or source.get("teaser") or "",
            "published_at": source.get("date") or source.get("release_date") or source.get("published_at"),
            "category": source.get("category") or source.get("type"),
            "agency": "SEC",
        }


class USAJobsSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://data.usajobs.gov/api/Search",
        api_key_env: str = "USAJOBS_API_KEY",
        user_agent_env: str = "USAJOBS_USER_AGENT",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.user_agent_env = user_agent_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        user_agent = os.environ.get(self.user_agent_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")
        if not user_agent:
            raise RuntimeError(f"Missing required environment variable: {self.user_agent_env}")

        normalized_limit = max(1, min(int(limit), 500))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "Keyword": query,
                "ResultsPerPage": normalized_limit,
                "Page": 1,
            },
            headers={
                "Accept": "application/json",
                "Host": "data.usajobs.gov",
                "User-Agent": user_agent,
                "Authorization-Key": api_key,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"USAJOBS search failed: {response.status_code} {response.text[:300]}") from exc

        items = (((response.json().get("SearchResult") or {}).get("SearchResultItems")) or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        descriptor = item.get("MatchedObjectDescriptor") or item
        salary = descriptor.get("PositionRemuneration") or []
        first_salary = salary[0] if salary else {}
        locations = descriptor.get("PositionLocation") or []
        organization = descriptor.get("OrganizationName") or descriptor.get("DepartmentName")
        return {
            "source_key": "usajobs_search",
            "name_zh": "USAJOBS 招聘薪酬",
            "source_type": "job_salary",
            "query": query,
            "rank": rank,
            "title": descriptor.get("PositionTitle", ""),
            "url": descriptor.get("PositionURI", ""),
            "snippet": descriptor.get("QualificationSummary", "") or descriptor.get("UserArea", {}).get("Details", {}).get("JobSummary", ""),
            "published_at": descriptor.get("PublicationStartDate"),
            "application_close_date": descriptor.get("ApplicationCloseDate"),
            "organization": organization,
            "department": descriptor.get("DepartmentName"),
            "salary_min": first_salary.get("MinimumRange"),
            "salary_max": first_salary.get("MaximumRange"),
            "salary_rate_interval": first_salary.get("RateIntervalCode"),
            "locations": [
                location.get("LocationName")
                for location in locations
                if location.get("LocationName")
            ][:8],
            "job_grade": descriptor.get("JobGrade"),
            "position_schedule": descriptor.get("PositionSchedule"),
        }


class USASpendingAwardSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        fiscal_years: list[int] | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.fiscal_years = fiscal_years or []
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        payload: dict[str, Any] = {
            "filters": {
                "keywords": [query],
                "award_type_codes": ["A", "B", "C", "D"],
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Start Date",
                "End Date",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Description",
                "Award Type",
            ],
            "page": 1,
            "limit": normalized_limit,
            "sort": "Award Amount",
            "order": "desc",
            "subawards": False,
        }
        if self.fiscal_years:
            payload["filters"]["time_period"] = [
                {
                    "start_date": f"{min(self.fiscal_years) - 1}-10-01",
                    "end_date": f"{max(self.fiscal_years)}-09-30",
                }
            ]

        import requests

        response = requests.post(
            self.endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"USAspending request failed: {response.status_code} {response.text[:300]}") from exc

        results = (response.json().get("results") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(results, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        award_id = item.get("Award ID") or item.get("generated_internal_id") or ""
        return {
            "source_key": "usaspending_awards",
            "name_zh": "USAspending 政府采购与拨款",
            "source_type": "procurement_awards",
            "query": query,
            "rank": rank,
            "title": f"{item.get('Recipient Name', '')} {item.get('Award Amount', '')}".strip(),
            "url": f"https://www.usaspending.gov/award/{award_id}" if award_id else "",
            "snippet": item.get("Description", ""),
            "published_at": item.get("Start Date"),
            "award_id": award_id,
            "recipient_name": item.get("Recipient Name"),
            "award_amount": item.get("Award Amount"),
            "start_date": item.get("Start Date"),
            "end_date": item.get("End Date"),
            "awarding_agency": item.get("Awarding Agency"),
            "awarding_sub_agency": item.get("Awarding Sub Agency"),
            "award_type": item.get("Award Type"),
        }


class SAMGovOpportunitySearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.sam.gov/opportunities/v2/search",
        api_key_env: str = "SAM_GOV_API_KEY",
        posted_from: str = "01/01/2025",
        posted_to: str = "12/31/2026",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.posted_from = posted_from
        self.posted_to = posted_to
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 1000))

        import requests

        response = requests.get(
            self.endpoint,
            params={
                "api_key": api_key,
                "title": query,
                "postedFrom": self.posted_from,
                "postedTo": self.posted_to,
                "limit": normalized_limit,
                "offset": 0,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SAM.gov opportunities request failed: {response.status_code} {response.text[:300]}") from exc

        items = (response.json().get("opportunitiesData") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(items, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        award = item.get("award") or {}
        awardee = award.get("awardee") or {}
        point_of_contact = item.get("pointOfContact") or []
        primary_contact = point_of_contact[0] if point_of_contact else {}
        place = item.get("placeOfPerformance") or {}
        office_address = item.get("officeAddress") or {}
        notice_id = item.get("noticeId") or ""
        url = item.get("uiLink")
        if not url or url == "null":
            url = f"https://sam.gov/opp/{notice_id}/view" if notice_id else "https://sam.gov/content/opportunities"
        return {
            "source_key": "sam_gov_opportunities",
            "name_zh": "SAM.gov 合同机会",
            "source_type": "procurement_opportunity",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": url,
            "snippet": item.get("description") or item.get("fullParentPathName") or "",
            "published_at": item.get("postedDate"),
            "notice_id": notice_id,
            "solicitation_number": item.get("solicitationNumber"),
            "opportunity_type": item.get("type"),
            "base_type": item.get("baseType"),
            "active": item.get("active"),
            "response_deadline": item.get("responseDeadLine"),
            "archive_type": item.get("archiveType"),
            "archive_date": item.get("archiveDate"),
            "set_aside": item.get("typeOfSetAsideDescription") or item.get("setAside"),
            "set_aside_code": item.get("typeOfSetAside") or item.get("setAsideCode"),
            "naics_code": item.get("naicsCode"),
            "classification_code": item.get("classificationCode"),
            "full_parent_path_name": item.get("fullParentPathName"),
            "full_parent_path_code": item.get("fullParentPathCode"),
            "organization_type": item.get("organizationType"),
            "office_city": office_address.get("city"),
            "office_state": office_address.get("state"),
            "office_zip": office_address.get("zipcode") or office_address.get("zip"),
            "place_of_performance_city": (place.get("city") or {}).get("name") if isinstance(place.get("city"), dict) else place.get("city"),
            "place_of_performance_state": (place.get("state") or {}).get("code") if isinstance(place.get("state"), dict) else place.get("state"),
            "place_of_performance_country": (place.get("country") or {}).get("code") if isinstance(place.get("country"), dict) else place.get("country"),
            "place_of_performance_zip": place.get("zip"),
            "award_number": award.get("number"),
            "award_amount": award.get("amount"),
            "award_date": award.get("date"),
            "awardee_name": awardee.get("name"),
            "awardee_uei_sam": awardee.get("ueiSAM"),
            "contact_name": primary_contact.get("fullName") or primary_contact.get("fullname"),
            "contact_email": primary_contact.get("email"),
            "contact_phone": primary_contact.get("phone"),
            "description_link": item.get("description"),
            "additional_info_link": item.get("additionalInfoLink"),
            "resource_links": item.get("resourceLinks") or [],
        }


class GrantsGovOpportunitySearchProvider:
    def __init__(
        self,
        endpoint: str = "https://api.grants.gov/v1/api/search2",
        opportunity_statuses: str = "forecasted|posted",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.opportunity_statuses = opportunity_statuses
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 1000))
        payload = {
            "rows": normalized_limit,
            "keyword": query,
            "oppStatuses": self.opportunity_statuses,
        }

        import requests

        response = requests.post(
            self.endpoint,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Grants.gov opportunity search failed: {response.status_code} {response.text[:300]}") from exc

        body = response.json()
        if body.get("errorcode") not in (None, 0):
            raise RuntimeError(f"Grants.gov opportunity search failed: {body.get('msg') or body.get('errorMsgs')}")
        hits = ((body.get("data") or {}).get("oppHits") or [])[:normalized_limit]
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(hits, start=1)
        ]

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        opportunity_id = item.get("id") or ""
        opportunity_number = item.get("number") or item.get("oppNum") or ""
        cfda_list = item.get("cfdaList") or item.get("alnist") or item.get("alnList") or []
        return {
            "source_key": "grants_gov_opportunities",
            "name_zh": "Grants.gov 资助机会",
            "source_type": "grant_opportunity",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": f"https://www.grants.gov/search-results-detail/{opportunity_id}" if opportunity_id else "https://www.grants.gov/search-grants",
            "snippet": f"{item.get('agency') or item.get('agencyName') or item.get('agencyCode') or ''} | {item.get('oppStatus') or ''}".strip(" |"),
            "published_at": item.get("openDate"),
            "opportunity_id": opportunity_id,
            "opportunity_number": opportunity_number,
            "agency_code": item.get("agencyCode"),
            "agency": item.get("agency") or item.get("agencyName"),
            "open_date": item.get("openDate"),
            "close_date": item.get("closeDate"),
            "opportunity_status": item.get("oppStatus"),
            "document_type": item.get("docType"),
            "cfda_list": cfda_list,
            "aln_list": cfda_list,
        }


class FREDSeriesSearchProvider:
    def __init__(
        self,
        search_endpoint: str = "https://api.stlouisfed.org/fred/series/search",
        observations_endpoint: str = "https://api.stlouisfed.org/fred/series/observations",
        api_key_env: str = "FRED_API_KEY",
        timeout_seconds: int = 20,
    ) -> None:
        self.search_endpoint = search_endpoint
        self.observations_endpoint = observations_endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required environment variable: {self.api_key_env}")

        normalized_limit = max(1, min(int(limit), 1000))

        import requests

        response = requests.get(
            self.search_endpoint,
            params={
                "api_key": api_key,
                "file_type": "json",
                "search_text": query,
                "limit": normalized_limit,
                "order_by": "search_rank",
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FRED series search failed: {response.status_code} {response.text[:300]}") from exc

        series_items = (response.json().get("seriess") or [])[:normalized_limit]
        return [
            self._to_result(
                query=query,
                rank=rank,
                item=item,
                latest_observation=self._latest_observation(api_key=api_key, series_id=str(item.get("id", ""))),
            )
            for rank, item in enumerate(series_items, start=1)
        ]

    def _latest_observation(self, api_key: str, series_id: str) -> dict[str, Any]:
        if not series_id:
            return {}

        import requests

        response = requests.get(
            self.observations_endpoint,
            params={
                "api_key": api_key,
                "file_type": "json",
                "series_id": series_id,
                "sort_order": "desc",
                "limit": 1,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"FRED observations request failed: {response.status_code} {response.text[:300]}") from exc
        observations = response.json().get("observations") or []
        return observations[0] if observations else {}

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any], latest_observation: dict[str, Any]) -> dict:
        series_id = item.get("id", "")
        return {
            "source_key": "fred_series_search",
            "name_zh": "FRED 宏观经济序列",
            "source_type": "macroeconomic_time_series",
            "query": query,
            "rank": rank,
            "title": item.get("title", ""),
            "url": f"https://fred.stlouisfed.org/series/{series_id}" if series_id else "https://fred.stlouisfed.org/",
            "snippet": item.get("notes", "") or item.get("units", ""),
            "published_at": latest_observation.get("date") or item.get("observation_end"),
            "series_id": series_id,
            "frequency": item.get("frequency"),
            "frequency_short": item.get("frequency_short"),
            "units": item.get("units"),
            "units_short": item.get("units_short"),
            "seasonal_adjustment": item.get("seasonal_adjustment"),
            "observation_start": item.get("observation_start"),
            "observation_end": item.get("observation_end"),
            "last_updated": item.get("last_updated"),
            "popularity": item.get("popularity"),
            "group_popularity": item.get("group_popularity"),
            "latest_date": latest_observation.get("date"),
            "latest_value": latest_observation.get("value"),
            "latest_realtime_start": latest_observation.get("realtime_start"),
            "latest_realtime_end": latest_observation.get("realtime_end"),
        }


class PatentsViewPatentSearchProvider:
    def __init__(
        self,
        endpoint: str = "https://search.patentsview.org/api/v1/patent/",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        fields = [
            "patent_id",
            "patent_title",
            "patent_date",
            "patent_abstract",
            "assignees.assignee_organization",
            "inventors.inventor_first_name",
            "inventors.inventor_last_name",
        ]
        params = {
            "q": json.dumps(self._query(query), separators=(",", ":")),
            "f": json.dumps(fields, separators=(",", ":")),
            "o": json.dumps({"size": normalized_limit}, separators=(",", ":")),
        }

        import requests

        try:
            response = requests.get(
                self.endpoint,
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            return [self._transition_result(query)]
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"PatentsView request failed: {response.status_code} {response.text[:300]}") from exc

        content_type = response.headers.get("content-type", "") if hasattr(response, "headers") else ""
        if response.status_code in {301, 302, 303, 307, 308} or "html" in content_type.casefold():
            return [self._transition_result(query)]
        try:
            payload = response.json()
        except ValueError:
            return [self._transition_result(query)]
        patents = payload.get("data") or payload.get("patents") or []
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(patents[:normalized_limit], start=1)
        ]

    @staticmethod
    def _query(query: str) -> dict[str, Any]:
        return {
            "_or": [
                {"_text_any": {"patent_title": query}},
                {"_text_any": {"patent_abstract": query}},
                {"_text_any": {"assignee_organization": query}},
            ]
        }

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        patent_number = str(item.get("patent_number") or item.get("patent_id") or "")
        assignees = item.get("assignees") or []
        inventors = item.get("inventors") or []
        assignee_names = [
            str(assignee.get("assignee_organization"))
            for assignee in assignees
            if assignee.get("assignee_organization")
        ]
        inventor_names = [
            " ".join(
                part
                for part in [
                    str(inventor.get("inventor_first_name") or ""),
                    str(inventor.get("inventor_last_name") or ""),
                ]
                if part
            )
            for inventor in inventors
        ]
        return {
            "source_key": "patentsview_patents",
            "name_zh": "PatentsView 专利",
            "source_type": "patent",
            "query": query,
            "rank": rank,
            "title": item.get("patent_title", ""),
            "url": f"https://patents.google.com/patent/US{patent_number}" if patent_number else "",
            "snippet": item.get("patent_abstract", ""),
            "published_at": item.get("patent_date"),
            "patent_number": patent_number,
            "assignees": assignee_names[:8],
            "inventors": [name for name in inventor_names if name][:8],
        }

    @staticmethod
    def _transition_result(query: str) -> dict:
        return {
            "source_key": "patentsview_patents",
            "name_zh": "PatentsView 专利",
            "source_type": "patent",
            "query": query,
            "rank": 1,
            "title": "PatentsView API migrated to USPTO Open Data Portal",
            "url": "https://data.uspto.gov/support/transition-guide/patentsview",
            "snippet": "PatentsView search APIs are temporarily unavailable during the USPTO Open Data Portal migration; use USPTO ODP downloads or the transition guide.",
            "published_at": "2026-03-20",
            "retrieval_status": "temporarily_unavailable",
            "patent_number": "",
            "assignees": [],
            "inventors": [],
        }


class OFACSanctionsListSearchProvider:
    def __init__(
        self,
        sdn_xml_url: str = "https://www.treasury.gov/ofac/downloads/sdn.xml",
        consolidated_xml_url: str = "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml",
        timeout_seconds: int = 30,
    ) -> None:
        self.sdn_xml_url = sdn_xml_url
        self.consolidated_xml_url = consolidated_xml_url
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized_limit = max(1, min(int(limit), 100))
        matches: list[dict[str, Any]] = []
        for list_name, url in [
            ("SDN", self.sdn_xml_url),
            ("Consolidated", self.consolidated_xml_url),
        ]:
            payload = self._download(url)
            matches.extend(self._search_xml(query=query, list_name=list_name, url=url, payload=payload))
            if len(matches) >= normalized_limit:
                break
        return [
            self._to_result(query=query, rank=rank, item=item)
            for rank, item in enumerate(matches[:normalized_limit], start=1)
        ]

    def _download(self, url: str) -> bytes:
        import requests

        response = requests.get(
            url,
            headers={"Accept": "application/xml,text/xml,*/*"},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"OFAC sanctions list request failed: {response.status_code} {response.text[:300]}") from exc
        return response.content

    def _search_xml(self, query: str, list_name: str, url: str, payload: bytes) -> list[dict[str, Any]]:
        tokens = [token.casefold() for token in SearchSourceCatalogProvider._tokens(query)]
        if not tokens:
            return []
        root = ElementTree.fromstring(payload)
        entries = [
            element
            for element in root.iter()
            if self._local_name(element.tag) in {"sdnEntry", "sanctionsEntry", "entity"}
        ]
        matches = []
        for entry in entries:
            haystack = " ".join(text.casefold() for text in entry.itertext() if text)
            if all(token in haystack for token in tokens):
                matches.append(self._entry_payload(entry=entry, list_name=list_name, source_url=url))
        return matches

    @classmethod
    def _entry_payload(cls, entry: ElementTree.Element, list_name: str, source_url: str) -> dict[str, Any]:
        names = [
            text
            for tag in ("firstName", "lastName", "name", "sdnName")
            for text in cls._texts(entry, tag)
        ]
        programs = cls._texts(entry, "program")
        aliases = [
            " ".join(part for part in [first, last] if part)
            for first, last in zip(cls._texts(entry, "firstName"), cls._texts(entry, "lastName"))
        ]
        entity_type = cls._first_text(entry, "sdnType") or cls._first_text(entry, "type")
        uid = cls._first_text(entry, "uid") or cls._first_text(entry, "id")
        return {
            "uid": uid,
            "list_name": list_name,
            "name": " ".join(names[:2]).strip() or cls._first_non_empty(entry),
            "entity_type": entity_type,
            "programs": programs[:8],
            "aliases": [alias for alias in aliases if alias][:8],
            "source_url": source_url,
        }

    @staticmethod
    def _to_result(query: str, rank: int, item: dict[str, Any]) -> dict:
        name = item.get("name", "")
        return {
            "source_key": "ofac_sanctions_lists",
            "name_zh": "OFAC 制裁清单",
            "source_type": "sanctions",
            "query": query,
            "rank": rank,
            "title": name,
            "url": item.get("source_url", ""),
            "snippet": f"{item.get('list_name', '')} {item.get('entity_type', '')}".strip(),
            "published_at": None,
            "uid": item.get("uid"),
            "list_name": item.get("list_name"),
            "entity_type": item.get("entity_type"),
            "programs": item.get("programs", []),
            "aliases": item.get("aliases", []),
        }

    @classmethod
    def _texts(cls, element: ElementTree.Element, tag_name: str) -> list[str]:
        values = []
        for child in element.iter():
            if cls._local_name(child.tag) == tag_name and child.text and child.text.strip():
                values.append(child.text.strip())
        return values

    @classmethod
    def _first_text(cls, element: ElementTree.Element, tag_name: str) -> str | None:
        values = cls._texts(element, tag_name)
        return values[0] if values else None

    @staticmethod
    def _first_non_empty(element: ElementTree.Element) -> str:
        for text in element.itertext():
            if text and text.strip():
                return text.strip()
        return ""

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]


class DueDiligenceFederatedSearchProvider:
    """Compliance-first intelligence search across source planning and live web."""

    def __init__(
        self,
        source_catalog: SearchSourceCatalogProvider,
        web_search: SearchProviderProtocol | None = None,
        live_searches: list[SearchProviderProtocol] | None = None,
        web_enabled_by_default: bool = False,
        live_enabled_by_default: bool = False,
    ) -> None:
        self.source_catalog = source_catalog
        self.web_search = web_search
        self.live_searches = live_searches or []
        self.web_enabled_by_default = web_enabled_by_default
        self.live_enabled_by_default = live_enabled_by_default

    def search(self, query: str, limit: int = 10) -> list[dict]:
        normalized_limit = max(1, int(limit))
        catalog_limit = max(8, normalized_limit)
        results = [
            {
                **source,
                "source_key": f"catalog:{source['source_key']}",
                "source_type": "source_catalog",
                "retrieval_status": "planned",
                "retrieved_at": self._now(),
            }
            for source in self.source_catalog.search(query, limit=catalog_limit)
        ]

        if self.web_search and self.web_enabled_by_default:
            results.extend(self._safe_web_results(query, max(1, normalized_limit - len(results))))
        if self.live_searches and self.live_enabled_by_default:
            results.extend(self._safe_live_results(query, max(1, normalized_limit - len(results))))

        return results[:normalized_limit]

    def plan(self, query: str, limit: int = 12) -> dict:
        source_plan = self.source_catalog.plan(query, limit=limit)
        registered_live_sources = self._registered_live_sources()
        coverage = self._coverage_matrix(source_plan["recommended_sources"] + registered_live_sources)
        return {
            "query": query,
            "mode": "financial_due_diligence_intelligence",
            "recommended_sources": source_plan["recommended_sources"],
            "registered_live_sources": registered_live_sources,
            "coverage_matrix": coverage,
            "search_phases": [
                {
                    "phase": "market_map",
                    "goal": "确认赛道、公司、融资、竞品和二级市场披露信号。",
                    "source_types": ["regulatory_filings", "news_media", "business_databases", "market_data"],
                },
                {
                    "phase": "technical_depth",
                    "goal": "追踪论文、专利、代码、模型、Demo、会议和技术路线变化。",
                    "source_types": ["academic", "patents", "code", "model_hubs", "video_demo"],
                },
                {
                    "phase": "people_network",
                    "goal": "定位公开职业履历、作者网络、发明人网络、团队流动和招聘需求。",
                    "source_types": ["professional_profile", "recruiting", "conference", "community"],
                },
                {
                    "phase": "evidence_review",
                    "goal": "按来源质量、新鲜度、冲突证据和合规边界做交叉验证。",
                    "source_types": ["primary_source", "secondary_source", "human_review"],
                },
                {
                    "phase": "compliance_risk",
                    "goal": "筛查制裁、监管处罚、诉讼、出口管制和交易限制风险。",
                    "source_types": ["sanctions", "litigation", "regulatory_enforcement", "export_control"],
                },
                {
                    "phase": "operational_risk",
                    "goal": "筛查产品召回、质量事件、环境合规、客户投诉和供应链/贸易暴露。",
                    "source_types": [
                        "product_safety_recall",
                        "fda_enforcement_recall",
                        "consumer_finance_complaint",
                        "vehicle_safety_recall",
                        "environmental_compliance",
                        "trade_flows",
                    ],
                },
                {
                    "phase": "governance_and_contracts",
                    "goal": "追踪内部人交易、重大持股、政府合同、采购拨款和临床/产品验证里程碑。",
                    "source_types": [
                        "insider_transactions",
                        "ownership_activism",
                        "procurement_awards",
                        "clinical_trial_registry",
                        "healthcare_payments",
                    ],
                },
            ],
            "query_templates": self._query_templates(query),
            "evidence_rules": [
                "每条结论至少保留 URL/文件名、发布时间、检索时间、来源类型和验证状态。",
                "关键投资/招聘结论至少需要两个独立来源，优先官方披露、监管文件、论文/专利、公司官网。",
                "区分事实、推断和建议；对传闻、社区讨论、二手媒体默认标记为待验证。",
                "个人信息仅限公开职业信息和与岗位评估直接相关的能力证据。",
            ],
            "guardrails": source_plan["guardrails"]
            + [
                "不绕过登录、付费墙、robots.txt、反爬、访问控制或数据授权限制。",
                "不采集非公开个人敏感信息，不做骚扰式触达或批量画像滥用。",
            ],
        }

    def evidence(self, query: str, limit: int = 12, claim: str | None = None) -> dict:
        records = [
            self._to_evidence_record(query=query, result=result, claim=claim)
            for result in self.search(query, limit=limit)
        ]
        by_validation: dict[str, int] = {}
        by_source_tier: dict[str, int] = {}
        for record in records:
            by_validation[record["validation_status"]] = by_validation.get(record["validation_status"], 0) + 1
            by_source_tier[record["source_tier"]] = by_source_tier.get(record["source_tier"], 0) + 1

        return {
            "query": query,
            "claim": claim,
            "records": records,
            "review": {
                "record_count": len(records),
                "validation_status_counts": by_validation,
                "source_tier_counts": by_source_tier,
                "cross_check_status": self._cross_check_status(records),
                "minimum_standard": "关键结论至少需要两个独立来源，其中至少一个优先级来源应为官方披露、监管文件、论文/专利、公司官网或授权数据库。",
                "next_actions": self._next_actions(records),
            },
            "guardrails": [
                "证据记录只代表检索候选，不等于事实结论。",
                "引用前必须人工或模型复核原文、日期、主体名称和上下文。",
                "个人相关记录只允许用于职业能力和公开经历验证，不扩展到敏感或非公开信息。",
            ],
        }

    def brief(self, query: str, limit: int = 12, claim: str | None = None) -> dict:
        plan = self.plan(query, limit=limit)
        evidence = self.evidence(query, limit=limit, claim=claim)
        records = evidence["records"]
        top_records = sorted(records, key=lambda record: (-float(record["confidence"]), record["source_key"]))[:5]
        return {
            "query": query,
            "claim": claim,
            "brief_type": "financial_due_diligence_intelligence_brief",
            "generated_at": self._now(),
            "executive_summary": self._executive_summary(evidence),
            "coverage_matrix": plan["coverage_matrix"],
            "evidence_review": evidence["review"],
            "priority_evidence": [
                {
                    "record_id": record["record_id"],
                    "source_key": record["source_key"],
                    "source_name": record["source_name"],
                    "source_tier": record["source_tier"],
                    "validation_status": record["validation_status"],
                    "confidence": record["confidence"],
                    "snippet": record["snippet"],
                }
                for record in top_records
            ],
            "risk_register": self._risk_register(records),
            "intelligence_gaps": self._intelligence_gaps(plan, evidence),
            "next_search_actions": self._brief_next_search_actions(plan, evidence),
            "report_guardrails": [
                "该简报是检索与证据工作台输出，不是投资建议、法律意见或事实最终认定。",
                "所有关键判断必须回看原始来源，并记录证据引用位置、日期、主体和可引用范围。",
                "涉及个人和候选人时，仅允许使用公开职业信息和岗位相关能力证据。",
            ],
        }

    def _safe_web_results(self, query: str, limit: int) -> list[dict]:
        if not self.web_search or limit <= 0:
            return []
        try:
            web_results = self.web_search.search(query, limit=limit)
        except RuntimeError as exc:
            return [
                {
                    "source_key": "brave_web_search",
                    "source_type": "open_web",
                    "retrieval_status": "skipped",
                    "reason": str(exc),
                    "query": query,
                    "retrieved_at": self._now(),
                }
            ]
        return [
            {
                **result,
                "retrieval_status": "retrieved",
                "retrieved_at": self._now(),
            }
            for result in web_results
        ]

    def _safe_live_results(self, query: str, limit: int) -> list[dict]:
        if limit <= 0:
            return []
        per_source_limit = max(1, limit // max(1, len(self.live_searches)))
        results = []
        for provider in self.live_searches:
            try:
                provider_results = provider.search(query, limit=per_source_limit)
            except RuntimeError as exc:
                results.append(
                    {
                        "source_key": provider.__class__.__name__,
                        "source_type": "live_source",
                        "retrieval_status": "skipped",
                        "reason": str(exc),
                        "query": query,
                        "retrieved_at": self._now(),
                    }
                )
                continue
            results.extend(
                {
                    **result,
                    "retrieval_status": result.get("retrieval_status", "retrieved"),
                    "retrieved_at": self._now(),
                }
                for result in provider_results
            )
        return results[:limit]

    def _to_evidence_record(self, query: str, result: dict[str, Any], claim: str | None) -> dict:
        source_key = str(result.get("source_key", "unknown")).removeprefix("catalog:")
        title = str(result.get("title") or result.get("name_zh") or source_key)
        url = str(result.get("url") or "")
        retrieved_at = str(result.get("retrieved_at") or self._now())
        record_id = self._record_id(query=query, source_key=source_key, title=title, url=url)
        source_tier = self._source_tier(result)
        return {
            "record_id": record_id,
            "query": query,
            "claim": claim,
            "source_key": source_key,
            "source_name": title,
            "source_type": result.get("source_type", "source_catalog"),
            "source_tier": source_tier,
            "url": url or None,
            "title": title,
            "snippet": result.get("snippet") or result.get("description") or result.get("purpose") or "",
            "published_at": result.get("published_at"),
            "retrieved_at": retrieved_at,
            "freshness": result.get("freshness"),
            "risk_level": result.get("risk_level"),
            "validation_status": self._validation_status(result, source_tier),
            "confidence": self._confidence(result, source_tier),
            "signals": result.get("talent_signals", []),
            "access_pattern": result.get("access_pattern"),
            "compliance_notes": self._compliance_notes(result),
        }

    @staticmethod
    def _record_id(query: str, source_key: str, title: str, url: str) -> str:
        digest = sha256("|".join([query, source_key, title, url]).encode("utf-8")).hexdigest()[:16]
        return f"ev_{digest}"

    @staticmethod
    def _source_tier(result: dict[str, Any]) -> str:
        source_key = str(result.get("source_key", "")).removeprefix("catalog:")
        source_type = str(result.get("source_type", ""))
        purpose = str(result.get("purpose", "")).casefold()
        if source_key in {
            "regulatory_filings_global",
            "filings_annual_reports",
            "company_websites",
            "patent_databases",
            "conference_paper_lists",
            "scholar_arxiv",
            "openalex_works_search",
            "sec_edgar_company_filings",
            "patentsview_patents",
            "ofac_sanctions_lists",
            "github_repositories",
            "huggingface_models",
            "companies_house_search",
            "courtlistener_search",
            "sec_company_facts",
            "sec_insider_transactions",
            "sec_ownership_activism",
            "sec_investment_adviser_reports",
            "fdic_bankfind_institutions",
            "federal_register_documents",
            "cpsc_recalls",
            "fda_enforcement_recalls",
            "fda_device_510k",
            "fda_device_events",
            "fda_device_classification",
            "fda_device_registration_listing",
            "cfpb_consumer_complaints",
            "nhtsa_recalls",
            "epa_echo_facilities",
            "clinicaltrials_studies",
            "cms_openpayments",
            "census_international_trade",
            "fred_series_search",
            "gnews_funding_news",
            "sec_enforcement_search",
            "usajobs_search",
            "procurement_tenders",
            "sam_gov_opportunities",
            "grants_gov_opportunities",
            "standards_certifications",
            "datasets_benchmarks",
            "github_candidates",
            "github_users",
            "github_code",
            "github_topics",
        }:
            return "primary_or_authoritative"
        if source_key in {
            "funding_private_market",
            "business_databases_cn",
            "market_data_secondary",
            "pdl_people_search",
            "crustdata_signal_search",
            "earnings_calls_transcripts",
            "supply_chain_import_export",
            "job_salary_labor_market",
            "app_traffic_product_analytics",
        }:
            return "licensed_or_structured_database"
        if source_type in {"open_web", "academic", "regulatory_filings", "patent", "sanctions", "code_repository", "code_search", "code_topic", "developer_profile", "model_repository", "company_registry", "litigation", "financial_facts", "investment_adviser_registry", "financial_institution_registry", "insider_transactions", "ownership_activism", "regulatory_policy", "product_safety_recall", "fda_enforcement_recall", "fda_device_clearance", "fda_device_adverse_event", "fda_device_classification", "fda_device_registration_listing", "consumer_finance_complaint", "vehicle_safety_recall", "environmental_compliance", "clinical_trial_registry", "healthcare_payments", "trade_flows", "macroeconomic_time_series", "funding_news", "regulatory_enforcement", "job_salary", "identity_enrichment", "market_signal", "social_platform_search", "adaptive_web_scraping", "browser_automation", "supervised_browser_operation", "chrome_cdp_web_access"}:
            return "primary_or_authoritative" if source_type in {"academic", "regulatory_filings", "patent", "sanctions", "code_repository", "code_search", "code_topic", "developer_profile", "model_repository", "company_registry", "litigation", "financial_facts", "investment_adviser_registry", "financial_institution_registry", "insider_transactions", "ownership_activism", "regulatory_policy", "product_safety_recall", "fda_enforcement_recall", "fda_device_clearance", "fda_device_adverse_event", "fda_device_classification", "fda_device_registration_listing", "consumer_finance_complaint", "vehicle_safety_recall", "environmental_compliance", "clinical_trial_registry", "healthcare_payments", "trade_flows", "macroeconomic_time_series", "regulatory_enforcement"} else "secondary_or_open_web"
        if any(token in purpose for token in ("新闻", "媒体", "社区", "论坛")):
            return "secondary_or_open_web"
        if source_key == "expert_network_interviews":
            return "human_research"
        return "source_catalog"

    @staticmethod
    def _validation_status(result: dict[str, Any], source_tier: str) -> str:
        if result.get("retrieval_status") == "retrieved" and result.get("url"):
            return "single_source"
        if source_tier in {"primary_or_authoritative", "licensed_or_structured_database"}:
            return "planned_authoritative_source"
        if source_tier == "human_research":
            return "requires_interview_confirmation"
        return "planned_unverified"

    @staticmethod
    def _confidence(result: dict[str, Any], source_tier: str) -> float:
        base_by_tier = {
            "primary_or_authoritative": 0.72,
            "licensed_or_structured_database": 0.64,
            "human_research": 0.56,
            "secondary_or_open_web": 0.48,
            "source_catalog": 0.4,
        }
        base = base_by_tier.get(source_tier, 0.4)
        if result.get("retrieval_status") == "retrieved" and result.get("url"):
            base += 0.12
        if result.get("risk_level") == "high":
            base -= 0.08
        return round(max(0.1, min(base, 0.95)), 2)

    @staticmethod
    def _compliance_notes(result: dict[str, Any]) -> list[str]:
        notes = ["保留来源、检索时间和验证状态。"]
        if result.get("risk_level") == "high":
            notes.append("高合规风险来源：必须使用授权账号、官方 API、人工导出或用户提供材料。")
        if result.get("source_type") == "open_web":
            notes.append("开放网页结果需回看原文并交叉验证。")
        if result.get("access_pattern"):
            notes.append(str(result["access_pattern"]))
        return notes

    @staticmethod
    def _cross_check_status(records: list[dict[str, Any]]) -> str:
        authoritative = [record for record in records if record["source_tier"] == "primary_or_authoritative"]
        independent_sources = {record["source_key"] for record in records}
        if len(independent_sources) >= 2 and authoritative:
            return "ready_for_human_review"
        if len(independent_sources) >= 2:
            return "needs_authoritative_source"
        if records:
            return "single_source_only"
        return "no_evidence"

    @staticmethod
    def _next_actions(records: list[dict[str, Any]]) -> list[str]:
        tiers = {record["source_tier"] for record in records}
        actions = []
        if "primary_or_authoritative" not in tiers:
            actions.append("补充监管披露、公司官网、论文/专利、招投标或标准认证等权威来源。")
        if "licensed_or_structured_database" not in tiers:
            actions.append("补充授权金融/工商/融资/薪酬/流量数据库记录，并标注数据口径。")
        if "secondary_or_open_web" not in tiers:
            actions.append("补充新闻、开放网页或社区信号，用于发现线索但不单独下结论。")
        if not actions:
            actions.append("进入人工复核：核对原文、主体、日期、冲突证据和可引用范围。")
        return actions

    @staticmethod
    def _executive_summary(evidence: dict[str, Any]) -> dict[str, Any]:
        review = evidence["review"]
        status = review["cross_check_status"]
        if status == "ready_for_human_review":
            conclusion = "已有至少两个独立来源且包含权威来源，可进入人工复核和原文核验。"
        elif status == "needs_authoritative_source":
            conclusion = "已有多个线索来源，但缺少权威来源，不能用于关键结论。"
        elif status == "single_source_only":
            conclusion = "当前只有单一来源线索，必须扩展来源后再判断。"
        else:
            conclusion = "当前没有可用证据记录。"
        return {
            "status": status,
            "conclusion": conclusion,
            "record_count": review["record_count"],
            "source_tier_counts": review["source_tier_counts"],
            "validation_status_counts": review["validation_status_counts"],
        }

    @staticmethod
    def _risk_register(records: list[dict[str, Any]]) -> list[dict[str, str]]:
        risks: list[dict[str, str]] = []
        if any(record.get("risk_level") == "high" for record in records):
            risks.append(
                {
                    "risk": "high_compliance_source",
                    "severity": "high",
                    "mitigation": "仅使用授权 API、授权账号、人工导出或用户提供材料；不得绕过访问控制。",
                }
            )
        if any(record["validation_status"] == "planned_unverified" for record in records):
            risks.append(
                {
                    "risk": "unverified_planned_sources",
                    "severity": "medium",
                    "mitigation": "把 planned 来源转成真实原文证据后再用于判断。",
                }
            )
        if not any(record["source_tier"] == "primary_or_authoritative" for record in records):
            risks.append(
                {
                    "risk": "missing_authoritative_source",
                    "severity": "high",
                    "mitigation": "补充监管披露、公司官网、论文、专利、招投标或标准认证来源。",
                }
            )
        if not risks:
            risks.append(
                {
                    "risk": "human_review_required",
                    "severity": "medium",
                    "mitigation": "进入人工复核，核对原文、日期、主体、上下文和冲突证据。",
                }
            )
        return risks

    @staticmethod
    def _intelligence_gaps(plan: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
        gaps = []
        coverage = plan["coverage_matrix"]
        review = evidence["review"]
        if not coverage["primary_disclosure"]:
            gaps.append("缺少监管披露、公告、招股书、年报或公司一手材料。")
        if not coverage["market_and_funding"]:
            gaps.append("缺少融资、股权、估值、薪酬或二级市场结构化数据。")
        if not coverage["macro_market_context"]:
            gaps.append("缺少利率、通胀、失业率、收益率曲线、信用利差或宏观周期线索。")
        if not coverage["non_dilutive_funding"]:
            gaps.append("缺少 Grants.gov、SBIR/STTR、政府拨款或非稀释资金机会线索。")
        if not coverage["technical_evidence"]:
            gaps.append("缺少论文、专利、代码、模型、Demo 或 benchmark 技术证据。")
        if not coverage["regulatory_enforcement"]:
            gaps.append("缺少制裁、诉讼、SEC 执法、监管政策或处罚记录筛查。")
        if not coverage["product_quality_safety"]:
            gaps.append("缺少产品召回、FDA enforcement、车辆安全、客户投诉或质量风险线索。")
        if not coverage["ownership_governance"]:
            gaps.append("缺少内部人交易、重大持股、控制权、减持或公司注册治理线索。")
        if not coverage["investment_adviser_due_diligence"]:
            gaps.append("缺少投顾/ERA、Form ADV、IAPD、资产管理业务或私募管理人监管身份线索。")
        if not coverage["financial_institution_risk"]:
            gaps.append("缺少银行/存款机构身份、FDIC certificate、监管机构、资产、存款或盈利质量线索。")
        if not coverage["environmental_supply_chain"]:
            gaps.append("缺少环境合规、贸易流、供应链暴露或设施层面风险线索。")
        if not coverage["clinical_validation"]:
            gaps.append("缺少临床试验、产品验证或监管产品管线证据。")
        if not coverage["healthcare_commercial_relationships"]:
            gaps.append("缺少药械/医药公司向医生、教学医院或研究相关方的付款和权益关系线索。")
        if not coverage["government_procurement"]:
            gaps.append("缺少政府采购、拨款、合同或公共部门需求信号。")
        if review["cross_check_status"] != "ready_for_human_review":
            gaps.append("尚未满足关键结论的双来源与权威来源交叉验证标准。")
        if not gaps:
            gaps.append("暂无结构性缺口；下一步重点是原文核验、冲突证据和人工判断。")
        return gaps

    @staticmethod
    def _brief_next_search_actions(plan: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, Any]]:
        actions = [
            {
                "action": "verify_priority_evidence",
                "owner": "researcher",
                "description": "打开优先证据原文，核对主体、日期、上下文、可引用范围和冲突证据。",
            }
        ]
        for query_template in plan["query_templates"][:4]:
            actions.append(
                {
                    "action": "run_query_template",
                    "owner": "search_agent",
                    "query": query_template,
                    "description": "用模板补齐跨市场、跨来源检索覆盖。",
                }
            )
        for next_action in evidence["review"]["next_actions"]:
            actions.append(
                {
                    "action": "close_evidence_gap",
                    "owner": "researcher",
                    "description": next_action,
                }
            )
        return actions

    @staticmethod
    def _coverage_matrix(sources: list[dict]) -> dict[str, list[str]]:
        matrix: dict[str, list[str]] = {
            "primary_disclosure": [],
            "market_and_funding": [],
            "macro_market_context": [],
            "non_dilutive_funding": [],
            "technical_evidence": [],
            "people_and_hiring": [],
            "community_signal": [],
            "regulatory_enforcement": [],
            "product_quality_safety": [],
            "ownership_governance": [],
            "investment_adviser_due_diligence": [],
            "financial_institution_risk": [],
            "environmental_supply_chain": [],
            "clinical_validation": [],
            "healthcare_commercial_relationships": [],
            "government_procurement": [],
        }
        key_buckets = {
            "primary_disclosure": {
                "regulatory_filings_global",
                "filings_annual_reports",
                "company_websites",
                "sec_edgar_company_filings",
                "sec_company_facts",
                "sec_investment_adviser_reports",
                "federal_register_documents",
            },
            "market_and_funding": {
                "funding_private_market",
                "business_databases_cn",
                "market_data_secondary",
                "earnings_calls_transcripts",
                "census_international_trade",
                "fdic_bankfind_institutions",
                "sec_investment_adviser_reports",
                "fred_series_search",
                "gnews_funding_news",
                "grants_gov_opportunities",
            },
            "macro_market_context": {
                "fred_series_search",
                "census_international_trade",
            },
            "non_dilutive_funding": {
                "grants_gov_opportunities",
                "usaspending_awards",
                "sam_gov_opportunities",
            },
            "technical_evidence": {
                "patent_databases",
                "conference_paper_lists",
                "scholar_arxiv",
                "datasets_benchmarks",
                "openalex_works_search",
                "patentsview_patents",
                "github_candidates",
                "github_users",
                "github_repositories",
                "github_code",
                "github_topics",
                "huggingface_models",
                "scrapling_adaptive_scrape",
            },
            "people_and_hiring": {
                "recruitment_boards_cn",
                "professional_profiles",
                "job_salary_labor_market",
                "usajobs_search",
                "agent_reach_social_search",
                "browser_use_agent_search",
                "claude_chrome_supervised_search",
                "web_access_cdp_search",
            },
            "community_signal": {
                "developer_communities",
                "ai_communities",
                "gdelt_doc_news",
                "brave_web_search",
                "agent_reach_social_search",
                "scrapling_adaptive_scrape",
                "browser_use_agent_search",
                "claude_chrome_supervised_search",
                "web_access_cdp_search",
            },
            "regulatory_enforcement": {
                "ofac_sanctions_lists",
                "courtlistener_search",
                "sec_enforcement_search",
                "fdic_bankfind_institutions",
                "sec_investment_adviser_reports",
                "federal_register_documents",
                "cfpb_consumer_complaints",
            },
            "product_quality_safety": {
                "cpsc_recalls",
                "fda_enforcement_recalls",
                "fda_device_510k",
                "fda_device_events",
                "fda_device_classification",
                "fda_device_registration_listing",
                "cfpb_consumer_complaints",
                "nhtsa_recalls",
            },
            "ownership_governance": {
                "companies_house_search",
                "fdic_bankfind_institutions",
                "sec_investment_adviser_reports",
                "sec_insider_transactions",
                "sec_ownership_activism",
                "sec_company_facts",
            },
            "investment_adviser_due_diligence": {
                "sec_investment_adviser_reports",
                "sec_enforcement_search",
                "courtlistener_search",
            },
            "financial_institution_risk": {
                "fdic_bankfind_institutions",
                "sec_investment_adviser_reports",
                "cfpb_consumer_complaints",
                "sec_company_facts",
                "sec_enforcement_search",
            },
            "environmental_supply_chain": {
                "epa_echo_facilities",
                "census_international_trade",
                "fda_device_registration_listing",
                "supply_chain_import_export",
            },
            "clinical_validation": {
                "clinicaltrials_studies",
                "fda_device_510k",
                "fda_device_classification",
                "fda_device_registration_listing",
            },
            "healthcare_commercial_relationships": {
                "cms_openpayments",
            },
            "government_procurement": {
                "procurement_tenders",
                "usaspending_awards",
                "sam_gov_opportunities",
                "grants_gov_opportunities",
            },
        }
        type_buckets = {
            "primary_disclosure": {"regulatory_filings", "financial_facts", "investment_adviser_registry", "financial_institution_registry", "regulatory_policy"},
            "market_and_funding": {"market_data", "investment_adviser_registry", "financial_institution_registry", "trade_flows", "macroeconomic_time_series", "funding_news", "grant_opportunity"},
            "macro_market_context": {"macroeconomic_time_series", "trade_flows"},
            "non_dilutive_funding": {"grant_opportunity", "procurement_awards", "procurement_opportunity"},
            "technical_evidence": {"academic", "patent", "code_repository", "code_search", "code_topic", "developer_profile", "model_repository", "adaptive_web_scraping"},
            "people_and_hiring": {"professional_profile", "developer_profile", "recruiting", "job_salary", "social_platform_search", "browser_automation", "supervised_browser_operation", "chrome_cdp_web_access"},
            "community_signal": {"community", "news_media", "open_web", "social_platform_search", "adaptive_web_scraping", "browser_automation", "supervised_browser_operation", "chrome_cdp_web_access"},
            "regulatory_enforcement": {
                "sanctions",
                "litigation",
                "regulatory_enforcement",
                "regulatory_policy",
                "consumer_finance_complaint",
                "financial_institution_registry",
                "investment_adviser_registry",
            },
            "product_quality_safety": {
                "product_safety_recall",
                "fda_enforcement_recall",
                "fda_device_clearance",
                "fda_device_adverse_event",
                "fda_device_classification",
                "fda_device_registration_listing",
                "consumer_finance_complaint",
                "vehicle_safety_recall",
            },
            "ownership_governance": {"company_registry", "investment_adviser_registry", "financial_institution_registry", "insider_transactions", "ownership_activism"},
            "investment_adviser_due_diligence": {"investment_adviser_registry", "regulatory_enforcement", "litigation"},
            "financial_institution_risk": {"financial_institution_registry", "investment_adviser_registry", "consumer_finance_complaint", "financial_facts"},
            "environmental_supply_chain": {"environmental_compliance", "trade_flows", "fda_device_registration_listing"},
            "clinical_validation": {"clinical_trial_registry", "fda_device_clearance", "fda_device_classification", "fda_device_registration_listing"},
            "healthcare_commercial_relationships": {"healthcare_payments"},
            "government_procurement": {"procurement_awards", "procurement_opportunity", "grant_opportunity", "procurement"},
        }
        for source in sources:
            key = str(source["source_key"])
            source_type = str(source.get("source_type", ""))
            haystack = " ".join(
                [
                    key,
                    source_type,
                    str(source.get("name_zh", "")),
                    str(source.get("purpose", "")),
                    " ".join(str(item) for item in source.get("source_names", [])),
                    " ".join(str(item) for item in source.get("talent_signals", [])),
                ]
            ).casefold()
            for bucket, keys in key_buckets.items():
                if key in keys:
                    matrix[bucket].append(key)
            for bucket, source_types in type_buckets.items():
                if source_type in source_types and key not in matrix[bucket]:
                    matrix[bucket].append(key)
            if any(token in haystack for token in ("sec", "年报", "招股书", "披露", "监管", "公告")):
                if key not in matrix["primary_disclosure"]:
                    matrix["primary_disclosure"].append(key)
            if any(token in haystack for token in ("融资", "股权", "市场", "薪酬", "交易", "funding")):
                if key not in matrix["market_and_funding"]:
                    matrix["market_and_funding"].append(key)
            if any(token in haystack for token in ("fred", "macro", "macroeconomic", "interest rate", "inflation", "cpi", "unemployment", "yield curve", "credit spread", "gdp", "宏观", "利率", "通胀", "失业率", "收益率曲线")):
                if key not in matrix["macro_market_context"]:
                    matrix["macro_market_context"].append(key)
            if any(token in haystack for token in ("grant", "grants.gov", "sbir", "sttr", "non-dilutive", "non dilutive", "cfda", "aln", "资助", "补助", "拨款", "非稀释")):
                if key not in matrix["non_dilutive_funding"]:
                    matrix["non_dilutive_funding"].append(key)
            if any(token in haystack for token in ("论文", "专利", "代码", "模型", "demo", "技术")):
                if key not in matrix["technical_evidence"]:
                    matrix["technical_evidence"].append(key)
            if any(token in haystack for token in ("候选人", "履历", "招聘", "作者", "发明人", "团队")):
                if key not in matrix["people_and_hiring"]:
                    matrix["people_and_hiring"].append(key)
            if any(token in haystack for token in ("社区", "论坛", "讨论", "reddit", "知乎", "小红书", "抖音", "youtube", "x/twitter", "browser", "chrome", "scraping", "crawl", "抓取")):
                if key not in matrix["community_signal"]:
                    matrix["community_signal"].append(key)
            if any(token in haystack for token in ("sanction", "ofac", "诉讼", "处罚", "执法", "enforcement", "litigation")):
                if key not in matrix["regulatory_enforcement"]:
                    matrix["regulatory_enforcement"].append(key)
            if any(token in haystack for token in ("recall", "召回", "hazard", "fda", "510(k)", "510k", "clearance", "classification", "registration", "listing", "fei", "establishment", "product code", "device class", "adverse event", "maude", "malfunction", "injury", "death", "nhtsa", "complaint", "质量", "安全", "准入", "分类", "注册", "列名", "产品代码", "不良事件", "故障", "伤害")):
                if key not in matrix["product_quality_safety"]:
                    matrix["product_quality_safety"].append(key)
            if any(token in haystack for token in ("insider", "ownership", "13d", "13g", "13f", "form 4", "公司注册", "控制权", "持股")):
                if key not in matrix["ownership_governance"]:
                    matrix["ownership_governance"].append(key)
            if any(token in haystack for token in ("investment adviser", "form adv", "iapd", "era", "exempt reporting adviser", "aum", "投顾", "投资顾问", "私募管理人", "资产管理")):
                if key not in matrix["investment_adviser_due_diligence"]:
                    matrix["investment_adviser_due_diligence"].append(key)
            if any(token in haystack for token in ("fdic", "bank", "depository", "deposit", "certificate", "bankfind", "银行", "存款", "金融机构", "监管机构")):
                if key not in matrix["financial_institution_risk"]:
                    matrix["financial_institution_risk"].append(key)
            if any(token in haystack for token in ("environment", "epa", "echo", "trade", "import", "export", "supply chain", "facility", "establishment", "fei", "registered facility", "环境", "贸易", "供应链", "设施", "工厂")):
                if key not in matrix["environmental_supply_chain"]:
                    matrix["environmental_supply_chain"].append(key)
            if any(token in haystack for token in ("clinical", "trial", "nct", "510(k)", "510k", "clearance", "classification", "registration", "listing", "product code", "device class", "substantially equivalent", "临床", "试验", "器械准入", "器械分类", "器械注册")):
                if key not in matrix["clinical_validation"]:
                    matrix["clinical_validation"].append(key)
            if any(token in haystack for token in ("open payments", "cms", "payment", "transfer of value", "ownership interest", "physician payment", "医疗付款", "医生付款", "权益关系")):
                if key not in matrix["healthcare_commercial_relationships"]:
                    matrix["healthcare_commercial_relationships"].append(key)
            if any(token in haystack for token in ("procurement", "award", "contract", "grant", "grants.gov", "solicitation", "rfp", "rfq", "sam.gov", "sources sought", "采购", "招标", "合同", "拨款")):
                if key not in matrix["government_procurement"]:
                    matrix["government_procurement"].append(key)
        return matrix

    @staticmethod
    def _query_templates(query: str) -> list[str]:
        return [
            f'"{query}" site:sec.gov OR site:hkexnews.hk OR site:cninfo.com.cn',
            f'"{query}" site:sec.gov Form 4 OR 13D OR 13G OR 13F',
            f'"{query}" Form ADV OR IAPD OR investment adviser OR exempt reporting adviser',
            f'"{query}" enforcement OR litigation OR sanctions OR OFAC OR penalty',
            f'"{query}" FDIC BankFind OR bank certificate OR insured depository OR primary regulator',
            f'"{query}" recall OR enforcement report OR complaint OR hazard OR remedy',
            f'"{query}" 510(k) OR K number OR product code OR substantially equivalent',
            f'"{query}" FDA classification OR product code OR device class OR regulation number',
            f'"{query}" FDA registration listing OR FEI OR establishment OR owner operator',
            f'"{query}" MAUDE OR adverse event OR malfunction OR injury OR death',
            f'"{query}" environmental compliance OR EPA ECHO OR facility OR violation',
            f'"{query}" clinical trial OR NCT OR sponsor OR primary outcome',
            f'"{query}" Open Payments OR CMS OR physician payment OR transfer of value',
            f'"{query}" FRED OR interest rate OR inflation OR unemployment OR yield curve OR credit spread',
            f'"{query}" contract OR grant OR award OR procurement OR USAspending',
            f'"{query}" SAM.gov OR solicitation OR RFP OR RFQ OR sources sought',
            f'"{query}" Grants.gov OR SBIR OR STTR OR non-dilutive funding OR federal grant',
            f'"{query}" funding OR financing OR 融资 OR 投资方',
            f'"{query}" patent OR 专利 OR inventor OR 发明人',
            f'"{query}" arxiv OR OpenReview OR ICRA OR IROS OR CoRL OR RSS',
            f'"{query}" GitHub OR Hugging Face OR ModelScope',
            f'"{query}" 招聘 OR careers OR jobs OR LinkedIn',
            f'"{query}" Reddit OR YouTube OR Twitter OR X OR 小红书 OR 抖音 OR 公众号',
            f'"{query}" browser automation OR logged-in page OR Chrome CDP',
            f'"{query}" scrape OR crawler OR structured extraction OR anti-bot',
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _registered_live_sources(self) -> list[dict[str, str]]:
        source_names = {
            "OpenAlexWorksSearchProvider": ("openalex_works_search", "OpenAlex 学术作品", "academic"),
            "SECEdgarCompanyFilingsProvider": ("sec_edgar_company_filings", "SEC EDGAR 公司披露", "regulatory_filings"),
            "SECInsiderTransactionsProvider": ("sec_insider_transactions", "SEC 内部人交易披露", "insider_transactions"),
            "SECOwnershipActivismProvider": ("sec_ownership_activism", "SEC 重大持股与控制权披露", "ownership_activism"),
            "SECInvestmentAdviserReportProvider": ("sec_investment_adviser_reports", "SEC 投顾/ERA Form ADV 数据", "investment_adviser_registry"),
            "FDICBankFindInstitutionProvider": ("fdic_bankfind_institutions", "FDIC BankFind 银行机构", "financial_institution_registry"),
            "GDELTDocNewsSearchProvider": ("gdelt_doc_news", "GDELT 全球新闻", "news_media"),
            "CPSCRecallSearchProvider": ("cpsc_recalls", "CPSC 产品召回", "product_safety_recall"),
            "FDAEnforcementRecallProvider": ("fda_enforcement_recalls", "FDA Enforcement 召回", "fda_enforcement_recall"),
            "FDADevice510kClearanceProvider": ("fda_device_510k", "FDA 510(k) 器械准入", "fda_device_clearance"),
            "FDADeviceAdverseEventProvider": ("fda_device_events", "FDA MAUDE 器械不良事件", "fda_device_adverse_event"),
            "FDADeviceClassificationProvider": ("fda_device_classification", "FDA 器械分类与产品代码", "fda_device_classification"),
            "FDADeviceRegistrationListingProvider": ("fda_device_registration_listing", "FDA 器械注册与列名", "fda_device_registration_listing"),
            "CFPBConsumerComplaintProvider": ("cfpb_consumer_complaints", "CFPB 消费金融投诉", "consumer_finance_complaint"),
            "NHTSARecallSearchProvider": ("nhtsa_recalls", "NHTSA 车辆召回", "vehicle_safety_recall"),
            "EPAEchoFacilityComplianceProvider": ("epa_echo_facilities", "EPA ECHO 设施合规", "environmental_compliance"),
            "ClinicalTrialsStudySearchProvider": ("clinicaltrials_studies", "ClinicalTrials.gov 试验登记", "clinical_trial_registry"),
            "CMSOpenPaymentsSearchProvider": ("cms_openpayments", "CMS Open Payments 医疗付款", "healthcare_payments"),
            "USASpendingAwardSearchProvider": ("usaspending_awards", "USAspending 政府采购与拨款", "procurement_awards"),
            "SAMGovOpportunitySearchProvider": ("sam_gov_opportunities", "SAM.gov 合同机会", "procurement_opportunity"),
            "GrantsGovOpportunitySearchProvider": ("grants_gov_opportunities", "Grants.gov 资助机会", "grant_opportunity"),
            "PatentsViewPatentSearchProvider": ("patentsview_patents", "PatentsView 专利", "patent"),
            "OFACSanctionsListSearchProvider": ("ofac_sanctions_lists", "OFAC 制裁清单", "sanctions"),
            "GitHubRepositorySearchProvider": ("github_repositories", "GitHub 代码仓库", "code_repository"),
            "GitHubCandidateSearchProvider": ("github_candidates", "GitHub 候选人搜索", "developer_profile"),
            "GitHubUserSearchProvider": ("github_users", "GitHub 用户搜索", "developer_profile"),
            "GitHubCodeSearchProvider": ("github_code", "GitHub 代码搜索", "code_search"),
            "GitHubTopicSearchProvider": ("github_topics", "GitHub Topic 搜索", "code_topic"),
            "HuggingFaceModelSearchProvider": ("huggingface_models", "Hugging Face 模型库", "model_repository"),
            "CompaniesHouseCompanySearchProvider": ("companies_house_search", "Companies House 公司注册", "company_registry"),
            "CourtListenerSearchProvider": ("courtlistener_search", "CourtListener 司法检索", "litigation"),
            "SECCompanyFactsProvider": ("sec_company_facts", "SEC Company Facts", "financial_facts"),
            "FederalRegisterDocumentSearchProvider": ("federal_register_documents", "Federal Register 监管文件", "regulatory_policy"),
            "CensusInternationalTradeProvider": ("census_international_trade", "US Census 国际贸易", "trade_flows"),
            "FREDSeriesSearchProvider": ("fred_series_search", "FRED 宏观经济序列", "macroeconomic_time_series"),
            "GNewsFundingNewsProvider": ("gnews_funding_news", "GNews 融资事件新闻", "funding_news"),
            "SECEnforcementSearchProvider": ("sec_enforcement_search", "SEC 执法/处罚搜索", "regulatory_enforcement"),
            "USAJobsSearchProvider": ("usajobs_search", "USAJOBS 招聘薪酬", "job_salary"),
            "BraveWebSearchProvider": ("brave_web_search", "Brave Search", "open_web"),
        }
        providers = list(self.live_searches)
        if self.web_search:
            providers.append(self.web_search)
        sources = []
        for provider in providers:
            if hasattr(provider, "source_metadata"):
                sources.append(provider.source_metadata())
                continue
            key, name_zh, source_type = source_names.get(
                provider.__class__.__name__,
                (provider.__class__.__name__, provider.__class__.__name__, "live_source"),
            )
            sources.append(
                {
                    "source_key": key,
                    "name_zh": name_zh,
                    "source_type": source_type,
                }
            )
        return sources
