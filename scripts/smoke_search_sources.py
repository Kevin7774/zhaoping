from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.router import get_router


def _summarize(results: list[dict]) -> list[dict]:
    return [
        {
            "source_key": result.get("source_key"),
            "title": result.get("title"),
            "url": result.get("url"),
            "published_at": result.get("published_at"),
            "retrieval_status": result.get("retrieval_status"),
            "error": result.get("error"),
        }
        for result in results
    ]


def _summarize_scrape(result: dict) -> dict:
    return {
        "provider": result.get("provider"),
        "url": result.get("url"),
        "has_markdown": bool(result.get("markdown")),
        "has_html": bool(result.get("html")),
        "metadata": result.get("metadata") or {},
        "retrieval_status": result.get("retrieval_status"),
        "error": result.get("error"),
    }


def _summarize_snapshot(result: dict) -> dict:
    return {
        "provider": result.get("provider"),
        "job_name": result.get("job_name"),
        "manifest_path": result.get("manifest_path"),
        "item_count": len(result.get("items") or []),
        "statuses": [item.get("status") for item in result.get("items") or []],
        "browserbase_session_id": (result.get("browserbase_session") or {}).get("session_id"),
        "retrieval_status": result.get("retrieval_status"),
        "error": result.get("error"),
    }


class _SafeSearchProvider:
    def __init__(self, service_name: str, provider) -> None:
        self.service_name = service_name
        self.provider = provider

    def search(self, query: str, limit: int = 5) -> list[dict]:
        try:
            return self.provider.search(query, limit=limit)
        except Exception as exc:  # pragma: no cover - exercised by live smoke only
            return [
                {
                    "source_key": self.service_name,
                    "title": f"{self.service_name} failed",
                    "url": None,
                    "published_at": None,
                    "retrieval_status": "error",
                    "error": str(exc)[:500],
                }
            ]


class _SafeScrapingProvider:
    def __init__(self, service_name: str, provider) -> None:
        self.service_name = service_name
        self.provider = provider

    def scrape(self, url: str) -> dict:
        try:
            return self.provider.scrape(url)
        except Exception as exc:  # pragma: no cover - exercised by live smoke only
            return {
                "provider": self.service_name,
                "url": url,
                "retrieval_status": "error",
                "error": str(exc)[:500],
            }

    def snapshot(self, **kwargs) -> dict:
        try:
            return self.provider.snapshot(**kwargs)
        except Exception as exc:  # pragma: no cover - exercised by live smoke only
            return {
                "provider": self.service_name,
                "retrieval_status": "error",
                "error": str(exc)[:500],
                "items": [],
            }


