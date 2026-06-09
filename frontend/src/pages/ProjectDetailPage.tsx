import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { CandidateTable } from "../features/candidates/components/CandidateTable";
import type { Candidate } from "../features/candidates/types";
import type { JobProfile, StepStatus } from "../features/jobs/types";
import {
  confirmTask,
  getProject,
  getProjectCandidates,
  getProjectJobs,
  getTask,
  runCandidateEvaluation,
  runProjectScenario,
  runWeeklyReport,
  type ProjectRecord,
  type RunProjectScenarioAction,
} from "../features/projects/api";
import { HumanConfirmModal } from "../features/projects/components/HumanConfirmModal";
import { LiveTaskSummary } from "../features/projects/components/LiveTaskSummary";
import { MultiJobProgressTable } from "../features/projects/components/MultiJobProgressTable";
import { ProjectSummaryCards } from "../features/projects/components/ProjectSummaryCards";
import { WeeklyReportCard } from "../features/projects/components/WeeklyReportCard";
import { humanGateRequestFromEvent, type HumanGateRequest } from "../features/projects/humanGate";
import {
  buildCandidateEmailDraft,
  defaultFilterCriteria,
  filterCandidates,
  type FilterCriteria,
} from "../features/projects/state";
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

function workflowStatus(index: number, jobs: JobProfile[], candidates: Candidate[], taskStatus: string | null) {
  if (taskStatus === "awaiting_human" && index === 3) return "current";
  if (taskStatus === "processing" && index >= 2 && index <= 3) return "current";
  if (index === 0) return "done";
  if (index === 1) return jobs.length ? "done" : "current";
  if (index === 2) return candidates.length ? "done" : jobs.length ? "current" : "pending";
  if (index === 3) return candidates.some((candidate) => candidate.matchScore > 0) ? "done" : "pending";
  if (index === 4) return candidates.length ? "current" : "pending";
  return candidates.some((candidate) => candidate.outreachStatus === "sent") ? "done" : "pending";
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

export function ProjectDetailPage() {
  const { projectId: routeProjectId } = useParams();
  const projectId = routeProjectId || DEFAULT_PROJECT_ID;
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [jobs, setJobs] = useState<JobProfile[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [visibleCandidates, setVisibleCandidates] = useState<Candidate[]>([]);
  const [hasMoreCandidates, setHasMoreCandidates] = useState(false);
  const [loadingMoreCandidates, setLoadingMoreCandidates] = useState(false);
  const [filterCriteria, setFilterCriteria] = useState<FilterCriteria>(defaultFilterCriteria);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [emailSubject, setEmailSubject] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [draftConfirmOpen, setDraftConfirmOpen] = useState(false);
  const [taskPanelOpen, setTaskPanelOpen] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [runningJobAction, setRunningJobAction] = useState<{
    jobProfileId: string;
    action: RunProjectScenarioAction;
  } | null>(null);
  const [runningCandidateId, setRunningCandidateId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [humanGateRequest, setHumanGateRequest] = useState<HumanGateRequest | null>(null);
  const [humanGateBusy, setHumanGateBusy] = useState(false);
  const completedTaskIdsRef = useRef<Set<string>>(new Set());
  const handledHumanGateKeysRef = useRef<Set<string>>(new Set());

  const { events, taskSnapshot, connectionState, error: streamError } = useTaskStream(activeTaskId);
  const taskStatus = taskSnapshot?.status ?? (activeTaskId ? connectionState : "idle");

  const loadProjectData = useCallback(
    async (criteria: FilterCriteria) => {
      setLoadingState((current) => (current === "idle" ? "loading" : current));
      setLoadError(null);

      try {
        const [projectData, jobsData, candidatesData] = await Promise.all([
          getProject(projectId),
          getProjectJobs(projectId),
          getProjectCandidates(projectId, { skip: 0, limit: CANDIDATE_PAGE_SIZE }),
        ]);

        setProject(projectData);
        setJobs(jobsData);
        setCandidates(candidatesData);
        setVisibleCandidates(filterCandidates(candidatesData, criteria));
        setHasMoreCandidates(candidatesData.length === CANDIDATE_PAGE_SIZE);
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

  useEffect(() => {
    setLoadingState("idle");
    setCandidates([]);
    setJobs([]);
    setProject(null);
    setVisibleCandidates([]);
    setHasMoreCandidates(false);
    setLoadingMoreCandidates(false);
    setHumanGateRequest(null);
    setRunningCandidateId(null);
    setDraftConfirmOpen(false);
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
      setToast("任务已完成，正在刷新候选人列表");
      loadProjectData(filterCriteria);
    }

    if (taskSnapshot.status === "error" || taskSnapshot.status === "cancelled") {
      setRunningJobAction(null);
      setRunningCandidateId(null);
    }
  }, [activeTaskId, filterCriteria, loadProjectData, taskSnapshot]);

  useEffect(() => {
    if (!activeTaskId) return;

    const latestHumanGate = [...events]
      .reverse()
      .map((event) => humanGateRequestFromEvent(event, activeTaskId))
      .find((request): request is HumanGateRequest => Boolean(request));

    if (!latestHumanGate || handledHumanGateKeysRef.current.has(latestHumanGate.eventKey)) return;
    setHumanGateRequest(latestHumanGate);
    setTaskPanelOpen(false);
    setToast("AI Agent 等待人工确认");
  }, [activeTaskId, events]);

  const projectSummary = useMemo(() => summaryFrom(jobs, candidates), [jobs, candidates]);
  const jobCandidateCounts = useMemo(() => candidateCounts(candidates), [candidates]);
  const cities = useMemo(() => uniqueValues(candidates.map((candidate) => candidate.city)), [candidates]);
  const sources = useMemo(() => uniqueValues(candidates.map((candidate) => candidate.sourcePlatform)), [candidates]);

  const handleGenerateSegment = () => {
    // 本地筛选真实后端候选人，不是 mock；后端 segments/query 接口接入后可替换为服务端筛选。
    const filtered = filterCandidates(candidates, filterCriteria);
    setVisibleCandidates(filtered);
    setToast(`已生成目标人群：${filtered.length} 人`);
  };

  const handleLoadMoreCandidates = async () => {
    if (loadingMoreCandidates || !hasMoreCandidates) return;
    setLoadingMoreCandidates(true);
    try {
      const nextCandidates = await getProjectCandidates(projectId, {
        skip: candidates.length,
        limit: CANDIDATE_PAGE_SIZE,
      });
      const mergedCandidates = [...candidates, ...nextCandidates];
      setCandidates(mergedCandidates);
      setVisibleCandidates(filterCandidates(mergedCandidates, filterCriteria));
      setHasMoreCandidates(nextCandidates.length === CANDIDATE_PAGE_SIZE);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "候选人加载失败");
    } finally {
      setLoadingMoreCandidates(false);
    }
  };

  const handleRunAction = async (job: JobProfile, action: RunProjectScenarioAction) => {
    setRunningJobAction({ jobProfileId: job.jobProfileId, action });
    setRunningCandidateId(null);
    setToast(action === "find_candidates" ? "正在启动找候选人任务" : "正在启动候选人评估任务");

    try {
      const created = await runProjectScenario(projectId, job, action);
      setActiveTaskId(created.task_id);
      setTaskPanelOpen(true);
      getTask(created.task_id).catch(() => null);
    } catch (error) {
      setRunningJobAction(null);
      setToast(error instanceof Error ? error.message : "任务启动失败");
    }
  };

  const handleRunCandidateEvaluation = async (candidate: Candidate) => {
    setRunningCandidateId(candidate.candidateId);
    setRunningJobAction(null);
    setToast(`正在启动 ${candidate.name} 的 Agent 评估`);

    try {
      const created = await runCandidateEvaluation(projectId, candidate);
      setActiveTaskId(created.task_id);
      setTaskPanelOpen(true);
      getTask(created.task_id).catch(() => null);
    } catch (error) {
      setRunningCandidateId(null);
      setToast(error instanceof Error ? error.message : "候选人评估任务启动失败");
    }
  };

  const handleRunWeeklyReport = async () => {
    if (!project) return;
    setToast("正在启动招聘周报任务");
    try {
      const created = await runWeeklyReport(projectId, project.name);
      setActiveTaskId(created.task_id);
      setTaskPanelOpen(true);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "周报任务启动失败");
    }
  };

  const handleRunAllJobs = async () => {
    const firstJob = jobs[0];
    if (!firstJob) return;
    await handleRunAction(firstJob, "find_candidates");
  };

  const handleSelectEmailCandidate = (candidate: Candidate) => {
    const job = jobs.find((item) => item.jobProfileId === candidate.targetJobProfileId);
    setSelectedCandidate({ ...candidate, outreachStatus: "drafted" });
    setEmailSubject(`关于「${job?.roleName ?? candidate.title}」的一次沟通邀请`);
    setEmailDraft(buildCandidateEmailDraft(candidate, job));
    setCandidates((current) =>
      current.map((item) =>
        item.candidateId === candidate.candidateId ? { ...item, outreachStatus: "drafted" as const } : item,
      ),
    );
    setVisibleCandidates((current) =>
      current.map((item) =>
        item.candidateId === candidate.candidateId ? { ...item, outreachStatus: "drafted" as const } : item,
      ),
    );
  };

  const handleConfirmDraft = async (draft: string) => {
    if (!selectedCandidate) return;
    setEmailDraft(draft);
    setDraftConfirmOpen(false);
    setToast("草稿已确认，等待真实发送接口接入");
  };

  const handleApproveHumanGate = async (draft: string) => {
    if (!humanGateRequest) return;
    setHumanGateBusy(true);
    try {
      await confirmTask(humanGateRequest.taskId, "approve", {
        draft,
        candidateName: humanGateRequest.candidateName,
      });
      handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
      setHumanGateRequest(null);
      setToast("已批准，任务继续执行");
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
      await confirmTask(humanGateRequest.taskId, "reject", {
        draft: humanGateRequest.draft,
        candidateName: humanGateRequest.candidateName,
      });
      handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
      setHumanGateRequest(null);
      setToast("已拒绝，任务继续处理人工反馈");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "人工拒绝失败");
    } finally {
      setHumanGateBusy(false);
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
            {new Date(project.updatedAt).toLocaleString("zh-CN")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleRunAllJobs}
            disabled={!jobs.length}
            className="h-[38px] rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
          >
            运行全部岗位
          </button>
          <button
            type="button"
            onClick={handleRunWeeklyReport}
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

      <section className="my-5 rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="grid grid-cols-6 items-start">
          {steps.map((step, index) => {
            const state = workflowStatus(index, jobs, candidates, taskSnapshot?.status ?? null);
            const isDone = state === "done";
            const isCurrent = state === "current";
            return (
              <div key={step} className="relative flex flex-col items-center gap-2">
                {index > 0 ? (
                  <div
                    className={[
                      "absolute right-1/2 top-[14px] h-0.5 w-full",
                      workflowStatus(index - 1, jobs, candidates, taskSnapshot?.status ?? null) === "done"
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
            runningJobAction={runningJobAction}
            onRunAction={handleRunAction}
            onRefresh={() => loadProjectData(filterCriteria)}
          />
          <CandidateTable
            candidates={visibleCandidates}
            onSendEmail={handleSelectEmailCandidate}
            onRunEvaluation={handleRunCandidateEvaluation}
            evaluatingCandidateId={runningCandidateId}
            hasMore={hasMoreCandidates}
            isLoadingMore={loadingMoreCandidates}
            onLoadMore={handleLoadMoreCandidates}
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
                onClick={handleGenerateSegment}
                className="h-10 w-full rounded-[10px] bg-[#2563EB] text-[14px] font-medium text-white transition hover:bg-[#1D4ED8]"
              >
                生成目标人群
              </button>
            </div>
          </section>

          <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">邮件草稿</h2>
              <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[12px] font-medium text-[#6B7280]">
                前端生成
              </span>
            </div>
            {selectedCandidate ? (
              <div className="mt-4 space-y-3">
                <p className="text-[12px] leading-[18px] text-[#9CA3AF]">草稿为前端辅助生成，发送前需人工确认</p>
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
                    className="h-9 w-full rounded-[9px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] text-[#111827]"
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-[#6B7280]">正文</span>
                  <textarea
                    value={emailDraft}
                    onChange={(event) => setEmailDraft(event.target.value)}
                    rows={7}
                    className="h-40 w-full resize-none rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2 text-[13px] leading-[22px] text-[#111827]"
                  />
                </label>
                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={() => setEmailDraft(buildCandidateEmailDraft(selectedCandidate, jobs.find((job) => job.jobProfileId === selectedCandidate.targetJobProfileId)))}
                    className="h-9 rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151]"
                  >
                    重新生成
                  </button>
                  <button
                    type="button"
                    className="h-9 rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151]"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraftConfirmOpen(true)}
                    className="h-9 rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white"
                  >
                    确认草稿
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-4 rounded-[10px] border border-dashed border-[#E5E7EB] bg-[#F9FAFB] px-4 py-6 text-center text-[13px] leading-5 text-[#6B7280]">
                从候选人表点击“发邮件”后，这里会生成辅助草稿。
              </p>
            )}
          </section>

          <WeeklyReportCard report={project.weeklyReport} onGenerate={handleRunWeeklyReport} />
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
            />
          </div>
        </div>
      ) : null}

      <HumanConfirmModal
        open={Boolean(humanGateRequest) || draftConfirmOpen}
        busy={humanGateBusy}
        context={
          humanGateRequest?.context ??
          (selectedCandidate ? `请确认候选人 ${selectedCandidate.name} 的邮件草稿。` : "")
        }
        draft={humanGateRequest?.draft ?? emailDraft}
        candidateName={humanGateRequest?.candidateName ?? selectedCandidate?.name}
        onApprove={humanGateRequest ? handleApproveHumanGate : handleConfirmDraft}
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
