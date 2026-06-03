from __future__ import annotations

from typing import Any, Dict, List

from app.skills.tech_space import ROBOT_ROLES_METADATA, get_capabilities_for_role


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
            "抽取经历与技能",
            "识别真实项目深度",
            "匹配家庭机器人岗位画像",
            "判断技术迁移性",
            "识别风险点",
            "生成面试追问",
            "给出推荐结论",
        ],
        "output_fields": ["匹配评分", "风险点", "面试追问", "推荐结论", "证据链"],
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
    "vla_embodied_expert": ["vla", "具身大脑", "具身智能", "机器人基础模型", "action token", "diffusion policy"],
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
            "加分能力": special_checks or role.get("suggested_questions", []),
            "排除项": role["exclusion_keywords"],
        },
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
        "优先来源公司": priority_sources,
        "次优来源公司": secondary_sources,
        "高校/实验室": labs,
        "候选人关键词": keywords,
        "排除来源": role["exclusion_keywords"],
        "触达话术": outreach_strategy,
    }


def evaluate_candidate(candidate_material: str, target: str | None = None) -> Dict[str, Any]:
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

    return {
        "匹配评分": score,
        "推荐等级": level,
        "适合岗位": role["name_zh"],
        "技术强项": matched_keywords[:10],
        "风险点": risks,
        "面试追问": [node for capability in capabilities for node in capability["evaluation_nodes"]],
        "推荐结论": conclusion,
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
    "role_aliases": ROLE_ALIASES,
    "talent_source_map": HOME_ROBOT_TALENT_SOURCE_MAP,
    "special_checks": HOME_ROBOT_SPECIAL_CHECKS,
    "data_flywheel": DATA_FLYWHEEL_LOOP,
    "functions": {
        "infer_role_key": infer_role_key,
        "generate_job_profile_and_jd": generate_job_profile_and_jd,
        "build_talent_map": build_talent_map,
        "evaluate_candidate": evaluate_candidate,
        "generate_weekly_report": generate_weekly_report,
    },
}
