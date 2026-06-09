// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Candidate } from "../types";
import { CandidateTable } from "./CandidateTable";

const candidate: Candidate = {
  candidateId: "cand_zhou_han",
  jobCandidateId: 42,
  name: "Zhou Han",
  targetJobProfileId: "job_vla_algorithm",
  sourcePlatform: "Backend",
  currentCompany: "Robot Foundation Team",
  city: "上海",
  email: "zhou.han@example.com",
  title: "VLA / 具身智能算法工程师",
  isAiNativeTalent: false,
  technicalLayerTags: [],
  parsedCapabilities: [],
  matchScore: 88,
  pipelineStatus: "pending_outreach",
  stage: "technical_interview",
  stepStatus: "processing",
  outreachStatus: "not_sent",
  riskAlerts: [],
  evidence: [],
};

describe("CandidateTable", () => {
  afterEach(() => {
    cleanup();
  });

  it("runs agent evaluation for the selected candidate row", () => {
    const onRunEvaluation = vi.fn();

    render(<CandidateTable candidates={[candidate]} onSendEmail={() => undefined} onRunEvaluation={onRunEvaluation} />);

    fireEvent.click(screen.getByRole("button", { name: "候选人评估" }));

    expect(onRunEvaluation).toHaveBeenCalledWith(candidate);
    expect(screen.getByText("待触达")).toBeTruthy();
  });

  it("disables email outreach when the backend candidate has no email", () => {
    const onSendEmail = vi.fn();
    const candidateWithoutEmail = { ...candidate, email: undefined };

    render(<CandidateTable candidates={[candidateWithoutEmail]} onSendEmail={onSendEmail} />);

    const button = screen.getByRole("button", { name: "生成草稿" });
    expect(button).toHaveProperty("disabled", true);
    expect(button.getAttribute("title")).toBe("候选人无邮箱");
    fireEvent.click(button);
    expect(onSendEmail).not.toHaveBeenCalled();
  });

  it("requires HR compliance confirmation before outreach for obfuscated contact sources", () => {
    const onSendEmail = vi.fn();
    const onConfirmCompliance = vi.fn();
    const complianceCandidate = {
      ...candidate,
      pipelineStatus: "pending_compliance_review",
      stepStatus: "awaiting_human" as const,
    };

    render(
      <CandidateTable
        candidates={[complianceCandidate]}
        onSendEmail={onSendEmail}
        onConfirmCompliance={onConfirmCompliance}
      />,
    );

    expect(screen.getByText("合规待审")).toBeTruthy();
    const draftButton = screen.getByRole("button", { name: "生成草稿" });
    expect(draftButton).toHaveProperty("disabled", true);
    expect(draftButton.getAttribute("title")).toBe("候选人联系方式待合规确认");

    fireEvent.click(screen.getByRole("button", { name: "确认来源" }));

    expect(onConfirmCompliance).toHaveBeenCalledWith(complianceCandidate);
    expect(onSendEmail).not.toHaveBeenCalled();
  });

  it("labels email outreach as draft generation instead of real sending", () => {
    const onSendEmail = vi.fn();

    render(<CandidateTable candidates={[candidate]} onSendEmail={onSendEmail} />);

    fireEvent.click(screen.getByRole("button", { name: "生成草稿" }));

    expect(onSendEmail).toHaveBeenCalledWith(candidate);
    expect(screen.queryByText("已发送")).toBeNull();
  });

  it("shows a dash when the backend candidate has no match score", () => {
    render(<CandidateTable candidates={[{ ...candidate, matchScore: null }]} onSendEmail={() => undefined} />);

    expect(screen.getByText("—")).toBeTruthy();
  });

  it("loads more candidates when more pages are available", () => {
    const onLoadMore = vi.fn();

    render(
      <CandidateTable
        candidates={[candidate]}
        onSendEmail={() => undefined}
        hasMore
        onLoadMore={onLoadMore}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("shows a loading state while loading the next candidate page", () => {
    render(
      <CandidateTable
        candidates={[candidate]}
        onSendEmail={() => undefined}
        hasMore
        isLoadingMore
        onLoadMore={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "加载中..." })).toHaveProperty("disabled", true);
  });

  it("shows visible, loaded, and total candidate match counts", () => {
    render(
      <CandidateTable
        candidates={[candidate]}
        onSendEmail={() => undefined}
        loadedCount={50}
        totalCount={137}
      />,
    );

    expect(screen.getByText("已显示 1 · 已加载 50 / 共 137 条关联")).toBeTruthy();
  });
});
