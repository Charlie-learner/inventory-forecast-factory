import json
from pathlib import Path

from inventory_agent.cli import main
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


def test_visualize_graph_command_writes_standalone_html(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("LLM_MODE", "mock")
    output = tmp_path / "graph.html"
    exit_code = main(
        [
            "visualize-graph",
            "--knowledge",
            str(tmp_path / "missing.json"),
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert "Inventory Capability Knowledge Graph" in output.read_text(encoding="utf-8")


def test_replicate_capability_command_writes_review_artifacts(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("LLM_MODE", "mock")
    root = Path(__file__).resolve().parents[1]
    manifest = tmp_path / "review.json"

    exit_code = main(
        [
            "replicate-capability",
            "--source",
            str(root / "examples/capabilities/moving_average.md"),
            "--output-dir",
            str(tmp_path / "generated"),
            "--manifest",
            str(manifest),
        ]
    )

    assert exit_code == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["review"]["status"] == "auto_validated"
    assert manifest.with_suffix(".md").exists()


def test_versions_command_promotes_validated_version(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    knowledge_path = tmp_path / "knowledge.json"
    graph = CapabilityKnowledgeGraph.bootstrap()
    graph.record_validation(
        1,
        "1",
        "moving_average",
        {"inventory_cost": 1.0},
        capability_version={
            "capability_version": "1.0.0",
            "generation_mode": "spec_template",
            "spec_hash": "1" * 64,
            "source_hash": "a" * 64,
            "source_ref": "source.md",
            "generated_path": "generated.py",
        },
    )
    graph.save(knowledge_path)

    exit_code = main(
        [
            "versions",
            "promote",
            "--knowledge",
            str(knowledge_path),
            "--model",
            "moving_average",
            "--version",
            "a" * 12,
        ]
    )

    assert exit_code == 0
    saved = CapabilityKnowledgeGraph.load(knowledge_path)
    assert saved.graph.nodes["version:moving_average:aaaaaaaaaaaa"][
        "lifecycle_status"
    ] == "active"
