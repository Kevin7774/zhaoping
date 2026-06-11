import type { Candidate } from "../candidates/types";
import type { FunnelStageKey, JobProfile, JobRationale, StepStatus } from "../jobs/types";
import type { FilterCriteria } from "./state";
import { ApiError, apiClient } from "../../shared/api/client";
import type { TaskSnapshot } from "../../shared/hooks/useTaskStream";
import {
  searchConfigToBackendState,
  type ActionExplanation,
  type ProviderPreflightItem,
  type SearchConfig,
} from "./explainableAction";

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
  bpFilePath?: string;
  openJobs: number;
  totalCandidates: number;
  awaitingHuman: number;
  averageMatchScore: number;
  weeklyReport: WeeklyReport;
};

export type RunProjectScenarioAction = "job_analysis" | "find_candidates" | "candidate_evaluation";

export type ProjectScenarioRunOptions = {
  searchConfig?: SearchConfig;
  providerPreflight?: ProviderPreflightItem[];
  actionExplanation?: ActionExplanation;
};

export type RunScenarioResponse = {
  task_id: string;
  scenario: string;
  status: string;
};

export type ResumeImportResponse = {
  taskId: string;
  scenario: string;
  status: string;
};

export type ProjectMaterialUploadResponse = {
  fileName: string;
  bpFilePath: string;
  sourceFilePath: string;
  sizeBytes: number;
  parser?: string | null;
  confidence?: number | null;
  degradedReason?: string | null;
};

export type IntegrationCapabilityStatus = {
  id: string;
  service_type: string;
  label?: string;
  name_zh?: string;
  status: "active" | "available" | "missing_key" | "disabled" | "not_configured" | "manual_setup" | "missing_tool" | string;
  connected?: boolean;
  connected_name_zh?: string;
  code_path?: string | null;
  services?: Array<{
    name?: string;
    name_zh?: string;
    status?: string;
    connected?: boolean;
    provider?: string;
    code_path?: string | null;
    is_default?: boolean;
  }>;
};

export type IntegrationsStatusResponse = {
  capabilities?: IntegrationCapabilityStatus[];
  services?: Array<Record<string, unknown>>;
};

export type ScenarioMetaResponse = {
  scenarios?: Array<{ id: string; name_zh?: string; title?: string }>;
  agents?: Record<string, unknown>;
};

export type ListQueryOptions = {
  skip?: number;
  limit?: number;
};

export type CandidatePage = {
  candidates: Candidate[];
  total: number | null;
  hasMore: boolean;
};

export type OutreachDraft = {
  draftId: string;
  projectId: string;
  jobId: string;
  candidateId: string;
  segmentId?: string | null;
  subject: string;
  body: string;
  status: string;
  strategyTag?: string | null;
  createdByUserId?: string | null;
  backendGenerated: boolean;
  createdAt?: string;
  updatedAt?: string;
};

export type OutreachHistoryItem = {
  historyId: string;
  projectId: string;
  jobId?: string | null;
  candidateId?: string | null;
  draftId?: string | null;
  segmentId?: string | null;
  email?: string | null;
  senderEmail?: string | null;
  sentByUserId?: string | null;
  strategyTag?: string | null;
  subject: string;
  body: string;
  status: string;
  deliveryMode: string;
  providerStatus?: string | null;
  createdAt?: string;
};

export type OutreachHistoryResponse = {
  items: OutreachHistoryItem[];
};

export type SegmentQueryResponse = {
  projectId: string;
  criteria: Record<string, unknown>;
  total: number;
  candidates: Candidate[];
};

export type SegmentRecord = {
  segmentId: string;
  projectId: string;
  name: string;
  criteria: Record<string, unknown>;
  candidateIds: string[];
  candidateCount: number;
  createdAt?: string;
  candidates?: Candidate[];
};

export type WeeklyReportRecord = {
  reportId: string;
  projectId: string;
  sourceTaskId?: string | null;
  content: WeeklyReport;
  createdAt?: string;
};

export type JobMatchResponse = {
  results?: unknown[];
  [key: string]: unknown;
};

export type ProjectGenerationMode = "bp_file" | "prompt" | "bp_plus_prompt";

export type ProjectResearchTraceItem = {
  stage: string;
  summary: string;
  evidence: string[];
  assumptions: string[];
  risk?: string | null;
};

export type ProjectRoleRejection = {
  title: string;
  reasons: string[];
};

