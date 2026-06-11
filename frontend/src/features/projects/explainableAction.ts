export type SearchProfile = "candidate_sourcing" | "due_diligence";
export type SearchExecutionPolicy = "bounded_live" | "deep_live";
export type SearchSourceLayer =
  | "liveWeb"
  | "academic"
  | "codeModel"
  | "peopleDatabase"
  | "social"
  | "platformSearch"
  | "newsFunding"
  | "educationCompetition"
  | "crawlerSnapshot"
  | "dueDiligence"
  | "financialRegulatory"
  | "healthcareRegulatory"
  | "safetyEnvironment"
  | "publicFunding";

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
  searchConfig?: SearchConfig;
  providerPreflight?: ProviderPreflightItem[];
  taskId?: string;
  failureReason?: string;
};

export const SEARCH_EXECUTION_POLICY_OPTIONS: Array<{ value: SearchExecutionPolicy; label: string }> = [
  { value: "bounded_live", label: "标准联网" },
  { value: "deep_live", label: "深度联网" },
];

export const SEARCH_SOURCE_LAYER_GROUPS: Array<{ id: string; label: string; description: string }> = [
  { id: "core", label: "默认招聘源", description: "候选人、代码、论文、社媒和新闻线索。" },
  { id: "diligence", label: "高级尽调源", description: "公司披露、监管、安全、医疗和政府资金信号。" },
  { id: "platform", label: "授权平台", description: "需要本机 OpenCLI 和授权浏览器状态，默认不自动运行。" },
  { id: "snapshot", label: "网页正文", description: "只在深度联网时读取已发现 URL 的正文。" },
];

export const SEARCH_SOURCE_LAYER_OPTIONS: Array<{
  value: SearchSourceLayer;
  label: string;
  hint?: string;
  highRisk?: boolean;
  group: string;
}> = [
  { value: "liveWeb", label: "开放网页", group: "core" },
  { value: "academic", label: "学术", group: "core" },
  { value: "codeModel", label: "GitHub/代码/模型", hint: "GitHub 搜人、Repo、Code、Topic + Hugging Face 模型。", group: "core" },
  { value: "social", label: "社媒", hint: "只保留当前实测可用的 Agent-Reach 社媒搜索。", group: "core" },
  { value: "newsFunding", label: "新闻融资", group: "core" },
  { value: "educationCompetition", label: "学校竞赛", group: "core" },
  { value: "platformSearch", label: "OpenCLI 平台", hint: "B站、知乎、小红书、LinkedIn、YouTube、X/Reddit/公众号；需要授权浏览器，默认不自动跑。", highRisk: true, group: "platform" },
  { value: "dueDiligence", label: "公司/SEC/召回", highRisk: true, group: "diligence" },
  { value: "financialRegulatory", label: "金融/投诉", highRisk: true, group: "diligence" },
  { value: "healthcareRegulatory", label: "医疗/FDA", highRisk: true, group: "diligence" },
  { value: "safetyEnvironment", label: "安全/环境", highRisk: true, group: "diligence" },
  { value: "publicFunding", label: "政府资金", highRisk: true, group: "diligence" },
  { value: "crawlerSnapshot", label: "网页抓取", hint: "OpenCLI 网页正文读取，需 deep live 和抓取页数预算。", highRisk: true, group: "snapshot" },
];

const DEFAULT_SOURCE_LAYERS: SearchSourceLayers = {
  liveWeb: true,
  academic: true,
  codeModel: true,
  peopleDatabase: false,
  social: true,
  platformSearch: false,
  newsFunding: true,
  educationCompetition: true,
  crawlerSnapshot: false,
  dueDiligence: false,
  financialRegulatory: false,
  healthcareRegulatory: false,
  safetyEnvironment: false,
  publicFunding: false,
};

const POLICY_BUDGETS: Record<SearchExecutionPolicy, SearchBudget> = {
  bounded_live: { maxProviders: 14, perProviderLimit: 3, timeoutSeconds: 10, maxCrawlPages: 0 },
  deep_live: { maxProviders: 36, perProviderLimit: 4, timeoutSeconds: 18, maxCrawlPages: 3 },
};

