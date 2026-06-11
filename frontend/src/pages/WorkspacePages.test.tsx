// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { CandidatesPage } from "./CandidatesPage";
import { DashboardPage } from "./DashboardPage";
import { IntegrationsPage } from "./IntegrationsPage";
import { JobsPage } from "./JobsPage";
import { OutreachPage } from "./OutreachPage";
import { ReportsPage } from "./ReportsPage";
import { ScenariosPage } from "./ScenariosPage";
import { TalentMapPage } from "./TalentMapPage";
import { TasksPage } from "./TasksPage";
import { RECENT_TASK_IDS_KEY } from "./projectWorkspace";

function jsonResponse(payload: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const projectPayload = {
  id: "project_2026_ai_team",
  name: "真实后端项目",
  status: "active",
  createdAt: "2026-06-09T00:00:00Z",
  openJobs: 1,
  totalCandidates: 2,
  awaitingHuman: 0,
  averageMatchScore: 86,
};

const activeProjectStorageKey = "zhaoping_active_project_id";

const hannoProjectPayload = {
  id: "project_hanno_ai_hardware",
  name: "汉诺云智招聘",
  status: "active",
  createdAt: "2026-06-10T00:00:00Z",
  openJobs: 1,
  totalCandidates: 0,
  awaitingHuman: 0,
  averageMatchScore: 0,
};

const jobsPayload = [
  {
    id: "job_vla_algorithm",
    projectId: "project_2026_ai_team",
    title: "VLA / 具身智能算法工程师",
    headcount: 2,
    status: "processing",
    pipelineStatus: "processing",
    candidateCount: 2,
    averageMatchScore: 86,
  },
];

const hannoJobsPayload = [
  {
    id: "job_hanno_edge_ai",
    projectId: "project_hanno_ai_hardware",
    title: "边缘 AI 架构师",
    headcount: 1,
    status: "sourcing",
    pipelineStatus: "sourcing",
    candidateCount: 0,
    averageMatchScore: 0,
  },
];

const candidatesPayload = [
  {
    id: "cand_zhou_han",
    jobCandidateId: 1,
    jobId: "job_vla_algorithm",
    jobTitle: "VLA / 具身智能算法工程师",
    name: "Zhou Han",
    sourcePlatform: "GitHub",
    sourceUrl: "https://github.com/example/robot-vla",
    currentCompany: "Robot Foundation Team",
    city: "上海",
    email: "zhou.han@example.com",
    matchScore: 91,
    pipelineStatus: "pending_outreach",
  },
  {
    id: "cand_lin_yu",
    jobCandidateId: 2,
    jobId: "job_vla_algorithm",
    jobTitle: "VLA / 具身智能算法工程师",
    name: "Lin Yu",
    sourcePlatform: "Paper",
    currentCompany: "Embodied AI Lab",
    city: "北京",
    email: null,
    matchScore: 81,
    pipelineStatus: "screening",
  },
];

const integrationsPayload = {
  capabilities: [
    { id: "search_api", service_type: "search", label: "Search API", status: "active", connected: true, code_path: "app/providers/search.py" },
    { id: "llm_api", service_type: "llm", label: "LLM API", status: "active", connected: true, code_path: "app/providers/llm.py" },
    { id: "vector_api", service_type: "vector_store", label: "Vector API", status: "active", connected: true, code_path: "app/providers/vector_store.py" },
  ],
  services: [
    {
      name: "brave_web_search",
      name_zh: "Brave 开放网页搜索",
      type: "search",
      provider: "brave_web",
      status: "available",
      is_default: false,
      code_path: "app/providers/search.py",
    },
    {
      name: "openrouter_auto_reasoning",
      name_zh: "OpenRouter 自动推理",
      type: "llm",
      provider: "openrouter_chat",
      status: "active",
      is_default: true,
      code_path: "app/providers/llm.py",
    },
  ],
};

const reportPayload = {
  reportId: "report_1",
  projectId: "project_2026_ai_team",
  sourceTaskId: "task_report",
  createdAt: "2026-06-09T08:00:00Z",
  content: {
    conclusion: "本周候选人质量稳定。",
    keyProgress: ["已完成 VLA 岗位初筛"],
    topCandidates: ["Zhou Han"],
    risks: ["高分候选人触达节奏需要跟进"],
    nextActions: ["安排技术面"],
  },
};

function renderPage(element: ReactElement) {
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

describe("workspace sidebar pages", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    window.localStorage.clear();
    window.localStorage.setItem(RECENT_TASK_IDS_KEY, JSON.stringify(["task_demo"]));
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/projects") return jsonResponse([projectPayload, hannoProjectPayload]);
      if (url === "/api/projects/project_2026_ai_team") return jsonResponse(projectPayload);
      if (url === "/api/projects/project_2026_ai_team/jobs") return jsonResponse(jobsPayload);
      if (url.startsWith("/api/projects/project_2026_ai_team/candidates")) {
        return jsonResponse(candidatesPayload, 200, {
          "X-Total-Count": String(candidatesPayload.length),
          "X-Has-More": "false",
        });
      }
      if (url === "/api/projects/project_hanno_ai_hardware") return jsonResponse(hannoProjectPayload);
      if (url === "/api/projects/project_hanno_ai_hardware/jobs") return jsonResponse(hannoJobsPayload);
      if (url.startsWith("/api/projects/project_hanno_ai_hardware/candidates")) {
        return jsonResponse([], 200, {
          "X-Total-Count": "0",
          "X-Has-More": "false",
        });
      }
      if (url === "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/upload-resumes") {
        return jsonResponse({ taskId: "task_resume", scenario: "RESUME_IMPORT", status: "processing" });
      }
      if (url === "/api/integrations/status") return jsonResponse(integrationsPayload);
      if (url === "/api/scenarios/meta") {
        return jsonResponse({
          scenarios: [
            { id: "A", name_zh: "岗位分析" },
            { id: "B", name_zh: "找候选人" },
            { id: "C", name_zh: "候选人评估" },
            { id: "D", name_zh: "招聘周报" },
          ],
        });
      }
      if (url === "/api/projects/project_2026_ai_team/reports/latest") return jsonResponse(reportPayload);
      if (url.startsWith("/api/outreach/history")) {
        return jsonResponse({
          items: [
            {
              historyId: "history_1",
              projectId: "project_2026_ai_team",
              candidateId: "cand_zhou_han",
              email: "zhou.han@example.com",
              subject: "沟通 VLA 岗位",
              body: "模拟触达",
              status: "simulated",
              deliveryMode: "simulated",
              createdAt: "2026-06-09T09:00:00Z",
            },
          ],
        });
      }
      if (url === "/api/tasks/task_demo") {
        return jsonResponse({
          task_id: "task_demo",
          scenario_id: "C",
          status: "done",
          current_step: 4,
          total_steps: 4,
          audit_events: [{ type: "done", created_at: "2026-06-09T09:30:00Z" }],
          steps_done: [],
        });
      }
      return jsonResponse({ detail: `Unhandled ${url}` }, 404);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it.each([
    ["工作台", <DashboardPage />, "项目一览"],
    ["岗位分析", <JobsPage />, "岗位列表"],
    ["找候选人", <TalentMapPage />, "来源分布"],
    ["候选人评估", <ScenariosPage />, "候选人评估队列"],
    ["人群筛选", <CandidatesPage />, "候选人结果"],
    ["邮件触达", <OutreachPage />, "可触达候选人"],
    ["招聘周报", <ReportsPage />, "周报输入范围"],
    ["任务记录", <TasksPage />, "最近任务"],
    ["系统设置", <IntegrationsPage />, "能力接入状态"],
  ])("%s renders backend-backed content", async (title, element, marker) => {
    renderPage(element);

    expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    expect(await screen.findByText(marker)).toBeTruthy();
  });

  it("renders a project-management dashboard without development monitor noise", async () => {
    renderPage(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "工作台" })).toBeTruthy();
    expect(await screen.findByLabelText("工作台总览")).toBeTruthy();
    expect(await screen.findByLabelText("项目数量")).toBeTruthy();
    expect(await screen.findByText("项目数量")).toBeTruthy();
    expect((await screen.findByLabelText("项目总数")).textContent).toBe("2");
    expect(await screen.findByText("项目管理")).toBeTruthy();
    expect(await screen.findByText("项目一览")).toBeTruthy();
    expect(screen.queryByText("测试监控")).toBeNull();
    expect(screen.queryByText("一键启动监控")).toBeNull();
    expect(screen.queryByText("开放岗位")).toBeNull();
  });

  it("creates, updates, enters, and deletes projects through real project endpoints", async () => {
    const projectList = [projectPayload, hannoProjectPayload];
    const createdProject = {
      id: "project_new_market",
      name: "新市场项目",
      status: "active",
      createdAt: "2026-06-11T00:00:00Z",
      openJobs: 0,
      totalCandidates: 0,
      awaitingHuman: 0,
      averageMatchScore: 0,
    };
    const updatedProject = { ...projectPayload, name: "真实后端项目更新版", status: "paused" };
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/projects" && (!init || init.method === "GET")) return jsonResponse(projectList);
      if (url === "/api/projects" && init?.method === "POST") {
        projectList.unshift(createdProject);
        return jsonResponse(createdProject, 201);
      }
      if (url === "/api/projects/project_2026_ai_team" && init?.method === "PATCH") {
        projectList.splice(1, 1, updatedProject);
        return jsonResponse(updatedProject);
      }
      if (url === "/api/projects/project_2026_ai_team" && init?.method === "DELETE") {
        const index = projectList.findIndex((project) => project.id === "project_2026_ai_team");
        if (index >= 0) projectList.splice(index, 1);
        return new Response(null, { status: 204 });
      }
      return jsonResponse({ detail: `Unhandled ${url}` }, 404);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage(<DashboardPage />);

    expect((await screen.findAllByText("真实后端项目")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("项目 ID"), { target: { value: "project_new_market" } });
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "新市场项目" } });
    fireEvent.click(screen.getByRole("button", { name: "添加项目" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ id: "project_new_market", name: "新市场项目", status: "active" }),
        }),
      );
    });
    expect((await screen.findAllByText("新市场项目")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "编辑 真实后端项目" }));
    fireEvent.change(screen.getByLabelText("编辑项目名称"), { target: { value: "真实后端项目更新版" } });
    fireEvent.change(screen.getByLabelText("编辑状态"), { target: { value: "paused" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_2026_ai_team",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ name: "真实后端项目更新版", status: "paused" }),
        }),
      );
    });
    expect((await screen.findAllByText("真实后端项目更新版")).length).toBeGreaterThan(0);

    const enterLink = screen.getByRole("link", { name: "进入项目 真实后端项目更新版" });
    expect(enterLink.getAttribute("href")).toBe("/projects/project_2026_ai_team");

    window.localStorage.setItem(activeProjectStorageKey, "project_2026_ai_team");
    fireEvent.click(screen.getByRole("button", { name: "删除 真实后端项目更新版" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_2026_ai_team",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    await waitFor(() => expect(screen.queryByText("真实后端项目更新版")).toBeNull());
    expect(window.localStorage.getItem(activeProjectStorageKey)).toBeNull();
  });

  it("shows concrete backend services on the integrations page", async () => {
    renderPage(<IntegrationsPage />);

    expect(await screen.findByText("服务明细")).toBeTruthy();
    expect(await screen.findByText("brave_web_search")).toBeTruthy();
    expect(await screen.findByText("OpenRouter 自动推理")).toBeTruthy();
    expect(screen.queryByText("email_delivery_api")).toBeNull();
  });

  it("uploads a resume from the candidates page and refreshes backend candidates", async () => {
    renderPage(<CandidatesPage />);

    expect(await screen.findByRole("heading", { name: "人群筛选" })).toBeTruthy();
    const file = new File(["# Lin Chen"], "lin-chen-resume.md", { type: "text/markdown" });
    fireEvent.change(screen.getByLabelText("简历文件"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "上传简历" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/upload-resumes",
        expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      );
    });
    expect(window.localStorage.getItem(RECENT_TASK_IDS_KEY)).toContain("task_resume");
    expect(await screen.findByText("已创建导入任务：task_resume")).toBeTruthy();
  });

  it("loads workspace pages from the active project instead of the default project", async () => {
    window.localStorage.setItem(activeProjectStorageKey, "project_hanno_ai_hardware");

    renderPage(<JobsPage />);

    expect(await screen.findByRole("heading", { name: "岗位分析" })).toBeTruthy();
    expect(await screen.findByText("边缘 AI 架构师")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_hanno_ai_hardware/jobs",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
