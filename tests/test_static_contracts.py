from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import load_app_config
from app.core.router import ServiceRouter
from app.rag.ingest_worker import chunk_markdown, stable_point_id
from app.skills.tech_space import (
    CAPABILITY_STANDARDS,
    ROBOT_ROLES_METADATA,
    ROBOT_TEAM_PROFILES,
    get_capabilities_for_role,
    validate_role_capabilities,
)
from app.skills.search_sources import SEARCH_DATA_SOURCES
from app.skills.recruiting_scenarios import (
    HOME_ROBOT_RECRUITING_SCENARIOS,
    build_talent_map,
    evaluate_candidate,
    generate_job_profile_and_jd,
    generate_weekly_report,
    infer_role_key,
)


def test_all_role_capabilities_exist() -> None:
    validate_role_capabilities()
    assert len(ROBOT_ROLES_METADATA) == 12
    assert len(ROBOT_TEAM_PROFILES) == 6
    assert len(SEARCH_DATA_SOURCES) == 16
    assert "github" in SEARCH_DATA_SOURCES
    assert "ai_communities" in SEARCH_DATA_SOURCES
    assert "video_platforms" in SEARCH_DATA_SOURCES
    assert "cap_vla_imitation" in CAPABILITY_STANDARDS


def test_get_capabilities_for_role_includes_ids() -> None:
    capabilities = get_capabilities_for_role("robot_data_infrastructure")
    assert {capability["capability_id"] for capability in capabilities} == {
        "cap_teleop_system",
        "cap_data_alignment",
        "cap_data_cleaning_pipeline",
    }


def test_chunking_and_stable_ids() -> None:
    text = "short\n\n" + ("具身智能数据采集 " * 10) + "\n\n" + ("Diffusion Policy " * 10)
    chunks = chunk_markdown(text)
    assert len(chunks) == 2
    assert stable_point_id("cand_1", 0) == stable_point_id("cand_1", 0)
    assert stable_point_id("cand_1", 0) != stable_point_id("cand_1", 1)


def test_service_config_defaults_exist() -> None:
    config = load_app_config()
    assert config.default_service_name("document_parser") == "auto_document_parser"
    assert config.service("bge_m3_local").provider == "sentence_transformers"
    assert config.service("qdrant_local").model_extra["vector_size"] == 1024
    assert config.default_service_name("ocr") == "aliyun_ocr"
    assert config.default_service_name("llm") == "token_plan_anthropic"
    assert config.default_service_name("search") == "talent_source_catalog"
    assert "robot_role_metadata" in config.skills
    assert "robot_team_profiles" in config.skills
    assert "search_data_sources" in config.skills
    assert "home_robot_recruiting_scenarios" in config.skills


def test_router_uses_plain_text_parser_without_embedding(tmp_path: Path) -> None:
    resume = tmp_path / "resume.md"
    resume.write_text("# 候选人\n\nDiffusion Policy 项目经验。", encoding="utf-8")

    router = ServiceRouter(load_app_config())
    parser = router.document_parser("plain_text_document_parser")

    assert parser.parse(str(resume)).startswith("# 候选人")


def test_router_registries_and_structured_output_provider() -> None:
    router = ServiceRouter(load_app_config())

    assert "robot_capability_standards" in router.skill_registry.all()
    assert "robot_team_profiles" in router.skill_registry.all()
    assert "search_data_sources" in router.skill_registry.all()
    assert "home_robot_recruiting_scenarios" in router.skill_registry.all()
    assert "disabled_mcp" in router.mcp_registry.services()
    assert router.structured_output("outlines_structured_output").model_service == "token_plan_anthropic"


def test_home_robot_recruiting_scenarios_cover_a_b_c_d() -> None:
    workflows = HOME_ROBOT_RECRUITING_SCENARIOS["workflows"]

    assert set(workflows) == {
        "scenario_a_job_profile_jd",
        "scenario_b_talent_map",
        "scenario_c_candidate_evaluation",
        "scenario_d_weekly_report",
    }
    assert "生成 JD" in workflows["scenario_a_job_profile_jd"]["workflow"]
    assert "触达策略" in workflows["scenario_b_talent_map"]["output_fields"]
    assert workflows["scenario_c_candidate_evaluation"]["scoring_weights"]["核心技术能力匹配度"] == 25
    assert workflows["scenario_d_weekly_report"]["name_zh"] == "场景 D：招聘周报"
    assert "MCP Connectors" in HOME_ROBOT_RECRUITING_SCENARIOS["infrastructure_layer"]
    assert "知识库持续进化" in HOME_ROBOT_RECRUITING_SCENARIOS["data_flywheel"]