export type ProjectBpInitializeResponse = {
  projectId: string;
  projectName: string;
  promptName: string;
  generationMode: ProjectGenerationMode;
  jobCount: number;
  jobs: JobProfile[];
  industryReading?: string | null;
  technicalAssumptions: string[];
  coverageGaps: string[];
  researchTrace: ProjectResearchTraceItem[];
  claims?: Record<string, unknown> | null;
  capabilityGraph?: Record<string, unknown> | null;
  gapAnalysis?: Record<string, unknown> | null;
  rejectedRoles?: ProjectRoleRejection[];
  generationDegraded?: boolean;
};

export type ProjectCreateRequest = {
  id: string;
  name: string;
  status?: string;
};

export type ProjectUpdateRequest = {
  name: string;
  status?: string;
};

export type ProjectBpRequest = {
  projectName: string;
  generationMode?: ProjectGenerationMode;
  bpFilePath?: string;
  projectPrompt?: string;
  industryResearchPrompt?: string;
  llmService?: string | null;
  minimumRoleCount?: number;
};

export type CandidateSearchSchedule = {
  id: number;
  projectId: string;
  jobId: string;
  jobTitle: string;
  enabled: boolean;
  intervalMinutes: number;
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  lastTaskId?: string | null;
  lastStatus?: string | null;
  lastError?: string | null;
};

export type CandidateSearchScheduleListResponse = {
  items: CandidateSearchSchedule[];
};

type ProjectBackendResponse = {
  id?: string;
  name?: string;
  status?: string;
  createdAt?: string;
  bpFilePath?: string;
  bp_file_path?: string;
  openJobs?: number;
  totalCandidates?: number;
  awaitingHuman?: number;
  averageMatchScore?: number;
};

type JobBackendResponse = {
  id: string;
  projectId: string;
  title?: string;
  headcount?: number | null;
  seniority?: string | null;
  responsibilities?: string[] | null;
  mustHaveSkills?: string[] | null;
  niceToHaveSkills?: string[] | null;
  targetCompanies?: string[] | null;
  exclusionSignals?: string[] | null;
  interviewQuestions?: string[] | null;
  scoringRubric?: Record<string, unknown> | null;
  searchStrategy?: Record<string, unknown> | null;
  rationale?: JobRationale | null;
  status?: string | null;
  pipelineStatus?: string | null;
  candidateCount?: number | null;
  averageMatchScore?: number | null;
};

type CandidateBackendResponse = {
  id: string;
  jobCandidateId: number;
  jobId: string;
  jobTitle?: string | null;
  name?: string | null;
  sourcePlatform?: string | null;
  sourceUrl?: string | null;
  currentCompany?: string | null;
  location?: string | null;
  city?: string | null;
  email?: string | null;
  githubUrl?: string | null;
  linkedinUrl?: string | null;
  homepageUrl?: string | null;
  skills?: string[] | null;
  matchScore?: number | null;
  pipelineStatus?: string | null;
  outreachStatus?: "not_sent" | "drafted" | "sent" | null;
  evidence?: Array<
    | string
    | {
        label?: string;
        source?: string;
        summary?: string;
      }
  > | null;
  jobEvidence?: Array<
    | string
    | {
        label?: string;
        source?: string;
        summary?: string;
      }
  > | null;
  sourceTaskId?: string | null;
};

export function getProject(projectId: string): Promise<ProjectRecord> {
  return apiClient.get<ProjectBackendResponse>(`/projects/${encodeURIComponent(projectId)}`).then(mapProject);
}

export function listProjects(): Promise<ProjectRecord[]> {
  return apiClient.get<ProjectBackendResponse[]>("/projects").then((projects) => projects.map(mapProject));
}

export function createProject(request: ProjectCreateRequest): Promise<ProjectRecord> {
  return apiClient.post<ProjectBackendResponse>("/projects", request).then(mapProject);
}

export function updateProject(projectId: string, request: ProjectUpdateRequest): Promise<ProjectRecord> {
  return apiClient
    .patch<ProjectBackendResponse>(`/projects/${encodeURIComponent(projectId)}`, request)
    .then(mapProject);
}

export function deleteProject(projectId: string): Promise<void> {
  return apiClient.delete<void>(`/projects/${encodeURIComponent(projectId)}`);
}

