import type { Candidate } from "../candidates/types";
import type { FunnelStageKey, JobProfile, StepStatus } from "../jobs/types";
import { apiClient } from "../../shared/api/client";
import type { TaskSnapshot } from "../../shared/hooks/useTaskStream";

export type WeeklyReport = {
  conclusion?: string;
  keyProgress: string[];
  topCandidates: string[];
  risks: string[];
  nextActions: string[];
};

export type ProjectRecord = {
  projectId: string;
  name: string;
  status: string;
  owner?: string;
  updatedAt: string;
  openJobs: number;
  totalCandidates: number;
  awaitingHuman: number;
  averageMatchScore: number;
  weeklyReport: WeeklyReport;
};

export type RunProjectScenarioAction = "find_candidates" | "candidate_evaluation";

export type RunScenarioResponse = {
  task_id: string;
  scenario: string;
  status: string;
};

export type ScenarioMetaResponse = {
  scenarios?: Array<{ id: string; name_zh?: string; title?: string }>;
  agents?: Record<string, unknown>;
};

export type ListQueryOptions = {
  skip?: number;
  limit?: number;
};

type ProjectBackendResponse = {
  id: string;
  name: string;
  status: string;
  createdAt: string;
  openJobs: number;
  totalCandidates: number;
  awaitingHuman: number;
  averageMatchScore: number;
};

type JobBackendResponse = {
  id: string;
  projectId: string;
  title: string;
  headcount: number;
  status: string;
  pipelineStatus: string;
  candidateCount: number;
  averageMatchScore: number;
};

type CandidateBackendResponse = {
  id: string;
  jobCandidateId: number;
  jobId: string;
  jobTitle: string;
  name: string;
  currentCompany?: string | null;
  city?: string | null;
  email?: string | null;
  matchScore: number;
  pipelineStatus: string;
};

export function getProject(projectId: string): Promise<ProjectRecord> {
  return apiClient.get<ProjectBackendResponse>(`/projects/${encodeURIComponent(projectId)}`).then(mapProject);
}

export function getProjectJobs(projectId: string, options: ListQueryOptions = {}): Promise<JobProfile[]> {
  return apiClient
    .get<JobBackendResponse[]>(`/projects/${encodeURIComponent(projectId)}/jobs`, { query: options })
    .then((jobs) => jobs.map(mapJob));
}

export function getProjectCandidates(projectId: string, options: ListQueryOptions = {}): Promise<Candidate[]> {
  return apiClient
    .get<CandidateBackendResponse[]>(`/projects/${encodeURIComponent(projectId)}/candidates`, { query: options })
    .then((candidates) => candidates.map(mapCandidate));
}

export function getScenariosMeta() {
  return apiClient.get<ScenarioMetaResponse>("/scenarios/meta");
}