def test_generate_vla_job_profile_is_robot_specific() -> None:
    result = generate_job_profile_and_jd("我们想招一个家庭机器人 VLA 算法工程师")

    assert infer_role_key("家庭机器人 VLA 算法工程师") == "vla_embodied_expert"
    assert "VLA / 具身智能算法工程师" in result["岗位定位"]
    assert "连续动作空间离散化与多模态Token编排" in result["能力矩阵"]["必备能力"]
    assert "是否理解 action token 和连续动作离散化" in result["能力矩阵"]["加分能力"]
    assert "纯NLP" in result["能力矩阵"]["排除项"]
    assert any("Diffusion Policy" in keyword for keyword in result["候选人来源"]["岗位关键词"])


def test_build_slam_talent_map_uses_transfer_sources() -> None:
    result = build_talent_map("家庭机器人 SLAM 工程师")

    assert "科沃斯" in result["优先来源公司"]
    assert "科沃斯" in result["目标公司"]
    assert "AR 空间计算团队" in result["次优来源公司"]
    assert "纯网页前端" in result["排除来源"]
    assert any(keyword == "SLAM / 导航算法工程师" for keyword in result["候选人关键词"])
    assert any(keyword == "SLAM / 导航算法工程师" for keyword in result["搜索关键词"])


def test_evaluate_candidate_distinguishes_real_robot_from_sim_only() -> None:
    real_robot = evaluate_candidate(
        "主导家庭机器人 VLA 项目，负责第一视角遥操作数据、Action Token、Diffusion Policy，"
        "ROS 实机部署，处理长程任务失败恢复和家具变化长尾场景。",
        target="家庭机器人 VLA 算法工程师",
    )
    sim_only = evaluate_candidate(
        "参与 Isaac Sim 仿真环境搭建和策略训练，主要负责边缘模块。",
        target="家庭机器人 VLA 算法工程师",
    )

    assert real_robot["推荐等级"] in {"强推", "可面"}
    assert real_robot["匹配评分"] > sim_only["匹配评分"]
    assert any("真实机器人/硬件部署" in risk for risk in sim_only["风险点"])
    assert real_robot["推荐结论"] == real_robot["结论"]
    assert real_robot["证据链"]["真实机器人证据"] is True


def test_generate_weekly_report_routes_to_data_flywheel() -> None:
    report = generate_weekly_report(
        "本周 VLA 岗位面试反馈已校准，GitHub 和 B站 Demo 发现两个候选人，暂无 offer 结果。",
        focus_roles=["家庭机器人 VLA 算法工程师"],
    )

    assert "招聘周报" in HOME_ROBOT_RECRUITING_SCENARIOS["workflows"]["scenario_d_weekly_report"]["name_zh"]
    assert "本周招聘结论" in report
    assert "GitHub" in report["市场人才信号"]
    assert "B站" in report["市场人才信号"]
    assert report["回流目标"] == ["知识库", "画像库", "评分体系"]


def test_search_source_catalog_provider_returns_recruiting_sources() -> None:
    router = ServiceRouter(load_app_config())
    search = router.search()

    results = search.search("VLA 机器人 招聘 薪酬", limit=3)
    assert results
    assert results[0]["source_key"] == "recruitment_boards_cn"
    assert "Boss直聘" in results[0]["source_names"]

    plan = search.plan("ICRA humanoid control", limit=5)
    assert plan["recommended_sources"]
    assert any(source["source_key"] == "conference_paper_lists" for source in plan["recommended_sources"])
    assert any("不绕过登录" in guardrail for guardrail in plan["guardrails"])


def test_config_rejects_vector_size_mismatch(tmp_path: Path) -> None:
    config = tmp_path / "services.toml"
    config.write_text(
        """
[defaults]
embedding = "emb"
vector_store = "store"

[services.emb]
type = "embedding"
provider = "sentence_transformers"
model_name = "BAAI/bge-m3"
vector_size = 1024

[services.store]
type = "vector_store"
provider = "qdrant_local"
path = "./qdrant_mvp_store"
collection_name = "robot_talents"
distance = "cosine"
embedding_service = "emb"
vector_size = 768
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="vector_size"):
        load_app_config(config)
