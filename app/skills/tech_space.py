from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

CAPABILITY_STANDARDS: Dict[str, Dict[str, Any]] = {
    "cap_sys_integration": {
        "tech_layer": "system_architecture",
        "capability_name_zh": "整机软硬件系统集成与链路打通",
        "capability_name_en": "Full-system hardware/software integration",
        "keywords": ["系统集成", "整机联调", "ROS2", "实时链路", "软硬件协同"],
        "evaluation_nodes": ["是否有整机量产或实机部署经验", "是否能解释跨模块时序和故障定位链路"],
    },
    "cap_latency_optimization": {
        "tech_layer": "hardware_software_co_design",
        "capability_name_zh": "端到端时延控制与实时总线设计",
        "capability_name_en": "End-to-end latency optimization and realtime bus design",
        "keywords": ["端到端时延", "实时总线", "EtherCAT", "CANopen", "RT latency"],
        "evaluation_nodes": ["是否量化过传感器到执行器延迟", "是否处理过控制链路 jitter"],
    },
    "cap_failover_design": {
        "tech_layer": "system_architecture",
        "capability_name_zh": "系统级防御性编程与失效安全故障保护机制",
        "capability_name_en": "System-level failover and fail-safe design",
        "keywords": ["故障保护", "fail-safe", "watchdog", "防御性编程", "降级策略"],
        "evaluation_nodes": ["是否设计过故障注入测试", "是否覆盖急停、跌倒、通信中断等异常路径"],
    },
    "cap_compute_allocation": {
        "tech_layer": "hardware_software_co_design",
        "capability_name_zh": "异构算力分配",
        "capability_name_en": "Heterogeneous compute allocation",
        "keywords": ["CPU", "GPU", "MCU", "边缘计算", "算力裁剪", "部署优化"],
        "evaluation_nodes": ["是否能在边缘端拆分模型和控制任务", "是否理解功耗、热和实时性的权衡"],
    },
    "cap_wbc_qp": {
        "tech_layer": "cerebellum_control",
        "capability_name_zh": "基于WBC与QP的力控算法",
        "capability_name_en": "WBC and QP based force control",
        "keywords": ["WBC", "QP", "全身控制", "力控", "接触力"],
        "evaluation_nodes": ["是否推导过约束优化形式", "是否在实机调过接触力控制"],
    },
    "cap_mpc_locomotion": {
        "tech_layer": "dynamics",
        "capability_name_zh": "基于MPC的高频步态规划",
        "capability_name_en": "MPC-based high-frequency locomotion planning",
        "keywords": ["MPC", "locomotion", "步态规划", "双足", "四足"],
        "evaluation_nodes": ["是否处理过模型误差和约束", "是否有高频控制上线经验"],
    },
    "cap_state_estimation": {
        "tech_layer": "dynamics",
        "capability_name_zh": "本体高频状态估计",
        "capability_name_en": "High-frequency proprioceptive state estimation",
        "keywords": ["状态估计", "IMU", "运动学融合", "EKF", "proprioception"],
        "evaluation_nodes": ["是否融合过IMU和关节编码器", "是否能解释漂移和接触状态判断"],
    },
    "cap_sim2real_loco": {
        "tech_layer": "dynamics",
        "capability_name_zh": "足式运动Sim-to-Real迁移",
        "capability_name_en": "Legged locomotion sim-to-real transfer",
        "keywords": ["Sim-to-Real", "domain randomization", "跌倒恢复", "扰动恢复"],
        "evaluation_nodes": ["是否做过动态扰动恢复", "是否能解释仿真参数随机化策略"],
    },
    "cap_hardware_stress_test": {
        "tech_layer": "hardware_test",
        "capability_name_zh": "消费级硬件压力与寿命测试",
        "capability_name_en": "Consumer hardware stress and lifetime testing",
        "keywords": ["跌倒测试", "高低温", "疲劳寿命", "可靠性", "硬件测试"],
        "evaluation_nodes": ["是否能设计可复现测试工况", "是否能把测试结论反馈到设计改进"],
    },
    "cap_corner_case_capture": {
        "tech_layer": "QA_reliability",
        "capability_name_zh": "真实家庭长尾场景用例设计",
        "capability_name_en": "Home long-tail corner case test design",
        "keywords": ["corner case", "家庭场景", "长尾", "自动化用例", "回归测试"],
        "evaluation_nodes": ["是否建立过场景库", "是否能从线上日志抽取复现用例"],
    },
    "cap_automated_log_analysis": {
        "tech_layer": "QA_reliability",
        "capability_name_zh": "高并发全栈日志故障归因",
        "capability_name_en": "Automated full-stack log fault attribution",
        "keywords": ["日志分析", "故障归因", "OpenTelemetry", "Python", "监控"],
        "evaluation_nodes": ["是否能关联控制、感知、系统日志", "是否有自动化报警和聚类经验"],
    },
    "cap_vla_imitation": {
        "tech_layer": "brain_learning",
        "capability_name_zh": "基于模仿学习/行为克隆的端到端策略",
        "capability_name_en": "Imitation learning and behavior cloning policy",
        "keywords": ["Imitation Learning", "Behavior Cloning", "BC", "VLA", "端到端策略"],
        "evaluation_nodes": ["是否复现过真实VLA/BC项目", "是否能说明数据质量对策略崩溃的影响"],
    },
    "cap_diffusion_policy": {
        "tech_layer": "brain_learning",
        "capability_name_zh": "扩散策略多模态动作轨迹生成",
        "capability_name_en": "Diffusion policy for multimodal action trajectories",
        "keywords": ["Diffusion Policy", "动作轨迹", "多模态", "robot policy"],
        "evaluation_nodes": ["是否理解扩散去噪过程", "是否能处理动作分布多峰问题"],
    },
    "cap_action_tokenization": {
        "tech_layer": "foundation_model",
        "capability_name_zh": "连续动作空间离散化与多模态Token编排",
        "capability_name_en": "Action tokenization for multimodal policies",
        "keywords": ["Action Token", "动作离散化", "tokenization", "VLA", "多模态编排"],
        "evaluation_nodes": ["是否能设计动作编码粒度", "是否能解释频率对齐和量化误差"],
    },
    "cap_long_horizon_task": {
        "tech_layer": "brain_learning",
        "capability_name_zh": "长程任务规划与打散",
        "capability_name_en": "Long-horizon task planning and decomposition",
        "keywords": ["long-horizon", "任务规划", "洗碗", "整理厨房", "task graph"],
        "evaluation_nodes": ["是否能把家庭任务拆成可执行技能", "是否考虑失败恢复和状态机"],
    },
    "cap_world_model_predict": {
        "tech_layer": "brain_simulator",
        "capability_name_zh": "动作条件下未来状态预测",
        "capability_name_en": "Action-conditioned future state prediction",
        "keywords": ["world model", "future prediction", "latent dynamics", "视频预测"],
        "evaluation_nodes": ["是否能说明状态/像素/隐空间建模差异", "是否评估过预测误差"],
    },
    "cap_sim_env_building": {
        "tech_layer": "data_generation",
        "capability_name_zh": "高保真物理仿真环境重构",
        "capability_name_en": "High-fidelity simulation environment building",
        "keywords": ["Isaac Sim", "MuJoCo", "Genesis", "Omniverse", "仿真环境"],
        "evaluation_nodes": ["是否能建家庭交互任务", "是否能校准物理材质和碰撞参数"],
    },
    "cap_synthetic_data_gen": {
        "tech_layer": "data_generation",
        "capability_name_zh": "长尾失败场景合成数据生成",
        "capability_name_en": "Synthetic data generation for failure cases",
        "keywords": ["合成数据", "failure case", "domain randomization", "数据生成"],
        "evaluation_nodes": ["是否能针对失败模式生成数据", "是否能验证合成数据有效性"],
    },
    "cap_vlm_grounding": {
        "tech_layer": "perception_vlm",
        "capability_name_zh": "VLM物理实体Grounding与开放域识别",
        "capability_name_en": "VLM grounding and open-vocabulary recognition",
        "keywords": ["VLM", "grounding", "open-vocabulary", "OOD", "物体识别"],
        "evaluation_nodes": ["是否能处理开放词表物体", "是否能连接感知结果到操作目标"],
    },
    "cap_audio_intent_parse": {
        "tech_layer": "perception_vlm",
        "capability_name_zh": "家庭噪声环境语音与意图解析",
        "capability_name_en": "Audio denoising and intent parsing in homes",
        "keywords": ["语音消噪", "意图解析", "多轮指令", "ASR", "家庭噪声"],
        "evaluation_nodes": ["是否考虑多人、多房间、噪声", "是否能输出结构化任务意图"],
    },
    "cap_scene_understanding": {
        "tech_layer": "perception_vlm",
        "capability_name_zh": "家庭语义拓扑图关系构建",
        "capability_name_en": "Home semantic topology and scene understanding",
        "keywords": ["场景理解", "语义拓扑图", "房间关系", "scene graph"],
        "evaluation_nodes": ["是否能维护家庭空间记忆", "是否能处理家具变化"],
    },
    "cap_6d_pose": {
        "tech_layer": "perception_spatial",
        "capability_name_zh": "弱纹理/透明/反光物体6D位姿估计",
        "capability_name_en": "6D pose estimation for difficult objects",
        "keywords": ["6D Pose", "透明物体", "反光", "弱纹理", "RGB-D"],
        "evaluation_nodes": ["是否处理过难检测物体", "是否能解释标注和评估指标"],
    },
    "cap_spatial_reconstruction": {
        "tech_layer": "perception_spatial",
        "capability_name_zh": "实时场景稠密重建",
        "capability_name_en": "Realtime dense spatial reconstruction",
        "keywords": ["3DGS", "NeRF", "稠密重建", "SLAM", "空间计算"],
        "evaluation_nodes": ["是否能权衡质量和实时性", "是否能服务导航或操作任务"],
    },
    "cap_point_cloud_seg": {
        "tech_layer": "perception_spatial",
        "capability_name_zh": "点云/RGB-D动态实时分割",
        "capability_name_en": "Realtime point cloud and RGB-D segmentation",
        "keywords": ["点云分割", "RGB-D", "动态过滤", "segmentation"],
        "evaluation_nodes": ["是否能处理动态物体", "是否能联动抓取或避障"],
    },
    "cap_grasp_detection": {
        "tech_layer": "manipulation",
        "capability_name_zh": "未知/柔性/杂乱物体抓取点检测",
        "capability_name_en": "Grasp detection for unknown and cluttered objects",
        "keywords": ["AnyGrasp", "抓取检测", "柔性物体", "杂乱堆叠"],
        "evaluation_nodes": ["是否在实物上评估抓取成功率", "是否考虑遮挡和材质"],
    },
    "cap_motion_planning": {
        "tech_layer": "manipulation",
        "capability_name_zh": "避障路径规划与轨迹平滑",
        "capability_name_en": "Collision-free motion planning and trajectory smoothing",
        "keywords": ["MoveIt", "OMPL", "IK", "轨迹规划", "避障"],
        "evaluation_nodes": ["是否能调规划失败场景", "是否理解IK、多解和约束"],
    },
    "cap_deformable_objects": {
        "tech_layer": "manipulation",
        "capability_name_zh": "柔性物体非刚性操纵规划",
        "capability_name_en": "Deformable object manipulation planning",
        "keywords": ["毛巾", "衣物", "柔性物体", "deformable manipulation"],
        "evaluation_nodes": ["是否能定义状态表示", "是否有仿真或实机闭环经验"],
    },
    "cap_laser_visual_slam": {
        "tech_layer": "spatial_navigation",
        "capability_name_zh": "激光/视觉/IMU多传感器融合建图",
        "capability_name_en": "LiDAR-visual-IMU SLAM",
        "keywords": ["LIO-SAM", "ORB-SLAM3", "VIO", "IMU", "图优化"],
        "evaluation_nodes": ["是否调过真实传感器标定", "是否能定位退化场景"],
    },
    "cap_dynamic_obstacle_avoidance": {
        "tech_layer": "spatial_navigation",
        "capability_name_zh": "高动态环境实时局部避障与重规划",
        "capability_name_en": "Dynamic obstacle avoidance and replanning",
        "keywords": ["DWA", "TEB", "Nav2", "costmap", "局部避障"],
        "evaluation_nodes": ["是否解决过人宠动态干扰", "是否能解释代价地图参数"],
    },
    "cap_long_term_localization": {
        "tech_layer": "spatial_navigation",
        "capability_name_zh": "长期地图动态更新与高精重定位",
        "capability_name_en": "Long-term localization and map updating",
        "keywords": ["重定位", "地图更新", "家具变化", "long-term localization"],
        "evaluation_nodes": ["是否处理过环境长期变化", "是否有闭环验证指标"],
    },
    "cap_tactile_feedback": {
        "tech_layer": "actuation_tactile",
        "capability_name_zh": "触觉反馈滑动检测与力控制",
        "capability_name_en": "Tactile feedback for slip detection and force control",
        "keywords": ["GelSight", "电子皮肤", "触觉", "滑动检测"],
        "evaluation_nodes": ["是否采集过触觉数据", "是否能闭环调抓取力度"],
    },
    "cap_compliance_control": {
        "tech_layer": "actuation_tactile",
        "capability_name_zh": "柔顺控制/阻抗控制/导纳控制",
        "capability_name_en": "Compliance, impedance, and admittance control",
        "keywords": ["柔顺控制", "阻抗控制", "导纳控制", "安全交互"],
        "evaluation_nodes": ["是否理解力位混合控制", "是否考虑人机安全边界"],
    },
    "cap_in_hand_manipulation": {
        "tech_layer": "actuation_tactile",
        "capability_name_zh": "手内操纵",
        "capability_name_en": "In-hand manipulation",
        "keywords": ["手内操纵", "灵巧手", "finger gaiting", "dexterous manipulation"],
        "evaluation_nodes": ["是否能控制多指协同", "是否有实机或高保真仿真经验"],
    },
    "cap_foc_bldc": {
        "tech_layer": "embedded_hardware",
        "capability_name_zh": "无刷电机/力矩电机FOC三环控制",
        "capability_name_en": "FOC control for BLDC and torque motors",
        "keywords": ["FOC", "BLDC", "三环控制", "力矩电机", "电机控制"],
        "evaluation_nodes": ["是否调过电流/速度/位置环", "是否能用示波器定位问题"],
    },
    "cap_rtos_firmware": {
        "tech_layer": "embedded_hardware",
        "capability_name_zh": "STM32/FreeRTOS/实时Linux固件与调度",
        "capability_name_en": "RTOS firmware and realtime scheduling",
        "keywords": ["STM32", "FreeRTOS", "实时Linux", "固件", "调度"],
        "evaluation_nodes": ["是否理解中断、DMA、任务优先级", "是否处理过实时抖动"],
    },
    "cap_bus_communication": {
        "tech_layer": "embedded_hardware",
        "capability_name_zh": "确定性总线协议与多轴同步",
        "capability_name_en": "Deterministic bus communication and multi-axis sync",
        "keywords": ["EtherCAT", "CANopen", "RS485", "多轴同步", "总线协议"],
        "evaluation_nodes": ["是否抓过总线包", "是否能处理丢包、同步和时钟漂移"],
    },
    "cap_teleop_system": {
        "tech_layer": "teleoperation",
        "capability_name_zh": "高精度六自由度遥操作映射",
        "capability_name_en": "High-precision 6-DoF teleoperation mapping",
        "keywords": ["Vision Pro", "VR", "动捕手套", "示教器", "遥操作"],
        "evaluation_nodes": ["是否能处理坐标系映射", "是否考虑延迟、限位和安全"],
    },
    "cap_data_alignment": {
        "tech_layer": "data_infrastructure",
        "capability_name_zh": "多源机器人数据毫秒级时间戳对齐",
        "capability_name_en": "Millisecond timestamp alignment for robot data",
        "keywords": ["时间戳对齐", "多摄像头", "关节角", "力矩", "同步"],
        "evaluation_nodes": ["是否能解释不同频率采样对齐", "是否处理过丢帧和时钟漂移"],
    },
    "cap_data_cleaning_pipeline": {
        "tech_layer": "data_infrastructure",
        "capability_name_zh": "无效遥操作与失败数据清洗Pipeline",
        "capability_name_en": "Teleoperation data cleaning pipeline",
        "keywords": ["数据清洗", "Pipeline", "OpenTelemetry", "Python", "失败样本"],
        "evaluation_nodes": ["是否能自动剔除坏数据", "是否能保留失败案例用于训练"],
    },
}


