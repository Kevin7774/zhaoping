from __future__ import annotations

import re
from typing import Any, Dict, List

from app.skills.tech_space import (
    CROSS_VALIDATION_RULES,
    EVIDENCE_RECORD_SCHEMA,
    ROBOT_ROLES_METADATA,
    STATIC_DYNAMIC_DECISION_TABLE,
    get_capabilities_for_role,
    get_role_capability_traceability,
)


MULTIMODAL_MULTI_SOURCE_INPUTS: Dict[str, List[str]] = {
    "招聘数据": ["JD", "简历", "面试反馈", "招聘漏斗", "薪酬数据"],
    "行业数据": ["机器人公司", "融资新闻", "产品发布", "技术报告"],
    "技术数据": ["论文", "专利", "GitHub", "Hugging Face", "ModelScope"],
    "AI 社区": ["AI 论坛", "Discord", "微信群", "知乎", "即刻", "Reddit"],
    "AI 活动": ["Hackathon", "Meetup", "会议", "直播", "Workshop"],
    "视频内容": ["B站", "YouTube", "技术演讲", "Demo 视频", "字幕"],
    "内部数据": ["公司战略", "团队结构", "历史 JD", "候选人库"],
    "业务请求输入": ["一句招聘需求", "目标岗位", "候选人材料", "周报数据"],
}


AI_NATIVE_INFRASTRUCTURE: Dict[str, List[str]] = {
    "MCP Connectors": ["外部 API", "内部系统", "多源工具"],
    "Workflow Orchestrator": ["A/B/C/D 场景编排", "状态流转", "失败恢复"],
    "Skills": ["岗位画像", "简历解析", "人才地图", "视频解析", "GitHub 分析"],
    "RAG / Retrieval": ["行业资料", "岗位库", "候选人库", "公司库"],
    "Memory": ["招聘上下文", "候选人历史", "岗位偏好", "反馈记录"],
    "Evaluation": ["评分卡", "人工校准", "输出质量评估"],
    "Guardrails": ["数据脱敏", "权限控制", "合规检查", "人工审核"],
}


KNOWLEDGE_ASSETS: List[str] = [
    "家庭机器人技术路线库",
    "全栈岗位能力矩阵库",
    "目标公司与团队库",
    "AI 原生人才画像库",
    "候选人画像库",
    "面试题与评分卡库",
    "招聘市场与薪酬数据库",
    "历史反馈与成功画像库",
]


DATA_FLYWHEEL_LOOP: List[str] = [
    "输出结果",
    "人工修改",
    "面试反馈",
    "offer / reject 结果",
    "入职表现",
    "岗位画像修正",
    "候选人评分校准",
    "人才地图更新",
    "知识库持续进化",
]


SCENARIO_WORKFLOWS: Dict[str, Dict[str, Any]] = {
    "scenario_a_job_profile_jd": {
        "name_zh": "场景 A：岗位画像与 JD",
        "input": "业务请求输入：一句招聘需求，例如：我们想招一个家庭机器人 VLA 算法工程师。",
        "workflow": [
            "识别岗位所属技术层",
            "匹配家庭机器人技术路线",
            "拆解能力矩阵",
            "生成岗位画像",
            "生成 JD",
            "生成面试问题",
            "生成候选人来源建议",
        ],
        "output_fields": ["岗位定位", "能力矩阵", "JD", "面试问题", "候选人来源"],
    },
    "scenario_b_talent_map": {
        "name_zh": "场景 B：人才地图",
        "input": "业务请求输入：目标岗位或技术方向，例如：灵巧手控制负责人。",
        "workflow": [
            "拆解技术能力",
            "识别适配行业",
            "筛选目标公司 / 实验室",
            "生成候选人来源层级",
            "生成搜索关键词",
            "生成触达策略",
        ],
        "output_fields": ["目标公司", "目标团队", "候选人来源", "搜索关键词", "触达策略"],
    },
    "scenario_c_candidate_evaluation": {
        "name_zh": "场景 C：候选人评估",
        "input": "业务请求输入：候选人材料，包括简历、作品、论文、GitHub、视频或项目经历。",
        "workflow": [
            "Task A：解构工程事实链",
            "Task B/C：交叉核验与本地 RAG 增强",
            "Task D：模拟能力向量平移",
            "Human-in-the-loop：生成苏格拉底追问与反馈闭环",
        ],
        "output_fields": ["工程事实链", "能力频谱", "增量价值", "能力平移推演", "潜在工程边界", "追问武器库", "证据链"],
        "scoring_weights": {
            "家庭机器人场景相关性": 20,
            "真实机器人/硬件部署经验": 20,
            "核心技术能力匹配度": 25,
            "项目深度与独立贡献": 15,
            "跨学科协作能力": 10,
            "阶段匹配度与稳定性": 10,
        },
    },
    "scenario_d_weekly_report": {
        "name_zh": "场景 D：招聘周报",
        "input": "业务请求输入：本周招聘进展、候选人状态、面试反馈、市场信号和下周重点。",
        "workflow": [
            "汇总本周招聘结论",
            "梳理关键岗位进展",
            "提取 Top 候选人",
            "归纳市场人才信号",
            "识别招聘风险",
            "生成下周行动建议",
            "沉淀可回流数据",
        ],
        "output_fields": ["本周招聘结论", "关键岗位进展", "Top 候选人", "市场人才信号", "招聘风险", "下周行动建议"],
    },
}


ROLE_ALIASES: Dict[str, List[str]] = {
    "vla_embodied_expert": [
        "vla",
        "算法工程师",
        "家庭机器人算法",
        "具身大脑",
        "具身智能",
        "机器人基础模型",
        "action token",
        "diffusion policy",
    ],
    "slam_navigation_expert": ["slam", "导航", "建图", "定位", "空间计算", "重定位"],
    "dexterous_hand_control": ["灵巧手", "多指", "触觉", "手内操纵", "dexterous"],
    "motion_control_mpc_wbc": ["运动控制", "mpc", "wbc", "全身控制", "四足", "人形"],
    "robot_data_infrastructure": ["数据采集", "遥操作", "数据闭环", "teleop", "数据平台"],
    "embedded_foc_engineer": ["嵌入式", "foc", "电机", "固件", "rtos", "驱动"],
    "qa_reliability_engineer": ["可靠性", "测试", "量产", "整机测试", "质量"],
    "manipulation_grasping": ["抓取", "操作", "机械臂", "操作规划", "柔性物体"],
    "vision_3d_algorithm": ["3d视觉", "rgb-d", "点云", "6d位姿", "重建"],
    "multimodal_perception": ["多模态感知", "vlm", "语音", "意图", "grounding"],
    "world_model_simulation": ["世界模型", "仿真", "isaac", "mujoco", "合成数据"],
    "robot_system_architect": ["系统架构", "整机", "架构师", "软硬件协同", "技术负责人"],
}


