import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Candidate } from "../candidates/types";
import {
  cancelTask,
  confirmTask,
  createOutreachDraft,
  createSegment,
  getIntegrationsStatus,
  getLatestWeeklyReport,
  getProject,
  getProjectCandidates,
  getProjectCandidatesPage,
  getProjectJobs,
  getOutreachHistory,
  uploadProjectResume,
  retryTask,
  runJobMatch,
  runCandidateEvaluation,
  runProjectScenario,
  runWeeklyReport,
  saveWeeklyReport,
  sendOutreachDraft,
  updateOutreachDraft,
  querySegmentCandidates,
} from "./api";
import type { JobProfile } from "../jobs/types";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function jsonResponseWithHeaders(payload: unknown, headers: Record<string, string>, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("projects api", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads project data from the real backend endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "project_2026_ai_team",
        name: "2026 AI 团队招聘",
        status: "active",
        createdAt: "2026-06-09T00:00:00Z",
        openJobs: 3,
        totalCandidates: 5,
        awaitingHuman: 1,
        averageMatchScore: 84,
      }),
    );

    await expect(getProject("project_2026_ai_team")).resolves.toMatchObject({
      projectId: "project_2026_ai_team",
      name: "2026 AI 团队招聘",
      status: "active",
      updatedAt: "2026-06-09T00:00:00Z",
      openJobs: 3,
      totalCandidates: 5,
      awaitingHuman: 1,
      averageMatchScore: 84,
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project_2026_ai_team", expect.objectContaining({ method: "GET" }));
  });

  it("maps backend jobs into the dashboard job profile shape", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "job_vla_algorithm",
          projectId: "project_2026_ai_team",
          title: "VLA / 具身智能算法工程师",
          headcount: 2,
          status: "processing",
          pipelineStatus: "processing",
          candidateCount: 2,
          averageMatchScore: 85,
        },
      ]),
    );

    const jobs = await getProjectJobs("project_2026_ai_team");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/jobs",
      expect.objectContaining({ method: "GET" }),
    );
    expect(jobs[0]).toMatchObject({
      jobProfileId: "job_vla_algorithm",
      roleName: "VLA / 具身智能算法工程师",
      pipelineStatus: "processing",
      candidateCount: 2,
      averageMatchScore: 85,
    });
    expect(jobs[0].funnel).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: "sourcing", status: "processing" }),
        expect.objectContaining({ key: "evaluation", status: "processing" }),
      ]),
    );
  });

  it("maps backend candidate matches into the candidate table shape", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          id: "cand_lin_chen",
          jobCandidateId: 1,
          jobId: "job_vla_algorithm",
          jobTitle: "VLA / 具身智能算法工程师",
          name: "Alex Chen",
          currentCompany: "Embodied AI Lab",
          city: "深圳",
          email: "alex.chen@example.com",
          matchScore: 92,
          pipelineStatus: "awaiting_human",
        },
      ]),
    );

    const candidates = await getProjectCandidates("project_2026_ai_team");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/candidates",
      expect.objectContaining({ method: "GET" }),
    );
    expect(candidates[0]).toMatchObject({
      candidateId: "cand_lin_chen",
      targetJobProfileId: "job_vla_algorithm",
      pipelineStatus: "awaiting_human",
      title: "VLA / 具身智能算法工程师",
      email: "alex.chen@example.com",
      matchScore: 92,
      stage: "human_gate",
      stepStatus: "awaiting_human",
      outreachStatus: "not_sent",
    });
  });

  it("requests candidate pages with skip and limit query parameters", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await getProjectCandidates("project_2026_ai_team", { skip: 50, limit: 25 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/candidates?skip=50&limit=25",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("reads candidate pagination metadata from response headers", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponseWithHeaders(
        [
          {
            id: "cand_lin_chen",
            jobCandidateId: 1,
            jobId: "job_vla_algorithm",
            jobTitle: "VLA / 具身智能算法工程师",
            name: "Alex Chen",
            currentCompany: "Embodied AI Lab",
            city: "深圳",
            email: "alex.chen@example.com",
            matchScore: 92,
            pipelineStatus: "processing",
          },
        ],
        {
          "X-Total-Count": "51",
          "X-Has-More": "true",
        },
      ),
    );

    await expect(getProjectCandidatesPage("project_2026_ai_team", { skip: 0, limit: 50 })).resolves.toMatchObject({
      total: 51,
      hasMore: true,
      candidates: [expect.objectContaining({ candidateId: "cand_lin_chen" })],
    });
  });

  it("uploads a resume file to the selected project job using multipart form data", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ taskId: "task_resume", scenario: "RESUME_IMPORT", status: "processing" }));
    const file = new File(["# Lin Chen"], "lin-chen-resume.md", { type: "text/markdown" });

    await uploadProjectResume("project_2026_ai_team", "job_vla_algorithm", file);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_2026_ai_team/jobs/job_vla_algorithm/upload-resumes",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      }),
    );
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).has("Content-Type")).toBe(false);
  });

  it("confirms a human gate task using the backend decision/edits/data payload contract", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        task_id: "task_1",
        status: "processing",
        audit_events: [],
      }),
    );

    await confirmTask("task_1", "approve", { draft: "updated message" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task_1/confirm",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          decision: "approve",
          edits: "updated message",
          data: { draft: "updated message" },
        }),
      }),
    );
  });

  it("cancels and retries tasks through real task endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ task_id: "task_1", status: "cancelled", audit_events: [] }))
      .mockResolvedValueOnce(jsonResponse({ task_id: "task_2", scenario: "B", status: "processing" }));

    await cancelTask("task_1");
    await retryTask("task_1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/tasks/task_1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/tasks/task_1/retry",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("loads integration status from the real backend capability endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        capabilities: [{ id: "search_api", service_type: "search", status: "missing_key", connected: false }],
        services: [],
      }),
    );

    await expect(getIntegrationsStatus()).resolves.toMatchObject({
      capabilities: [expect.objectContaining({ id: "search_api", status: "missing_key" })],
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/integrations/status", expect.objectContaining({ method: "GET" }));
  });

  it.each([
    ["job_analysis", "A"],
    ["find_candidates", "B"],
    ["candidate_evaluation", "C"],
  ] as const)("starts %s through /scenarios/run scenario %s", async (action, scenario) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: `task_${scenario}`, scenario, status: "processing" }));
    const job = {
      jobProfileId: "job_vla_algorithm",
      roleName: "VLA / 具身智能算法工程师",
      headcount: 2,
      priorityLevel: "P0",
      isAiNativeFriendly: true,
      essentialCapabilities: [],
      preferredCapabilities: [],
      exclusionTags: [],
      targetCompanyTypes: [],
      targetSchoolsLabs: [],
      salaryRangeMin: 0,
      salaryRangeMax: 0,
      funnel: [],
    } satisfies JobProfile;

    await runProjectScenario("project_2026_ai_team", job, action);

    const [, init] = fetchMock.mock.calls[0];
    expect(fetchMock).toHaveBeenCalledWith("/api/scenarios/run", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(init.body as string)).toMatchObject({
      scenario,
      frontend_state: {
        project_id: "project_2026_ai_team",
        job_profile_id: "job_vla_algorithm",
        job_title: "VLA / 具身智能算法工程师",
        action,
      },
    });
  });

  it("starts weekly report through scenario D", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "task_weekly", scenario: "D", status: "processing" }));

    await runWeeklyReport("project_2026_ai_team", "2026 AI 团队招聘");

    const [, init] = fetchMock.mock.calls[0];
    expect(fetchMock).toHaveBeenCalledWith("/api/scenarios/run", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(init.body as string)).toMatchObject({
      scenario: "D",
      frontend_state: {
        project_id: "project_2026_ai_team",
        action: "weekly_report",
      },
    });
  });

  it("starts candidate evaluation with candidate and job identifiers", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        task_id: "task_candidate_eval",
        scenario: "C",
        status: "processing",
      }),
    );
    const candidate = {
      candidateId: "cand_zhou_han",
      name: "Zhou Han",
      targetJobProfileId: "job_vla_algorithm",
      title: "VLA / 具身智能算法工程师",
      currentCompany: "Robot Foundation Team",
      city: "上海",
    } as Candidate;

    await runCandidateEvaluation("project_2026_ai_team", candidate);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/scenarios/run",
      expect.objectContaining({
        method: "POST",
      }),
    );
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toMatchObject({
      scenario: "C",
      frontend_state: {
        source: "CandidateTable",
        project_id: "project_2026_ai_team",
        candidate_id: "cand_zhou_han",
        candidateId: "cand_zhou_han",
        job_id: "job_vla_algorithm",
        jobId: "job_vla_algorithm",
        action: "candidate_evaluation",
      },
    });
  });

  it("uses backend generated outreach drafts, editable drafts, send, and history endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          draftId: "draft_1",
          projectId: "project_2026_ai_team",
          jobId: "job_vla_algorithm",
          candidateId: "cand_zhou_han",
          subject: "沟通邀请",
          body: "后端草稿",
          status: "draft",
          backendGenerated: true,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          draftId: "draft_1",
          subject: "更新主题",
          body: "更新正文",
          status: "draft",
          backendGenerated: true,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          historyId: "history_1",
          draftId: "draft_1",
          status: "simulated",
          deliveryMode: "simulated",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ items: [{ historyId: "history_1", status: "simulated" }] }));

    await createOutreachDraft({
      projectId: "project_2026_ai_team",
      jobId: "job_vla_algorithm",
      candidateId: "cand_zhou_han",
    });
    await updateOutreachDraft("draft_1", { subject: "更新主题", body: "更新正文" });
    await sendOutreachDraft({ draftId: "draft_1", decision: "approve", simulate: true });
    await getOutreachHistory({ projectId: "project_2026_ai_team" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/outreach/draft",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          projectId: "project_2026_ai_team",
          jobId: "job_vla_algorithm",
          candidateId: "cand_zhou_han",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/outreach/drafts/draft_1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ subject: "更新主题", body: "更新正文" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/outreach/send",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ draftId: "draft_1", decision: "approve", simulate: true }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/outreach/history?projectId=project_2026_ai_team",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("uses backend segment query, save, and list endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ candidates: [], total: 0, criteria: { minScore: 80 } }))
      .mockResolvedValueOnce(
        jsonResponse({
          segmentId: "segment_1",
          projectId: "project_2026_ai_team",
          name: "高匹配人群",
          candidateIds: ["cand_zhou_han"],
          candidateCount: 1,
        }),
      );

    await querySegmentCandidates("project_2026_ai_team", { jobProfileId: "all", minScore: 80, city: "", keyword: "", outreachStatus: "all", hasEmail: "yes", sourcePlatform: "all" });
    await createSegment({
      projectId: "project_2026_ai_team",
      name: "高匹配人群",
      criteria: { jobProfileId: "all", minScore: 80, city: "", keyword: "", outreachStatus: "all", hasEmail: "yes", sourcePlatform: "all" },
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/segments/query",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({
      projectId: "project_2026_ai_team",
      criteria: { minScore: 80, hasEmail: "yes" },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/segments",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("persists and reloads weekly reports through backend report endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          reportId: "report_1",
          projectId: "project_2026_ai_team",
          content: { conclusion: "真实周报", keyProgress: [], topCandidates: [], risks: [], nextActions: [] },
          sourceTaskId: "task_weekly",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          reportId: "report_1",
          projectId: "project_2026_ai_team",
          content: { conclusion: "真实周报", keyProgress: [], topCandidates: [], risks: [], nextActions: [] },
        }),
      );

    await saveWeeklyReport("project_2026_ai_team", "task_weekly", {
      conclusion: "真实周报",
      keyProgress: [],
      topCandidates: [],
      risks: [],
      nextActions: [],
    });
    await getLatestWeeklyReport("project_2026_ai_team");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/reports/weekly",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          projectId: "project_2026_ai_team",
          sourceTaskId: "task_weekly",
          report: {
            conclusion: "真实周报",
            keyProgress: [],
            topCandidates: [],
            risks: [],
            nextActions: [],
          },
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/project_2026_ai_team/reports/latest",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("calls the existing jobs match endpoint without frontend generated scores", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ results: [{ candidate_id: "cand_1", score: 0.82 }] }));

    await expect(runJobMatch("VLA / 具身智能算法工程师", 5)).resolves.toEqual({
      results: [{ candidate_id: "cand_1", score: 0.82 }],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs/match",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "VLA / 具身智能算法工程师", top_k: 5 }),
      }),
    );
  });
});
