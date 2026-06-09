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
    fireEvent.click(screen.getByRole("button", { name: "修改并批准 Approve" }));

    expect(onApprove).toHaveBeenCalledWith("Hi Alex, updated.");
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

    fireEvent.click(screen.getByRole("button", { name: "拒绝 Reject" }));

    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onApprove).not.toHaveBeenCalled();
  });
});
