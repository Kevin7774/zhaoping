import type { TaskSnapshot, TaskStreamConnectionState, TaskStreamEvent } from "../../../shared/hooks/useTaskStream";

type LiveTaskSummaryProps = {
  taskId: string | null;
  events: TaskStreamEvent[];
  taskSnapshot: TaskSnapshot | null;
  connectionState: TaskStreamConnectionState;
  error?: string | null;
};

export function LiveTaskSummary({ taskId, events, taskSnapshot, connectionState, error }: LiveTaskSummaryProps) {
  if (!taskId) return null;

  const latestEvent = events.at(-1);
  const status = taskSnapshot?.status ?? connectionState;

  return (
    <aside className="fixed bottom-5 right-5 z-40 w-[min(420px,calc(100vw-40px))] rounded-lg border border-blue-100 bg-white shadow-xl">
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-950">LiveTaskSummary</div>
            <div className="mt-0.5 text-xs text-slate-500">task_id: {taskId}</div>
          </div>
          <span className="rounded-md bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700">{status}</span>
        </div>
      </div>
      <div className="space-y-3 px-4 py-3">
        {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="text-sm text-slate-700">{latestEvent?.message || "正在连接任务事件流..."}</div>
        <div className="max-h-32 space-y-2 overflow-auto">
          {events.slice(-5).map((event, index) => (
            <div key={`${event.id ?? index}-${event.type}`} className="rounded-md bg-slate-50 px-3 py-2">
              <div className="text-xs font-semibold text-slate-500">{event.type}</div>
              <div className="mt-1 text-sm text-slate-700">{event.message || event.step_label || "任务事件更新"}</div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
