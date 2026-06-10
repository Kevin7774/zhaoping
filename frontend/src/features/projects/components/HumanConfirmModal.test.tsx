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
    const textarea = screen.getByLabelText("草稿正文");
    fireEvent.change(textarea, { target: { value: "Hi Alex, updated." } });
    fireEvent.click(screen.getByRole("button", { name: "编辑后通过" }));

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

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));

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
    expect(screen.getByText("Maintains robot-vla with diffusion policy examples.")).toBeTruthy();
    expect(screen.getByText("确认后将把这些线索写入项目候选人库。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "通过" }));

    expect(onApprove).toHaveBeenCalledWith("{}", "approve");
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
    expect((screen.getByRole("button", { name: "通过" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "编辑后通过" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
