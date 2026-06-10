export type SearchMode = "planning_only" | "live_recruiting" | "due_diligence" | "social_expansion";

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

const SEARCH_MODE_SERVICE_FILTER: Record<SearchMode, Set<string> | null> = {
  planning_only: null,
  live_recruiting: null,
  due_diligence: null,
  social_expansion: new Set(["x_recent_posts_search", "agent_reach_social_search", "crustdata_signal_search"]),
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
  searchMode: SearchMode,
): ProviderPreflightItem[] {
  const searchCapability = integrations?.capabilities?.find(
    (item) => item.service_type === "search" || item.id === "search_api",
  );
  if (!searchCapability) {
    return [{ service: "search_api", status: "not_configured", reason: "Search API 未接入" }];
  }

  const services = Array.isArray(searchCapability.services) ? searchCapability.services : [];
  const filter = SEARCH_MODE_SERVICE_FILTER[searchMode];
  const filteredServices =
    searchMode === "planning_only"
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

function statusReason(status?: string) {
  if (status === "active" || status === "available" || status === "ready") return "可用";
  if (status === "missing_key") return "缺少 Key";
  if (status === "missing_tool") return "缺少运行工具";
  if (status === "manual_setup") return "需要人工配置";
  if (status === "not_configured" || status === "disabled") return "未接入";
  return status || "状态未知";
}
