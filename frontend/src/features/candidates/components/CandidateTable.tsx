import type { Candidate } from "../types";

type CandidateTableProps = {
  candidates: Candidate[];
  onSendEmail: (candidate: Candidate) => void;
  onRunEvaluation?: (candidate: Candidate) => void;
  evaluatingCandidateId?: string | null;
};

const statusTone: Record<Candidate["stepStatus"], string> = {
  pending: "bg-slate-100 text-slate-500",
  processing: "bg-blue-50 text-blue-700",
  awaiting_human: "bg-amber-50 text-amber-700",
  done: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-700",
  cancelled: "bg-slate-100 text-slate-500",
};

const outreachLabel: Record<Candidate["outreachStatus"], string> = {
  not_sent: "未发送",
  drafted: "已起草",
  sent: "已发送",
};

const pipelineLabel: Record<string, string> = {
  pending: "待处理",
  processing: "处理中",
  awaiting_human: "待确认",
  done: "已完成",
  error: "异常",
  cancelled: "已取消",
  sourced: "已入库",
  screening: "初筛中",
  technical_interview: "技术面",
  offer: "Offer",
  offer_review: "Offer 复核",
  pending_outreach: "待触达",
};

function statusLabel(candidate: Candidate) {
  const status = candidate.pipelineStatus || candidate.stepStatus;
  return pipelineLabel[status] || status;
}

export function CandidateTable({
  candidates,
  onSendEmail,
  onRunEvaluation,
  evaluatingCandidateId = null,
}: CandidateTableProps) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-950">候选人名单</h2>
        <span className="text-sm text-slate-500">{candidates.length} 人</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-5 py-3 text-left font-semibold text-slate-600">姓名</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">当前公司</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">城市</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">匹配分</th>
              <th className="px-4 py-3 text-left font-semibold text-slate-600">状态</th>
              <th className="px-4 py-3 text-right font-semibold text-slate-600">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {candidates.map((candidate) => (
              <tr key={candidate.candidateId}>
                <td className="px-5 py-4">
                  <div className="font-semibold text-slate-950">{candidate.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{candidate.title}</div>
                </td>
                <td className="px-4 py-4 text-slate-700">{candidate.currentCompany ?? "未知"}</td>
                <td className="px-4 py-4 text-slate-600">{candidate.city ?? "-"}</td>
                <td className="px-4 py-4">
                  <span className="font-semibold text-slate-950">{candidate.matchScore}</span>
                </td>
                <td className="px-4 py-4">
                  <div className="flex flex-wrap gap-2">
                    <span className={`rounded-md px-2 py-1 text-xs font-medium ${statusTone[candidate.stepStatus]}`}>
                      {statusLabel(candidate)}
                    </span>
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
                      {outreachLabel[candidate.outreachStatus]}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-4 text-right">
                  <div className="flex flex-wrap justify-end gap-2">
                    {onRunEvaluation ? (
                      <button
                        type="button"
                        onClick={() => onRunEvaluation(candidate)}
                        disabled={evaluatingCandidateId === candidate.candidateId}
                        className="rounded-md border border-slate-300 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {evaluatingCandidateId === candidate.candidateId ? "评估中" : "Agent 评估"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => onSendEmail(candidate)}
                      className="rounded-md border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                    >
                      发邮件
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {candidates.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-500">
                  暂无符合条件的候选人
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
