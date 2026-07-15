from pathlib import Path

from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


def test_graph_bootstrap_retrieves_suitable_algorithm():
    graph = CapabilityKnowledgeGraph.bootstrap()
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
    graph.save(json_path, graphml_path)
    loaded = CapabilityKnowledgeGraph.load(json_path)
    assert loaded.graph.nodes[run_id]["status"] == "success"
    assert graphml_path.exists()
