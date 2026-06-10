from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse


def _require_env(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {env_name}")
    return value


class FirecrawlScrapeProvider:
    def __init__(
        self,
        endpoint: str = "https://api.firecrawl.dev/v2/scrape",
        api_key_env: str = "FIRECRAWL_API_KEY",
        timeout_seconds: int = 60,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def scrape(self, url: str, *, formats: list[str] | None = None) -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)

        import requests

        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": formats or ["markdown"]},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Firecrawl scrape failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        data = payload.get("data") or payload
        return {
            "provider": "firecrawl_scrape",
            "url": url,
            "markdown": data.get("markdown"),
            "html": data.get("html"),
            "metadata": data.get("metadata") or {},
            "raw": payload,
        }


class OpenCLICrawlProvider:
    def __init__(
        self,
        command: str = "opencli",
        command_args: list[str] | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.command = command
        self.command_args = command_args or ["crawl", "{url}", "--format", "{format}", "--json"]
        self.timeout_seconds = timeout_seconds

    def scrape(self, url: str, *, formats: list[str] | None = None) -> dict[str, Any]:
        self._validate_public_url(url)
        if not shutil.which(self.command):
            raise RuntimeError(f"Missing required command: {self.command}")

        output_format = (formats or ["markdown"])[0]
        args = [self.command, *self._render_args(url=url, output_format=output_format)]
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"OpenCLI command failed: {stderr[:300]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"OpenCLI command timed out after {self.timeout_seconds}s") from exc

        return self._parse_output(url=url, stdout=completed.stdout)

    def _render_args(self, *, url: str, output_format: str) -> list[str]:
        values = {
            "url": url,
            "format": output_format,
        }
        return [arg.format(**values) for arg in self.command_args]

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenCLI crawl requires an absolute http(s) URL.")

    @staticmethod
    def _parse_output(*, url: str, stdout: str) -> dict[str, Any]:
        text = stdout.strip()
        if not text:
            return {
                "provider": "opencli_crawl",
                "url": url,
                "markdown": "",
                "html": None,
                "metadata": {},
                "raw": {"stdout": stdout},
            }

        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError:
            return {
                "provider": "opencli_crawl",
                "url": url,
                "markdown": stdout,
                "html": None,
                "metadata": {},
                "raw": {"stdout": stdout},
            }

        data = (payload.get("data") or payload) if isinstance(payload, dict) else payload
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict)), {})
        if not isinstance(data, dict):
            return {
                "provider": "opencli_crawl",
                "url": url,
                "markdown": None,
                "html": None,
                "metadata": {},
                "raw": payload,
            }

        saved_markdown = OpenCLICrawlProvider._read_saved_markdown(data.get("saved"))
        return {
            "provider": "opencli_crawl",
            "url": data.get("url") or url,
            "markdown": data.get("markdown") or data.get("content") or data.get("text") or saved_markdown,
            "html": data.get("html"),
            "metadata": data.get("metadata") or data.get("meta") or OpenCLICrawlProvider._metadata_from_saved_result(data),
            "raw": payload,
        }

    @staticmethod
    def _read_saved_markdown(saved: Any) -> str | None:
        if not isinstance(saved, str) or not saved:
            return None
        saved_path = Path(saved)
        if saved_path.is_absolute() or ".." in saved_path.parts:
            return None
        path = Path.cwd() / saved_path
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _metadata_from_saved_result(data: dict[str, Any]) -> dict[str, Any]:
        keys = ("title", "author", "publish_time", "status", "size", "saved")
        return {key: data[key] for key in keys if data.get(key) is not None}


