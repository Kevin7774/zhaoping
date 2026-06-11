import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { createProject, deleteProject, listProjects, updateProject, type ProjectRecord } from "../features/projects/api";
import {
  ACTIVE_PROJECT_ID_KEY,
  DataError,
  DataLoading,
  formatDateTime,
  PageHeader,
  rememberActiveProjectId,
  SectionPanel,
  StatusPill,
} from "./projectWorkspace";

function projectUrl(projectId: string) {
  return `/projects/${encodeURIComponent(projectId)}`;
}

function clearActiveProjectId(projectId: string) {
  if (typeof window === "undefined") return;
  try {
    if (window.localStorage.getItem(ACTIVE_PROJECT_ID_KEY) === projectId) {
      window.localStorage.removeItem(ACTIVE_PROJECT_ID_KEY);
    }
  } catch {
    // localStorage may be unavailable; deleting the backend project remains the source of truth.
  }
}

export function DashboardPage() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [formError, setFormError] = useState("");
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectStatus, setProjectStatus] = useState("active");
  const [reloadToken, setReloadToken] = useState(0);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectStatus, setEditProjectStatus] = useState("active");

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

  async function reloadProjects() {
    setProjects(await listProjects());
  }

  async function handleCreateProject() {
    const id = projectId.trim();
    const name = projectName.trim();
    if (!id || !name) {
      setFormError("请填写项目 ID 和项目名称。");
      return;
    }
    setBusyAction("create");
    setFormError("");
    try {
      await createProject({ id, name, status: projectStatus });
      await reloadProjects();
      setProjectId("");
      setProjectName("");
      setProjectStatus("active");
    } catch (createProjectError) {
      setFormError(createProjectError instanceof Error ? createProjectError.message : "项目创建失败");
    } finally {
      setBusyAction(null);
    }
  }

  function startEditProject(project: ProjectRecord) {
    setEditingProjectId(project.projectId);
    setEditProjectName(project.name);
    setEditProjectStatus(project.status || "active");
    setFormError("");
  }

  async function handleUpdateProject() {
    if (!editingProjectId) return;
    const name = editProjectName.trim();
    if (!name) {
      setFormError("请填写项目名称。");
      return;
    }
    setBusyAction(`update:${editingProjectId}`);
    setFormError("");
    try {
      await updateProject(editingProjectId, { name, status: editProjectStatus });
      await reloadProjects();
      setEditingProjectId(null);
      setEditProjectName("");
      setEditProjectStatus("active");
    } catch (updateProjectError) {
      setFormError(updateProjectError instanceof Error ? updateProjectError.message : "项目更新失败");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteProject(project: ProjectRecord) {
    const confirmed = window.confirm(`确认删除项目「${project.name}」？此操作会删除该项目的岗位和项目内关联数据。`);
    if (!confirmed) return;
    setBusyAction(`delete:${project.projectId}`);
    setFormError("");
    try {
      await deleteProject(project.projectId);
      clearActiveProjectId(project.projectId);
      if (editingProjectId === project.projectId) {
        setEditingProjectId(null);
        setEditProjectName("");
        setEditProjectStatus("active");
      }
      await reloadProjects();
    } catch (deleteProjectError) {
      setFormError(deleteProjectError instanceof Error ? deleteProjectError.message : "项目删除失败");
    } finally {
      setBusyAction(null);
    }
  }

  if (loading) return <DataLoading />;
  if (error) return <DataError message={error} onRetry={() => setReloadToken((current) => current + 1)} />;

  return (
    <div className="min-w-0 pb-8">
      <PageHeader title="工作台" subtitle="项目管理入口。" />

      <section
        aria-label="项目数量"
        className="mb-5 flex min-w-0 flex-col justify-between gap-4 rounded-[14px] border border-[#E5E7EB] bg-white px-5 py-4 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)] md:flex-row md:items-center"
      >
        <div>
          <div className="text-[13px] leading-5 text-[#6B7280]">项目数量</div>
          <strong className="mt-1 block text-[32px] font-bold leading-10 text-[#2563EB]">{projects.length}</strong>
        </div>
        <button
          type="button"
          onClick={() => setReloadToken((current) => current + 1)}
          disabled={busyAction !== null}
          className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
        >
          刷新列表
        </button>
      </section>

      <SectionPanel title="项目管理">
        <div className="grid min-w-0 gap-4 lg:grid-cols-[1fr_1fr_160px_120px]">
          <label className="block text-[12px] font-medium text-[#6B7280]">
            项目 ID
            <input
              value={projectId}
              onChange={(event) => setProjectId(event.currentTarget.value)}
              placeholder="project_new_market"
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
            />
          </label>
          <label className="block text-[12px] font-medium text-[#6B7280]">
            项目名称
            <input
              value={projectName}
              onChange={(event) => setProjectName(event.currentTarget.value)}
              placeholder="新市场项目"
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
          <div className="flex items-end">
            <button
              type="button"
              onClick={handleCreateProject}
              disabled={busyAction !== null}
              className="h-10 w-full rounded-[10px] bg-[#2563EB] text-[13px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:bg-[#BFDBFE]"
            >
              {busyAction === "create" ? "添加中" : "添加项目"}
            </button>
          </div>
        </div>

        {editingProjectId ? (
          <div className="mt-5 grid min-w-0 gap-4 border-t border-[#EEF2F7] pt-4 lg:grid-cols-[1fr_180px_120px_100px]">
            <label className="block text-[12px] font-medium text-[#6B7280]">
              编辑项目名称
              <input
                value={editProjectName}
                onChange={(event) => setEditProjectName(event.currentTarget.value)}
                className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
              />
            </label>
            <label className="block text-[12px] font-medium text-[#6B7280]">
              编辑状态
              <select
                value={editProjectStatus}
                onChange={(event) => setEditProjectStatus(event.currentTarget.value)}
                className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
              >
                <option value="active">进行中</option>
                <option value="paused">暂停</option>
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="button"
                onClick={handleUpdateProject}
                disabled={busyAction !== null}
                className="h-10 w-full rounded-[10px] bg-[#16A34A] text-[13px] font-medium text-white transition hover:bg-[#15803D] disabled:cursor-not-allowed disabled:bg-[#BBF7D0]"
              >
                保存修改
              </button>
            </div>
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => setEditingProjectId(null)}
                disabled={busyAction !== null}
                className="h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
              >
                取消
              </button>
            </div>
          </div>
        ) : null}
        {formError ? <div className="mt-3 text-[13px] text-[#EF4444]">{formError}</div> : null}
      </SectionPanel>

      <div className="mt-5">
        <SectionPanel title="项目一览">
          {projects.length === 0 ? (
            <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-5 py-8 text-center text-[13px] text-[#6B7280]">
              暂无项目。
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[320px] px-4">项目</th>
                    <th className="w-[130px] px-3">状态</th>
                    <th className="w-[180px] px-3">创建时间</th>
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
                      <td className="px-3 py-4">
                        <StatusPill status={project.status} />
                      </td>
                      <td className="px-3 py-4 text-[#374151]">{formatDateTime(project.updatedAt)}</td>
                      <td className="px-4 py-4">
                        <div className="flex justify-end gap-2">
                          <Link
                            to={projectUrl(project.projectId)}
                            aria-label={`进入项目 ${project.name}`}
                            onClick={() => rememberActiveProjectId(project.projectId)}
                            className="inline-flex h-9 items-center rounded-[10px] bg-[#2563EB] px-3 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8]"
                          >
                            进入
                          </Link>
                          <button
                            type="button"
                            aria-label={`编辑 ${project.name}`}
                            onClick={() => startEditProject(project)}
                            disabled={busyAction !== null}
                            className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
                          >
                            编辑
                          </button>
                          <button
                            type="button"
                            aria-label={`删除 ${project.name}`}
                            onClick={() => handleDeleteProject(project)}
                            disabled={busyAction !== null}
                            className="h-9 rounded-[10px] border border-[#FCA5A5] bg-white px-3 text-[13px] font-medium text-[#DC2626] transition hover:bg-[#FEF2F2] disabled:cursor-not-allowed disabled:text-[#FCA5A5]"
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>
      </div>
    </div>
  );
}