export function getProjectJobs(projectId: string, options: ListQueryOptions = {}): Promise<JobProfile[]> {
  return apiClient
    .get<JobBackendResponse[]>(`/projects/${encodeURIComponent(projectId)}/jobs`, { query: options })
    .then((jobs) => jobs.map(mapJob));
}

function mapBpInitializeResponse(
  response: Omit<ProjectBpInitializeResponse, "jobs"> & { jobs: JobBackendResponse[] },
): ProjectBpInitializeResponse {
  return {
    ...response,
    generationMode: response.generationMode ?? "bp_file",
    technicalAssumptions: response.technicalAssumptions ?? [],
    coverageGaps: response.coverageGaps ?? [],
    researchTrace: response.researchTrace ?? [],
    rejectedRoles: response.rejectedRoles ?? [],
    generationDegraded: response.generationDegraded ?? false,
    jobs: response.jobs.map(mapJob),
  };
}

export async function previewProjectFromBp(
  projectId: string,
  request: ProjectBpRequest,
): Promise<ProjectBpInitializeResponse> {
  const response = await apiClient.post<
    Omit<ProjectBpInitializeResponse, "jobs"> & { jobs: JobBackendResponse[] }
  >(`/projects/${encodeURIComponent(projectId)}/preview-from-bp`, request);
  return mapBpInitializeResponse(response);
}

export async function initializeProjectFromBp(
  projectId: string,
  request: ProjectBpRequest,
): Promise<ProjectBpInitializeResponse> {
  const response = await apiClient.post<
    Omit<ProjectBpInitializeResponse, "jobs"> & { jobs: JobBackendResponse[] }
  >(`/projects/${encodeURIComponent(projectId)}/initialize-from-bp`, request);
  return mapBpInitializeResponse(response);
}

export function getProjectCandidates(projectId: string, options: ListQueryOptions = {}): Promise<Candidate[]> {
  return getProjectCandidatesPage(projectId, options).then((page) => page.candidates);
}

export function uploadProjectResume(projectId: string, jobId: string, file: File): Promise<ResumeImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<ResumeImportResponse>(
    `/projects/${encodeURIComponent(projectId)}/jobs/${encodeURIComponent(jobId)}/upload-resumes`,
    formData,
  );
}

export function uploadProjectMaterial(projectId: string, file: File): Promise<ProjectMaterialUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<ProjectMaterialUploadResponse>(
    `/projects/${encodeURIComponent(projectId)}/materials/upload`,
    formData,
  );
}

export async function getProjectCandidatesPage(
  projectId: string,
  options: ListQueryOptions = {},
): Promise<CandidatePage> {
  const response = await apiClient.getWithMeta<CandidateBackendResponse[]>(
    `/projects/${encodeURIComponent(projectId)}/candidates`,
    { query: options },
  );
  const candidates = response.data.map(mapCandidate);
  const headerHasMore = readBooleanHeader(response.headers, "X-Has-More");
  return {
    candidates,
    total: readNumberHeader(response.headers, "X-Total-Count"),
    hasMore: headerHasMore ?? (typeof options.limit === "number" && candidates.length === options.limit),
  };
}

export function getScenariosMeta() {
  return apiClient.get<ScenarioMetaResponse>("/scenarios/meta");
}

export function getTask(taskId: string) {
  return apiClient.get<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function confirmTask(
  taskId: string,
  decision: "approve" | "edit" | "reject" = "approve",
  data: Record<string, unknown> = {},
  edits?: string,
) {
  const normalizedEdits =
    edits ??
    readStringValue(data.draft) ??
    readStringValue(data.body) ??
    readStringValue(data.edits);

  return apiClient.post<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}/confirm`, {
    decision,
    edits: normalizedEdits,
    data,
  });
}

export function cancelTask(taskId: string) {
  return apiClient.post<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}/cancel`);
}

export function retryTask(taskId: string) {
  return apiClient.post<RunScenarioResponse>(`/tasks/${encodeURIComponent(taskId)}/retry`);
}

export function getIntegrationsStatus() {
  return apiClient.get<IntegrationsStatusResponse>("/integrations/status");
}

export interface SearchProviderProbe {
  service: string;
  name_zh?: string;
  probe_status: "verified" | "probe_failed" | "probe_timeout" | string;
  latency_ms?: number;
  result_count?: number;
  reason?: string;
}

export interface SearchProbeResponse {
  probe_query?: string;
  timeout_seconds?: number;
  probed: number;
  verified: number;
  failed: number;
  probes: SearchProviderProbe[];
}

