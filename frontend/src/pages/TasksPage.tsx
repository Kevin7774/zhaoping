import { useEffect, useState } from "react";

import { getTask } from "../features/projects/api";
import type { TaskSnapshot } from "../shared/hooks/useTaskStream";
import {
  DataError,
  DataLoading,
  EmptyState,
  formatDateTime,
  MetricStrip,
  PageHeader,
  PrimaryButton,
  readRecentTaskIds,
  rememberTaskId,
  SectionPanel,
  StatusPill,
  useWorkspaceData,
} from "./projectWorkspace";

type TaskLookupState = {
  snapshots: Record<string, TaskSnapshot>;
  errors: Record<string, string>;
  loading: boolean;
};

type TaskLookupResult = { taskId: string; snapshot: TaskSnapshot } | { taskId: string; error: string };

export function TasksPage() {
  const data = useWorkspaceData();
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [inputTaskId, setInputTaskId] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [lookup, setLookup] = useState<TaskLookupState>({ snapshots: {}, errors: {}, loading: false });

  useEffect(() => {
    setTaskIds(readRecentTaskIds());
  }, []);

  useEffect(() => {
    let cancelled = false;
    const ids = taskIds.filter(Boolean);
    if (!ids.length) {
      setLookup({ snapshots: {}, errors: {}, loading: false });
      return;
    }

    setLookup((current) => ({ ...current, loading: true }));
    Promise.all(
      ids.map(async (taskId): Promise<TaskLookupResult> => {
        try {
          const snapshot = await getTask(taskId);
          return { taskId, snapshot };
        } catch (error) {
          return { taskId, error: error instanceof Error ? error.message : "任务读取失败" };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      const snapshots: Record<string, TaskSnapshot> = {};
      const errors: Record<string, string> = {};
      for (const result of results) {
        if ("snapshot" in result) snapshots[result.taskId] = result.snapshot;
        if ("error" in result) errors[result.taskId] = result.error;
      }
      setLookup({ snapshots, errors, loading: false });
    });

    return () => {
      cancelled = true;
    };
  }, [refreshToken, taskIds]);

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const handleLookup = () => {
    const normalized = inputTaskId.trim();
    if (!normalized) return;
    rememberTaskId(normalized);
    setTaskIds(readRecentTaskIds());
    setRefreshToken((current) => current + 1);
  };

  const snapshots = Object.values(lookup.snapshots);
  const awaitingCount = snapshots.filter((snapshot) => snapshot.status === "awaiting_human").length;
  const doneCount = snapshots.filter((snapshot) => snapshot.status === "done").length;

  return (
    <div className="pb-8">
      <PageHeader
        title="任务记录"
        subtitle="查看本机最近启动过的后端任务，也可以手动输入 task_id 查询任务快照。"
        action={
          <button
            type="button"
            onClick={() => setRefreshToken((current) => current + 1)}
            className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
          >
            刷新任务
          </button>
        }
      />

      <MetricStrip
        items={[
          { label: "已记录 task_id", value: taskIds.length, helper: "浏览器 localStorage" },
          { label: "已读取快照", value: snapshots.length, helper: lookup.loading ? "读取中" : "GET /tasks/{taskId}" },
          { label: "等待人工", value: awaitingCount, helper: "awaiting_human", tone: "text-[#F59E0B]" },
          { label: "已完成", value: doneCount, helper: "done", tone: "text-[#16A34A]" },
        ]}
      />

      <SectionPanel title="查询任务" subtitle="如果你从 SSE 面板或接口返回里拿到 task_id，可以在这里粘贴查询。">
        <div className="flex flex-col gap-3 md:flex-row">
          <input
            value={inputTaskId}
            onChange={(event) => setInputTaskId(event.currentTarget.value)}
            placeholder="例如 task_..."
            className="h-10 flex-1 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
          />
          <PrimaryButton onClick={handleLookup}>查询 task</PrimaryButton>
        </div>
      </SectionPanel>

      <div className="mt-5">
        <SectionPanel title="最近任务" subtitle="项目页、找候选人页、候选人评估页和周报页启动任务后会自动记录。">
          {taskIds.length === 0 ? (
            <EmptyState
              title="暂无最近任务"
              body="先在招聘项目、找候选人、候选人评估或招聘周报页启动一个后端任务，这里会显示 task_id 和状态。"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[260px] px-4">task_id</th>
                    <th className="w-[120px] px-3">状态</th>
                    <th className="w-[140px] px-3">场景</th>
                    <th className="w-[120px] px-3">当前步骤</th>
                    <th className="w-[160px] px-3">事件数</th>
                    <th className="px-4">错误 / 等待内容</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {taskIds.map((taskId) => {
                    const snapshot = lookup.snapshots[taskId];
                    const error = lookup.errors[taskId];
                    return (
                      <tr key={taskId}>
                        <td className="px-4 py-4 font-mono text-[12px] text-[#111827]">{taskId}</td>
                        <td className="px-3 py-4">
                          {snapshot ? <StatusPill status={snapshot.status} /> : <span className="text-[#9CA3AF]">—</span>}
                        </td>
                        <td className="px-3 py-4 text-[#374151]">{snapshot?.scenario_id ?? "—"}</td>
                        <td className="px-3 py-4 text-[#374151]">
                          {snapshot?.current_step ?? "—"} / {snapshot?.total_steps ?? "—"}
                        </td>
                        <td className="px-3 py-4 text-[#374151]">
                          {snapshot?.audit_events?.length ?? "—"}
                          {snapshot?.audit_events?.at(-1)?.created_at ? (
                            <div className="mt-1 text-[12px] text-[#9CA3AF]">
                              {formatDateTime(snapshot.audit_events.at(-1)?.created_at)}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-4 py-4 text-[#374151]">
                          {error || snapshot?.error || (snapshot?.awaiting ? "等待人工确认" : "—")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>
      </div>
    </div>
  );
}