HOME_ROBOT_TALENT_SOURCE_MAP: Dict[str, Dict[str, List[str]]] = {
    "robot_system_architect": {
        "priority_sources": ["特斯拉 Optimus", "宇树", "智元机器人", "开普勒", "小米物理 AI 组", "小鹏鹏行", "大疆"],
        "secondary_sources": ["自动驾驶系统架构团队", "复杂智能硬件平台团队", "工业机器人整机平台团队"],
        "labs": ["CMU Robotics Institute", "MIT CSAIL Robotics", "Stanford AI/Robotics", "清华智能产业研究院", "上海 AI Lab 具身智能方向"],
    },
    "slam_navigation_expert": {
        "priority_sources": ["科沃斯", "石头科技", "追觅", "高仙自动化", "九号机器人"],
        "secondary_sources": ["低速无人车公司", "AR 空间计算团队", "自动驾驶泊车/AVP 团队"],
        "labs": ["港科大 Robotics Institute", "清华智能产业研究院", "浙江大学机器人实验室"],
    },
    "dexterous_hand_control": {
        "priority_sources": ["因时机器人", "大寰机器人", "帕西尼感知", "柔触机器人", "智元机器人"],
        "secondary_sources": ["工业机械臂公司", "仿真操作团队", "工业装配自动化团队"],
        "labs": ["清华机器人实验室", "北大具身智能实验室", "上海交大机器人研究所"],
    },
    "motion_control_mpc_wbc": {
        "priority_sources": ["宇树", "逐际动力", "乐聚机器人", "优必选", "智元机器人"],
        "secondary_sources": ["移动机器人公司", "机械臂控制团队", "自动驾驶控制团队"],
        "labs": ["MIT Biomimetic Robotics Lab", "ETH Robotics Systems Lab", "浙大控制学院机器人方向"],
    },
    "vla_embodied_expert": {
        "priority_sources": ["Physical Intelligence", "World Labs", "银河通用", "智元机器人", "小米物理 AI 组"],
        "secondary_sources": ["大模型多模态团队", "自动驾驶世界模型/预测团队", "机器人基础模型团队"],
        "labs": ["Stanford IRIS", "Berkeley BAIR", "北大/清华具身智能实验室"],
    },
    "robot_data_infrastructure": {
        "priority_sources": ["自动驾驶数据闭环团队", "具身智能遥操作团队", "机器人数据平台团队"],
        "secondary_sources": ["VR/AR 交互团队", "游戏动捕团队", "数据标注平台团队"],
        "labs": ["CMU Robotics Institute", "上海 AI Lab 具身智能方向", "北航机器人相关实验室"],
    },
    "embedded_foc_engineer": {
        "priority_sources": ["大疆动力组", "汇川技术", "步科", "大族电机", "拓普集团"],
        "secondary_sources": ["无人机公司", "工业自动化公司", "汽车电子控制器团队"],
        "labs": ["电机控制实验室", "嵌入式系统实验室", "机器人驱动与控制实验室"],
    },
    "qa_reliability_engineer": {
        "priority_sources": ["科沃斯", "石头科技", "追觅", "九号公司", "小米硬件测试团队"],
        "secondary_sources": ["家电公司", "汽车电子测试团队", "消费硬件可靠性团队"],
        "labs": ["可靠性工程实验室", "智能硬件测试平台团队"],
    },
}


HOME_ROBOT_SPECIAL_CHECKS: Dict[str, List[str]] = {
    "vla_embodied_expert": [
        "是否做过机器人第一视角数据",
        "是否理解 action token 和连续动作离散化",
        "是否有 imitation learning / diffusion policy / VLA 经验",
        "是否懂机器人操作任务而非纯文本多模态",
        "是否能处理长程任务失败恢复",
        "是否有真实机器人部署经验",
        "是否理解家庭场景中的泛化问题",
    ],
    "slam_navigation_expert": [
        "是否处理过家具变化、低纹理、狭窄通道和人宠动态障碍",
        "是否做过真实传感器标定和长期重定位",
        "是否能把 SLAM 输出服务于导航、避障和操作任务",
    ],
    "dexterous_hand_control": [
        "是否有触觉、滑动检测或力控闭环经验",
        "是否做过多指协同和手内操纵",
        "是否能处理家庭物体材质、形状和安全约束",
    ],
    "robot_data_infrastructure": [
        "是否做过多传感器、多频率数据时间戳对齐",
        "是否能清洗失败遥操作数据而不是简单丢弃",
        "是否理解数据质量对 VLA/模仿学习策略崩溃的影响",
    ],
}


def infer_role_key(text: str) -> str:
    normalized = text.lower()
    scores: dict[str, int] = {}
    for role_key, aliases in ROLE_ALIASES.items():
        role = ROBOT_ROLES_METADATA[role_key]
        haystack = [role["name_zh"], *aliases, *role["tech_layer"]]
        scores[role_key] = sum(1 for item in haystack if item.lower() in normalized)
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "robot_system_architect"


def _role_capability_names(role_key: str) -> List[str]:
    return [capability["capability_name_zh"] for capability in get_capabilities_for_role(role_key)]


def _role_capability_profile_summaries(role_key: str) -> List[Dict[str, Any]]:
    traceability = get_role_capability_traceability(role_key)
    summaries: List[Dict[str, Any]] = []
    for capability in traceability["capabilities"]:
        summaries.append(
            {
                "capability_id": capability["capability_id"],
                "能力名称": capability["capability_name_zh"],
                "静态部分": capability["static_parts"],
                "动态校准项": capability["dynamic_parts"],
                "技术路线细分": [
                    {
                        "route_id": route["route_id"],
                        "名称": route["name_zh"],
                        "关键词": route["keywords"],
                        "验证问题": route["validation_questions"],
                    }
                    for route in capability["route_breakdown"]
                ],
                "证据要求": capability["evidence_requirements"],
                "待验证假设": capability["open_assumptions"],
                "长期记忆信号": capability["memory_signals"],
                "验证状态": capability["validation_status"],
            }
        )
    return summaries


def _role_traceability_summary(role_key: str) -> Dict[str, Any]:
    traceability = get_role_capability_traceability(role_key)
    return {
        "静态基座": traceability["static_base"],
        "动态校准目标": traceability["dynamic_calibration_targets"],
        "交叉验证规则": traceability["cross_validation_rules"],
        "证据记录字段": EVIDENCE_RECORD_SCHEMA,
        "长期记忆回流": traceability["long_term_memory_targets"],
        "当前状态": "静态基线已生成，仍需接入搜索证据和人工反馈后升级为 cross_validated 或 human_approved。",
    }


