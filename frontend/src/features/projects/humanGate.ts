import type { TaskStreamEvent } from "../../shared/hooks/useTaskStream";

export type HumanGateRequest = {
  eventKey: string;
  taskId: string;
  context: string;
  draft: string;
  candidateName?: string;
  requiresLeadPreview?: boolean;
  leadPreview?: LeadPreview;
};

export type LeadPreview = {
  totalCount: number;
  omittedCount: number;
  leads: LeadPreviewItem[];
  searchTrace?: LeadSearchTrace;
};

export type LeadSearchTrace = {
  query?: string;
  services: string[];
  resultCount: number;
  errors: LeadSearchTraceError[];
  researchLayers: LeadResearchLayer[];
};

export type LeadSearchTraceError = {
  service?: string;
  reason?: string;
};

export type LeadResearchLayer = {
  id: string;
  nameZh: string;
  purpose?: string;
  services: string[];
  resultCount: number;
  errorCount: number;
};

export type LeadPreviewItem = {
  name?: string;
  sourcePlatform?: string;
  sourceUrl?: string;
  evidenceSummary?: string;
  confidence?: number;
  githubScore?: number;
  representativeRepositories?: LeadRepositoryPreview[];
  repositoryEvidence?: LeadRepositoryEvidence[];
  recentActivity?: LeadRecentActivity;
  scoringSignals?: Record<string, unknown>;
  matchedJob?: string;
  complianceStatus?: string;
  ingestionAction?: string;
};

export type LeadRepositoryPreview = {
  fullName?: string;
  url?: string;
  language?: string;
  stars?: number;
  forks?: number;
  topics: string[];
};

export type LeadRepositoryEvidence = {
  source?: string;
  title?: string;
  url?: string;
  snippet?: string;
};

export type LeadRecentActivity = {
  recentRepositoryCount?: number;
  latestRepositoryPushedAt?: string;
};

type AwaitingPayload = {
  prompt?: string;
  draft?: unknown;
  requires_lead_preview?: unknown;
  requiresLeadPreview?: unknown;
  lead_preview?: unknown;
  leadPreview?: unknown;
};

export function humanGateRequestFromEvent(event: TaskStreamEvent, taskId: string): HumanGateRequest | null {
  if (event.type !== "human_gate" || event.status === "processing") return null;

  const awaiting = event.data?.awaiting as AwaitingPayload | undefined;
  if (!awaiting) return null;

  const draft = awaiting.draft;
  const candidateName = readString(draft, ["candidate_name", "candidateName", "name"]);
  const request: HumanGateRequest = {
    eventKey: String(event.id ?? `${event.created_at ?? ""}:${event.message ?? ""}`),
    taskId,
    context: awaiting.prompt || event.message || "AI Agent 请求人工确认",
    draft: draftToText(draft),
    candidateName,
  };
  const requiresLeadPreview = Boolean(awaiting.requires_lead_preview ?? awaiting.requiresLeadPreview);
  const leadPreview = normalizeLeadPreview(awaiting.lead_preview ?? awaiting.leadPreview);
  if (requiresLeadPreview) request.requiresLeadPreview = true;
  if (leadPreview) request.leadPreview = leadPreview;
  return request;
}

function normalizeLeadPreview(value: unknown): LeadPreview | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const rawLeads = Array.isArray(record.leads) ? record.leads : [];
  return {
    totalCount: readNumber(record, ["total_count", "totalCount"]),
    omittedCount: readNumber(record, ["omitted_count", "omittedCount"]),
    searchTrace: normalizeSearchTrace(record.search_trace ?? record.searchTrace),
    leads: rawLeads
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({
        name: readString(item, ["name", "entity_name", "entityName"]),
        sourcePlatform: readString(item, ["source_platform", "sourcePlatform"]),
        sourceUrl: readString(item, ["source_url", "sourceUrl"]),
        evidenceSummary: readString(item, ["evidence_summary", "evidenceSummary"]),
        confidence: readOptionalNumber(item, ["confidence"]),
        githubScore: readOptionalNumber(item, ["github_score", "githubScore"]),
        representativeRepositories: normalizeRepositories(item.representative_repositories ?? item.representativeRepositories),
        repositoryEvidence: normalizeRepositoryEvidence(item.repository_evidence ?? item.repositoryEvidence),
        recentActivity: normalizeRecentActivity(item.recent_activity ?? item.recentActivity),
        scoringSignals: normalizeScoringSignals(item.scoring_signals ?? item.scoringSignals),
        matchedJob: readString(item, ["matched_job", "matchedJob"]),
        complianceStatus: readString(item, ["compliance_status", "complianceStatus"]),
        ingestionAction: readString(item, ["ingestion_action", "ingestionAction"]),
      })),
  };
}

