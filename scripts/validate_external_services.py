"""Run explicit network checks that are intentionally excluded from offline CI."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from inventory_agent.agents.research import IndustryResearchAgent
from inventory_agent.config import Settings
from inventory_agent.llm.client import (
    MockLLMClient,
    create_llm,
    verify_llm_connection,
)


def _safe_error(exc: Exception) -> str:
    """Return bounded diagnostics without serializing credentials or request headers."""

    return f"{type(exc).__name__}: {str(exc)[:300]}"


def main() -> int:
    """Validate the configured LLM and DOI research provider with real requests."""

    parser = argparse.ArgumentParser(
        description="Live, secret-safe external LLM and Crossref validation"
    )
    parser.add_argument(
        "--output-dir", default="artifacts/external_validation"
    )
    parser.add_argument(
        "--profile",
        choices=["stable", "volatile", "intermittent", "weekly_seasonal", "trend"],
        default="intermittent",
    )
    parser.add_argument("--limit", type=int, choices=range(1, 11), default=5)
    args = parser.parse_args()

    settings = Settings.from_env()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    llm = MockLLMClient()
    try:
        llm = create_llm(settings)
        llm_result = verify_llm_connection(settings, client=llm)
    except Exception as exc:
        llm_result = {
            "status": "failed",
            "provider_type": "openai_compatible",
            "model": settings.model,
            "base_url": settings.base_url,
            "latency_ms": None,
            "error": _safe_error(exc),
            "api_key_exposed": False,
        }
        llm = MockLLMClient()
    research = IndustryResearchAgent(llm).research(
        "inventory demand forecasting and stock control",
        {"demand_type": args.profile},
        output / "online_knowledge_extraction.json",
        limit=args.limit,
    )
    summary = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "llm": llm_result,
        "research": {
            "status": research["status"],
            "provider": research["provider"],
            "query": research["query"],
            "record_count": len(research["records"]),
            "recommended_models": research["analysis"]["recommended_models"],
            "analysis_mode": research["analysis"]["analysis_mode"],
            "result_path": research["result_path"],
            "warnings": research["warnings"],
        },
        "secrets_exposed": False,
    }
    (output / "external_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = "\n".join(
        [
            "# 外部服务联网测试",
            "",
            f"- 时间：{summary['created_at']}",
            f"- LLM：{llm_result['status']}，模型 `{llm_result['model']}`，"
            f"延迟 {llm_result['latency_ms'] or '未取得'} ms；",
            f"- 行业检索：{research['status']}，Crossref 返回 "
            f"{len(research['records'])} 条 DOI/URL 记录；",
            f"- 资料分析：{research['analysis']['analysis_mode']}；",
            "- 密钥：未写入报告、Trace 或知识抽取文件；",
            "- 注意：该脚本需要网络，不属于离线 CI 门禁。",
        ]
    )
    (output / "external_validation_summary.md").write_text(
        markdown + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if llm_result["status"] == "passed" and research["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