def generate_job_profile_and_jd(requirement: str) -> Dict[str, Any]:
    role_key = infer_role_key(requirement)
    role = ROBOT_ROLES_METADATA[role_key]
    capabilities = get_capabilities_for_role(role_key)
    special_checks = HOME_ROBOT_SPECIAL_CHECKS.get(role_key, [])
    target_sources = HOME_ROBOT_TALENT_SOURCE_MAP.get(role_key, {})

    return {
        "岗位定位": f"{role['name_zh']}，位于家庭机器人技术层 {', '.join(role['tech_layer'])}，负责把相关算法或工程能力接入真实家庭场景闭环。",
        "核心任务": [
            f"围绕{capability['capability_name_zh']}解决家庭机器人落地问题。"
            for capability in capabilities
        ],
        "能力矩阵": {
            "必备能力": _role_capability_names(role_key),
            "能力画像": _role_capability_profile_summaries(role_key),
            "加分能力": special_checks or role.get("suggested_questions", []),
            "排除项": role["exclusion_keywords"],
        },
        "证据链与验证": _role_traceability_summary(role_key),
        "JD": {
            "职责": [
                "负责家庭机器人目标场景下的技术方案设计、实现、评估和迭代。",
                "与感知、控制、硬件、数据和产品团队协同打通真实机器人闭环。",
                "沉淀可复用的评测指标、失败案例和工程化部署流程。",
            ],
            "要求": _role_capability_names(role_key),
            "经验": ["有真实机器人、智能硬件、自动驾驶或工业自动化项目经验", "能说明个人独立贡献和上线/实机验证结果"],
            "加分项": special_checks,
        },
        "面试问题": {
            "技术面": [node for capability in capabilities for node in capability["evaluation_nodes"]],
            "项目面": ["请拆解一个你独立负责的真实项目：输入、输出、模块边界、失败点和验证指标是什么？"],
            "场景面": special_checks,
        },
        "候选人来源": {
            "公司": target_sources.get("priority_sources", role["target_targets"]),
            "实验室": target_sources.get("labs", []),
            "岗位关键词": build_search_keywords(role_key),
            "来源验证要求": [
                "目标公司列表必须由招聘站、公司官网、新闻/融资、论文/专利或人工触达结果定期校准。",
                "次优来源必须说明可迁移能力，不把行业相似直接等同于岗位匹配。",
                "候选人个人信息只记录公开且与招聘评估相关的职业线索。",
            ],
        },
    }


def build_search_keywords(role_key: str) -> List[str]:
    role = ROBOT_ROLES_METADATA[role_key]
    capabilities = get_capabilities_for_role(role_key)
    keywords = [role["name_zh"], *ROLE_ALIASES.get(role_key, [])]
    for capability in capabilities:
        keywords.extend(capability["keywords"])
    return list(dict.fromkeys(keywords))


def build_talent_map(target: str) -> Dict[str, Any]:
    role_key = infer_role_key(target)
    role = ROBOT_ROLES_METADATA[role_key]
    source_map = HOME_ROBOT_TALENT_SOURCE_MAP.get(role_key, {})
    priority_sources = source_map.get("priority_sources", role["target_targets"])
    secondary_sources = source_map.get("secondary_sources", [])
    labs = source_map.get("labs", [])
    keywords = build_search_keywords(role_key)
    outreach_strategy = (
        f"我们在找{role['name_zh']}，重点不是泛机器人关键词，而是"
        f"{', '.join(_role_capability_names(role_key))}在家庭机器人真实场景中的落地经验。"
        "想了解你是否做过实机闭环、失败恢复和跨模块协同。"
    )

    return {
        "目标公司": priority_sources,
        "目标团队": labs + secondary_sources,
        "候选人来源": {
            "优先来源公司": priority_sources,
            "次优来源公司": secondary_sources,
            "高校/实验室": labs,
        },
        "搜索关键词": keywords,
        "触达策略": outreach_strategy,
        "溯源验证计划": _role_traceability_summary(role_key),
        "能力细分": _role_capability_profile_summaries(role_key),
        "优先来源公司": priority_sources,
        "次优来源公司": secondary_sources,
        "高校/实验室": labs,
        "候选人关键词": keywords,
        "排除来源": role["exclusion_keywords"],
        "触达话术": outreach_strategy,
    }


def _contains_any(text: str, terms: List[str]) -> bool:
    return any(term.casefold() in text for term in terms)


def _extract_engineering_metrics(candidate_material: str) -> List[Dict[str, Any]]:
    metric_patterns = [
        ("latency", "控制回路延迟", r"(\d+(?:\.\d+)?)\s*(ms|毫秒)"),
        ("frequency", "数据采集频率", r"(\d+(?:\.\d+)?)\s*(hz|khz|fps|帧/秒)"),
        ("scale", "数据规模", r"(\d+(?:\.\d+)?)\s*(小时|条|万条|轨迹|episodes?|demos?)"),
    ]
    metrics: List[Dict[str, Any]] = []
    for metric_id, label, pattern in metric_patterns:
        for match in re.finditer(pattern, candidate_material, flags=re.IGNORECASE):
            value, unit = match.groups()
            metrics.append(
                {
                    "id": metric_id,
                    "label": label,
                    "value": f"{value}{unit}",
                    "evidence": candidate_material[max(0, match.start() - 28): match.end() + 28].strip(),
                    "confidence": 0.72,
                }
            )
    return metrics[:8]


def _metric_value(metrics: List[Dict[str, Any]], metric_id: str) -> str | None:
    for metric in metrics:
        if metric["id"] == metric_id:
            return str(metric["value"])
    return None


def _fact_status(active: bool) -> str:
    return "已看到事实" if active else "未量化"


def _fact(
    fact_id: str,
    label: str,
    dimension: str,
    value: str,
    evidence: str,
    confidence: float,
    *,
    metric: bool = False,
    keywords: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "id": fact_id,
        "label": label,
        "dimension": dimension,
        "status": "observed",
        "value": value,
        "evidence": evidence,
        "source": "resume_payload",
        "verification_status": "candidate_quantified" if metric else "candidate_claim_only",
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "keywords": keywords or [],
        "validation_evidence": [],
    }