export function getTask(taskId: string) {
  return apiClient.get<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function confirmTask(
  taskId: string,
  action: "approve" | "edit" | "reject" = "approve",
  data: Record<string, unknown> = {},
) {
  return apiClient.post<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}/confirm`, {
    action,
    data,
  });
}

function scenarioForAction(action: RunProjectScenarioAction) {
  return action === "find_candidates" ? "B" : "C";
}

function inputForAction(action: RunProjectScenarioAction, job: JobProfile) {
  if (action === "find_candidates") {
    return `请围绕「${job.roleName}」生成人才地图、候选人来源、搜索关键词和触达策略。`;
  }
  return `请对「${job.roleName}」岗位的候选人进行评估，重点关注团队约束、证据链和面试追问。`;
}

export function runProjectScenario(projectId: string, job: JobProfile, action: RunProjectScenarioAction) {
  const scenario = scenarioForAction(action);

  return apiClient.post<RunScenarioResponse>("/scenarios/run", {
    scenario,
    input: inputForAction(action, job),
    team_constraint: "真机泛化",
    aperture_weight: 0.7,
    frontend_state: {
      source: "ProjectDetailPage",
      project_id: projectId,
      job_profile_id: job.jobProfileId,
      action,
    },
  });
}

export function runCandidateEvaluation(projectId: string, candidate: Candidate) {
  return apiClient.post<RunScenarioResponse>("/scenarios/run", {
    scenario: "C",
    input: `请评估候选人「${candidate.name}」与「${candidate.title}」岗位的匹配度，并在需要时触发人工确认。`,
    team_constraint: "真机泛化",
    aperture_weight: 0.7,
    frontend_state: {
      source: "CandidateTable",
      project_id: projectId,
      candidate_id: candidate.candidateId,
      candidateId: candidate.candidateId,
      job_id: candidate.targetJobProfileId,
      jobId: candidate.targetJobProfileId,
      action: "candidate_evaluation",
    },
  });
}

export function runWeeklyReport(projectId: string, projectName: string) {
  return apiClient.post<RunScenarioResponse>("/scenarios/run", {
    scenario: "D",
    input: `请基于「${projectName}」当前真实项目、岗位和候选人数据生成本周招聘周报。`,
    team_constraint: "真机泛化",
    aperture_weight: 0.7,
    frontend_state: {
      source: "ProjectDetailPage",
      project_id: projectId,
      action: "weekly_report",
    },
  });
}

function mapProject(project: ProjectBackendResponse): ProjectRecord {
  return {
    projectId: project.id,
    name: project.name,
    status: project.status,
    owner: undefined,
    updatedAt: project.createdAt,
    openJobs: project.openJobs,
    totalCandidates: project.totalCandidates,
    awaitingHuman: project.awaitingHuman,
    averageMatchScore: project.averageMatchScore,
    weeklyReport: {
      conclusion: undefined,
      keyProgress: [],
      topCandidates: [],
      risks: [],
      nextActions: [],
    },
  };
}

function mapJob(job: JobBackendResponse): JobProfile {
  const status = normalizeStepStatus(job.pipelineStatus || job.status);
  return {
    jobProfileId: job.id,
    roleName: job.title,
    headcount: job.headcount,
    priorityLevel: priorityFromHeadcount(job.headcount),
    pipelineStatus: status,
    candidateCount: job.candidateCount,
    averageMatchScore: job.averageMatchScore,
    isAiNativeFriendly: true,
    essentialCapabilities: [],
    preferredCapabilities: [],
    exclusionTags: [],
    targetCompanyTypes: ["真实后端岗位"],
    targetSchoolsLabs: [],
    salaryRangeMin: 0,
    salaryRangeMax: 0,
    funnel: buildFunnel(status, job.candidateCount, job.headcount),
  };
}

function mapCandidate(candidate: CandidateBackendResponse): Candidate {
  const stepStatus = normalizeStepStatus(candidate.pipelineStatus);
  return {
    candidateId: candidate.id,
    name: candidate.name,
    targetJobProfileId: candidate.jobId,
    sourcePlatform: "Backend",
    currentCompany: candidate.currentCompany ?? undefined,
    city: candidate.city ?? undefined,
    email: candidate.email ?? undefined,
    title: candidate.jobTitle,
    isAiNativeTalent: false,
    technicalLayerTags: [],
    parsedCapabilities: [],
    matchScore: candidate.matchScore,
    pipelineStatus: candidate.pipelineStatus,
    stage: candidateStage(candidate.pipelineStatus),
    stepStatus,
    outreachStatus: "not_sent",
    riskAlerts: [],
    evidence: [
      {
        label: "后端关联",
        source: "manual",
        summary: `${candidate.jobTitle} · 匹配分 ${candidate.matchScore}`,
      },
    ],
  };
}

function normalizeStepStatus(status: string): StepStatus {
  if (["pending", "processing", "awaiting_human", "done", "error", "cancelled"].includes(status)) {
    return status as StepStatus;
  }
  if (["offer", "offer_review", "technical_interview", "screening", "sourced", "pending_outreach"].includes(status)) {
    return "processing";
  }
  return "pending";
}

function candidateStage(status: string): Candidate["stage"] {
  if (status === "awaiting_human") return "human_gate";
  if (status === "done" || status === "pending_outreach") return "agent_evaluated";
  if (status === "screening" || status === "sourced") return status;
  if (status === "offer" || status === "offer_review") return "offer_review";
  return "technical_interview";
}

function priorityFromHeadcount(headcount: number): JobProfile["priorityLevel"] {
  if (headcount >= 2) return "P0";
  if (headcount === 1) return "P1";
  return "P2";
}

function buildFunnel(status: StepStatus, candidateCount: number, headcount: number) {
  const target = Math.max(candidateCount, headcount * 5, 1);
  const stages: Array<{ key: FunnelStageKey; label: string; divisor: number }> = [
    { key: "sourcing", label: "人才地图", divisor: 1 },
    { key: "screening", label: "初筛", divisor: 2 },
    { key: "evaluation", label: "Agent 评估", divisor: 3 },
    { key: "human_gate", label: "人工复核", divisor: 6 },
    { key: "interview", label: "技术面", divisor: 8 },
    { key: "offer", label: "Offer", divisor: 12 },
  ];

  return stages.map((stage) => ({
    key: stage.key,
    label: stage.label,
    count: Math.max(0, Math.round(candidateCount / stage.divisor)),
    target: Math.max(1, Math.round(target / stage.divisor)),
    status: stage.key === "human_gate" && status === "awaiting_human" ? "awaiting_human" : status,
  }));
}
