from __future__ import annotations

from typing import Any

from app.skills.recruiting_effect_cases import DEFAULT_RECRUITING_EFFECT_CASES
from app.skills.recruiting_scenarios import evaluate_candidate, score_candidate_against_job


DEFAULT_RSI_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "real_robot_latency_positive",
        "name": "真实机器人低延迟候选人应进入面试",
        "candidate_material": (
            "主导家庭机器人 VLA 项目，负责第一视角遥操作数据、Action Token、"
            "Diffusion Policy，ROS 实机部署，处理家具变化长尾场景，控制链路延迟 12ms。"
        ),
        "target": "家庭机器人 VLA 算法工程师",
        "team_constraint": "真机动作延迟高",
        "expectations": {
            "min_score": 65,
            "allowed_levels": ["强推", "可面"],
            "required_evidence_flags": {"真实机器人证据": True},
            "required_output_paths": [
                "decision_sandbox.fact_chain",
                "decision_sandbox.probing_toolkit",
                "decision_sandbox.feedback_loop.status",
            ],
        },
    },
    {
        "case_id": "sim_only_guardrail",
        "name": "仿真候选人不能被误判为强实机",
        "candidate_material": "参与 Isaac Sim 仿真环境搭建和策略训练，主要负责边缘模块。",
        "target": "家庭机器人 VLA 算法工程师",
        "team_constraint": "真机泛化",
        "expectations": {
            "max_score": 55,
            "allowed_levels": ["备选", "不推荐"],
            "required_risk_terms": ["真实机器人/硬件部署"],
            "required_output_paths": ["decision_sandbox.feedback_loop.status"],
        },
    },
    {
        "case_id": "evidence_contract_iteration_gap",
        "name": "暴露裸评估路径缺少证据依赖合约",
        "candidate_material": (
            "主导家庭机器人 VLA 项目，负责第一视角遥操作数据、Diffusion Policy，"
            "ROS 实机部署，控制链路延迟 12ms。"
        ),
        "target": "家庭机器人 VLA 算法工程师",
        "team_constraint": "真机动作延迟高",
        "expectations": {
            "min_score": 70,
            "required_evidence_flags": {"真实机器人证据": True},
            "required_output_paths": ["decision_sandbox.evidence_dependency_contract.guardrail"],
        },
    },
)


