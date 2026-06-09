import { describe, expect, it } from "vitest";

import {
  projectMock,
  projectSummary,
  getJobCandidateCounts,
} from "./projectMock";

describe("projectMock", () => {
  it("contains two jobs and five candidates for project dashboard rendering", () => {
    expect(projectMock.jobs).toHaveLength(2);
    expect(projectMock.candidates).toHaveLength(5);
  });

  it("aggregates project summary from mock jobs and candidates", () => {
    expect(projectSummary.openJobs).toBe(2);
    expect(projectSummary.totalCandidates).toBe(5);
    expect(projectSummary.awaitingHuman).toBe(1);
    expect(projectSummary.averageMatchScore).toBe(84);
  });

  it("counts candidates by target job profile", () => {
    expect(getJobCandidateCounts(projectMock)).toEqual({
      job_vla_algorithm: 3,
      job_robot_data_platform: 2,
    });
  });
});
