import { describe, expect, it } from "vitest";

import { budgetForExecutionPolicy, createDefaultSearchConfig, searchConfigToBackendState } from "./explainableAction";

describe("search budget defaults", () => {
  it("keeps frontend search budgets aligned with backend execution policy defaults", () => {
    expect(budgetForExecutionPolicy("bounded_live")).toEqual({
      maxProviders: 17,
      perProviderLimit: 3,
      timeoutSeconds: 10,
      maxCrawlPages: 0,
    });
    expect(budgetForExecutionPolicy("deep_live")).toEqual({
      maxProviders: 28,
      perProviderLimit: 4,
      timeoutSeconds: 18,
      maxCrawlPages: 3,
    });

    expect(searchConfigToBackendState(createDefaultSearchConfig()).search_budget).toEqual({
      max_providers: 17,
      per_provider_limit: 3,
      timeout_seconds: 10,
      max_crawl_pages: 0,
    });
  });
});
