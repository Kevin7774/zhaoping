// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Candidate } from "../types";
import { CandidateTable } from "./CandidateTable";

const candidate: Candidate = {
  candidateId: "cand_zhou_han",
  name: "Zhou Han",
  targetJobProfileId: "job_vla_algorithm",
  sourcePlatform: "Backend",
  currentCompany: "Robot Foundation Team",
  city: "上海",
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

    fireEvent.click(screen.getByRole("button", { name: "Agent 评估" }));

    expect(onRunEvaluation).toHaveBeenCalledWith(candidate);
    expect(screen.getByText("待触达")).toBeTruthy();
  });
});
