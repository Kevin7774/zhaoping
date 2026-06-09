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

type LeadIngestionStats = {
  found: number;
  normalized: number;
  insertedCandidates: number;
  updatedCandidates: number;
  linkedJobCandidates: number;
  duplicates: number;
  rejected: number;
  rejectedReasons: Record<string, number>;
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
  const leadIngestion = leadIngestionStatsFromResult(taskSnapshot?.result);

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
        {leadIngestion ? <LeadIngestionSummary stats={leadIngestion} /> : null}
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

function LeadIngestionSummary({ stats }: { stats: LeadIngestionStats }) {
  const items = [
    ["发现线索", stats.found],
    ["新增候选人", stats.insertedCandidates],
    ["更新候选人", stats.updatedCandidates],
    ["关联岗位", stats.linkedJobCandidates],
    ["去重", stats.duplicates],
    ["拒绝入库", stats.rejected],
  ] as const;
  const rejectedReasons = Object.entries(stats.rejectedReasons).filter(([, count]) => count > 0);

  return (
    <section className="border-t border-[#EEF2F7] pt-3">
      <div className="text-[12px] font-semibold text-[#6B7280]">候选人线索入库</div>
      <div className="mt-2 grid grid-cols-3 gap-x-3 gap-y-2">
        {items.map(([label, value]) => (
          <div key={label}>
            <div className="text-[11px] text-[#9CA3AF]">{label}</div>
            <div className="text-[16px] font-semibold leading-6 text-[#111827]">{value}</div>
          </div>
        ))}
      </div>
      {rejectedReasons.length ? (
        <div className="mt-2 text-[12px] leading-5 text-[#6B7280]">
          {rejectedReasons.map(([reason, count]) => `${reason} × ${count}`).join("；")}
        </div>
      ) : null}
    </section>
  );
}

function leadIngestionStatsFromResult(result: unknown): LeadIngestionStats | null {
  if (!isRecord(result)) return null;
  const ingestion = result.lead_ingestion;
  if (!isRecord(ingestion)) return null;
  return {
    found: readNumber(ingestion.found),
    normalized: readNumber(ingestion.normalized),
    insertedCandidates: readNumber(ingestion.inserted_candidates),
    updatedCandidates: readNumber(ingestion.updated_candidates),
    linkedJobCandidates: readNumber(ingestion.linked_job_candidates),
    duplicates: readNumber(ingestion.duplicates),
    rejected: readNumber(ingestion.rejected),
    rejectedReasons: readRejectedReasons(ingestion.rejected_reasons),
  };
}

function readRejectedReasons(value: unknown) {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, count]) => [key, readNumber(count)]));
}

function readNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
