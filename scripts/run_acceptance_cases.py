"""Run deterministic multi-scenario acceptance cases and write review evidence."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.config import Settings
from inventory_agent.extraction.extractor import CapabilityExtractor
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.services.replenishment import calculate_replenishment
from inventory_agent.web.api_docs import openapi_document, post_route_handlers
from inventory_agent.web.app import WebApplication


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_DATA = ROOT / "examples/business_data"
OUTPUT = ROOT / "examples/acceptance"


def run_acceptance_cases() -> dict[str, Any]:
    """Execute representative cases without network access."""

    application = WebApplication(
        workspace=ROOT,
        settings=Settings(llm_mode="mock"),
        output_root="artifacts/acceptance_runs",
        knowledge_path="artifacts/acceptance_knowledge.json",
    )
    item_master = pd.read_csv(BUSINESS_DATA / "item_master.csv")
    benchmark_cases = []
    models = [
        "last_value",
        "moving_average",
        "seasonal_naive",
        "croston",
        "ridge_lag",
    ]
    for row in item_master.itertuples(index=False):
        result = application.benchmark(
            {
                "data_path": "examples/business_data/demand_history.csv",
                "item_id": int(row.item_id),
                "store_code": "1",
                "horizon": 14,
                "task_type": "inventory_target",
                "models": models,
            }
        )
        target = float(result["target_inventory"])
        if (
            not math.isfinite(target)
            or target < 0
            or len(result["candidates"]) != len(models)
            or result["costs"]["source"] != "replenishment_policy.csv"
        ):
            raise RuntimeError(f"Invalid benchmark result for item {row.item_id}")
        advice = calculate_replenishment(
            BUSINESS_DATA / "demand_history.csv",
            int(row.item_id),
            "1",
            target,
        )
        if not advice["available"] or advice["recommended_order_qty"] < 0:
            raise RuntimeError(
                f"Invalid replenishment result for item {row.item_id}"
            )
        benchmark_cases.append(
            {
                "item_id": int(row.item_id),
                "declared_pattern": row.demand_pattern,
                "detected_profile": result["profile"]["demand_type"],
                "selected_model": result["selected_model"],
                "target_inventory": target,
                "recommended_order_qty": advice["recommended_order_qty"],
                "inventory_cost": next(
                    candidate["metrics"]["inventory_cost"]
                    for candidate in result["candidates"]
                    if candidate["model"] == result["selected_model"]
                ),
                "status": "passed",
            }
        )

    data_path = BUSINESS_DATA / "demand_history.csv"
    language_cases = {
        "multiple_items": application._request_targets(
            "预测商品 1001 和 1003 在仓库 1 未来14天库存",
            data_path,
        ),
        "all_warehouses": application._request_targets(
            "预测商品 1003 在所有仓库未来7天库存",
            data_path,
        ),
    }
    if language_cases["multiple_items"] != [(1001, "1"), (1003, "1")]:
        raise RuntimeError("Multiple-item natural-language expansion failed")
    if language_cases["all_warehouses"] != [
        (1003, "1"),
        (1003, "2"),
        (1003, "3"),
    ]:
        raise RuntimeError("All-warehouse natural-language expansion failed")

    spec = CapabilityExtractor().extract(
        ROOT / "examples/capabilities/moving_average.md"
    )[0]
    with tempfile.TemporaryDirectory(prefix="acceptance-replication-") as temp:
        temp_path = Path(temp)
        replication = CapabilityReplicator().replicate(
            spec,
            temp_path / "generated",
            temp_path / "review.json",
        )
        replication_case = {
            "valid": replication["validation"]["valid"],
            "equivalence_cases": replication["validation"][
                "equivalence_cases"
            ],
            "review_status": replication["review"]["status"],
            "implementation_candidates": len(
                replication["implementation_candidates"]
            ),
        }
    if (
        not replication_case["valid"]
        or replication_case["equivalence_cases"] != 4
        or replication_case["review_status"] != "auto_validated"
    ):
        raise RuntimeError("Capability replication acceptance failed")

    repair_index = json.loads(
        (ROOT / "examples/repair_run/index.json").read_text(encoding="utf-8")
    )
    graph = CapabilityKnowledgeGraph.load(
        ROOT / "examples/knowledge_graph/complete_capability_graph.json"
    )
    node_types = {
        attributes.get("type")
        for _, attributes in graph.graph.nodes(data=True)
    }
    lifecycle_types = {
        "ValidationRun",
        "FailureCase",
        "RepairStrategy",
        "CapabilityVersion",
        "VersionEvent",
    }
    api_schema = openapi_document()
    documented_posts = {
        path
        for path, operations in api_schema["paths"].items()
        if "post" in operations
    }
    cross_component_cases = {
        "repair_loop": {
            "status": repair_index["status"],
            "repair_count": repair_index["repair_count"],
            "passed": (
                repair_index["status"] == "success_after_repair"
                and repair_index["repair_count"] == 1
            ),
        },
        "knowledge_lifecycle": {
            "required_types": sorted(lifecycle_types),
            "passed": lifecycle_types <= node_types,
        },
        "api_documentation": {
            "openapi": api_schema["openapi"],
            "post_routes": sorted(documented_posts),
            "passed": documented_posts == set(post_route_handlers()),
        },
        "capability_replication": {
            **replication_case,
            "passed": True,
        },
    }
    if not all(case["passed"] for case in cross_component_cases.values()):
        raise RuntimeError("One or more cross-component acceptance cases failed")
    return {
        "schema_version": "1.0",
        "mode": "deterministic_mock",
        "benchmark_cases": benchmark_cases,
        "language_cases": {
            name: [list(target) for target in targets]
            for name, targets in language_cases.items()
        },
        "cross_component_cases": cross_component_cases,
        "summary": {
            "benchmark_cases": len(benchmark_cases),
            "cross_component_cases": len(cross_component_cases),
            "passed": True,
        },
    }


def write_report(result: dict[str, Any], output_dir: Path = OUTPUT) -> None:
    """Write machine-readable and reviewer-friendly acceptance evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "acceptance_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    benchmark_rows = [
        "| 商品 | 预设需求类型 | 检测画像 | 选中算法 | 目标库存 | 建议补货 | 库存成本 |",
        "|---:|---|---|---|---:|---:|---:|",
        *[
            f"| {case['item_id']} | {case['declared_pattern']} | "
            f"{case['detected_profile']} | {case['selected_model']} | "
            f"{case['target_inventory']:.2f} | "
            f"{case['recommended_order_qty']:.2f} | "
            f"{case['inventory_cost']:.2f} |"
            for case in result["benchmark_cases"]
        ],
    ]
    component_rows = [
        "| 验收项 | 结果 | 证据摘要 |",
        "|---|---|---|",
        *[
            f"| {name} | {'通过' if case['passed'] else '失败'} | "
            f"`{json.dumps(case, ensure_ascii=False, default=str)}` |"
            for name, case in result["cross_component_cases"].items()
        ],
    ]
    markdown = "\n".join(
        [
            "# 多场景自动验收报告",
            "",
            "- 模式：确定性 Mock，不依赖外部 API；",
            f"- 需求画像与库存案例：{len(result['benchmark_cases'])} 个；",
            f"- 跨组件案例：{len(result['cross_component_cases'])} 个；",
            "- 总结：全部通过。",
            "",
            "## 六类库存需求与补货结果",
            "",
            *benchmark_rows,
            "",
            "## 自然语言批量范围",
            "",
            f"- 多商品：`{result['language_cases']['multiple_items']}`",
            f"- 所有仓库：`{result['language_cases']['all_warehouses']}`",
            "",
            "## 核心闭环验收",
            "",
            *component_rows,
            "",
            "## 使用说明",
            "",
            "重新运行：`uv run python scripts/run_acceptance_cases.py`。",
            "该报告用于提交评审证据，不替代完整的 pytest、覆盖率和端到端验收。",
        ]
    )
    (output_dir / "acceptance_report.md").write_text(
        markdown + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Run cases and update committed acceptance evidence."""

    result = run_acceptance_cases()
    write_report(result)
    print(
        "Acceptance cases passed:",
        f"benchmarks={result['summary']['benchmark_cases']}",
        f"cross_component={result['summary']['cross_component_cases']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
