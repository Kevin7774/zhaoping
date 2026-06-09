import type { Candidate } from "../candidates/types";
import type { JobProfile } from "../jobs/types";

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

export function buildCandidateEmailDraft(candidate: Candidate, job?: JobProfile) {
  const roleName = job?.roleName ?? "AI 招聘助手相关岗位";
  const capability = candidate.parsedCapabilities[0] ?? candidate.technicalLayerTags[0] ?? "工程项目";
  const secondaryCapability = candidate.parsedCapabilities[1] ?? candidate.technicalLayerTags[1] ?? "复杂业务系统工程";
  const company = candidate.currentCompany ?? "近期项目";

  return [
    `${candidate.name} 兄，`,
    "",
    `最近关注到你在 ${company} 的 ${capability} 经历，尤其是关于 ${secondaryCapability} 的处理方式，这种在复杂海量数据下追求极速响应的思路很有价值。`,
    "",
    "我是量化派的招聘团队。我们最近在重构“羊小咩”背后的智能决策引擎，旨在将 AI 从单纯推荐进化为更精准的消费撮合决策。",
    "",
    `我们正在推进「${roleName}」相关建设，希望把你的 ${capability} 经验放到“羊小咩”电商平台化和 AI 决策服务结合的场景里讨论，而不是直接进入面试流程。`,
    "",
    "如果你这周五下午或者下周一晚上有 20 分钟，我们可以先做一次纯技术推演，不聊面试。",
  ].join("\n");
}
