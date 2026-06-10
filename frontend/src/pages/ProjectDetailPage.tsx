import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CandidateTable } from "../features/candidates/components/CandidateTable";
import type { Candidate } from "../features/candidates/types";
import type { JobProfile, StepStatus } from "../features/jobs/types";
import {
  initializeProjectFromBp,
  createOutreachDraft,
  confirmCandidateCompliance,
  createSegment,
  confirmTask,
  cancelTask,
  getCandidateSearchSchedules,
  getIntegrationsStatus,
  getLatestWeeklyReport,
  getOutreachHistory,
  getProject,
  getProjectCandidatesPage,
  getProjectJobs,
  getTask,
  previewProjectFromBp,
  querySegmentCandidates,
  retryTask,
  runJobMatch,
  runCandidateEvaluation,
  runProjectScenario,
  runWeeklyReport,
  saveWeeklyReport,
  sendOutreachDraft,
  updateCandidateSearchSchedule,
  type CandidateSearchSchedule,
  type IntegrationsStatusResponse,
  type JobMatchResponse,
  type OutreachDraft,
  type OutreachHistoryItem,
  type ProjectBpInitializeResponse,
  type ProjectGenerationMode,
  type ProjectRecord,
  type ProjectScenarioRunOptions,
  type RunProjectScenarioAction,
  type SegmentRecord,
  type WeeklyReport,
  updateOutreachDraft,
} from "../features/projects/api";
import { BackendLinkPanel } from "../features/projects/components/BackendLinkPanel";
import { HumanConfirmModal } from "../features/projects/components/HumanConfirmModal";
import { LiveTaskSummary } from "../features/projects/components/LiveTaskSummary";
import { MultiJobProgressTable } from "../features/projects/components/MultiJobProgressTable";
import { ProjectSummaryCards } from "../features/projects/components/ProjectSummaryCards";
import { WeeklyReportCard } from "../features/projects/components/WeeklyReportCard";
import {
  SEARCH_MODE_OPTIONS,
  buildActionExplanation,
  providerPreflightFromIntegrations,
  providerPreflightSummary,
  type SearchMode,
} from "../features/projects/explainableAction";
import { humanGateRequestFromEvent, type HumanGateRequest } from "../features/projects/humanGate";
import { defaultFilterCriteria, type FilterCriteria } from "../features/projects/state";
import { apiClient, type ApiRequestLogEntry } from "../shared/api/client";
import { useTaskStream } from "../shared/hooks/useTaskStream";
import { rememberActiveProjectId, rememberTaskId, useActiveProjectId } from "./projectWorkspace";

type LoadingState = "idle" | "loading" | "ready" | "error";

const CANDIDATE_PAGE_SIZE = 50;
const DEFAULT_BP_FILE_PATH = "data/input/projects/bp_ai_hardware.md";

const generationModeLabel: Record<ProjectGenerationMode, string> = {
  bp_file: "仅 BP",
  prompt: "仅提示词",
  bp_plus_prompt: "BP + 提示词",
};

const projectStatusLabel: Record<string, string> = {
  active: "进行中",
  done: "已完成",
  completed: "已完成",
  pending: "需处理",
  paused: "已暂停",
};

const taskStatusTone: Record<string, string> = {
  idle: "bg-[#F3F4F6] text-[#6B7280]",
  connecting: "bg-[#EFF6FF] text-[#2563EB]",
  open: "bg-[#EFF6FF] text-[#2563EB]",
  retrying: "bg-[#EFF6FF] text-[#2563EB]",
  polling: "bg-[#FFFBEB] text-[#F59E0B]",
  processing: "bg-[#EFF6FF] text-[#2563EB]",
  awaiting_human: "bg-[#FFFBEB] text-[#F59E0B]",
  done: "bg-[#ECFDF3] text-[#16A34A]",
  error: "bg-[#FEF2F2] text-[#EF4444]",
  cancelled: "bg-[#FEF2F2] text-[#EF4444]",
};

const taskStatusLabel: Record<string, string> = {
  idle: "无任务",
  connecting: "任务连接中",
  open: "任务执行中",
  retrying: "任务重连中",
  polling: "轮询任务中",
  processing: "任务执行中",
  awaiting_human: "等待确认",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
};

function candidateCounts(candidates: Candidate[]) {
  return candidates.reduce<Record<string, number>>((counts, candidate) => {
    counts[candidate.targetJobProfileId] = (counts[candidate.targetJobProfileId] ?? 0) + 1;
    return counts;
  }, {});
}

function summaryFrom(jobs: JobProfile[], candidates: Candidate[]) {
  return {
    openJobs: jobs.length,
    totalCandidates: candidates.length,
    pendingEmailCount: null,
    weeklyInterviewCount: null,
  };
}

function upsertSchedule(items: CandidateSearchSchedule[], updated: CandidateSearchSchedule) {
  const exists = items.some((item) => item.jobId === updated.jobId);
  if (!exists) return [...items, updated];
  return items.map((item) => (item.jobId === updated.jobId ? updated : item));
}

function workflowStatus(
  index: number,
  jobs: JobProfile[],
  candidates: Candidate[],
  taskStatus: string | null,
  activeAction: RunProjectScenarioAction | "weekly_report" | null,
) {
  const activeStep: Record<RunProjectScenarioAction | "weekly_report", number> = {
    job_analysis: 1,
    find_candidates: 2,
    candidate_evaluation: 3,
    weekly_report: 4,
  };
  const currentTaskStep = activeAction ? activeStep[activeAction] : null;
  if (currentTaskStep === index && taskStatus === "done") return "done";
  if (currentTaskStep === index && (taskStatus === "processing" || taskStatus === "awaiting_human")) return "current";
  if (index === 0) return "done";
  if (index === 1) return jobs.length ? "current" : "pending";
  if (index === 2) return candidates.length ? "current" : jobs.length ? "pending" : "pending";
  if (index === 3) return candidates.length ? "pending" : "pending";
  if (index === 4) return candidates.length ? "current" : "pending";
  return "pending";
}

function statusBadge(status: StepStatus | string) {
  if (status === "done") return "bg-[#ECFDF3] text-[#16A34A]";
  if (status === "awaiting_human") return "bg-[#FFFBEB] text-[#F59E0B]";
  if (status === "error" || status === "cancelled") return "bg-[#FEF2F2] text-[#EF4444]";
  if (status === "processing") return "bg-[#EFF6FF] text-[#2563EB]";
  return "bg-[#F3F4F6] text-[#6B7280]";
}

function uniqueValues(values: Array<string | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();
}

type CapabilityGate = {
  enabled: boolean;
  reason?: string;
  status?: string;
};

const CONNECTED_STATUSES = new Set(["active", "available"]);

function capabilityStatusLabel(status?: string) {
  if (status === "active" || status === "available") return "已接入";
  if (status === "missing_key") return "缺少 Key";
  if (status === "disabled" || status === "not_configured") return "未接入";
  if (status === "manual_setup") return "需人工配置";
  if (status === "missing_tool") return "缺少运行工具";
  return status || "状态未知";
}

function capabilityGate(
  integrations: IntegrationsStatusResponse | null,
  serviceType: string,
  label: string,
  integrationError: string | null,
): CapabilityGate {
  if (integrationError) return { enabled: false, reason: `${label} 状态读取失败：${integrationError}` };
  if (!integrations) return { enabled: false, reason: `${label} 能力状态加载中` };
  const capability = integrations.capabilities?.find((item) => item.service_type === serviceType || item.id === `${serviceType}_api`);
  if (!capability) return { enabled: false, reason: `${label} 未接入`, status: "not_configured" };
  const statusText = capabilityStatusLabel(capability.status);
  return {
    enabled: CONNECTED_STATUSES.has(capability.status),
    reason: `${label} ${statusText}`,
    status: capability.status,
  };
}

function candidateSearchScenarioOptions(
  searchMode: SearchMode,
  searchGate: CapabilityGate,
  job: JobProfile,
  integrations: IntegrationsStatusResponse | null,
): ProjectScenarioRunOptions {
  const providerPreflight = providerPreflightFromIntegrations(integrations, searchMode);
  return {
    searchMode,
    providerPreflight,
    actionExplanation: buildActionExplanation({
      actionId: "project.find_candidates",
      label: "找候选人",
      apiRoute: "POST /scenarios/run",
      inputSummary: job.roleName,
      expectedOutput: "候选人线索、人机确认、任务审计事件",
      capabilityGate: searchGate.reason || "Search API 状态未知",
      searchMode,
      providerPreflight,
    }),
  };
}

