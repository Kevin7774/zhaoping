import { describe, expect, it } from "vitest";

import {
  SEARCH_SOURCE_LAYER_SERVICES,
  budgetForExecutionPolicy,
  createDefaultSearchConfig,
  searchConfigToBackendState,
} from "./explainableAction";

const REMOVED_UNSTABLE_SEARCH_SERVICES = new Set([
  "cms_openpayments",
  "gdelt_doc_news",
  "ofac_sanctions_lists",
  "patentsview_patents",
  "semantic_scholar_authors_search",
]);

describe("search budget defaults", () => {
  it("keeps frontend search budgets aligned with backend execution policy defaults", () => {
    expect(budgetForExecutionPolicy("bounded_live")).toEqual({
      maxProviders: 14,
      perProviderLimit: 3,
      timeoutSeconds: 10,
      maxCrawlPages: 0,
    });
    expect(budgetForExecutionPolicy("deep_live")).toEqual({
      maxProviders: 36,
      perProviderLimit: 4,
      timeoutSeconds: 18,
      maxCrawlPages: 3,
    });

    expect(searchConfigToBackendState(createDefaultSearchConfig()).search_budget).toEqual({
      max_providers: 14,
      per_provider_limit: 3,
      timeout_seconds: 10,
      max_crawl_pages: 0,
    });
  });

  it("exposes every remaining backend search provider through a source layer", () => {
    const services = new Set(Object.values(SEARCH_SOURCE_LAYER_SERVICES).flat());

    for (const service of REMOVED_UNSTABLE_SEARCH_SERVICES) {
      expect(services.has(service)).toBe(false);
    }

    expect(services).toEqual(
      new Set([
        "agent_reach_social_search",
        "brave_web_search",
        "cfpb_consumer_complaints",
        "clinicaltrials_studies",
        "cpsc_recalls",
        "education_competition_monitor",
        "epa_echo_facilities",
        "fda_device_510k",
        "fda_device_classification",
        "fda_device_events",
        "fda_device_registration_listing",
        "fda_enforcement_recalls",
        "fdic_bankfind_institutions",
        "federal_register_documents",
        "github_candidates",
        "github_code",
        "github_repositories",
        "github_topics",
        "github_users",
        "gnews_funding_news",
        "grants_gov_opportunities",
        "huggingface_models",
        "nhtsa_recalls",
        "openalex_authors_search",
        "openalex_institutions_search",
        "openalex_works_search",
        "opencli_platform_search",
        "opencli_web_read_search",
        "sec_company_facts",
        "sec_edgar_company_filings",
        "sec_enforcement_search",
        "sec_insider_transactions",
        "sec_investment_adviser_reports",
        "sec_ownership_activism",
        "semantic_scholar_papers_search",
        "usaspending_awards",
      ]),
    );
  });
});
