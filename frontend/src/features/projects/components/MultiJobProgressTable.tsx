import type { JobProfile, StepStatus } from "../../jobs/types";
import type { RunProjectScenarioAction } from "../api";

type MultiJobProgressTableProps = {
  jobs: JobProfile[];
  candidateCounts: Record<string, number>;
  runningJobAction?: {
    jobProfileId: string;
    action: RunProjectScenarioAction;
  } | null;
  onRunAction?: (job: JobProfile, action: RunProjectScenarioAction) => void;
  onRefresh?: () => void;
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

export function MultiJobProgressTable({
  jobs,
  candidateCounts,
  runningJobAction,
  onRunAction,
  onRefresh,
}: MultiJobProgressTableProps) {
  return (
    <section className="overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="flex items-center justify-between border-b border-[#EEF2F7] px-5 py-4">
        <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">岗位进展</h2>
        <button type="button" onClick={onRefresh} className="text-[13px] font-medium text-[#2563EB]">
          刷新
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="px-5 py-10 text-center text-[14px] text-[#6B7280]">暂无岗位，请先从招聘需求中创建岗位</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[768px] table-fixed w-full text-[13px] leading-5">
            <thead className="h-11 bg-[#F9FAFB] text-left text-[12px] font-semibold text-[#6B7280]">
              <tr>
                <th className="w-[184px] px-5">岗位</th>
                <th className="w-[52px] px-2">人数</th>
                <th className="w-[72px] px-2">分析</th>
                <th className="w-[84px] px-2">找候选人</th>
                <th className="w-[76px] px-2">评估</th>
                <th className="w-[76px] px-2">邮件</th>
                <th className="w-[72px] px-2">状态</th>
                <th className="w-[132px] px-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EEF2F7]">
              {jobs.map((job) => {
                const findCandidatesRunning =
                  runningJobAction?.jobProfileId === job.jobProfileId &&
                  runningJobAction.action === "find_candidates";
                const evaluationRunning =
                  runningJobAction?.jobProfileId === job.jobProfileId &&
                  runningJobAction.action === "candidate_evaluation";

                return (
                  <tr key={job.jobProfileId} className="h-[52px]">
                    <td className="px-5 py-3">
                      <div className="truncate font-semibold text-[#111827]" title={job.roleName}>
                        {job.roleName}
                      </div>
                      <div className="mt-0.5 truncate text-[12px] text-[#9CA3AF]">真实后端岗位 · 已关联 {candidateCounts[job.jobProfileId] ?? 0} 人</div>
                    </td>
                    <td className="px-2 py-3 text-[#374151]">{job.headcount ?? "—"}</td>
                    <td className="px-2 py-3"><MiniStatus status={actionStatus(job, "analysis")} /></td>
                    <td className="px-2 py-3"><MiniStatus status={actionStatus(job, "sourcing")} /></td>
                    <td className="px-2 py-3"><MiniStatus status={actionStatus(job, "evaluation")} /></td>
                    <td className="px-2 py-3"><MiniStatus status={actionStatus(job, "outreach")} /></td>
                    <td className="px-2 py-3"><MiniStatus status={job.pipelineStatus ?? "pending"} /></td>
                    <td className="px-3 py-3">
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          disabled={findCandidatesRunning}
                          onClick={() => onRunAction?.(job, "find_candidates")}
                          className="h-[30px] shrink-0 whitespace-nowrap rounded-lg bg-[#2563EB] px-2.5 text-[12px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {findCandidatesRunning ? "运行中" : "运行"}
                        </button>
                        <button
                          type="button"
                          disabled={evaluationRunning}
                          onClick={() => onRunAction?.(job, "candidate_evaluation")}
                          className="h-[30px] shrink-0 whitespace-nowrap rounded-lg border border-[#E5E7EB] bg-white px-2.5 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {evaluationRunning ? "评估中" : "查看"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
