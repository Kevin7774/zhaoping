"""Live preflight probe: verified vs probe_failed must reflect real request outcomes."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.core.integration_status as integration_status
from app.api.main import app
from app.core.config import load_app_config
from app.core.integration_status import probe_search_services


class _StubProvider:
    def __init__(self, results=None, error: Exception | None = None):
        self._results = results or []
        self._error = error

    def search(self, query: str, limit: int = 1):
        if self._error is not None:
            raise self._error
        return self._results


class _StubRouter:
    def __init__(self, providers: dict[str, _StubProvider]):
        self._providers = providers

    def search(self, service_name: str):
        return self._providers[service_name]


def _probe_with_stub(monkeypatch, providers: dict[str, _StubProvider], **kwargs):
    import app.core.router as router_module

    monkeypatch.setattr(router_module, "ServiceRouter", lambda config: _StubRouter(providers))
    return probe_search_services(services=list(providers), **kwargs)


def test_probe_marks_real_results_as_verified(monkeypatch) -> None:
    payload = _probe_with_stub(
        monkeypatch,
        {
            "github_candidates": _StubProvider(
                results=[{"title": "candidate", "url": "https://github.com/x", "retrieval_status": "retrieved"}]
            )
        },
    )

    assert payload["probed"] == 1
    assert payload["verified"] == 1
    probe = payload["probes"][0]
    assert probe["service"] == "github_candidates"
    assert probe["probe_status"] == "verified"
    assert probe["result_count"] == 1
    assert probe["latency_ms"] >= 0


def test_probe_marks_exceptions_and_error_status_results_as_failed(monkeypatch) -> None:
    payload = _probe_with_stub(
        monkeypatch,
        {
            "openalex_authors_search": _StubProvider(error=RuntimeError("HTTP 429 Too Many Requests")),
            "gnews_funding_news": _StubProvider(
                results=[{"retrieval_status": "error", "error": "query too long"}]
            ),
        },
    )

    assert payload["probed"] == 2
    assert payload["verified"] == 0
    by_service = {probe["service"]: probe for probe in payload["probes"]}
    assert by_service["openalex_authors_search"]["probe_status"] == "probe_failed"
    assert "429" in by_service["openalex_authors_search"]["reason"]
    assert by_service["gnews_funding_news"]["probe_status"] == "probe_failed"
    assert "query too long" in by_service["gnews_funding_news"]["reason"]


def test_probe_only_targets_ready_search_services() -> None:
    config = load_app_config()
    payload = probe_search_services(config=config, services=["definitely_not_a_service"])
    assert payload["probed"] == 0
    assert payload["probes"] == []


def test_service_status_reports_config_only_verification() -> None:
    status = integration_status.get_integration_status()
    search_services = [service for service in status["services"] if service["type"] == "search"]
    assert search_services
    assert all(service["verification"] == "config_only" for service in search_services)


def test_probe_api_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.main.probe_search_services",
        lambda services=None, timeout_seconds=12.0: {
            "probe_query": "robotics",
            "timeout_seconds": timeout_seconds,
            "probed": 1,
            "verified": 1,
            "failed": 0,
            "probes": [{"service": "github_candidates", "probe_status": "verified", "result_count": 1}],
        },
    )
    client = TestClient(app)
    response = client.post("/integrations/search/probe", json={"services": ["github_candidates"], "timeout_seconds": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] == 1
    assert payload["probes"][0]["probe_status"] == "verified"