def _build_engineering_fact_chain(
    candidate_material: str,
    role_key: str,
    matched_keywords: List[str],
    has_real_robot: bool,
    has_sim_only_risk: bool,
    has_ownership: bool,
    has_home_context: bool,
) -> List[Dict[str, Any]]:
    text = candidate_material.casefold()
    metrics = _extract_engineering_metrics(candidate_material)
    latency = _metric_value(metrics, "latency")
    frequency = _metric_value(metrics, "frequency")
    data_terms = ["遥操作", "数据采集", "数据清洗", "多摄像头", "时间戳", "同步", "dataset", "teleop"]
    generalization_terms = ["泛化", "长尾", "domain randomization", "sim-to-real", "家具", "家庭", "失败恢复", "ood"]
    control_terms = ["控制", "ros", "rtos", "ethercat", "can", "闭环", "实时", "mpc", "wbc"]
    simulation_terms = ["isaac", "mujoco", "genesis", "omniverse", "仿真"]

    facts: List[Dict[str, Any]] = []
    if matched_keywords:
        facts.append(
            _fact(
                "fact_role_keywords",
                "岗位能力关键词命中",
                "algorithm_research",
                " / ".join(matched_keywords[:8]),
                "候选人材料中出现了岗位能力库的原文关键词；这只是事实命中，不等于能力已被证明。",
                0.52 + min(len(matched_keywords), 6) * 0.04,
                keywords=matched_keywords[:8],
            )
        )
    if frequency:
        facts.append(
            _fact(
                "fact_data_frequency",
                "数据采集频率",
                "data_loop",
                frequency,
                next(metric["evidence"] for metric in metrics if metric["id"] == "frequency"),
                0.78,
                metric=True,
                keywords=["数据采集频率", "frequency"],
            )
        )
    elif _contains_any(text, data_terms):
        facts.append(
            _fact(
                "fact_data_loop",
                "数据链路事实",
                "data_loop",
                "候选人材料提到数据采集/清洗/同步，但没有量化频率或规模。",
                "候选人材料包含数据采集、数据清洗、遥操作、多摄像头、时间戳或同步相关词。",
                0.55,
                keywords=[term for term in data_terms if term.casefold() in text][:6],
            )
        )
    if latency:
        facts.append(
            _fact(
                "fact_control_latency",
                "控制回路延迟",
                "real_time_control",
                latency,
                next(metric["evidence"] for metric in metrics if metric["id"] == "latency"),
                0.82,
                metric=True,
                keywords=["控制回路延迟", "latency"],
            )
        )
    elif _contains_any(text, control_terms):
        facts.append(
            _fact(
                "fact_control_loop",
                "控制闭环事实",
                "real_time_control",
                "候选人材料提到控制/ROS/实时链路，但没有量化延迟或 jitter。",
                "候选人材料包含控制、ROS、实时、闭环、MPC/WBC、总线或 RTOS 相关词。",
                0.53,
                keywords=[term for term in control_terms if term.casefold() in text][:6],
            )
        )
    if _contains_any(text, generalization_terms):
        facts.append(
            _fact(
                "fact_generalization",
                "模型泛化策略",
                "generalization",
                "候选人材料提到泛化、长尾、Sim-to-Real、家庭变化或失败恢复。",
                "候选人材料包含泛化、长尾、domain randomization、sim-to-real、家具、家庭、失败恢复或 OOD 相关词。",
                0.62,
                keywords=[term for term in generalization_terms if term.casefold() in text][:6],
            )
        )
    if _contains_any(text, simulation_terms):
        facts.append(
            _fact(
                "fact_simulation_depth",
                "仿真复杂度",
                "simulation",
                "候选人材料提到 Isaac/MuJoCo/Genesis/Omniverse 或仿真环境。",
                "候选人材料包含仿真平台或仿真任务构建相关词。",
                0.6,
                keywords=[term for term in simulation_terms if term.casefold() in text][:6],
            )
        )
    if has_real_robot:
        facts.append(
            _fact(
                "fact_real_robot",
                "实机闭环证据",
                "deployment",
                "候选人材料提到实机、真实机器人、部署、量产、硬件、ROS 或机器人。",
                "候选人材料包含实机/真实机器人/部署/量产/硬件/ROS/机器人相关词。",
                0.66,
                keywords=["实机", "真实机器人", "部署", "量产", "硬件", "ROS"],
            )
        )
    if has_ownership:
        facts.append(
            _fact(
                "fact_ownership",
                "独立贡献边界",
                "ownership",
                "候选人材料提到负责、主导、Owner、Lead 或独立贡献。",
                "候选人材料包含责任边界相关表达。",
                0.6,
                keywords=["负责", "主导", "Owner", "Lead", "独立"],
            )
        )
    if role_key == "robot_data_infrastructure" or _contains_any(text, ["时间戳", "同步", "多频率", "对齐"]):
        facts.append(
            _fact(
                "fact_time_sync_sensitivity",
                "时间同步敏感度",
                "sync_sensitivity",
                "候选人材料提到多源同步、时间戳、多频率或对齐。",
                "候选人材料包含时间戳、同步、多频率或对齐相关词。",
                0.68,
                keywords=["时间戳", "同步", "多频率", "对齐"],
            )
        )
    if has_home_context:
        facts.append(
            _fact(
                "fact_home_context",
                "家庭场景约束",
                "home_context",
                "候选人材料提到家庭、家用、室内、人宠、家具或长尾场景。",
                "候选人材料包含家庭场景相关上下文。",
                0.58,
                keywords=["家庭", "家用", "室内", "人宠", "家具", "长尾"],
            )
        )
    return facts


def _energy_label(score: int | None) -> str:
    if score is None:
        return "数据不足，无法推演"
    if score >= 76:
        return "性能涌现点"
    if score <= 42:
        return "系统崩溃点"
    return "待验证边界"


def _build_capability_spectrum(
    facts: List[Dict[str, Any]],
    text: str,
    matched_keywords: List[str],
    has_sim_only_risk: bool,
) -> List[Dict[str, Any]]:
    dimension_fact_map: Dict[str, List[Dict[str, Any]]] = {}
    for fact in facts:
        dimension_fact_map.setdefault(str(fact.get("dimension")), []).append(fact)
    text_signals = {
        "cross_module": ["软硬件", "跨团队", "控制", "感知", "数据", "系统集成"],
    }
    items = [
        ("algorithm_research", "纯算法研究区", ["algorithm_research"], "模型、策略、论文/开源复现和算法理解深度。"),
        ("simulation_lab", "仿真验证区", ["simulation"], "仿真任务构建、物理参数、合成数据和 Sim-to-Real 准备度。"),
        ("engineering_landing", "工程落地区", ["deployment", "real_time_control"], "真实机器人、硬件、ROS、部署、调试和故障恢复。"),
        ("sync_sensitivity", "时间同步敏感度", ["sync_sensitivity", "data_loop", "real_time_control"], "多源数据频率、延迟、对齐、丢帧和控制链路抖动。"),
        ("cross_module", "跨模块协同区", ["ownership"], "感知、控制、硬件、数据和产品团队之间的接口经验。"),
        ("home_generalization", "家庭泛化区", ["home_context", "generalization"], "家具变化、人宠干扰、长尾失败和真实家庭任务泛化。"),
    ]
    spectrum: List[Dict[str, Any]] = []
    for item_id, label, dimensions, boundary in items:
        supporting_facts = [fact for dimension in dimensions for fact in dimension_fact_map.get(dimension, [])]
        if item_id == "cross_module" and _contains_any(text, text_signals["cross_module"]):
            supporting_facts = supporting_facts or [
                _fact(
                    "fact_cross_module_terms",
                    "跨模块协同词命中",
                    "cross_module",
                    "候选人材料提到软硬件、跨团队、控制、感知、数据或系统集成。",
                    "候选人材料包含跨模块协同相关词。",
                    0.48,
                    keywords=[term for term in text_signals["cross_module"] if term.casefold() in text][:6],
                )
            ]
        if not supporting_facts:
            energy = None
            temperature = "muted"
            evidence_state = "insufficient_data"
        else:
            confidence = sum(float(fact.get("confidence", 0)) for fact in supporting_facts) / len(supporting_facts)
            verified_bonus = 12 if any(fact.get("verification_status") == "cross_validated" for fact in supporting_facts) else 0
            quantified_bonus = 8 if any(fact.get("verification_status") == "candidate_quantified" for fact in supporting_facts) else 0
            risk_penalty = 14 if item_id == "engineering_landing" and has_sim_only_risk else 0
            keyword_bonus = min(len(matched_keywords), 6) * 3 if item_id == "algorithm_research" else 0
            energy = int(max(18, min(96, confidence * 78 + verified_bonus + quantified_bonus + keyword_bonus - risk_penalty)))
            temperature = "warm" if energy >= 76 else ("cold" if energy <= 42 else "neutral")
            evidence_state = "evidence_supported" if any(fact.get("verification_status") == "cross_validated" for fact in supporting_facts) else "candidate_claim_only"
        spectrum.append(
            {
                "id": item_id,
                "label": label,
                "energy": energy,
                "signal": _energy_label(energy),
                "boundary": boundary,
                "temperature": temperature,
                "evidence_state": evidence_state,
                "supporting_fact_ids": [str(fact.get("id")) for fact in supporting_facts],
                "blocked_reason": None if supporting_facts else "上游事实链没有提供该能力边界的可观察事实。",
            }
        )
    return spectrum


