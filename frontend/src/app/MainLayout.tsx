import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { navigationItemsForProject } from "./navigation";
import { listProjects, type ProjectRecord } from "../features/projects/api";
import { rememberActiveProjectId, useActiveProjectId } from "../pages/projectWorkspace";

function activeSection(pathname: string) {
  if (pathname.startsWith("/dashboard")) return "dashboard";
  if (/^\/projects\/[^/]+\/jobs(?:\/|$)/.test(pathname)) return "jobs";
  if (/^\/projects\/[^/]+\/talent-map(?:\/|$)/.test(pathname)) return "talent-map";
  if (/^\/projects\/[^/]+\/scenarios(?:\/|$)/.test(pathname)) return "evaluation";
  if (/^\/projects\/[^/]+\/candidates(?:\/|$)/.test(pathname)) return "segments";
  if (/^\/projects\/[^/]+\/outreach(?:\/|$)/.test(pathname)) return "outreach";
  if (/^\/projects\/[^/]+\/reports(?:\/|$)/.test(pathname)) return "reports";
  if (pathname.startsWith("/projects")) return "projects";
  if (pathname.startsWith("/jobs")) return "jobs";
  if (pathname.startsWith("/talent-map")) return "talent-map";
  if (pathname.startsWith("/scenarios")) return "evaluation";
  if (pathname.startsWith("/candidates")) return "segments";
  if (pathname.startsWith("/outreach")) return "outreach";
  if (pathname.startsWith("/reports")) return "reports";
  if (pathname.startsWith("/tasks")) return "tasks";
  if (pathname.startsWith("/integrations")) return "settings";
  return "dashboard";
}

function sectionPath(projectId: string, section: string) {
  return navigationItemsForProject(projectId).find((item) => item.section === section)?.path ?? `/projects/${encodeURIComponent(projectId)}`;
}

export function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeProjectId = useActiveProjectId();
  const currentSection = activeSection(location.pathname);
  const navigationItems = navigationItemsForProject(activeProjectId);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((response) => {
        if (!cancelled) setApiOnline(response.ok);
      })
      .catch(() => {
        if (!cancelled) setApiOnline(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((items) => {
        if (!cancelled) setProjects(items);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const activeProjectName = projects.find((project) => project.projectId === activeProjectId)?.name ?? activeProjectId;

  return (
    <div className="min-h-screen bg-[#F6F8FB] bg-[radial-gradient(1100px_circle_at_50%_-320px,rgba(37,99,235,0.06),transparent_60%)] text-[#111827]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] border-r border-[#E5E7EB] bg-white lg:flex lg:flex-col">
        <div className="flex h-16 items-center gap-3 border-b border-[#F3F4F6] px-5">
          <div className="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] text-[13px] font-bold text-white shadow-[0_2px_6px_rgba(37,99,235,0.35)]">
            AI
          </div>
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold leading-5 text-[#111827]">AI 招聘助手</div>
            <div className="truncate text-[12px] leading-4 text-[#9CA3AF]">Recruiting Assistant</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3 py-3">
          {navigationItems.map((item) => {
            const isActive = item.section === currentSection;
            return (
              <Link
                key={`${item.section}-${item.label}`}
                to={item.path}
                className={[
                  "relative flex h-10 items-center gap-2.5 rounded-[10px] px-3 text-[14px] font-medium leading-5 transition-colors duration-150",
                  isActive ? "bg-[#EFF6FF] text-[#2563EB]" : "text-[#374151] hover:bg-[#F3F4F6] hover:text-[#111827]",
                ].join(" ")}
              >
                {isActive ? <span className="absolute left-0 h-5 w-[3px] rounded-r-full bg-[#2563EB]" /> : null}
                <span
                  aria-hidden="true"
                  className={[
                    "grid h-[18px] w-[18px] place-items-center rounded-md text-[10px] font-semibold transition-colors duration-150",
                    isActive
                      ? "bg-white text-[#2563EB] shadow-[0_1px_2px_rgba(37,99,235,0.18)]"
                      : "bg-[#F3F4F6] text-[#6B7280]",
                  ].join(" ")}
                >
                  {item.label.slice(0, 1)}
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-[232px]">
        <header className="sticky top-0 z-20 h-16 border-b border-[#E5E7EB] bg-white/85 backdrop-blur-md">
          <div className="flex h-full items-center justify-between gap-4 px-6">
            <div className="hidden min-w-0 text-[13px] leading-5 text-[#6B7280] md:block">
              招聘项目 <span className="mx-2 text-[#D1D5DB]">/</span> {activeProjectName}
            </div>
            <label className="hidden min-w-[220px] text-[12px] font-medium text-[#6B7280] md:block">
              <span className="sr-only">切换项目</span>
              <select
                value={activeProjectId}
                onChange={(event) => {
                  const nextProjectId = event.currentTarget.value;
                  rememberActiveProjectId(nextProjectId);
                  navigate(sectionPath(nextProjectId, currentSection));
                }}
                className="h-[38px] w-full rounded-[10px] border border-[#E5E7EB] bg-[#F9FAFB] px-3 text-[13px] text-[#111827] outline-none transition focus:border-[#BFDBFE] focus:bg-white focus:ring-2 focus:ring-[#EFF6FF]"
              >
                {projects.some((project) => project.projectId === activeProjectId) ? null : (
                  <option value={activeProjectId}>{activeProjectName}</option>
                )}
                {projects.map((project) => (
                  <option key={project.projectId} value={project.projectId}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="relative hidden w-[360px] max-w-[38vw] md:block">
              <span className="sr-only">搜索候选人、岗位、项目</span>
              <input
                className="h-[38px] w-full rounded-[10px] border border-[#E5E7EB] bg-[#F9FAFB] px-3 text-[13px] text-[#111827] outline-none transition placeholder:text-[#9CA3AF] focus:border-[#BFDBFE] focus:bg-white focus:ring-2 focus:ring-[#EFF6FF]"
                placeholder="搜索候选人、岗位、项目"
              />
            </label>
            <div className="ml-auto flex items-center gap-3">
              <span
                className={[
                  "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium",
                  apiOnline === false ? "bg-[#FEF2F2] text-[#EF4444]" : "bg-[#ECFDF3] text-[#16A34A]",
                ].join(" ")}
              >
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                {apiOnline === false ? "API 未连接" : "API 在线"}
              </span>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition hover:border-[#BFDBFE] hover:bg-[#F9FAFB] active:translate-y-px"
              >
                刷新数据
              </button>
              <Link
                to="/dashboard"
                className="inline-flex h-[38px] items-center rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white shadow-[0_1px_2px_rgba(37,99,235,0.28)] transition hover:bg-[#1D4ED8] active:translate-y-px"
              >
                新建项目
              </Link>
              <div className="grid h-8 w-8 place-items-center rounded-full border border-[#DBEAFE] bg-[#EFF6FF] text-[12px] font-semibold text-[#2563EB]">
                HR
              </div>
            </div>
          </div>
        </header>

        <main className="min-h-[calc(100dvh-64px)] px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
