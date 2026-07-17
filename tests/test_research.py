import json
from pathlib import Path

from inventory_agent.agents.planner import PlanningAgent
from inventory_agent.agents.research import IndustryResearchAgent
from inventory_agent.domain import CapabilityRequest
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.research.crossref import CrossrefResearchProvider


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _Provider:
    def search(self, query: str, limit: int = 5):
        assert "seasonal demand" in query
        assert limit == 3
        return [
            {
                "title": "Seasonal demand forecasting and inventory control",
                "doi": "10.1000/seasonal-demo",
                "url": "https://doi.org/10.1000/seasonal-demo",
                "abstract_excerpt": "A seasonal naive benchmark for inventory demand.",
                "authors": ["A Researcher"],
                "year": 2024,
                "venue": "Forecasting Journal",
                "citation_count": 25,
                "license_url": "",
                "provider": "crossref",
            }
        ]


def test_crossref_provider_normalizes_doi_metadata():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _Response(
            {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/demo",
                            "title": ["Inventory <b>forecasting</b>"],
                            "abstract": "<jats:p>Demand evidence</jats:p>",
                            "URL": "https://doi.org/10.1000/demo",
                            "published": {"date-parts": [[2024, 1, 1]]},
                            "author": [{"given": "Ada", "family": "Lovelace"}],
                            "container-title": ["Demo Journal"],
                            "is-referenced-by-count": 7,
                            "type": "journal-article",
                        }
                    ]
                }
            }
        )

    records = CrossrefResearchProvider(opener=opener).search(
        "inventory forecasting", limit=1
    )

    assert "query.bibliographic=inventory+forecasting" in captured["url"]
    assert captured["timeout"] == 15.0
    assert records[0]["title"] == "Inventory forecasting"
    assert records[0]["abstract_excerpt"] == "Demand evidence"
    assert records[0]["authors"] == ["Ada Lovelace"]


def test_research_agent_writes_evidence_and_influences_planning(tmp_path: Path):
    output = tmp_path / "online_knowledge_extraction.json"
    result = IndustryResearchAgent(provider=_Provider()).research(
        "预测周季节性商品库存",
        {"demand_type": "weekly_seasonal"},
        output,
        limit=3,
    )

    assert result["status"] == "success"
    assert result["analysis"]["recommended_models"][0] == "seasonal_naive"
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["records"][0]["doi"]

    graph = CapabilityKnowledgeGraph.bootstrap()
    nodes = graph.ingest_research_evidence(result)
    assert len(nodes) == 1
    assert graph.graph.has_edge("algorithm:seasonal_naive", nodes[0])

    request = CapabilityRequest("weekly inventory", 1, "1")
    plan = PlanningAgent().plan(
        request,
        {"demand_type": "weekly_seasonal", "zero_ratio": 0.0},
        graph,
        available_models={"last_value", "moving_average", "seasonal_naive"},
        research_evidence=result,
    )
    assert plan.candidates[0] == "seasonal_naive"
    assert plan.design_basis["online_research"]["record_count"] == 1


def test_research_agent_degrades_without_breaking_artifact(tmp_path: Path):
    class FailingProvider:
        def search(self, query: str, limit: int = 5):
            raise TimeoutError("offline")

    output = tmp_path / "research.json"
    result = IndustryResearchAgent(provider=FailingProvider()).research(
        "inventory", {"demand_type": "stable"}, output
    )

    assert result["status"] == "degraded"
    assert result["records"] == []
    assert "TimeoutError" in result["warnings"][0]
    assert output.exists()
