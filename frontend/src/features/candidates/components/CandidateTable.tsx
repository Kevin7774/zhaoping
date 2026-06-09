import type { Candidate } from "../types";

type CandidateTableProps = {
  candidates: Candidate[];
  onSendEmail: (candidate: Candidate) => void;
  onConfirmCompliance?: (candidate: Candidate) => void;
  onRunEvaluation?: (candidate: Candidate) => void;
  canRunEvaluation?: boolean;
  evaluationDisabledReason?: string;
  evaluatingCandidateId?: string | null;
  confirmingComplianceCandidateId?: string | null;
  hasMore?: boolean;
  isLoadingMore?: boolean;
  loadedCount?: number;
  onLoadMore?: () => void;
  totalCount?: number | null;
};

const statusTone: Record<Candidate["stepStatus"], string> = {
  pending: "bg-[#F3F4F6] text-[#6B7280]",
  processing: "bg-[#EFF6FF] text-[#2563EB]",
  awaiting_human: "bg-[#FFFBEB] text-[#F59E0B]",
  done: "bg-[#ECFDF3] text-[#16A34A]",
  error: "bg-[#FEF2F2] text-[#EF4444]",
  cancelled: "bg-[#F3F4F6] text-[#6B7280]",
};

const pipelineLabel: Record<string, string> = {
  pending: "等待中",
  processing: "评估中",
  awaiting_human: "待确认",
  done: "已评估",
  error: "失败",
  cancelled: "已取消",
  sourced: "已入库",
  pending_compliance_review: "合规待审",
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

function scoreTone(score: number | null) {
  if (score === null) return "text-[#6B7280]";
  if (score >= 85) return "text-[#2563EB]";
  if (score < 70) return "text-[#6B7280]";
  return "text-[#111827]";
}

function avatarText(name: string) {
  const normalized = name.trim();
  if (!normalized) return "候";
  return normalized.slice(0, 1).toUpperCase();
}

export function CandidateTable({
  candidates,
  onSendEmail,
  onConfirmCompliance,
  onRunEvaluation,
  canRunEvaluation = true,
  evaluationDisabledReason,
  evaluatingCandidateId = null,
  confirmingComplianceCandidateId = null,
  hasMore = false,
  isLoadingMore = false,
  loadedCount,
  onLoadMore,
  totalCount = null,
}: CandidateTableProps) {
  const visibleCount = candidates.length;
  const normalizedLoadedCount = loadedCount ?? visibleCount;
  const countSummary =
    typeof totalCount === "number"
      ? `已显示 ${visibleCount} · 已加载 ${normalizedLoadedCount} / 共 ${totalCount} 条关联`
      : `已显示 ${visibleCount}`;

  return (
    <section className="overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="flex items-center justify-between border-b border-[#EEF2F7] px-5 py-4">
        <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">候选人名单</h2>
        <button type="button" className="text-[13px] font-medium text-[#2563EB]">
          查看全部
        </button>
      </div>

      {candidates.length === 0 ? (
        <div className="px-5 py-10 text-center text-[14px] text-[#6B7280]">暂无候选人，运行找候选人后会显示在这里</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[768px] w-full text-[13px] leading-5">
            <thead className="h-11 bg-[#F9FAFB] text-left text-[12px] font-semibold text-[#6B7280]">
              <tr>
                <th className="w-[178px] px-5">姓名</th>
                <th className="w-[128px] px-2">当前公司</th>
                <th className="w-[142px] px-2">目标岗位</th>
                <th className="w-[70px] px-2">匹配分</th>
                <th className="w-[84px] px-2">状态</th>
                <th className="w-[166px] px-4 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EEF2F7]">
              {candidates.map((candidate) => {
                const hasEmail = Boolean(candidate.email);
                const compliancePending = candidate.pipelineStatus === "pending_compliance_review";
                const isEvaluating = evaluatingCandidateId === candidate.candidateId;
                const isConfirmingCompliance = confirmingComplianceCandidateId === candidate.candidateId;
                const evaluationDisabled = isEvaluating || !canRunEvaluation;
                const draftDisabled = !hasEmail || compliancePending;
                const draftDisabledTitle = compliancePending
                  ? "候选人联系方式待合规确认"
                  : hasEmail
                    ? undefined
                    : "候选人无邮箱";

                return (
                  <tr key={`${candidate.targetJobProfileId}-${candidate.candidateId}`} className="h-[58px]">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[12px] font-semibold text-[#2563EB]">
                          {avatarText(candidate.name)}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-[#111827]">{candidate.name || "—"}</div>
                          <div className="truncate text-[12px] text-[#9CA3AF]">{candidate.title || "—"}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-2 py-3 text-[#374151]">{candidate.currentCompany ?? "—"}</td>
                    <td className="px-2 py-3 text-[#374151]">{candidate.title || "—"}</td>
                    <td className={`px-2 py-3 text-[15px] font-bold ${scoreTone(candidate.matchScore)}`}>
                      {candidate.matchScore ?? "—"}
                    </td>
                    <td className="px-2 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px] ${statusTone[candidate.stepStatus]}`}>
                        {statusLabel(candidate)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1.5">
                        {onRunEvaluation ? (
                          <button
                            type="button"
                            onClick={() => onRunEvaluation(candidate)}
                            disabled={evaluationDisabled}
                            title={!canRunEvaluation ? evaluationDisabledReason : undefined}
                            className="h-[30px] whitespace-nowrap rounded-lg border border-[#E5E7EB] bg-white px-2 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isEvaluating ? "评估中" : "候选人评估"}
                          </button>
                        ) : null}
                        {compliancePending && onConfirmCompliance ? (
                          <button
                            type="button"
                            onClick={() => onConfirmCompliance(candidate)}
                            disabled={isConfirmingCompliance}
                            className="h-[30px] whitespace-nowrap rounded-lg border border-[#F59E0B] bg-[#FFFBEB] px-2 text-[12px] font-medium text-[#92400E] transition hover:bg-[#FEF3C7] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isConfirmingCompliance ? "确认中" : "确认来源"}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="h-[30px] whitespace-nowrap rounded-lg border border-[#E5E7EB] bg-white px-2 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
                        >
                          查看
                        </button>
                        <button
                          type="button"
                          disabled={draftDisabled}
                          title={draftDisabledTitle}
                          onClick={() => {
                            if (!draftDisabled) onSendEmail(candidate);
                          }}
                          className="h-[30px] whitespace-nowrap rounded-lg bg-[#2563EB] px-2 text-[12px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          生成草稿
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#EEF2F7] bg-[#FCFCFD] px-5 py-3">
            <div className="text-[12px] font-medium text-[#6B7280]">{countSummary}</div>
            {hasMore ? (
              <button
                type="button"
                onClick={onLoadMore}
                disabled={isLoadingMore}
                className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-4 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoadingMore ? "加载中..." : "加载更多"}
              </button>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
