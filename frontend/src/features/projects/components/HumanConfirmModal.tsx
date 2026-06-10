import { useEffect, useId, useState } from "react";

import type { LeadPreview } from "../humanGate";

type HumanConfirmModalProps = {
  open: boolean;
  busy: boolean;
  context: string;
  draft: string;
  candidateName?: string;
  requiresLeadPreview?: boolean;
  leadPreview?: LeadPreview;
  onApprove: (draft: string, decision: "approve" | "edit") => void;
  onReject: () => void;
  onClose: () => void;
};

export function HumanConfirmModal({
  open,
  busy,
  context,
  draft,
  candidateName,
  requiresLeadPreview,
  leadPreview,
  onApprove,
  onReject,
  onClose,
}: HumanConfirmModalProps) {
  const textareaId = useId();
  const [draftText, setDraftText] = useState(draft);

  useEffect(() => {
    if (open) setDraftText(draft);
  }, [draft, open]);

  if (!open) return null;
  const missingRequiredLeadPreview = Boolean(requiresLeadPreview && !leadPreview);
  const approveDisabled = busy || missingRequiredLeadPreview;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#111827]/45 px-4 py-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="human-confirm-title"
        className="w-full max-w-[720px] overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-2xl"
      >
        <div className="border-b border-[#EEF2F7] px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-normal text-[#F59E0B]">Human Gate</div>
              <h2 id="human-confirm-title" className="mt-1 text-[18px] font-bold text-[#111827]">
                人工确认
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="h-[34px] rounded-[10px] border border-[#E5E7EB] bg-white px-3 text-[13px] font-medium text-[#6B7280] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-60"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="space-y-4 px-6 py-6">
          <div className="rounded-[12px] border border-[#FDE68A] bg-[#FFFBEB] px-4 py-3">
            <div className="text-[14px] font-semibold text-[#111827]">{candidateName || "AI Agent 请求确认"}</div>
            <p className="mt-1 text-[13px] leading-5 text-[#92400E]">{context}</p>
          </div>

          {requiresLeadPreview ? (
            <section className="rounded-[12px] border border-[#D1D5DB] bg-[#F9FAFB] px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-[14px] font-semibold text-[#111827]">即将入库的候选线索</h3>
                {leadPreview ? (
                  <span className="text-[12px] text-[#6B7280]">
                    {leadPreview.totalCount} 条{leadPreview.omittedCount > 0 ? `，另有 ${leadPreview.omittedCount} 条未展示` : ""}
                  </span>
                ) : null}
              </div>
              {leadPreview ? (
                <div className="mt-3 space-y-2">
                  {leadPreview.leads.map((lead, index) => (
                    <article key={`${lead.sourceUrl || lead.name || index}-${index}`} className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-[#111827]">
                        <span>{lead.name || "Unknown Candidate"}</span>
                        <span className="text-[12px] font-medium text-[#6B7280]">{lead.sourcePlatform || "unknown_source"}</span>
                        {lead.confidence !== undefined ? (
                          <span className="text-[12px] font-medium text-[#047857]">{Math.round(lead.confidence * 100)}%</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[12px] leading-[18px] text-[#4B5563]">{lead.evidenceSummary || "暂无证据摘要"}</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[#6B7280]">
                        <span>岗位：{lead.matchedJob || "未匹配"}</span>
                        <span>动作：{lead.ingestionAction || "unknown"}</span>
                        <span>合规：{lead.complianceStatus || "unknown"}</span>
                      </div>
                      {lead.sourceUrl ? (
                        <div className="mt-1 truncate text-[11px] text-[#6B7280]">{lead.sourceUrl}</div>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[13px] leading-5 text-[#B45309]">缺少候选线索预览，无法确认入库。</p>
              )}
            </section>
          ) : null}

          <label htmlFor={textareaId} className="block text-[13px] font-semibold text-[#374151]">
            草稿正文
          </label>
          <textarea
            id={textareaId}
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
            rows={10}
            className="w-full resize-y rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2 text-[13px] leading-[22px] text-[#111827] outline-none transition focus:border-[#BFDBFE] focus:ring-2 focus:ring-[#EFF6FF]"
          />
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-[#EEF2F7] bg-[#F9FAFB] px-6 py-4 sm:flex-row sm:items-center sm:justify-end">
          {requiresLeadPreview ? (
            <p className="text-[12px] leading-5 text-[#6B7280] sm:mr-auto">确认后将把这些线索写入项目候选人库。</p>
          ) : null}
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="h-[38px] rounded-[10px] bg-[#EF4444] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#DC2626] disabled:cursor-not-allowed disabled:opacity-60"
          >
            拒绝
          </button>
          <button
            type="button"
            onClick={() => onApprove(draftText, "edit")}
            disabled={approveDisabled}
            className="h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-60"
          >
            编辑后通过
          </button>
          <button
            type="button"
            onClick={() => onApprove(draftText, "approve")}
            disabled={approveDisabled}
            className="h-[38px] rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-60"
          >
            通过
          </button>
        </div>
      </section>
    </div>
  );
}
