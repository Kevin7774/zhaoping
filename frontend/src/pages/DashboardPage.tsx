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

  const activeProjectCount = projects.filter((project) => project.status === "active").length;
  const pausedProjectCount = projects.filter((project) => project.status === "paused").length;

  return (
    <div className="min-w-0 pb-6">
      <PageHeader title="工作台" subtitle="招聘项目、状态和入口集中管理。" />

      <section aria-label="工作台总览" className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <SectionPanel
            title="项目一览"
            subtitle="项目入口、状态和更新时间集中展示。"
            action={
              <button
                type="button"
                onClick={() => setReloadToken((current) => current + 1)}
                disabled={busyAction !== null}
                className="h-8 rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
              >
                刷新列表
              </button>
            }
          >
          {projects.length === 0 ? (
            <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-5 py-8 text-center text-[13px] text-[#6B7280]">
              暂无项目。
            </div>
          ) : (
            <>
            <div className="hidden overflow-x-auto md:block">
              <table className="min-w-[680px] w-full text-left text-[13px] leading-5">
                <thead className="h-10 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[280px] px-4">项目</th>
                    <th className="w-[100px] px-3">状态</th>
                    <th className="w-[150px] px-3">创建时间</th>
                    <th className="w-[150px] px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {projects.map((project) => (
                    <tr key={project.projectId} className="transition-colors hover:bg-[#FAFBFD]">
                      <td className="px-4 py-3">
                        <div className="font-semibold text-[#111827]">{project.name}</div>
                        <div className="mt-1 font-mono text-[12px] text-[#9CA3AF]">{project.projectId}</div>
                      </td>
                      <td className="px-3 py-3">
                        <StatusPill status={project.status} />
                      </td>
                      <td className="px-3 py-3 text-[#374151]">{formatDateTime(project.updatedAt)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-nowrap justify-end gap-1.5">
                          <Link
                            to={projectUrl(project.projectId)}
                            aria-label={`进入项目 ${project.name}`}
                            onClick={() => rememberActiveProjectId(project.projectId)}
                            className="inline-flex h-8 items-center whitespace-nowrap rounded-[9px] bg-[#2563EB] px-2.5 text-[12px] font-medium text-white transition hover:bg-[#1D4ED8]"
                          >
                            进入
                          </Link>
                          <button
                            type="button"
                            aria-label={`编辑 ${project.name}`}
                            onClick={() => startEditProject(project)}
                            disabled={busyAction !== null}
                            className="h-8 whitespace-nowrap rounded-[9px] border border-[#D1D5DB] bg-white px-2.5 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
                          >
                            编辑
                          </button>
                          <button
                            type="button"
                            aria-label={`删除 ${project.name}`}
                            onClick={() => handleDeleteProject(project)}
                            disabled={busyAction !== null}
                            className="h-8 whitespace-nowrap rounded-[9px] border border-[#FCA5A5] bg-white px-2.5 text-[12px] font-medium text-[#DC2626] transition hover:bg-[#FEF2F2] disabled:cursor-not-allowed disabled:text-[#FCA5A5]"
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
            <div className="grid gap-3 md:hidden">
              {projects.map((project) => (
                <article key={project.projectId} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-semibold text-[#111827]">{project.name}</div>
                    <div className="mt-1 truncate font-mono text-[12px] text-[#9CA3AF]">{project.projectId}</div>
                  </div>
                  <div className="mt-3 flex min-w-0 items-center justify-between gap-2">
                    <StatusPill status={project.status} />
                    <span className="truncate text-[12px] text-[#6B7280]">{formatDateTime(project.updatedAt)}</span>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-1.5">
                    <Link
                      to={projectUrl(project.projectId)}
                      aria-label={`进入项目卡片 ${project.name}`}
                      onClick={() => rememberActiveProjectId(project.projectId)}
                      className="inline-flex h-8 items-center justify-center rounded-[9px] bg-[#2563EB] px-1.5 text-[12px] font-medium text-white transition hover:bg-[#1D4ED8]"
                    >
                      进入
                    </Link>
                    <button
                      type="button"
                      aria-label={`编辑项目卡片 ${project.name}`}
                      onClick={() => startEditProject(project)}
                      disabled={busyAction !== null}
                      className="h-8 rounded-[9px] border border-[#D1D5DB] bg-white px-1.5 text-[12px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      aria-label={`删除项目卡片 ${project.name}`}
                      onClick={() => handleDeleteProject(project)}
                      disabled={busyAction !== null}
                      className="h-8 rounded-[9px] border border-[#FCA5A5] bg-white px-1.5 text-[12px] font-medium text-[#DC2626] transition hover:bg-[#FEF2F2] disabled:cursor-not-allowed disabled:text-[#FCA5A5]"
                    >
                      删除
                    </button>
                  </div>
                </article>
              ))}
            </div>
            </>
          )}
          </SectionPanel>
        </div>

        <aside className="grid min-w-0 gap-4 xl:sticky xl:top-4">
          <section
            aria-label="项目数量"
            className="min-w-0 rounded-[14px] border border-[#E5E7EB] bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[13px] leading-5 text-[#6B7280]">项目数量</div>
                <strong
                  aria-label="项目总数"
                  className="mt-1 block text-[34px] font-bold leading-9 tracking-[-0.03em] text-[#2563EB]"
                >
                  {projects.length}
                </strong>
              </div>
              <div className="rounded-full bg-[#EFF6FF] px-2.5 py-1 text-[12px] font-medium text-[#2563EB]">总览</div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="rounded-[10px] border border-[#E5E7EB] bg-[#F9FAFB] px-3 py-2">
                <div className="text-[11px] text-[#6B7280]">进行中</div>
                <div className="mt-0.5 text-[18px] font-semibold text-[#16A34A]">{activeProjectCount}</div>
              </div>
              <div className="rounded-[10px] border border-[#E5E7EB] bg-[#F9FAFB] px-3 py-2">
                <div className="text-[11px] text-[#6B7280]">暂停</div>
                <div className="mt-0.5 text-[18px] font-semibold text-[#6B7280]">{pausedProjectCount}</div>
              </div>
            </div>
          </section>

          <section className="min-w-0 rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
            <div className="border-b border-[#EEF2F7] bg-[#F9FAFB]/70 px-4 py-3">
              <h2 className="text-[15px] font-semibold leading-6 text-[#111827]">项目管理</h2>
            </div>
            <div className="space-y-3 p-4">
              <label className="block text-[12px] font-medium text-[#6B7280]">
                项目 ID
                <input
                  value={projectId}
                  onChange={(event) => setProjectId(event.currentTarget.value)}
                  placeholder="project_new_market"
                  className="mt-1 h-9 w-full rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
                />
              </label>
              <label className="block text-[12px] font-medium text-[#6B7280]">
                项目名称
                <input
                  value={projectName}
                  onChange={(event) => setProjectName(event.currentTarget.value)}
                  placeholder="新市场项目"
                  className="mt-1 h-9 w-full rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
                />
              </label>
              <label className="block text-[12px] font-medium text-[#6B7280]">
                状态
                <select
                  value={projectStatus}
                  onChange={(event) => setProjectStatus(event.currentTarget.value)}
                  className="mt-1 h-9 w-full rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
                >
                  <option value="active">进行中</option>
                  <option value="paused">暂停</option>
                </select>
              </label>
              <button
                type="button"
                onClick={handleCreateProject}
                disabled={busyAction !== null}
                className="h-9 w-full rounded-[9px] bg-[#2563EB] text-[13px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:bg-[#BFDBFE]"
              >
                {busyAction === "create" ? "添加中" : "添加项目"}
              </button>

              {editingProjectId ? (
                <div className="space-y-3 border-t border-[#EEF2F7] pt-3">
                  <label className="block text-[12px] font-medium text-[#6B7280]">
                    编辑项目名称
                    <input
                      value={editProjectName}
                      onChange={(event) => setEditProjectName(event.currentTarget.value)}
                      className="mt-1 h-9 w-full rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
                    />
                  </label>
                  <label className="block text-[12px] font-medium text-[#6B7280]">
                    编辑状态
                    <select
                      value={editProjectStatus}
                      onChange={(event) => setEditProjectStatus(event.currentTarget.value)}
                      className="mt-1 h-9 w-full rounded-[9px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
                    >
                      <option value="active">进行中</option>
                      <option value="paused">暂停</option>
                    </select>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={handleUpdateProject}
                      disabled={busyAction !== null}
                      className="h-9 rounded-[9px] bg-[#16A34A] text-[13px] font-medium text-white transition hover:bg-[#15803D] disabled:cursor-not-allowed disabled:bg-[#BBF7D0]"
                    >
                      保存修改
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingProjectId(null)}
                      disabled={busyAction !== null}
                      className="h-9 rounded-[9px] border border-[#D1D5DB] bg-white text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : null}
              {formError ? <div className="text-[13px] text-[#EF4444]">{formError}</div> : null}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
