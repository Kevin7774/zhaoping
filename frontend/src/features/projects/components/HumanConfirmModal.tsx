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
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/45 px-4 py-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="human-confirm-title"
        className="w-full max-w-2xl overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl"
      >
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-normal text-amber-700">Human Gate</div>
              <h2 id="human-confirm-title" className="mt-1 text-lg font-semibold text-slate-950">
                人工确认
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="space-y-4 px-5 py-5">
          <div className="rounded-md border border-amber-100 bg-amber-50 px-4 py-3">
            <div className="text-sm font-semibold text-amber-900">{candidateName || "AI Agent 请求确认"}</div>
            <p className="mt-1 text-sm leading-6 text-amber-800">{context}</p>
          </div>

          <label htmlFor={textareaId} className="block text-sm font-semibold text-slate-700">
            草稿正文
          </label>
          <textarea
            id={textareaId}
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
            rows={10}
            className="w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-900 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 bg-slate-50 px-5 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="rounded-md border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            拒绝 Reject
          </button>
          <button
            type="button"
            onClick={() => onApprove(draftText)}
            disabled={busy}
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            修改并批准 Approve
          </button>
        </div>
      </section>
    </div>
  );
}
