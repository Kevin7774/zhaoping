import { Link } from "react-router-dom";
import { useState } from "react";

import { runWeeklyReport } from "../features/projects/api";
import { WeeklyReportCard } from "../features/projects/components/WeeklyReportCard";
import {
  DataError,
  DataLoading,
  emptyWeeklyReport,
  formatDateTime,
  hasWeeklyReport,
  MetricStrip,
  PageHeader,
  rememberTaskId,
  SectionPanel,
  useActiveProjectId,
  useWorkspaceData,
} from "./projectWorkspace";

export function ReportsPage() {
  const projectId = useActiveProjectId();
  const data = useWorkspaceData({ projectId, includeLatestReport: true });
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const report = data.latestReport?.content ?? emptyWeeklyReport();
  const reportReady = hasWeeklyReport(report);

  const generateReport = async () => {
    if (!data.project) return;
    setBusy(true);
    setActionError(null);
    try {
      const created = await runWeeklyReport(data.projectId, data.project.name);
      rememberTaskId(created.task_id);
      setCreatedTaskId(created.task_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "周报任务启动失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-w-0 pb-8">
      <PageHeader
        title="招聘周报"
        subtitle="读取当前项目最新持久化周报，也可以启动后端周报任务；任务完成后项目页会保存报告。"
        action={
          <Link
            to={`/projects/${encodeURIComponent(data.projectId)}`}
            className="inline-flex h-9 items-center rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
          >
            回到项目页保存结果
          </Link>
        }
      />

      <MetricStrip
        items={[
          { label: "周报状态", value: reportReady ? "已生成" : "暂无", helper: data.latestReport?.reportId ?? "未找到最新周报" },
          { label: "开放岗位", value: data.jobs.length, helper: data.project?.name },
          { label: "候选人", value: data.candidates.length, helper: "周报输入数据", tone: "text-[#16A34A]" },
          { label: "更新时间", value: data.latestReport?.createdAt ? "已记录" : "—", helper: formatDateTime(data.latestReport?.createdAt) },
        ]}
      />

      {createdTaskId ? (
        <div className="mb-5 rounded-[12px] border border-[#BFDBFE] bg-[#EFF6FF] px-4 py-3 text-[13px] text-[#1E40AF]">
          已创建周报任务：{createdTaskId}。可在任务记录页查看状态；任务完成后回到项目页会持久化周报结果。
        </div>
      ) : null}
      {actionError ? (
        <div className="mb-5 rounded-[12px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#EF4444]">
          {actionError}
        </div>
      ) : null}

      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <WeeklyReportCard
          report={report}
          onGenerate={generateReport}
          canGenerate={!busy}
          disabledReason={busy ? "周报任务启动中" : undefined}
        />

        <SectionPanel title="周报输入范围" subtitle="当前后端周报任务会基于这些项目数据生成。">
          <div className="space-y-3 text-[13px] leading-5 text-[#374151]">
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">项目：{data.project?.name ?? "—"}</div>
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">岗位数：{data.jobs.length}</div>
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">候选人数：{data.candidates.length}</div>
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
              读取接口：GET /projects/{data.projectId}/reports/latest
            </div>
          </div>
        </SectionPanel>
      </div>
    </div>
  );
}