function normalizeRepositories(value: unknown): LeadRepositoryPreview[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const repos = value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      fullName: readString(item, ["full_name", "fullName", "name"]),
      url: readString(item, ["url", "html_url", "htmlUrl"]),
      language: readString(item, ["language"]),
      stars: readOptionalNumber(item, ["stars", "stargazers_count", "stargazersCount"]),
      forks: readOptionalNumber(item, ["forks", "forks_count", "forksCount"]),
      topics: readStringArray(item, ["topics"]),
    }))
    .filter((item) => item.fullName || item.url);
  return repos.length ? repos : undefined;
}

function normalizeRepositoryEvidence(value: unknown): LeadRepositoryEvidence[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const evidence = value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      source: readString(item, ["source"]),
      title: readString(item, ["title"]),
      url: readString(item, ["url"]),
      snippet: readString(item, ["snippet", "fragment"]),
    }))
    .filter((item) => item.title || item.snippet || item.url);
  return evidence.length ? evidence : undefined;
}

function normalizeRecentActivity(value: unknown): LeadRecentActivity | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const recentRepositoryCount = readOptionalNumber(record, ["recent_repository_count", "recentRepositoryCount"]);
  const latestRepositoryPushedAt = readString(record, ["latest_repository_pushed_at", "latestRepositoryPushedAt"]);
  if (recentRepositoryCount === undefined && !latestRepositoryPushedAt) return undefined;
  return { recentRepositoryCount, latestRepositoryPushedAt };
}

function normalizeScoringSignals(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function normalizeSearchTrace(value: unknown): LeadSearchTrace | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const rawErrors = Array.isArray(record.errors) ? record.errors : [];
  const rawLayers = Array.isArray(record.research_layers)
    ? record.research_layers
    : Array.isArray(record.researchLayers)
      ? record.researchLayers
      : [];
  return {
    query: readString(record, ["query"]),
    services: readStringArray(record, ["services"]),
    resultCount: readNumber(record, ["result_count", "resultCount"]),
    errors: rawErrors
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({
        service: readString(item, ["service"]),
        reason: readString(item, ["reason"]),
      })),
    researchLayers: rawLayers
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({
        id: readString(item, ["id"]) ?? "unknown_layer",
        nameZh: readString(item, ["name_zh", "nameZh", "name"]) ?? "未知研究层",
        purpose: readString(item, ["purpose"]),
        services: readStringArray(item, ["services"]),
        resultCount: readNumber(item, ["result_count", "resultCount"]),
        errorCount: readNumber(item, ["error_count", "errorCount"]),
      })),
  };
}

function readString(value: unknown, keys: string[]) {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  for (const key of keys) {
    const item = record[key];
    if (typeof item === "string" && item.trim()) return item;
  }
  return undefined;
}

function readStringArray(value: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const item = value[key];
    if (!Array.isArray(item)) continue;
    return item.filter((entry): entry is string => typeof entry === "string" && Boolean(entry.trim()));
  }
  return [];
}

function readNumber(value: Record<string, unknown>, keys: string[]) {
  return readOptionalNumber(value, keys) ?? 0;
}

function readOptionalNumber(value: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const item = value[key];
    if (typeof item === "number" && Number.isFinite(item)) return item;
  }
  return undefined;
}

function draftToText(value: unknown) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  for (const key of ["body", "draft", "message", "content", "email_body"]) {
    const item = record[key];
    if (typeof item === "string") return item;
  }
  return JSON.stringify(value, null, 2);
}
