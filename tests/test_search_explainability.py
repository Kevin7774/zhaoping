from __future__ import annotations

import json

import pytest

from app.core import orchestrator


def test_unknown_execution_policy_falls_back_to_bounded_live() -> None:
    config = orchestrator._search_config_from_ctx(
        {"frontend_state": {"execution_policy": "unsupported_policy", "source_layers": {"social": True}}}
    )
    services = orchestrator._live_services_for_search_config(config)

    assert config["execution_policy"] == "bounded_live"
    assert config["budget"]["max_providers"] == orchestrator.MAX_LIVE_RECRUITING_PROVIDERS
    assert "agent_reach_social_search" in services
    assert "opencli_platform_search" in services
    assert "search_mode" not in config


def test_search_config_layers_are_additive_and_budgeted() -> None:
    config = orchestrator._search_config_from_ctx(
        {
            "frontend_state": {
                "search_profile": "candidate_sourcing",
                "execution_policy": "deep_live",
                "source_layers": {
                    "academic": True,
                    "code_model": True,
                    "social": True,
                    "crawler_snapshot": True,
                    "people_database": False,
                    "news_funding": False,
                    "education_competition": False,
                },
                "search_budget": {
                    "max_providers": 5,
                    "per_provider_limit": 3,
                    "timeout_seconds": 9,
                    "max_crawl_pages": 2,
                },
            }
        }
    )

    services = orchestrator._live_services_for_search_config(config)

    assert config["search_profile"] == "candidate_sourcing"
    assert config["execution_policy"] == "deep_live"
    assert config["source_layers"]["academic"] is True
    assert config["source_layers"]["social"] is True
    assert config["source_layers"]["crawler_snapshot"] is True
    assert config["budget"] == {
        "max_providers": 5,
        "per_provider_limit": 3,
        "timeout_seconds": 9,
        "max_crawl_pages": 2,
    }
    assert "openalex_works_search" in services
    assert "github_repositories" in services
    assert "agent_reach_social_search" in services
    assert "opencli_web_read_search" in services
    assert "x_recent_posts_search" not in services
    assert "scrapling_adaptive_scrape" not in services
    assert "pdl_people_search" not in services


def test_default_candidate_sourcing_budget_reaches_opencli_platform_search() -> None:
    config = orchestrator._search_config_from_ctx({"frontend_state": {}})
    services = orchestrator._live_services_for_search_config(config)
    opencli_index = services.index("opencli_platform_search") + 1

    assert "opencli_platform_search" in services
    assert config["budget"]["max_providers"] >= opencli_index


def test_crawler_snapshot_layer_requires_deep_live_crawl_budget() -> None:
    bounded_config = orchestrator._search_config_from_ctx(
        {
            "frontend_state": {
                "search_profile": "candidate_sourcing",
                "execution_policy": "bounded_live",
                "source_layers": {"crawler_snapshot": True},
                "search_budget": {"max_crawl_pages": 3},
            }
        }
    )
    zero_budget_config = orchestrator._search_config_from_ctx(
        {
            "frontend_state": {
                "search_profile": "candidate_sourcing",
                "execution_policy": "deep_live",
                "source_layers": {"crawler_snapshot": True},
                "search_budget": {"max_crawl_pages": 0},
            }
        }
    )

    assert bounded_config["source_layers"]["crawler_snapshot"] is False
    assert zero_budget_config["source_layers"]["crawler_snapshot"] is False
    assert "opencli_web_read_search" not in orchestrator._live_services_for_search_config(bounded_config)
    assert "opencli_web_read_search" not in orchestrator._live_services_for_search_config(zero_budget_config)


def test_legacy_search_mode_field_is_ignored_after_structured_search_cutover() -> None:
    config = orchestrator._search_config_from_ctx({"frontend_state": {"search_mode": "legacy_mode"}})
    services = orchestrator._live_services_for_search_config(config)

    assert config["search_profile"] == "candidate_sourcing"
    assert config["source_layers"]["social"] is True
    assert "agent_reach_social_search" in services
    assert "x_recent_posts_search" not in services
    assert "github_repositories" in services
    assert "openalex_works_search" in services
    assert "search_mode" not in config


