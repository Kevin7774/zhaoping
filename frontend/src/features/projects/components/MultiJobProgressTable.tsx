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
};

const statusTone: Record<StepStatus, string> = {
  pending: "bg-slate-100 text-slate-500",
  processing: "bg-blue-50 text-blue-700",
  awaiting_human: "bg-amber-50 text-amber-700",
  done: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-700",
  cancelled: "bg-slate-100 text-slate-500",
};

function progressPercent(count: number, target: number) {
  if (target <= 0) return 0;
  return Math.min(100, Math.round((count / target) * 100));
}

function stageAction(stageKey: string): RunProjectScenarioAction | null {
  if (stageKey === "sourcing") return "find_candidates";
  if (stageKey === "evaluation") return "candidate_evaluation";
  return null;
}

function actionLabel(action: RunProjectScenarioAction) {
  return action === "find_candidates" ? "找候选人" : "候选人评估";
}

export function MultiJobProgressTable({
  jobs,
  candidateCounts,
  runningJobAction,
  onRunAction,
}: MultiJobProgressTableProps) {
  const stages = jobs[0]?.funnel ?? [];

  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-950">岗位漏斗进展</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="w-72 px-5 py-3 text-left font-semibold text-slate-600">岗位</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">优先级</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">候选人</th>
              {stages.map((stage) => (
                <th key={stage.key} className="min-w-36 px-4 py-3 text-left font-semibold text-slate-600">
                  {stage.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {jobs.map((job) => (
              <tr key={job.jobProfileId} className="align-top">
                <td className="px-5 py-4">
                  <div className="font-semibold text-slate-950">{job.roleName}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {job.targetCompanyTypes.slice(0, 2).join(" / ")}
                  </div>
                </td>
                <td className="px-4 py-4">
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">
                    {job.priorityLevel}
                  </span>
                </td>
                <td className="px-4 py-4 font-semibold text-slate-700">{candidateCounts[job.jobProfileId] ?? 0}</td>
                {job.funnel.map((stage) => {
                  const percent = progressPercent(stage.count, stage.target);
                  const action = stageAction(stage.key);
                  const isRunning =
                    runningJobAction?.jobProfileId === job.jobProfileId && runningJobAction.action === action;
                  return (
                    <td key={stage.key} className="px-4 py-4">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-800">{stage.count}</span>
                        <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${statusTone[stage.status]}`}>
                          {stage.status}
                        </span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-blue-600" style={{ width: `${percent}%` }} />
                      </div>
                      <div className="mt-1 text-xs text-slate-400">目标 {stage.target}</div>
                      {action ? (
                        <button
                          type="button"
                          disabled={isRunning}
                          onClick={() => onRunAction?.(job, action)}
                          className="mt-3 rounded-md border border-blue-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {isRunning ? "运行中" : `运行${actionLabel(action)}`}
                        </button>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
