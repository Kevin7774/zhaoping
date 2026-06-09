import type { StepStatus } from "../jobs/types";

export type CandidateStage =
  | "sourced"
  | "screening"
  | "agent_evaluated"
  | "human_gate"
  | "technical_interview"
  | "offer_review";

export type CandidateEvidence = {
  label: string;
  source: "resume" | "github" | "paper" | "demo" | "interview" | "manual";
  summary: string;
};

export type Candidate = {
  candidateId: string;
  name: string;
  targetJobProfileId: string;
  sourcePlatform: string;
  sourceUrl?: string;
  currentCompany?: string;
  city?: string;
  title: string;
  isAiNativeTalent: boolean;
  technicalLayerTags: string[];
  parsedCapabilities: string[];
  githubMetrics?: {
    repositories: number;
    stars: number;
  };
  paperMetrics?: {
    papers: number;
    citations: number;
  };
  matchScore: number;
  pipelineStatus?: string;
  stage: CandidateStage;
  stepStatus: StepStatus;
  outreachStatus: "not_sent" | "drafted" | "sent";
  riskAlerts: string[];
  evidence: CandidateEvidence[];
};

export type { StepStatus };