def _constraint_focus_terms(team_constraint: str) -> List[str]:
    normalized = team_constraint.casefold()
    groups = {
        "真机泛化": ["真机", "实机", "部署", "sim-to-real", "泛化", "长尾", "家庭"],
        "动作延迟": ["延迟", "时延", "实时", "控制", "jitter", "同步"],
        "数据闭环": ["数据", "遥操作", "采集", "清洗", "时间戳", "多摄像头"],
        "灵巧操作": ["抓取", "操作", "灵巧手", "触觉", "柔性"],
        "系统联调": ["软硬件", "系统", "ros", "总线", "联调", "故障"],
    }
    for label, terms in groups.items():
        if label in normalized or any(term in normalized for term in terms):
            return terms
    return [term for term in re.split(r"[\s,，/]+", team_constraint) if term][:6] or ["真机", "泛化", "工程落地"]


def _projection_score(facts: List[Dict[str, Any]], focus_terms: List[str], aperture_weight: float) -> int:
    weighted = 0.0
    for fact in facts:
        haystack = f"{fact.get('label', '')} {fact.get('value', '')} {fact.get('evidence', '')}".casefold()
        verification = fact.get("verification_status")
        verification_weight = 1.0 if verification == "cross_validated" else (0.68 if verification == "candidate_quantified" else 0.42)
        if any(term.casefold() in haystack for term in focus_terms):
            weighted += float(fact.get("confidence", 0)) * 58 * verification_weight
        elif fact.get("status") == "observed":
            weighted += float(fact.get("confidence", 0)) * 20 * verification_weight
    base = min(100, weighted)
    return int(max(0, min(100, base * (0.72 + min(max(aperture_weight, 0.0), 1.0) * 0.28))))


def _build_projection(
    facts: List[Dict[str, Any]],
    team_constraint: str,
    aperture_weight: float,
) -> List[Dict[str, Any]]:
    focus_terms = _constraint_focus_terms(team_constraint)
    active_facts = [
        fact for fact in facts
        if fact.get("verification_status") in {"cross_validated", "candidate_quantified"}
    ]
    projections = []
    for fact in active_facts[:4]:
        score = _projection_score([fact], focus_terms, aperture_weight)
        if fact.get("verification_status") == "cross_validated":
            transfer = "强平移" if score >= 70 else ("弱平移" if score < 45 else "可验证平移")
            projection_status = "evidence_supported"
        else:
            transfer = "待核验平移"
            projection_status = "requires_cross_validation"
        projections.append(
            {
                "from_fact": f"{fact['label']}：{fact['value']}",
                "to_team_need": f"当前卡点「{team_constraint}」",
                "transfer": transfer,
                "transfer_score": score,
                "projection_status": projection_status,
                "supporting_fact_ids": [fact["id"]],
                "projection": f"只能基于已观察事实「{fact['label']}」推演其与「{team_constraint}」的潜在关系；未被 RAG/公开信源支持时不得当作确定能力。",
                "validation_needed": f"面试中要求候选人给出 {fact['label']} 的输入、输出、失败点和量化指标。",
            }
        )
    return projections


def _build_hidden_limits(
    has_real_robot: bool,
    has_sim_only_risk: bool,
    has_ownership: bool,
    has_home_context: bool,
    missing_core: List[str],
) -> List[str]:
    limits: List[str] = []
    if not has_real_robot:
        limits.append("实机闭环证据不足，真机部署阶段可能需要补 1-2 周的硬件/ROS 调试上下文。")
    if has_sim_only_risk:
        limits.append("仿真经验较突出，但需要确认物理参数、传感器噪声和执行器延迟如何迁移到真机。")
    if not has_ownership:
        limits.append("独立贡献边界不清晰，需要拆出他本人负责的模块、接口和上线结果。")
    if not has_home_context:
        limits.append("家庭长尾场景经验不足，需要验证能否处理家具变化、人宠干扰和开放词表物体。")
    if missing_core:
        limits.append(f"能力覆盖仍有空白：{', '.join(missing_core[:3])}。")
    return limits or ["当前材料没有暴露明显硬边界，但仍需要通过项目复盘和代码/实机记录做交叉确认。"]


def _build_probe_toolkit(team_constraint: str, projections: List[Dict[str, Any]], hidden_limits: List[str]) -> List[Dict[str, Any]]:
    probes: List[Dict[str, Any]] = []
    for index, projection in enumerate(projections[:2], start=1):
        status_clause = "已被证据支持" if projection.get("projection_status") == "evidence_supported" else "目前只来自候选人材料，尚未被外部证据支持"
        probes.append(
            {
                "id": f"probe_{index}",
                "question": (
                    f"你材料中的「{projection['from_fact']}」{status_clause}。如果迁移到我们「{team_constraint}」这个卡点，"
                    "请给出第一天要量化的三个指标、采集方式和失败退出条件。"
                ),
                "intent": "验证能力是否能从既有事实平移到当前团队卡点。",
                "success_signal": "能给出指标、基线、失败模式、排查顺序和验证数据，而不是只复述项目名。",
                "feedback_key": f"{projection['transfer']}_{index}",
            }
        )
    if hidden_limits:
        probes.append(
            {
                "id": f"probe_{len(probes) + 1}",
                "question": f"当前上游证据显示「{hidden_limits[0]}」。请把这个边界拆成一个 3 天验证计划：输入数据、硬件依赖、观察指标、停止条件分别是什么？",
                "intent": "验证候选人是否能正视能力边界，并设计可执行补偿路径。",
                "success_signal": "能把边界转成实验计划、依赖资源、退出条件和风险缓释动作。",
                "feedback_key": "hidden_limit_recovery",
            }
        )
    if not probes:
        probes.append(
            {
                "id": "probe_1",
                "question": f"目前材料和检索上下文不足以支撑「{team_constraint}」方向的能力平移。请候选人现场补充一个真实项目的原始日志、指标截图或代码入口，并解释输入、输出和失败样本。",
                "intent": "在证据不足时先补齐上游事实，不进入无依据推演。",
                "success_signal": "能提供可复核材料或明确承认没有相关经验。",
                "feedback_key": "insufficient_data_recovery",
            }
        )
    return probes[:3]


