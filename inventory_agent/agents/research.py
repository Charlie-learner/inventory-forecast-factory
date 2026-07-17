"""Agent for optional online industry research and knowledge extraction."""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from inventory_agent.llm.client import LLMClient, MockLLMClient
from inventory_agent.research.crossref import CrossrefResearchProvider


logger = logging.getLogger(__name__)


class ResearchProvider(Protocol):
    """Define the bounded metadata search contract."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


class IndustryResearchAgent:
    """Search, rank, analyze, and persist source-traceable industry evidence."""

    PROFILE_TERMS = {
        "intermittent": "intermittent demand Croston spare parts",
        "weekly_seasonal": "seasonal demand forecasting inventory",
        "trend": "demand forecasting trend regression inventory",
        "volatile": "volatile demand forecasting safety stock",
        "stable": "inventory demand forecasting stock control",
    }
    MODEL_TERMS = {
        "croston": ("croston", "intermittent demand", "spare parts"),
        "seasonal_naive": ("seasonal", "seasonality", "weekly"),
        "ridge_lag": ("regression", "autoregressive", "machine learning", "trend"),
        "moving_average": ("moving average", "smoothing"),
        "last_value": ("naive forecast", "benchmark", "baseline"),
    }

    def __init__(
        self,
        llm: LLMClient | None = None,
        provider: ResearchProvider | None = None,
    ) -> None:
        self.llm = llm or MockLLMClient()
        self.provider = provider or CrossrefResearchProvider()

    @staticmethod
    def _keywords(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9_-]{2,}", text.lower())
            if token not in {"the", "and", "for", "with", "from", "using"}
        }

    def _rank(
        self, records: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        query_terms = self._keywords(query)
        ranked = []
        for record in records:
            evidence = f"{record.get('title', '')} {record.get('abstract_excerpt', '')}"
            matched = query_terms & self._keywords(evidence)
            citations = max(int(record.get("citation_count", 0) or 0), 0)
            record = dict(record)
            record["relevance_score"] = round(
                len(matched) / max(len(query_terms), 1)
                + min(math.log1p(citations) / 20, 0.5),
                4,
            )
            record["matched_terms"] = sorted(matched)
            ranked.append(record)
        return sorted(
            ranked,
            key=lambda item: (
                -float(item["relevance_score"]),
                -int(item.get("citation_count", 0)),
                item.get("doi", ""),
            ),
        )

    def _deterministic_analysis(
        self, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        corpus = " ".join(
            f"{record.get('title', '')} {record.get('abstract_excerpt', '')}"
            for record in records
        ).lower()
        recommended = [
            model
            for model, terms in self.MODEL_TERMS.items()
            if any(term in corpus for term in terms)
        ]
        findings = [
            f"检索到 {len(records)} 条带 DOI/URL 的元数据记录；候选建议只用于规划，"
            "最终选择仍由本地滚动回测决定。"
        ]
        if recommended:
            findings.append("资料关键词关联的已注册候选：" + "、".join(recommended) + "。")
        return {
            "recommended_models": recommended,
            "findings": findings,
            "risks": [
                "元数据和摘要不能替代全文复核。",
                "网络资料不得绕过生成代码的安全与数值等价验证。",
            ],
            "analysis_mode": "deterministic",
        }

    def _llm_analysis(
        self, records: list[dict[str, Any]], profile: str
    ) -> dict[str, Any] | None:
        if isinstance(self.llm, MockLLMClient) or not records:
            return None
        response = self.llm.complete(
            "你是库存算法研究 Agent。只返回 JSON，字段为 recommended_models、findings、"
            "risks。recommended_models 只能从 last_value、moving_average、"
            "seasonal_naive、croston、ridge_lag 中选择。只依据给定标题和摘要，"
            "不得声称阅读了全文，不得输出代码。",
            json.dumps(
                {"demand_profile": profile, "records": records},
                ensure_ascii=False,
            ),
        )
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            text = "\n".join(lines)
        payload = json.loads(text)
        allowed = set(self.MODEL_TERMS)
        models = [
            model
            for model in payload.get("recommended_models", [])
            if model in allowed
        ]
        return {
            "recommended_models": models,
            "findings": [str(item) for item in payload.get("findings", [])][:8],
            "risks": [str(item) for item in payload.get("risks", [])][:8],
            "analysis_mode": "llm_evidence_analysis",
        }

    def research(
        self,
        description: str,
        profile: dict[str, Any],
        output: str | Path,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Run a bounded search and write a reviewable knowledge artifact."""

        demand_type = str(profile.get("demand_type", "stable"))
        query = (
            f"{self.PROFILE_TERMS.get(demand_type, self.PROFILE_TERMS['stable'])} "
            "algorithm validation"
        )
        warnings = []
        try:
            records = self._rank(self.provider.search(query, limit=limit), query)
            status = "success" if records else "no_results"
        except Exception as exc:
            logger.warning("Industry research degraded: %s", type(exc).__name__)
            records = []
            status = "degraded"
            warnings.append(f"{type(exc).__name__}: {exc}")
        analysis = self._deterministic_analysis(records)
        try:
            llm_analysis = self._llm_analysis(records, demand_type)
            if llm_analysis is not None:
                analysis = llm_analysis
        except Exception as exc:
            logger.warning("Research analysis fallback: %s", type(exc).__name__)
            warnings.append(f"LLM analysis fallback: {type(exc).__name__}: {exc}")
        payload = {
            "schema_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "provider": "crossref",
            "query": query,
            "request_excerpt": description[:300],
            "demand_profile": demand_type,
            "records": records,
            "analysis": analysis,
            "warnings": warnings,
            "safety_policy": (
                "Remote content is treated as untrusted evidence; no downloaded code is executed."
            ),
        }
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        payload["result_path"] = str(path)
        return payload
