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
    <div className="fixed inset-0 z-[70] flex items-start justify-center overflow-y-auto bg-[#111827]/45 px-3 py-4 backdrop-blur-[2px] sm:items-center sm:px-4 sm:py-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="human-confirm-title"
        className="flex max-h-[calc(100dvh-2rem)] w-full max-w-[720px] flex-col overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_24px_64px_-16px_rgba(16,24,40,0.28)]"
      >
        <div className="border-b border-[#EEF2F7] bg-[#F9FAFB]/60 px-6 py-5">
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

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
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
                  {leadPreview.searchTrace ? (
                    <div className="rounded-[10px] border border-[#DBEAFE] bg-[#EFF6FF] px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h4 className="text-[13px] font-semibold text-[#1E3A8A]">Top-down 搜索链路</h4>
                        <span className="text-[11px] font-medium text-[#1D4ED8]">
                          {leadPreview.searchTrace.resultCount} 总命中 / {leadPreview.searchTrace.errors.length} 异常
                        </span>
                      </div>
                      {leadPreview.searchTrace.query ? (
                        <p className="mt-1 truncate text-[11px] text-[#1E40AF]">Query：{leadPreview.searchTrace.query}</p>
                      ) : null}
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {leadPreview.searchTrace.researchLayers.map((layer) => (
                          <div key={layer.id} className="rounded-[8px] border border-[#BFDBFE] bg-white px-2.5 py-2">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[12px] font-semibold text-[#111827]">{layer.nameZh}</span>
                              <span className="whitespace-nowrap text-[11px] text-[#2563EB]">
                                {layer.resultCount} 命中 / {layer.errorCount} 异常
                              </span>
                            </div>
                            {layer.purpose ? (
                              <p className="mt-1 text-[11px] leading-[16px] text-[#4B5563]">{layer.purpose}</p>
                            ) : null}
                            {layer.services.length ? (
                              <div className="mt-1.5 flex flex-wrap gap-1">
                                {layer.services.map((service) => (
                                  <span key={`${layer.id}-${service}`} className="rounded-[6px] bg-[#F3F4F6] px-1.5 py-0.5 text-[10px] text-[#374151]">
                                    {service}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                      {leadPreview.searchTrace.errors.length ? (
                        <div className="mt-2 space-y-1">
                          {leadPreview.searchTrace.errors.slice(0, 4).map((error, index) => (
                            <div key={`${error.service || "unknown"}-${index}`} className="text-[11px] leading-[16px] text-[#B45309]">
                              {error.service || "unknown"}: {error.reason || "unknown_error"}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {leadPreview.leads.map((lead, index) => (
                    <article key={`${lead.sourceUrl || lead.name || index}-${index}`} className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-[#111827]">
                        <span>{lead.name || "Unknown Candidate"}</span>
                        <span className="text-[12px] font-medium text-[#6B7280]">{lead.sourcePlatform || "unknown_source"}</span>
                        {lead.confidence !== undefined ? (
                          <span className="text-[12px] font-medium text-[#047857]">{Math.round(lead.confidence * 100)}%</span>
                        ) : null}
                        {lead.githubScore !== undefined ? (
                          <span className="text-[12px] font-medium text-[#1D4ED8]">GitHub {Math.round(lead.githubScore)}</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[12px] leading-[18px] text-[#4B5563]">{lead.evidenceSummary || "暂无证据摘要"}</p>
                      {lead.representativeRepositories?.length ? (
                        <div className="mt-2 space-y-1.5 rounded-[8px] border border-[#E5E7EB] bg-[#F9FAFB] px-2.5 py-2">
                          {lead.representativeRepositories.slice(0, 2).map((repo, repoIndex) => (
                            <div key={`${repo.fullName || repo.url || repoIndex}-${repoIndex}`}>
                              <div className="truncate text-[12px] font-semibold text-[#111827]">{repo.fullName || repo.url}</div>
                              <div className="mt-0.5 text-[11px] text-[#6B7280]">
                                {repo.language || "unknown"} · {repo.stars ?? 0} stars · {repo.forks ?? 0} forks
                              </div>
                              {repo.topics.length ? (
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {repo.topics.slice(0, 4).map((topic) => (
                                    <span key={`${repo.fullName || repo.url}-${topic}`} className="rounded-[6px] bg-white px-1.5 py-0.5 text-[10px] text-[#4B5563]">
                                      {topic}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {lead.repositoryEvidence?.length ? (
                        <div className="mt-2 space-y-1">
                          {lead.repositoryEvidence.slice(0, 2).map((evidence, evidenceIndex) => (
                            <div key={`${evidence.title || evidence.url || evidenceIndex}-${evidenceIndex}`} className="rounded-[8px] bg-[#EFF6FF] px-2.5 py-1.5">
                              {evidence.title ? <div className="truncate text-[11px] font-medium text-[#1E3A8A]">{evidence.title}</div> : null}
                              {evidence.snippet ? <div className="mt-0.5 text-[11px] leading-[16px] text-[#1E40AF]">{evidence.snippet}</div> : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
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

        <div className="shrink-0 flex flex-col-reverse gap-3 border-t border-[#EEF2F7] bg-[#F9FAFB] px-4 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6">
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