def _build_narrative_stream(
    team_constraint: str,
    projections: List[Dict[str, Any]],
    facts: List[Dict[str, Any]],
    hidden_limits: List[str],
) -> Dict[str, Any]:
    supported = [item for item in projections if item.get("projection_status") == "evidence_supported"]
    quantified = [item for item in projections if item.get("projection_status") == "requires_cross_validation"]
    if supported:
        status = "evidence_supported_projection"
        core = f"围绕「{team_constraint}」，当前最强因果链是：{supported[0]['from_fact']} -> {supported[0]['to_team_need']}。"
    elif quantified:
        status = "candidate_quantified_requires_validation"
        core = f"围绕「{team_constraint}」，只能基于候选人自述的量化事实做待核验推演：{quantified[0]['from_fact']}。"
    else:
        status = "insufficient_data"
        core = f"围绕「{team_constraint}」，上游事实链和核验证据不足，系统不生成能力平移结论。"
    return {
        "status": status,
        "core_incremental_value": core,
        "causal_chain": [
            {
                "step": "resume_fact",
                "fact_ids": [fact["id"] for fact in facts],
                "state": "observed" if facts else "missing",
            },
            {
                "step": "verified_projection",
                "projection_count": len(supported),
                "state": "ready" if supported else ("requires_cross_validation" if quantified else "blocked"),
            },
            {
                "step": "probing",
                "state": "target_evidence_gap" if not supported else "target_transfer_claim",
            },
        ],
        "paragraphs": [
            core,
            "所有推演只允许引用上游事实链与核验状态；未命中的维度保留为数据缺口，不转写成能力判断。",
            f"当前主要边界：{hidden_limits[0] if hidden_limits else '暂无可由事实链支撑的边界结论。'}",
        ],
        "evidence_gaps": hidden_limits,
    }


