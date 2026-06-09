import { useEffect, useId, useState } from "react";

type HumanConfirmModalProps = {
  open: boolean;
  busy: boolean;
  context: string;
  draft: string;
  candidateName?: string;
  onApprove: (draft: string) => void;
  onReject: () => void;
  onClose: () => void;
};

export function HumanConfirmModal({
  open,
  busy,
  context,
  draft,
  candidateName,
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

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#111827]/45 px-4 py-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="human-confirm-title"
        className="w-full max-w-[560px] overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-2xl"
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

        <div className="flex flex-col-reverse gap-3 border-t border-[#EEF2F7] bg-[#F9FAFB] px-6 py-4 sm:flex-row sm:justify-end">
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
            onClick={() => onApprove(draftText)}
            disabled={busy}
            className="h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-60"
          >
            编辑后通过
          </button>
          <button
            type="button"
            onClick={() => onApprove(draftText)}
            disabled={busy}
            className="h-[38px] rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-60"
          >
            通过
          </button>
        </div>
      </section>
    </div>
  );
}
