import json
from pathlib import Path

import pandas as pd

from inventory_agent.extraction.extractor import CapabilityExtractor
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_DATA = ROOT / "examples/business_data"


def test_business_demo_tables_are_relationally_complete():
    demand = pd.read_csv(BUSINESS_DATA / "demand_history.csv")
    items = pd.read_csv(BUSINESS_DATA / "item_master.csv")
    inventory = pd.read_csv(BUSINESS_DATA / "inventory_snapshot.csv")
    policies = pd.read_csv(BUSINESS_DATA / "replenishment_policy.csv")
    events = pd.read_csv(BUSINESS_DATA / "demand_events.csv")

    assert len(demand) >= 2800
    assert demand["item_id"].nunique() == 6
    assert demand["store_code"].nunique() == 3
    assert not demand.duplicated(["date", "item_id", "store_code"]).any()
    assert set(items["demand_pattern"]) == {
        "stable",
        "weekly_seasonal",
        "intermittent",
        "trend",
        "volatile",
        "cold_start",
    }
    assert set(demand["item_id"]) == set(items["item_id"])
    assert set(inventory["item_id"]) == set(items["item_id"])
    assert set(policies["item_id"]) == set(items["item_id"])
    assert len(inventory) == len(policies) == 18
    assert (inventory["lead_time_days"] > 0).all()
    assert policies["target_service_level"].between(0, 1).all()
    assert {"promotion", "stockout", "new_product_launch"} <= set(
        events["event_type"]
    )


def test_business_demo_source_metadata_is_explicit():
    metadata = json.loads(
        (BUSINESS_DATA / "source_metadata.json").read_text(encoding="utf-8")
    )

    assert metadata["source_type"] == "deterministic_synthetic"
    assert metadata["contains_third_party_raw_records"] is False
    assert metadata["tables"]["demand_history.csv"]["rows"] >= 2800

    cainiao_metadata = json.loads(
        (ROOT / "examples/data/source_metadata.json").read_text(encoding="utf-8")
    )
    assert cainiao_metadata["source_url"].startswith("https://tianchi.aliyun.com/")
    assert cainiao_metadata["rows"] == 140
    assert cainiao_metadata["contains_cost_configuration"] is False


def test_external_capability_documents_include_reviewable_provenance():
    extractor = CapabilityExtractor()
    specs = []
    for path in sorted((ROOT / "examples/capabilities").glob("*.md")):
        specs.extend(extractor.extract(path))

    assert {spec.name for spec in specs} == {
        "last_value",
        "moving_average",
        "seasonal_naive",
        "croston",
        "ridge_lag",
    }
    assert all(spec.source_url.startswith("https://") for spec in specs)
    assert all(spec.source_title for spec in specs)
    assert all(spec.accessed_at == "2026-07-16" for spec in specs)
    assert all(spec.review_status == "source_reviewed" for spec in specs)
    assert all(spec.evidence_refs for spec in specs)


def test_committed_repair_and_complete_graph_evidence_are_linked():
    index = json.loads(
        (ROOT / "examples/repair_run/index.json").read_text(encoding="utf-8")
    )
    run_dir = ROOT / index["run_dir"]
    report = json.loads(
        (run_dir / "validation_report.json").read_text(encoding="utf-8")
    )
    graph = CapabilityKnowledgeGraph.load(
        ROOT / "examples/knowledge_graph/complete_capability_graph.json"
    )
    node_types = {
        attributes.get("type")
        for _, attributes in graph.graph.nodes(data=True)
    }

    assert index["status"] == "success_after_repair"
    assert index["repair_count"] == 1
    assert len(report["repairs"]) == 1
    assert len(report["failure_history"]) == 1
    assert {
        "SourceArtifact",
        "ValidationRun",
        "FailureCase",
        "RepairStrategy",
        "CapabilityVersion",
        "VersionEvent",
    } <= node_types
