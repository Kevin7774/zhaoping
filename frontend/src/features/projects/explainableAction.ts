export type SearchMode = "planning_only" | "live_recruiting" | "due_diligence" | "social_expansion";
export type SearchProfile = "candidate_sourcing" | "due_diligence" | "social_expansion";
export type SearchExecutionPolicy = "planning_only" | "bounded_live" | "deep_live";
export type SearchSourceLayer =
  | "liveWeb"
  | "academic"
  | "codeModel"
  | "peopleDatabase"
  | "social"
  | "newsFunding"
  | "educationCompetition"
  | "crawlerSnapshot"
  | "dueDiligence";

export type SearchSourceLayers = Record<SearchSourceLayer, boolean>;

export type SearchBudget = {
  maxProviders: number;
  perProviderLimit: number;
  timeoutSeconds: number;
  maxCrawlPages: number;
};

export type SearchConfig = {
  searchProfile: SearchProfile;
  executionPolicy: SearchExecutionPolicy;
  sourceLayers: SearchSourceLayers;
  budget: SearchBudget;
};

export type ProviderPreflightItem = {
  service: string;
  status: string;
  reason?: string;
};

export type ActionExplanation = {
  actionId: string;
  label: string;
  apiRoute: string;
  inputSummary: string;
  expectedOutput: string;
  capabilityGate: string;
  searchMode?: SearchMode;
  searchConfig?: SearchConfig;
  providerPreflight?: ProviderPreflightItem[];
  taskId?: string;
  failureReason?: string;
};

export const SEARCH_MODE_OPTIONS: Array<{ value: SearchMode; label: string }> = [
  { value: "live_recruiting", label: "实时招聘搜索" },
  { value: "planning_only", label: "规划模式" },
  { value: "due_diligence", label: "尽调深搜" },
  { value: "social_expansion", label: "社媒扩展" },
];

export const SEARCH_EXECUTION_POLICY_OPTIONS: Array<{ value: SearchExecutionPolicy; label: string }> = [
  { value: "bounded_live", label: "标准联网" },
  { value: "planning_only", label: "仅规划" },
  { value: "deep_live", label: "深度联网" },
];

export const SEARCH_SOURCE_LAYER_OPTIONS: Array<{ value: SearchSourceLayer; label: string; highRisk?: boolean }> = [
  { value: "liveWeb", label: "开放网页" },
  { value: "academic", label: "学术" },
  { value: "codeModel", label: "代码/模型" },
  { value: "peopleDatabase", label: "人脉库" },
  { value: "social", label: "社媒" },
  { value: "newsFunding", label: "新闻融资" },
  { value: "educationCompetition", label: "学校竞赛" },
  { value: "crawlerSnapshot", label: "网页抓取", highRisk: true },
  { value: "dueDiligence", label: "尽调源", highRisk: true },
];

const SEARCH_MODE_SERVICE_FILTER: Record<SearchMode, Set<string> | null> = {
  planning_only: null,
  live_recruiting: null,
  due_diligence: null,
  social_expansion: new Set(["x_recent_posts_search", "agent_reach_social_search", "crustdata_signal_search"]),
};

const DEFAULT_SOURCE_LAYERS: SearchSourceLayers = {
  liveWeb: true,
  academic: true,
  codeModel: true,
  peopleDatabase: true,
  social: true,
  newsFunding: true,
  educationCompetition: true,
  crawlerSnapshot: false,
  dueDiligence: false,
};

const POLICY_BUDGETS: Record<SearchExecutionPolicy, SearchBudget> = {
  planning_only: { maxProviders: 0, perProviderLimit: 0, timeoutSeconds: 0, maxCrawlPages: 0 },
  bounded_live: { maxProviders: 8, perProviderLimit: 2, timeoutSeconds: 6, maxCrawlPages: 0 },
  deep_live: { maxProviders: 14, perProviderLimit: 3, timeoutSeconds: 12, maxCrawlPages: 3 },
};

const SOURCE_LAYER_SERVICE_FILTER: Record<SearchSourceLayer, string[]> = {
  liveWeb: ["brave_web_search"],
  academic: [
    "openalex_works_search",
    "openalex_authors_search",
    "openalex_institutions_search",
    "semantic_scholar_papers_search",
    "semantic_scholar_authors_search",
  ],
  codeModel: ["github_repositories", "huggingface_models"],
  peopleDatabase: ["pdl_people_search"],
  social: ["x_recent_posts_search", "agent_reach_social_search", "crustdata_signal_search"],
  newsFunding: ["gdelt_doc_news", "gnews_funding_news"],
  educationCompetition: ["education_competition_monitor"],
  crawlerSnapshot: [
    "scrapling_adaptive_scrape",
    "browser_use_agent_search",
    "claude_chrome_supervised_search",
    "web_access_cdp_search",
  ],
  dueDiligence: [
    "sec_edgar_company_filings",
    "sec_company_facts",
    "sec_insider_transactions",
    "sec_ownership_activism",
    "sec_investment_adviser_reports",
    "companies_house_search",
    "courtlistener_search",
    "patentsview_patents",
    "ofac_sanctions_lists",
    "federal_register_documents",
    "cpsc_recalls",
    "fda_enforcement_recalls",
    "sec_enforcement_search",
  ],
};

