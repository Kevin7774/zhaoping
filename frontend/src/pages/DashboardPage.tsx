import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createProject, listProjects, type ProjectRecord } from "../features/projects/api";
import { apiClient } from "../shared/api/client";
import {
  DataError,
  DataLoading,
  formatDateTime,
  MetricStrip,
  PageHeader,
  rememberActiveProjectId,
  SectionPanel,
  StatusPill,
} from "./projectWorkspace";

function projectUrl(projectId: string) {
  return `/projects/${encodeURIComponent(projectId)}`;
}

type MonitorResult = {
  ok: boolean;
  action: string;
  output: string;
};

export function DashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectStatus, setProjectStatus] = useState("active");
  const [reloadToken, setReloadToken] = useState(0);
  const [monitorBusy, setMonitorBusy] = useState<"start" | "status" | null>(null);
  const [monitorOutput, setMonitorOutput] = useState("");
  const [monitorError, setMonitorError] = useState("");

  async function runMonitor(action: "start" | "status") {
    setMonitorBusy(action);
    setMonitorError("");
    try {
      const result =
        action === "start"
          ? await apiClient.post<MonitorResult>("/monitor/start")
          : await apiClient.get<MonitorResult>("/monitor/status");
      setMonitorOutput(result.output);
      if (!result.ok) setMonitorError("监控脚本返回非零退出码，请检查输出。");
    } catch (error) {
      setMonitorError(error instanceof Error ? error.message : "监控接口调用失败");
    } finally {
      setMonitorBusy(null);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listProjects()
      .then((items) => {
        if (!cancelled) setProjects(items);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "项目列表加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const totals = useMemo(
    () => ({
      jobs: projects.reduce((total, project) => total + project.openJobs, 0),
      candidates: projects.reduce((total, project) => total + project.totalCandidates, 0),
      awaiting: projects.reduce((total, project) => total + project.awaitingHuman, 0),
    }),
    [projects],
  );

  async function handleCreateProject() {
    const id = projectId.trim();
    const name = projectName.trim();
    if (!id || !name) {
      setCreateError("请填写项目 ID 和项目名称。");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const created = await createProject({ id, name, status: projectStatus });
      setProjects((current) => [created, ...current.filter((project) => project.projectId !== created.projectId)]);
      rememberActiveProjectId(created.projectId);
      navigate(projectUrl(created.projectId));
    } catch (createProjectError) {
      setCreateError(createProjectError instanceof Error ? createProjectError.message : "项目创建失败");
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <DataLoading />;
  if (error) return <DataError message={error} onRetry={() => setReloadToken((current) => current + 1)} />;

  return (
    <div className="min-w-0 pb-8">
      <PageHeader
        title="工作台"
        subtitle="项目是顶层隔离空间。先选择或创建项目，再进入该项目的岗位、候选人、周报和触达流程。"
      />

      <MetricStrip
        items={[
          { label: "项目数", value: projects.length, helper: "GET /projects", tone: "text-[#2563EB]" },
          { label: "开放岗位", value: totals.jobs, helper: "按项目汇总" },
          { label: "候选人", value: totals.candidates, helper: "按项目去重统计", tone: "text-[#16A34A]" },
          { label: "待确认", value: totals.awaiting, helper: "需要处理的事项", tone: "text-[#F59E0B]" },
        ]}
      />

      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <SectionPanel title="项目列表" subtitle="点击项目进入独立工作空间。">
          {projects.length === 0 ? (
            <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-5 py-8 text-center text-[13px] text-[#6B7280]">
              暂无项目。先创建一个空项目，或进入项目后用岗位智能生成创建岗位矩阵。
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[260px] px-4">项目</th>
                    <th className="w-[100px] px-3">岗位</th>
                    <th className="w-[100px] px-3">候选人</th>
                    <th className="w-[120px] px-3">状态</th>
                    <th className="w-[170px] px-3">创建时间</th>
                    <th className="px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {projects.map((project) => (
                    <tr key={project.projectId} className="transition-colors hover:bg-[#FAFBFD]">
                      <td className="px-4 py-4">
                        <div className="font-semibold text-[#111827]">{project.name}</div>
                        <div className="mt-1 font-mono text-[12px] text-[#9CA3AF]">{project.projectId}</div>
                      </td>
                      <td className="px-3 py-4 text-[#374151]">{project.openJobs}</td>
                      <td className="px-3 py-4 text-[#374151]">{project.totalCandidates}</td>
                      <td className="px-3 py-4">
                        <StatusPill status={project.status} />
                      </td>
                      <td className="px-3 py-4 text-[#374151]">{formatDateTime(project.updatedAt)}</td>
                      <td className="px-4 py-4 text-right">
                        <Link
                          to={projectUrl(project.projectId)}
                          onClick={() => rememberActiveProjectId(project.projectId)}
                          className="inline-flex h-9 items-center rounded-[10px] bg-[#2563EB] px-3 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8]"
                        >
                          进入项目
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>

        <div className="min-w-0 space-y-5">
        <SectionPanel title="新建项目" subtitle="创建后会进入一个没有岗位和候选人的隔离空间。">
          <div className="space-y-4">
            <label className="block text-[12px] font-medium text-[#6B7280]">
              项目 ID
              <input
                value={projectId}
                onChange={(event) => setProjectId(event.currentTarget.value)}
                placeholder="project_hanno_ai_hardware"
                className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
              />
            </label>
            <label className="block text-[12px] font-medium text-[#6B7280]">
              项目名称
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.currentTarget.value)}
                placeholder="汉诺云智招聘"
                className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
              />
            </label>
            <label className="block text-[12px] font-medium text-[#6B7280]">
              状态
              <select
                value={projectStatus}
                onChange={(event) => setProjectStatus(event.currentTarget.value)}
                className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
              >
                <option value="active">进行中</option>
                <option value="paused">暂停</option>
              </select>
            </label>
            <button
              type="button"
              onClick={handleCreateProject}
              disabled={creating}
              className="h-10 w-full rounded-[10px] bg-[#2563EB] text-[13px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:bg-[#BFDBFE]"
            >
              {creating ? "创建中" : "创建空项目"}
            </button>
            {createError ? <div className="text-[13px] text-[#EF4444]">{createError}</div> : null}
          </div>
        </SectionPanel>

        <SectionPanel title="测试监控" subtitle="开发环境专用：HTTP 访问日志 + PG 行级审计 + watcher 汇总流。">
          <div className="space-y-3">
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => runMonitor("start")}
                disabled={monitorBusy !== null}
                className="h-10 flex-1 rounded-[10px] bg-[#16A34A] text-[13px] font-medium text-white transition hover:bg-[#15803D] disabled:cursor-not-allowed disabled:bg-[#BBF7D0]"
              >
                {monitorBusy === "start" ? "启动中" : "一键启动监控"}
              </button>
              <button
                type="button"
                onClick={() => runMonitor("status")}
                disabled={monitorBusy !== null}
                className="h-10 flex-1 rounded-[10px] border border-[#D1D5DB] bg-white text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
              >
                {monitorBusy === "status" ? "查询中" : "查看状态"}
              </button>
            </div>
            {monitorOutput ? (
              <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded-[10px] bg-[#0F172A] px-3 py-2 font-mono text-[12px] leading-5 text-[#A7F3D0]">
                {monitorOutput}
              </pre>
            ) : (
              <div className="text-[12px] text-[#9CA3AF]">
                日志：artifacts/manual_test_20260610/monitor.log（可终端 tail -f 实时查看）
              </div>
            )}
            {monitorError ? <div className="text-[13px] text-[#EF4444]">{monitorError}</div> : null}
          </div>
        </SectionPanel>
        </div>
      </div>
    </div>
  );
}
