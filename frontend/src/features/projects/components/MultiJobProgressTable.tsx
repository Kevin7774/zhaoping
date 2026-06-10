import type { JobProfile, StepStatus } from "../../jobs/types";
import type { CandidateSearchSchedule, RunProjectScenarioAction } from "../api";

type MultiJobProgressTableProps = {
  jobs: JobProfile[];
  candidateCounts: Record<string, number>;
  actionAvailability?: Partial<Record<RunProjectScenarioAction, { enabled: boolean; reason?: string }>>;
  matchAvailability?: { enabled: boolean; reason?: string };
  schedules?: CandidateSearchSchedule[];
  scheduleBusyJobId?: string | null;
  canUpdateSchedule?: boolean;
  scheduleDisabledReason?: string;
  runningJobAction?: {
    jobProfileId: string;
    action: RunProjectScenarioAction;
  } | null;
  matchingJobId?: string | null;
  onRunAction?: (job: JobProfile, action: RunProjectScenarioAction) => void;
  onRunMatch?: (job: JobProfile) => void;
  onToggleSchedule?: (job: JobProfile, enabled: boolean) => void;
  onScheduleIntervalChange?: (job: JobProfile, intervalMinutes: number) => void;
  onRefresh?: () => void;
};

type PrimaryJobAction = {
  action: RunProjectScenarioAction;
  label: string;
  runningLabel: string;
  reason: string;
};

const statusTone: Record<StepStatus, string> = {
  pending: "bg-[#F3F4F6] text-[#6B7280]",
  processing: "bg-[#EFF6FF] text-[#2563EB]",
  awaiting_human: "bg-[#FFFBEB] text-[#F59E0B]",
  done: "bg-[#ECFDF3] text-[#16A34A]",
  error: "bg-[#FEF2F2] text-[#EF4444]",
  cancelled: "bg-[#F3F4F6] text-[#6B7280]",
};

const statusLabel: Record<StepStatus, string> = {
  pending: "等待中",
  processing: "进行中",
  awaiting_human: "待确认",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
};

const secondaryActionCopy: Record<RunProjectScenarioAction, { label: string; runningLabel: string }> = {
  job_analysis: { label: "岗位分析", runningLabel: "分析中" },
  find_candidates: { label: "找候选人", runningLabel: "搜索中" },
  candidate_evaluation: { label: "候选人评估", runningLabel: "评估中" },
};

function actionStatus(job: JobProfile, key: "analysis" | "sourcing" | "evaluation" | "outreach") {
  if (key === "analysis") return job.pipelineStatus ?? "processing";
  if (key === "sourcing") return job.funnel.find((stage) => stage.key === "sourcing")?.status ?? "pending";
  if (key === "evaluation") return job.funnel.find((stage) => stage.key === "evaluation")?.status ?? "pending";
  if (key === "outreach") return job.funnel.find((stage) => stage.key === "offer")?.status ?? "pending";
  return "pending";
}

