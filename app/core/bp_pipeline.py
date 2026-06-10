"""Five-stage BP-to-role pipeline.

First principles: a role is the endpoint of an auditable chain
business commitment -> required capability -> capability gap -> hire decision.

Stages:
  1. bp_claims            - extract business commitments / existing resources with verbatim quotes
  2. bp_capability_graph  - capabilities required to deliver the commitments
  3. bp_gap_analysis      - existing / partial / missing + hire vs vendor decision
  4. bp_role_design       - roles only for resolution=hire gaps, with full rationale fields
  5. critic gate          - deterministic: rejects roles without BP evidence, without a real
                            why_needed chain, or overlapping another role's boundary

TimeoutError propagates to the caller (the API router falls back / reports honestly).
Structured-output exhaustion raises BpStageOutputError.
"""

from __future__ import annotations

import json
import queue
import re
import threading
from typing import Any

from app.core.prompt_config import load_system_prompt

CLAIMS_PROMPT = "bp_claims_v1"
CAPABILITY_PROMPT = "bp_capability_graph_v1"
GAP_PROMPT = "bp_gap_analysis_v1"
ROLE_PROMPT = "bp_role_designer_v1"

ROLE_RATIONALE_FIELDS = (
    "why_needed",
    "bp_evidence",
    "business_commitments",
    "capability_gaps",
    "why_hire_not_vendor",
    "if_not_hired_risk",
    "dependencies",
    "first_90_day_outcomes",
    "hiring_priority",
    "confidence",
)

OVERLAP_REJECT_THRESHOLD = 0.62
MIN_WHY_NEEDED_CHARS = 20
MIN_QUOTE_CHARS = 6


class BpStageOutputError(RuntimeError):
    """A pipeline stage exhausted retries without valid structured output."""


def run_bp_pipeline(
    llm: Any,
    *,
    source_sections: list[tuple[str, str]],
    minimum_role_count: int,
    call_timeout_seconds: float,
    max_attempts: int = 3,
    claims_max_tokens: int = 3000,
    roles_max_tokens: int = 12000,
) -> dict[str, Any]:
    """Run all five stages and return a matrix compatible with the BP initialize response."""

    source_text = "\n\n".join(text for _, text in source_sections)
    materials = "\n\n".join(f"{label}:\n{text}" for label, text in source_sections)

    claims = _run_stage(
        llm,
        CLAIMS_PROMPT,
        [("输入材料", materials)],
        validator=_validate_claims,
        timeout_seconds=call_timeout_seconds,
        max_attempts=max_attempts,
        max_tokens=claims_max_tokens,
    )
    capability_graph = _run_stage(
        llm,
        CAPABILITY_PROMPT,
        [("第一阶段输出", json.dumps(claims, ensure_ascii=False))],
        validator=_validate_capabilities,
        timeout_seconds=call_timeout_seconds,
        max_attempts=max_attempts,
        max_tokens=claims_max_tokens,
    )
    gap_analysis = _run_stage(
        llm,
        GAP_PROMPT,
        [
            ("第一阶段输出", json.dumps(claims, ensure_ascii=False)),
            ("第二阶段输出", json.dumps(capability_graph, ensure_ascii=False)),
        ],
        validator=_validate_gaps,
        timeout_seconds=call_timeout_seconds,
        max_attempts=max_attempts,
        max_tokens=claims_max_tokens,
    )

    role_inputs = [
        ("第一阶段输出", json.dumps(claims, ensure_ascii=False)),
        ("第二阶段输出", json.dumps(capability_graph, ensure_ascii=False)),
        ("第三阶段输出", json.dumps(gap_analysis, ensure_ascii=False)),
        ("最少岗位数", str(minimum_role_count)),
    ]
    design = _run_stage(
        llm,
        ROLE_PROMPT,
        role_inputs,
        validator=_validate_role_design,
        timeout_seconds=call_timeout_seconds,
        max_attempts=max_attempts,
        max_tokens=roles_max_tokens,
    )
    accepted, rejected = critic_gate(design.get("roles") or [], source_text=source_text)

    if len(accepted) < minimum_role_count:
        feedback = (
            f"当前通过 Critic Gate 的岗位只有 {len(accepted)} 个，少于要求的 {minimum_role_count} 个。"
            "请基于 hire 缺口重新输出完整 roles；只有证据支持时才补充岗位，否则在 coverage_gaps 说明。"
        )
        if rejected:
            feedback += "\n以下岗位被拒绝，请修复证据链或重新划分边界：\n" + json.dumps(rejected, ensure_ascii=False)
        retry_inputs = role_inputs + [("Critic Gate 反馈", feedback)]
        design = _run_stage(
            llm,
            ROLE_PROMPT,
            retry_inputs,
            validator=_validate_role_design,
            timeout_seconds=call_timeout_seconds,
            max_attempts=max_attempts,
            max_tokens=roles_max_tokens,
        )
        accepted, rejected = critic_gate(design.get("roles") or [], source_text=source_text)

    if len(accepted) < minimum_role_count:
        raise BpStageOutputError(
            f"critic gate accepted {len(accepted)} roles; expected at least {minimum_role_count}. "
            f"rejected: {json.dumps(rejected, ensure_ascii=False)[:600]}"
        )

    return {
        "industry_reading": design.get("industry_reading"),
        "technical_assumptions": design.get("technical_assumptions") or [],
        "roles": accepted,
        "coverage_gaps": design.get("coverage_gaps") or [],
        "claims": claims,
        "capability_graph": capability_graph,
        "gap_analysis": gap_analysis,
        "rejected_roles": rejected,
        "research_trace": _research_trace(claims, capability_graph, gap_analysis, accepted, rejected),
    }