class SelfRSIEvaluator:
    """Deterministic self-evaluation loop for local recruiting agent behavior."""

    def __init__(self, suite_id: str, baseline_threshold: float = 0.8) -> None:
        self.suite_id = suite_id
        self.baseline_threshold = max(0.0, min(float(baseline_threshold), 1.0))

    def evaluate(
        self,
        suite: str | None = None,
        cases: list[dict[str, Any]] | None = None,
        threshold: float | None = None,
        mode: str = "local",
        allow_live: bool = False,
        max_live_results: int = 1,
        router: Any | None = None,
        search_service: str | None = None,
        llm_service: str | None = "openrouter_evidence_judge",
    ) -> dict[str, Any]:
        suite_id = (suite or self.suite_id).strip() or self.suite_id
        normalized_cases = self._normalize_cases(cases, suite_id=suite_id)
        active_threshold = self.baseline_threshold if threshold is None else max(0.0, min(float(threshold), 1.0))
        case_results = [self._run_case(case) for case in normalized_cases]
        check_count = sum(len(case["checks"]) for case in case_results)
        passed_checks = sum(1 for case in case_results for check in case["checks"] if check["passed"])
        suite_score = round(passed_checks / check_count, 3) if check_count else 0.0
        feedback = self._build_feedback(case_results)
        iteration = self._build_iteration(feedback)
        status = "passed" if suite_score >= active_threshold and not feedback["gaps"] else "needs_iteration"
        operator_summary = self._build_operator_summary(suite_id, case_results)
        normalized_mode = "full" if mode == "full" else "local"
        full_mode_artifacts: dict[str, Any] = {}
        capability_trace = [
            {
                "capability": "candidate_evaluation",
                "status": "used",
                "details": {
                    "case_count": len(case_results),
                    "check_count": check_count,
                },
            }
        ]
        if normalized_mode == "full":
            full_mode_artifacts, extra_trace = self._run_full_mode_capabilities(
                router=router,
                normalized_cases=normalized_cases,
                case_results=case_results,
                feedback=feedback,
                allow_live=allow_live,
                max_live_results=max_live_results,
                search_service=search_service,
                llm_service=llm_service,
            )
            capability_trace.extend(extra_trace)

        return {
            "suite_id": suite_id,
            "provider": "self_rsi",
            "mode": normalized_mode,
            "rsi_cycle": ["evaluate", "test", "feedback", "iterate"],
            "status": status,
            "summary": {
                "case_count": len(case_results),
                "passed_cases": sum(1 for case in case_results if case["passed"]),
                "failed_cases": sum(1 for case in case_results if not case["passed"]),
                "check_count": check_count,
                "passed_checks": passed_checks,
                "failed_checks": check_count - passed_checks,
                "suite_score": suite_score,
                "threshold": active_threshold,
            },
            "case_results": case_results,
            "feedback": feedback,
            "iteration": iteration,
            "operator_summary": operator_summary,
            "capability_trace": capability_trace,
            "full_mode_artifacts": full_mode_artifacts,
            "guardrails": [
                "默认 local 模式不调用外部 LLM 或 live API；full 模式只有 allow_live=true 时才尝试 live/付费能力。",
                "反馈缺口不返回候选人原文，只返回用例 ID、检查项和改进动作。",
                "RSI 输出只生成下一轮测试和工程建议，不自动修改评分逻辑。",
            ],
        }

    def _run_full_mode_capabilities(
        self,
        *,
        router: Any | None,
        normalized_cases: list[dict[str, Any]],
        case_results: list[dict[str, Any]],
        feedback: dict[str, Any],
        allow_live: bool,
        max_live_results: int,
        search_service: str | None,
        llm_service: str | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        active_router = router or self._default_router()
        limit = max(1, min(int(max_live_results), 5))
        query = self._capability_query(normalized_cases)
        artifacts: dict[str, Any] = {}
        trace: list[dict[str, Any]] = []

        artifacts["integration_status"] = self._integration_status_artifact()
        trace.append(
            {
                "capability": "integration_status",
                "status": artifacts["integration_status"]["status"],
                "details": artifacts["integration_status"],
            }
        )

        artifacts["live_search"] = self._live_search_artifact(
            router=active_router,
            query=query,
            limit=limit,
            service_name=search_service,
            allow_live=allow_live,
        )
        trace.append(
            {
                "capability": "live_search",
                "status": artifacts["live_search"]["status"],
                "details": {
                    "result_count": artifacts["live_search"].get("result_count", 0),
                    "service": artifacts["live_search"].get("service"),
                    "reason": artifacts["live_search"].get("reason"),
                },
            }
        )

        artifacts["llm_judge"] = self._llm_judge_artifact(
            router=active_router,
            case_results=case_results,
            feedback=feedback,
            service_name=llm_service,
            allow_live=allow_live,
        )
        trace.append(
            {
                "capability": "llm_judge",
                "status": artifacts["llm_judge"]["status"],
                "details": {
                    "service": artifacts["llm_judge"].get("service"),
                    "reason": artifacts["llm_judge"].get("reason"),
                },
            }
        )

        artifacts["rag_vector"] = self._rag_vector_artifact(
            router=active_router,
            query=query,
            top_k=limit,
        )
        trace.append(
            {
                "capability": "rag_vector",
                "status": artifacts["rag_vector"]["status"],
                "details": {
                    "result_count": artifacts["rag_vector"].get("result_count", 0),
                    "reason": artifacts["rag_vector"].get("reason"),
                },
            }
        )
        return artifacts, trace

    def _default_router(self) -> Any:
        from app.core.router import get_router

        return get_router()

    def _integration_status_artifact(self) -> dict[str, Any]:
        try:
            from app.core.integration_status import get_integration_status

            payload = get_integration_status()
            capabilities = payload.get("capabilities", [])
            return {
                "status": "used",
                "capability_count": len(capabilities),
                "connected_count": sum(1 for item in capabilities if item.get("connected")),
                "not_ready": [
                    {
                        "id": item.get("id"),
                        "status": item.get("status"),
                        "connected_name_zh": item.get("connected_name_zh"),
                    }
                    for item in capabilities
                    if not item.get("connected")
                ][:8],
            }
        except Exception as exc:
            return {"status": "error", "reason": str(exc)}

    def _live_search_artifact(
        self,
        *,
        router: Any,
        query: str,
        limit: int,
        service_name: str | None,
        allow_live: bool,
    ) -> dict[str, Any]:
        if not allow_live:
            return {
                "status": "skipped",
                "reason": "allow_live=false；未触发 live search 或可能产生外部成本的检索。",
                "result_count": 0,
                "results": [],
            }
        try:
            provider = router.search(service_name)
            results = provider.search(query, limit=limit)
            return {
                "status": "used",
                "service": service_name or "default",
                "query": query,
                "result_count": len(results),
                "results": [self._safe_search_result(item) for item in results[:limit]],
            }
        except Exception as exc:
            return {
                "status": "error",
                "service": service_name or "default",
                "reason": str(exc),
                "result_count": 0,
                "results": [],
            }

    def _llm_judge_artifact(
        self,
        *,
        router: Any,
        case_results: list[dict[str, Any]],
        feedback: dict[str, Any],
        service_name: str | None,
        allow_live: bool,
    ) -> dict[str, Any]:
        if not allow_live:
            return {
                "status": "skipped",
                "service": service_name,
                "reason": "allow_live=false；未触发 LLM judge。",
            }
        try:
            llm = router.llm(service_name)
            prompt = self._llm_judge_prompt(case_results, feedback)
            if hasattr(llm, "text"):
                judgment = llm.text(prompt, max_tokens=220)
            else:
                judgment = str(llm.message(prompt, max_tokens=220))
            return {
                "status": "used",
                "service": service_name,
                "judgment": str(judgment)[:1200],
            }
        except Exception as exc:
            return {
                "status": "error",
                "service": service_name,
                "reason": str(exc),
            }

    def _rag_vector_artifact(self, *, router: Any, query: str, top_k: int) -> dict[str, Any]:
        try:
            embeddings = router.embedding().embed_texts([query])
            vector = embeddings[0]
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            results = router.vector_store().search(vector, top_k=top_k)
            return {
                "status": "used",
                "query": query,
                "result_count": len(results),
                "results": [self._safe_rag_result(item) for item in results[:top_k]],
            }
        except Exception as exc:
            return {
                "status": "error",
                "reason": str(exc),
                "result_count": 0,
                "results": [],
            }

    def _capability_query(self, cases: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for case in cases[:3]:
            parts.extend(
                [
                    str(case.get("target", "")),
                    str(case.get("team_constraint", "")),
                    str(case.get("name", "")),
                ]
            )
        text = " ".join(parts)
        if "VLA" in text or "具身" in text or "Diffusion" in text:
            return "diffusion policy robotics"
        if "SLAM" in text or "导航" in text:
            return "robot SLAM navigation localization"
        if "仿真" in text or "sim" in text.casefold():
            return "robotics sim-to-real simulation"
        return "robotics real robot deployment"

    def _safe_search_result(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_key": item.get("source_key"),
            "source_type": item.get("source_type"),
            "title": item.get("title") or item.get("source_name"),
            "url": item.get("url"),
            "snippet": str(item.get("snippet") or "")[:300],
            "retrieval_status": item.get("retrieval_status"),
        }

    def _safe_rag_result(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": item.get("candidate_id"),
            "chunk_index": item.get("chunk_index"),
            "score": item.get("score"),
            "content_preview": str(item.get("content") or item.get("text") or "")[:300],
        }

    def _llm_judge_prompt(self, case_results: list[dict[str, Any]], feedback: dict[str, Any]) -> str:
        compact_cases = [
            {
                "case_id": item["case_id"],
                "passed": item["passed"],
                "score": item["score"],
                "recommendation_level": item["recommendation_level"],
                "failed_checks": [
                    check["check_id"]
                    for check in item["checks"]
                    if not check["passed"]
                ],
            }
            for item in case_results
        ]
        compact_gaps = [
            {
                "case_id": gap["case_id"],
                "check_id": gap["check_id"],
                "priority": gap["priority"],
                "suggested_fix": gap["suggested_fix"],
            }
            for gap in feedback.get("gaps", [])
        ]
        return (
            "你是招聘评估系统的独立 judge。请审查 RSI 测试结果，指出最重要的 3 个改进动作。"
            f"\ncase_results={compact_cases}\nfeedback_gaps={compact_gaps}"
        )

    def _normalize_cases(self, cases: list[dict[str, Any]] | None, *, suite_id: str) -> list[dict[str, Any]]:
        source_cases = cases if cases is not None else self._default_cases_for_suite(suite_id)
        normalized = []
        for index, case in enumerate(source_cases, start=1):
            case_type = str(case.get("case_type") or case.get("type") or "").strip()
            if case_type == "job_candidate_ranking" or ("job_profile" in case and "candidates" in case):
                normalized.append(self._normalize_ranking_case(case, index))
                continue
            candidate_material = str(case.get("candidate_material") or "").strip()
            if not candidate_material:
                candidate_material = "空候选人材料"
            normalized.append(
                {
                    "case_type": "single_candidate",
                    "case_id": str(case.get("case_id") or f"case_{index}"),
                    "name": str(case.get("name") or f"RSI case {index}"),
                    "candidate_material": candidate_material,
                    "target": str(case.get("target") or "家庭机器人 VLA 算法工程师"),
                    "team_constraint": str(case.get("team_constraint") or "真机泛化"),
                    "expectations": dict(case.get("expectations") or {}),
                }
            )
        return normalized

    def _default_cases_for_suite(self, suite_id: str) -> list[dict[str, Any]]:
        if suite_id == "recruiting_effect_v1":
            return list(DEFAULT_RECRUITING_EFFECT_CASES)
        return list(DEFAULT_RSI_CASES)

    def _build_operator_summary(self, suite_id: str, case_results: list[dict[str, Any]]) -> dict[str, Any]:
        review_cases = [case for case in case_results if not case.get("passed")]
        visible_source = review_cases if review_cases else case_results[:5]
        visible_cards = [self._operator_case_card(case) for case in visible_source[:5]]
        return {
            "suite_id": suite_id,
            "manual_labeling_required": False,
            "human_role": "decision_maker",
            "human_touch_level": "light",
            "automation_default": "ai_runs_full_pipeline",
            "human_decisions": ["approve", "reject", "adjust"],
            "ai_automation_scope": [
                "generate_search_plan",
                "collect_evidence",
                "deduplicate_candidates",
                "score_and_rank",
                "explain_risks",
                "prepare_recommendation",
                "queue_only_exceptions_for_review",
            ],
            "review_policy": "默认只看失败或边界 case；通过 case 保留在 details，不要求人工逐个打标签。",
            "review_count": len(review_cases),
            "visible_case_count": len(visible_cards),
            "hidden_case_count": max(0, len(case_results) - len(visible_cards)),
            "coverage_domains": self._coverage_domains(case_results)[:8],
            "review_queue": [self._operator_case_card(case) for case in review_cases[:10]],
            "visible_case_cards": visible_cards,
            "next_action": (
                "优先处理 review_queue 中的失败 case。"
                if review_cases
                else "当前离线效果集通过；下一步只需补真实岗位样本或校准分数分布。"
            ),
        }

    def _operator_case_card(self, case: dict[str, Any]) -> dict[str, Any]:
        summary = dict(case.get("result_summary") or {})
        ranked = list(summary.get("ranked_candidates") or [])
        top = ranked[0] if ranked else {}
        second = ranked[1] if len(ranked) > 1 else {}
        top_score = int(top.get("score") or 0)
        second_score = int(second.get("score") or 0) if second else None
        failed_checks = [check["check_id"] for check in case.get("checks", []) if not check.get("passed")]
        card = {
            "case_id": case.get("case_id"),
            "target": case.get("target"),
            "passed": bool(case.get("passed")),
            "top_candidate_id": top.get("candidate_id"),
            "top_score": top_score,
            "top_level": top.get("recommendation_level"),
            "score_gap": top_score - second_score if second_score is not None else None,
            "failed_checks": failed_checks,
        }
        if ranked:
            card["risk_count"] = sum(int(item.get("risk_count") or 0) for item in ranked)
        return card

    def _coverage_domains(self, case_results: list[dict[str, Any]]) -> list[str]:
        domain_keywords = [
            ("AI Native FDE", ["AI Native FDE", "Agentic Builder"]),
            ("VLA", ["VLA", "具身 MLLM"]),
            ("数据平台", ["数据平台", "云端平台"]),
            ("运动控制", ["运动控制", "Sim2Real"]),
            ("嵌入式", ["嵌入式"]),
            ("SLAM", ["SLAM", "导航"]),
            ("评测", ["评测", "QA", "安全合规"]),
            ("现场", ["现场", "NPI", "制造"]),
            ("3D 感知", ["3D", "三维感知"]),
            ("硬件可靠性", ["硬件可靠性"]),
            ("产品", ["产品经理", "场景定义"]),
            ("招聘运营", ["招聘运营", "Talent Sourcer"]),
        ]
        targets = " ".join(str(case.get("target") or "") for case in case_results)
        return [domain for domain, keywords in domain_keywords if any(keyword in targets for keyword in keywords)]

    def _normalize_ranking_case(self, case: dict[str, Any], index: int) -> dict[str, Any]:
        raw_candidates = case.get("candidates") if isinstance(case.get("candidates"), list) else []
        candidates = []
        for candidate_index, candidate in enumerate(raw_candidates, start=1):
            if not isinstance(candidate, dict):
                continue
            candidate_material = str(candidate.get("candidate_material") or candidate.get("material") or "").strip()
            candidates.append(
                {
                    "candidate_id": str(candidate.get("candidate_id") or candidate.get("id") or f"candidate_{candidate_index}"),
                    "name": str(candidate.get("name") or f"Candidate {candidate_index}"),
                    "candidate_material": candidate_material or "空候选人材料",
                }
            )
        return {
            "case_type": "job_candidate_ranking",
            "case_id": str(case.get("case_id") or f"ranking_case_{index}"),
            "name": str(case.get("name") or f"Recruiting effect case {index}"),
            "job_profile": dict(case.get("job_profile") or {}),
            "candidates": candidates,
            "expectations": dict(case.get("expectations") or {}),
        }

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        if case.get("case_type") == "job_candidate_ranking":
            return self._run_ranking_case(case)
        return self._run_single_candidate_case(case)

    def _run_single_candidate_case(self, case: dict[str, Any]) -> dict[str, Any]:
        result = evaluate_candidate(
            case["candidate_material"],
            target=case["target"],
            team_constraint=case["team_constraint"],
        )
        checks = self._checks_from_expectations(case, result)
        passed = all(check["passed"] for check in checks)
        failed_checks = [check for check in checks if not check["passed"]]
        return {
            "case_id": case["case_id"],
            "name": case["name"],
            "target": case["target"],
            "team_constraint": case["team_constraint"],
            "passed": passed,
            "score": result.get("匹配评分"),
            "recommendation_level": result.get("推荐等级"),
            "result_summary": {
                "risk_count": len(result.get("风险点", [])),
                "fact_count": len(result.get("工程事实链", [])),
                "probe_count": len(result.get("追问武器库", [])),
                "feedback_status": self._path_value(result, "decision_sandbox.feedback_loop.status"),
            },
            "checks": checks,
            "feedback": (
                ["检查通过，保留该用例作为回归基线。"]
                if passed
                else [self._feedback_message(case["case_id"], check) for check in failed_checks]
            ),
        }

    def _run_ranking_case(self, case: dict[str, Any]) -> dict[str, Any]:
        ranked_candidates = []
        for candidate in case["candidates"]:
            scoring = score_candidate_against_job(case["job_profile"], candidate["candidate_material"])
            ranked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "name": candidate["name"],
                    "score": int(scoring["匹配评分"]),
                    "recommendation_level": scoring["推荐等级"],
                    "matched_skills": scoring["必备技能命中"],
                    "missing_skills": scoring["必备技能缺口"],
                    "bonus_hits": scoring["加分信号命中"],
                    "risk_hits": scoring["风险信号命中"],
                    "risk_count": len(scoring["风险点"]),
                }
            )
        ranked_candidates.sort(key=lambda item: (-int(item["score"]), str(item["candidate_id"])))
        checks = self._checks_from_ranking_expectations(case, ranked_candidates)
        passed = all(check["passed"] for check in checks)
        failed_checks = [check for check in checks if not check["passed"]]
        top_candidate = ranked_candidates[0] if ranked_candidates else {}
        return {
            "case_type": "job_candidate_ranking",
            "case_id": case["case_id"],
            "name": case["name"],
            "target": str(case["job_profile"].get("title") or ""),
            "team_constraint": "job_rubric_ranking",
            "passed": passed,
            "score": top_candidate.get("score", 0),
            "recommendation_level": top_candidate.get("recommendation_level", ""),
            "result_summary": {
                "job_title": str(case["job_profile"].get("title") or ""),
                "candidate_count": len(ranked_candidates),
                "top_candidate_id": top_candidate.get("candidate_id"),
                "ranked_candidates": ranked_candidates,
            },
            "checks": checks,
            "feedback": (
                ["检查通过，保留该招聘效果 case 作为排序回归基线。"]
                if passed
                else [self._feedback_message(case["case_id"], check) for check in failed_checks]
            ),
        }

    def _checks_from_ranking_expectations(
        self,
        case: dict[str, Any],
        ranked_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        expectations = case["expectations"]
        checks: list[dict[str, Any]] = []
        by_id = {candidate["candidate_id"]: candidate for candidate in ranked_candidates}
        observed_order = [candidate["candidate_id"] for candidate in ranked_candidates]
        top_candidate_id = observed_order[0] if observed_order else None

        if expectations.get("top_candidate_id"):
            expected = str(expectations["top_candidate_id"])
            checks.append(
                self._check(
                    "top_candidate_id",
                    top_candidate_id == expected,
                    top_candidate_id,
                    expected,
                    "岗位排序第一名不符合期望。",
                )
            )

        expected_order = [str(item) for item in expectations.get("ranking_order", [])]
        if expected_order:
            checks.append(
                self._check(
                    "ranking_order",
                    observed_order[: len(expected_order)] == expected_order,
                    observed_order,
                    expected_order,
                    "候选人排序不符合招聘效果基线。",
                )
            )

        if "min_top_score" in expectations:
            expected = int(expectations["min_top_score"])
            observed = int(ranked_candidates[0]["score"]) if ranked_candidates else 0
            checks.append(
                self._check("min_top_score", observed >= expected, observed, f">= {expected}", "第一名分数低于期望。")
            )

        if "score_gap_min" in expectations and len(ranked_candidates) >= 2:
            expected = int(expectations["score_gap_min"])
            observed = int(ranked_candidates[0]["score"]) - int(ranked_candidates[1]["score"])
            checks.append(
                self._check(
                    "score_gap_min",
                    observed >= expected,
                    observed,
                    f">= {expected}",
                    "第一名和第二名的分差不够，排序区分度不足。",
                )
            )

        for candidate_id, expected in dict(expectations.get("min_scores") or {}).items():
            candidate = by_id.get(str(candidate_id))
            observed = int(candidate["score"]) if candidate else None
            expected_score = int(expected)
            checks.append(
                self._check(
                    f"candidate_min_score:{candidate_id}",
                    observed is not None and observed >= expected_score,
                    observed,
                    f">= {expected_score}",
                    "指定候选人分数低于最低期望。",
                )
            )

        for candidate_id, expected in dict(expectations.get("max_scores") or {}).items():
            candidate = by_id.get(str(candidate_id))
            observed = int(candidate["score"]) if candidate else None
            expected_score = int(expected)
            checks.append(
                self._check(
                    f"candidate_max_score:{candidate_id}",
                    observed is not None and observed <= expected_score,
                    observed,
                    f"<= {expected_score}",
                    "指定风险候选人分数高于上限。",
                )
            )

        for candidate_id, allowed_levels in dict(expectations.get("allowed_levels") or {}).items():
            candidate = by_id.get(str(candidate_id))
            observed = candidate.get("recommendation_level") if candidate else None
            expected = [str(item) for item in allowed_levels]
            checks.append(
                self._check(
                    f"candidate_allowed_level:{candidate_id}",
                    observed in expected,
                    observed,
                    expected,
                    "指定候选人推荐等级不符合期望。",
                )
            )

        for candidate_id, required_terms in dict(expectations.get("required_risk_terms") or {}).items():
            candidate = by_id.get(str(candidate_id))
            risk_hits = [str(item) for item in candidate.get("risk_hits", [])] if candidate else []
            for term in required_terms:
                checks.append(
                    self._check(
                        f"candidate_required_risk:{candidate_id}:{term}",
                        any(str(term) in risk for risk in risk_hits),
                        risk_hits,
                        f"包含 {term}",
                        "指定候选人缺少必须暴露的岗位风险信号。",
                    )
                )

        if not checks:
            checks.append(self._check("case_executable", True, "executed", "executed", "排序用例可执行。"))
        return checks

    def _checks_from_expectations(self, case: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
        expectations = case["expectations"]
        checks: list[dict[str, Any]] = []
        score = int(result.get("匹配评分") or 0)
        level = str(result.get("推荐等级") or "")

        if "min_score" in expectations:
            expected = int(expectations["min_score"])
            checks.append(
                self._check("min_score", score >= expected, score, f">= {expected}", "候选人评分低于最低期望。")
            )
        if "max_score" in expectations:
            expected = int(expectations["max_score"])
            checks.append(
                self._check("max_score", score <= expected, score, f"<= {expected}", "候选人评分高于风险用例上限。")
            )

        allowed_levels = [str(item) for item in expectations.get("allowed_levels", [])]
        if allowed_levels:
            checks.append(
                self._check(
                    "allowed_levels",
                    level in allowed_levels,
                    level,
                    allowed_levels,
                    "推荐等级不在期望集合内。",
                )
            )

        evidence_flags = dict(expectations.get("required_evidence_flags") or {})
        evidence = dict(result.get("证据链") or {})
        for flag_name, expected_value in evidence_flags.items():
            observed = evidence.get(flag_name)
            checks.append(
                self._check(
                    f"evidence_flag:{flag_name}",
                    observed == expected_value,
                    observed,
                    expected_value,
                    "证据链布尔标记不符合期望。",
                )
            )

        risks = [str(item) for item in result.get("风险点", [])]
        for term in expectations.get("required_risk_terms", []):
            checks.append(
                self._check(
                    f"required_risk:{term}",
                    any(str(term) in risk for risk in risks),
                    risks,
                    f"包含 {term}",
                    "缺少必须暴露的风险提示。",
                )
            )
        for term in expectations.get("forbidden_risk_terms", []):
            checks.append(
                self._check(
                    f"forbidden_risk:{term}",
                    not any(str(term) in risk for risk in risks),
                    risks,
                    f"不包含 {term}",
                    "出现了禁止出现的风险提示。",
                )
            )

        for path in expectations.get("required_output_paths", []):
            value = self._path_value(result, str(path))
            checks.append(
                self._check(
                    f"required_path:{path}",
                    self._has_value(value),
                    self._safe_observed(value),
                    "present",
                    "输出缺少必须字段，说明被测链路还没有形成完整契约。",
                )
            )

        if not checks:
            checks.append(self._check("case_executable", True, "executed", "executed", "用例可执行。"))
        return checks

    def _check(
        self,
        check_id: str,
        passed: bool,
        observed: Any,
        expected: Any,
        message: str,
    ) -> dict[str, Any]:
        return {
            "check_id": check_id,
            "passed": passed,
            "observed": observed,
            "expected": expected,
            "message": message,
        }

    def _build_feedback(self, case_results: list[dict[str, Any]]) -> dict[str, Any]:
        strengths = []
        gaps = []
        for case in case_results:
            if case["passed"]:
                strengths.append(
                    {
                        "case_id": case["case_id"],
                        "message": f"{case['name']} 通过，可作为后续迭代的回归保护。",
                    }
                )
                continue
            for check in case["checks"]:
                if check["passed"]:
                    continue
                gaps.append(
                    {
                        "case_id": case["case_id"],
                        "check_id": check["check_id"],
                        "message": check["message"],
                        "observed": check["observed"],
                        "expected": check["expected"],
                        "priority": self._gap_priority(check),
                        "suggested_fix": self._suggested_fix(check),
                    }
                )
        return {
            "strengths": strengths,
            "gaps": gaps,
            "risk_level": "high" if any(gap["priority"] == "high" for gap in gaps) else ("medium" if gaps else "low"),
        }

    def _build_iteration(self, feedback: dict[str, Any]) -> dict[str, Any]:
        generated_tests = [
            {
                "type": "regression_case",
                "source_case_id": gap["case_id"],
                "name": f"锁定缺口：{gap['check_id']}",
                "assertion": gap["expected"],
                "focus": gap["suggested_fix"],
            }
            for gap in feedback["gaps"]
        ]
        next_actions = (
            [gap["suggested_fix"] for gap in feedback["gaps"]]
            if feedback["gaps"]
            else ["保持当前评估基线，并在新增业务场景时追加 RSI 用例。"]
        )
        return {
            "status": "queued" if feedback["gaps"] else "watch",
            "generated_tests": generated_tests,
            "next_actions": list(dict.fromkeys(next_actions)),
            "stop_condition": "所有高优先级 gap 关闭，且 suite_score 连续两轮达到 threshold。",
        }

    def _feedback_message(self, case_id: str, check: dict[str, Any]) -> str:
        return f"{case_id}::{check['check_id']} 未通过：{check['message']}"

    def _gap_priority(self, check: dict[str, Any]) -> str:
        check_id = str(check["check_id"])
        if check_id in {"top_candidate_id", "ranking_order"}:
            return "high"
        if "evidence_dependency_contract" in check_id or check_id.startswith("required_path"):
            return "high"
        if check_id.startswith(("min_score", "max_score", "allowed_levels", "candidate_", "score_gap")):
            return "medium"
        return "low"

    def _suggested_fix(self, check: dict[str, Any]) -> str:
        check_id = str(check["check_id"])
        if check_id in {"top_candidate_id", "ranking_order"}:
            return "校准岗位评分 rubric、技能命中和风险扣分，让真实强候选人在离线效果集里稳定排到前面。"
        if check_id.startswith("candidate_required_risk"):
            return "补强岗位风险信号匹配，避免风险候选人缺少明确扣分和解释。"
        if check_id.startswith(("candidate_", "score_gap")):
            return "校准候选人分数阈值和排序区分度，并把该 case 保留为效果回归。"
        if "evidence_dependency_contract" in check_id:
            return "把证据增强后的评估结果纳入 RSI 被测路径，并要求输出 evidence_dependency_contract。"
        if check_id.startswith("required_path"):
            return "补齐稳定输出契约，避免前端、反馈回写或后续评估读取缺失字段。"
        if check_id.startswith("required_risk"):
            return "加强风险提示规则，确保负向用例暴露关键风险。"
        if check_id.startswith(("min_score", "max_score", "allowed_levels")):
            return "校准评分阈值和推荐等级映射，并保留该用例做回归测试。"
        return "保留失败检查，下一轮迭代前先定位被测链路的输入、输出和阈值。"

    def _path_value(self, payload: dict[str, Any], path: str) -> Any:
        value: Any = payload
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
                continue
            return None
        return value

    def _has_value(self, value: Any) -> bool:
        return value is not None and value != "" and value != [] and value != {}

    def _safe_observed(self, value: Any) -> Any:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            return f"dict[{len(value)}]"
        return value
