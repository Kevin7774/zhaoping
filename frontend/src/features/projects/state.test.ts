import { describe, expect, it } from "vitest";

import { projectMock } from "../../shared/mocks/projectMock";
import {
  buildCandidateEmailDraft,
  defaultFilterCriteria,
  filterCandidates,
  type FilterCriteria,
} from "./state";

describe("project local state helpers", () => {
  it("filters candidates by job, minimum score, city, and free text", () => {
    const criteria: FilterCriteria = {
      ...defaultFilterCriteria,
      jobProfileId: "job_vla_algorithm",
      minScore: 85,
      city: "上海",
      keyword: "VLA",
    };

    const result = filterCandidates(projectMock.candidates, criteria);

    expect(result.map((candidate) => candidate.candidateId)).toEqual(["cand_zhou_han"]);
  });

  it("builds a deterministic outreach draft for a selected candidate", () => {
    const candidate = projectMock.candidates[0];
    const job = projectMock.jobs[0];
    const draft = buildCandidateEmailDraft(candidate, job);

    expect(draft).toContain(`${candidate.name}，你好`);
    expect(draft).toContain("量化派");
    expect(draft).toContain("羊小咩");
    expect(draft).toContain("消费撮合决策");
    expect(draft).toContain("量化派技术团队");
    expect(draft).toContain("行业内部困惑");
    expect(draft).toContain("Trade-off");
    expect(draft).toContain("闭门技术探讨");
    expect(draft).toContain(job.roleName);
    expect(draft).not.toContain(`Hi ${candidate.name}`);
    expect(draft).not.toContain("招聘团队");
  });

  it("keeps candidates without a backend score visible when no score threshold is selected", () => {
    const result = filterCandidates([{ ...projectMock.candidates[0], matchScore: null }], defaultFilterCriteria);

    expect(result).toHaveLength(1);
  });
});
