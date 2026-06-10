import type { Candidate } from "../candidates/types";

export type FilterCriteria = {
  jobProfileId: string;
  minScore: number;
  city: string;
  keyword: string;
  outreachStatus: "all" | "not_sent" | "drafted" | "sent";
  hasEmail: "all" | "yes" | "no";
  sourcePlatform: string;
};

export const defaultFilterCriteria: FilterCriteria = {
  jobProfileId: "all",
  minScore: 0,
  city: "",
  keyword: "",
  outreachStatus: "all",
  hasEmail: "all",
  sourcePlatform: "all",
};

function includesText(value: string | undefined, keyword: string) {
  if (!keyword.trim()) return true;
  return (value ?? "").toLowerCase().includes(keyword.trim().toLowerCase());
}

export function filterCandidates(candidates: Candidate[], criteria: FilterCriteria) {
  return candidates.filter((candidate) => {
    const matchesJob =
      criteria.jobProfileId === "all" || !criteria.jobProfileId || candidate.targetJobProfileId === criteria.jobProfileId;
    const matchesScore = candidate.matchScore === null ? criteria.minScore <= 0 : candidate.matchScore >= criteria.minScore;
    const matchesCity = !criteria.city.trim() || includesText(candidate.city, criteria.city);
    const matchesOutreach =
      criteria.outreachStatus === "all" || candidate.outreachStatus === criteria.outreachStatus;
    const matchesEmail =
      criteria.hasEmail === "all" ||
      (criteria.hasEmail === "yes" ? Boolean(candidate.email) : !candidate.email);
    const matchesSource =
      criteria.sourcePlatform === "all" || candidate.sourcePlatform === criteria.sourcePlatform;
    const keyword = criteria.keyword.trim();
    const matchesKeyword =
      !keyword ||
      [
        candidate.name,
        candidate.currentCompany,
        candidate.title,
        candidate.city,
        candidate.technicalLayerTags.join(" "),
        candidate.parsedCapabilities.join(" "),
      ].some((value) => includesText(value, keyword));

    return matchesJob && matchesScore && matchesCity && matchesOutreach && matchesEmail && matchesSource && matchesKeyword;
  });
}