def test_source_intelligence_archives_search_evidence_ledger(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "evidence-ledger.jsonl"
    monkeypatch.setenv("INTELLIGENCE_ARCHIVE_PATH", str(archive_path))

    class FakeSearch:
        @staticmethod
        def plan(query: str, limit: int = 12) -> dict:
            return {
                "recommended_sources": [
                    {"source_key": "github", "name_zh": "GitHub", "source_names": ["GitHub"], "talent_signals": ["repo"], "suggested_queries": [query]},
                ]
            }

        @staticmethod
        def evidence(query: str, limit: int = 12) -> dict:
            return {
                "records": [
                    {
                        "source_key": "github_repositories",
                        "source_name": "GitHub",
                        "source_tier": "primary",
                        "validation_status": "verified",
                        "confidence": 0.86,
                        "signals": ["robotics"],
                        "snippet": "Maintains a robot policy repository.",
                    }
                ]
            }

    class FakeRouter:
        @staticmethod
        def search(*_args, **_kwargs):
            return FakeSearch()

    monkeypatch.setattr(orchestrator, "get_router", lambda: FakeRouter())
    monkeypatch.setattr(
        orchestrator,
        "_live_search_context",
        lambda *_args, **_kwargs: {
            "search_profile": "candidate_sourcing",
            "execution_policy": "bounded_live",
            "source_layers": {"academic": True, "code_model": True},
            "external_request_policy": "bounded_live",
            "services": ["github_repositories"],
            "query": "robotics diffusion policy",
            "results": [
                {
                    "source_key": "github_repositories",
                    "source_name": "GitHub",
                    "source_type": "code_repository",
                    "title": "robot-policy",
                    "url": "https://github.com/example/robot-policy",
                    "snippet": "Robot policy repository.",
                    "rank": 1,
                }
            ],
            "errors": [],
            "result_count": 1,
            "research_layers": [],
            "provider_health": [{"service": "github_repositories", "status": "ready"}],
            "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 0},
        },
    )

    intelligence = orchestrator._source_intelligence(
        "请围绕 VLA 机器人岗位生成人才地图",
        "vla_embodied_expert",
        limit=3,
        ctx={
            "task_id": "task_ledger",
            "frontend_state": {"project_id": "project_2026_ai_team", "job_profile_id": "job_vla_algorithm"},
            "data": {},
        },
        agent_id="test",
    )

    ledger = intelligence["搜索运行追踪"]["evidence_ledger"]
    assert ledger["archive_id"].startswith("intel_")
    assert ledger["artifact_type"] == "search_evidence_ledger"
    assert archive_path.exists()

    archived = json.loads(archive_path.read_text(encoding="utf-8").splitlines()[0])
    artifact = archived["artifact"]
    assert artifact["ledger_type"] == "search_evidence_ledger"
    assert artifact["task_id"] == "task_ledger"
    assert artifact["project_id"] == "project_2026_ai_team"
    assert artifact["job_id"] == "job_vla_algorithm"
    assert artifact["evidence_counts"]["records"] == 1
    assert artifact["live_results"][0]["source_key"] == "github_repositories"
    assert artifact["evidence_records"][0]["validation_status"] == "verified"


def test_source_intelligence_uses_project_job_query_for_live_search(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeSearch:
        @staticmethod
        def plan(query: str, limit: int = 12) -> dict:
            return {"recommended_sources": [{"source_key": "github", "suggested_queries": [query]}]}

        @staticmethod
        def evidence(query: str, limit: int = 12) -> dict:
            return {"records": []}

    class FakeRouter:
        @staticmethod
        def search(*_args, **_kwargs):
            return FakeSearch()

    def fake_live_context(router, query: str, *, role_key=None, **kwargs):  # noqa: ANN001, ANN003
        captured["query"] = query
        captured["role_key"] = role_key
        return {
            "search_profile": "candidate_sourcing",
            "execution_policy": "bounded_live",
            "source_layers": {"code_model": True},
            "external_request_policy": "bounded_live",
            "services": ["github_candidates"],
            "query": query,
            "results": [],
            "errors": [],
            "result_count": 0,
            "research_layers": [],
            "provider_health": [{"service": "github_candidates", "status": "ready"}],
            "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 0},
        }

    monkeypatch.setattr(orchestrator, "get_router", lambda: FakeRouter())
    monkeypatch.setattr(orchestrator, "_live_search_context", fake_live_context)

    orchestrator._source_intelligence(
        "请为 AI Native FDE 找候选人",
        "robot_system_architect",
        limit=3,
        ctx={
            "sourcing_job_profile": {
                "id": "job_fde",
                "title": "AI Native FDE / Agentic Builder",
                "must_have_skills": ["Agentic workflow", "AI coding 实战", "全栈开发"],
                "rationale": {"sourcing_keywords": ["MCP", "RAG", "Tool Calling"]},
            },
            "frontend_state": {"search_profile": "candidate_sourcing", "execution_policy": "bounded_live"},
            "data": {},
        },
        agent_id="test",
    )

    assert captured["role_key"] is None
    assert "AI Native FDE / Agentic Builder" in str(captured["query"])
    assert "Agentic workflow" in str(captured["query"])
    assert "robot system architecture" not in str(captured["query"])


def test_build_search_run_trace_summarizes_evidence_and_provider_health() -> None:
    trace = orchestrator._build_search_run_trace(
        query="robotics diffusion policy hiring",
        search_config={
            "search_profile": "candidate_sourcing",
            "execution_policy": "bounded_live",
            "source_layers": {"academic": True, "social": True},
            "budget": {"max_providers": 8, "per_provider_limit": 2, "timeout_seconds": 6, "max_crawl_pages": 0},
        },
        recommended_sources=[{"source_key": "github"}, {"source_key": "agent_reach_social_search"}],
        records=[
            {"source_tier": "primary", "validation_status": "verified"},
            {"source_tier": "secondary", "validation_status": "needs_cross_check"},
            {"source_tier": "primary", "validation_status": "verified"},
        ],
        live_context={
            "services": ["agent_reach_social_search"],
            "result_count": 2,
            "errors": [{"service": "github_code", "reason": "deferred_by_live_budget"}],
            "research_layers": [{"id": "social_signal", "result_count": 2, "error_count": 1}],
            "provider_health": [
                {"service": "agent_reach_social_search", "status": "ready"},
                {"service": "github_code", "status": "ready"},
            ],
            "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 1},
            "external_request_policy": "bounded_live",
        },
    )

    assert trace == {
        "query": "robotics diffusion policy hiring",
        "search_profile": "candidate_sourcing",
        "execution_policy": "bounded_live",
        "source_layers": {"academic": True, "social": True},
        "external_request_policy": "bounded_live",
        "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 1},
        "providers": {
            "selected": ["agent_reach_social_search"],
            "health": [
                {"service": "agent_reach_social_search", "status": "ready"},
                {"service": "github_code", "status": "ready"},
            ],
            "errors": [{"service": "github_code", "reason": "deferred_by_live_budget"}],
        },
        "result_count": 2,
        "research_layers": [{"id": "social_signal", "result_count": 2, "error_count": 1}],
        "evidence_counts": {
            "recommended_sources": 2,
            "records": 3,
            "source_tiers": {"primary": 2, "secondary": 1},
            "validation_statuses": {"verified": 2, "needs_cross_check": 1},
        },
        "evidence_gaps": [],
        "next_queries": ["robotics diffusion policy hiring site:github.com", "robotics diffusion policy hiring demo hiring team"],
        "next_actions": [
            "补齐缺失 provider 的凭证或本地工具后重跑同一搜索配置。",
            "优先复核 primary/verified 证据；needs_cross_check 只能作为线索。",
            "将高置信来源写入候选人或情报归档前保留 source_url 和 validation_status。",
        ],
    }
