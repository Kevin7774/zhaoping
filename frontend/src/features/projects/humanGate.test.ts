import { describe, expect, it } from "vitest";

import { humanGateRequestFromEvent } from "./humanGate";
import type { TaskStreamEvent } from "../../shared/hooks/useTaskStream";

describe("human gate request helpers", () => {
  it("creates a modal request from the latest human_gate stream event", () => {
    const event: TaskStreamEvent = {
      id: 7,
      type: "human_gate",
      message: "流程暂停，等待人工确认：已生成触达邮件",
      data: {
        awaiting: {
          prompt: "已为您生成候选人 Alex 的触达邮件草稿",
          draft: {
            candidate_name: "Alex Chen",
            body: "Hi Alex, let's talk.",
          },
        },
      },
      status: "awaiting_human",
    };

    expect(humanGateRequestFromEvent(event, "task_1")).toEqual({
      eventKey: "7",
      taskId: "task_1",
      context: "已为您生成候选人 Alex 的触达邮件草稿",
      draft: "Hi Alex, let's talk.",
      candidateName: "Alex Chen",
    });
  });

  it("ignores non-human-gate events", () => {
    expect(humanGateRequestFromEvent({ id: 8, type: "summary", message: "done" }, "task_1")).toBeNull();
  });

  it("keeps Scenario B lead preview for non-blind HumanGate approval", () => {
    const event: TaskStreamEvent = {
      id: 9,
      type: "human_gate",
      message: "流程暂停，等待人工确认：请确认待入库线索",
      data: {
        awaiting: {
          prompt: "确认后将把这些线索写入项目候选人库。",
          requires_lead_preview: true,
          lead_preview: {
            total_count: 1,
            omitted_count: 0,
            search_trace: {
              query: "robotics VLA",
              services: ["github_repositories", "github_code"],
              result_count: 3,
              errors: [{ service: "github_code", reason: "deferred_by_live_budget" }],
              research_layers: [
                {
                  id: "people_network",
                  name_zh: "人才网络",
                  purpose: "从人员库、作者网络和开源/社媒身份定位可触达候选人。",
                  services: ["github_repositories", "github_code"],
                  result_count: 3,
                  error_count: 1,
                },
              ],
            },
            leads: [
              {
                name: "Alice Wang",
                source_platform: "github_repositories",
                source_url: "https://github.com/alicewang/robot-vla",
                evidence_summary: "Maintains robot-vla with diffusion policy examples.",
                confidence: 0.86,
                github_score: 91,
                representative_repositories: [
                  {
                    full_name: "alice-robotics/agentic-rag-robot",
                    url: "https://github.com/alice-robotics/agentic-rag-robot",
                    language: "TypeScript",
                    stars: 860,
                    forks: 74,
                    topics: ["agentic-workflow", "rag", "mcp"],
                  },
                ],
                repository_evidence: [
                  {
                    source: "code",
                    title: "alice-robotics/agentic-rag-robot:src/workflow.ts",
                    url: "https://github.com/alice-robotics/agentic-rag-robot/blob/main/src/workflow.ts",
                    snippet: "createAgenticWorkflow({ mcp, rag, fullstack })",
                  },
                ],
                recent_activity: {
                  recent_repository_count: 2,
                  latest_repository_pushed_at: "2026-06-01T12:00:00Z",
                },
                matched_job: "VLA / 具身智能算法工程师",
                compliance_status: "clear",
                ingestion_action: "insert",
              },
            ],
          },
          draft: {
            "触达话术": "技术切磋",
          },
        },
      },
      status: "awaiting_human",
    };

    const request = humanGateRequestFromEvent(event, "task_B");

    expect(request?.requiresLeadPreview).toBe(true);
    expect(request?.leadPreview?.totalCount).toBe(1);
    expect(request?.leadPreview?.searchTrace).toMatchObject({
      query: "robotics VLA",
      services: ["github_repositories", "github_code"],
      resultCount: 3,
      researchLayers: [
        {
          id: "people_network",
          nameZh: "人才网络",
          resultCount: 3,
          errorCount: 1,
        },
      ],
    });
    expect(request?.leadPreview?.leads[0]).toMatchObject({
      name: "Alice Wang",
      sourcePlatform: "github_repositories",
      evidenceSummary: "Maintains robot-vla with diffusion policy examples.",
      githubScore: 91,
      representativeRepositories: [
        {
          fullName: "alice-robotics/agentic-rag-robot",
          url: "https://github.com/alice-robotics/agentic-rag-robot",
          language: "TypeScript",
          stars: 860,
          forks: 74,
          topics: ["agentic-workflow", "rag", "mcp"],
        },
      ],
      repositoryEvidence: [
        {
          source: "code",
          title: "alice-robotics/agentic-rag-robot:src/workflow.ts",
          url: "https://github.com/alice-robotics/agentic-rag-robot/blob/main/src/workflow.ts",
          snippet: "createAgenticWorkflow({ mcp, rag, fullstack })",
        },
      ],
      recentActivity: {
        recentRepositoryCount: 2,
        latestRepositoryPushedAt: "2026-06-01T12:00:00Z",
      },
      ingestionAction: "insert",
    });
  });
});
