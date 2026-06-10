import { describe, expect, it } from "vitest";

import { projectMock } from "../../shared/mocks/projectMock";
import {
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

  it("keeps candidates without a backend score visible when no score threshold is selected", () => {
    const result = filterCandidates([{ ...projectMock.candidates[0], matchScore: null }], defaultFilterCriteria);

    expect(result).toHaveLength(1);
  });
});
