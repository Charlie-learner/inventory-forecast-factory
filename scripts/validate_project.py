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
from inventory_agent.services.audit import audit_as_markdown, build_submission_audit
from inventory_agent.services.replenishment import (
    calculate_replenishment,
    load_business_costs,
)
from inventory_agent.web.api_docs import openapi_document, post_route_handlers
from inventory_agent.web.server import ASSET_ROOT
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow
from run_acceptance_cases import run_acceptance_cases


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=inventory_agent",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ]
    )
    run([sys.executable, "-m", "ruff", "check", "inventory_agent", "tests", "scripts"])
    audit = build_submission_audit(ROOT)
    incomplete = [
        item
        for item in audit["items"]
        if item["required"] and item["status"] != "passed"
    ]
    if audit["summary"]["required_total"] < 19 or incomplete:
        details = ", ".join(
            f"{item['item_id']}={item['status']}" for item in incomplete
        )
        raise RuntimeError(f"Written-test submission audit is incomplete: {details}")
    audit_document = ROOT / "docs/evaluation_acceptance_matrix.md"
    expected_audit_markdown = audit_as_markdown(audit).strip()
    if (
        not audit_document.is_file()
        or audit_document.read_text(encoding="utf-8").strip()
        != expected_audit_markdown
    ):
        raise RuntimeError(
            "Submission audit document is stale; regenerate it with "
            "`python -m inventory_agent audit --format markdown "
            "--output docs/evaluation_acceptance_matrix.md`"
        )
    demand_demo = pd.read_csv(ROOT / "examples/business_data/demand_history.csv")
    if (
        len(demand_demo) < 2800
        or demand_demo["item_id"].nunique() != 6
        or demand_demo["store_code"].nunique() != 3
    ):
        raise RuntimeError("Multi-table inventory business demo is incomplete")
    business_data_path = ROOT / "examples/business_data/demand_history.csv"
    business_costs = load_business_costs(business_data_path, 1001, "1")
    replenishment = calculate_replenishment(
        business_data_path,
        1001,
        "1",
        target_inventory=174,
    )
    if (
        business_costs is None
        or business_costs.source != "replenishment_policy.csv"
        or replenishment.get("recommended_order_qty") != 132
    ):
        raise RuntimeError("Inventory-position replenishment decision is incomplete")
    acceptance = run_acceptance_cases()
    if not acceptance["summary"]["passed"]:
        raise RuntimeError("Multi-scenario acceptance cases failed")
    external_summary = json.loads(
        (
            ROOT
            / "examples/external_validation/live_validation_summary.json"
        ).read_text(encoding="utf-8")
    )
    if (
        external_summary["llm"]["status"] != "passed"
        or external_summary["research"]["record_count"] < 1
        or external_summary["secrets_exposed"]
    ):
        raise RuntimeError("Sanitized external-service evidence is incomplete")
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
    latest_showcase = audit["latest_showcase"]["path"]
    collaboration = json.loads(
        (
            ROOT / latest_showcase / "protocol_demo/review_manifest.json"
        ).read_text(encoding="utf-8")
    )
    implementation_candidates = collaboration.get("implementation_candidates", [])
    collaboration_roles = set(
        collaboration.get("multi_agent_collaboration", {}).get("roles", [])
    )
    if (
        len(implementation_candidates) != 3
        or sum(candidate.get("selected", False) for candidate in implementation_candidates)
        != 1
        or not all(
            candidate.get("validation", {}).get("valid")
            for candidate in implementation_candidates
        )
        or not any(
            candidate.get("collaboration", {})
            .get("review", {})
            .get("revision_applied")
            for candidate in implementation_candidates
        )
        or collaboration_roles
        != {
            "CodeArchitectureAgent",
            "CodeImplementationAgent",
            "CodeReviewAgent",
            "GeneratedCodeValidator",
        }
    ):
        raise RuntimeError("Multi-agent code collaboration evidence is incomplete")
    api_schema = openapi_document()
    documented_posts = {
        path
        for path, operations in api_schema["paths"].items()
        if "post" in operations
    }
    if (
        api_schema["openapi"] != "3.0.3"
        or documented_posts != set(post_route_handlers())
        or "/api/run" not in documented_posts
    ):
        raise RuntimeError("Generated API documentation is incomplete or stale")
    web_index = (ASSET_ROOT / "index.html").read_text(encoding="utf-8")
    if (
        "和库存预测 Agent 对话" not in web_index
        or "/api/docs" not in web_index
        or "全零历史诊断" not in web_index
        or "联网检索 DOI 行业资料" not in web_index
    ):
        raise RuntimeError("Web interaction and guidance evidence is incomplete")
    with tempfile.TemporaryDirectory(prefix="inventory-agent-validation-") as temp:
        output = Path(temp)
        extractor = CapabilityExtractor()
        repository_capabilities = extractor.extract(ROOT)
        forecast_names = {
            capability.name
            for capability in repository_capabilities
            if capability.implementation_kind == "forecast_model"
        }
        function_count = sum(
            capability.implementation_kind == "function"
            for capability in repository_capabilities
        )
        if (
            forecast_names
            != {
                "last_value",
                "moving_average",
                "seasonal_naive",
                "croston",
                "ridge_lag",
            }
            or function_count == 0
            or extractor.last_scan_report["errors"]
        ):
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
        implementations = result.get("implementation_candidates", [])
        if (
            len(implementations) != 1
            or not implementations[0]["selected"]
            or not implementations[0]["validation"]["valid"]
        ):
            raise RuntimeError("Generated implementation selection evidence is incomplete")
        business_report = Path(result["report_paths"]["business_markdown"])
        if (
            not business_report.exists()
            or "建议补货量" not in business_report.read_text(encoding="utf-8")
        ):
            raise RuntimeError("Business-facing report was not generated")
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
            f"repository_functions={function_count}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
