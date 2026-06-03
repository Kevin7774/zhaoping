from __future__ import annotations

from typing import Any


class SearchProviderProtocol:
    def search(self, query: str, limit: int = 5) -> list[dict]:
        raise NotImplementedError


class SearchSourceCatalogProvider:
    def __init__(self, data_sources: dict[str, dict[str, Any]]) -> None:
        self.data_sources = data_sources

    def search(self, query: str, limit: int = 5) -> list[dict]:
        scored = [
            (self._score_source(query, source), source_key, source)
            for source_key, source in self.data_sources.items()
        ]
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        return [
            self._to_result(source_key, source, score)
            for score, source_key, source in ranked
            if score > 0
        ][:limit]

    def list_sources(self) -> list[dict]:
        return [
            self._to_result(source_key, source, score=0)
            for source_key, source in self.data_sources.items()
        ]

    def plan(self, query: str, limit: int = 8) -> dict:
        return {
            "query": query,
            "recommended_sources": self.search(query, limit=limit),
            "guardrails": [
                "优先使用官方 API、授权账号、公开网页、公开论文/披露文件或人工导出。",
                "不绕过登录、付费墙、robots.txt、平台反爬或访问控制。",
                "候选人个人信息只采集公开且与招聘评估相关的职业线索，并记录来源。",
            ],
        }

    def _score_source(self, query: str, source: dict[str, Any]) -> int:
        normalized_query = query.casefold()
        haystack_parts = [
            str(source.get("name_zh", "")),
            str(source.get("purpose", "")),
            " ".join(str(item) for item in source.get("source_names", [])),
            " ".join(str(item) for item in source.get("talent_signals", [])),
            " ".join(str(item) for item in source.get("suggested_queries", [])),
        ]
        haystack = " ".join(haystack_parts).casefold()

        score = 0
        for token in self._tokens(normalized_query):
            if token in haystack:
                score += 1
        if normalized_query and normalized_query in haystack:
            score += 3
        return score

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return [
            token.strip(" ,，/|:：()（）[]【】")
            for token in query.replace("/", " ").replace("-", " ").split()
            if token.strip(" ,，/|:：()（）[]【】")
        ]

    @staticmethod
    def _to_result(source_key: str, source: dict[str, Any], score: int) -> dict:
        return {
            "source_key": source_key,
            "name_zh": source["name_zh"],
            "source_names": source["source_names"],
            "purpose": source["purpose"],
            "talent_signals": source["talent_signals"],
            "suggested_queries": source["suggested_queries"],
            "access_pattern": source["access_pattern"],
            "risk_level": source["risk_level"],
            "freshness": source["freshness"],
            "score": score,
        }
