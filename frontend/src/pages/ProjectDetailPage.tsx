import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { CandidateTable } from "../features/candidates/components/CandidateTable";
import type { Candidate } from "../features/candidates/types";
import type { JobProfile } from "../features/jobs/types";
import {
  confirmTask,
  getProject,
  getProjectCandidates,
  getProjectJobs,
  getTask,
  runCandidateEvaluation,
  runProjectScenario,
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
  markCandidateEmailSent,
  type FilterCriteria,
} from "../features/projects/state";
import { useTaskStream } from "../shared/hooks/useTaskStream";

type LoadingState = "idle" | "loading" | "ready" | "error";

const DEFAULT_PROJECT_ID = "project_2026_ai_team";

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
    awaitingHuman: candidates.filter((candidate) => candidate.stepStatus === "awaiting_human").length,
    averageMatchScore: candidates.length
      ? Math.round(candidates.reduce((sum, candidate) => sum + candidate.matchScore, 0) / candidates.length)
      : 0,
  };
}

export function ProjectDetailPage() {
  const { projectId: routeProjectId } = useParams();
  const projectId = routeProjectId || DEFAULT_PROJECT_ID;
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [jobs, setJobs] = useState<JobProfile[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [visibleCandidates, setVisibleCandidates] = useState<Candidate[]>([]);
  const [filterCriteria, setFilterCriteria] = useState<FilterCriteria>(defaultFilterCriteria);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [emailDraft, setEmailDraft] = useState("");
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

  const loadProjectData = useCallback(
    async (criteria: FilterCriteria) => {
      setLoadingState((current) => (current === "idle" ? "loading" : current));
      setLoadError(null);

      try {
        const [projectData, jobsData, candidatesData] = await Promise.all([
          getProject(projectId),
          getProjectJobs(projectId),
          getProjectCandidates(projectId),
        ]);

        setProject(projectData);
        setJobs(jobsData);
        setCandidates(candidatesData);
        setVisibleCandidates(filterCandidates(candidatesData, criteria));
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
    setHumanGateRequest(null);
    setRunningCandidateId(null);
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
    setToast("AI Agent 等待人工确认");
  }, [activeTaskId, events]);

  const projectSummary = useMemo(() => summaryFrom(jobs, candidates), [jobs, candidates]);
  const jobCandidateCounts = useMemo(() => candidateCounts(candidates), [candidates]);

  const handleGenerateSegment = () => {
    const filtered = filterCandidates(candidates, filterCriteria);
    setVisibleCandidates(filtered);
    setToast(`已生成目标人群：${filtered.length} 人`);
  };

  const handleRunAction = async (job: JobProfile, action: RunProjectScenarioAction) => {
    setRunningJobAction({ jobProfileId: job.jobProfileId, action });
    setRunningCandidateId(null);
    setToast(action === "find_candidates" ? "正在启动人才地图任务" : "正在启动候选人评估任务");

    try {
      const created = await runProjectScenario(projectId, job, action);
      setActiveTaskId(created.task_id);
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
      getTask(created.task_id).catch(() => null);
    } catch (error) {
      setRunningCandidateId(null);
      setToast(error instanceof Error ? error.message : "候选人评估任务启动失败");
    }
  };

  const handleSelectEmailCandidate = (candidate: Candidate) => {
    const job = jobs.find((item) => item.jobProfileId === candidate.targetJobProfileId);
    setSelectedCandidate({ ...candidate, outreachStatus: "drafted" });
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

  const handleConfirmSend = async () => {
    if (!selectedCandidate) return;

    const canConfirmTask = Boolean(activeTaskId && taskSnapshot?.status === "awaiting_human");
    try {
      if (activeTaskId && canConfirmTask) {
        await confirmTask(activeTaskId, "approve", {
          draft: emailDraft,
          candidateId: selectedCandidate.candidateId,
        });
      }

      setCandidates((current) => markCandidateEmailSent(current, selectedCandidate.candidateId));
      setVisibleCandidates((current) => markCandidateEmailSent(current, selectedCandidate.candidateId));
      setSelectedCandidate({ ...selectedCandidate, outreachStatus: "sent" });
      setToast(canConfirmTask ? "已确认任务并标记邮件发送" : "邮件发送成功（本地演示）");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "邮件确认失败");
    }
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
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-sm text-slate-600 shadow-sm">
        正在加载项目数据...
      </div>
    );
  }

  if (loadingState === "error" || !project) {
    return (
      <div className="rounded-lg border border-red-100 bg-red-50 p-8 text-sm text-red-700 shadow-sm">
        {loadError || "项目数据加载失败"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-end">
        <div>
          <div className="text-sm font-medium text-blue-700">Project</div>
          <h1 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">{project.name}</h1>
          <div className="mt-2 flex flex-wrap gap-2 text-sm text-slate-500">
            <span>Owner: {project.owner}</span>
            <span>Updated: {new Date(project.updatedAt).toLocaleString("zh-CN")}</span>
          </div>
        </div>
        <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700">
          真实项目数据 + Live Agent 任务流
        </div>
      </section>

      <ProjectSummaryCards {...projectSummary} />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_380px]">
        <div className="space-y-6">
          <MultiJobProgressTable
            jobs={jobs}
            candidateCounts={jobCandidateCounts}
            runningJobAction={runningJobAction}
            onRunAction={handleRunAction}
          />
          <CandidateTable
            candidates={visibleCandidates}
            onSendEmail={handleSelectEmailCandidate}
            onRunEvaluation={handleRunCandidateEvaluation}
            evaluatingCandidateId={runningCandidateId}
          />
        </div>

        <div className="space-y-6">
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">人群筛选</h2>
            <div className="mt-4 space-y-4">
              <label className="block text-sm font-medium text-slate-600">
                岗位
                <select
                  value={filterCriteria.jobProfileId}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, jobProfileId: event.target.value }))}
                  className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="all">全部岗位</option>
                  {jobs.map((job) => (
                    <option key={job.jobProfileId} value={job.jobProfileId}>
                      {job.roleName}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-medium text-slate-600">
                最低匹配分
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={filterCriteria.minScore}
                  onChange={(event) =>
                    setFilterCriteria((current) => ({ ...current, minScore: Number(event.target.value) || 0 }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                />
              </label>
              <label className="block text-sm font-medium text-slate-600">
                城市
                <input
                  value={filterCriteria.city}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, city: event.target.value }))}
                  className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                  placeholder="上海 / 北京 / 深圳"
                />
              </label>
              <label className="block text-sm font-medium text-slate-600">
                关键词
                <input
                  value={filterCriteria.keyword}
                  onChange={(event) => setFilterCriteria((current) => ({ ...current, keyword: event.target.value }))}
                  className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                  placeholder="VLA / DataOps"
                />
              </label>
              <button
                type="button"
                onClick={handleGenerateSegment}
                className="w-full rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800"
              >
                生成目标人群
              </button>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">邮件草稿</h2>
            {selectedCandidate ? (
              <div className="mt-4 space-y-3">
                <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  收件人：{selectedCandidate.name} · {selectedCandidate.currentCompany}
                </div>
                <textarea
                  value={emailDraft}
                  onChange={(event) => setEmailDraft(event.target.value)}
                  rows={8}
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-900"
                />
                <button
                  type="button"
                  onClick={handleConfirmSend}
                  className="w-full rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  确认发送
                </button>
              </div>
            ) : (
              <p className="mt-4 text-sm leading-6 text-slate-500">从候选人表格点击“发邮件”后，这里会生成本地草稿。</p>
            )}
          </section>

          <WeeklyReportCard report={project.weeklyReport} />
        </div>
      </section>

      <LiveTaskSummary
        taskId={activeTaskId}
        events={events}
        taskSnapshot={taskSnapshot}
        connectionState={connectionState}
        error={streamError}
      />

      <HumanConfirmModal
        open={Boolean(humanGateRequest)}
        busy={humanGateBusy}
        context={humanGateRequest?.context ?? ""}
        draft={humanGateRequest?.draft ?? ""}
        candidateName={humanGateRequest?.candidateName}
        onApprove={handleApproveHumanGate}
        onReject={handleRejectHumanGate}
        onClose={() => {
          if (humanGateRequest) handledHumanGateKeysRef.current.add(humanGateRequest.eventKey);
          setHumanGateRequest(null);
        }}
      />

      {toast ? (
        <div className="fixed right-5 top-20 z-50 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-800 shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
