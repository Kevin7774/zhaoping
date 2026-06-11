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

  it("separates non-person search leads from confirmed candidates", () => {
    render(
      <CandidateTable
        candidates={[
          {
            ...candidate,
            candidateId: "lead_repo",
            name: "robotics-diffusion-transformer",
            currentCompany: undefined,
            email: undefined,
            sourcePlatform: "GitHub",
          },
        ]}
        onSendEmail={() => undefined}
      />,
    );

    expect(screen.getByRole("heading", { name: "候选人与线索" })).toBeTruthy();
    expect(screen.getByText("线索")).toBeTruthy();
    expect(screen.queryByRole("columnheader", { name: "当前公司" })).toBeNull();
  });

  it("treats GitHub person provider results as candidates even without email or company", () => {
    render(
      <CandidateTable
        candidates={[
          {
            ...candidate,
            candidateId: "github_person",
            name: "xuxiang",
            currentCompany: undefined,
            email: undefined,
            sourcePlatform: "github_candidates",
            githubUrl: "https://github.com/xu-xiang",
          },
        ]}
        onSendEmail={() => undefined}
      />,
    );

    expect(screen.getByText("候选人")).toBeTruthy();
    expect(screen.queryByText("线索")).toBeNull();
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

  it("calls the parent view-all action from the header button", () => {
    const onViewAll = vi.fn();

    render(<CandidateTable candidates={[candidate]} onSendEmail={() => undefined} onViewAll={onViewAll} />);

    fireEvent.click(screen.getByRole("button", { name: "查看全部" }));

    expect(onViewAll).toHaveBeenCalledTimes(1);
  });

  it("expands candidate evidence when clicking the row view button", () => {
    render(
      <CandidateTable
        candidates={[
          {
            ...candidate,
            sourceUrl: "https://github.com/example/robot-vla",
            evidence: [{ label: "GitHub", source: "github", summary: "维护 robot-vla 项目。" }],
          },
        ]}
        onSendEmail={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看" }));

    expect(screen.getByText("维护 robot-vla 项目。")).toBeTruthy();
    expect(screen.getByText("https://github.com/example/robot-vla")).toBeTruthy();
  });

  it("expands all available candidate details when clicking view", () => {
    render(
      <CandidateTable
        candidates={[
          {
            ...candidate,
            sourcePlatform: "github_candidates",
            sourceUrl: "https://github.com/example/agentic-fde",
            githubUrl: "https://github.com/example",
            linkedinUrl: "https://www.linkedin.com/in/example",
            homepageUrl: "https://example.dev",
            skills: ["Agentic workflow", "RAG", "Full-stack"],
            riskAlerts: ["需要确认最近上线项目"],
            evidence: [{ label: "GitHub", source: "github", summary: "维护 agentic-fde 项目。" }],
          },
        ]}
        onSendEmail={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看" }));

    expect(screen.getByText("邮箱")).toBeTruthy();
    expect(screen.getByText("zhou.han@example.com")).toBeTruthy();
    expect(screen.getByText("城市")).toBeTruthy();
    expect(screen.getByText("上海")).toBeTruthy();
    expect(screen.getByText("来源")).toBeTruthy();
    expect(screen.getAllByText("github_candidates").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^GitHub/).length).toBeGreaterThan(0);
    expect(screen.getByText("https://github.com/example")).toBeTruthy();
    expect(screen.getByText(/^LinkedIn/)).toBeTruthy();
    expect(screen.getByText("https://www.linkedin.com/in/example")).toBeTruthy();
    expect(screen.getByText(/^Homepage/)).toBeTruthy();
    expect(screen.getByText("https://example.dev")).toBeTruthy();
    expect(screen.getByText("技能")).toBeTruthy();
    expect(screen.getByText("Agentic workflow")).toBeTruthy();
    expect(screen.getByText("RAG")).toBeTruthy();
    expect(screen.getByText("Full-stack")).toBeTruthy();
    expect(screen.getByText("风险")).toBeTruthy();
    expect(screen.getByText("需要确认最近上线项目")).toBeTruthy();
    expect(screen.getByText("维护 agentic-fde 项目。")).toBeTruthy();
  });
});