STATIC_DYNAMIC_DECISION_TABLE: List[Dict[str, Any]] = [
    {
        "item": "技术层分类",
        "classification": "static_base",
        "search_verification": "low",
        "long_term_memory": "low",
        "update_policy": "人工版本化更新",
    },
    {
        "item": "岗位大类",
        "classification": "semi_static_base",
        "search_verification": "medium",
        "long_term_memory": "medium",
        "update_policy": "允许新增和合并，但不随单次搜索波动",
    },
    {
        "item": "能力 ID / 能力名称",
        "classification": "semi_static_base",
        "search_verification": "medium",
        "long_term_memory": "medium",
        "update_policy": "名称稳定，定义和证据版本化",
    },
    {
        "item": "能力与岗位映射",
        "classification": "dynamic_calibration",
        "search_verification": "high",
        "long_term_memory": "high",
        "update_policy": "由 JD、论文、开源、面试反馈和人工修订共同校准",
    },
    {
        "item": "必备 / 加分 / 排除项",
        "classification": "dynamic_calibration",
        "search_verification": "high",
        "long_term_memory": "high",
        "update_policy": "随岗位级别、公司阶段、市场供给和成功画像调整",
    },
    {
        "item": "技术路线覆盖范围",
        "classification": "dynamic_evidence",
        "search_verification": "high",
        "long_term_memory": "medium",
        "update_policy": "定期用学术、开源、产业资料补充和淘汰路线",
    },
    {
        "item": "目标公司 / 实验室 / 次优来源",
        "classification": "dynamic_market_fact",
        "search_verification": "high",
        "long_term_memory": "high",
        "update_policy": "由招聘、官网、新闻、论文、专利和实际触达结果更新",
    },
    {
        "item": "证据链记录",
        "classification": "dynamic_traceable_record",
        "search_verification": "high",
        "long_term_memory": "high",
        "update_policy": "每条结论保留来源、时间、摘录、置信度和验证状态",
    },
    {
        "item": "人工修订 / 面试反馈 / offer 或 reject / 入职表现",
        "classification": "long_term_memory",
        "search_verification": "medium",
        "long_term_memory": "high",
        "update_policy": "持续回流 Memory，反向修正能力权重和岗位标准",
    },
]


