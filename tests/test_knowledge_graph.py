from pathlib import Path

from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


def test_graph_bootstrap_retrieves_suitable_algorithm():
    graph = CapabilityKnowledgeGraph.bootstrap()
    assert graph.graph.graph["schema_version"] == "1.4"
    records = graph.retrieve_algorithms("intermittent", limit=2)
    assert records[0]["name"] == "croston"
    assert "target inventory" in records[0]["output_contract"]
    metric = graph.graph.nodes["metric:inventory_cost"]
    assert metric["evaluation_unit"] == "horizon_total"
    assert metric["cost_a"] == "understock"


def test_graph_round_trip_and_validation_writeback(tmp_path: Path):
    graph = CapabilityKnowledgeGraph.bootstrap()
    run_id = graph.record_validation(1, "2", "croston", {"wape": 0.2})
    json_path = tmp_path / "knowledge.json"
    graphml_path = tmp_path / "knowledge.graphml"
    html_path = tmp_path / "knowledge.html"
    graph.save(json_path, graphml_path, html_path)
    loaded = CapabilityKnowledgeGraph.load(json_path)
    assert loaded.graph.nodes[run_id]["status"] == "success"
    assert graphml_path.exists()
    assert "库存算法能力知识图谱" in html_path.read_text(encoding="utf-8")
    assert "croston" in html_path.read_text(encoding="utf-8")


def test_graph_validation_history_influences_suitable_algorithm_ranking():
    graph = CapabilityKnowledgeGraph.bootstrap()
    graph.record_validation(1, "1", "seasonal_naive", {"inventory_cost": 9.0})
    graph.record_validation(1, "1", "moving_average", {"inventory_cost": 2.0})
    records = graph.retrieve_algorithms("stable", limit=2)
    assert [record["name"] for record in records] == ["moving_average", "seasonal_naive"]
    assert records[0]["validation_count"] == 1
    assert records[0]["mean_inventory_cost"] == 2.0


def test_successful_repair_experience_is_retrievable_by_failure_category():
    graph = CapabilityKnowledgeGraph.bootstrap()
    failure = {
        "category": "runtime",
        "fingerprint": "runtime123",
        "normalized_error": "runtime: value error",
        "retryable": True,
    }
    graph.record_validation(
        1,
        "1",
        "moving_average",
        {"inventory_cost": 2.0},
        repair="fallback to safe moving-average template",
        failure_history=[failure],
    )

    experiences = graph.repair_experience("moving_average", "runtime")

    assert len(experiences) == 1
    assert experiences[0]["fingerprint"] == "runtime123"
    assert "safe moving-average" in experiences[0]["strategy"]
    failure_node = graph.graph.nodes["failure:runtime123"]
    assert failure_node["occurrence_count"] == 1


def test_capability_versions_can_be_compared_promoted_and_rolled_back():
    graph = CapabilityKnowledgeGraph.bootstrap()
    first = {
        "capability_version": "1.0.0",
        "generation_mode": "spec_template",
        "spec_hash": "1" * 64,
        "source_hash": "a" * 64,
        "source_ref": "first.md",
        "generated_path": "first.py",
    }
    second = {
        **first,
        "capability_version": "1.1.0",
        "spec_hash": "2" * 64,
        "source_hash": "b" * 64,
        "source_ref": "second.md",
        "generated_path": "second.py",
    }
    graph.record_validation(
        1, "1", "moving_average", {"inventory_cost": 2.0}, capability_version=first
    )
    graph.record_validation(
        1, "1", "moving_average", {"inventory_cost": 1.5}, capability_version=second
    )

    versions = graph.capability_versions("moving_average")
    assert len(versions) == 2
    comparison = graph.compare_versions("moving_average", "a" * 12, "b" * 12)
    assert comparison["differences"]["spec_hash"]["left"] == "1" * 64

    graph.promote_version("moving_average", "b" * 12)
    assert graph.graph.nodes["version:moving_average:bbbbbbbbbbbb"][
        "lifecycle_status"
    ] == "active"
    event = graph.rollback_version("moving_average", "a" * 12)
    assert graph.graph.nodes["version:moving_average:aaaaaaaaaaaa"][
        "lifecycle_status"
    ] == "active"
    assert graph.graph.nodes[event]["action"] == "rollback"
