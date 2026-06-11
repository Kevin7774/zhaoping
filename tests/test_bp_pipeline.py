from __future__ import annotations

from app.core.bp_pipeline import _parse_json_object, critic_gate

SOURCE = "汉诺云智承诺交付边缘计算与 AI 综合解决方案，已有 3000 平厂房和智能硬件供应链，目标东盟市场销售。"


def _role(**overrides) -> dict:
    role = {
        "role_id": "edge_ai_architect",
        "title": "边缘 AI 架构师",
        "responsibilities": ["设计边缘推理集群与云边协同架构"],
        "must_have_skills": ["边缘计算", "模型部署"],
        "why_needed": "业务承诺 C1 要求交付边缘 AI 解决方案，CAP1 能力缺口必须由专职架构师承接。",
        "bp_evidence": ["交付边缘计算与 AI 综合解决方案"],
        "business_commitments": ["C1"],
        "capability_gaps": ["CAP1"],
        "why_hire_not_vendor": "架构知识必须留在组织内，外包会失去交付控制。",
        "if_not_hired_risk": "边缘交付承诺将失败，客户验收无法通过。",
        "dependencies": [],
        "first_90_day_outcomes": ["完成首个边缘集群可验收交付"],
        "hiring_priority": "P0",
        "confidence": 0.9,
    }
    role.update(overrides)
    return role


def test_critic_accepts_role_with_full_chain() -> None:
    accepted, rejected = critic_gate([_role()], source_text=SOURCE)
    assert len(accepted) == 1
    assert rejected == []


def test_critic_matches_evidence_from_pdf_text_with_control_chars_and_compatibility_glyphs() -> None:
    source = (
        "岗位名称：AI\x01Native\x01FDE。\n"
        "我们招的不是普通全栈，而是能和领域专家一起，用\x01AI-native\x01方法独立驱动完整\x01SDLC\x01的"
        "\x01Agentic\x01 Builder。\n"
        "候选人也可以是 Agentic\x01全栈⼯程师。"
    )

    accepted, rejected = critic_gate(
        [
            _role(
                title="AI Native FDE / Agentic Builder",
                responsibilities=["用 AI-native 方法独立驱动完整 SDLC"],
                must_have_skills=["AI Native", "全栈工程师"],
                bp_evidence=["AI Native FDE"],
            )
        ],
        source_text=source,
    )

    assert len(accepted) == 1
    assert rejected == []


def test_critic_rejects_role_without_bp_evidence() -> None:
    accepted, rejected = critic_gate([_role(bp_evidence=[])], source_text=SOURCE)
    assert accepted == []
    assert len(rejected) == 1
    assert any("bp_evidence" in reason for reason in rejected[0]["reasons"])
    assert rejected[0]["critic_category"] == "no_evidence"
    assert rejected[0]["missing_evidence"]


def test_critic_rejects_role_whose_quote_is_not_in_source() -> None:
    accepted, rejected = critic_gate(
        [_role(bp_evidence=["BP 中根本不存在的编造引用内容"])],
        source_text=SOURCE,
    )
    assert accepted == []
    assert any("找到原文" in reason for reason in rejected[0]["reasons"])


def test_critic_rejects_role_without_why_needed_chain() -> None:
    accepted, rejected = critic_gate([_role(why_needed="需要")], source_text=SOURCE)
    assert accepted == []
    assert any("why_needed" in reason for reason in rejected[0]["reasons"])
    assert rejected[0]["critic_category"] == "incomplete_rationale"


def test_critic_overlap_rejection_carries_boundary_category() -> None:
    strong = _role(confidence=0.9)
    duplicate = _role(role_id="copy", title="边缘 AI 平台架构师", confidence=0.4)
    _, rejected = critic_gate([strong, duplicate], source_text=SOURCE)
    assert rejected and rejected[0]["critic_category"] == "boundary_overlap"
    assert rejected[0]["missing_evidence"] == []


def test_critic_rejects_role_without_commitment_or_gap_links() -> None:
    accepted, rejected = critic_gate(
        [_role(business_commitments=[], capability_gaps=[])],
        source_text=SOURCE,
    )
    assert accepted == []
    reasons = "；".join(rejected[0]["reasons"])
    assert "business_commitments" in reasons
    assert "capability_gaps" in reasons


def test_critic_rejects_overlapping_boundary_and_keeps_higher_confidence() -> None:
    strong = _role(confidence=0.9, title="边缘 AI 架构师")
    duplicate = _role(
        role_id="edge_ai_architect_copy",
        title="边缘 AI 平台架构师",
        confidence=0.5,
    )
    accepted, rejected = critic_gate([duplicate, strong], source_text=SOURCE)
    assert [role["title"] for role in accepted] == ["边缘 AI 架构师"]
    assert rejected[0]["title"] == "边缘 AI 平台架构师"
    assert any("边界" in reason for reason in rejected[0]["reasons"])


def test_critic_rejects_missing_vendor_and_risk_answers() -> None:
    accepted, rejected = critic_gate(
        [_role(why_hire_not_vendor="", if_not_hired_risk="")],
        source_text=SOURCE,
    )
    assert accepted == []
    reasons = "；".join(rejected[0]["reasons"])
    assert "why_hire_not_vendor" in reasons
    assert "if_not_hired_risk" in reasons


def test_parse_json_object_repairs_missing_commas_between_fields() -> None:
    payload = _parse_json_object(
        """
        {
          "gaps": [
            {
              "capability_id": "CAP1",
              "status": "missing",
              "resolution": "hire",
              "rationale": "核心交付能力需要留在组织内"
              "evidence": ["C1"]
            }
          ]
        }
        """
    )

    assert payload["gaps"][0]["evidence"] == ["C1"]


def test_parse_json_object_repairs_missing_commas_between_array_items() -> None:
    payload = _parse_json_object(
        """
        {
          "gaps": [
            {"capability_id": "CAP1", "status": "missing", "resolution": "hire", "rationale": "自建", "evidence": ["C1"]}
            {"capability_id": "CAP2", "status": "existing", "resolution": "existing", "rationale": "已有", "evidence": ["R1"]}
          ]
        }
        """
    )

    assert [item["capability_id"] for item in payload["gaps"]] == ["CAP1", "CAP2"]