EVIDENCE_RECORD_SCHEMA: Dict[str, Any] = {
    "required_fields": [
        "source_type",
        "source_key",
        "title",
        "url_or_reference",
        "published_at",
        "retrieved_at",
        "claim",
        "evidence_excerpt",
        "confidence",
        "validation_status",
    ],
    "source_types": [
        "academic",
        "industry_jd",
        "company_official",
        "open_source",
        "patent",
        "filing_or_report",
        "news",
        "candidate_material",
        "human_feedback",
    ],
    "validation_statuses": [
        "unverified",
        "single_source",
        "cross_validated",
        "human_approved",
        "deprecated",
    ],
    "confidence_scale": "0.0-1.0，先按来源可信度、独立来源数量、时间新鲜度和人工确认加权。",
}


CROSS_VALIDATION_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "must_have_cross_domain_evidence",
        "description": "把某能力标为必备前，至少需要学术/开源/产业/候选人反馈中的两个独立来源域支持。",
        "minimum_domains": 2,
    },
    {
        "rule_id": "industry_priority_requires_market_signal",
        "description": "调整能力重要性排序前，必须有 JD、公司官网、招聘热度、面试反馈或 offer 结果之一作为产业信号。",
        "minimum_domains": 1,
    },
    {
        "rule_id": "long_term_memory_overrides_single_search",
        "description": "单次搜索不能覆盖长期面试和入职表现记忆；冲突时输出冲突并等待人工确认。",
        "requires_human_review": True,
    },
    {
        "rule_id": "route_coverage_requires_explicit_scope",
        "description": "技术路线覆盖必须说明适用边界，例如室内低速、家庭动态障碍、长期地图、端侧算力或真实底盘。",
        "requires_scope": True,
    },
]