class ApifyActorRunProvider:
    def __init__(
        self,
        endpoint_template: str = "https://api.apify.com/v2/acts/{actor_id}/runs",
        api_token_env: str = "APIFY_API_TOKEN",
        timeout_seconds: int = 60,
    ) -> None:
        self.endpoint_template = endpoint_template
        self.api_token_env = api_token_env
        self.timeout_seconds = timeout_seconds

    def run_actor(self, actor_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        api_token = _require_env(self.api_token_env)
        endpoint = self.endpoint_template.format(actor_id=quote(actor_id, safe="~"))

        import requests

        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            json=payload or {},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Apify actor run failed: {response.status_code} {response.text[:300]}") from exc

        data = response.json().get("data") or response.json()
        return {
            "provider": "apify_actor_run",
            "run_id": data.get("id"),
            "status": data.get("status"),
            "default_dataset_id": data.get("defaultDatasetId"),
            "raw": data,
        }


class BrightDataWebUnlockerProvider:
    def __init__(
        self,
        endpoint: str = "https://api.brightdata.com/request",
        api_key_env: str = "BRIGHTDATA_API_KEY",
        zone_env: str = "BRIGHTDATA_ZONE",
        timeout_seconds: int = 60,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.zone_env = zone_env
        self.timeout_seconds = timeout_seconds

    def scrape(self, url: str, *, data_format: str = "markdown") -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)
        zone = _require_env(self.zone_env)

        import requests

        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "zone": zone,
                "url": url,
                "format": "raw",
                "method": "GET",
                "data_format": data_format,
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Bright Data Web Unlocker failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        return {
            "provider": "brightdata_web_unlocker",
            "url": url,
            "status_code": payload.get("status_code") or payload.get("status"),
            "body": payload.get("body") or payload.get("html") or payload.get("content"),
            "raw": payload,
        }


class BrowserbaseSessionProvider:
    def __init__(
        self,
        endpoint: str = "https://api.browserbase.com/v1/sessions",
        api_key_env: str = "BROWSERBASE_API_KEY",
        project_id_env: str = "BROWSERBASE_PROJECT_ID",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.project_id_env = project_id_env
        self.timeout_seconds = timeout_seconds

    def create_session(self, **options: Any) -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)
        project_id = _require_env(self.project_id_env)

        import requests

        response = requests.post(
            self.endpoint,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={"projectId": project_id, **options},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Browserbase session creation failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        return {
            "provider": "browserbase_session",
            "session_id": payload.get("id"),
            "connect_url": payload.get("connectUrl") or payload.get("connect_url"),
            "raw": payload,
        }


class PublicWebSnapshotMonitorProvider:
    def __init__(
        self,
        snapshot_dir: str = "data/snapshots/public_web",
        primary_scrape_provider: Any | None = None,
        browser_session_provider: Any | None = None,
        target_groups: dict[str, list[str]] | None = None,
    ) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self.primary_scrape_provider = primary_scrape_provider
        self.browser_session_provider = browser_session_provider
        self.target_groups = target_groups or {}

    def snapshot(
        self,
        *,
        urls: list[str] | None = None,
        job_name: str = "public-web",
        target_group: str | None = None,
        use_browserbase: bool = False,
        formats: list[str] | None = None,
    ) -> dict[str, Any]:
        target_urls = self._target_urls(urls=urls, target_group=target_group)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.snapshot_dir / self._safe_slug(job_name) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        browserbase_session = None
        if use_browserbase and self.browser_session_provider is not None:
            browserbase_session = self.browser_session_provider.create_session(
                metadata={"job_name": job_name, "target_group": target_group or ""}
            )

        items = [
            self._snapshot_one(url=url, run_dir=run_dir, index=index, formats=formats or ["markdown"])
            for index, url in enumerate(target_urls, start=1)
        ]
        manifest = {
            "provider": "public_web_snapshot_monitor",
            "job_name": job_name,
            "target_group": target_group,
            "run_id": run_id,
            "run_dir": str(run_dir),
            "browserbase_session": browserbase_session,
            "items": items,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            **manifest,
            "manifest_path": str(manifest_path),
        }

    def _target_urls(self, *, urls: list[str] | None, target_group: str | None) -> list[str]:
        if urls:
            target_urls = urls
        elif target_group:
            target_urls = self.target_groups.get(target_group, [])
        else:
            target_urls = []
        if not target_urls:
            raise ValueError("Public web snapshot requires at least one URL or a configured target_group.")
        for url in target_urls:
            self._validate_public_url(url)
        return target_urls

    def _snapshot_one(self, *, url: str, run_dir: Path, index: int, formats: list[str]) -> dict[str, Any]:
        if self.primary_scrape_provider is None:
            return {
                "url": url,
                "status": "error",
                "error": "No primary scrape provider configured.",
            }

        safe_name = f"{index:03d}-{self._safe_slug(urlparse(url).netloc or 'page')}"
        markdown_path = run_dir / f"{safe_name}.md"
        raw_path = run_dir / f"{safe_name}.json"
        try:
            payload = self.primary_scrape_provider.scrape(url, formats=formats)
            markdown = payload.get("markdown") or payload.get("body") or payload.get("html") or ""
            markdown_path.write_text(str(markdown), encoding="utf-8")
            raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "url": url,
                "status": "saved",
                "provider": payload.get("provider"),
                "markdown_path": str(markdown_path),
                "raw_path": str(raw_path),
                "metadata": payload.get("metadata") or {},
            }
        except Exception as exc:
            return {
                "url": url,
                "status": "error",
                "error": str(exc)[:500],
            }

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Public web snapshot requires absolute http(s) URLs.")

    @staticmethod
    def _safe_slug(value: str) -> str:
        slug = "".join(char if char.isalnum() else "-" for char in value.lower())
        slug = "-".join(part for part in slug.split("-") if part)
        return slug[:80] or "snapshot"