const SOURCE_LAYER_BACKEND_KEYS: Record<SearchSourceLayer, string> = {
  liveWeb: "live_web",
  academic: "academic",
  codeModel: "code_model",
  peopleDatabase: "people_database",
  social: "social",
  newsFunding: "news_funding",
  educationCompetition: "education_competition",
  crawlerSnapshot: "crawler_snapshot",
  dueDiligence: "due_diligence",
};

type IntegrationLike = {
  capabilities?: Array<{
    id?: string;
    service_type?: string;
    status?: string;
    connected_name_zh?: string;
    services?: Array<{
      name?: string;
      name_zh?: string;
      status?: string;
      connected?: boolean;
    }>;
  }>;
};

export function createDefaultSearchConfig(): SearchConfig {
  return {
    searchProfile: "candidate_sourcing",
    executionPolicy: "bounded_live",
    sourceLayers: { ...DEFAULT_SOURCE_LAYERS },
    budget: { ...POLICY_BUDGETS.bounded_live },
  };
}

export function budgetForExecutionPolicy(policy: SearchExecutionPolicy): SearchBudget {
  return { ...POLICY_BUDGETS[policy] };
}

export function searchConfigToBackendState(config: SearchConfig) {
  return {
    search_profile: config.searchProfile,
    execution_policy: config.executionPolicy,
    source_layers: Object.fromEntries(
      Object.entries(config.sourceLayers).map(([key, value]) => [
        SOURCE_LAYER_BACKEND_KEYS[key as SearchSourceLayer],
        value,
      ]),
    ),
    search_budget: {
      max_providers: config.budget.maxProviders,
      per_provider_limit: config.budget.perProviderLimit,
      timeout_seconds: config.budget.timeoutSeconds,
      max_crawl_pages: config.budget.maxCrawlPages,
    },
  };
}

export function buildActionExplanation(explanation: ActionExplanation): ActionExplanation {
  return explanation;
}

export async function runExplainableAction<T>({
  explanation,
  run,
  onRecord,
}: {
  explanation: ActionExplanation;
  run: () => Promise<T>;
  onRecord: (explanation: ActionExplanation) => void;
}): Promise<T> {
  onRecord(explanation);
  try {
    return await run();
  } catch (error) {
    onRecord({
      ...explanation,
      failureReason: error instanceof Error ? error.message : "动作执行失败",
    });
    throw error;
  }
}

export function providerPreflightFromIntegrations(
  integrations: IntegrationLike | null,
  searchConfigOrMode: SearchConfig | SearchMode,
): ProviderPreflightItem[] {
  const searchCapability = integrations?.capabilities?.find(
    (item) => item.service_type === "search" || item.id === "search_api",
  );
  if (!searchCapability) {
    return [{ service: "search_api", status: "not_configured", reason: "Search API 未接入" }];
  }

  const services = Array.isArray(searchCapability.services) ? searchCapability.services : [];
  const filter = providerFilterForSearchInput(searchConfigOrMode);
  const planningOnly = isSearchConfig(searchConfigOrMode) && searchConfigOrMode.executionPolicy === "planning_only";
  const filteredServices = planningOnly
    ? services.filter((service) => service.name === "talent_source_catalog" || service.connected)
    : filter
      ? services.filter((service) => service.name && filter.has(service.name))
      : services;

  if (!filteredServices.length) {
    return [
      {
        service: searchCapability.connected_name_zh || searchCapability.id || "search_api",
        status: searchCapability.status || "unknown",
        reason: statusReason(searchCapability.status),
      },
    ];
  }

  return filteredServices.map((service) => ({
    service: service.name || service.name_zh || "unknown_search_service",
    status: service.status || "unknown",
    reason: statusReason(service.status),
  }));
}

export function providerPreflightSummary(items: ProviderPreflightItem[]) {
  const total = items.length;
  const ready = items.filter((item) => item.status === "active" || item.status === "available" || item.status === "ready").length;
  const blocked = items.filter((item) => ["missing_key", "missing_tool", "manual_setup", "not_configured"].includes(item.status)).length;
  return { total, ready, blocked };
}

function providerFilterForSearchInput(searchConfigOrMode: SearchConfig | SearchMode): Set<string> | null {
  if (!isSearchConfig(searchConfigOrMode)) return SEARCH_MODE_SERVICE_FILTER[searchConfigOrMode];
  if (searchConfigOrMode.executionPolicy === "planning_only") return null;
  const services = new Set<string>();
  for (const [layer, enabled] of Object.entries(searchConfigOrMode.sourceLayers)) {
    if (!enabled) continue;
    for (const service of SOURCE_LAYER_SERVICE_FILTER[layer as SearchSourceLayer] ?? []) {
      services.add(service);
    }
  }
  return services;
}

function isSearchConfig(value: SearchConfig | SearchMode): value is SearchConfig {
  return typeof value === "object" && value !== null && "sourceLayers" in value;
}

function statusReason(status?: string) {
  if (status === "active" || status === "available" || status === "ready") return "可用";
  if (status === "missing_key") return "缺少 Key";
  if (status === "missing_tool") return "缺少运行工具";
  if (status === "manual_setup") return "需要人工配置";
  if (status === "not_configured" || status === "disabled") return "未接入";
  return status || "状态未知";
}