DEFAULT_CAPABILITY_TRACEABILITY: Dict[str, Any] = {
    "static_parts": ["capability_id", "capability_name_zh", "capability_name_en", "tech_layer"],
    "dynamic_parts": ["is_required", "importance_rank", "route_coverage", "evidence_records", "market_weight"],
    "evidence_requirements": [
        {
            "source_type": "academic",
            "source_keys": ["scholar_arxiv", "conference_paper_lists"],
            "minimum_items": 1,
            "validates": "学术可行性和技术路线演进",
        },
        {
            "source_type": "industry_jd",
            "source_keys": ["recruitment_boards_cn", "company_websites"],
            "minimum_items": 1,
            "validates": "岗位市场需求和产业落地权重",
        },
        {
            "source_type": "human_feedback",
            "source_keys": ["interview_feedback", "offer_reject", "hire_performance"],
            "minimum_items": 1,
            "validates": "能力标准是否预测真实招聘和入职表现",
        },
    ],
    "route_breakdown": [],
    "open_assumptions": ["当前能力标准是专家启发式基线，需要证据链和人工反馈持续校准。"],
    "memory_signals": ["人工修订意见", "面试反馈", "offer/reject 结果", "入职后表现"],
}


CAPABILITY_TRACEABILITY_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "cap_laser_visual_slam": {
        "route_breakdown": [
            {
                "route_id": "sensor_calibration_sync",
                "name_zh": "传感器标定与时间同步",
                "keywords": ["相机-LiDAR-IMU外参", "时间戳同步", "rolling shutter", "硬件触发"],
                "validation_questions": ["是否做过真实传感器外参标定", "是否定位过不同频率传感器的时间漂移"],
            },
            {
                "route_id": "state_estimation",
                "name_zh": "状态估计与后端优化",
                "keywords": ["VIO", "LIO", "RGB-D SLAM", "EKF", "因子图", "回环检测"],
                "validation_questions": ["是否能解释退化场景", "是否能权衡前端里程计和后端图优化"],
            },
            {
                "route_id": "map_representation",
                "name_zh": "地图表示与更新接口",
                "keywords": ["稀疏地图", "稠密地图", "占据栅格", "语义地图", "拓扑图"],
                "validation_questions": ["是否能说明地图如何服务导航和操作", "是否处理过地图尺寸和端侧算力约束"],
            },
            {
                "route_id": "engineering_observability",
                "name_zh": "工程部署与可观测性",
                "keywords": ["ROS2", "日志回放", "定位健康度", "漂移报警", "端侧部署"],
                "validation_questions": ["是否能用日志复现定位失败", "是否定义过重定位成功率和漂移指标"],
            },
        ],
        "evidence_requirements": [
            {
                "source_type": "academic",
                "source_keys": ["scholar_arxiv", "conference_paper_lists"],
                "minimum_items": 3,
                "validates": "VIO/LIO/RGB-D/图优化路线是否仍是主流候选路线",
            },
            {
                "source_type": "open_source",
                "source_keys": ["github"],
                "minimum_items": 2,
                "validates": "候选人是否能落到可运行 SLAM 系统和真实工程 issue",
            },
            {
                "source_type": "industry_jd",
                "source_keys": ["recruitment_boards_cn", "company_websites"],
                "minimum_items": 3,
                "validates": "多传感器建图是否被目标公司明确写入岗位要求",
            },
        ],
        "open_assumptions": [
            "家庭机器人 SLAM 岗通常需要真实传感器标定和端侧部署经验。",
            "单一视觉或单一激光路线是否足够，需要根据目标硬件配置和家庭场景重新验证。",
        ],
    },
    "cap_dynamic_obstacle_avoidance": {
        "route_breakdown": [
            {
                "route_id": "local_planner",
                "name_zh": "局部规划器与控制接口",
                "keywords": ["DWA", "TEB", "MPC local planner", "Nav2", "速度障碍"],
                "validation_questions": ["是否调过局部规划器参数", "是否处理过规划振荡和原地转圈"],
            },
            {
                "route_id": "costmap_dynamic_layer",
                "name_zh": "动态障碍代价地图",
                "keywords": ["costmap layer", "动态障碍", "膨胀半径", "障碍预测", "实时分割"],
                "validation_questions": ["是否能解释代价地图参数", "是否处理过人宠动态干扰"],
            },
            {
                "route_id": "recovery_behavior",
                "name_zh": "失败恢复与重规划策略",
                "keywords": ["behavior tree", "recovery", "replanning", "deadlock", "狭窄通道"],
                "validation_questions": ["是否设计过恢复行为", "是否能定义可回归的失败场景库"],
            },
            {
                "route_id": "safety_boundary",
                "name_zh": "家庭场景安全边界",
                "keywords": ["低速安全", "儿童/宠物", "急停", "软硬件协同", "碰撞风险"],
                "validation_questions": ["是否考虑过人机安全边界", "是否能联动底盘控制和急停策略"],
            },
        ],
        "evidence_requirements": [
            {
                "source_type": "industry_jd",
                "source_keys": ["recruitment_boards_cn", "company_websites"],
                "minimum_items": 3,
                "validates": "实时局部避障是否是家庭/服务机器人岗位高频要求",
            },
            {
                "source_type": "open_source",
                "source_keys": ["github"],
                "minimum_items": 2,
                "validates": "Nav2、costmap、局部规划相关工程能力是否可从项目证据识别",
            },
            {
                "source_type": "human_feedback",
                "source_keys": ["interview_feedback", "field_failures"],
                "minimum_items": 1,
                "validates": "面试题能否区分只会调用导航栈和能定位真实失败的人",
            },
        ],
        "open_assumptions": [
            "家庭高动态环境比仓储静态环境更强调局部避障和失败恢复。",
            "是否必须会 Nav2 取决于目标公司技术栈，不能把框架名等同于能力本身。",
        ],
    },
    "cap_long_term_localization": {
        "route_breakdown": [
            {
                "route_id": "long_term_map_lifecycle",
                "name_zh": "长期地图生命周期管理",
                "keywords": ["地图版本", "变化检测", "增量更新", "家具变化", "地图回滚"],
                "validation_questions": ["是否处理过环境长期变化", "是否定义过地图更新触发条件"],
            },
            {
                "route_id": "relocalization",
                "name_zh": "高精重定位与失效恢复",
                "keywords": ["重定位", "place recognition", "回环", "定位丢失恢复", "全局定位"],
                "validation_questions": ["是否量化过重定位成功率", "是否处理过低纹理和重复结构环境"],
            },
            {
                "route_id": "semantic_memory",
                "name_zh": "语义空间记忆",
                "keywords": ["语义地图", "房间拓扑", "物体位置记忆", "家庭空间记忆"],
                "validation_questions": ["是否能把地图变化服务于任务规划", "是否能处理物体/家具位置长期漂移"],
            },
            {
                "route_id": "fleet_feedback_loop",
                "name_zh": "设备数据回流与评测闭环",
                "keywords": ["日志回流", "失败案例库", "A/B测试", "定位健康度", "线上回归"],
                "validation_questions": ["是否建立过定位失败案例库", "是否能把线上数据反馈到地图和参数更新"],
            },
        ],
        "evidence_requirements": [
            {
                "source_type": "academic",
                "source_keys": ["scholar_arxiv", "conference_paper_lists"],
                "minimum_items": 2,
                "validates": "长期定位、变化检测和语义地图路线是否有持续研究基础",
            },
            {
                "source_type": "company_official",
                "source_keys": ["company_websites", "filings_annual_reports"],
                "minimum_items": 2,
                "validates": "目标公司产品是否真的需要长期地图更新能力",
            },
            {
                "source_type": "human_feedback",
                "source_keys": ["interview_feedback", "hire_performance"],
                "minimum_items": 1,
                "validates": "该能力是否能预测候选人在真实产品中的表现",
            },
        ],
        "open_assumptions": [
            "长期地图能力对家庭机器人高价值，但对短周期 demo 岗位可能不是入门必备。",
            "高精重定位指标需要和硬件传感器、家庭面积、任务类型一起定义。",
        ],
    },
}