function MiniStatus({ status }: { status: StepStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px] ${statusTone[status]}`}>
      {statusLabel[status]}
    </span>
  );
}

function candidateTarget(job: JobProfile) {
  return Math.max((job.headcount ?? 1) * 3, 3);
}

function primaryActionForJob(job: JobProfile, linkedCount: number): PrimaryJobAction {
  const target = candidateTarget(job);
  if (job.pipelineStatus === "pending" && linkedCount === 0) {
    return {
      action: "job_analysis",
      label: "岗位分析",
      runningLabel: "分析中",
      reason: "岗位画像还未生成，先明确职责、能力和搜索策略。",
    };
  }
  if (linkedCount < target) {
    return {
      action: "find_candidates",
      label: "找候选人",
      runningLabel: "搜索中",
      reason: `候选人不足：${linkedCount}/${target}，优先补充可评估线索。`,
    };
  }
  return {
    action: "candidate_evaluation",
    label: "候选人评估",
    runningLabel: "评估中",
    reason: "候选人池已具备基础规模，下一步评估匹配度和风险。",
  };
}

function matrixSummary(job: JobProfile, linkedCount: number) {
  const parts = [
    job.seniority,
    ...(job.mustHaveSkills ?? []).slice(0, 2),
    ...(job.targetCompanies ?? []).slice(0, 1),
    ...Object.values(job.searchStrategy ?? {}).slice(0, 1).map((value) => String(value)),
  ].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return `真实后端岗位 · 已关联 ${linkedCount} 人`;
}

function intervalLabel(intervalMinutes: number) {
  if (intervalMinutes === 60) return "每 1 小时";
  if (intervalMinutes === 180) return "每 3 小时";
  if (intervalMinutes === 360) return "每 6 小时";
  if (intervalMinutes === 1440) return "每天";
  return `每 ${intervalMinutes} 分钟`;
}

function isRunningAction(
  runningJobAction: MultiJobProgressTableProps["runningJobAction"],
  job: JobProfile,
  action: RunProjectScenarioAction,
) {
  return runningJobAction?.jobProfileId === job.jobProfileId && runningJobAction.action === action;
}

export function MultiJobProgressTable({
  jobs,
  candidateCounts,
  actionAvailability = {},
  matchAvailability = { enabled: true },
  schedules = [],
  scheduleBusyJobId = null,
  canUpdateSchedule = true,
  scheduleDisabledReason,
  runningJobAction,
  matchingJobId = null,
  onRunAction,
  onRunMatch,
  onToggleSchedule,
  onScheduleIntervalChange,
  onRefresh,
}: MultiJobProgressTableProps) {
  const availabilityFor = (action: RunProjectScenarioAction) => actionAvailability[action] ?? { enabled: true };
  const scheduleByJobId = new Map(schedules.map((schedule) => [schedule.jobId, schedule]));

  return (
    <section className="overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
      <div className="flex items-center justify-between border-b border-[#EEF2F7] px-5 py-4">
        <div>
          <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">岗位工作台</h2>
          <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">每个岗位只突出当前下一步；低频动作收在更多操作里。</p>
        </div>
        <button type="button" onClick={onRefresh} className="text-[13px] font-medium text-[#2563EB]">
          刷新
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="px-5 py-10 text-center text-[14px] text-[#6B7280]">暂无岗位，请先从招聘需求中创建岗位</div>
      ) : (
        <div className="divide-y divide-[#EEF2F7]">
          {jobs.map((job) => {
            const linkedCount = Math.max(candidateCounts[job.jobProfileId] ?? 0, job.candidateCount ?? 0);
            const primaryAction = primaryActionForJob(job, linkedCount);
            const primaryAvailability = availabilityFor(primaryAction.action);
            const primaryRunning = isRunningAction(runningJobAction, job, primaryAction.action);
            const matchRunning = matchingJobId === job.jobProfileId;
            const schedule = scheduleByJobId.get(job.jobProfileId);
            const scheduleEnabled = Boolean(schedule?.enabled);
            const scheduleInterval = schedule?.intervalMinutes ?? 360;
            const scheduleBusy = scheduleBusyJobId === job.jobProfileId;
            const progressItems = [
              { label: "搜索", status: actionStatus(job, "sourcing") },
              { label: "评估", status: actionStatus(job, "evaluation") },
              { label: "邮件", status: actionStatus(job, "outreach") },
            ];

            return (
              <div key={job.jobProfileId} className="grid grid-cols-1 gap-4 px-5 py-4 text-[13px] leading-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(260px,0.9fr)_minmax(220px,0.85fr)] xl:items-start">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="truncate font-semibold text-[#111827]" title={job.roleName}>
                      {job.roleName}
                    </div>
                    <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[11px] font-medium text-[#6B7280]">
                      HC {job.headcount ?? "—"}
                    </span>
                  </div>
                  <div className="mt-1 truncate text-[12px] text-[#9CA3AF]" title={matrixSummary(job, linkedCount)}>
                    {matrixSummary(job, linkedCount)}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {progressItems.map((item) => (
                      <span key={item.label} className="inline-flex items-center gap-1 rounded-[8px] bg-[#F9FAFB] px-1.5 py-1">
                        <span className="text-[11px] text-[#6B7280]">{item.label}</span>
                        <MiniStatus status={item.status} />
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded-[10px] bg-[#F9FAFB] px-3 py-3">
                  <div className="text-[12px] font-semibold text-[#111827]">下一步</div>
                  <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">{primaryAction.reason}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={primaryRunning || !primaryAvailability.enabled}
                      title={!primaryAvailability.enabled ? primaryAvailability.reason : undefined}
                      onClick={() => onRunAction?.(job, primaryAction.action)}
                      className="h-8 rounded-[9px] bg-[#2563EB] px-3 text-[12px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {primaryRunning ? primaryAction.runningLabel : primaryAction.label}
                    </button>
                    <details>
                      <summary
                        role="button"
                        aria-label={`更多操作 ${job.roleName}`}
                        className="cursor-pointer list-none rounded-[9px] border border-[#E5E7EB] bg-white px-3 py-1.5 text-[12px] font-medium text-[#374151] marker:content-none"
                      >
                        更多操作
                      </summary>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(["job_analysis", "find_candidates", "candidate_evaluation"] as const)
                          .filter((action) => action !== primaryAction.action)
                          .map((action) => {
                            const copy = secondaryActionCopy[action];
                            const availability = availabilityFor(action);
                            const running = isRunningAction(runningJobAction, job, action);
                            return (
                              <button
                                key={action}
                                type="button"
                                disabled={running || !availability.enabled}
                                title={!availability.enabled ? availability.reason : undefined}
                                onClick={() => onRunAction?.(job, action)}
                                className="h-8 rounded-[9px] border border-[#E5E7EB] bg-white px-3 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {running ? copy.runningLabel : copy.label}
                              </button>
                            );
                          })}
                        <button
                          type="button"
                          disabled={matchRunning || !matchAvailability.enabled}
                          title={!matchAvailability.enabled ? matchAvailability.reason : undefined}
                          onClick={() => onRunMatch?.(job)}
                          className="h-8 rounded-[9px] border border-[#E5E7EB] bg-white px-3 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {matchRunning ? "匹配中" : "重算匹配分"}
                        </button>
                      </div>
                    </details>
                  </div>
                </div>

                <div className="rounded-[10px] border border-[#EEF2F7] px-3 py-3">
                  <div className="text-[12px] font-semibold text-[#111827]">
                    自动搜索：{scheduleEnabled ? `已开启 · ${intervalLabel(scheduleInterval)}` : "未开启"}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onToggleSchedule?.(job, !scheduleEnabled)}
                      disabled={scheduleBusy || !canUpdateSchedule || !onToggleSchedule}
                      title={!canUpdateSchedule ? scheduleDisabledReason : undefined}
                      aria-label={`${scheduleEnabled ? "关闭搜索计划" : "开启搜索计划"} ${job.roleName}`}
                      className={
                        scheduleEnabled
                          ? "h-8 rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[12px] font-medium text-[#374151] disabled:cursor-not-allowed disabled:opacity-50"
                          : "h-8 rounded-[9px] bg-[#2563EB] px-3 text-[12px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                      }
                    >
                      {scheduleBusy ? "保存中" : scheduleEnabled ? "关闭计划" : "开启计划"}
                    </button>
                    <select
                      value={scheduleInterval}
                      aria-label={`搜索计划频率 ${job.roleName}`}
                      onChange={(event) => onScheduleIntervalChange?.(job, Number(event.target.value))}
                      disabled={scheduleBusy || !canUpdateSchedule || !onScheduleIntervalChange}
                      className="h-8 min-w-[112px] rounded-[9px] border border-[#E5E7EB] bg-white px-2 text-[12px] text-[#111827] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <option value={60}>每 1 小时</option>
                      <option value={180}>每 3 小时</option>
                      <option value={360}>每 6 小时</option>
                      <option value={1440}>每天</option>
                    </select>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
