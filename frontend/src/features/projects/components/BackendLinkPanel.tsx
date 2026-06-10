import type { ApiRequestLogEntry } from "../../../shared/api/client";
import type { TaskSnapshot, TaskStreamConnectionState, TaskStreamEvent } from "../../../shared/hooks/useTaskStream";
import type { RunProjectScenarioAction } from "../api";

type BackendLinkPanelProps = {
  projectId: string;
  lastRequest: ApiRequestLogEntry | null;
  taskId: string | null;
  taskAction?: RunProjectScenarioAction | "weekly_report" | null;
  taskSnapshot: TaskSnapshot | null;
  connectionState: TaskStreamConnectionState;
  retryCount: number;
  usedFallbackPolling: boolean;
  events: TaskStreamEvent[];
};

function compactJson(value: unknown) {
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value, null, 2);
}

function shouldShowBackendDebugPanel() {
  if (!import.meta.env.DEV || typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("debugBackend") === "1" || window.localStorage.getItem("zhaoping.debugBackendLinks") === "1";
}

export function BackendLinkPanel({
  projectId,
  lastRequest,
  taskId,
  taskAction,
  taskSnapshot,
  connectionState,
  retryCount,
  usedFallbackPolling,
  events,
}: BackendLinkPanelProps) {
  if (!shouldShowBackendDebugPanel()) return null;

  const lastEvent = events.at(-1);

  return (
    <section className="mt-5 rounded-[14px] border border-[#BFDBFE] bg-[#EFF6FF] p-4 text-[12px] leading-5 text-[#1E3A8A]">
      <h2 className="text-[14px] font-semibold text-[#111827]">开发环境后端链路</h2>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <div className="font-semibold text-[#1E40AF]">数据源</div>
          <div>项目：GET /projects/{projectId}</div>
          <div>岗位：GET /projects/{projectId}/jobs</div>
          <div>候选人：GET /projects/{projectId}/candidates</div>
        </div>
        <div>
          <div className="font-semibold text-[#1E40AF]">当前 task</div>
          <div>task_id: {taskId ?? "—"}</div>
          <div>scenario/action: {taskAction ?? taskSnapshot?.scenario_id ?? "—"}</div>
          <div>status: {taskSnapshot?.status ?? "—"}</div>
          <div>current_agent: {taskSnapshot?.current_agent ?? "—"}</div>
          <div>current_step: {taskSnapshot?.current_step ?? "—"}</div>
          <div>error: {taskSnapshot?.error ?? "—"}</div>
        </div>
        <div>
          <div className="font-semibold text-[#1E40AF]">SSE 状态</div>
          <div>connectionState: {connectionState}</div>
          <div>retryCount: {retryCount}</div>
          <div>event count: {events.length}</div>
          <div>last event time: {lastEvent?.created_at ?? "—"}</div>
          <div>fallback polling: {usedFallbackPolling ? "yes" : "no"}</div>
        </div>
        <div>
          <div className="font-semibold text-[#1E40AF]">前端辅助逻辑声明</div>
          <div>邮件草稿：backend generated via /outreach/draft</div>
          <div>人群筛选：backend query via /segments/query</div>
          <div>周报：persisted via /reports/weekly</div>
          <div>岗位匹配：backend result via /jobs/match</div>
        </div>
      </div>
      <div className="mt-3 rounded-[10px] bg-white/70 p-3">
        <div className="font-semibold text-[#1E40AF]">最近一次 API 请求</div>
        {lastRequest ? (
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            <div>
              <div>{lastRequest.method} {lastRequest.path}</div>
              <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded-[8px] bg-white p-2 text-[#374151]">
                {compactJson(lastRequest.requestSummary)}
              </pre>
            </div>
            <div>
              <div>status: {lastRequest.status ?? "—"}</div>
              <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded-[8px] bg-white p-2 text-[#374151]">
                {compactJson(lastRequest.responseSummary)}
              </pre>
            </div>
          </div>
        ) : (
          <div className="mt-1 text-[#64748B]">暂无请求记录</div>
        )}
      </div>
    </section>
  );
}