export function probeSearchProviders(services?: string[], timeoutSeconds = 12) {
  return apiClient.post<SearchProbeResponse>("/integrations/search/probe", {
    services: services && services.length ? services : null,
    timeout_seconds: timeoutSeconds,
  });
}

export function createOutreachDraft(request: {
  projectId: string;
  jobId: string;
  candidateId: string;
  segmentId?: string | null;
  strategyTag?: string | null;
}) {
  return apiClient.post<OutreachDraft>("/outreach/draft", request);
}

export function updateOutreachDraft(draftId: string, request: { subject?: string; body?: string }) {
  return apiClient.patch<OutreachDraft>(`/outreach/drafts/${encodeURIComponent(draftId)}`, request);
}

export function sendOutreachDraft(request: {
  draftId: string;
  decision: "approve" | "edit" | "reject";
  simulate: boolean;
}) {
  return apiClient.post<OutreachHistoryItem>("/outreach/send", request);
}

export function getOutreachHistory(query: { projectId: string; candidateId?: string; segmentId?: string }) {
  return apiClient.get<OutreachHistoryResponse>("/outreach/history", { query });
}

export function confirmCandidateCompliance(projectId: string, jobCandidateId: number) {
  return apiClient
    .post<CandidateBackendResponse>(
      `/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(String(jobCandidateId))}/compliance-review`,
      { decision: "approve" },
    )
    .then(mapCandidate);
}

export async function querySegmentCandidates(projectId: string, criteria: FilterCriteria): Promise<SegmentQueryResponse> {
  const response = await apiClient.post<Omit<SegmentQueryResponse, "candidates"> & { candidates: CandidateBackendResponse[] }>(
    "/segments/query",
    {
      projectId,
      criteria,
    },
  );
  return {
    ...response,
    candidates: response.candidates.map(mapCandidate),
  };
}

export async function createSegment(request: {
  projectId: string;
  name: string;
  criteria: FilterCriteria;
  candidateIds?: string[];
}): Promise<SegmentRecord> {
  const response = await apiClient.post<Omit<SegmentRecord, "candidates"> & { candidates?: CandidateBackendResponse[] }>(
    "/segments",
    request,
  );
  return {
    ...response,
    candidates: response.candidates?.map(mapCandidate),
  };
}

export async function saveWeeklyReport(
  projectId: string,
  sourceTaskId: string | null,
  report: WeeklyReport,
): Promise<WeeklyReportRecord> {
  const response = await apiClient.post<WeeklyReportRecord>("/reports/weekly", {
    projectId,
    sourceTaskId,
    report,
  });
  return mapWeeklyReportRecord(response);
}

