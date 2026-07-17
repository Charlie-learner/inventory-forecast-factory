"""Regenerate external extraction, repair-loop, and complete graph evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.codegen.validator import (
    CodeValidationResult,
    GeneratedCodeValidator,
)
from inventory_agent.config import Settings
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.agents.report import ReportAgent
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_DIR = Path("examples/capabilities")
REPAIR_OUTPUT = Path("examples/repair_run")
GRAPH_OUTPUT = Path("examples/knowledge_graph")
REPORT_EXAMPLE_ROOTS = (
    Path("examples/complete_run"),
    Path("examples/detailed_run"),
    Path("examples/extraction_run"),
    Path("examples/repair_run"),
)


class _FailFinalCodeOnceValidator:
    """Inject one reviewable syntax failure only for the selected final code."""

    def __init__(self) -> None:
        self.failed = False
        self.delegate = GeneratedCodeValidator()

    def validate(
        self,
        path: Path,
        reference_model: str | None = None,
        reference_parameters: dict | None = None,
    ) -> CodeValidationResult:
        selected_final_code = path.parent.name == "generated"
        if selected_final_code and not self.failed:
            self.failed = True
            return CodeValidationResult(
                valid=False,
                checks={
                    "syntax": False,
                    "imports": False,
                    "interface": False,
                    "runtime": False,
                    "stability": False,
                    "equivalence": False,
                },
                errors=(
                    "syntax: injected demonstration failure before safe repair",
                ),
            )
        return self.delegate.validate(
            path,
            reference_model=reference_model,
            reference_parameters=reference_parameters,
        )


def _extract_external_capabilities() -> list:
    sources = sorted(CAPABILITY_DIR.glob("*.md"))
    agent = CapabilityExtractionAgent()
    capabilities = agent.extract_sources(sources)
    CapabilityExtractionAgent.write_result(
        capabilities,
        Path("knowledge/extracted_external_capabilities.json"),
        agent.scan_reports,
    )
    return capabilities


def _generate_repair_and_graph_example(capability_sources: list[Path]) -> dict:
    REPAIR_OUTPUT.mkdir(parents=True, exist_ok=True)
    GRAPH_OUTPUT.mkdir(parents=True, exist_ok=True)
    knowledge_path = GRAPH_OUTPUT / "complete_capability_graph.json"
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=knowledge_path,
    )
    # Reset previously committed evidence so regeneration stays bounded and repeatable.
    workflow.knowledge = CapabilityKnowledgeGraph.bootstrap(workflow.registry)
    workflow.validator = _FailFinalCodeOnceValidator()
    result = workflow.run(
        "为商品 1002 在仓库 1 预测未来14天目标库存，比较候选算法并展示失败修复",
        Path("examples/business_data/demand_history.csv"),
        REPAIR_OUTPUT,
        capability_sources=capability_sources,
        trace_level="full",
        keep_runs=1,
    )
    if len(result["repairs"]) != 1 or not result["code_validation"].valid:
        raise RuntimeError("Repair demonstration did not repair exactly one injected failure")
    graph = CapabilityKnowledgeGraph.load(knowledge_path)
    versions = graph.capability_versions(result["selected_model"])
    graph.promote_version(result["selected_model"], versions[0]["id"])
    graph.save(
        knowledge_path,
        GRAPH_OUTPUT / "complete_capability_graph.graphml",
        GRAPH_OUTPUT / "complete_capability_graph.html",
    )
    run_dir = Path(result["trace_paths"]["manifest"]).parent
    index = {
        "schema_version": "1.0",
        "run_dir": str(run_dir),
        "status": "success_after_repair",
        "selected_model": result["selected_model"],
        "repair_count": len(result["repairs"]),
        "failure_history": result["failure_history"],
        "trace_paths": dict(result["trace_paths"]),
        "knowledge_graph": {
            "json": "examples/knowledge_graph/complete_capability_graph.json",
            "graphml": "examples/knowledge_graph/complete_capability_graph.graphml",
            "html": "examples/knowledge_graph/complete_capability_graph.html",
        },
    }
    (REPAIR_OUTPUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index


def _refresh_committed_reports() -> int:
    """Regenerate human-readable reports from committed machine reports."""

    refreshed = 0
    report_agent = ReportAgent()
    for root in REPORT_EXAMPLE_ROOTS:
        if not root.exists():
            continue
        for json_path in root.rglob("validation_report.json"):
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            report_agent.create(payload, json_path.parent)
            refreshed += 1
    return refreshed


def main() -> int:
    """Generate all submission evidence from tracked source materials."""

    os.chdir(ROOT)
    capabilities = _extract_external_capabilities()
    index = _generate_repair_and_graph_example(
        sorted(CAPABILITY_DIR.glob("*.md"))
    )
    refreshed_reports = _refresh_committed_reports()
    print(
        "Generated submission evidence:",
        f"external_capabilities={len(capabilities)}",
        f"selected_model={index['selected_model']}",
        f"repairs={index['repair_count']}",
        f"reports={refreshed_reports}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
