import { describe, expect, it } from "vitest";

import type { Candidate } from "../candidates/types";
import {
  defaultFilterCriteria,
  filterCandidates,
  type FilterCriteria,
} from "./state";

const candidates: Candidate[] = [
  {
    candidateId: "cand_zhou_han",
    name: "Zhou Han",
    targetJobProfileId: "job_vla_algorithm",
    sourcePlatform: "Paper",
    currentCompany: "Robot Foundation Team",
    city: "上海",
    title: "Applied Scientist",
    isAiNativeTalent: true,
    technicalLayerTags: ["VLA", "Generalization", "Sim2Real"],
    parsedCapabilities: ["长尾泛化评估", "数据增强", "策略消融"],
    matchScore: 88,
    stage: "human_gate",
    stepStatus: "awaiting_human",
    outreachStatus: "not_sent",
    riskAlerts: [],
    evidence: [],
  },
  {
    candidateId: "cand_maya_li",
    name: "Maya Li",
    targetJobProfileId: "job_vla_algorithm",
    sourcePlatform: "LinkedIn",
    currentCompany: "Autonomy Stack",
    city: "北京",
    title: "ML Engineer",
    isAiNativeTalent: true,
    technicalLayerTags: ["Imitation Learning", "Data Collection"],
    parsedCapabilities: ["遥操作数据采集", "模仿学习训练", "评估集构建"],
    matchScore: 78,
    stage: "agent_evaluated",
    stepStatus: "done",
    outreachStatus: "not_sent",
    riskAlerts: [],
    evidence: [],
  },
  {
    candidateId: "cand_wang_ke",
    name: "Wang Ke",
    targetJobProfileId: "job_robot_data_platform",
    sourcePlatform: "Resume",
    currentCompany: "Autonomous Driving Data",
    city: "上海",
    title: "Senior Data Platform Engineer",
    isAiNativeTalent: false,
    technicalLayerTags: ["Data Pipeline", "MLOps", "Feature Store"],
    parsedCapabilities: ["多源同步", "数据质量监控", "训练样本版本化"],
    matchScore: 84,
    stage: "offer_review",
    stepStatus: "done",
    outreachStatus: "not_sent",
    riskAlerts: [],
    evidence: [],
  },
];

describe("project local state helpers", () => {
  it("filters candidates by job, minimum score, city, and free text", () => {
    const criteria: FilterCriteria = {
      ...defaultFilterCriteria,
      jobProfileId: "job_vla_algorithm",
      minScore: 85,
      city: "上海",
      keyword: "VLA",
    };

    const result = filterCandidates(candidates, criteria);

    expect(result.map((candidate) => candidate.candidateId)).toEqual(["cand_zhou_han"]);
  });

  it("keeps candidates without a backend score visible when no score threshold is selected", () => {
    const result = filterCandidates([{ ...candidates[0], matchScore: null }], defaultFilterCriteria);

    expect(result).toHaveLength(1);
  });
});
