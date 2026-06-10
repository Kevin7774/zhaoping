from __future__ import annotations

import pytest

from app.core import orchestrator


def test_planning_only_search_mode_skips_live_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_live_search(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("planning_only must not call live search providers")

    monkeypatch.setattr(orchestrator, "_live_search_context", fail_live_search)

    intelligence = orchestrator._source_intelligence(
        "请围绕 VLA 机器人岗位生成人才地图",
        "vla_embodied_expert",
        limit=3,
        ctx={"frontend_state": {"search_mode": "planning_only"}, "data": {}},
        agent_id="test",
    )

    trace = intelligence["搜索运行追踪"]

    assert intelligence["实时检索"]["search_mode"] == "planning_only"
    assert intelligence["实时检索"]["services"] == []
    assert trace["search_mode"] == "planning_only"
    assert trace["external_request_policy"] == "blocked_by_mode"
    assert trace["provider_budget"]["selected"] == 0
    assert trace["evidence_counts"]["recommended_sources"] >= 0
    assert trace["next_actions"]


def test_build_search_run_trace_summarizes_evidence_and_provider_health() -> None:
    trace = orchestrator._build_search_run_trace(
        query="robotics diffusion policy hiring",
        search_mode="social_expansion",
        recommended_sources=[{"source_key": "github"}, {"source_key": "x_recent_posts_search"}],
        records=[
            {"source_tier": "primary", "validation_status": "verified"},
            {"source_tier": "secondary", "validation_status": "needs_cross_check"},
            {"source_tier": "primary", "validation_status": "verified"},
        ],
        live_context={
            "search_mode": "social_expansion",
            "mode_label": "社媒扩展",
            "services": ["x_recent_posts_search"],
            "result_count": 2,
            "errors": [{"service": "agent_reach_social_search", "reason": "missing_tool:opencli"}],
            "research_layers": [{"id": "social_signal", "result_count": 2, "error_count": 1}],
            "provider_health": [
                {"service": "x_recent_posts_search", "status": "ready"},
                {"service": "agent_reach_social_search", "status": "missing_tool", "missing_runtime": ["opencli"]},
            ],
            "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 1},
            "external_request_policy": "bounded_live",
        },
    )

    assert trace == {
        "query": "robotics diffusion policy hiring",
        "search_mode": "social_expansion",
        "search_mode_label": "社媒扩展",
        "external_request_policy": "bounded_live",
        "provider_budget": {"max_live_providers": 8, "selected": 1, "skipped": 1},
        "providers": {
            "selected": ["x_recent_posts_search"],
            "health": [
                {"service": "x_recent_posts_search", "status": "ready"},
                {"service": "agent_reach_social_search", "status": "missing_tool", "missing_runtime": ["opencli"]},
            ],
            "errors": [{"service": "agent_reach_social_search", "reason": "missing_tool:opencli"}],
        },
        "result_count": 2,
        "research_layers": [{"id": "social_signal", "result_count": 2, "error_count": 1}],
        "evidence_counts": {
            "recommended_sources": 2,
            "records": 3,
            "source_tiers": {"primary": 2, "secondary": 1},
            "validation_statuses": {"verified": 2, "needs_cross_check": 1},
        },
        "next_actions": [
            "补齐缺失 provider 的凭证或本地工具后重跑同一 search_mode。",
            "优先复核 primary/verified 证据；needs_cross_check 只能作为线索。",
            "将高置信来源写入候选人或情报归档前保留 source_url 和 validation_status。",
        ],
    }
