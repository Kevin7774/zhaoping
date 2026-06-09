import type { Candidate } from "../candidates/types";
import type { JobProfile } from "../jobs/types";

export type FilterCriteria = {
  jobProfileId: string;
  minScore: number;
  city: string;
  keyword: string;
};

export const defaultFilterCriteria: FilterCriteria = {
  jobProfileId: "all",
  minScore: 0,
  city: "",
  keyword: "",
};

function includesText(value: string | undefined, keyword: string) {
  if (!keyword.trim()) return true;
  return (value ?? "").toLowerCase().includes(keyword.trim().toLowerCase());
}

export function filterCandidates(candidates: Candidate[], criteria: FilterCriteria) {
  return candidates.filter((candidate) => {
    const matchesJob =
      criteria.jobProfileId === "all" || !criteria.jobProfileId || candidate.targetJobProfileId === criteria.jobProfileId;
    const matchesScore = candidate.matchScore >= criteria.minScore;
    const matchesCity = !criteria.city.trim() || includesText(candidate.city, criteria.city);
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

    return matchesJob && matchesScore && matchesCity && matchesKeyword;
  });
}

export function buildCandidateEmailDraft(candidate: Candidate, job?: JobProfile) {
  const roleName = job?.roleName ?? "AI 招聘助手相关岗位";
  const capability = candidate.parsedCapabilities[0] ?? candidate.technicalLayerTags[0] ?? "工程项目";

  return [
    `Hi ${candidate.name},`,
    "",
    `看到你在 ${candidate.currentCompany ?? "近期项目"} 的 ${capability} 经历，我们正在推进「${roleName}」招聘，想和你聊聊真实机器人场景中的落地问题。`,
    "",
    "如果你方便，我可以发一份更详细的岗位说明，并约 20 分钟做一次初步沟通。",
  ].join("\n");
}

export function markCandidateEmailSent(candidates: Candidate[], candidateId: string) {
  return candidates.map((candidate) =>
    candidate.candidateId === candidateId ? { ...candidate, outreachStatus: "sent" as const } : candidate,
  );
}