ROBOT_TEAM_PROFILES: Dict[str, Dict[str, Any]] = {
    "system_architect": {
        "name_zh": "系统级总架构师",
        "mission": "负责大脑、小脑、硬件、数据、操作系统和客户场景之间的架构解耦。",
        "required_domains": ["系统架构", "机器人整机", "软硬件协同", "数据闭环", "客户场景"],
        "ideal_backgrounds": ["机器人实验室", "自动驾驶公司", "工业机器人公司", "大模型公司", "复杂硬件系统公司"],
        "mapped_role_keys": ["robot_system_architect"],
        "capability_requirements": ["cap_sys_integration", "cap_latency_optimization", "cap_failover_design", "cap_compute_allocation"],
        "evaluation_focus": ["是否能定义跨模块边界", "是否能做系统级取舍", "是否能处理实机部署和客户现场反馈"],
    },
    "ai_multimodal_scientist": {
        "name_zh": "AI 与多模态算法科学家",
        "mission": "负责视觉、语言、动作、触觉、空间重建和世界预测模型。",
        "required_domains": ["大规模训练", "视频模型", "3D视觉", "VLA", "扩散模型", "自回归模型", "模型压缩"],
        "ideal_backgrounds": ["大模型公司", "多模态模型团队", "具身智能实验室", "自动驾驶感知/预测团队"],
        "mapped_role_keys": ["vla_embodied_expert", "world_model_simulation", "multimodal_perception", "vision_3d_algorithm"],
        "capability_requirements": [
            "cap_vla_imitation",
            "cap_diffusion_policy",
            "cap_action_tokenization",
            "cap_world_model_predict",
            "cap_vlm_grounding",
            "cap_spatial_reconstruction",
        ],
        "evaluation_focus": ["是否能把模型能力接到动作闭环", "是否理解数据质量和训练规模", "是否能在边缘端压缩部署"],
    },
    "robot_control_scientist": {
        "name_zh": "机器人控制科学家",
        "mission": "负责 WBC、MPC、轨迹优化、状态估计、阻抗控制、强化学习控制和稳定性验证。",
        "required_domains": ["WBC", "MPC", "轨迹优化", "状态估计", "阻抗控制", "强化学习控制", "稳定性验证"],
        "ideal_backgrounds": ["足式机器人公司", "工业机器人公司", "机器人控制实验室", "自动驾驶控制团队"],
        "mapped_role_keys": ["motion_control_mpc_wbc", "manipulation_grasping", "dexterous_hand_control", "slam_navigation_expert"],
        "capability_requirements": [
            "cap_wbc_qp",
            "cap_mpc_locomotion",
            "cap_state_estimation",
            "cap_compliance_control",
            "cap_motion_planning",
        ],
        "evaluation_focus": ["是否有实机闭环经验", "是否能解释稳定性边界", "是否能让模型输出安全落到真实机器人"],
    },
    "mechatronics_structure_expert": {
        "name_zh": "机电与结构专家",
        "mission": "负责关节、传动、灵巧手、散热、线束、结构强度和可制造性。",
        "required_domains": ["关节模组", "传动系统", "灵巧手", "热设计", "线束", "结构强度", "DFM"],
        "ideal_backgrounds": ["消费硬件公司", "工业机器人公司", "电机/执行器公司", "汽车零部件公司"],
        "mapped_role_keys": ["embedded_foc_engineer", "dexterous_hand_control", "qa_reliability_engineer"],
        "capability_requirements": ["cap_foc_bldc", "cap_tactile_feedback", "cap_hardware_stress_test", "cap_bus_communication"],
        "evaluation_focus": ["是否能把可靠性问题前移到设计阶段", "是否理解量产制造约束", "是否能闭环硬件失效分析"],
    },
    "embedded_realtime_engineer": {
        "name_zh": "嵌入式与实时系统工程师",
        "mission": "负责驱动板、通信总线、RTOS、实时调度、传感器同步和边缘推理。",
        "required_domains": ["驱动板", "通信总线", "RTOS", "实时调度", "传感器同步", "边缘推理"],
        "ideal_backgrounds": ["机器人嵌入式团队", "汽车电子团队", "运动控制公司", "边缘计算硬件团队"],
        "mapped_role_keys": ["embedded_foc_engineer", "robot_data_infrastructure", "robot_system_architect"],
        "capability_requirements": ["cap_rtos_firmware", "cap_bus_communication", "cap_latency_optimization", "cap_data_alignment"],
        "evaluation_focus": ["是否能定位实时抖动", "是否能做多传感器同步", "是否能支撑世界模型进入真实设备"],
    },
    "product_delivery_team": {
        "name_zh": "产品和行业交付团队",
        "mission": "负责找到可复制场景，将 demo 转化为客户付费。",
        "required_domains": ["场景定义", "客户交付", "运维体系", "售前验证", "商业闭环", "现场问题管理"],
        "ideal_backgrounds": ["机器人行业解决方案团队", "智能硬件交付团队", "工业自动化集成商", "ToB 产品团队"],
        "mapped_role_keys": ["qa_reliability_engineer", "robot_system_architect", "robot_data_infrastructure"],
        "capability_requirements": ["cap_corner_case_capture", "cap_automated_log_analysis", "cap_sys_integration", "cap_data_cleaning_pipeline"],
        "evaluation_focus": ["是否能定义可复制客户场景", "是否能把现场问题转成产品迭代", "是否能建立部署和运维节奏"],
    },
}

