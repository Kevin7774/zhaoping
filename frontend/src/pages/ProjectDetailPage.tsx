import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { CandidateTable } from "../features/candidates/components/CandidateTable";
import type { Candidate } from "../features/candidates/types";
import type { JobProfile, StepStatus } from "../features/jobs/types";
import {
  createOutreachDraft,
  createSegment,
  confirmTask,
  cancelTask,
  getIntegrationsStatus,
  getLatestWeeklyReport,
  getOutreachHistory,
  getProject,
  getProjectCandidatesPage,
  getProjectJobs,
  getTask,
  querySegmentCandidates,
  retryTask,
  runJobMatch,
  runCandidateEvaluation,
  runProjectScenario,
  runWeeklyReport,
  saveWeeklyReport,
  sendOutreachDraft,
  type IntegrationsStatusResponse,
  type JobMatchResponse,
  type OutreachDraft,
  type OutreachHistoryItem,
  type ProjectRecord,
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
import { humanGateRequestFromEvent, type HumanGateRequest } from "../features/projects/humanGate";
import { defaultFilterCriteria, type FilterCriteria } from "../features/projects/state";
import { apiClient, type ApiRequestLogEntry } from "../shared/api/client";
import { useTaskStream } from "../shared/hooks/useTaskStream";

type LoadingState = "idle" | "loading" | "ready" | "error";

const DEFAULT_PROJECT_ID = "project_2026_ai_team";
const CANDIDATE_PAGE_SIZE = 50;

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
  const { projectId: routeProjectId } = useParams();
  const projectId = routeProjectId || DEFAULT_PROJECT_ID;
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
  const [matchResult, setMatchResult] = useState<{ jobName: string; response: JobMatchResponse } | null>(null);
  const [matchingJobId, setMatchingJobId] = useState<string | null>(null);
  const [taskPanelOpen, setTaskPanelOpen] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeTaskAction, setActiveTaskAction] = useState<RunProjectScenarioAction | "weekly_report" | null>(null);
  const [runningJobAction, setRunningJobAction] = useState<{
    jobProfileId: string;
    action: RunProjectScenarioAction;
  } | null>(null);
  const [runningCandidateId, setRunningCandidateId] = useState<string | null>(null);
  const [taskControlBusy, setTaskControlBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastApiRequest, setLastApiRequest] = useState<ApiRequestLogEntry | null>(null);
  const [humanGateRequest, setHumanGateRequest] = useState<HumanGateRequest | null>(null);
  const [humanGateBusy, setHumanGateBusy] = useState(false);
  const completedTaskIdsRef = useRef<Set<string>>(new Set());
  const savedWeeklyReportTaskIdsRef = useRef<Set<string>>(new Set());
  const handledHumanGateKeysRef = useRef<Set<string>>(new Set());

  const {
    events,
    taskSnapshot,
    connectionState,
    error: streamError,
    retryCount,
    usedFallbackPolling,
  } = useTaskStream(activeTaskId);
  const taskStatus = taskSnapshot?.status ?? (activeTaskId ? connectionState : "idle");

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
    setMatchResult(null);
    setMatchingJobId(null);
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
      if (!report) return;
      savedWeeklyReportTaskIdsRef.current.add(activeTaskId);
      saveWeeklyReport(projectId, activeTaskId, report)
        .then((record) => {
          setPersistedWeeklyReport(record.content);
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
    if (!databaseGate.enabled) {
      setToast(`目标人群保存不可用：${databaseGate.reason}`);
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
    setToast(`正在启动${actionLabel}任务`);

    try {
      const created = await runProjectScenario(projectId, job, action);
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
        simulate: true,
      });
      setOutreachHistory((current) => [sendResult, ...current]);
      setDraftConfirmOpen(false);
      setToast(sendResult.deliveryMode === "simulated" ? "已记录模拟发送，未真实发送。" : "已写入触达记录。");
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
    <div className="pb-8">
      <section className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div>
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
        <div className="flex flex-wrap gap-2">
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

      {integrationsError || integrations ? (
        <section className="mt-5 rounded-[14px] border border-[#E5E7EB] bg-white px-5 py-3 text-[13px] leading-5 text-[#374151] shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <div className="font-semibold text-[#111827]">后端能力状态</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <span>Search：{capabilityStatusLabel(searchGate.status)}</span>
            <span>LLM：{capabilityStatusLabel(llmGate.status)}</span>
            <span>Embedding：{capabilityStatusLabel(embeddingGate.status)}</span>
            <span>Vector：{capabilityStatusLabel(vectorGate.status)}</span>
            <span>Database：{capabilityStatusLabel(databaseGate.status)}</span>
            <span>Email Delivery：{capabilityStatusLabel(emailDeliveryGate.status)}</span>
          </div>
          {integrationsError ? <div className="mt-1 text-[#EF4444]">{integrationsError}</div> : null}
        </section>
      ) : null}

      <section className="my-5 rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="grid grid-cols-6 items-start">
          {steps.map((step, index) => {
            const state = workflowStatus(index, jobs, candidates, taskSnapshot?.status ?? null, activeTaskAction);
            const isDone = state === "done";
            const isCurrent = state === "current";
            return (
              <div key={step} className="relative flex flex-col items-center gap-2">
                {index > 0 ? (
                  <div
                    className={[
                      "absolute right-1/2 top-[14px] h-0.5 w-full",
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

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
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
            <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
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
            onRunEvaluation={handleRunCandidateEvaluation}
            canRunEvaluation={actionAvailability.candidate_evaluation.enabled}
            evaluationDisabledReason={actionAvailability.candidate_evaluation.reason}
            evaluatingCandidateId={runningCandidateId}
            hasMore={hasMoreCandidates}
            isLoadingMore={loadingMoreCandidates}
            loadedCount={candidates.length}
            onLoadMore={handleLoadMoreCandidates}
            totalCount={candidateTotalCount}
          />
        </div>

        <aside className="space-y-5 xl:sticky xl:top-[84px] xl:self-start">
          <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
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
                disabled={segmentBusy || segmentPreviewCount === null || !databaseGate.enabled}
                title={!databaseGate.enabled ? databaseGate.reason : undefined}
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

          <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
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
                <p className="text-[12px] leading-[18px] text-[#F59E0B]">
                  当前真实邮件提供方未接入发送动作，确认后仅记录模拟发送，不显示真实发送成功。
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
