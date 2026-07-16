"""One-command project validation used before submission."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from inventory_agent.config import Settings
from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.extraction.extractor import CapabilityExtractor
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run([sys.executable, "-m", "pytest"])
    run([sys.executable, "-m", "ruff", "check", "inventory_agent", "tests", "scripts"])
    demand_demo = pd.read_csv(ROOT / "examples/business_data/demand_history.csv")
    if (
        len(demand_demo) < 2800
        or demand_demo["item_id"].nunique() != 6
        or demand_demo["store_code"].nunique() != 3
    ):
        raise RuntimeError("Multi-table inventory business demo is incomplete")
    external = json.loads(
        (ROOT / "knowledge/extracted_external_capabilities.json").read_text(
            encoding="utf-8"
        )
    )
    if external["count"] != 5 or not all(
        capability["source_url"] and capability["evidence_refs"]
        for capability in external["capabilities"]
    ):
        raise RuntimeError("External capability extraction evidence is incomplete")
    complete_graph = CapabilityKnowledgeGraph.load(
        ROOT / "examples/knowledge_graph/complete_capability_graph.json"
    )
    required_node_types = {
        "Algorithm",
        "SourceArtifact",
        "ValidationRun",
        "FailureCase",
        "RepairStrategy",
        "CapabilityVersion",
        "VersionEvent",
    }
    actual_node_types = {
        attributes.get("type")
        for _, attributes in complete_graph.graph.nodes(data=True)
    }
    if not required_node_types <= actual_node_types:
        raise RuntimeError("Complete submission knowledge graph lacks lifecycle evidence")
    repair_index = json.loads(
        (ROOT / "examples/repair_run/index.json").read_text(encoding="utf-8")
    )
    if repair_index["status"] != "success_after_repair" or repair_index[
        "repair_count"
    ] != 1:
        raise RuntimeError("Repair-loop submission example is incomplete")
    with tempfile.TemporaryDirectory(prefix="inventory-agent-validation-") as temp:
        output = Path(temp)
        extractor = CapabilityExtractor()
        repository_capabilities = extractor.extract(ROOT)
        if len(repository_capabilities) != 5 or extractor.last_scan_report["errors"]:
            raise RuntimeError("Local repository capability extraction failed")
        moving_average = next(
            capability
            for capability in repository_capabilities
            if capability.name == "moving_average"
        )
        replication = CapabilityReplicator().replicate(
            moving_average,
            output / "replication/generated",
            output / "replication/review.json",
        )
        if not replication["review"]["registration_ready"]:
            raise RuntimeError("Standalone capability replication was not validated")
        result = InventoryCapabilityWorkflow(
            settings=Settings(llm_mode="mock"),
            knowledge_path=output / "knowledge.json",
        ).run(
            "为商品 3424 在仓库 1 预测未来14天需求",
            ROOT / "examples/data/cainiao_demo.csv",
            output / "runs",
            capability_sources=[ROOT / "examples/capabilities/moving_average.md"],
            trace_level="full",
            keep_runs=2,
        )
        if not result["code_validation"].valid:
            raise RuntimeError("Generated capability did not pass validation")
        if not result["code_validation"].checks.get("stability"):
            raise RuntimeError("Generated capability stability check did not run")
        if not result["code_validation"].checks.get("equivalence"):
            raise RuntimeError("Generated capability did not match its reference behavior")
        if result["report"]["capability_extraction"]["count"] != 1:
            raise RuntimeError("Capability source was not extracted into the workflow")
        if "from inventory_agent.forecasting.registry" in result["generated"].source:
            raise RuntimeError("Generated code is still a registry wrapper")
        if len(result.get("candidate_code_solutions", [])) != 3:
            raise RuntimeError("Full trace did not generate all candidate code solutions")
        trace_paths = result.get("trace_paths") or {}
        if not all(Path(path).exists() for path in trace_paths.values()):
            raise RuntimeError("Detailed workflow trace artifacts were not generated")
        saved_knowledge = CapabilityKnowledgeGraph.load(output / "knowledge.json")
        versions = saved_knowledge.capability_versions(result["selected_model"])
        if len(versions) != 1 or not versions[0]["validated"]:
            raise RuntimeError("Validated capability version was not deposited")
        saved_knowledge.promote_version(result["selected_model"], versions[0]["id"])
        if saved_knowledge.capability_versions(result["selected_model"])[0][
            "lifecycle_status"
        ] != "active":
            raise RuntimeError("Capability version promotion failed")
        graph_html = output / "knowledge.html"
        if not graph_html.exists() or "库存算法能力知识图谱" not in graph_html.read_text(
            encoding="utf-8"
        ):
            raise RuntimeError("Knowledge graph HTML visualization was not generated")
        print(
            "E2E OK:",
            result["selected_model"],
            f"target_inventory={result['benchmark']['target_inventory']:.2f}",
            f"repository_capabilities={len(repository_capabilities)}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
