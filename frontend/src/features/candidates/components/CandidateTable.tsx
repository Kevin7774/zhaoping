import { Fragment, useState } from "react";

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
  onViewAll?: () => void;
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

function candidateDisplayKind(candidate: Candidate) {
  const source = candidate.sourcePlatform.toLowerCase();
  const name = candidate.name.toLowerCase();
  const hasPersonSignal = Boolean(candidate.email || candidate.currentCompany);
  const sourceLooksLikeArtifact = /github|repository|repo|paper|arxiv|huggingface|model|project|url/.test(source);
  const nameLooksLikeArtifact = /[-_/]|\$|\d{4,}|transformer|diffusion|repository|equation|dataset|benchmark|model/.test(name);
  return !hasPersonSignal && (sourceLooksLikeArtifact || nameLooksLikeArtifact) ? "线索" : "候选人";
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
  onViewAll,
  totalCount = null,
}: CandidateTableProps) {
  const [expandedCandidateId, setExpandedCandidateId] = useState<string | null>(null);
  const visibleCount = candidates.length;
  const normalizedLoadedCount = loadedCount ?? visibleCount;
  const countSummary =
    typeof totalCount === "number"
      ? `已显示 ${visibleCount} · 已加载 ${normalizedLoadedCount} / 共 ${totalCount} 条关联`
      : `已显示 ${visibleCount}`;

  return (
    <section className="overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
      <div className="flex items-center justify-between border-b border-[#EEF2F7] px-5 py-4">
        <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">候选人与线索</h2>
        <button
          type="button"
          onClick={onViewAll}
          disabled={!onViewAll}
          className="text-[13px] font-medium text-[#2563EB] disabled:cursor-not-allowed disabled:opacity-50"
        >
          查看全部
        </button>
      </div>

      {candidates.length === 0 ? (
        <div className="px-5 py-10 text-center text-[14px] text-[#6B7280]">暂无候选人，运行找候选人后会显示在这里</div>
      ) : (
        <>
          <div className="hidden grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)_70px_82px_minmax(0,192px)] gap-3 bg-[#F9FAFB] px-5 py-3 text-[12px] font-semibold text-[#6B7280] md:grid">
            <div>对象</div>
            <div>目标岗位</div>
            <div>匹配分</div>
            <div>状态</div>
            <div className="text-right">操作</div>
          </div>
          <div className="divide-y divide-[#EEF2F7]">
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
                const displayKind = candidateDisplayKind(candidate);
                const displayKindClass =
                  displayKind === "候选人" ? "bg-[#ECFDF3] text-[#047857]" : "bg-[#EFF6FF] text-[#2563EB]";

                return (
                  <Fragment key={`${candidate.targetJobProfileId}-${candidate.candidateId}`}>
                  <div className="grid grid-cols-1 gap-3 px-5 py-4 text-[13px] leading-5 transition-colors hover:bg-[#FAFBFD] md:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)_70px_82px_minmax(0,192px)] md:items-center">
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[12px] font-semibold text-[#2563EB]">
                          {avatarText(candidate.name)}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-[#111827]">{candidate.name || "—"}</div>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium leading-4 ${displayKindClass}`}>
                              {displayKind}
                            </span>
                            <span className="truncate text-[12px] text-[#9CA3AF]">{candidate.sourcePlatform || "—"}</span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 truncate text-[12px] text-[#6B7280]" title={candidate.currentCompany ?? candidate.title}>
                        {candidate.currentCompany ? `${candidate.currentCompany} · ${candidate.title || "—"}` : candidate.title || "—"}
                      </div>
                    </div>
                    <div className="min-w-0 text-[#374151]">
                      <div className="mb-1 text-[11px] font-medium text-[#9CA3AF] md:hidden">目标岗位</div>
                      <div className="truncate" title={candidate.title}>{candidate.title || "—"}</div>
                    </div>
                    <div className={`text-[15px] font-bold ${scoreTone(candidate.matchScore)}`}>
                      <div className="mb-1 text-[11px] font-medium text-[#9CA3AF] md:hidden">匹配分</div>
                      {candidate.matchScore ?? "—"}
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] font-medium text-[#9CA3AF] md:hidden">状态</div>
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px] ${statusTone[candidate.stepStatus]}`}>
                        {statusLabel(candidate)}
                      </span>
                    </div>
                    <div>
                      <div className="flex flex-wrap justify-start gap-1.5 md:justify-end">
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
                          onClick={() =>
                            setExpandedCandidateId((current) =>
                              current === candidate.candidateId ? null : candidate.candidateId,
                            )
                          }
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
                    </div>
                  </div>
                  {expandedCandidateId === candidate.candidateId ? (
                    <div className="bg-[#FAFBFD] px-5 py-3">
                        <div className="space-y-2 rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2 text-[12px] leading-[18px] text-[#374151]">
                          {candidate.evidence.length ? (
                            candidate.evidence.map((item) => (
                              <div key={`${item.label}-${item.summary}`}>
                                <span className="font-semibold text-[#111827]">{item.label}：</span>
                                {item.summary}
                              </div>
                            ))
                          ) : (
                            <div className="text-[#9CA3AF]">暂无证据摘要</div>
                          )}
                          {candidate.sourceUrl ? (
                            <div className="break-all text-[#2563EB]">{candidate.sourceUrl}</div>
                          ) : null}
                        </div>
                    </div>
                  ) : null}
                  </Fragment>
                );
              })}
          </div>
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
        </>
      )}
    </section>
  );
}
