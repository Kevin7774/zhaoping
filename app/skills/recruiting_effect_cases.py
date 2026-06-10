from __future__ import annotations

from typing import Any


def _ranking_case(
    *,
    case_id: str,
    name: str,
    job_profile: dict[str, Any],
    candidates: tuple[dict[str, str], ...],
    ranking_order: tuple[str, str, str],
    risk_candidate_id: str,
    risk_term: str,
    min_top_score: int = 85,
    score_gap_min: int = 20,
    risk_max_score: int = 60,
) -> dict[str, Any]:
    return {
        "case_type": "job_candidate_ranking",
        "case_id": case_id,
        "name": name,
        "job_profile": job_profile,
        "candidates": list(candidates),
        "expectations": {
            "top_candidate_id": ranking_order[0],
            "ranking_order": list(ranking_order),
            "min_top_score": min_top_score,
            "score_gap_min": score_gap_min,
            "max_scores": {risk_candidate_id: risk_max_score},
            "allowed_levels": {ranking_order[0]: ["强推"], risk_candidate_id: ["不推荐", "备选"]},
            "required_risk_terms": {risk_candidate_id: [risk_term]},
        },
    }


DEFAULT_RECRUITING_EFFECT_CASES: tuple[dict[str, Any], ...] = (
    _ranking_case(
        case_id="fde_business_builder_ranking",
        name="AI Native FDE 岗位应把业务闭环 builder 排在 prompt operator 前面",
        job_profile={
            "title": "AI Native FDE / Agentic Builder",
            "must_have_skills": ["全栈开发", "Agentic workflow"],
            "scoring_rubric": {
                "完整业务工程闭环（问题定义/上线/指标复盘）": 3,
                "业务抽象能力（订单/支付/风控）": 2,
            },
            "rationale": {"must_have_signals": ["AI coding"], "risk_signals": ["只会写 prompt"]},
        },
        candidates=(
            {
                "candidate_id": "cand_prompt_operator",
                "name": "Prompt Operator",
                "candidate_material": "使用 AI coding 编写 prompt demo，了解 Agentic workflow，只会写 prompt。",
            },
            {
                "candidate_id": "cand_fde_builder",
                "name": "FDE Builder",
                "candidate_material": "主导订单支付风控系统上线，问题定义到指标复盘，全栈开发 Agentic workflow AI coding。",
            },
            {
                "candidate_id": "cand_general_fullstack",
                "name": "General Fullstack",
                "candidate_material": "负责后台 CRUD 和报表，全栈开发，交付过内部工具。",
            },
        ),
        ranking_order=("cand_fde_builder", "cand_general_fullstack", "cand_prompt_operator"),
        risk_candidate_id="cand_prompt_operator",
        risk_term="只会写 prompt",
        min_top_score=80,
    ),
    _ranking_case(
        case_id="vla_real_robot_vs_sim_ranking",
        name="VLA 岗位应把真机闭环候选人排在仿真候选人前面",
        job_profile={
            "title": "家庭机器人 VLA 算法工程师",
            "must_have_skills": ["VLA", "Diffusion Policy", "ROS 实机部署"],
            "scoring_rubric": {
                "实机闭环和延迟优化（ROS/真机/控制回路）": 3,
                "数据策略能力（遥操作/Action Token/长尾场景）": 2,
            },
            "rationale": {"bonus_signals": ["真实机器人"], "risk_signals": ["只做仿真"]},
        },
        candidates=(
            {
                "candidate_id": "cand_vla_sim_only",
                "name": "Simulation Only",
                "candidate_material": "参与 Isaac Sim 仿真策略训练和论文复现，了解 VLA，只做仿真。",
            },
            {
                "candidate_id": "cand_vla_real_robot",
                "name": "Real Robot VLA",
                "candidate_material": (
                    "主导真实机器人 VLA 和 Diffusion Policy，负责实机闭环和延迟优化，ROS 实机部署上线，"
                    "ROS 真机控制回路 12ms，数据策略能力覆盖遥操作、Action Token、长尾场景。"
                ),
            },
            {
                "candidate_id": "cand_vla_data_operator",
                "name": "VLA Data Operator",
                "candidate_material": "负责遥操作数据采集、Action Token 标注清洗，支撑 Diffusion Policy 训练。",
            },
        ),
        ranking_order=("cand_vla_real_robot", "cand_vla_data_operator", "cand_vla_sim_only"),
        risk_candidate_id="cand_vla_sim_only",
        risk_term="只做仿真",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="robotics_data_platform_ranking",
        name="机器人数据平台岗位应优先端到端数据闭环候选人",
        job_profile={
            "title": "机器人数据平台工程师",
            "must_have_skills": ["数据管线", "评测体系", "Python"],
            "scoring_rubric": {
                "端到端数据闭环（采集/清洗/标注/回放）": 3,
                "评测指标体系（回归集/失败案例/看板）": 2,
            },
            "rationale": {"bonus_signals": ["真实机器人日志"], "risk_signals": ["只做标注外包"]},
        },
        candidates=(
            {"candidate_id": "cand_label_vendor", "name": "Label Vendor", "candidate_material": "只做标注外包，整理数据表格和图片标签。"},
            {
                "candidate_id": "cand_data_platform_lead",
                "name": "Data Platform Lead",
                "candidate_material": (
                    "主导端到端数据闭环，覆盖采集、清洗、标注、回放，Python 数据管线上线，"
                    "建立评测体系、评测指标体系、回归集、失败案例和看板，接入真实机器人日志。"
                ),
            },
            {"candidate_id": "cand_ml_researcher", "name": "ML Researcher", "candidate_material": "Python 模型训练和论文复现，参与离线评测脚本。"},
        ),
        ranking_order=("cand_data_platform_lead", "cand_ml_researcher", "cand_label_vendor"),
        risk_candidate_id="cand_label_vendor",
        risk_term="只做标注外包",
        min_top_score=90,
        score_gap_min=30,
        risk_max_score=45,
    ),
    _ranking_case(
        case_id="motion_control_closed_loop_ranking",
        name="运动控制岗位应优先实机闭环和接触稳定候选人",
        job_profile={
            "title": "机器人运动控制工程师",
            "must_have_skills": ["运动控制", "MPC", "轨迹规划"],
            "scoring_rubric": {"运动控制闭环（MPC/轨迹规划/接触稳定）": 3, "实机调参和故障定位（电机/传感器/日志）": 2},
            "rationale": {"bonus_signals": ["实机"], "risk_signals": ["只做 MATLAB 仿真"]},
        },
        candidates=(
            {"candidate_id": "cand_motion_matlab", "name": "Matlab Planner", "candidate_material": "只做 MATLAB 仿真，复现轨迹规划论文。"},
            {
                "candidate_id": "cand_motion_real_loop",
                "name": "Motion Control Lead",
                "candidate_material": (
                    "主导运动控制闭环，覆盖 MPC、轨迹规划、接触稳定，负责实机调参和故障定位，"
                    "分析电机、传感器、日志并上线实机控制。"
                ),
            },
            {"candidate_id": "cand_motion_planner", "name": "Planner Engineer", "candidate_material": "负责轨迹规划和离线调参，了解 MPC。"},
        ),
        ranking_order=("cand_motion_real_loop", "cand_motion_planner", "cand_motion_matlab"),
        risk_candidate_id="cand_motion_matlab",
        risk_term="只做 MATLAB 仿真",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="embedded_realtime_ranking",
        name="嵌入式岗位应优先实时链路和总线调试候选人",
        job_profile={
            "title": "机器人嵌入式实时系统工程师",
            "must_have_skills": ["嵌入式", "RTOS", "CAN"],
            "scoring_rubric": {"实时系统链路（中断/DMA/任务优先级）": 3, "总线调试和量产故障定位（CAN/UART/日志）": 2},
            "rationale": {"bonus_signals": ["示波器"], "risk_signals": ["只写上位机"]},
        },
        candidates=(
            {"candidate_id": "cand_upper_app", "name": "Upper App", "candidate_material": "只写上位机工具，调用串口命令。"},
            {
                "candidate_id": "cand_embedded_realtime",
                "name": "Realtime Firmware Lead",
                "candidate_material": (
                    "主导嵌入式 RTOS 实时系统链路，处理中断、DMA、任务优先级，负责 CAN、UART、日志，"
                    "用示波器定位量产故障并上线。"
                ),
            },
            {"candidate_id": "cand_firmware_basic", "name": "Firmware Basic", "candidate_material": "写过嵌入式 CAN 驱动和日志模块。"},
        ),
        ranking_order=("cand_embedded_realtime", "cand_firmware_basic", "cand_upper_app"),
        risk_candidate_id="cand_upper_app",
        risk_term="只写上位机",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="slam_navigation_ranking",
        name="SLAM 导航岗位应优先真实场景闭环候选人",
        job_profile={
            "title": "机器人 SLAM / 导航工程师",
            "must_have_skills": ["SLAM", "导航", "定位"],
            "scoring_rubric": {"SLAM定位稳定性（建图/回环/重定位）": 3, "导航闭环（代价地图/动态避障/路径规划）": 2},
            "rationale": {"bonus_signals": ["真实场景"], "risk_signals": ["只跑公开数据集"]},
        },
        candidates=(
            {"candidate_id": "cand_dataset_slam", "name": "Dataset SLAM", "candidate_material": "只跑公开数据集，调过 ORB-SLAM 参数。"},
            {
                "candidate_id": "cand_slam_nav_field",
                "name": "SLAM Navigation Lead",
                "candidate_material": (
                    "主导真实场景 SLAM定位稳定性，覆盖建图、回环、重定位，负责导航闭环、代价地图、"
                    "动态避障、路径规划，上线多楼层机器人。"
                ),
            },
            {"candidate_id": "cand_nav_planner", "name": "Navigation Planner", "candidate_material": "负责导航和路径规划，维护代价地图参数。"},
        ),
        ranking_order=("cand_slam_nav_field", "cand_nav_planner", "cand_dataset_slam"),
        risk_candidate_id="cand_dataset_slam",
        risk_term="只跑公开数据集",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="qa_evaluation_system_ranking",
        name="评测岗位应优先回归集和失败闭环候选人",
        job_profile={
            "title": "机器人 QA / 评测工程师",
            "must_have_skills": ["评测", "回归集", "自动化测试"],
            "scoring_rubric": {"评测体系（指标/回归集/覆盖率）": 3, "失败闭环（复现/归因/缺陷推动）": 2},
            "rationale": {"bonus_signals": ["现场日志"], "risk_signals": ["只会手工点检"]},
        },
        candidates=(
            {"candidate_id": "cand_manual_qa", "name": "Manual QA", "candidate_material": "只会手工点检，记录问题截图。"},
            {
                "candidate_id": "cand_eval_loop",
                "name": "Evaluation Loop Owner",
                "candidate_material": (
                    "主导评测体系，定义指标、回归集、覆盖率，建设自动化测试，负责失败闭环、复现、归因、"
                    "缺陷推动，接入现场日志。"
                ),
            },
            {"candidate_id": "cand_test_script", "name": "Test Script Engineer", "candidate_material": "写过自动化测试和评测脚本，维护回归集。"},
        ),
        ranking_order=("cand_eval_loop", "cand_test_script", "cand_manual_qa"),
        risk_candidate_id="cand_manual_qa",
        risk_term="只会手工点检",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="field_deployment_ranking",
        name="现场部署岗位应优先客户现场闭环候选人",
        job_profile={
            "title": "机器人现场部署 / FAE 工程师",
            "must_have_skills": ["现场部署", "客户问题定位", "日志分析"],
            "scoring_rubric": {"现场闭环（部署/验收/问题复现）": 3, "跨团队推动（产品/算法/硬件/客户）": 2},
            "rationale": {"bonus_signals": ["客户现场"], "risk_signals": ["只做售前演示"]},
        },
        candidates=(
            {"candidate_id": "cand_presales_demo", "name": "Presales Demo", "candidate_material": "只做售前演示，准备 PPT 和 demo 脚本。"},
            {
                "candidate_id": "cand_field_owner",
                "name": "Field Deployment Owner",
                "candidate_material": (
                    "主导客户现场现场闭环，负责现场部署、验收、问题复现、客户问题定位和日志分析，"
                    "跨团队推动产品、算法、硬件、客户问题上线修复。"
                ),
            },
            {"candidate_id": "cand_support_engineer", "name": "Support Engineer", "candidate_material": "负责现场部署和日志分析，跟进客户问题定位。"},
        ),
        ranking_order=("cand_field_owner", "cand_support_engineer", "cand_presales_demo"),
        risk_candidate_id="cand_presales_demo",
        risk_term="只做售前演示",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="perception_3d_ranking",
        name="三维感知岗位应优先传感器融合和实物评测候选人",
        job_profile={
            "title": "机器人三维感知工程师",
            "must_have_skills": ["3D 感知", "传感器融合", "目标检测"],
            "scoring_rubric": {"3D感知链路（深度/点云/目标检测）": 3, "传感器融合和实物评测（相机/LiDAR/标定）": 2},
            "rationale": {"bonus_signals": ["实物评测"], "risk_signals": ["只做离线标注"]},
        },
        candidates=(
            {"candidate_id": "cand_offline_label", "name": "Offline Labeler", "candidate_material": "只做离线标注，清洗检测框。"},
            {
                "candidate_id": "cand_3d_perception",
                "name": "3D Perception Lead",
                "candidate_material": (
                    "主导 3D 感知链路，覆盖深度、点云、目标检测，负责传感器融合和实物评测，"
                    "完成相机、LiDAR、标定并上线。"
                ),
            },
            {"candidate_id": "cand_detection_model", "name": "Detection Engineer", "candidate_material": "做过目标检测模型训练和 3D 感知 demo。"},
        ),
        ranking_order=("cand_3d_perception", "cand_detection_model", "cand_offline_label"),
        risk_candidate_id="cand_offline_label",
        risk_term="只做离线标注",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="hardware_reliability_ranking",
        name="硬件可靠性岗位应优先失效分析和量产闭环候选人",
        job_profile={
            "title": "机器人硬件可靠性工程师",
            "must_have_skills": ["可靠性测试", "失效分析", "量产"],
            "scoring_rubric": {"可靠性体系（HALT/寿命/环境测试）": 3, "失效分析和量产闭环（8D/BOM/供应商）": 2},
            "rationale": {"bonus_signals": ["量产闭环"], "risk_signals": ["只会画原理图"]},
        },
        candidates=(
            {"candidate_id": "cand_schematic_only", "name": "Schematic Only", "candidate_material": "只会画原理图，没有量产测试经验。"},
            {
                "candidate_id": "cand_hw_reliability",
                "name": "Hardware Reliability Lead",
                "candidate_material": (
                    "主导可靠性体系，覆盖 HALT、寿命、环境测试，负责可靠性测试、失效分析和量产闭环，"
                    "推动 8D、BOM、供应商改善并上线。"
                ),
            },
            {"candidate_id": "cand_test_fixture", "name": "Fixture Engineer", "candidate_material": "负责可靠性测试治具和环境测试记录。"},
        ),
        ranking_order=("cand_hw_reliability", "cand_test_fixture", "cand_schematic_only"),
        risk_candidate_id="cand_schematic_only",
        risk_term="只会画原理图",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="product_scene_definition_ranking",
        name="产品岗位应优先场景定义和指标闭环候选人",
        job_profile={
            "title": "机器人产品经理 / 场景定义",
            "must_have_skills": ["场景定义", "需求拆解", "指标体系"],
            "scoring_rubric": {"场景定义闭环（用户任务/失败路径/验收标准）": 3, "指标体系和版本迭代（数据/反馈/优先级）": 2},
            "rationale": {"bonus_signals": ["客户访谈"], "risk_signals": ["只写 PRD"]},
        },
        candidates=(
            {"candidate_id": "cand_prd_only", "name": "PRD Writer", "candidate_material": "只写 PRD，整理需求列表。"},
            {
                "candidate_id": "cand_scene_pm",
                "name": "Scene Product Owner",
                "candidate_material": (
                    "主导场景定义闭环，覆盖用户任务、失败路径、验收标准，负责需求拆解、指标体系，"
                    "通过数据、反馈、优先级驱动版本迭代，并做客户访谈。"
                ),
            },
            {"candidate_id": "cand_ops_pm", "name": "Operations PM", "candidate_material": "负责需求拆解和版本迭代，维护指标体系。"},
        ),
        ranking_order=("cand_scene_pm", "cand_ops_pm", "cand_prd_only"),
        risk_candidate_id="cand_prd_only",
        risk_term="只写 PRD",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="embodied_mllm_planning_ranking",
        name="具身 MLLM 任务规划岗位应优先闭环执行候选人",
        job_profile={
            "title": "具身 MLLM 任务规划工程师",
            "must_have_skills": ["MLLM", "任务规划", "工具调用"],
            "scoring_rubric": {"任务规划闭环（意图理解/工具调用/失败恢复）": 3, "具身约束落地（状态机/安全边界/实时反馈）": 2},
            "rationale": {"bonus_signals": ["真实机器人"], "risk_signals": ["只做聊天机器人"]},
        },
        candidates=(
            {"candidate_id": "cand_chatbot_only", "name": "Chatbot Engineer", "candidate_material": "只做聊天机器人，接过普通问答。"},
            {
                "candidate_id": "cand_embodied_mllm",
                "name": "Embodied MLLM Planner",
                "candidate_material": (
                    "主导 MLLM 任务规划闭环，覆盖意图理解、工具调用、失败恢复，负责具身约束落地、"
                    "状态机、安全边界、实时反馈并接入真实机器人。"
                ),
            },
            {"candidate_id": "cand_agent_planner", "name": "Agent Planner", "candidate_material": "做过工具调用和任务规划 demo，了解状态机。"},
        ),
        ranking_order=("cand_embodied_mllm", "cand_agent_planner", "cand_chatbot_only"),
        risk_candidate_id="cand_chatbot_only",
        risk_term="只做聊天机器人",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="sim2real_transfer_ranking",
        name="Sim2Real 岗位应优先仿真到实机迁移闭环候选人",
        job_profile={
            "title": "机器人 Sim2Real 工程师",
            "must_have_skills": ["仿真", "Sim2Real", "实机验证"],
            "scoring_rubric": {"仿真到实机迁移（domain randomization/参数辨识/校准）": 3, "实机验证闭环（失败案例/指标/数据回灌）": 2},
            "rationale": {"bonus_signals": ["实机验证"], "risk_signals": ["只调仿真环境"]},
        },
        candidates=(
            {"candidate_id": "cand_sim_env_only", "name": "Simulation Env", "candidate_material": "只调仿真环境，搭建 Isaac Sim 场景。"},
            {
                "candidate_id": "cand_sim2real_owner",
                "name": "Sim2Real Owner",
                "candidate_material": (
                    "主导仿真到实机迁移，覆盖 domain randomization、参数辨识、校准，负责 Sim2Real 和实机验证闭环，"
                    "沉淀失败案例、指标、数据回灌并上线。"
                ),
            },
            {"candidate_id": "cand_sim_generalist", "name": "Simulation Generalist", "candidate_material": "负责仿真数据生成和部分实机验证记录。"},
        ),
        ranking_order=("cand_sim2real_owner", "cand_sim_generalist", "cand_sim_env_only"),
        risk_candidate_id="cand_sim_env_only",
        risk_term="只调仿真环境",
        min_top_score=90,
        score_gap_min=30,
    ),
    _ranking_case(
        case_id="cloud_devops_platform_ranking",
        name="云端平台岗位应优先设备数据和发布闭环候选人",
        job_profile={
            "title": "机器人云端平台 / DevOps 工程师",
            "must_have_skills": ["云端平台", "设备日志", "CI/CD"],
            "scoring_rubric": {"设备数据平台（日志/遥测/告警）": 3, "发布和运维闭环（CI/CD/灰度/回滚）": 2},
            "rationale": {"bonus_signals": ["线上运维"], "risk_signals": ["只做后台 CRUD"]},
        },
        candidates=(
            {"candidate_id": "cand_crud_backend", "name": "CRUD Backend", "candidate_material": "只做后台 CRUD，写管理页面接口。"},
            {
                "candidate_id": "cand_robot_cloud",
                "name": "Robot Cloud Platform Lead",
                "candidate_material": (
                    "主导云端平台和设备数据平台，覆盖设备日志、遥测、告警，负责 CI/CD、灰度、回滚，"
                    "形成发布和运维闭环，支撑线上运维。"
                ),
            },
            {"candidate_id": "cand_devops_basic", "name": "DevOps Basic", "candidate_material": "维护 CI/CD 和设备日志查询，做过灰度发布。"},
        ),
        ranking_order=("cand_robot_cloud", "cand_devops_basic", "cand_crud_backend"),
        risk_candidate_id="cand_crud_backend",
        risk_term="只做后台 CRUD",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="outreach_recruiter_quality_ranking",
        name="招聘运营岗位应优先人才地图和触达闭环候选人",
        job_profile={
            "title": "机器人招聘运营 / Talent Sourcer",
            "must_have_skills": ["人才地图", "候选人触达", "数据复盘"],
            "scoring_rubric": {"人才地图构建（渠道/画像/优先级）": 3, "触达闭环（话术/A-B测试/数据复盘）": 2},
            "rationale": {"bonus_signals": ["技术理解"], "risk_signals": ["只会群发简历"]},
        },
        candidates=(
            {"candidate_id": "cand_resume_spammer", "name": "Resume Spammer", "candidate_material": "只会群发简历，批量加好友。"},
            {
                "candidate_id": "cand_talent_sourcer",
                "name": "Talent Sourcer",
                "candidate_material": (
                    "主导人才地图构建，覆盖渠道、画像、优先级，负责候选人触达、话术、A-B测试、数据复盘，"
                    "具备机器人技术理解并上线触达闭环。"
                ),
            },
            {"candidate_id": "cand_recruiter_ops", "name": "Recruiter Ops", "candidate_material": "做过候选人触达和数据复盘，维护渠道表。"},
        ),
        ranking_order=("cand_talent_sourcer", "cand_recruiter_ops", "cand_resume_spammer"),
        risk_candidate_id="cand_resume_spammer",
        risk_term="只会群发简历",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="safety_compliance_ranking",
        name="安全合规岗位应优先风险分析和测试闭环候选人",
        job_profile={
            "title": "机器人安全合规工程师",
            "must_have_skills": ["安全分析", "风险评估", "测试闭环"],
            "scoring_rubric": {"安全风险分析（FMEA/危害场景/边界条件）": 3, "测试闭环（用例/证据/整改跟踪）": 2},
            "rationale": {"bonus_signals": ["认证"], "risk_signals": ["只会写文档"]},
        },
        candidates=(
            {"candidate_id": "cand_doc_only", "name": "Document Writer", "candidate_material": "只会写文档，整理认证资料。"},
            {
                "candidate_id": "cand_safety_owner",
                "name": "Safety Compliance Owner",
                "candidate_material": (
                    "主导安全风险分析，覆盖 FMEA、危害场景、边界条件，负责安全分析、风险评估、测试闭环，"
                    "维护用例、证据、整改跟踪并通过认证。"
                ),
            },
            {"candidate_id": "cand_test_compliance", "name": "Compliance Tester", "candidate_material": "参与测试闭环和风险评估，整理用例证据。"},
        ),
        ranking_order=("cand_safety_owner", "cand_test_compliance", "cand_doc_only"),
        risk_candidate_id="cand_doc_only",
        risk_term="只会写文档",
        min_top_score=90,
        score_gap_min=25,
    ),
    _ranking_case(
        case_id="manufacturing_npi_ranking",
        name="NPI 岗位应优先试产和量产问题闭环候选人",
        job_profile={
            "title": "机器人制造 NPI 工程师",
            "must_have_skills": ["NPI", "试产", "量产问题"],
            "scoring_rubric": {"NPI导入闭环（工艺/治具/试产）": 3, "量产问题闭环（良率/根因/供应商）": 2},
            "rationale": {"bonus_signals": ["量产爬坡"], "risk_signals": ["只做采购跟单"]},
        },
        candidates=(
            {"candidate_id": "cand_procurement_only", "name": "Procurement Coordinator", "candidate_material": "只做采购跟单，催交物料。"},
            {
                "candidate_id": "cand_npi_owner",
                "name": "NPI Owner",
                "candidate_material": (
                    "主导 NPI导入闭环，覆盖工艺、治具、试产，负责 NPI、试产、量产问题闭环，"
                    "推动良率、根因、供应商改善和量产爬坡。"
                ),
            },
            {"candidate_id": "cand_process_engineer", "name": "Process Engineer", "candidate_material": "参与试产工艺和治具维护，跟进部分量产问题。"},
        ),
        ranking_order=("cand_npi_owner", "cand_process_engineer", "cand_procurement_only"),
        risk_candidate_id="cand_procurement_only",
        risk_term="只做采购跟单",
        min_top_score=90,
        score_gap_min=30,
    ),
)
