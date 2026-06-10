// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ProjectDetailPage } from "./ProjectDetailPage";

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
  totalCandidates: 1,
  awaitingHuman: 0,
  averageMatchScore: 81,
};

const jobsPayload = [
  {
    id: "job_vla_algorithm",
    projectId: "project_2026_ai_team",
    title: "VLA / 具身智能算法工程师",
    headcount: 2,
    status: "processing",
    pipelineStatus: "processing",
    candidateCount: 1,
    averageMatchScore: 81,
  },
];

const candidatesPayload = [
  {
    id: "cand_zhou_han",
    jobCandidateId: 1,
    jobId: "job_vla_algorithm",
    jobTitle: "VLA / 具身智能算法工程师",
    name: "Zhou Han",
    currentCompany: "Robot Foundation Team",
    city: "上海",
    email: "zhou.han@example.com",
    matchScore: 88,
    pipelineStatus: "pending_outreach",
  },
];

function integrationsPayload(overrides: Record<string, string> = {}) {
  const statusFor = (id: string) => overrides[id] ?? "active";
  return {
    capabilities: [
      { id: "search_api", service_type: "search", status: statusFor("search_api"), connected: statusFor("search_api") === "active" },
      { id: "llm_api", service_type: "llm", status: statusFor("llm_api"), connected: statusFor("llm_api") === "active" },
      {
        id: "embedding_api",
        service_type: "embedding",
        status: statusFor("embedding_api"),
        connected: statusFor("embedding_api") === "active",
      },
      {
        id: "vector_api",
        service_type: "vector_store",
        status: statusFor("vector_api"),
        connected: statusFor("vector_api") === "active",
      },
      {
        id: "database_api",
        service_type: "database",
        status: statusFor("database_api"),
        connected: statusFor("database_api") === "active",
      },
      {
        id: "segments.query",
        service_type: "segments.query",
        status: statusFor("segments.query"),
        connected: statusFor("segments.query") === "active",
      },
      {
        id: "segments.create",
        service_type: "segments.create",
        status: statusFor("segments.create"),
        connected: statusFor("segments.create") === "active",
      },
      {
        id: "segments.read",
        service_type: "segments.read",
        status: statusFor("segments.read"),
        connected: statusFor("segments.read") === "active",
      },
      {
        id: "email_delivery_api",
        service_type: "email_delivery",
        status: statusFor("email_delivery_api"),
        connected: statusFor("email_delivery_api") === "active",
      },
    ],
    services: [],
  };
}

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (message: MessageEvent<string>) => void>();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener as (message: MessageEvent<string>) => void);
  }

  emit(type: string, payload: unknown) {
    this.listeners.get(type)?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

function renderProjectPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/project_2026_ai_team"]}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectDetailPage backend hardening", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    MockEventSource.instances = [];
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function mockBackend(options: {
    candidates?: unknown[];
    candidateResponses?: unknown[][];
    schedules?: unknown[];
    scheduleResponse?: unknown;
    updatedSchedule?: unknown;
    projectStatus?: number;
    integrations?: Record<string, string>;
    latestReport?: unknown;
    taskSnapshots?: Record<string, unknown>;
  } = {}) {
    let candidateResponseIndex = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/integrations/status") return jsonResponse(integrationsPayload(options.integrations));
      if (url === "/api/projects/project_2026_ai_team") return jsonResponse(projectPayload, options.projectStatus ?? 200);
      if (url === "/api/projects/project_2026_ai_team/jobs") return jsonResponse(jobsPayload);
      if (url === "/api/projects/project_2026_ai_team/preview-from-bp") {
        return jsonResponse({
          projectId: "project_2026_ai_team",
          projectName: "真实后端项目",
          promptName: "bp_pipeline_v1",
          jobCount: 14,
          jobs: [
            {
              id: "job_edge_ai_architect",
              projectId: "project_2026_ai_team",
              title: "边缘 AI 架构师",
              headcount: 1,
              status: "sourcing",
              pipelineStatus: "sourcing",
              candidateCount: 0,
              averageMatchScore: 0,
            },
          ],
          industryReading: "边缘 AI 项目",
          technicalAssumptions: ["需要云边协同"],
          coverageGaps: [],
        });
      }
      if (url === "/api/projects/project_2026_ai_team/initialize-from-bp") {
        return jsonResponse({
          projectId: "project_2026_ai_team",
          projectName: "真实后端项目",
          promptName: "bp_pipeline_v1",
          jobCount: 14,
          jobs: [
            {
              id: "job_edge_ai_architect",
              projectId: "project_2026_ai_team",
              title: "边缘 AI 架构师",
              headcount: 1,
              status: "sourcing",
              pipelineStatus: "sourcing",
              candidateCount: 0,
              averageMatchScore: 0,
            },
          ],
          industryReading: "边缘 AI 项目",
          technicalAssumptions: ["需要云边协同"],
          coverageGaps: [],
        });
      }
      if (url === "/api/projects/project_2026_ai_team/candidate-search-schedules") {
        if (options.scheduleResponse !== undefined) return jsonResponse(options.scheduleResponse);
        return jsonResponse({ items: options.schedules ?? [] });
      }
      if (url === "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule") {
        const body = JSON.parse(String(init?.body));
        return jsonResponse(
          options.updatedSchedule ?? {
            id: 1,
            projectId: "project_2026_ai_team",
            jobId: "job_vla_algorithm",
            jobTitle: "VLA / 具身智能算法工程师",
            enabled: body.enabled,
            intervalMinutes: body.intervalMinutes,
            nextRunAt: body.enabled ? "2026-06-09T12:00:00Z" : null,
            lastTaskId: null,
            lastStatus: null,
          },
        );
      }
      if (url === "/api/projects/project_2026_ai_team/reports/latest") {
        return options.latestReport
          ? jsonResponse(options.latestReport)
          : jsonResponse({ detail: "Weekly report not found for project: project_2026_ai_team" }, 404);
      }
      if (url.startsWith("/api/projects/project_2026_ai_team/candidates")) {
        const candidates =
          options.candidateResponses?.[
            Math.min(candidateResponseIndex++, Math.max(0, options.candidateResponses.length - 1))
          ] ??
          options.candidates ??
          candidatesPayload;
        return jsonResponse(candidates, 200, {
          "X-Total-Count": String(candidates.length),
          "X-Has-More": "false",
        });
      }
      if (url === "/api/outreach/draft") {
        return jsonResponse({
          draftId: "draft_backend_1",
          projectId: "project_2026_ai_team",
          jobId: "job_vla_algorithm",
          candidateId: "cand_zhou_han",
          subject: "后端生成主题",
          body: "后端生成邮件草稿",
          status: "draft",
          backendGenerated: true,
        });
      }
      if (url === "/api/outreach/drafts/draft_backend_1") {
        const body = JSON.parse(String(init?.body));
        return jsonResponse({
          draftId: "draft_backend_1",
          subject: body.subject,
          body: body.body,
          status: "draft",
          backendGenerated: true,
        });
      }
      if (url === "/api/outreach/send") {
        const body = JSON.parse(String(init?.body));
        const simulated = Boolean(body.simulate);
        return jsonResponse({
          historyId: "history_1",
          draftId: "draft_backend_1",
          status: simulated ? "simulated" : "sent",
          deliveryMode: simulated ? "simulated" : "real",
          providerStatus: simulated ? "simulated" : "mailtrap_smtp_email:sent",
        });
      }
      if (url.startsWith("/api/outreach/history")) return jsonResponse({ items: [] });
      if (url === "/api/segments/query") {
        return jsonResponse({
          projectId: "project_2026_ai_team",
          criteria: JSON.parse(String(init?.body)).criteria,
          total: 1,
          candidates: candidatesPayload,
        });
      }
      if (url === "/api/segments") {
        return jsonResponse({
          segmentId: "segment_1",
          projectId: "project_2026_ai_team",
          name: "当前筛选目标人群",
          criteria: JSON.parse(String(init?.body)).criteria,
          candidateIds: ["cand_zhou_han"],
          candidateCount: 1,
        });
      }
      if (url === "/api/reports/weekly") {
        return jsonResponse({
          reportId: "report_1",
          projectId: "project_2026_ai_team",
          sourceTaskId: "task_D",
          content: { conclusion: "后端保存周报", keyProgress: [], topCandidates: [], risks: [], nextActions: [] },
        });
      }
      if (url === "/api/jobs/match") {
        return jsonResponse({ results: [{ candidate_id: "cand_zhou_han", score: 0.87, reason: "后端返回匹配结果" }] });
      }
      if (url === "/api/scenarios/run") {
        const body = JSON.parse(String(init?.body));
        return jsonResponse({
          task_id: `task_${body.scenario}`,
          scenario: body.scenario,
          status: "processing",
        });
      }
      if (url === "/api/tasks/task_C/confirm") {
        return jsonResponse({
          task_id: "task_C",
          status: "processing",
          audit_events: [],
        });
      }
      if (url.startsWith("/api/tasks/task_")) {
        const taskId = url.split("/").at(-1) ?? "";
        return jsonResponse(options.taskSnapshots?.[taskId] ?? { task_id: taskId, status: "processing", audit_events: [] });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
  }

  it("loads project, job, and candidate data from real backend endpoints", async () => {
    mockBackend();

    renderProjectPage();

    expect(await screen.findByRole("heading", { name: "真实后端项目" })).toBeTruthy();
    expect(screen.getAllByText("VLA / 具身智能算法工程师").length).toBeGreaterThan(0);
    expect(screen.getByText("Zhou Han")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project_2026_ai_team", expect.objectContaining({ method: "GET" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project_2026_ai_team/jobs", expect.objectContaining({ method: "GET" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/candidates?skip=0&limit=50",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("previews BP generated roles before confirming overwrite", async () => {
    mockBackend();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderProjectPage();

    expect(await screen.findByRole("heading", { name: "真实后端项目" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "预览岗位矩阵" }));

    expect(await screen.findByText("边缘 AI 架构师")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认覆盖岗位" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_2026_ai_team/initialize-from-bp",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("sends prompt and industry research context when generating project roles", async () => {
    mockBackend();

    renderProjectPage();

    expect(await screen.findByRole("heading", { name: "真实后端项目" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "岗位智能生成" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("项目提示词"), {
      target: { value: "我要为工业质检边缘 AI 项目生成岗位，覆盖算法、硬件、交付和客户成功。" },
    });
    fireEvent.change(screen.getByLabelText("行业研究偏好"), {
      target: { value: "重点关注工业质检、边缘盒子、现场交付、数据闭环和政企合规。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预览岗位矩阵" }));

    await waitFor(() => {
      const previewCall = fetchMock.mock.calls.find(([url]) => url === "/api/projects/project_2026_ai_team/preview-from-bp");
      expect(previewCall).toBeTruthy();
      expect(JSON.parse(String(previewCall?.[1]?.body))).toMatchObject({
        generationMode: "bp_plus_prompt",
        projectPrompt: "我要为工业质检边缘 AI 项目生成岗位，覆盖算法、硬件、交付和客户成功。",
        industryResearchPrompt: "重点关注工业质检、边缘盒子、现场交付、数据闭环和政企合规。",
      });
    });
  });

  it("shows the candidate empty state when the backend returns an empty candidate array", async () => {
    mockBackend({ candidates: [] });

    renderProjectPage();

    expect(await screen.findByText("暂无候选人，运行找候选人后会显示在这里")).toBeTruthy();
  });

  it("shows an error state when backend project loading fails", async () => {
    mockBackend({ projectStatus: 500 });

    renderProjectPage();

    expect(await screen.findByText("HTTP 500")).toBeTruthy();
    expect(screen.queryByText("真实后端项目")).toBeNull();
  });

  it("starts job analysis with scenario A and opens the task stream", async () => {
    mockBackend();

    renderProjectPage();

    fireEvent.click(await screen.findByRole("button", { name: "岗位分析" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/scenarios/run", expect.objectContaining({ method: "POST" })));
    const scenarioCall = fetchMock.mock.calls.find(([url]) => url === "/api/scenarios/run");
    expect(JSON.parse(String(scenarioCall?.[1]?.body))).toMatchObject({
      scenario: "A",
      frontend_state: {
        project_id: "project_2026_ai_team",
        job_profile_id: "job_vla_algorithm",
        job_title: "VLA / 具身智能算法工程师",
        action: "job_analysis",
      },
    });
    await waitFor(() => expect(MockEventSource.instances[0]?.url).toBe("/api/tasks/task_A/stream"));
  });

  it("disables candidate search when search capability is missing a key", async () => {
    mockBackend({ integrations: { search_api: "missing_key" } });

    renderProjectPage();

    const button = await screen.findByRole("button", { name: "找候选人" });
    expect(button).toHaveProperty("disabled", true);
    expect(button.getAttribute("title")).toContain("缺少 Key");
  });

  it("lets the user choose a search mode and sends provider preflight with candidate search", async () => {
    mockBackend();

    renderProjectPage();

    await screen.findByRole("heading", { name: "真实后端项目" });
    fireEvent.change(screen.getByLabelText("搜索模式"), { target: { value: "social_expansion" } });
    fireEvent.click(screen.getByRole("button", { name: "找候选人" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/scenarios/run", expect.objectContaining({ method: "POST" })));
    const scenarioCall = fetchMock.mock.calls.find(([url]) => url === "/api/scenarios/run");
    const body = JSON.parse(String(scenarioCall?.[1]?.body));
    expect(body).toMatchObject({
      scenario: "B",
      frontend_state: {
        search_mode: "social_expansion",
        action_explainability: {
          actionId: "project.find_candidates",
          apiRoute: "POST /scenarios/run",
        },
      },
    });
    expect(body.frontend_state.provider_preflight.length).toBeGreaterThan(0);
    expect(await screen.findByText(/动作解释：找候选人/)).toBeTruthy();
  });

  it("shows lead ingestion stats and refreshes candidates from the backend after candidate search", async () => {
    const refreshedCandidates = [
      ...candidatesPayload,
      {
        id: "cand_lead_alice",
        jobCandidateId: 2,
        jobId: "job_vla_algorithm",
        jobTitle: "VLA / 具身智能算法工程师",
        name: "Alice Wang",
        currentCompany: "Open Robotics",
        city: "深圳",
        email: "alice@example.com",
        sourcePlatform: "github_repositories",
        sourceUrl: "https://github.com/alicewang/robot-vla",
        evidence: ["Maintains robot-vla with diffusion policy examples."],
        matchScore: 91,
        pipelineStatus: "sourced",
      },
    ];
    mockBackend({
      candidateResponses: [candidatesPayload, refreshedCandidates],
      taskSnapshots: {
        task_B: {
          task_id: "task_B",
          status: "done",
          result: {
            lead_ingestion: {
              found: 2,
              normalized: 2,
              inserted_candidates: 1,
              updated_candidates: 0,
              linked_job_candidates: 1,
              duplicates: 1,
              rejected: 0,
              rejected_reasons: {},
              source_task_id: "task_B",
            },
          },
          audit_events: [],
        },
      },
    });

    renderProjectPage();

    await screen.findByRole("heading", { name: "真实后端项目" });
    expect(screen.queryByText("Alice Wang")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "找候选人" }));

    expect(await screen.findByText("候选人线索入库")).toBeTruthy();
    expect(screen.getByText("新增候选人")).toBeTruthy();
    expect(screen.getByText("关联岗位")).toBeTruthy();
    expect(await screen.findByText("Alice Wang")).toBeTruthy();
    const candidateApiCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).startsWith("/api/projects/project_2026_ai_team/candidates"),
    );
    expect(candidateApiCalls.length).toBeGreaterThanOrEqual(2);
  });

  it("configures automatic candidate search through backend schedule API", async () => {
    mockBackend({
      schedules: [
        {
          id: 1,
          projectId: "project_2026_ai_team",
          jobId: "job_vla_algorithm",
          jobTitle: "VLA / 具身智能算法工程师",
          enabled: false,
          intervalMinutes: 360,
          nextRunAt: null,
          lastTaskId: null,
          lastStatus: null,
        },
      ],
    });

    renderProjectPage();

    expect(await screen.findByText("自动搜候选人")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "开启自动搜索 VLA / 具身智能算法工程师" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const updateCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/candidate-search-schedule" &&
        init?.method === "PUT",
    );
    expect(JSON.parse(String(updateCall?.[1]?.body))).toMatchObject({
      enabled: true,
      intervalMinutes: 360,
    });
    expect(await screen.findByText("自动搜候选人已开启")).toBeTruthy();
  });

  it("does not crash when automatic search schedule response has no items", async () => {
    mockBackend({ scheduleResponse: {} });

    renderProjectPage();

    expect(await screen.findByRole("heading", { name: "真实后端项目" })).toBeTruthy();
    expect(screen.getByText("自动搜候选人")).toBeTruthy();
    expect(screen.getByRole("button", { name: "开启自动搜索 VLA / 具身智能算法工程师" })).toBeTruthy();
  });

  it("starts candidate evaluation and weekly report through backend scenarios", async () => {
    mockBackend();

    renderProjectPage();

    await screen.findByRole("button", { name: "岗位分析" });
    fireEvent.click(screen.getAllByRole("button", { name: "候选人评估" })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: "生成周报" })[0]);

    await waitFor(() => {
      const scenarioBodies = fetchMock.mock.calls
        .filter(([url]) => url === "/api/scenarios/run")
        .map(([, init]) => JSON.parse(String(init?.body)));
      expect(scenarioBodies).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ scenario: "C" }),
          expect.objectContaining({ scenario: "D" }),
        ]),
      );
    });
  });

  it("persists a completed weekly report task result with backend Chinese fields", async () => {
    mockBackend({
      taskSnapshots: {
        task_D: {
          task_id: "task_D",
          status: "done",
          result: {
            本周招聘结论: "本周真实后端周报结论",
            关键岗位进展: ["岗位画像已更新"],
            "Top 候选人": ["Zhou Han"],
            招聘风险: ["证据链需要补齐"],
            下周行动建议: ["继续推进人工校准"],
            human_report: {
              title: "招聘周报",
              summary: [{ text: "human_report 摘要" }],
            },
          },
          audit_events: [],
        },
      },
    });

    renderProjectPage();

    await screen.findByRole("heading", { name: "真实后端项目" });
    fireEvent.click(screen.getAllByRole("button", { name: "生成周报" })[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/reports/weekly", expect.objectContaining({ method: "POST" })));
    const saveCall = fetchMock.mock.calls.find(([url]) => url === "/api/reports/weekly");
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
      projectId: "project_2026_ai_team",
      sourceTaskId: "task_D",
      report: {
        conclusion: "本周真实后端周报结论",
        keyProgress: ["岗位画像已更新"],
        topCandidates: ["Zhou Han"],
        risks: ["证据链需要补齐"],
        nextActions: ["继续推进人工校准"],
      },
    });
  });

  it("shows an explicit error when a completed weekly report task cannot be parsed", async () => {
    mockBackend({
      taskSnapshots: {
        task_D: {
          task_id: "task_D",
          status: "done",
          result: {
            message: "任务完成但未返回周报结构",
          },
          audit_events: [],
        },
      },
    });

    renderProjectPage();

    await screen.findByRole("heading", { name: "真实后端项目" });
    fireEvent.click(screen.getAllByRole("button", { name: "生成周报" })[0]);

    expect(await screen.findByText(/周报解析失败/)).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/reports/weekly")).toBe(false);
  });

  it("opens HumanGate from an awaiting task snapshot and confirms through the task API", async () => {
    mockBackend({
      taskSnapshots: {
        task_C: {
          task_id: "task_C",
          status: "awaiting_human",
          awaiting: {
            prompt: "AI 已生成候选人评估，请确认是否推进。",
            draft: {
              candidate_name: "Zhou Han",
              body: "候选人评估报告",
            },
          },
          audit_events: [],
        },
      },
    });

    renderProjectPage();

    await screen.findByRole("button", { name: "岗位分析" });
    const candidateEvaluationButtons = screen.getAllByRole("button", { name: "候选人评估" });
    fireEvent.click(candidateEvaluationButtons.at(-1)!);

    expect(await screen.findByRole("heading", { name: "人工确认" })).toBeTruthy();
    expect(screen.getAllByText("Zhou Han").length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("button", { name: "通过" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task_C/confirm", expect.objectContaining({ method: "POST" })),
    );
  });

  it("uses backend generated email drafts and sends real email when delivery is connected", async () => {
    mockBackend();

    renderProjectPage();

    fireEvent.click(await screen.findByRole("button", { name: "生成草稿" }));
    expect(await screen.findByText("后端生成")).toBeTruthy();
    expect(screen.getByDisplayValue("后端生成主题")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认草稿" }));
    fireEvent.click(screen.getByRole("button", { name: "通过" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/outreach/draft", expect.objectContaining({ method: "POST" }));
      expect(fetchMock).toHaveBeenCalledWith("/api/outreach/drafts/draft_backend_1", expect.objectContaining({ method: "PATCH" }));
      expect(fetchMock).toHaveBeenCalledWith("/api/outreach/send", expect.objectContaining({ method: "POST" }));
    });
    const sendCall = fetchMock.mock.calls.find(([url]) => url === "/api/outreach/send");
    expect(JSON.parse(String(sendCall?.[1]?.body))).toMatchObject({
      draftId: "draft_backend_1",
      decision: "approve",
      simulate: false,
    });
    expect(await screen.findByText("真实邮件已发送，并写入触达历史。")).toBeTruthy();
  });

  it("queries and saves target segments through backend segment endpoints", async () => {
    mockBackend();

    renderProjectPage();

    fireEvent.click(await screen.findByRole("button", { name: "查询目标人群" }));
    expect(await screen.findByText("后端筛选命中 1 人，可保存为目标人群。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存目标人群" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/segments/query", expect.objectContaining({ method: "POST" }));
      expect(fetchMock).toHaveBeenCalledWith("/api/segments", expect.objectContaining({ method: "POST" }));
    });
    expect(await screen.findByText("已保存目标人群 segment_1，可用于后续触达。")).toBeTruthy();
  });

  it("allows Segment save when segments.create is active even if database_api is disabled", async () => {
    mockBackend({ integrations: { database_api: "disabled", "segments.create": "active" } });

    renderProjectPage();

    fireEvent.click(await screen.findByRole("button", { name: "查询目标人群" }));
    expect(await screen.findByText("后端筛选命中 1 人，可保存为目标人群。")).toBeTruthy();
    const saveButton = screen.getByRole("button", { name: "保存目标人群" });
    expect((saveButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/segments", expect.objectContaining({ method: "POST" }));
    });
    expect(await screen.findByText("已保存目标人群 segment_1，可用于后续触达。")).toBeTruthy();
  });

  it("loads the latest persisted weekly report from the backend", async () => {
    mockBackend({
      latestReport: {
        reportId: "report_1",
        projectId: "project_2026_ai_team",
        content: {
          conclusion: "页面刷新后仍可见的真实周报",
          keyProgress: ["后端持久化进展"],
          topCandidates: [],
          risks: [],
          nextActions: [],
        },
      },
    });

    renderProjectPage();

    expect(await screen.findByText("页面刷新后仍可见的真实周报")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/reports/latest",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("runs job matching through /jobs/match and displays only backend results", async () => {
    mockBackend();

    renderProjectPage();

    fireEvent.click(await screen.findByRole("button", { name: "岗位匹配" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/jobs/match", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByText(/后端返回匹配结果/)).toBeTruthy();
  });
});
