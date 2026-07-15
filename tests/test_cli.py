from pathlib import Path

from inventory_agent.cli import main


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