export const SEARCH_SOURCE_LAYER_SERVICES: Record<SearchSourceLayer, string[]> = {
  liveWeb: ["brave_web_search"],
  academic: [
    "openalex_works_search",
    "openalex_authors_search",
    "openalex_institutions_search",
    "semantic_scholar_papers_search",
  ],
  codeModel: [
    "github_candidates",
    "github_repositories",
    "github_code",
    "github_topics",
    "github_users",
    "huggingface_models",
  ],
  peopleDatabase: [],
  social: ["agent_reach_social_search"],
  platformSearch: ["opencli_platform_search"],
  newsFunding: ["gnews_funding_news"],
  educationCompetition: ["education_competition_monitor"],
  crawlerSnapshot: ["opencli_web_read_search"],
  dueDiligence: [
    "sec_edgar_company_filings",
    "sec_company_facts",
    "sec_insider_transactions",
    "sec_ownership_activism",
    "sec_investment_adviser_reports",
    "federal_register_documents",
    "cpsc_recalls",
    "fda_enforcement_recalls",
    "sec_enforcement_search",
  ],
  financialRegulatory: ["fdic_bankfind_institutions", "cfpb_consumer_complaints"],
  healthcareRegulatory: [
    "fda_device_510k",
    "fda_device_events",
    "fda_device_classification",
    "fda_device_registration_listing",
    "clinicaltrials_studies",
  ],
  safetyEnvironment: ["nhtsa_recalls", "epa_echo_facilities"],
  publicFunding: ["usaspending_awards", "grants_gov_opportunities"],
};

const SOURCE_LAYER_BACKEND_KEYS: Record<SearchSourceLayer, string> = {
  liveWeb: "live_web",
  academic: "academic",
  codeModel: "code_model",
  peopleDatabase: "people_database",
  social: "social",
  platformSearch: "platform_search",
  newsFunding: "news_funding",
  educationCompetition: "education_competition",
  crawlerSnapshot: "crawler_snapshot",
  dueDiligence: "due_diligence",
  financialRegulatory: "financial_regulatory",
  healthcareRegulatory: "healthcare_regulatory",
  safetyEnvironment: "safety_environment",
  publicFunding: "public_funding",
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

export function effectiveMaxProvidersForSearchConfig(config: SearchConfig): number {
  const selectedProviderCount = Object.entries(config.sourceLayers).reduce((count, [layer, enabled]) => {
    if (!enabled) return count;
    return count + (SEARCH_SOURCE_LAYER_SERVICES[layer as SearchSourceLayer]?.length ?? 0);
  }, 0);
  return Math.max(config.budget.maxProviders, selectedProviderCount);
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
      max_providers: effectiveMaxProvidersForSearchConfig(config),
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
  searchConfig: SearchConfig,
): ProviderPreflightItem[] {
  const searchCapability = integrations?.capabilities?.find(
    (item) => item.service_type === "search" || item.id === "search_api",
  );
  if (!searchCapability) {
    return [{ service: "search_api", status: "not_configured", reason: "Search API 未接入" }];
  }

  const services = Array.isArray(searchCapability.services) ? searchCapability.services : [];
  const filter = providerFilterForSearchConfig(searchConfig);
  const filteredServices = filter ? services.filter((service) => service.name && filter.has(service.name)) : services;

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

function providerFilterForSearchConfig(searchConfig: SearchConfig): Set<string> | null {
  const services = new Set<string>();
  for (const [layer, enabled] of Object.entries(searchConfig.sourceLayers)) {
    if (!enabled) continue;
    for (const service of SEARCH_SOURCE_LAYER_SERVICES[layer as SearchSourceLayer] ?? []) {
      services.add(service);
    }
  }
  return services;
}

function statusReason(status?: string) {
  if (status === "active" || status === "available" || status === "ready") return "可用";
  if (status === "missing_key") return "缺少 Key";
  if (status === "missing_tool") return "缺少运行工具";
  if (status === "manual_setup") return "需要人工配置";
  if (status === "not_configured" || status === "disabled") return "未接入";
  return status || "状态未知";
}
