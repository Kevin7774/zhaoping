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

export type JobProfile = {
  jobProfileId: string;
  roleName: string;
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
