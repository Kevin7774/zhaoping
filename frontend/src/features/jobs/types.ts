export type StepStatus = "pending" | "processing" | "awaiting_human" | "done" | "error" | "cancelled";

export type CapabilityRequirement = {
  capabilityId: string;
  name: string;
  weight: number;
};

export type FunnelStageKey = "sourcing" | "screening" | "evaluation" | "human_gate" | "interview" | "offer";

export type FunnelStageProgress = {
  key: FunnelStageKey;
  label: string;
  count: number;
  target: number;
  status: StepStatus;
};

export type JobRationale = {
  whyNeeded?: string | null;
  bpEvidence?: string[];
  businessCommitments?: string[];
  capabilityGaps?: string[];
  whyHireNotVendor?: string | null;
  ifNotHiredRisk?: string | null;
  dependencies?: string[];
  first90DayOutcomes?: string[];
  hiringPriority?: string | null;
  confidence?: number | null;
};

export type JobProfile = {
  jobProfileId: string;
  roleName: string;
  rationale?: JobRationale | null;
  headcount?: number;
  seniority?: string;
  responsibilities?: string[];
  mustHaveSkills?: string[];
  niceToHaveSkills?: string[];
  targetCompanies?: string[];
  exclusionSignals?: string[];
  interviewQuestions?: string[];
  scoringRubric?: Record<string, unknown>;
  searchStrategy?: Record<string, unknown>;
  pipelineStatus?: StepStatus;
  candidateCount?: number;
  averageMatchScore?: number;
  priorityLevel: "P0" | "P1" | "P2";
  isAiNativeFriendly: boolean;
  essentialCapabilities: CapabilityRequirement[];
  preferredCapabilities: CapabilityRequirement[];
  exclusionTags: string[];
  targetCompanyTypes: string[];
  targetSchoolsLabs: string[];
  salaryRangeMin: number;
  salaryRangeMax: number;
  funnel: FunnelStageProgress[];
};