ROBOT_ROLES_METADATA: Dict[str, Dict[str, Any]] = {
    "robot_system_architect": {
        "name_zh": "机器人系统架构师",
        "tech_layer": ["system_architecture", "hardware_software_co_design"],
        "ai_native_friendly": False,
        "ai_native_fit_level": "极低",
        "capability_requirements": ["cap_sys_integration", "cap_latency_optimization", "cap_failover_design", "cap_compute_allocation"],
        "exclusion_keywords": ["纯算法研究员", "无实机部署经验", "单模块工程师", "无全栈全局观"],
        "target_targets": ["特斯拉 Optimus", "宇树", "智元机器人", "开普勒", "小米物理 AI 组", "小鹏鹏行", "大疆"],
    },
    "motion_control_mpc_wbc": {
        "name_zh": "运动控制 / MPC / WBC 工程师",
        "tech_layer": ["cerebellum_control", "dynamics"],
        "ai_native_friendly": False,
        "ai_native_fit_level": "低",
        "capability_requirements": ["cap_wbc_qp", "cap_mpc_locomotion", "cap_state_estimation", "cap_sim2real_loco"],
        "exclusion_keywords": ["只懂纯几何运动学", "不懂动力学", "不懂接触力模型"],
        "target_targets": ["宇树", "波士顿动力", "逐际动力", "乐聚机器人", "优必选", "MIT Biomimetic Robotics Lab"],
    },
    "qa_reliability_engineer": {
        "name_zh": "整机测试 / 可靠性工程师",
        "tech_layer": ["QA_reliability", "hardware_test"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "中等",
        "capability_requirements": ["cap_hardware_stress_test", "cap_corner_case_capture", "cap_automated_log_analysis"],
        "exclusion_keywords": ["只做手工测试", "无自动化脚本能力"],
        "target_targets": ["石头科技", "科沃斯", "追觅", "九号公司", "汽车电子测试部"],
    },
    "vla_embodied_expert": {
        "name_zh": "VLA / 具身智能算法工程师",
        "tech_layer": ["brain_learning", "foundation_model"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "极高",
        "capability_requirements": ["cap_vla_imitation", "cap_diffusion_policy", "cap_action_tokenization", "cap_long_horizon_task"],
        "exclusion_keywords": ["纯NLP", "文本生成", "无物理世界实体", "推荐系统"],
        "target_targets": ["World Labs", "Physical Intelligence", "AMI Labs", "银河通用", "北大/清华具身智能实验室"],
        "suggested_questions": [
            "面对家庭场景中易碎/透明物体，如何在VLA数据流水线中做Action Token对齐与增强？",
            "说明你复现Diffusion Policy或Imitation Learning项目时遇到的核心痛点和优化方式。",
        ],
    },
    "world_model_simulation": {
        "name_zh": "世界模型 / 仿真算法工程师",
        "tech_layer": ["brain_simulator", "data_generation"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "高",
        "capability_requirements": ["cap_world_model_predict", "cap_sim_env_building", "cap_synthetic_data_gen"],
        "exclusion_keywords": ["只做静态3D建模", "无物理仿真经验"],
        "target_targets": ["NVIDIA Cosmos", "51World", "腾讯智能路网", "腾讯天美", "网易雷火"],
    },
    "multimodal_perception": {
        "name_zh": "多模态感知算法工程师",
        "tech_layer": ["perception_vlm"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "极高",
        "capability_requirements": ["cap_vlm_grounding", "cap_audio_intent_parse", "cap_scene_understanding"],
        "exclusion_keywords": ["只做分类模型", "无开放域识别经验"],
        "target_targets": ["智谱", "零一万物", "月之暗面", "Qwen", "商汤多模态组"],
    },
    "vision_3d_algorithm": {
        "name_zh": "3D 视觉算法工程师",
        "tech_layer": ["perception_spatial"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "中高",
        "capability_requirements": ["cap_6d_pose", "cap_spatial_reconstruction", "cap_point_cloud_seg"],
        "exclusion_keywords": ["只做2D检测", "无几何基础"],
        "target_targets": ["Apple Vision Pro 研发链", "大疆感知组", "奥比中光", "商汤 3D 组"],
    },
    "manipulation_grasping": {
        "name_zh": "操作规划 / 抓取算法工程师",
        "tech_layer": ["cerebellum_action", "manipulation"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "中高",
        "capability_requirements": ["cap_grasp_detection", "cap_motion_planning", "cap_deformable_objects"],
        "exclusion_keywords": ["只会仿真不调实机", "无抓取失败分析"],
        "target_targets": ["库卡", "ABB", "梅卡曼德", "大族机器人", "高校机器人操作实验室"],
    },
    "slam_navigation_expert": {
        "name_zh": "SLAM / 导航算法工程师",
        "tech_layer": ["spatial_navigation"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "中等",
        "capability_requirements": ["cap_laser_visual_slam", "cap_dynamic_obstacle_avoidance", "cap_long_term_localization"],
        "exclusion_keywords": ["纯网页前端", "单纯GPS室内导航", "未上过真实底盘"],
        "target_targets": ["高仙自动化", "九号机器人", "极智嘉", "海康机器人", "小鹏/蔚来/理想AVP算法组"],
        "suggested_questions": [
            "在狭窄高动态家庭环境中，Nav2局部规划陷入死循环时，你如何优化Costmap？",
        ],
    },
    "dexterous_hand_control": {
        "name_zh": "灵巧手控制工程师",
        "tech_layer": ["actuation_tactile"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "中等",
        "capability_requirements": ["cap_tactile_feedback", "cap_compliance_control", "cap_in_hand_manipulation"],
        "exclusion_keywords": ["只会开环控制", "无触觉或力控经验"],
        "target_targets": ["因时机器人", "大寰机器人", "帕西尼感知", "柔触机器人"],
    },
    "embedded_foc_engineer": {
        "name_zh": "嵌入式控制 / FOC 工程师",
        "tech_layer": ["embedded_hardware"],
        "ai_native_friendly": False,
        "ai_native_fit_level": "低",
        "capability_requirements": ["cap_foc_bldc", "cap_rtos_firmware", "cap_bus_communication"],
        "exclusion_keywords": ["只写上层应用", "不懂示波器", "无电机调试经验"],
        "target_targets": ["汇川技术", "步科", "大疆动力组", "拓普集团", "大族电机"],
    },
    "robot_data_infrastructure": {
        "name_zh": "机器人数据采集 / 遥操作工程师",
        "tech_layer": ["data_infrastructure", "teleoperation"],
        "ai_native_friendly": True,
        "ai_native_fit_level": "极高",
        "capability_requirements": ["cap_teleop_system", "cap_data_alignment", "cap_data_cleaning_pipeline"],
        "exclusion_keywords": ["传统外包数据标注", "无编程能力"],
        "target_targets": ["游戏动捕数据工程师", "VR/AR交互工程师", "车载数据清洗工程师", "数据标注平台架构师"],
        "suggested_questions": [
            "如果使用Vision Pro采集第一视角具身数据，如何解决90Hz头显与200Hz/1kHz机械臂控制频率的时间戳对齐？",
        ],
    },
}


def get_capabilities_for_role(role_key: str) -> List[Dict[str, Any]]:
    role = ROBOT_ROLES_METADATA[role_key]
    return [CAPABILITY_STANDARDS[capability_id] | {"capability_id": capability_id} for capability_id in role["capability_requirements"]]


def get_capability_traceability(capability_id: str) -> Dict[str, Any]:
    capability = CAPABILITY_STANDARDS[capability_id]
    profile = deepcopy(DEFAULT_CAPABILITY_TRACEABILITY)
    override = CAPABILITY_TRACEABILITY_OVERRIDES.get(capability_id, {})
    for key, value in override.items():
        profile[key] = deepcopy(value)

    return {
        "capability_id": capability_id,
        "capability_name_zh": capability["capability_name_zh"],
        "capability_name_en": capability["capability_name_en"],
        "tech_layer": capability["tech_layer"],
        "keywords": capability["keywords"],
        "evaluation_nodes": capability["evaluation_nodes"],
        "static_parts": profile["static_parts"],
        "dynamic_parts": profile["dynamic_parts"],
        "route_breakdown": profile["route_breakdown"],
        "evidence_requirements": profile["evidence_requirements"],
        "open_assumptions": profile["open_assumptions"],
        "memory_signals": profile["memory_signals"],
        "evidence_record_schema": EVIDENCE_RECORD_SCHEMA,
        "validation_status": "unverified_static_baseline",
    }


def get_role_capability_traceability(role_key: str) -> Dict[str, Any]:
    role = ROBOT_ROLES_METADATA[role_key]
    capability_profiles = [
        get_capability_traceability(capability_id)
        for capability_id in role["capability_requirements"]
    ]
    return {
        "role_key": role_key,
        "role_name_zh": role["name_zh"],
        "static_base": {
            "tech_layer": role["tech_layer"],
            "role_definition": role["name_zh"],
            "capability_ids": role["capability_requirements"],
        },
        "dynamic_calibration_targets": [
            "能力是否仍应列为必备",
            "必备/加分/排除项边界",
            "能力重要性排序",
            "技术路线覆盖范围",
            "目标公司、实验室和次优来源迁移价值",
        ],
        "capabilities": capability_profiles,
        "cross_validation_rules": CROSS_VALIDATION_RULES,
        "long_term_memory_targets": [
            "人工修订意见",
            "面试反馈",
            "offer/reject 结果",
            "入职后表现",
            "搜索证据链版本",
        ],
    }


def validate_role_capabilities() -> None:
    missing = {
        capability_id
        for role in ROBOT_ROLES_METADATA.values()
        for capability_id in role["capability_requirements"]
        if capability_id not in CAPABILITY_STANDARDS
    }
    missing.update(
        capability_id
        for profile in ROBOT_TEAM_PROFILES.values()
        for capability_id in profile["capability_requirements"]
        if capability_id not in CAPABILITY_STANDARDS
    )
    if missing:
        raise ValueError(f"Missing capability standards: {sorted(missing)}")