def _flatten_evidence_context(capability_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    rag = capability_context.get("本地RAG") or {}
    for item in rag.get("results", []):
        content = str(item.get("content") or "")
        if not content:
            continue
        records.append(
            {
                "source_type": "local_rag",
                "title": f"candidate:{item.get('candidate_id', 'unknown')} chunk:{item.get('chunk_index', 'unknown')}",
                "snippet": content,
                "score": item.get("score"),
                "url": None,
            }
        )
    public = ((capability_context.get("公开检索") or {}).get("实时检索") or {})
    for item in public.get("results", []):
        snippet = " ".join(
            str(value or "")
            for value in [item.get("title"), item.get("snippet"), item.get("source_name")]
            if value
        )
        if not snippet:
            continue
        records.append(
            {
                "source_type": "public_search",
                "source_key": item.get("source_key"),
                "title": item.get("title") or item.get("source_name"),
                "snippet": snippet,
                "score": item.get("rank"),
                "url": item.get("url"),
            }
        )
    return records


def _fact_matches_evidence(fact: Dict[str, Any], record: Dict[str, Any]) -> bool:
    haystack = f"{record.get('title', '')} {record.get('snippet', '')}".casefold()
    terms = [
        str(term).casefold()
        for term in [fact.get("label"), fact.get("value"), *fact.get("keywords", [])]
        if term and len(str(term).strip()) >= 2
    ]
    return any(term in haystack for term in terms)


def _merge_evidence_into_facts(facts: List[Dict[str, Any]], evidence_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for fact in facts:
        matched = [
            {
                "source_type": record.get("source_type"),
                "source_key": record.get("source_key"),
                "title": record.get("title"),
                "snippet": str(record.get("snippet", ""))[:260],
                "url": record.get("url"),
                "score": record.get("score"),
            }
            for record in evidence_records
            if _fact_matches_evidence(fact, record)
        ][:4]
        next_fact = dict(fact)
        next_fact["validation_evidence"] = matched
        if matched:
            next_fact["verification_status"] = "cross_validated"
            next_fact["confidence"] = round(min(0.96, float(fact.get("confidence", 0)) + 0.18), 2)
        merged.append(next_fact)
    return merged


def _evidence_dependency_contract(capability_context: Dict[str, Any], facts: List[Dict[str, Any]], projections: List[Dict[str, Any]]) -> Dict[str, Any]:
    rag = capability_context.get("本地RAG") or {}
    live = ((capability_context.get("公开检索") or {}).get("实时检索") or {})
    return {
        "task_a": {
            "fact_count": len(facts),
            "fact_ids": [fact["id"] for fact in facts],
        },
        "task_b_c": {
            "rag_status": rag.get("status", "unknown"),
            "rag_result_count": rag.get("result_count", 0),
            "public_result_count": live.get("result_count", 0),
            "matched_fact_count": sum(1 for fact in facts if fact.get("verification_status") == "cross_validated"),
            "errors": live.get("errors", []),
        },
        "task_d": {
            "input_fact_ids": [fact["id"] for fact in facts if fact.get("verification_status") in {"cross_validated", "candidate_quantified"}],
            "projection_count": len(projections),
            "blocked": not projections,
        },
        "guardrail": "Task D 只读取 Task A facts 经 Task B/C 标注后的 verification_status；未验证事实不会升级成确定结论。",
    }


def apply_evidence_context_to_candidate_evaluation(
    evaluation: Dict[str, Any],
    capability_context: Dict[str, Any],
    candidate_material: str,
    aperture_weight: float = 0.7,
) -> Dict[str, Any]:
    sandbox = dict(evaluation.get("decision_sandbox") or {})
    aperture_anchor = sandbox.get("aperture_anchor") or sandbox.get("aperture") or {}
    constraint = str(aperture_anchor.get("team_constraint") or "真机泛化")
    evidence_records = _flatten_evidence_context(capability_context)
    facts = _merge_evidence_into_facts(list(sandbox.get("fact_chain") or []), evidence_records)
    hidden_limits = list(evaluation.get("潜在工程边界") or sandbox.get("hidden_limits") or [])
    matched_keywords = list((evaluation.get("证据链") or {}).get("命中关键词") or evaluation.get("技术强项") or [])
    has_sim_only_risk = any("仿真" in str(item) for item in evaluation.get("风险点", []))
    normalized_weight = max(0.0, min(float(aperture_weight), 1.0))
    spectrum = _build_capability_spectrum(
        facts=facts,
        text=candidate_material.casefold(),
        matched_keywords=matched_keywords,
        has_sim_only_risk=has_sim_only_risk,
    )
    projections = _build_projection(facts, constraint, normalized_weight)
    narrative = _build_narrative_stream(constraint, projections, facts, hidden_limits)
    probes = _build_probe_toolkit(constraint, projections, hidden_limits)
    evidence_contract = _evidence_dependency_contract(capability_context, facts, projections)
    agent_matrix = [
        {"id": "task_a", "label": "Task A：事实解构", "output": f"工程事实链 {len(facts)} 条", "status": "ready" if facts else "blocked_insufficient_input"},
        {
            "id": "task_b_c",
            "label": "Task B/C：交叉核验与增强",
            "output": f"本地 RAG {evidence_contract['task_b_c']['rag_result_count']} 条 + 公开检索 {evidence_contract['task_b_c']['public_result_count']} 条；匹配事实 {evidence_contract['task_b_c']['matched_fact_count']} 条",
            "status": "ready" if evidence_records else "no_external_evidence",
        },
        {"id": "task_d", "label": "Task D：边界模拟与对齐", "output": f"能力向量平移推演 {len(projections)} 条", "status": "ready" if projections else "blocked_waiting_evidence"},
        {"id": "human_gate", "label": "Human-in-the-loop：认知闭环", "output": f"追问 {len(probes)} 条，等待面试反馈", "status": "awaiting_interview_feedback"},
    ]
    sandbox.update(
        {
            "aperture_anchor": aperture_anchor,
            "aperture": aperture_anchor,
            "agent_matrix": agent_matrix,
            "routing_trace": {
                "mode": "contextual_soft_routing",
                "selected_nodes": [node["id"] for node in agent_matrix if not str(node["status"]).startswith("blocked")],
                "blocked_nodes": [node["id"] for node in agent_matrix if str(node["status"]).startswith("blocked")],
                "route_reason": f"前端 Aperture={constraint}；Task D 输入来自 {len(evidence_contract['task_d']['input_fact_ids'])} 条可用事实。",
            },
            "fact_chain": facts,
            "capability_spectrum": spectrum,
            "spectrum": spectrum,
            "narrative_stream": narrative,
            "core_incremental_value": narrative["core_incremental_value"],
            "cognitive_projection": projections,
            "projection": projections,
            "probing_toolkit": probes,
            "evidence_dependency_contract": evidence_contract,
        }
    )
    scored_spectrum = [item for item in spectrum if item.get("energy") is not None]
    strongest = max(scored_spectrum, key=lambda item: item["energy"]) if scored_spectrum else None
    sandbox["emergent_strength"] = (
        f"{strongest['label']}存在「{strongest['signal']}」"
        if strongest else
        "数据不足，无法计算性能涌现点。"
    )
    evaluation["decision_sandbox"] = sandbox
    evaluation["工程事实链"] = facts
    evaluation["能力频谱"] = spectrum
    evaluation["增量价值"] = narrative["core_incremental_value"]
    evaluation["能力平移推演"] = projections
    evaluation["追问武器库"] = probes
    return evaluation


def _build_decision_sandbox(
    candidate_material: str,
    role_key: str,
    matched_keywords: List[str],
    has_real_robot: bool,
    has_sim_only_risk: bool,
    has_ownership: bool,
    has_home_context: bool,
    missing_core: List[str],
    team_constraint: str | None,
    aperture_weight: float,
) -> Dict[str, Any]:
    role = ROBOT_ROLES_METADATA[role_key]
    constraint = (team_constraint or "真机泛化").strip() or "真机泛化"
    normalized_weight = max(0.0, min(float(aperture_weight), 1.0))
    facts = _build_engineering_fact_chain(
        candidate_material=candidate_material,
        role_key=role_key,
        matched_keywords=matched_keywords,
        has_real_robot=has_real_robot,
        has_sim_only_risk=has_sim_only_risk,
        has_ownership=has_ownership,
        has_home_context=has_home_context,
    )
    spectrum = _build_capability_spectrum(
        facts=facts,
        text=candidate_material.casefold(),
        matched_keywords=matched_keywords,
        has_sim_only_risk=has_sim_only_risk,
    )
    projection = _build_projection(facts, constraint, normalized_weight)
    hidden_limits = _build_hidden_limits(
        has_real_robot=has_real_robot,
        has_sim_only_risk=has_sim_only_risk,
        has_ownership=has_ownership,
        has_home_context=has_home_context,
        missing_core=missing_core,
    )
    toolkit = _build_probe_toolkit(constraint, projection, hidden_limits)
    narrative = _build_narrative_stream(constraint, projection, facts, hidden_limits)
    scored_spectrum = [item for item in spectrum if item["energy"] is not None]
    strongest_spectrum = max(scored_spectrum, key=lambda item: item["energy"]) if scored_spectrum else None
    core_value = narrative["core_incremental_value"]
    aperture_anchor = {
        "raw_text": constraint,
        "team_constraint": constraint,
        "constraint_weight": normalized_weight,
        "focus_terms": _constraint_focus_terms(constraint),
        "source": "frontend_payload",
    }
    return {
        "aperture_anchor": aperture_anchor,
        "aperture": aperture_anchor,
        "agent_matrix": [
            {"id": "task_a", "label": "Task A：事实解构", "output": f"工程事实链 {len(facts)} 条", "status": "ready" if facts else "blocked_insufficient_input"},
            {"id": "task_b_c", "label": "Task B/C：交叉核验与增强", "output": "本地 RAG + 公开信源上下文", "status": "pending_evidence_merge"},
            {"id": "task_d", "label": "Task D：边界模拟与对齐", "output": f"能力向量平移推演 {len(projection)} 条", "status": "ready" if projection else "blocked_waiting_evidence"},
            {"id": "human_gate", "label": "Human-in-the-loop：认知闭环", "output": "追问反馈更新画像", "status": "awaiting_interview_feedback"},
        ],
        "routing_trace": {
            "mode": "contextual_soft_routing",
            "selected_nodes": [node_id for node_id, active in {
                "task_a": bool(facts),
                "task_b_c": True,
                "task_d": bool(projection),
                "human_gate": bool(toolkit),
            }.items() if active],
            "blocked_nodes": [node_id for node_id, active in {
                "task_a": bool(facts),
                "task_d": bool(projection),
            }.items() if not active],
        },
        "role": {"role_key": role_key, "name_zh": role["name_zh"]},
        "fact_chain": facts,
        "capability_spectrum": spectrum,
        "spectrum": spectrum,
        "narrative_stream": narrative,
        "core_incremental_value": core_value,
        "emergent_strength": f"{strongest_spectrum['label']}存在「{strongest_spectrum['signal']}」" if strongest_spectrum else "数据不足，无法计算性能涌现点。",
        "cognitive_projection": projection,
        "projection": projection,
        "hidden_limits": hidden_limits,
        "probing_toolkit": toolkit,
        "feedback_loop": {
            "model_update_policy": "面试官勾选追问是否答出后，反馈会写回当前任务画像；后续可接入候选人画像库和评分校准表。",
            "signals": ["probe_answered", "probe_failed", "human_note", "constraint_reweight"],
            "status": "awaiting_feedback",
        },
    }


def evaluate_candidate(
    candidate_material: str,
    target: str | None = None,
    team_constraint: str | None = None,
    aperture_weight: float = 0.7,
) -> Dict[str, Any]:
    role_key = infer_role_key(target or candidate_material)
    text = candidate_material.lower()
    role = ROBOT_ROLES_METADATA[role_key]
    capabilities = get_capabilities_for_role(role_key)
    keywords = build_search_keywords(role_key)

    matched_keywords = [keyword for keyword in keywords if keyword.lower() in text]
    has_real_robot = any(term in text for term in ["实机", "真实机器人", "部署", "量产", "硬件", "ros", "机器人"])
    has_sim_only_risk = "仿真" in text and not has_real_robot
    has_ownership = any(term in text for term in ["负责", "主导", "owner", "lead", "独立"])
    has_home_context = any(term in text for term in ["家庭", "家用", "室内", "人宠", "家具", "长尾"])

    score = min(25, len(matched_keywords) * 4)
    score += 20 if has_real_robot else 0
    score += 15 if has_ownership else 5
    score += 20 if has_home_context else 8
    score += 10 if any(term in text for term in ["跨团队", "软硬件", "控制", "感知", "数据"]) else 4
    score += 10 if any(term in text for term in ["创业", "0到1", "量产", "交付", "长期"]) else 4
    score = max(0, min(100, score - (15 if has_sim_only_risk else 0)))

    if score >= 80:
        level = "强推"
    elif score >= 65:
        level = "可面"
    elif score >= 50:
        level = "备选"
    else:
        level = "不推荐"

    risks = []
    if not has_real_robot:
        risks.append("未看到真实机器人/硬件部署证据")
    if has_sim_only_risk:
        risks.append("材料更像仿真经验，需确认能否迁移到实机")
    if not has_ownership:
        risks.append("独立贡献边界不清晰")
    missing_core = [
        capability["capability_name_zh"]
        for capability in capabilities
        if not any(keyword.lower() in text for keyword in capability["keywords"])
    ]
    if missing_core:
        risks.append(f"核心能力缺口待确认：{', '.join(missing_core)}")

    conclusion = "建议进入下一轮" if level in {"强推", "可面"} else "暂不建议进入下一轮，除非业务阶段可以接受补足周期。"
    decision_sandbox = _build_decision_sandbox(
        candidate_material=candidate_material,
        role_key=role_key,
        matched_keywords=matched_keywords,
        has_real_robot=has_real_robot,
        has_sim_only_risk=has_sim_only_risk,
        has_ownership=has_ownership,
        has_home_context=has_home_context,
        missing_core=missing_core,
        team_constraint=team_constraint,
        aperture_weight=aperture_weight,
    )

    return {
        "匹配评分": score,
        "推荐等级": level,
        "适合岗位": role["name_zh"],
        "技术强项": matched_keywords[:10],
        "风险点": risks,
        "面试追问": [node for capability in capabilities for node in capability["evaluation_nodes"]],
        "推荐结论": conclusion,
        "工程事实链": decision_sandbox["fact_chain"],
        "能力频谱": decision_sandbox["spectrum"],
        "增量价值": decision_sandbox["core_incremental_value"],
        "能力平移推演": decision_sandbox["projection"],
        "潜在工程边界": decision_sandbox["hidden_limits"],
        "追问武器库": decision_sandbox["probing_toolkit"],
        "decision_sandbox": decision_sandbox,
        "证据链": {
            "命中关键词": matched_keywords[:10],
            "真实机器人证据": has_real_robot,
            "独立贡献证据": has_ownership,
            "家庭场景证据": has_home_context,
        },
        "结论": conclusion,
    }


def generate_weekly_report(weekly_data: str, focus_roles: List[str] | None = None) -> Dict[str, Any]:
    text = weekly_data.casefold()
    role_keys = [infer_role_key(role) for role in focus_roles] if focus_roles else []
    if not role_keys:
        role_keys = [
            role_key
            for role_key, aliases in ROLE_ALIASES.items()
            if ROBOT_ROLES_METADATA[role_key]["name_zh"].casefold() in text
            or any(alias.casefold() in text for alias in aliases)
        ][:3]
    if not role_keys:
        role_keys = ["robot_system_architect"]

    focus_role_names = [ROBOT_ROLES_METADATA[role_key]["name_zh"] for role_key in dict.fromkeys(role_keys)]
    market_signal_terms = [
        "融资",
        "产品发布",
        "论文",
        "专利",
        "GitHub",
        "Hugging Face",
        "ModelScope",
        "Hackathon",
        "Meetup",
        "会议",
        "直播",
        "B站",
        "YouTube",
        "薪酬",
        "人才流动",
    ]
    market_signals = [term for term in market_signal_terms if term.casefold() in text]

    risks: List[str] = []
    if not any(term in text for term in ["offer", "reject", "入职", "淘汰"]):
        risks.append("缺少 offer / reject / 入职结果，候选人评分体系无法闭环校准。")
    if not any(term in text for term in ["面试反馈", "评分", "复盘", "校准"]):
        risks.append("缺少面试反馈或人工校准记录，需补齐证据链。")
    if not market_signals:
        risks.append("市场信号不足，需补充招聘站、社区、活动、视频、GitHub 和论文来源。")

    return {
        "本周招聘结论": f"本周围绕{', '.join(focus_role_names)}推进招聘，需同时看岗位进展、候选人质量和市场信号。",
        "关键岗位进展": [
            f"{role_name}：结合招聘漏斗、面试反馈和候选人库更新进展。"
            for role_name in focus_role_names
        ],
        "Top 候选人": ["从候选人画像库提取本周高分候选人，并附匹配评分、风险点和证据链。"],
        "市场人才信号": market_signals or ["未在本周数据中识别到明确市场信号，建议补充多源检索。"],
        "招聘风险": risks,
        "下周行动建议": [
            "更新岗位画像和目标公司列表。",
            "校准候选人评分卡并补齐面试追问。",
            "把人工修改、面试反馈和 offer / reject 结果回流到知识库、画像库和评分体系。",
        ],
        "回流目标": ["知识库", "画像库", "评分体系"],
    }


HOME_ROBOT_RECRUITING_SCENARIOS: Dict[str, Any] = {
    "input_layer": MULTIMODAL_MULTI_SOURCE_INPUTS,
    "infrastructure_layer": AI_NATIVE_INFRASTRUCTURE,
    "knowledge_assets": KNOWLEDGE_ASSETS,
    "workflows": SCENARIO_WORKFLOWS,
    "static_dynamic_decision_table": STATIC_DYNAMIC_DECISION_TABLE,
    "evidence_record_schema": EVIDENCE_RECORD_SCHEMA,
    "cross_validation_rules": CROSS_VALIDATION_RULES,
    "role_aliases": ROLE_ALIASES,
    "talent_source_map": HOME_ROBOT_TALENT_SOURCE_MAP,
    "special_checks": HOME_ROBOT_SPECIAL_CHECKS,
    "data_flywheel": DATA_FLYWHEEL_LOOP,
    "functions": {
        "infer_role_key": infer_role_key,
        "generate_job_profile_and_jd": generate_job_profile_and_jd,
        "build_talent_map": build_talent_map,
        "evaluate_candidate": evaluate_candidate,
        "apply_evidence_context_to_candidate_evaluation": apply_evidence_context_to_candidate_evaluation,
        "generate_weekly_report": generate_weekly_report,
    },
}
