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
                search_mode_label: "社媒扩展",
                execution_policy: "deep_live",
                source_layers: { academic: true, social: true, crawler_snapshot: true },
                result_count: 7,
                provider_budget: { selected: 2, skipped: 1 },
                providers: {
                  selected: ["x_recent_posts_search", "agent_reach_social_search"],
                  errors: [{ service: "crustdata_signal_search", reason: "missing_key" }],
                },
                evidence_counts: {
                  recommended_sources: 4,
                  records: 6,
                },
                evidence_gaps: ["网页抓取层需要人工配置或运行工具，当前只能作为待执行线索。"],
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
    expect(screen.getByText("社媒扩展")).toBeTruthy();
    expect(screen.getByText("deep_live")).toBeTruthy();
    expect(screen.getByText("academic / social / crawler_snapshot")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("x_recent_posts_search")).toBeTruthy();
    expect(screen.getByText(/crustdata_signal_search/)).toBeTruthy();
    expect(screen.getByText(/网页抓取层需要人工配置/)).toBeTruthy();
    expect(screen.getByText(/intel_ledger123/)).toBeTruthy();
  });
});
