import type { TaskSnapshot, TaskStreamConnectionState, TaskStreamEvent } from "../../../shared/hooks/useTaskStream";

type LiveTaskSummaryProps = {
  taskId: string | null;
  events: TaskStreamEvent[];
  taskSnapshot: TaskSnapshot | null;
  connectionState: TaskStreamConnectionState;
  error?: string | null;
  usedFallbackPolling?: boolean;
  busy?: boolean;
  onCancel?: () => void;
  onRetry?: () => void;
};

export function LiveTaskSummary({
  taskId,
  events,
  taskSnapshot,
  connectionState,
  error,
  usedFallbackPolling = false,
  busy = false,
  onCancel,
  onRetry,
}: LiveTaskSummaryProps) {
  if (!taskId) return null;

  const latestEvent = events.at(-1);
  const status = taskSnapshot?.status ?? connectionState;
  const isTerminal = ["done", "error", "cancelled"].includes(taskSnapshot?.status ?? "");

  return (
    <aside className="rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="border-b border-[#EEF2F7] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[14px] font-semibold leading-[22px] text-[#111827]">任务实时日志</div>
            <div className="mt-0.5 text-[12px] text-[#9CA3AF]">task_id: {taskId}</div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span className="rounded-full bg-[#EFF6FF] px-2 py-1 text-[12px] font-semibold text-[#2563EB]">{status}</span>
            <span className="text-[11px] text-[#9CA3AF]">{usedFallbackPolling ? "fallback polling" : connectionState}</span>
          </div>
        </div>
      </div>
      <div className="space-y-3 px-4 py-3">
        {error ? <div className="rounded-[10px] bg-[#FEF2F2] px-3 py-2 text-[13px] text-[#EF4444]">{error}</div> : null}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy || isTerminal}
            className="h-8 rounded-[9px] border border-[#FECACA] bg-white px-3 text-[12px] font-medium text-[#EF4444] disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消任务
          </button>
          <button
            type="button"
            onClick={onRetry}
            disabled={busy || !isTerminal}
            className="h-8 rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[12px] font-medium text-[#374151] disabled:cursor-not-allowed disabled:opacity-50"
          >
            重试任务
          </button>
        </div>
        <div className="text-[13px] leading-5 text-[#374151]">{latestEvent?.message || "正在连接任务事件流..."}</div>
        <div className="max-h-32 space-y-2 overflow-auto">
          {events.slice(-5).map((event, index) => (
            <div key={`${event.id ?? index}-${event.type}`} className="rounded-[10px] bg-[#F9FAFB] px-3 py-2">
              <div className="text-[12px] font-semibold text-[#6B7280]">{event.type}</div>
              <div className="mt-1 text-[13px] leading-5 text-[#374151]">{event.message || event.step_label || "任务事件更新"}</div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