export async function getLatestWeeklyReport(projectId: string): Promise<WeeklyReportRecord | null> {
  try {
    const response = await apiClient.get<WeeklyReportRecord | undefined>(`/projects/${encodeURIComponent(projectId)}/reports/latest`);
    if (!response) return null;
    return mapWeeklyReportRecord(response);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function runJobMatch(query: string, topK = 5) {
  return apiClient.post<JobMatchResponse>("/jobs/match", {
    query,
    top_k: topK,
  });
}

export function getCandidateSearchSchedules(projectId: string) {
  return apiClient.get<CandidateSearchScheduleListResponse>(
    `/projects/${encodeURIComponent(projectId)}/candidate-search-schedules`,
  );
}

export function updateCandidateSearchSchedule(
  projectId: string,
  jobId: string,
  request: { enabled: boolean; intervalMinutes: number },
) {
  return apiClient.put<CandidateSearchSchedule>(
    `/projects/${encodeURIComponent(projectId)}/jobs/${encodeURIComponent(jobId)}/candidate-search-schedule`,
    request,
  );
}

function scenarioForAction(action: RunProjectScenarioAction) {
  if (action === "job_analysis") return "A";
  if (action === "find_candidates") return "B";
  return "C";
}

function inputForAction(action: RunProjectScenarioAction, job: JobProfile) {
  if (action === "job_analysis") {
    return `请对「${job.roleName}」岗位进行岗位画像、能力约束、搜索策略和风险点分析。`;
  }
  if (action === "find_candidates") {
    return `请围绕「${job.roleName}」生成人才地图、候选人来源、搜索关键词和触达策略。`;
  }
  return `请对「${job.roleName}」岗位的候选人进行评估，重点关注团队约束、证据链和面试追问。`;
}

export function runProjectScenario(
  projectId: string,
  job: JobProfile,
  action: RunProjectScenarioAction,
  options: ProjectScenarioRunOptions = {},
) {
  const scenario = scenarioForAction(action);

  return apiClient.post<RunScenarioResponse>("/scenarios/run", {
    scenario,
    input: inputForAction(action, job),
    aperture_weight: 0.7,
    frontend_state: {
      source: "ProjectDetailPage",
      project_id: projectId,
      job_profile_id: job.jobProfileId,
      job_title: job.roleName,
      jobTitle: job.roleName,
      action,
      ...(options.searchConfig
        ? { ...searchConfigToBackendState(options.searchConfig), archive_search_evidence: true }
        : {}),
      ...(options.providerPreflight ? { provider_preflight: options.providerPreflight } : {}),
      ...(options.actionExplanation ? { action_explainability: options.actionExplanation } : {}),
    },
  });
}

export function runCandidateEvaluation(projectId: string, candidate: Candidate) {
  return apiClient.post<RunScenarioResponse>("/scenarios/run", {
    scenario: "C",
    input: `请评估候选人「${candidate.name}」与「${candidate.title}」岗位的匹配度，并在需要时触发人工确认。`,
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
    projectId: project.id || "—",
    name: project.name || "—",
    status: project.status || "—",
    owner: undefined,
    updatedAt: project.createdAt || "",
    bpFilePath: project.bpFilePath ?? project.bp_file_path,
    openJobs: project.openJobs ?? 0,
    totalCandidates: project.totalCandidates ?? 0,
    awaitingHuman: project.awaitingHuman ?? 0,
    averageMatchScore: project.averageMatchScore ?? 0,
    weeklyReport: {
      conclusion: undefined,
      keyProgress: [],
      topCandidates: [],
      risks: [],
      nextActions: [],
    },
  };
}

function mapWeeklyReportRecord(record: WeeklyReportRecord): WeeklyReportRecord {
  return {
    ...record,
    content: {
      conclusion: record.content?.conclusion,
      keyProgress: record.content?.keyProgress ?? [],
      topCandidates: record.content?.topCandidates ?? [],
      risks: record.content?.risks ?? [],
      nextActions: record.content?.nextActions ?? [],
    },
  };
}

function readNumberHeader(headers: Headers, name: string): number | null {
  const raw = headers.get(name);
  if (!raw) return null;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) ? value : null;
}

function readBooleanHeader(headers: Headers, name: string): boolean | null {
  const raw = headers.get(name);
  if (!raw) return null;
  if (raw.toLowerCase() === "true") return true;
  if (raw.toLowerCase() === "false") return false;
  return null;
}

function mapJob(job: JobBackendResponse): JobProfile {
  const status = normalizeStepStatus(job.pipelineStatus || job.status || "pending");
  const headcount = job.headcount ?? undefined;
  const candidateCount = job.candidateCount ?? 0;
  return {
    jobProfileId: job.id,
    roleName: job.title || "—",
    rationale: job.rationale ?? null,
    headcount,
    seniority: job.seniority ?? undefined,
    responsibilities: Array.isArray(job.responsibilities) ? job.responsibilities : [],
    mustHaveSkills: Array.isArray(job.mustHaveSkills) ? job.mustHaveSkills : [],
    niceToHaveSkills: Array.isArray(job.niceToHaveSkills) ? job.niceToHaveSkills : [],
    targetCompanies: Array.isArray(job.targetCompanies) ? job.targetCompanies : [],
    exclusionSignals: Array.isArray(job.exclusionSignals) ? job.exclusionSignals : [],
    interviewQuestions: Array.isArray(job.interviewQuestions) ? job.interviewQuestions : [],
    scoringRubric: job.scoringRubric ?? {},
    searchStrategy: job.searchStrategy ?? {},
    priorityLevel: priorityFromRationale(job.rationale) ?? priorityFromHeadcount(headcount ?? 0),
    pipelineStatus: status,
    candidateCount,
    averageMatchScore: job.averageMatchScore ?? undefined,
    isAiNativeFriendly: true,
    essentialCapabilities: [],
    preferredCapabilities: [],
    exclusionTags: [],
    // Frontend projection label only; detailed target company types are not exposed by the current backend endpoint.
    targetCompanyTypes: [],
    targetSchoolsLabs: [],
    salaryRangeMin: 0,
    salaryRangeMax: 0,
    funnel: buildFunnel(status, candidateCount, headcount ?? 0),
  };
}

function mapCandidate(candidate: CandidateBackendResponse): Candidate {
  const pipelineStatus = candidate.pipelineStatus || "pending";
  const stepStatus = normalizeStepStatus(pipelineStatus);
  const matchScore = typeof candidate.matchScore === "number" && Number.isFinite(candidate.matchScore) ? candidate.matchScore : null;
  return {
    candidateId: candidate.id,
    jobCandidateId: candidate.jobCandidateId,
    name: candidate.name || "—",
    targetJobProfileId: candidate.jobId,
    // Frontend projection: current project candidate API does not expose a normalized source platform.
    sourcePlatform: candidate.sourcePlatform || "Backend",
    sourceUrl: candidate.sourceUrl ?? undefined,
    currentCompany: candidate.currentCompany ?? undefined,
    location: candidate.location ?? undefined,
    city: candidate.city ?? undefined,
    email: candidate.email ?? undefined,
    githubUrl: candidate.githubUrl ?? undefined,
    linkedinUrl: candidate.linkedinUrl ?? undefined,
    homepageUrl: candidate.homepageUrl ?? undefined,
    skills: Array.isArray(candidate.skills) ? candidate.skills : [],
    sourceTaskId: candidate.sourceTaskId ?? undefined,
    title: candidate.jobTitle || "—",
    isAiNativeTalent: false,
    technicalLayerTags: [],
    parsedCapabilities: [],
    matchScore,
    pipelineStatus,
    stage: candidateStage(pipelineStatus),
    stepStatus,
    // Frontend UI projection only. This is not a real email-delivery status unless backend returns it.
    outreachStatus: candidate.outreachStatus ?? "not_sent",
    riskAlerts: [],
    evidence: mergeCandidateEvidence(candidate),
  };
}

function mergeCandidateEvidence(candidate: CandidateBackendResponse): Candidate["evidence"] {
  const items = (Array.isArray(candidate.evidence) ? candidate.evidence : [])
    .map((item) => ({
      label: typeof item === "string" ? "搜索证据" : item.label || "后端证据",
      source:
        typeof item === "string"
          ? normalizeEvidenceSource(candidate.sourcePlatform ?? undefined)
          : normalizeEvidenceSource(item.source),
      summary: typeof item === "string" ? item : item.summary || "",
    }))
    .filter((item) => item.summary);
  const seen = new Set(items.map((item) => item.summary));
  for (const raw of Array.isArray(candidate.jobEvidence) ? candidate.jobEvidence : []) {
    const summary = typeof raw === "string" ? raw : raw.summary || "";
    if (!summary || seen.has(summary)) {
      continue;
    }
    seen.add(summary);
    items.push({
      label: summary.startsWith("初筛依据｜") ? "岗位初筛" : "岗位证据",
      source: "manual" as const,
      summary,
    });
  }
  return items;
}

function readStringValue(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function normalizeEvidenceSource(source: string | undefined): Candidate["evidence"][number]["source"] {
  if (["resume", "github", "paper", "demo", "interview", "manual"].includes(source ?? "")) {
    return source as Candidate["evidence"][number]["source"];
  }
  return "manual";
}

function normalizeStepStatus(status: string): StepStatus {
  if (["pending", "processing", "awaiting_human", "done", "error", "cancelled"].includes(status)) {
    return status as StepStatus;
  }
  if (status === "pending_compliance_review") {
    return "awaiting_human";
  }
  if (["offer", "offer_review", "technical_interview", "screening", "sourced", "pending_outreach"].includes(status)) {
    return "processing";
  }
  return "pending";
}

function candidateStage(status: string): Candidate["stage"] {
  if (status === "awaiting_human" || status === "pending_compliance_review") return "human_gate";
  if (status === "done" || status === "pending_outreach") return "agent_evaluated";
  if (status === "screening" || status === "sourced") return status;
  if (status === "offer" || status === "offer_review") return "offer_review";
  return "technical_interview";
}

function priorityFromRationale(rationale: JobRationale | null | undefined): JobProfile["priorityLevel"] | null {
  const priority = rationale?.hiringPriority?.toUpperCase();
  return priority === "P0" || priority === "P1" || priority === "P2" ? priority : null;
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
