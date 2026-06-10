// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HumanConfirmModal } from "./HumanConfirmModal";

describe("HumanConfirmModal", () => {
  afterEach(() => {
    cleanup();
  });

  it("lets HR edit the draft and approve it", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();

    render(
      <HumanConfirmModal
        open
        busy={false}
        context="已为您生成候选人 Alex 的触达邮件草稿"
        draft="Hi Alex"
        candidateName="Alex Chen"
        onApprove={onApprove}
        onReject={onReject}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("已为您生成候选人 Alex 的触达邮件草稿")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "确认继续" })).toBeTruthy();
    expect(screen.queryByText(/AI|决策/)).toBeNull();
    expect(screen.queryByLabelText("调整内容")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "调整" }));
    const textarea = screen.getByLabelText("调整内容");
    fireEvent.change(textarea, { target: { value: "Hi Alex, updated." } });
    fireEvent.click(screen.getByRole("button", { name: "保存并继续" }));

    expect(onApprove).toHaveBeenCalledWith("Hi Alex, updated.", "edit");
    expect(onReject).not.toHaveBeenCalled();
  });

  it("can reject the human gate without approving the draft", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();

    render(
      <HumanConfirmModal
        open
        busy={false}
        context="边缘情况需要人工确认"
        draft="Risk note"
        onApprove={onApprove}
        onReject={onReject}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "暂不推进" }));

    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("shows Scenario B lead preview before allowing ingestion approval", () => {
    const onApprove = vi.fn();

    render(
      <HumanConfirmModal
        open
        busy={false}
        context="请确认目标公司与触达策略，可通过或填写调整意见。"
        draft="{}"
        requiresLeadPreview
        leadPreview={{
          totalCount: 2,
          omittedCount: 1,
          leads: [
            {
              name: "Alice Wang",
              sourcePlatform: "github_repositories",
              sourceUrl: "https://github.com/alicewang/robot-vla",
              evidenceSummary: "Maintains robot-vla with diffusion policy examples.",
              confidence: 0.86,
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
              matchedJob: "VLA / 具身智能算法工程师",
              complianceStatus: "clear",
              ingestionAction: "insert",
            },
          ],
        }}
        onApprove={onApprove}
        onReject={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("即将入库的候选线索")).toBeTruthy();
    expect(screen.getByText("Alice Wang")).toBeTruthy();
    expect(screen.getByText("github_repositories")).toBeTruthy();
    expect(screen.getByText("GitHub 91")).toBeTruthy();
    expect(screen.getByText("alice-robotics/agentic-rag-robot")).toBeTruthy();
    expect(screen.getByText("TypeScript · 860 stars · 74 forks")).toBeTruthy();
    expect(screen.getByText("createAgenticWorkflow({ mcp, rag, fullstack })")).toBeTruthy();
    expect(screen.getByText("Maintains robot-vla with diffusion policy examples.")).toBeTruthy();
    expect(screen.getByText("确认后将把这些线索写入项目候选人库。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "继续" }));

    expect(onApprove).toHaveBeenCalledWith("{}", "approve");
  });

  it("shows the top-down search trace behind Scenario B lead preview", () => {
    render(
      <HumanConfirmModal
        open
        busy={false}
        context="请确认目标公司与触达策略，可通过或填写调整意见。"
        draft="{}"
        requiresLeadPreview
        leadPreview={{
          totalCount: 1,
          omittedCount: 0,
          searchTrace: {
            query: "robotics VLA",
            services: ["github_repositories", "github_code"],
            resultCount: 3,
            errors: [{ service: "github_code", reason: "deferred_by_live_budget" }],
            researchLayers: [
              {
                id: "people_network",
                nameZh: "人才网络",
                purpose: "从人员库、作者网络和开源/社媒身份定位可触达候选人。",
                services: ["github_repositories", "github_code"],
                resultCount: 3,
                errorCount: 1,
              },
            ],
          },
          leads: [
            {
              name: "Alice Wang",
              sourcePlatform: "github_repositories",
              sourceUrl: "https://github.com/alicewang/robot-vla",
            },
          ],
        }}
        onApprove={() => undefined}
        onReject={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("Top-down 搜索链路")).toBeTruthy();
    expect(screen.getByText("人才网络")).toBeTruthy();
    expect(screen.getByText("3 命中 / 1 异常")).toBeTruthy();
    expect(screen.getAllByText("github_repositories").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("github_code").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("github_code: deferred_by_live_budget")).toBeTruthy();
  });

  it("disables approve actions when Scenario B lead preview is missing", () => {
    const onApprove = vi.fn();

    render(
      <HumanConfirmModal
        open
        busy={false}
        context="请确认待入库线索。"
        draft="{}"
        requiresLeadPreview
        onApprove={onApprove}
        onReject={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("缺少候选线索预览，无法确认入库。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "继续" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "调整" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("softens internal status language before showing it", () => {
    render(
      <HumanConfirmModal
        open
        busy={false}
        context="AI Agent 请求人工确认：AI 已生成候选人评估，请确认是否推进。"
        draft="候选人评估报告"
        onApprove={() => undefined}
        onReject={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("请求确认：已生成候选人评估，请确认是否继续。")).toBeTruthy();
    expect(screen.queryByText(/AI|人工确认|决策/)).toBeNull();
  });
});
