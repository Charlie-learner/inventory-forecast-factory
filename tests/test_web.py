import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from inventory_agent.config import Settings
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.web.app import WebApplication
from inventory_agent.web.server import ASSET_ROOT, create_server


ROOT = Path(__file__).resolve().parents[1]


def _request(url: str, payload: dict | None = None) -> tuple[int, str, str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=10) as response:
        return (
            response.status,
            response.headers.get_content_type(),
            response.read().decode("utf-8"),
        )


def test_web_index_is_self_contained_and_utf8():
    source = (ASSET_ROOT / "index.html").read_text(encoding="utf-8")

    assert "<title>库存算法能力工厂</title>" in source
    assert "完整 Agent 能力工厂" in source
    assert "styles.css" not in source
    assert "app.js" not in source


def test_web_server_exposes_dashboard_api_and_graph(tmp_path: Path):
    application = WebApplication(
        workspace=ROOT,
        settings=Settings(llm_mode="mock"),
        output_root=tmp_path.relative_to(ROOT) if ROOT in tmp_path.parents else "artifacts/runs",
        knowledge_path="knowledge/base_capability_graph.json",
    )
    server = create_server(application, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, content_type, index = _request(base_url + "/")
        assert status == 200
        assert content_type == "text/html"
        assert "库存算法能力工厂" in index

        status, content_type, body = _request(base_url + "/api/overview")
        overview = json.loads(body)
        assert status == 200
        assert content_type == "application/json"
        assert overview["counts"]["algorithms"] == 5
        assert overview["counts"]["validation_profiles"] >= 3

        status, content_type, graph = _request(base_url + "/graph")
        assert status == 200
        assert content_type == "text/html"
        assert "库存算法能力知识图谱" in graph
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_benchmark_api_uses_real_backtest():
    application = WebApplication(
        workspace=ROOT,
        settings=Settings(llm_mode="mock"),
        output_root="artifacts/runs",
        knowledge_path="knowledge/base_capability_graph.json",
    )

    result = application.benchmark(
        {
            "data_path": "examples/data/cainiao_demo.csv",
            "item_id": 3424,
            "store_code": "1",
            "models": ["last_value", "moving_average"],
            "horizon": 14,
            "task_type": "inventory_target",
        }
    )

    assert len(result["candidates"]) == 2
    assert result["selected_model"] in {"last_value", "moving_average"}
    assert result["validation_profile"]["primary_metric"] == "inventory_cost"


def test_web_version_management_exposes_lifecycle_and_metrics(tmp_path: Path):
    knowledge_path = tmp_path / "knowledge.json"
    graph = CapabilityKnowledgeGraph.bootstrap()
    graph.record_validation(
        1,
        "1",
        "moving_average",
        {"inventory_cost": 1.0},
        validation_checks={"syntax": True},
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
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        knowledge_path="knowledge.json",
        output_root="runs",
    )

    before = application.versions("moving_average")
    assert before["versions"][0]["validation_status"] == "success"

    after = application.manage_version(
        {
            "action": "promote",
            "model": "moving_average",
            "version": "a" * 12,
        }
    )

    assert after["versions"][0]["lifecycle_status"] == "active"
    assert after["events"][0]["action"] == "promote"