# --------------------------------------------------------------------------
# critic gate (deterministic, auditable)
# --------------------------------------------------------------------------


def critic_gate(
    roles: list[Any],
    *,
    source_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject roles without BP evidence, without a real rationale chain, or overlapping boundaries."""

    normalized_source = _normalize(source_text)
    candidates: list[dict[str, Any]] = [role for role in roles if isinstance(role, dict)]
    ordered = sorted(
        enumerate(candidates),
        key=lambda pair: (-_confidence(pair[1]), pair[0]),
    )
    accepted: list[tuple[int, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for index, role in ordered:
        reasons = _rationale_reject_reasons(role, normalized_source)
        if not reasons:
            overlap = _boundary_overlap(role, [item for _, item in accepted])
            if overlap is not None:
                other_title, score = overlap
                reasons.append(
                    f"岗位边界与「{other_title}」重复（相似度 {score:.2f}），未划分独立技术边界"
                )
        if reasons:
            rejected.append({"title": str(role.get("title") or f"role_{index + 1}"), "reasons": reasons})
        else:
            accepted.append((index, role))
    accepted.sort(key=lambda pair: pair[0])
    return [role for _, role in accepted], rejected


def _rationale_reject_reasons(role: dict[str, Any], normalized_source: str) -> list[str]:
    reasons: list[str] = []
    why_needed = str(role.get("why_needed") or "").strip()
    if len(why_needed) < MIN_WHY_NEEDED_CHARS:
        reasons.append("why_needed 缺失或过短，没有讲清业务承诺到能力缺口的链条")
    quotes = [str(q).strip() for q in role.get("bp_evidence") or [] if str(q).strip()]
    if not quotes:
        reasons.append("bp_evidence 为空：岗位没有 BP 证据")
    elif normalized_source and not any(
        len(_normalize(quote)) >= MIN_QUOTE_CHARS and _normalize(quote)[:80] in normalized_source
        for quote in quotes
    ):
        reasons.append("bp_evidence 没有任何一条能在输入材料中找到原文")
    if not [c for c in role.get("business_commitments") or [] if str(c).strip()]:
        reasons.append("business_commitments 为空：岗位没有挂到任何业务承诺")
    if not [c for c in role.get("capability_gaps") or [] if str(c).strip()]:
        reasons.append("capability_gaps 为空：岗位没有对应的能力缺口")
    if len(str(role.get("if_not_hired_risk") or "").strip()) < 8:
        reasons.append("if_not_hired_risk 缺失：没有回答不招会导致什么业务风险")
    if len(str(role.get("why_hire_not_vendor") or "").strip()) < 8:
        reasons.append("why_hire_not_vendor 缺失：没有回答为什么必须招聘而不是外包")
    return reasons


def _boundary_overlap(
    role: dict[str, Any],
    accepted: list[dict[str, Any]],
) -> tuple[str, float] | None:
    fingerprint = _role_fingerprint(role)
    if not fingerprint:
        return None
    for other in accepted:
        other_fingerprint = _role_fingerprint(other)
        if not other_fingerprint:
            continue
        union = fingerprint | other_fingerprint
        if not union:
            continue
        score = len(fingerprint & other_fingerprint) / len(union)
        if score > OVERLAP_REJECT_THRESHOLD:
            return str(other.get("title") or "未命名岗位"), score
    return None


def _role_fingerprint(role: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    for key in ("responsibilities", "must_have_skills"):
        parts.extend(str(item) for item in role.get(key) or [])
    return _char_bigrams(_normalize(" ".join(parts)))


def _char_bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _confidence(role: dict[str, Any]) -> float:
    try:
        value = float(role.get("confidence"))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(value, 1.0))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


# --------------------------------------------------------------------------
# stage runner
# --------------------------------------------------------------------------


def _run_stage(
    llm: Any,
    prompt_name: str,
    sections: list[tuple[str, str]],
    *,
    validator: Any,
    timeout_seconds: float,
    max_attempts: int,
    max_tokens: int,
) -> dict[str, Any]:
    system_prompt = load_system_prompt(prompt_name)
    if not system_prompt:
        raise BpStageOutputError(f"missing prompt: {prompt_name}")
    prompt = f"{system_prompt}\n\n" + "\n\n".join(f"{label}:\n{text}" for label, text in sections)
    last_error = "unknown structured output error"
    for _attempt in range(max_attempts):
        output = _run_with_timeout(
            lambda: _llm_json_text(llm, prompt, max_tokens=max_tokens),
            timeout_seconds=timeout_seconds,
            label=f"BP pipeline stage {prompt_name}",
        )
        try:
            payload = _parse_json_object(output)
            validator(payload)
            return payload
        except (ValueError, BpStageOutputError) as exc:
            last_error = str(exc)
            prompt = (
                f"{system_prompt}\n\n"
                + "\n\n".join(f"{label}:\n{text}" for label, text in sections)
                + "\n\n上一次输出不合法，错误是：\n"
                + last_error
                + "\n\n请重新输出一个完整、合法、紧凑的 JSON 对象，不要输出其他内容。"
                + f"\n上一次输出（截断）：\n{output[:1500]}"
            )
    raise BpStageOutputError(f"stage {prompt_name} structured output failed: {last_error}")


def _validate_claims(payload: dict[str, Any]) -> None:
    for key in ("business_commitments", "existing_resources"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"claims output missing list field: {key}")
    if not payload["business_commitments"]:
        raise ValueError("claims output has no business_commitments")
    for item in payload["business_commitments"]:
        if not isinstance(item, dict) or not str(item.get("quote") or "").strip():
            raise ValueError("every business commitment requires a verbatim quote")


def _validate_capabilities(payload: dict[str, Any]) -> None:
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("capability graph output has no capabilities")
    for item in capabilities:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            raise ValueError("every capability requires id and name")
        if not item.get("supports_commitments"):
            raise ValueError(f"capability {item.get('id')} is not linked to any commitment")


def _validate_gaps(payload: dict[str, Any]) -> None:
    gaps = payload.get("gaps")
    if not isinstance(gaps, list) or not gaps:
        raise ValueError("gap analysis output has no gaps")
    for item in gaps:
        if not isinstance(item, dict) or not item.get("capability_id"):
            raise ValueError("every gap requires capability_id")
        if item.get("resolution") not in {"hire", "vendor", "partner", "existing"}:
            raise ValueError(f"gap {item.get('capability_id')} has invalid resolution")


def _validate_role_design(payload: dict[str, Any]) -> None:
    roles = payload.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("role design output has no roles")
    for index, role in enumerate(roles):
        if not isinstance(role, dict) or not str(role.get("title") or "").strip():
            raise ValueError(f"role #{index + 1} is missing title")


# --------------------------------------------------------------------------
# research trace from real stage outputs
# --------------------------------------------------------------------------


def _research_trace(
    claims: dict[str, Any],
    capability_graph: dict[str, Any],
    gap_analysis: dict[str, Any],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    commitments = [item for item in claims.get("business_commitments") or [] if isinstance(item, dict)]
    resources = [item for item in claims.get("existing_resources") or [] if isinstance(item, dict)]
    capabilities = [item for item in capability_graph.get("capabilities") or [] if isinstance(item, dict)]
    gaps = [item for item in gap_analysis.get("gaps") or [] if isinstance(item, dict)]
    by_resolution: dict[str, int] = {}
    for gap in gaps:
        key = str(gap.get("resolution") or "unknown")
        by_resolution[key] = by_resolution.get(key, 0) + 1
    priorities: dict[str, int] = {}
    for role in accepted:
        key = str(role.get("hiring_priority") or "unrated")
        priorities[key] = priorities.get(key, 0) + 1
    return [
        {
            "stage": "业务承诺抽取",
            "summary": f"抽取业务承诺 {len(commitments)} 条、已有资源 {len(resources)} 条，全部带原文引用。",
            "evidence": [str(item.get("quote") or "")[:80] for item in commitments[:5] if item.get("quote")],
            "assumptions": [],
            "risk": "承诺为 0 时说明 BP 输入过短，应人工复核。" if not commitments else None,
        },
        {
            "stage": "能力图谱",
            "summary": f"承诺拆解为 {len(capabilities)} 个能力节点，每个节点关联到具体承诺编号。",
            "evidence": [f"{item.get('id')}: {item.get('name')}" for item in capabilities[:6]],
            "assumptions": [],
            "risk": None,
        },
        {
            "stage": "缺口分析",
            "summary": "能力现状与解决方式：" + "，".join(f"{key}={count}" for key, count in sorted(by_resolution.items())),
            "evidence": [
                f"{item.get('capability_id')} -> {item.get('resolution')}: {str(item.get('rationale') or '')[:60]}"
                for item in gaps[:6]
            ],
            "assumptions": ["可外包/合作覆盖的能力不生成岗位。"],
            "risk": None,
        },
        {
            "stage": "岗位设计",
            "summary": (
                f"仅针对 hire 缺口设计岗位 {len(accepted)} 个；优先级分布："
                + "，".join(f"{key}={count}" for key, count in sorted(priorities.items()))
            ),
            "evidence": [f"{role.get('title')}: {str(role.get('why_needed') or '')[:60]}" for role in accepted[:6]],
            "assumptions": [],
            "risk": None,
        },
        {
            "stage": "Critic Gate",
            "summary": f"通过 {len(accepted)} 个，拒绝 {len(rejected)} 个（无 BP 证据 / 理由链不完整 / 边界重复）。",
            "evidence": [
                f"{item.get('title')}: {'；'.join(item.get('reasons') or [])[:80]}" for item in rejected[:6]
            ],
            "assumptions": [],
            "risk": "被拒绝岗位仅在响应中列出，不会写入数据库。" if rejected else None,
        },
    ]


# --------------------------------------------------------------------------
# LLM call helpers
# --------------------------------------------------------------------------


def _parse_json_object(raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("stage returned non-object JSON")
    return payload


def _llm_json_text(llm: Any, prompt: str, *, max_tokens: int) -> str:
    messages = getattr(llm, "messages", None)
    if callable(messages):
        response = messages(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = _message_response_content(response)
        if content:
            return content
    return llm.text(prompt, max_tokens=max_tokens)


def _message_response_content(response: Any) -> str | None:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return str(content).strip() if content else None
    text = first_choice.get("text")
    return str(text).strip() if text else None


def _run_with_timeout(fn, *, timeout_seconds: float, label: str) -> Any:  # noqa: ANN001
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def target() -> None:
        try:
            result_queue.put(("ok", fn()))
        except BaseException as exc:  # noqa: BLE001
            result_queue.put(("error", exc))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"{label} timed out after {timeout_seconds:g}s")
    status, payload = result_queue.get()
    if status == "error":
        raise payload
    return payload