function emptyWeeklyReport(): WeeklyReport {
  return {
    conclusion: undefined,
    keyProgress: [],
    topCandidates: [],
    risks: [],
    nextActions: [],
  };
}

function weeklyReportFromTaskResult(result: unknown): WeeklyReport | null {
  if (!result || typeof result !== "object") return null;
  const record = result as Record<string, unknown>;
  const report = (record.report && typeof record.report === "object" ? record.report : record) as Record<string, unknown>;
  const humanReport =
    record.human_report && typeof record.human_report === "object"
      ? (record.human_report as Record<string, unknown>)
      : report.human_report && typeof report.human_report === "object"
        ? (report.human_report as Record<string, unknown>)
        : null;
  const weeklyReport: WeeklyReport = {
    conclusion:
      readString(report.conclusion) ??
      readString(report.summary) ??
      readString(report.executive_summary) ??
      readString(report["本周招聘结论"]) ??
      readString(report["结论"]) ??
      readHumanReportSummary(humanReport),
    keyProgress:
      readStringArray(report.keyProgress) ??
      readStringArray(report.key_progress) ??
      readStringArray(report.progress) ??
      readStringArray(report["关键岗位进展"]) ??
      readHumanReportSection(humanReport, "关键岗位进展") ??
      [],
    topCandidates:
      readStringArray(report.topCandidates) ??
      readStringArray(report.top_candidates) ??
      readStringArray(report["Top 候选人"]) ??
      readStringArray(report["重点候选人"]) ??
      readHumanReportSection(humanReport, "候选人") ??
      [],
    risks:
      readStringArray(report.risks) ??
      readStringArray(report["招聘风险"]) ??
      readStringArray(report["风险"]) ??
      readHumanReportSection(humanReport, "风险") ??
      [],
    nextActions:
      readStringArray(report.nextActions) ??
      readStringArray(report.next_actions) ??
      readStringArray(report["下周行动建议"]) ??
      readStringArray(report["下一步行动"]) ??
      readHumanReportSection(humanReport, "下周") ??
      [],
  };
  return weeklyReport.conclusion ||
    weeklyReport.keyProgress.length ||
    weeklyReport.topCandidates.length ||
    weeklyReport.risks.length ||
    weeklyReport.nextActions.length
    ? weeklyReport
    : null;
}

function readString(value: unknown) {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function readStringArray(value: unknown) {
  if (!Array.isArray(value)) return undefined;
  return value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()));
}

function readHumanReportSummary(report: Record<string, unknown> | null) {
  if (!report) return undefined;
  const summary = report.summary;
  if (typeof summary === "string" && summary.trim()) return summary;
  if (!Array.isArray(summary)) return undefined;
  return summary
    .map((item) => {
      if (typeof item === "string") return readString(item);
      if (item && typeof item === "object") return readString((item as Record<string, unknown>).text);
      return undefined;
    })
    .find(Boolean);
}

