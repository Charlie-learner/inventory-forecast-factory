import json
from dataclasses import fields
from pathlib import Path

import pytest

from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.domain import CapabilitySpec
from inventory_agent.extraction.extractor import CapabilityExtractor
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


ROOT = Path(__file__).resolve().parents[1]


def test_extract_structured_markdown_with_provenance(tmp_path: Path):
    source = tmp_path / "capability.md"
    source.write_text(
        """# Stable demand capability
- name: moving_average
- description: Average recent demand.
- template_name: moving_average
- suitable_for: stable, short_history
- metrics: inventory_cost, wape
- dependencies: pandas
- parameters: {"window": 21}
- version: 2.0.0
""",
        encoding="utf-8",
    )
    spec = CapabilityExtractor().extract(source)[0]
    assert spec.name == "moving_average"
    assert spec.parameters == {"window": 21}
    assert spec.suitable_for == ("stable", "short_history")
    assert spec.source_type == "document"
    assert len(spec.source_hash) == 64


def test_extract_forecast_capabilities_from_real_python_source():
    specs = CapabilityExtractor().extract(
        ROOT / "inventory_agent/forecasting/models.py"
    )
    by_name = {spec.name: spec for spec in specs}
    assert set(by_name) == {
        "last_value",
        "moving_average",
        "seasonal_naive",
        "croston",
        "ridge_lag",
    }
    assert by_name["moving_average"].parameters == {"window": 14}
    assert by_name["last_value"].dependencies == ("numpy", "pandas")
    assert by_name["croston"].dependencies == ("numpy", "pandas")
    assert by_name["ridge_lag"].dependencies == ("numpy", "pandas", "sklearn")
    assert by_name["croston"].suitable_for == ("intermittent", "many_zeros")
    assert by_name["ridge_lag"].suitable_for == ("trend", "dense", "volatile")
    assert by_name["croston"].extracted_by == "python_ast"


def test_recursively_extract_capabilities_from_local_repository():
    extractor = CapabilityExtractor()
    specs = extractor.extract(ROOT)

    assert {spec.name for spec in specs} == {
        "last_value",
        "moving_average",
        "seasonal_naive",
        "croston",
        "ridge_lag",
    }
    assert extractor.last_scan_report["source_kind"] == "repository"
    assert extractor.last_scan_report["files_scanned"] > 1
    assert extractor.last_scan_report["files_matched"] == 1
    assert extractor.last_scan_report["capabilities_found"] == 5


def test_repository_scan_has_a_configurable_file_limit(tmp_path: Path):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("value = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exceeds 1 Python files"):
        CapabilityExtractor(max_repository_files=1).extract(tmp_path)


def test_extraction_result_and_graph_ingestion_are_auditable(tmp_path: Path):
    specs = CapabilityExtractor().extract(
        ROOT / "examples/capabilities/moving_average.md"
    )
    result_path = CapabilityExtractionAgent.write_result(
        specs,
        tmp_path / "extracted.json",
        [{"source_kind": "file", "files_scanned": 1}],
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["scan_reports"][0]["files_scanned"] == 1
    graph = CapabilityKnowledgeGraph.bootstrap()
    graph.ingest_capabilities(specs)
    round_trip = graph.capability_spec("moving_average")
    assert round_trip.version == "1.1.0"
    assert round_trip.parameters == {"window": 14}
    source_edges = [
        edge
        for edge in graph.graph.out_edges("algorithm:moving_average", data=True)
        if edge[2].get("relation") == "EXTRACTED_FROM"
    ]
    assert len(source_edges) == 1


def test_capability_spec_json_schema_covers_every_exported_field():
    schema = json.loads(
        (ROOT / "knowledge/capability_spec.schema.json").read_text(encoding="utf-8")
    )

    assert set(schema["properties"]) == {field.name for field in fields(CapabilitySpec)}
    assert {"source_hash", "confidence", "review_status"} <= set(schema["required"])