class _SafeRouter:
    def __init__(self, router) -> None:
        self.router = router

    def search(self, service_name: str) -> _SafeSearchProvider:
        return _SafeSearchProvider(service_name, self.router.search(service_name))

    def scraping(self, service_name: str) -> _SafeScrapingProvider:
        return _SafeScrapingProvider(service_name, self.router.scraping(service_name))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke check live search providers.")
    parser.add_argument("--academic-query", default="robot foundation model")
    parser.add_argument("--openalex-author-query", default="robot learning researcher")
    parser.add_argument("--openalex-institution-query", default="robotics university lab")
    parser.add_argument("--semantic-paper-query", default="vision language action robotics")
    parser.add_argument("--semantic-author-query", default="robot learning")
    parser.add_argument("--sec-query", default="MSFT annual report")
    parser.add_argument("--sec-facts-query", default="MSFT revenue")
    parser.add_argument("--insider-query", default="MSFT insider transactions")
    parser.add_argument("--ownership-query", default="Berkshire Hathaway 13F")
    parser.add_argument("--adviser-query", default="BlackRock")
    parser.add_argument("--fdic-query", default="Silicon Valley Bank")
    parser.add_argument("--regulatory-query", default="robotics")
    parser.add_argument("--recall-query", default="robot vacuum")
    parser.add_argument("--fda-query", default="robotic surgical system")
    parser.add_argument("--fda-510k-query", default="robotic surgical system")
    parser.add_argument("--fda-event-query", default="robotic surgical system")
    parser.add_argument("--fda-classification-query", default="NAY")
    parser.add_argument("--fda-registration-query", default="NAY")
    parser.add_argument("--cfpb-query", default="fintech lender")
    parser.add_argument("--nhtsa-query", default="2024 Tesla Model Y recall")
    parser.add_argument("--epa-query", default="battery manufacturing")
    parser.add_argument("--clinical-query", default="robotic surgery")
    parser.add_argument("--openpayments-query", default="Medtronic")
    parser.add_argument("--trade-query", default="854231 imports")
    parser.add_argument("--fred-query", default="inflation interest rate")
    parser.add_argument("--news-query", default="robotics funding")
    parser.add_argument("--funding-query", default="robotics funding")
    parser.add_argument("--enforcement-query", default="robotics")
    parser.add_argument("--jobs-query", default="robotics engineer")
    parser.add_argument("--spending-query", default="robotics")
    parser.add_argument("--sam-query", default="robotics")
    parser.add_argument("--grants-query", default="robotics")
    parser.add_argument("--patent-query", default="robot manipulation")
    parser.add_argument("--sanctions-query", default="example")
    parser.add_argument("--github-query", default="robotics foundation model")
    parser.add_argument("--hf-query", default="robotics")
    parser.add_argument("--pdl-query", default="robotics machine learning lead")
    parser.add_argument("--x-query", default="robotics VLA demo -is:retweet")
    parser.add_argument("--crustdata-query", default="robotics hiring funding")
    parser.add_argument("--company-query", default="openai")
    parser.add_argument("--court-query", default="robotics")
    parser.add_argument("--social-query", default="robotics VLA demo")
    parser.add_argument("--education-query", default="机器人 天池 高校 实验室")
    parser.add_argument("--scrape-query", default="https://example.com robotics")
    parser.add_argument("--opencli-url", default="https://example.com")
    parser.add_argument("--snapshot-url", default="https://example.com")
    parser.add_argument("--snapshot-job-name", default="smoke-public-web")
    parser.add_argument("--browser-query", default="Find robotics hiring evidence on an authorized site")
    parser.add_argument("--chrome-query", default="Review a complex authorized page under supervision")
    parser.add_argument("--web-access-query", default="robotics hiring search with public web first")
    parser.add_argument("--web-query", default="robot foundation model")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--include-brave", action="store_true")
    parser.add_argument("--external-only", action="store_true", help="Smoke only external tool providers.")
    args = parser.parse_args()

    router = _SafeRouter(get_router())
    external_output = {
        "agent_reach_social_search": _summarize(
            router.search("agent_reach_social_search").search(args.social_query, limit=args.limit)
        ),
        "scrapling_adaptive_scrape": _summarize(
            router.search("scrapling_adaptive_scrape").search(args.scrape_query, limit=args.limit)
        ),
        "opencli_crawl_scrape": _summarize_scrape(
            router.scraping("opencli_crawl_scrape").scrape(args.opencli_url)
        ),
        "public_web_snapshot_monitor": _summarize_snapshot(
            router.scraping("public_web_snapshot_monitor").snapshot(
                urls=[args.snapshot_url],
                job_name=args.snapshot_job_name,
            )
        ),
        "browser_use_agent_search": _summarize(
            router.search("browser_use_agent_search").search(args.browser_query, limit=args.limit)
        ),
        "claude_chrome_supervised_search": _summarize(
            router.search("claude_chrome_supervised_search").search(args.chrome_query, limit=args.limit)
        ),
        "web_access_cdp_search": _summarize(
            router.search("web_access_cdp_search").search(args.web_access_query, limit=args.limit)
        ),
    }
    if args.external_only:
        print(json.dumps(external_output, ensure_ascii=False, indent=2))
        return

    output = {
        "openalex_works_search": _summarize(
            router.search("openalex_works_search").search(args.academic_query, limit=args.limit)
        ),
        "openalex_authors_search": _summarize(
            router.search("openalex_authors_search").search(args.openalex_author_query, limit=args.limit)
        ),
        "openalex_institutions_search": _summarize(
            router.search("openalex_institutions_search").search(args.openalex_institution_query, limit=args.limit)
        ),
        "semantic_scholar_papers_search": _summarize(
            router.search("semantic_scholar_papers_search").search(args.semantic_paper_query, limit=args.limit)
        ),
        "semantic_scholar_authors_search": _summarize(
            router.search("semantic_scholar_authors_search").search(args.semantic_author_query, limit=args.limit)
        ),
        "sec_edgar_company_filings": _summarize(
            router.search("sec_edgar_company_filings").search(args.sec_query, limit=args.limit)
        ),
        "sec_company_facts": _summarize(
            router.search("sec_company_facts").search(args.sec_facts_query, limit=args.limit)
        ),
        "sec_insider_transactions": _summarize(
            router.search("sec_insider_transactions").search(args.insider_query, limit=args.limit)
        ),
        "sec_ownership_activism": _summarize(
            router.search("sec_ownership_activism").search(args.ownership_query, limit=args.limit)
        ),
        "sec_investment_adviser_reports": _summarize(
            router.search("sec_investment_adviser_reports").search(args.adviser_query, limit=args.limit)
        ),
        "fdic_bankfind_institutions": _summarize(
            router.search("fdic_bankfind_institutions").search(args.fdic_query, limit=args.limit)
        ),
        "federal_register_documents": _summarize(
            router.search("federal_register_documents").search(args.regulatory_query, limit=args.limit)
        ),
        "cpsc_recalls": _summarize(
            router.search("cpsc_recalls").search(args.recall_query, limit=args.limit)
        ),
        "fda_enforcement_recalls": _summarize(
            router.search("fda_enforcement_recalls").search(args.fda_query, limit=args.limit)
        ),
        "fda_device_510k": _summarize(
            router.search("fda_device_510k").search(args.fda_510k_query, limit=args.limit)
        ),
        "fda_device_events": _summarize(
            router.search("fda_device_events").search(args.fda_event_query, limit=args.limit)
        ),
        "fda_device_classification": _summarize(
            router.search("fda_device_classification").search(args.fda_classification_query, limit=args.limit)
        ),
        "fda_device_registration_listing": _summarize(
            router.search("fda_device_registration_listing").search(args.fda_registration_query, limit=args.limit)
        ),
        "cfpb_consumer_complaints": _summarize(
            router.search("cfpb_consumer_complaints").search(args.cfpb_query, limit=args.limit)
        ),
        "nhtsa_recalls": _summarize(
            router.search("nhtsa_recalls").search(args.nhtsa_query, limit=args.limit)
        ),
        "epa_echo_facilities": _summarize(
            router.search("epa_echo_facilities").search(args.epa_query, limit=args.limit)
        ),
        "clinicaltrials_studies": _summarize(
            router.search("clinicaltrials_studies").search(args.clinical_query, limit=args.limit)
        ),
        "cms_openpayments": _summarize(
            router.search("cms_openpayments").search(args.openpayments_query, limit=args.limit)
        ),
        "gdelt_doc_news": _summarize(
            router.search("gdelt_doc_news").search(args.news_query, limit=args.limit)
        ),
        "sec_enforcement_search": _summarize(
            router.search("sec_enforcement_search").search(args.enforcement_query, limit=args.limit)
        ),
        "usaspending_awards": _summarize(
            router.search("usaspending_awards").search(args.spending_query, limit=args.limit)
        ),
        "grants_gov_opportunities": _summarize(
            router.search("grants_gov_opportunities").search(args.grants_query, limit=args.limit)
        ),
        "patentsview_patents": _summarize(
            router.search("patentsview_patents").search(args.patent_query, limit=args.limit)
        ),
        "ofac_sanctions_lists": _summarize(
            router.search("ofac_sanctions_lists").search(args.sanctions_query, limit=args.limit)
        ),
        "github_repositories": _summarize(
            router.search("github_repositories").search(args.github_query, limit=args.limit)
        ),
        "huggingface_models": _summarize(
            router.search("huggingface_models").search(args.hf_query, limit=args.limit)
        ),
        "pdl_people_search": _summarize(
            router.search("pdl_people_search").search(args.pdl_query, limit=args.limit)
        ),
        "x_recent_posts_search": _summarize(
            router.search("x_recent_posts_search").search(args.x_query, limit=args.limit)
        ),
        "crustdata_signal_search": _summarize(
            router.search("crustdata_signal_search").search(args.crustdata_query, limit=args.limit)
        ),
        "courtlistener_search": _summarize(
            router.search("courtlistener_search").search(args.court_query, limit=args.limit)
        ),
        "education_competition_monitor": _summarize(
            router.search("education_competition_monitor").search(args.education_query, limit=args.limit)
        ),
        **external_output,
    }
    if os.getenv("COMPANIES_HOUSE_API_KEY"):
        output["companies_house_search"] = _summarize(
            router.search("companies_house_search").search(args.company_query, limit=args.limit)
        )
    else:
        output["companies_house_search"] = {
            "status": "skipped",
            "reason": "COMPANIES_HOUSE_API_KEY is not set.",
        }
    if os.getenv("GNEWS_API_KEY"):
        output["gnews_funding_news"] = _summarize(
            router.search("gnews_funding_news").search(args.funding_query, limit=args.limit)
        )
    else:
        output["gnews_funding_news"] = {
            "status": "skipped",
            "reason": "GNEWS_API_KEY is not set.",
        }
    if os.getenv("USAJOBS_API_KEY") and os.getenv("USAJOBS_USER_AGENT"):
        output["usajobs_search"] = _summarize(
            router.search("usajobs_search").search(args.jobs_query, limit=args.limit)
        )
    else:
        output["usajobs_search"] = {
            "status": "skipped",
            "reason": "USAJOBS_API_KEY or USAJOBS_USER_AGENT is not set.",
        }
    if os.getenv("FRED_API_KEY"):
        output["fred_series_search"] = _summarize(
            router.search("fred_series_search").search(args.fred_query, limit=args.limit)
        )
    else:
        output["fred_series_search"] = {
            "status": "skipped",
            "reason": "FRED_API_KEY is not set.",
        }
    if os.getenv("CENSUS_API_KEY"):
        output["census_international_trade"] = _summarize(
            router.search("census_international_trade").search(args.trade_query, limit=args.limit)
        )
    else:
        output["census_international_trade"] = {
            "status": "skipped",
            "reason": "CENSUS_API_KEY is not set.",
        }
    if os.getenv("SAM_GOV_API_KEY"):
        output["sam_gov_opportunities"] = _summarize(
            router.search("sam_gov_opportunities").search(args.sam_query, limit=args.limit)
        )
    else:
        output["sam_gov_opportunities"] = {
            "status": "skipped",
            "reason": "SAM_GOV_API_KEY is not set.",
        }

    if args.include_brave:
        if not os.getenv("BRAVE_SEARCH_API_KEY"):
            output["brave_web_search"] = {
                "status": "skipped",
                "reason": "BRAVE_SEARCH_API_KEY is not set.",
            }
        else:
            output["brave_web_search"] = _summarize(
                router.search("brave_web_search").search(args.web_query, limit=args.limit)
            )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