function readHumanReportSection(report: Record<string, unknown> | null, headingKeyword: string) {
  if (!report || !Array.isArray(report.sections)) return undefined;
  const section = report.sections.find((item) => {
    if (!item || typeof item !== "object") return false;
    const heading = readString((item as Record<string, unknown>).heading);
    return Boolean(heading?.includes(headingKeyword));
  });
  if (!section || typeof section !== "object") return undefined;
  return readStringArray((section as Record<string, unknown>).bullets);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

export function ProjectDetailPage() {
  const projectId = useActiveProjectId();
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [jobs, setJobs] = useState<JobProfile[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [visibleCandidates, setVisibleCandidates] = useState<Candidate[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationsStatusResponse | null>(null);
  const [integrationsError, setIntegrationsError] = useState<string | null>(null);
  const [candidateTotalCount, setCandidateTotalCount] = useState<number | null>(null);
  const [hasMoreCandidates, setHasMoreCandidates] = useState(false);
  const [loadingMoreCandidates, setLoadingMoreCandidates] = useState(false);
  const [filterCriteria, setFilterCriteria] = useState<FilterCriteria>(defaultFilterCriteria);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [outreachDraft, setOutreachDraft] = useState<OutreachDraft | null>(null);
  const [outreachHistory, setOutreachHistory] = useState<OutreachHistoryItem[]>([]);
  const [emailSubject, setEmailSubject] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [emailDraftLoading, setEmailDraftLoading] = useState(false);
  const [draftConfirmOpen, setDraftConfirmOpen] = useState(false);
  const [segmentBusy, setSegmentBusy] = useState(false);
  const [segmentPreviewCount, setSegmentPreviewCount] = useState<number | null>(null);
  const [savedSegment, setSavedSegment] = useState<SegmentRecord | null>(null);
  const [persistedWeeklyReport, setPersistedWeeklyReport] = useState<WeeklyReport | null>(null);
  const [weeklyReportError, setWeeklyReportError] = useState<string | null>(null);
  const [matchResult, setMatchResult] = useState<{ jobName: string; response: JobMatchResponse } | null>(null);
  const [matchingJobId, setMatchingJobId] = useState<string | null>(null);
  const [candidateSearchSchedules, setCandidateSearchSchedules] = useState<CandidateSearchSchedule[]>([]);
  const [scheduleBusyJobId, setScheduleBusyJobId] = useState<string | null>(null);
  const [bpGenerationMode, setBpGenerationMode] = useState<ProjectGenerationMode>("bp_plus_prompt");
  const [candidateSearchMode, setCandidateSearchMode] = useState<SearchMode>("live_recruiting");
  const [actionExplanationText, setActionExplanationText] = useState<string | null>(null);
  const [bpFilePath, setBpFilePath] = useState(DEFAULT_BP_FILE_PATH);
  const [bpProjectPrompt, setBpProjectPrompt] = useState("");
  const [bpIndustryResearchPrompt, setBpIndustryResearchPrompt] = useState("");
  const [bpMinimumRoleCount, setBpMinimumRoleCount] = useState(14);
  const [bpPreview, setBpPreview] = useState<ProjectBpInitializeResponse | null>(null);
  const [bpBusy, setBpBusy] = useState<"preview" | "confirm" | null>(null);
  const [bpError, setBpError] = useState<string | null>(null);
  const [taskPanelOpen, setTaskPanelOpen] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeTaskAction, setActiveTaskAction] = useState<RunProjectScenarioAction | "weekly_report" | null>(null);
  const [runningJobAction, setRunningJobAction] = useState<{
    jobProfileId: string;
    action: RunProjectScenarioAction;
  } | null>(null);
  const [runningCandidateId, setRunningCandidateId] = useState<string | null>(null);
  const [confirmingComplianceCandidateId, setConfirmingComplianceCandidateId] = useState<string | null>(null);
  const [taskControlBusy, setTaskControlBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastApiRequest, setLastApiRequest] = useState<ApiRequestLogEntry | null>(null);
  const [humanGateRequest, setHumanGateRequest] = useState<HumanGateRequest | null>(null);
  const [humanGateBusy, setHumanGateBusy] = useState(false);
  const completedTaskIdsRef = useRef<Set<string>>(new Set());
  const savedWeeklyReportTaskIdsRef = useRef<Set<string>>(new Set());
  const failedWeeklyReportTaskIdsRef = useRef<Set<string>>(new Set());
  const handledHumanGateKeysRef = useRef<Set<string>>(new Set());
  const emailDraftTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const {
    events,
    taskSnapshot,
    connectionState,
    error: streamError,
    retryCount,
    usedFallbackPolling,
  } = useTaskStream(activeTaskId);
  const taskStatus = taskSnapshot?.status ?? (activeTaskId ? connectionState : "idle");

  useEffect(() => {
    rememberActiveProjectId(projectId);
  }, [projectId]);

  useEffect(() => {
    if (activeTaskId) rememberTaskId(activeTaskId);
  }, [activeTaskId]);

  const loadProjectData = useCallback(
    async (criteria: FilterCriteria) => {
      setLoadingState((current) => (current === "idle" ? "loading" : current));
      setLoadError(null);

      try {
        const [projectData, jobsData, candidatesPage] = await Promise.all([
          getProject(projectId),
          getProjectJobs(projectId),
          getProjectCandidatesPage(projectId, { skip: 0, limit: CANDIDATE_PAGE_SIZE }),
        ]);
        const candidatesData = candidatesPage.candidates;

        setProject(projectData);
        setJobs(jobsData);
        setCandidates(candidatesData);
        setVisibleCandidates(candidatesData);
        setCandidateTotalCount(candidatesPage.total);
        setHasMoreCandidates(candidatesPage.hasMore);
        setLoadingMoreCandidates(false);
        setLoadingState("ready");
      } catch (error) {
        setLoadingState("error");
        setLoadError(error instanceof Error ? error.message : "项目数据加载失败");
      }
    },
    [projectId],
  );

  useEffect(() => {
    loadProjectData(defaultFilterCriteria);
  }, [loadProjectData]);

  const loadLatestReport = useCallback(async () => {
    try {
      const latest = await getLatestWeeklyReport(projectId);
      setPersistedWeeklyReport(latest?.content ?? null);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "最近周报加载失败");
    }
  }, [projectId]);

  useEffect(() => {
    loadLatestReport();
  }, [loadLatestReport]);

  const loadCandidateSearchSchedules = useCallback(async () => {
    try {
      const response = await getCandidateSearchSchedules(projectId);
      setCandidateSearchSchedules(Array.isArray(response.items) ? response.items : []);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "自动搜索配置加载失败");
    }
  }, [projectId]);

  useEffect(() => {
    loadCandidateSearchSchedules();
  }, [loadCandidateSearchSchedules]);

  useEffect(() => {
    let cancelled = false;
    setIntegrations(null);
    setIntegrationsError(null);
    getIntegrationsStatus()
      .then((status) => {
        if (!cancelled) setIntegrations(status);
      })
      .catch((error) => {
        if (!cancelled) setIntegrationsError(error instanceof Error ? error.message : "能力状态加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => apiClient.addRequestLogListener(setLastApiRequest), []);

  useEffect(() => {
    setLoadingState("idle");
    setCandidates([]);
    setJobs([]);
    setProject(null);
    setVisibleCandidates([]);
    setCandidateTotalCount(null);
    setHasMoreCandidates(false);
    setLoadingMoreCandidates(false);
    setHumanGateRequest(null);
    setRunningCandidateId(null);
    setConfirmingComplianceCandidateId(null);
    setActiveTaskId(null);
    setActiveTaskAction(null);
    setDraftConfirmOpen(false);
    setSelectedCandidate(null);
    setOutreachDraft(null);
    setOutreachHistory([]);
    setEmailSubject("");
    setEmailDraft("");
    setEmailDraftLoading(false);
    setSegmentPreviewCount(null);
    setSavedSegment(null);
    setPersistedWeeklyReport(null);
    setWeeklyReportError(null);
    setMatchResult(null);
    setMatchingJobId(null);
    setCandidateSearchSchedules([]);
    setScheduleBusyJobId(null);
    setBpGenerationMode("bp_plus_prompt");
    setCandidateSearchMode("live_recruiting");
    setActionExplanationText(null);
    setBpFilePath(DEFAULT_BP_FILE_PATH);
    setBpProjectPrompt("");
    setBpIndustryResearchPrompt("");
    setBpMinimumRoleCount(14);
    setBpPreview(null);
    setBpBusy(null);
    setBpError(null);
  }, [projectId]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!activeTaskId || !taskSnapshot) return;

    if (taskSnapshot.status === "done" && !completedTaskIdsRef.current.has(activeTaskId)) {
      completedTaskIdsRef.current.add(activeTaskId);
      setRunningJobAction(null);
      setRunningCandidateId(null);
      setToast(activeTaskAction === "weekly_report" ? "周报任务已完成，正在保存报告" : "任务已完成，正在刷新候选人列表");
      loadProjectData(filterCriteria);
    }

    if (
      taskSnapshot.status === "done" &&
      activeTaskAction === "weekly_report" &&
      !savedWeeklyReportTaskIdsRef.current.has(activeTaskId)
    ) {
      const report = weeklyReportFromTaskResult(taskSnapshot.result);
      if (!report) {
        if (!failedWeeklyReportTaskIdsRef.current.has(activeTaskId)) {
          failedWeeklyReportTaskIdsRef.current.add(activeTaskId);
          const message =
            "周报解析失败：后端任务已完成，但结果中没有 conclusion/keyProgress/topCandidates/risks/nextActions 或中文等价字段。";
          setWeeklyReportError(message);
        }
        return;
      }
      savedWeeklyReportTaskIdsRef.current.add(activeTaskId);
      saveWeeklyReport(projectId, activeTaskId, report)
        .then((record) => {
          setPersistedWeeklyReport(record.content);
          setWeeklyReportError(null);
          setToast("周报已保存，页面刷新后可读取最近周报");
        })
        .catch((error) => {
          savedWeeklyReportTaskIdsRef.current.delete(activeTaskId);
          setToast(error instanceof Error ? error.message : "周报保存失败");
        });
    }

    if (taskSnapshot.status === "error" || taskSnapshot.status === "cancelled") {
      setRunningJobAction(null);
      setRunningCandidateId(null);
    }
  }, [activeTaskAction, activeTaskId, filterCriteria, loadProjectData, projectId, taskSnapshot]);

  useEffect(() => {
    if (!activeTaskId) return;

    const latestHumanGate = [...events]
      .reverse()
      .map((event) => humanGateRequestFromEvent(event, activeTaskId))
      .find((request): request is HumanGateRequest => Boolean(request));
    const snapshotHumanGate =
      !latestHumanGate && taskSnapshot?.status === "awaiting_human"
        ? humanGateRequestFromEvent(
            {
              id: `snapshot-${taskSnapshot.task_id}`,
              task_id: taskSnapshot.task_id,
              type: "human_gate",
              message: "任务等待人工确认",
              data: { awaiting: taskSnapshot.awaiting },
              status: "awaiting_human",
            },
            activeTaskId,
          )
        : null;
    const humanGate = latestHumanGate ?? snapshotHumanGate;

    if (!humanGate || handledHumanGateKeysRef.current.has(humanGate.eventKey)) return;
    setHumanGateRequest(humanGate);
    setTaskPanelOpen(false);
    setToast("AI Agent 等待人工确认");
  }, [activeTaskId, events, taskSnapshot]);

  const projectSummary = useMemo(() => summaryFrom(jobs, candidates), [jobs, candidates]);
  const jobCandidateCounts = useMemo(() => candidateCounts(candidates), [candidates]);
  const cities = useMemo(() => uniqueValues(candidates.map((candidate) => candidate.city)), [candidates]);
  const sources = useMemo(() => uniqueValues(candidates.map((candidate) => candidate.sourcePlatform)), [candidates]);
  const llmGate = useMemo(() => capabilityGate(integrations, "llm", "LLM API", integrationsError), [integrations, integrationsError]);
  const searchGate = useMemo(
    () => capabilityGate(integrations, "search", "Search API", integrationsError),
    [integrations, integrationsError],
  );
  const emailDeliveryGate = useMemo(
    () => capabilityGate(integrations, "email_delivery", "邮件发送 API", integrationsError),
    [integrations, integrationsError],
  );
  const embeddingGate = useMemo(
    () => capabilityGate(integrations, "embedding", "Embedding API", integrationsError),
    [integrations, integrationsError],
  );
  const vectorGate = useMemo(
    () => capabilityGate(integrations, "vector_store", "Vector API", integrationsError),
    [integrations, integrationsError],
  );
  const databaseGate = useMemo(
    () => capabilityGate(integrations, "database", "数据库 API", integrationsError),
    [integrations, integrationsError],
  );
  const segmentCreateGate = useMemo(
    () => capabilityGate(integrations, "segments.create", "人群保存 API", integrationsError),
    [integrations, integrationsError],
  );
  const searchProviderPreflight = useMemo(
    () => providerPreflightFromIntegrations(integrations, candidateSearchMode),
    [candidateSearchMode, integrations],
  );
  const searchProviderSummary = useMemo(
    () => providerPreflightSummary(searchProviderPreflight),
    [searchProviderPreflight],
  );
  const actionAvailability = useMemo(
    () => ({
      job_analysis: llmGate.enabled
        ? { enabled: true }
        : { enabled: false, reason: `岗位分析不可用：${llmGate.reason}` },
      find_candidates: searchGate.enabled
        ? { enabled: true }
        : { enabled: false, reason: `搜索服务不可用：${searchGate.reason}` },
      candidate_evaluation: llmGate.enabled
        ? { enabled: true }
        : { enabled: false, reason: `候选人评估不可用：${llmGate.reason}` },
    }),
    [llmGate, searchGate],
  );
  const weeklyReportGate = llmGate.enabled
    ? { enabled: true }
    : { enabled: false, reason: `招聘周报不可用：${llmGate.reason}` };
  const matchGate =
    embeddingGate.enabled && vectorGate.enabled
      ? { enabled: true }
      : { enabled: false, reason: `岗位匹配不可用：${embeddingGate.reason || vectorGate.reason}` };
  const taskWeeklyReport = activeTaskAction === "weekly_report" ? weeklyReportFromTaskResult(taskSnapshot?.result) : null;
  const weeklyReport = taskWeeklyReport ?? persistedWeeklyReport ?? project?.weeklyReport ?? emptyWeeklyReport();

  const validateBpGenerationRequest = useCallback(() => {
    const hasBpFile = bpFilePath.trim().length > 0;
    const hasProjectPrompt = bpProjectPrompt.trim().length > 0;
    const hasIndustryPrompt = bpIndustryResearchPrompt.trim().length > 0;
    if (bpGenerationMode === "bp_file" && !hasBpFile) return "请填写 BP 文件路径。";
    if (bpGenerationMode === "prompt" && !hasProjectPrompt && !hasIndustryPrompt) {
      return "提示词模式需要填写项目提示词或行业研究偏好。";
    }
    if (bpGenerationMode === "bp_plus_prompt" && !hasBpFile && !hasProjectPrompt && !hasIndustryPrompt) {
      return "BP + 提示词模式需要至少提供 BP 文件路径、项目提示词或行业研究偏好。";
    }
    return null;
  }, [bpFilePath, bpGenerationMode, bpIndustryResearchPrompt, bpProjectPrompt]);

  const bpRequest = useCallback(
    () => {
      const request = {
        projectName: project?.name ?? projectId,
        generationMode: bpGenerationMode,
        minimumRoleCount: bpMinimumRoleCount,
        ...(bpGenerationMode !== "prompt" && bpFilePath.trim() ? { bpFilePath: bpFilePath.trim() } : {}),
        ...(bpProjectPrompt.trim() ? { projectPrompt: bpProjectPrompt.trim() } : {}),
        ...(bpIndustryResearchPrompt.trim() ? { industryResearchPrompt: bpIndustryResearchPrompt.trim() } : {}),
      };
      return request;
    },
    [bpFilePath, bpGenerationMode, bpIndustryResearchPrompt, bpMinimumRoleCount, bpProjectPrompt, project?.name, projectId],
  );

  const handlePreviewBpJobs = async () => {
    const validationError = validateBpGenerationRequest();
    if (validationError) {
      setBpError(validationError);
      return;
    }
    setBpBusy("preview");
    setBpError(null);
    try {
      const preview = await previewProjectFromBp(projectId, bpRequest());
      setBpPreview(preview);
      setToast(`已预览 ${preview.jobCount} 个岗位矩阵，确认后才会覆盖当前岗位。`);
    } catch (error) {
      setBpError(error instanceof Error ? error.message : "岗位矩阵预览失败");
    } finally {
      setBpBusy(null);
    }
  };

  const handleConfirmBpJobs = async () => {
    const validationError = validateBpGenerationRequest();
    if (validationError) {
      setBpError(validationError);
      return;
    }
    const roleCount = bpPreview?.jobCount ?? bpMinimumRoleCount;
    const confirmed = window.confirm(`将覆盖项目 ${projectId} 当前岗位，并清空这些岗位的候选人关联。确认写入 ${roleCount} 个岗位？`);
    if (!confirmed) return;
    setBpBusy("confirm");
    setBpError(null);
    try {
      const initialized = await initializeProjectFromBp(projectId, bpRequest());
      setBpPreview(initialized);
      await loadProjectData(filterCriteria);
      setToast(`已写入 ${initialized.jobCount} 个岗位。`);
    } catch (error) {
      setBpError(error instanceof Error ? error.message : "岗位矩阵写入失败");
    } finally {
      setBpBusy(null);
    }
  };

  const handleQuerySegment = async () => {
    setSegmentBusy(true);
    try {
      const result = await querySegmentCandidates(projectId, filterCriteria);
      setVisibleCandidates(result.candidates);
      setSegmentPreviewCount(result.total);
      setSavedSegment(null);
      setToast(`后端筛选命中 ${result.total} 人，可保存为目标人群。`);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "目标人群查询失败");
    } finally {
      setSegmentBusy(false);
    }
  };

  const handleSaveSegment = async () => {
    if (!segmentCreateGate.enabled) {
      setToast(`目标人群保存不可用：${segmentCreateGate.reason}`);
      return;
    }
    setSegmentBusy(true);
    try {
      const segment = await createSegment({
        projectId,
        name: "当前筛选目标人群",
        criteria: filterCriteria,
        candidateIds: visibleCandidates.map((candidate) => candidate.candidateId),
      });
      setSavedSegment(segment);
      setToast(`已保存目标人群 ${segment.segmentId}，可用于后续触达。`);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "目标人群保存失败");
    } finally {
      setSegmentBusy(false);
    }
  };

  const handleLoadMoreCandidates = async () => {
    if (loadingMoreCandidates || !hasMoreCandidates) return;
    setLoadingMoreCandidates(true);
    try {
      const nextPage = await getProjectCandidatesPage(projectId, {
        skip: candidates.length,
        limit: CANDIDATE_PAGE_SIZE,
      });
      const nextCandidates = nextPage.candidates;
      const mergedCandidates = [...candidates, ...nextCandidates];
      setCandidates(mergedCandidates);
      setVisibleCandidates(mergedCandidates);
      if (nextPage.total !== null) {
        setCandidateTotalCount(nextPage.total);
      }
      setHasMoreCandidates(nextPage.hasMore);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "候选人加载失败");
    } finally {
      setLoadingMoreCandidates(false);
    }
  };

  const handleRunAction = async (job: JobProfile, action: RunProjectScenarioAction) => {
    const availability = actionAvailability[action];
    if (!availability.enabled) {
      setToast(availability.reason || "能力不可用");
      return;
    }

    setRunningJobAction({ jobProfileId: job.jobProfileId, action });
    setRunningCandidateId(null);
    const actionLabel =
      action === "job_analysis" ? "岗位分析" : action === "find_candidates" ? "找候选人" : "候选人评估";
    const scenarioOptions: ProjectScenarioRunOptions =
      action === "find_candidates" ? candidateSearchScenarioOptions(candidateSearchMode, searchGate, job, integrations) : {};
    if (action === "find_candidates") {
      setActionExplanationText(
        `动作解释：${scenarioOptions.actionExplanation?.label ?? actionLabel} · ${scenarioOptions.actionExplanation?.apiRoute ?? "POST /scenarios/run"} · ${scenarioOptions.searchMode}`,
      );
    }
    setToast(`正在启动${actionLabel}任务`);

    try {
      const created = await runProjectScenario(projectId, job, action, scenarioOptions);
      setActiveTaskId(created.task_id);
      setActiveTaskAction(action);
      setTaskPanelOpen(true);
      getTask(created.task_id).catch(() => null);
    } catch (error) {
      setRunningJobAction(null);
      setToast(error instanceof Error ? error.message : "任务启动失败");
    }
  };

  const handleRunCandidateEvaluation = async (candidate: Candidate) => {
    if (!actionAvailability.candidate_evaluation.enabled) {
      setToast(actionAvailability.candidate_evaluation.reason || "候选人评估不可用");
      return;
    }

    setRunningCandidateId(candidate.candidateId);
    setRunningJobAction(null);
    setToast(`正在启动 ${candidate.name} 的 Agent 评估`);

    try {
      const created = await runCandidateEvaluation(projectId, candidate);
      setActiveTaskId(created.task_id);
      setActiveTaskAction("candidate_evaluation");
      setTaskPanelOpen(true);
      getTask(created.task_id).catch(() => null);
    } catch (error) {
      setRunningCandidateId(null);
      setToast(error instanceof Error ? error.message : "候选人评估任务启动失败");
    }
  };

  const handleRunWeeklyReport = async () => {
    if (!project) return;
    if (!weeklyReportGate.enabled) {
      setToast(weeklyReportGate.reason || "招聘周报不可用");
      return;
    }
    setWeeklyReportError(null);
    setToast("正在启动招聘周报任务");
    try {
      const created = await runWeeklyReport(projectId, project.name);
      setActiveTaskId(created.task_id);
      setActiveTaskAction("weekly_report");
      setTaskPanelOpen(true);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "周报任务启动失败");
    }
  };

  const handleRunFirstJob = async () => {
    const firstJob = jobs[0];
    if (!firstJob) return;
    await handleRunAction(firstJob, "find_candidates");
  };

  const handleRunMatch = async (job: JobProfile) => {
    if (!matchGate.enabled) {
      setToast(matchGate.reason || "岗位匹配不可用");
      return;
    }
    setMatchingJobId(job.jobProfileId);
    try {
      const response = await runJobMatch(job.roleName, 5);
      setMatchResult({ jobName: job.roleName, response });
      setToast("已返回后端岗位匹配结果");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "岗位匹配失败");
    } finally {
      setMatchingJobId(null);
    }
  };

  const handleUpdateCandidateSearchSchedule = async (job: JobProfile, enabled: boolean) => {
    if (!searchGate.enabled) {
      setToast(searchGate.reason || "搜索服务不可用");
      return;
    }
    const current = candidateSearchSchedules.find((item) => item.jobId === job.jobProfileId);
    setScheduleBusyJobId(job.jobProfileId);
    try {
      const updated = await updateCandidateSearchSchedule(projectId, job.jobProfileId, {
        enabled,
        intervalMinutes: current?.intervalMinutes ?? 360,
      });
      setCandidateSearchSchedules((items) => upsertSchedule(items, updated));
      setToast(enabled ? "自动搜候选人已开启" : "自动搜候选人已关闭");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "自动搜索配置保存失败");
    } finally {
      setScheduleBusyJobId(null);
    }
  };

  const handleCandidateSearchIntervalChange = async (job: JobProfile, intervalMinutes: number) => {
    const current = candidateSearchSchedules.find((item) => item.jobId === job.jobProfileId);
    setScheduleBusyJobId(job.jobProfileId);
    try {
      const updated = await updateCandidateSearchSchedule(projectId, job.jobProfileId, {
        enabled: current?.enabled ?? false,
        intervalMinutes,
      });
      setCandidateSearchSchedules((items) => upsertSchedule(items, updated));
      setToast("自动搜索频率已更新");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "自动搜索频率保存失败");
    } finally {
      setScheduleBusyJobId(null);
    }
  };

  const handleSelectEmailCandidate = async (candidate: Candidate) => {
    const job = jobs.find((item) => item.jobProfileId === candidate.targetJobProfileId);
    setSelectedCandidate(candidate);
    setOutreachDraft(null);
    setEmailSubject("");
    setEmailDraft("");
    setEmailDraftLoading(true);
    try {
      const draft = await createOutreachDraft({
        projectId,
        jobId: job?.jobProfileId ?? candidate.targetJobProfileId,
        candidateId: candidate.candidateId,
        segmentId: savedSegment?.segmentId,
      });
      setOutreachDraft(draft);
      setEmailSubject(draft.subject);
      setEmailDraft(draft.body);
      getOutreachHistory({ projectId, candidateId: candidate.candidateId })
        .then((history) => setOutreachHistory(history.items))
        .catch(() => null);
      setToast("已生成后端邮件草稿");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "邮件草稿生成失败");
    } finally {
      setEmailDraftLoading(false);
    }
  };

  const handleConfirmCandidateCompliance = async (candidate: Candidate) => {
    if (typeof candidate.jobCandidateId !== "number") {
      setToast("候选人关联 ID 缺失，无法确认来源");
      return;
    }
    setConfirmingComplianceCandidateId(candidate.candidateId);
    try {
      await confirmCandidateCompliance(projectId, candidate.jobCandidateId);
      setToast("已确认联系方式来源合法，候选人可进入触达流程");
      await loadProjectData(filterCriteria);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "来源合规确认失败");
    } finally {
      setConfirmingComplianceCandidateId(null);
    }
  };

  const handleConfirmDraft = async (draft: string) => {
    if (!selectedCandidate || !outreachDraft) return;
    setHumanGateBusy(true);
    try {
      const updated = await updateOutreachDraft(outreachDraft.draftId, {
        subject: emailSubject,
        body: draft,
      });
      setOutreachDraft(updated);
      setEmailSubject(updated.subject);
      setEmailDraft(updated.body);
      const sendResult = await sendOutreachDraft({
        draftId: updated.draftId,
        decision: "approve",
        simulate: !emailDeliveryGate.enabled,
      });
      setOutreachHistory((current) => [sendResult, ...current]);
      setDraftConfirmOpen(false);
      setToast(sendResult.deliveryMode === "simulated" ? "草稿已确认，未发送；已记录模拟触达。" : "真实邮件已发送，并写入触达历史。");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "草稿确认失败");
    } finally {
      setHumanGateBusy(false);
    }
  };

  const handleApproveHumanGate = async (draft: string, decision: "approve" | "edit" = "approve") => {
    if (!humanGateRequest) return;
    setHumanGateBusy(true);
    try {
      await confirmTask(
        humanGateRequest.taskId,
        decision,
        {
          draft,
          candidateName: humanGateRequest.candidateName,
        },
        draft,
      );
      handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
      setHumanGateRequest(null);
      setToast("已提交人工确认，等待后端继续任务");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "人工确认失败");
    } finally {
      setHumanGateBusy(false);
    }
  };

  const handleRejectHumanGate = async () => {
    if (!humanGateRequest) return;
    setHumanGateBusy(true);
    try {
      await confirmTask(
        humanGateRequest.taskId,
        "reject",
        {
          draft: humanGateRequest.draft,
          candidateName: humanGateRequest.candidateName,
        },
        humanGateRequest.draft,
      );
      handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
      setHumanGateRequest(null);
      setToast("已拒绝，任务继续处理人工反馈");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "人工拒绝失败");
    } finally {
      setHumanGateBusy(false);
    }
  };

  const handleCancelTask = async () => {
    if (!activeTaskId) return;
    setTaskControlBusy(true);
    try {
      await cancelTask(activeTaskId);
      setToast("已请求后端取消任务");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "取消任务失败");
    } finally {
      setTaskControlBusy(false);
    }
  };

  const handleRetryTask = async () => {
    if (!activeTaskId) return;
    setTaskControlBusy(true);
    try {
      const created = await retryTask(activeTaskId);
      setActiveTaskId(created.task_id);
      setTaskPanelOpen(true);
      setToast("已通过后端创建重试任务");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "重试任务失败");
    } finally {
      setTaskControlBusy(false);
    }
  };

  if (loadingState === "loading" || loadingState === "idle") {
    return (
      <div className="space-y-5">
        <div className="h-28 animate-pulse rounded-[14px] border border-[#E5E7EB] bg-white" />
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-[104px] animate-pulse rounded-[14px] border border-[#E5E7EB] bg-white" />
          ))}
        </div>
      </div>
    );
  }

  if (loadingState === "error" || !project) {
    return (
      <div className="rounded-[14px] border border-[#FECACA] bg-[#FEF2F2] p-8 text-[14px] text-[#EF4444]">
        <div>{loadError || "项目数据加载失败"}</div>
        <button
          type="button"
          onClick={() => loadProjectData(filterCriteria)}
          className="mt-4 h-[38px] rounded-[10px] bg-[#EF4444] px-3.5 text-[14px] font-medium text-white"
        >
          重新加载
        </button>
      </div>
    );
  }

  const steps = ["招聘需求", "岗位分析", "找候选人", "候选人评估", "筛选人群", "发送邮件"];
  const statusText = projectStatusLabel[project.status] ?? project.status;

  return (
    <div className="min-w-0 pb-8">
      <section className="mb-5 flex min-w-0 flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[24px] font-bold leading-8 text-[#111827]">{project.name}</h1>
            <span className={`rounded-full px-2 py-0.5 text-[12px] font-medium ${statusBadge(project.status)}`}>
              {statusText}
            </span>
          </div>
          <p className="mt-2 text-[13px] leading-5 text-[#6B7280]">
            真实后端数据驱动 · 负责人：{project.owner ?? "—"} · 更新时间：
            {formatDateTime(project.updatedAt)}
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-end gap-2">
          <label className="text-[12px] font-medium text-[#6B7280]">
            搜索模式
            <select
              value={candidateSearchMode}
              onChange={(event) => setCandidateSearchMode(event.currentTarget.value as SearchMode)}
              className="mt-1 h-[38px] w-[132px] rounded-[10px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
            >
              {SEARCH_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={handleRunFirstJob}
            disabled={!jobs.length || !actionAvailability.find_candidates.enabled}
            title={!actionAvailability.find_candidates.enabled ? actionAvailability.find_candidates.reason : undefined}
            className="h-[38px] rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
          >
            运行首个岗位找候选人
          </button>
          <button
            type="button"
            onClick={handleRunWeeklyReport}
            disabled={!weeklyReportGate.enabled}
            title={!weeklyReportGate.enabled ? weeklyReportGate.reason : undefined}
            className="h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
          >
            生成周报
          </button>
          <button
            type="button"
            onClick={() => {
              setActionExplanationText("动作解释：更多 · 打开任务记录 · 不调用后端 API");
              setTaskPanelOpen(true);
            }}
            className="grid h-[38px] w-[38px] place-items-center rounded-[10px] border border-[#E5E7EB] bg-white text-[18px] leading-none text-[#6B7280]"
            aria-label="更多"
          >
            ...
          </button>
          <button
            type="button"
            onClick={() => setTaskPanelOpen(true)}
            className={`h-[38px] rounded-full px-3.5 text-[13px] font-medium ${taskStatusTone[taskStatus] ?? taskStatusTone.idle}`}
          >
            {taskStatusLabel[taskStatus] ?? taskStatus}
          </button>
        </div>
      </section>

      <ProjectSummaryCards {...projectSummary} />

      {actionExplanationText ? (
        <section className="mt-5 rounded-[12px] border border-[#DBEAFE] bg-[#EFF6FF] px-4 py-3 text-[13px] leading-5 text-[#1E40AF]">
          {actionExplanationText}
        </section>
      ) : null}

      {integrationsError || integrations ? (
      <section className="mt-5 min-w-0 rounded-[14px] border border-[#E5E7EB] bg-white px-5 py-3 text-[13px] leading-5 text-[#374151] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
          <div className="font-semibold text-[#111827]">后端能力状态</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <span>Search：{capabilityStatusLabel(searchGate.status)}</span>
            <span>LLM：{capabilityStatusLabel(llmGate.status)}</span>
            <span>Embedding：{capabilityStatusLabel(embeddingGate.status)}</span>
            <span>Vector：{capabilityStatusLabel(vectorGate.status)}</span>
            <span>Database：{capabilityStatusLabel(databaseGate.status)}</span>
            <span>Email Delivery：{capabilityStatusLabel(emailDeliveryGate.status)}</span>
            <span>
              搜索预检：{searchProviderSummary.ready}/{searchProviderSummary.total} 可用
              {searchProviderSummary.blocked ? ` · ${searchProviderSummary.blocked} 阻断` : ""}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {searchProviderPreflight.slice(0, 6).map((item) => (
              <span
                key={`${item.service}-${item.status}`}
                className="rounded-[7px] bg-[#F3F4F6] px-2 py-0.5 text-[11px] text-[#4B5563]"
                title={item.reason}
              >
                {item.service}: {capabilityStatusLabel(item.status)}
              </span>
            ))}
          </div>
          {integrationsError ? <div className="mt-1 text-[#EF4444]">{integrationsError}</div> : null}
        </section>
      ) : null}

      <section className="mt-5 min-w-0 rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
        <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
          <div>
            <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">岗位智能生成</h2>
            <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">
              可从 BP、项目提示词或两者结合生成岗位矩阵；预览不会写入数据库，确认覆盖后才会重建当前项目岗位。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handlePreviewBpJobs}
              disabled={bpBusy !== null}
              className="h-[38px] rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {bpBusy === "preview" ? "生成中" : "预览岗位矩阵"}
            </button>
            <button
              type="button"
              onClick={handleConfirmBpJobs}
              disabled={!bpPreview || bpBusy !== null}
              className="h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {bpBusy === "confirm" ? "写入中" : "确认覆盖岗位"}
            </button>
          </div>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-[180px_minmax(260px,1fr)_160px]">
          <label className="text-[12px] font-medium text-[#6B7280]">
            生成方式
            <select
              value={bpGenerationMode}
              onChange={(event) => {
                setBpGenerationMode(event.currentTarget.value as ProjectGenerationMode);
                setBpPreview(null);
              }}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              <option value="bp_plus_prompt">BP + 提示词</option>
              <option value="bp_file">仅 BP</option>
              <option value="prompt">仅提示词</option>
            </select>
          </label>
          <label className="text-[12px] font-medium text-[#6B7280]">
            BP 文件路径
            <input
              value={bpFilePath}
              disabled={bpGenerationMode === "prompt"}
              onChange={(event) => {
                setBpFilePath(event.currentTarget.value);
                setBpPreview(null);
              }}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] disabled:bg-[#F3F4F6] disabled:text-[#9CA3AF]"
            />
          </label>
          <label className="text-[12px] font-medium text-[#6B7280]">
            最少岗位数
            <input
              type="number"
              min={1}
              max={64}
              value={bpMinimumRoleCount}
              onChange={(event) => {
                setBpMinimumRoleCount(Math.max(1, Math.min(64, Number(event.currentTarget.value) || 14)));
                setBpPreview(null);
              }}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            />
          </label>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <label className="text-[12px] font-medium text-[#6B7280]">
            项目提示词
            <textarea
              value={bpProjectPrompt}
              onChange={(event) => {
                setBpProjectPrompt(event.currentTarget.value);
                setBpPreview(null);
              }}
              rows={4}
              placeholder="例如：我要为工业质检边缘 AI 项目生成岗位，覆盖算法、硬件、交付和客户成功。"
              className="mt-1 min-h-[96px] w-full resize-y rounded-[10px] border border-[#D1D5DB] bg-white px-3 py-2 text-[13px] leading-5 text-[#111827]"
            />
          </label>
          <label className="text-[12px] font-medium text-[#6B7280]">
            行业研究偏好
            <textarea
              value={bpIndustryResearchPrompt}
              onChange={(event) => {
                setBpIndustryResearchPrompt(event.currentTarget.value);
                setBpPreview(null);
              }}
              rows={4}
              placeholder="例如：重点关注行业场景、竞品团队、交付链路、合规约束和候选人搜索策略。"
              className="mt-1 min-h-[96px] w-full resize-y rounded-[10px] border border-[#D1D5DB] bg-white px-3 py-2 text-[13px] leading-5 text-[#111827]"
            />
          </label>
        </div>
        {bpError ? <div className="mt-3 text-[13px] leading-5 text-[#EF4444]">{bpError}</div> : null}
        {bpPreview ? (
          <div className="mt-4 rounded-[12px] bg-[#F9FAFB] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-[13px] font-semibold text-[#111827]">
                预览岗位 {bpPreview.jobCount} 个 · {generationModeLabel[bpPreview.generationMode] ?? bpPreview.generationMode} ·{" "}
                {bpPreview.promptName}
              </div>
              <div className="text-[12px] text-[#6B7280]">{bpPreview.projectName}</div>
            </div>
            {bpPreview.generationDegraded ? (
              <div className="mt-2 rounded-[10px] border border-[#FCD34D] bg-[#FFFBEB] px-3 py-2 text-[12px] leading-[18px] text-[#92400E]">
                降级产出：LLM 不可用或超时，本次岗位矩阵未经过「承诺 → 能力 → 缺口 → 岗位」审计链，仅用于先启动项目，请稍后重新预览。
              </div>
            ) : null}
            {bpPreview.industryReading ? (
              <p className="mt-2 text-[12px] leading-[18px] text-[#6B7280]">{bpPreview.industryReading}</p>
            ) : null}
            {bpPreview.researchTrace.length ? (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {bpPreview.researchTrace.map((item) => (
                  <div key={`${item.stage}-${item.summary}`} className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
                    <div className="text-[12px] font-semibold text-[#111827]">{item.stage}</div>
                    <div className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">{item.summary}</div>
                    {item.risk ? <div className="mt-1 text-[12px] leading-[18px] text-[#92400E]">{item.risk}</div> : null}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-3 grid max-h-[320px] gap-2 overflow-auto md:grid-cols-2">
              {bpPreview.jobs.map((job) => (
                <div key={job.jobProfileId} className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[13px] font-semibold text-[#111827]">{job.roleName}</div>
                    {job.rationale?.hiringPriority ? (
                      <span className="rounded-full bg-[#EFF6FF] px-2 py-0.5 text-[11px] font-medium text-[#2563EB]">
                        {job.rationale.hiringPriority}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 text-[12px] text-[#6B7280]">
                    HC {job.headcount ?? 1}
                    {(job.mustHaveSkills ?? []).length ? ` · ${(job.mustHaveSkills ?? []).slice(0, 3).join(" / ")}` : ""}
                  </div>
                  {job.rationale?.whyNeeded ? (
                    <div className="mt-1 text-[12px] leading-[18px] text-[#374151]">为什么需要：{job.rationale.whyNeeded}</div>
                  ) : null}
                  {job.rationale?.ifNotHiredRisk ? (
                    <div className="mt-1 text-[12px] leading-[18px] text-[#92400E]">不招的风险：{job.rationale.ifNotHiredRisk}</div>
                  ) : null}
                  {(job.rationale?.bpEvidence ?? []).length ? (
                    <div className="mt-1 truncate text-[11px] text-[#6B7280]" title={(job.rationale?.bpEvidence ?? []).join("\n")}>
                      BP 证据：{(job.rationale?.bpEvidence ?? [])[0]}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
            {(bpPreview.rejectedRoles ?? []).length ? (
              <div className="mt-3 rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
                <div className="text-[12px] font-semibold text-[#111827]">
                  Critic Gate 拒绝 {(bpPreview.rejectedRoles ?? []).length} 个岗位（不会写入数据库）
                </div>
                {(bpPreview.rejectedRoles ?? []).map((item) => (
                  <div key={item.title} className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">
                    {item.title}：{item.reasons.join("；")}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="my-5 min-w-0 rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
        <div className="grid grid-cols-3 items-start gap-y-4 sm:grid-cols-6">
          {steps.map((step, index) => {
            const state = workflowStatus(index, jobs, candidates, taskSnapshot?.status ?? null, activeTaskAction);
            const isDone = state === "done";
            const isCurrent = state === "current";
            return (
              <div key={step} className="relative flex flex-col items-center gap-2">
                {index > 0 ? (
                  <div
                    className={[
                      "absolute right-1/2 top-[14px] hidden h-0.5 w-full sm:block",
                      workflowStatus(index - 1, jobs, candidates, taskSnapshot?.status ?? null, activeTaskAction) === "done"
                        ? "bg-[#2563EB]"
                        : "bg-[#E5E7EB]",
                    ].join(" ")}
                  />
                ) : null}
                <div
                  className={[
                    "relative z-10 grid h-7 w-7 place-items-center rounded-full text-[12px] font-semibold",
                    isDone
                      ? "bg-[#2563EB] text-white"
                      : isCurrent
                        ? "border-2 border-[#2563EB] bg-white text-[#2563EB]"
                        : "bg-[#F3F4F6] text-[#9CA3AF]",
                  ].join(" ")}
                >
                  {isDone ? "✓" : index + 1}
                </div>
                <div className={isDone || isCurrent ? "text-[13px] text-[#111827]" : "text-[13px] text-[#9CA3AF]"}>
                  {step}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-5">
          <MultiJobProgressTable
            jobs={jobs}
            candidateCounts={jobCandidateCounts}
            actionAvailability={actionAvailability}
            matchAvailability={matchGate}
            runningJobAction={runningJobAction}
            matchingJobId={matchingJobId}
            onRunAction={handleRunAction}
            onRunMatch={handleRunMatch}
            onRefresh={() => loadProjectData(filterCriteria)}
          />
          {matchResult ? (
            <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">岗位匹配结果</h2>
                <span className="text-[12px] text-[#6B7280]">{matchResult.jobName}</span>
              </div>
              <p className="mt-2 text-[12px] leading-[18px] text-[#9CA3AF]">
                以下内容完全来自后端 /jobs/match 返回结果，前端不生成或修正匹配分。
              </p>
              <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-[10px] bg-[#F9FAFB] p-3 text-[12px] leading-5 text-[#374151]">
                {JSON.stringify(matchResult.response, null, 2)}
              </pre>
            </section>
          ) : null}
          <CandidateTable
            candidates={visibleCandidates}
            onSendEmail={handleSelectEmailCandidate}
            onConfirmCompliance={handleConfirmCandidateCompliance}
            onRunEvaluation={handleRunCandidateEvaluation}
            canRunEvaluation={actionAvailability.candidate_evaluation.enabled}
            evaluationDisabledReason={actionAvailability.candidate_evaluation.reason}
            evaluatingCandidateId={runningCandidateId}
            confirmingComplianceCandidateId={confirmingComplianceCandidateId}
            hasMore={hasMoreCandidates}
            isLoadingMore={loadingMoreCandidates}
            loadedCount={candidates.length}
            onLoadMore={handleLoadMoreCandidates}
            onViewAll={() => {
              setVisibleCandidates(candidates);
              setSegmentPreviewCount(null);
              setActionExplanationText("动作解释：查看全部候选人 · 使用当前已加载候选人数据 · 不调用后端 API");
              setToast("已显示当前已加载的全部候选人");
            }}
            totalCount={candidateTotalCount}
          />
        </div>

        <aside className="space-y-5 xl:sticky xl:top-[84px] xl:self-start">
          <CandidateAutoSearchCard
            jobs={jobs}
            schedules={candidateSearchSchedules}
            busyJobId={scheduleBusyJobId}
            canUpdate={searchGate.enabled}
            disabledReason={searchGate.reason}
            onToggle={handleUpdateCandidateSearchSchedule}
            onIntervalChange={handleCandidateSearchIntervalChange}
          />
          <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
            <div className="flex items-center justify-between">
              <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">筛选条件</h2>
              <button
                type="button"
                onClick={() => setFilterCriteria(defaultFilterCriteria)}
                className="text-[13px] font-medium text-[#2563EB]"
              >
                清空
              </button>
            </div>
            <p className="mt-2 text-[12px] leading-[18px] text-[#9CA3AF]">
              筛选条件提交后端查询真实候选人，保存后生成 segmentId 供后续触达使用。
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">岗位</span>
                <select
                  value={filterCriteria.jobProfileId}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, jobProfileId: event.target.value }))}
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value="all">全部岗位</option>
                  {jobs.map((job) => (
                    <option key={job.jobProfileId} value={job.jobProfileId}>
                      {job.roleName}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">匹配分</span>
                <select
                  value={filterCriteria.minScore}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, minScore: Number(event.target.value) }))}
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value={60}>60分以上</option>
                  <option value={70}>70分以上</option>
                  <option value={80}>80分以上</option>
                  <option value={90}>90分以上</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">城市</span>
                <select
                  value={filterCriteria.city}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, city: event.target.value }))}
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value="">全部城市</option>
                  {cities.map((city) => (
                    <option key={city} value={city}>
                      {city}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">是否已触达</span>
                <select
                  value={filterCriteria.outreachStatus}
                  onChange={(event) =>
                    setFilterCriteria((current) => ({
                      ...current,
                      outreachStatus: event.target.value as FilterCriteria["outreachStatus"],
                    }))
                  }
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value="all">全部</option>
                  <option value="not_sent">未触达</option>
                  <option value="drafted">草稿中</option>
                  <option value="sent">已触达</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">有邮箱</span>
                <select
                  value={filterCriteria.hasEmail}
                  onChange={(event) =>
                    setFilterCriteria((current) => ({ ...current, hasEmail: event.target.value as FilterCriteria["hasEmail"] }))
                  }
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value="all">全部</option>
                  <option value="yes">是</option>
                  <option value="no">否</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] leading-[18px] text-[#6B7280]">来源</span>
                <select
                  value={filterCriteria.sourcePlatform}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, sourcePlatform: event.target.value }))}
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                >
                  <option value="all">全部来源</option>
                  {sources.map((source) => (
                    <option key={source} value={source}>
                      {source}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handleQuerySegment}
                disabled={segmentBusy}
                className="h-10 w-full rounded-[10px] bg-[#2563EB] text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {segmentBusy ? "查询中..." : "查询目标人群"}
              </button>
              <button
                type="button"
                onClick={handleSaveSegment}
                disabled={segmentBusy || segmentPreviewCount === null || !segmentCreateGate.enabled}
                title={!segmentCreateGate.enabled ? segmentCreateGate.reason : undefined}
                className="h-10 w-full rounded-[10px] border border-[#E5E7EB] bg-white text-[14px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
              >
                保存目标人群
              </button>
              {segmentPreviewCount !== null ? (
                <p className="text-[12px] leading-[18px] text-[#6B7280]">
                  后端筛选命中 {segmentPreviewCount} 人{savedSegment ? `，已保存 ${savedSegment.segmentId}` : "，尚未保存"}。
                </p>
              ) : null}
            </div>
          </section>

          <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">邮件草稿</h2>
              <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[12px] font-medium text-[#6B7280]">
                {outreachDraft?.backendGenerated ? "后端生成" : "等待后端草稿"}
              </span>
            </div>
            {selectedCandidate ? (
              <div className="mt-4 space-y-3">
                <p className="text-[12px] leading-[18px] text-[#9CA3AF]">
                  草稿由 POST /outreach/draft 生成，编辑通过 PATCH /outreach/drafts/&lt;draftId&gt; 保存，确认后写入触达历史。
                </p>
                <p className={`text-[12px] leading-[18px] ${emailDeliveryGate.enabled ? "text-[#047857]" : "text-[#F59E0B]"}`}>
                  {emailDeliveryGate.enabled
                    ? "邮件发送 API 已接入，确认后会调用后端真实发送并写入触达历史。"
                    : "邮件发送 API 未就绪，确认后仅记录模拟触达，不显示真实送达状态。"}
                </p>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-[#6B7280]">收件人</span>
                  <input
                    value={selectedCandidate.email ?? ""}
                    readOnly
                    className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-[#F9FAFB] px-2.5 text-[13px] text-[#374151]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-[#6B7280]">主题</span>
                  <input
                    value={emailSubject}
                    onChange={(event) => setEmailSubject(event.target.value)}
                    disabled={emailDraftLoading}
                    className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-[#6B7280]">正文</span>
                  <textarea
                    ref={emailDraftTextareaRef}
                    value={emailDraft}
                    onChange={(event) => setEmailDraft(event.target.value)}
                    disabled={emailDraftLoading}
                    rows={7}
                    className="h-40 w-full resize-none rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2 text-[13px] leading-[22px] text-[#111827]"
                  />
                </label>
                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={() => {
                      void handleSelectEmailCandidate(selectedCandidate);
                    }}
                    disabled={emailDraftLoading}
                    className="h-9 rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151]"
                  >
                    {emailDraftLoading ? "生成中" : "重新生成"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      emailDraftTextareaRef.current?.focus();
                      setActionExplanationText("动作解释：编辑邮件草稿 · 聚焦本地可编辑草稿 · 不调用后端 API");
                    }}
                    disabled={!outreachDraft}
                    className="h-9 rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151]"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraftConfirmOpen(true)}
                    disabled={!outreachDraft || emailDraftLoading}
                    className="h-9 rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white"
                  >
                    确认草稿
                  </button>
                </div>
                {outreachHistory.length ? (
                  <div className="rounded-[10px] bg-[#F9FAFB] px-3 py-2 text-[12px] leading-[18px] text-[#6B7280]">
                    最近触达记录：{outreachHistory[0].status} · {outreachHistory[0].deliveryMode}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-4 rounded-[10px] border border-dashed border-[#E5E7EB] bg-[#F9FAFB] px-4 py-6 text-center text-[13px] leading-5 text-[#6B7280]">
                从候选人表点击“生成草稿”后，这里会请求后端生成草稿；没有后端返回则不展示草稿。
              </p>
            )}
          </section>

          <WeeklyReportCard
            report={weeklyReport}
            onGenerate={handleRunWeeklyReport}
            canGenerate={weeklyReportGate.enabled}
            disabledReason={weeklyReportGate.reason}
            error={weeklyReportError}
          />
        </aside>
      </section>

      {taskPanelOpen ? (
        <div className="fixed inset-0 z-50 bg-[#111827]/30" onClick={() => setTaskPanelOpen(false)}>
          <div
            className="absolute right-0 top-0 h-full w-[min(460px,100vw)] overflow-auto bg-[#F6F8FB] p-5"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-[18px] font-bold text-[#111827]">任务记录</h2>
              <button
                type="button"
                onClick={() => setTaskPanelOpen(false)}
                className="grid h-[38px] w-[38px] place-items-center rounded-[10px] border border-[#E5E7EB] bg-white text-[#6B7280]"
              >
                ×
              </button>
            </div>
            <LiveTaskSummary
              taskId={activeTaskId}
              events={events}
              taskSnapshot={taskSnapshot}
              connectionState={connectionState}
              error={streamError}
              usedFallbackPolling={usedFallbackPolling}
              busy={taskControlBusy}
              onCancel={handleCancelTask}
              onRetry={handleRetryTask}
            />
          </div>
        </div>
      ) : null}

      <BackendLinkPanel
        projectId={projectId}
        lastRequest={lastApiRequest}
        taskId={activeTaskId}
        taskAction={activeTaskAction}
        taskSnapshot={taskSnapshot}
        connectionState={connectionState}
        retryCount={retryCount}
        usedFallbackPolling={usedFallbackPolling}
        events={events}
      />

      <HumanConfirmModal
        open={Boolean(humanGateRequest) || draftConfirmOpen}
        busy={humanGateBusy}
        context={
          humanGateRequest?.context ??
          (selectedCandidate ? `请确认候选人 ${selectedCandidate.name} 的邮件草稿。` : "")
        }
        draft={humanGateRequest?.draft ?? emailDraft}
        candidateName={humanGateRequest?.candidateName ?? selectedCandidate?.name}
        requiresLeadPreview={humanGateRequest?.requiresLeadPreview}
        leadPreview={humanGateRequest?.leadPreview}
        onApprove={
          humanGateRequest
            ? handleApproveHumanGate
            : (draft) => {
                void handleConfirmDraft(draft);
              }
        }
        onReject={humanGateRequest ? handleRejectHumanGate : () => setDraftConfirmOpen(false)}
        onClose={() => {
          if (humanGateRequest) handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
          setHumanGateRequest(null);
          setDraftConfirmOpen(false);
        }}
      />

      {toast ? (
        <div className="fixed right-5 top-20 z-50 rounded-[14px] border border-[#E5E7EB] bg-white px-4 py-3 text-[13px] font-medium text-[#111827] shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function CandidateAutoSearchCard({
  jobs,
  schedules,
  busyJobId,
  canUpdate,
  disabledReason,
  onToggle,
  onIntervalChange,
}: {
  jobs: JobProfile[];
  schedules: CandidateSearchSchedule[];
  busyJobId: string | null;
  canUpdate: boolean;
  disabledReason?: string;
  onToggle: (job: JobProfile, enabled: boolean) => void;
  onIntervalChange: (job: JobProfile, intervalMinutes: number) => void;
}) {
  const safeSchedules = Array.isArray(schedules) ? schedules : [];
  const safeJobs = Array.isArray(jobs) ? jobs : [];
  const scheduleByJobId = new Map(safeSchedules.map((schedule) => [schedule.jobId, schedule]));
  return (
    <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">自动搜候选人</h2>
        <span className={canUpdate ? "text-[12px] text-[#16A34A]" : "text-[12px] text-[#EF4444]"}>
          {canUpdate ? "可用" : "不可用"}
        </span>
      </div>
      <div className="mt-4 space-y-3">
        {safeJobs.map((job) => {
          const schedule = scheduleByJobId.get(job.jobProfileId);
          const enabled = Boolean(schedule?.enabled);
          const busy = busyJobId === job.jobProfileId;
          return (
            <div key={job.jobProfileId} className="rounded-[10px] border border-[#EEF2F7] px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-[#111827]">{job.roleName}</div>
                  <div className="mt-1 text-[12px] text-[#6B7280]">
                    {enabled ? "已开启" : "未开启"} · 下次：{schedule?.nextRunAt ? formatDateTime(schedule.nextRunAt) : "—"}
                  </div>
                  {schedule?.lastTaskId ? (
                    <div className="mt-1 text-[11px] text-[#9CA3AF]">
                      最近任务：{schedule.lastTaskId} · {schedule.lastStatus || "unknown"}
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => onToggle(job, !enabled)}
                  disabled={busy || !canUpdate}
                  title={!canUpdate ? disabledReason : undefined}
                  aria-label={`${enabled ? "关闭" : "开启"}自动搜索 ${job.roleName}`}
                  className={
                    enabled
                      ? "h-8 shrink-0 rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[12px] font-medium text-[#374151] disabled:cursor-not-allowed disabled:opacity-50"
                      : "h-8 shrink-0 rounded-[9px] bg-[#2563EB] px-3 text-[12px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                  }
                >
                  {busy ? "保存中" : enabled ? "关闭" : "开启"}
                </button>
              </div>
              <label className="mt-3 block">
                <span className="mb-1.5 block text-[12px] text-[#6B7280]">频率</span>
                <select
                  value={schedule?.intervalMinutes ?? 360}
                  onChange={(event) => onIntervalChange(job, Number(event.target.value))}
                  disabled={busy || !canUpdate}
                  className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <option value={60}>每 1 小时</option>
                  <option value={180}>每 3 小时</option>
                  <option value={360}>每 6 小时</option>
                  <option value={1440}>每天</option>
                </select>
              </label>
            </div>
          );
        })}
      </div>
    </section>
  );
}
