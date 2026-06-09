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
  const insiderQuestion =
    "用户意图校准应该放在召回前的特征门控，还是放在排序后的策略约束？前者压缩探索空间，后者会在大促和长尾供给里放大延迟反馈。";

  return [
    `${candidate.name}，你好。`,
    "",
    `关注你在 ${capability} 上的研究有一段时间了。你在 ${company} 里处理 ${secondaryCapability} 时展现出的工程洞察，在当前的 AI 决策领域并不常见。`,
    "",
    "量化派技术团队目前在重构“羊小咩”的实时决策底层，目标是把 AI 从单纯推荐推进到可验证的消费撮合决策。我们发现行业内大多方案在响应速度、策略精度和商业闭环之间存在明显的 Trade-off。",
    "",
    `行业内部困惑：${insiderQuestion}`,
    "",
    `这次不谈职位 JD，也不聊面试流程，只想把你的 ${capability} 经验放到“羊小咩”电商平台化和 AI 决策服务结合的场景里，围绕「${roleName}」背后的决策链路做一次技术复盘。`,
    "",
    "周五下午或者下周一，如果你方便，抽 20 分钟做一次闭门技术探讨，我想听听你的处理思路。",
    "",
    "祝好，",
    "量化派技术团队",
  ].join("\n");
}
