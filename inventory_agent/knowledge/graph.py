"""NetworkX-backed knowledge graph for algorithms, metrics and validation experience."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import networkx as nx
from networkx.readwrite import json_graph

from inventory_agent.forecasting.registry import ModelRegistry, default_registry


class CapabilityKnowledgeGraph:
    SCHEMA_VERSION = "1.0"

    def __init__(self, graph: nx.DiGraph | None = None):
        self.graph = graph or nx.DiGraph()
        self.graph.graph["schema_version"] = self.SCHEMA_VERSION

    @classmethod
    def bootstrap(cls, registry: ModelRegistry | None = None) -> "CapabilityKnowledgeGraph":
        registry = registry or default_registry()
        knowledge = cls()
        for demand_type in ["stable", "volatile", "intermittent", "weekly_seasonal", "dense"]:
            knowledge.graph.add_node(f"profile:{demand_type}", type="DemandProfile", name=demand_type)
        for metric in ["inventory_cost", "wape", "smape", "bias", "rmse"]:
            knowledge.graph.add_node(f"metric:{metric}", type="Metric", name=metric)

        for name in registry.names():
            metadata = registry.metadata(name)
            model_node = f"algorithm:{name}"
            knowledge.graph.add_node(
                model_node,
                type="Algorithm",
                name=name,
                description=metadata.description,
                min_history=metadata.min_history,
                dependencies=list(metadata.dependencies),
            )
            knowledge.graph.add_edge(model_node, "metric:inventory_cost", relation="EVALUATED_BY")
            knowledge.graph.add_edge(model_node, "metric:wape", relation="EVALUATED_BY")
            for profile in metadata.suitable_for:
                profile_node = f"profile:{profile}"
                if not knowledge.graph.has_node(profile_node):
                    knowledge.graph.add_node(profile_node, type="DemandProfile", name=profile)
                knowledge.graph.add_edge(model_node, profile_node, relation="SUITABLE_FOR")
        return knowledge

    def retrieve_algorithms(self, demand_type: str, limit: int = 3) -> list[dict]:
        profile_node = f"profile:{demand_type}"
        exact: list[dict] = []
        fallback: list[dict] = []
        for node, attributes in self.graph.nodes(data=True):
            if attributes.get("type") != "Algorithm":
                continue
            record = {"id": node, **attributes}
            if self.graph.has_edge(node, profile_node):
                exact.append(record)
            else:
                fallback.append(record)
        ordered = sorted(exact, key=lambda item: item["name"]) + sorted(
            fallback, key=lambda item: item["name"]
        )
        return ordered[:limit]

    def record_validation(
        self,
        item_id: int,
        store_code: str,
        model: str,
        metrics: dict[str, float],
        status: str = "success",
        repair: str | None = None,
    ) -> str:
        run_id = f"run:{uuid4().hex[:12]}"
        self.graph.add_node(
            run_id,
            type="ValidationRun",
            item_id=int(item_id),
            store_code=str(store_code),
            status=status,
            metrics=json.dumps(metrics, sort_keys=True),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        model_node = f"algorithm:{model}"
        if not self.graph.has_node(model_node):
            self.graph.add_node(model_node, type="Algorithm", name=model)
        self.graph.add_edge(run_id, model_node, relation="VALIDATED")
        if repair:
            repair_node = f"repair:{uuid4().hex[:10]}"
            self.graph.add_node(repair_node, type="RepairStrategy", description=repair)
            self.graph.add_edge(run_id, repair_node, relation="REPAIRED_BY")
        return run_id

    def save(self, json_path: str | Path, graphml_path: str | Path | None = None) -> None:
        json_output = Path(json_path)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        payload = json_graph.node_link_data(self.graph, edges="edges")
        json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if graphml_path:
            graphml_output = Path(graphml_path)
            graphml_output.parent.mkdir(parents=True, exist_ok=True)
            serializable = nx.DiGraph()
            serializable.graph.update(self.graph.graph)
            for node, attrs in self.graph.nodes(data=True):
                serializable.add_node(
                    node,
                    **{key: json.dumps(value) if isinstance(value, (list, dict)) else value for key, value in attrs.items()},
                )
            serializable.add_edges_from(self.graph.edges(data=True))
            nx.write_graphml(serializable, graphml_output)

    @classmethod
    def load(cls, path: str | Path) -> "CapabilityKnowledgeGraph":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(json_graph.node_link_graph(payload, edges="edges", directed=True))

