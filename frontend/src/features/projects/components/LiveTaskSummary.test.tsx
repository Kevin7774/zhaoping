// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LiveTaskSummary } from "./LiveTaskSummary";

describe("LiveTaskSummary", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows search run trace from audit events", () => {
    render(
      <LiveTaskSummary
        taskId="task_B"
        connectionState="open"
        taskSnapshot={null}
        events={[
          {
            id: 1,
            type: "evidence",
            message: "检索证据生成",
            data: {
              search_run_trace: {
                search_profile: "candidate_sourcing",
                execution_policy: "deep_live",
                source_layers: { academic: true, social: true, code_model: true },
                result_count: 7,
                provider_budget: { selected: 2, skipped: 1 },
                providers: {
                  selected: ["agent_reach_social_search", "github_candidates"],
                  errors: [{ service: "github_code", reason: "deferred_by_live_budget" }],
                },
                evidence_counts: {
                  recommended_sources: 4,
                  records: 6,
                },
                evidence_gaps: ["GitHub code 搜索因预算延后，需要深度联网或提高 provider 预算后复跑。"],
                evidence_ledger: {
                  archive_id: "intel_ledger123",
                  artifact_type: "search_evidence_ledger",
                  status: "archived",
                },
              },
            },
            status: "processing",
          },
        ]}
      />,
    );

    expect(screen.getByText("搜索运行追踪")).toBeTruthy();
    expect(screen.getByText("candidate_sourcing")).toBeTruthy();
    expect(screen.queryByText("社媒扩展")).toBeNull();
    expect(screen.getByText("deep_live")).toBeTruthy();
    expect(screen.getByText("academic / social / code_model")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("agent_reach_social_search")).toBeTruthy();
    expect(screen.getByText(/github_code/)).toBeTruthy();
    expect(screen.getByText(/GitHub code 搜索因预算延后/)).toBeTruthy();
    expect(screen.getByText(/intel_ledger123/)).toBeTruthy();
  });
});
