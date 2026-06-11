import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { navigationItemsForProject } from "./navigation";
import { getStoredAuthUser, loginWithCompanyEmail, signOut, type AuthUser } from "../features/auth/api";
import { useActiveProjectId } from "../pages/projectWorkspace";

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

export function MainLayout() {
  const location = useLocation();
  const activeProjectId = useActiveProjectId();
  const currentSection = activeSection(location.pathname);
  const navigationItems = navigationItemsForProject(activeProjectId);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => getStoredAuthUser());
  const [loginEmail, setLoginEmail] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

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

  async function handleLogin() {
    if (!loginEmail.trim()) {
      setLoginError("请输入公司邮箱");
      return;
    }
    setLoginBusy(true);
    setLoginError(null);
    try {
      const session = await loginWithCompanyEmail(loginEmail);
      setAuthUser(session.user);
      setLoginEmail("");
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoginBusy(false);
    }
  }

  function handleSignOut() {
    signOut();
    setAuthUser(null);
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#F6F8FB] bg-[radial-gradient(1100px_circle_at_50%_-320px,rgba(37,99,235,0.06),transparent_60%)] text-[#111827]">
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
        <header className="sticky top-0 z-20 min-h-16 border-b border-[#E5E7EB] bg-white/85 backdrop-blur-md">
          <div className="flex min-h-16 max-w-full flex-wrap items-center justify-end gap-3 px-4 py-3 sm:px-6">
            <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 sm:gap-3">
              <span
                className={[
                  "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium",
                  apiOnline === false ? "bg-[#FEF2F2] text-[#EF4444]" : "bg-[#ECFDF3] text-[#16A34A]",
                ].join(" ")}
              >
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                {apiOnline === false ? "API 未连接" : "API 在线"}
              </span>
              {authUser ? (
                <div className="flex min-w-0 items-center gap-2">
                  <span className="hidden max-w-[180px] truncate rounded-full bg-[#F3F4F6] px-2.5 py-1 text-[12px] font-medium text-[#374151] sm:inline">
                    {authUser.email}
                  </span>
                  <button
                    type="button"
                    onClick={handleSignOut}
                    className="h-[34px] rounded-[10px] border border-[#E5E7EB] bg-white px-2.5 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
                  >
                    退出
                  </button>
                </div>
              ) : (
                <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
                  <label className="sr-only" htmlFor="company-email-login">
                    公司邮箱
                  </label>
                  <input
                    id="company-email-login"
                    value={loginEmail}
                    onChange={(event) => setLoginEmail(event.currentTarget.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void handleLogin();
                    }}
                    placeholder="公司邮箱"
                    className="h-[34px] w-[min(178px,48vw)] rounded-[10px] border border-[#E5E7EB] bg-[#F9FAFB] px-2.5 text-[13px] text-[#111827] outline-none transition placeholder:text-[#9CA3AF] focus:border-[#BFDBFE] focus:bg-white focus:ring-2 focus:ring-[#EFF6FF]"
                  />
                  <button
                    type="button"
                    onClick={() => void handleLogin()}
                    disabled={loginBusy}
                    title={loginError ?? undefined}
                    className="h-[34px] rounded-[10px] border border-[#BFDBFE] bg-[#EFF6FF] px-2.5 text-[13px] font-medium text-[#2563EB] transition hover:bg-[#DBEAFE] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loginBusy ? "登录中" : "登录"}
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="hidden h-[38px] rounded-[10px] border border-[#E5E7EB] bg-white px-3.5 text-[14px] font-medium text-[#374151] shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition hover:border-[#BFDBFE] hover:bg-[#F9FAFB] active:translate-y-px sm:inline"
              >
                刷新数据
              </button>
              <Link
                to="/dashboard"
                className="hidden h-[38px] items-center rounded-[10px] bg-[#2563EB] px-3.5 text-[14px] font-medium text-white shadow-[0_1px_2px_rgba(37,99,235,0.28)] transition hover:bg-[#1D4ED8] active:translate-y-px sm:inline-flex"
              >
                新建项目
              </Link>
              <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[#DBEAFE] bg-[#EFF6FF] text-[12px] font-semibold text-[#2563EB]">
                HR
              </div>
            </div>
          </div>
        </header>

        <main className="min-h-[calc(100dvh-64px)] max-w-full overflow-x-hidden px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
