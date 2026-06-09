import type { Candidate } from "../../features/candidates/types";
import type { JobProfile } from "../../features/jobs/types";

export type WeeklyReport = {
  conclusion: string;
  keyProgress: string[];
  topCandidates: string[];
  risks: string[];
  nextActions: string[];
};

export type ProjectMock = {
  projectId: string;
  name: string;
  owner: string;
  updatedAt: string;
  jobs: JobProfile[];
  candidates: Candidate[];
  weeklyReport: WeeklyReport;
};

export const projectMock: ProjectMock = {
  projectId: "project_home_robot_recruiting",
  name: "家庭机器人核心招聘项目",
  owner: "Recruiting Ops",
  updatedAt: "2026-06-09T10:00:00+08:00",
  jobs: [
    {
      jobProfileId: "job_vla_algorithm",
      roleName: "VLA / 具身智能算法工程师",
      priorityLevel: "P0",
      isAiNativeFriendly: true,
      essentialCapabilities: [
        { capabilityId: "cap_vla_policy", name: "VLA 策略建模", weight: 0.34 },
        { capabilityId: "cap_real_robot", name: "实机部署闭环", weight: 0.3 },
        { capabilityId: "cap_ros_latency", name: "ROS 低延迟控制链路", weight: 0.22 },
      ],
      preferredCapabilities: [
        { capabilityId: "cap_open_source", name: "开源工程影响力", weight: 0.08 },
        { capabilityId: "cap_paper_repro", name: "论文复现与消融", weight: 0.06 },
      ],
      exclusionTags: ["纯仿真无实机", "无端到端策略经验"],
      targetCompanyTypes: ["具身智能创业公司", "机器人整机公司", "自动驾驶感知团队"],
      targetSchoolsLabs: ["CMU RI", "Stanford AI Lab", "清华交叉信息院"],
      salaryRangeMin: 60000,
      salaryRangeMax: 90000,
      funnel: [
        { key: "sourcing", label: "人才地图", count: 42, target: 60, status: "processing" },
        { key: "screening", label: "初筛", count: 18, target: 24, status: "processing" },
        { key: "evaluation", label: "Agent 评估", count: 9, target: 12, status: "done" },
        { key: "human_gate", label: "人工复核", count: 1, target: 4, status: "awaiting_human" },
        { key: "interview", label: "技术面", count: 3, target: 5, status: "processing" },
        { key: "offer", label: "Offer", count: 0, target: 1, status: "pending" },
      ],
    },
    {
      jobProfileId: "job_robot_data_platform",
      roleName: "机器人数据平台工程师",
      priorityLevel: "P1",
      isAiNativeFriendly: true,
      essentialCapabilities: [
        { capabilityId: "cap_data_pipeline", name: "多源数据管线", weight: 0.32 },
        { capabilityId: "cap_labeling_ops", name: "标注与数据治理", weight: 0.26 },
        { capabilityId: "cap_retrieval", name: "检索与评估闭环", weight: 0.2 },
      ],
      preferredCapabilities: [
        { capabilityId: "cap_mlops", name: "MLOps / Feature Store", weight: 0.12 },
        { capabilityId: "cap_privacy", name: "数据权限与隐私治理", weight: 0.1 },
      ],
      exclusionTags: ["只做 BI 报表", "无生产数据链路"],
      targetCompanyTypes: ["机器人数据团队", "自动驾驶数据平台", "AI Infra 团队"],
      targetSchoolsLabs: ["UW CSE", "上海交大 AI Lab", "浙大 CAD&CG"],
      salaryRangeMin: 45000,
      salaryRangeMax: 70000,
      funnel: [
        { key: "sourcing", label: "人才地图", count: 36, target: 45, status: "processing" },
        { key: "screening", label: "初筛", count: 15, target: 18, status: "processing" },
        { key: "evaluation", label: "Agent 评估", count: 6, target: 8, status: "done" },
        { key: "human_gate", label: "人工复核", count: 0, target: 2, status: "pending" },
        { key: "interview", label: "技术面", count: 2, target: 3, status: "processing" },
        { key: "offer", label: "Offer", count: 1, target: 1, status: "done" },
      ],
    },
  ],
  candidates: [
    {
      candidateId: "cand_lin_chen",
      name: "Alex Chen",
      targetJobProfileId: "job_vla_algorithm",
      sourcePlatform: "GitHub",
      sourceUrl: "https://github.com/example/vla-policy",
      currentCompany: "Embodied AI Lab",
      city: "深圳",
      title: "Robotics Research Engineer",
      isAiNativeTalent: true,
      technicalLayerTags: ["VLA", "Diffusion Policy", "ROS"],
      parsedCapabilities: ["实机策略部署", "多模态模型微调", "低延迟控制"],
      githubMetrics: { repositories: 18, stars: 1240 },
      paperMetrics: { papers: 3, citations: 168 },
      matchScore: 92,
      stage: "technical_interview",
      stepStatus: "processing",
      outreachStatus: "not_sent",
      riskAlerts: ["需要验证真实家庭场景失败样本处理经验"],
      evidence: [
        { label: "实机 Demo", source: "demo", summary: "双臂抓取任务有连续运行视频与日志截图。" },
        { label: "开源代码", source: "github", summary: "策略训练与 ROS bridge 代码结构完整。" },
      ],
    },
    {
      candidateId: "cand_zhou_han",
      name: "Zhou Han",
      targetJobProfileId: "job_vla_algorithm",
      sourcePlatform: "Paper",
      sourceUrl: "https://example.com/papers/robot-generalization",
      currentCompany: "Robot Foundation Team",
      city: "上海",
      title: "Applied Scientist",
      isAiNativeTalent: true,
      technicalLayerTags: ["VLA", "Generalization", "Sim2Real"],
      parsedCapabilities: ["长尾泛化评估", "数据增强", "策略消融"],
      githubMetrics: { repositories: 9, stars: 410 },
      paperMetrics: { papers: 5, citations: 326 },
      matchScore: 88,
      stage: "human_gate",
      stepStatus: "awaiting_human",
      outreachStatus: "not_sent",
      riskAlerts: ["实机部署 Owner 边界不清晰"],
      evidence: [
        { label: "论文", source: "paper", summary: "公开论文覆盖家庭长尾场景泛化评估。" },
        { label: "人工复核", source: "manual", summary: "需要面试官确认候选人是否主导实机闭环。" },
      ],
    },
    {
      candidateId: "cand_maya_li",
      name: "Maya Li",
      targetJobProfileId: "job_vla_algorithm",
      sourcePlatform: "LinkedIn",
      currentCompany: "Autonomy Stack",
      city: "北京",
      title: "ML Engineer",
      isAiNativeTalent: true,
      technicalLayerTags: ["Imitation Learning", "Data Collection"],
      parsedCapabilities: ["遥操作数据采集", "模仿学习训练", "评估集构建"],
      githubMetrics: { repositories: 6, stars: 180 },
      matchScore: 78,
      stage: "agent_evaluated",
      stepStatus: "done",
      outreachStatus: "not_sent",
      riskAlerts: ["机器人控制链路经验偏弱"],
      evidence: [
        { label: "项目经历", source: "resume", summary: "主导遥操作数据采集平台与训练样本清洗。" },
      ],
    },
    {
      candidateId: "cand_wang_ke",
      name: "Wang Ke",
      targetJobProfileId: "job_robot_data_platform",
      sourcePlatform: "Resume",
      currentCompany: "Autonomous Driving Data",
      city: "上海",
      title: "Senior Data Platform Engineer",
      isAiNativeTalent: false,
      technicalLayerTags: ["Data Pipeline", "MLOps", "Feature Store"],
      parsedCapabilities: ["多源同步", "数据质量监控", "训练样本版本化"],
      githubMetrics: { repositories: 4, stars: 96 },
      matchScore: 84,
      stage: "offer_review",
      stepStatus: "done",
      outreachStatus: "not_sent",
      riskAlerts: ["机器人域知识需要 onboarding"],
      evidence: [
        { label: "生产链路", source: "resume", summary: "建设 PB 级自动驾驶数据处理与样本治理平台。" },
      ],
    },
    {
      candidateId: "cand_sara_qi",
      name: "Sara Qi",
      targetJobProfileId: "job_robot_data_platform",
      sourcePlatform: "GitHub",
      sourceUrl: "https://github.com/example/robot-dataops",
      currentCompany: "AI Infra Startup",
      city: "杭州",
      title: "DataOps Engineer",
      isAiNativeTalent: true,
      technicalLayerTags: ["DataOps", "Evaluation", "RAG"],
      parsedCapabilities: ["检索评估", "数据权限", "自动化报告"],
      githubMetrics: { repositories: 12, stars: 520 },
      matchScore: 79,
      stage: "technical_interview",
      stepStatus: "processing",
      outreachStatus: "not_sent",
      riskAlerts: ["大规模实时数据经验待验证"],
      evidence: [
        { label: "开源工具", source: "github", summary: "维护面向机器人日志的检索和评估工具。" },
      ],
    },
  ],
  weeklyReport: {
    conclusion: "本周两个核心岗位均有可推进候选人，VLA 岗位需要尽快完成人工复核，数据平台岗位已有一个 Offer 候选人。",
    keyProgress: [
      "VLA 岗位完成 9 份 Agent 评估，3 人进入技术面。",
      "数据平台岗位完成 Offer review，候选人 Wang Ke 匹配生产数据链路需求。",
      "候选人 Sara Qi 的 RAG / DataOps 证据适合补充机器人日志检索方向。",
    ],
    topCandidates: ["Lin Chen: 92 分", "Zhou Han: 88 分", "Wang Ke: 84 分"],
    risks: [
      "VLA 岗位对实机 Owner 边界依赖人工确认。",
      "数据平台岗位候选人机器人域经验分布不均，需要补面试题。",
    ],
    nextActions: [
      "安排 Zhou Han 人工复核会。",
      "为 Lin Chen 准备家庭长尾失败样本追问。",
      "补充数据平台岗位的数据权限与隐私治理评分项。",
    ],
  },
};

export function getJobCandidateCounts(project: ProjectMock): Record<string, number> {
  return project.candidates.reduce<Record<string, number>>((accumulator, candidate) => {
    accumulator[candidate.targetJobProfileId] = (accumulator[candidate.targetJobProfileId] ?? 0) + 1;
    return accumulator;
  }, {});
}

export const projectSummary = {
  openJobs: projectMock.jobs.length,
  totalCandidates: projectMock.candidates.length,
  awaitingHuman: projectMock.candidates.filter((candidate) => candidate.stepStatus === "awaiting_human").length,
  averageMatchScore: Math.round(
    projectMock.candidates.reduce((sum, candidate) => sum + (candidate.matchScore ?? 0), 0) / projectMock.candidates.length,
  ),
};
