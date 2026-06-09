import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Candidate } from "../candidates/types";
import { confirmTask, getProject, getProjectCandidates, getProjectJobs, runCandidateEvaluation } from "./api";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
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

  it("confirms a human gate task using the action/data payload contract", async () => {
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
          action: "approve",
          data: { draft: "updated message" },
        }),
      }),
    );
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
});
