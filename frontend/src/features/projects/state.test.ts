import { describe, expect, it } from "vitest";

import { projectMock } from "../../shared/mocks/projectMock";
import {
  buildCandidateEmailDraft,
  defaultFilterCriteria,
  filterCandidates,
  markCandidateEmailSent,
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

    expect(buildCandidateEmailDraft(candidate, job)).toContain(`Hi ${candidate.name}`);
    expect(buildCandidateEmailDraft(candidate, job)).toContain(job.roleName);
  });

  it("marks one candidate as sent without mutating the original list", () => {
    const updated = markCandidateEmailSent(projectMock.candidates, "cand_lin_chen");

    expect(updated.find((candidate) => candidate.candidateId === "cand_lin_chen")?.outreachStatus).toBe("sent");
    expect(projectMock.candidates.find((candidate) => candidate.candidateId === "cand_lin_chen")?.outreachStatus).toBe(
      "not_sent",
    );
  });
});
