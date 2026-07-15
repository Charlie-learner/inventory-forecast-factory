"""NetworkX-backed knowledge graph for algorithms, metrics and validation experience."""

from __future__ import annotations

import json
import math
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import networkx as nx
from networkx.readwrite import json_graph

from inventory_agent.forecasting.registry import ModelRegistry, default_registry


class CapabilityKnowledgeGraph:
    """Store algorithm metadata and validation experience in a directed graph."""

    SCHEMA_VERSION = "1.1"

    def __init__(self, graph: nx.DiGraph | None = None):
        """Initialize a graph and attach the current schema version."""

        self.graph = graph or nx.DiGraph()
        self.graph.graph["schema_version"] = self.SCHEMA_VERSION

    @classmethod
    def bootstrap(cls, registry: ModelRegistry | None = None) -> "CapabilityKnowledgeGraph":
        """Build the base graph from registered algorithms and metrics."""

        registry = registry or default_registry()
        knowledge = cls()
        for demand_type in ["stable", "volatile", "intermittent", "weekly_seasonal", "dense"]:
            knowledge.graph.add_node(f"profile:{demand_type}", type="DemandProfile", name=demand_type)
        for metric in ["inventory_cost", "wape", "smape", "bias", "rmse"]:
            attributes = {"type": "Metric", "name": metric}
            if metric == "inventory_cost":
                attributes.update(
                    {
                        "evaluation_unit": "horizon_total",
                        "formula": "A*max(D-T,0) + B*max(T-D,0)",
                        "scenario": "inventory_forecasting",
                        "cost_a": "understock",
                        "cost_b": "overstock",
                    }
                )
            knowledge.graph.add_node(f"metric:{metric}", **attributes)

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
                input_contract="non-negative daily qty_alipay_njhs history",
                output_contract="daily forecast plus horizon-total target inventory",
                locations=["all", "1", "2", "3", "4", "5"],
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
        """Rank suitable algorithms with reusable historical validation evidence."""

        profile_node = f"profile:{demand_type}"
        exact: list[dict] = []
        fallback: list[dict] = []
        for node, attributes in self.graph.nodes(data=True):
            if attributes.get("type") != "Algorithm":
                continue
            history = []
            successes = 0
            for run_node in self.graph.predecessors(node):
                run = self.graph.nodes[run_node]
                if run.get("type") != "ValidationRun":
                    continue
                if run.get("status") == "success":
                    successes += 1
                try:
                    metrics = json.loads(str(run.get("metrics", "{}")))
                    value = float(metrics["inventory_cost"])
                    if math.isfinite(value):
                        history.append(value)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    pass
            validation_count = sum(
                1
                for run_node in self.graph.predecessors(node)
                if self.graph.nodes[run_node].get("type") == "ValidationRun"
            )
            record = {
                "id": node,
                **attributes,
                "validation_count": validation_count,
                "success_rate": successes / validation_count if validation_count else None,
                "mean_inventory_cost": sum(history) / len(history) if history else None,
            }
            if self.graph.has_edge(node, profile_node):
                exact.append(record)
            else:
                fallback.append(record)
        def history_key(item: dict) -> tuple:
            mean_cost = item["mean_inventory_cost"]
            success_rate = item["success_rate"]
            return (
                0 if item["validation_count"] else 1,
                mean_cost if mean_cost is not None else math.inf,
                -(success_rate if success_rate is not None else 0.0),
                item["name"],
            )

        ordered = sorted(exact, key=history_key) + sorted(fallback, key=history_key)
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
        """Record one model validation and any repair strategy used."""

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

    def render_html(self, path: str | Path) -> Path:
        """Render a dependency-free interactive-readable SVG overview as HTML."""

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        width, height = 1200, 760
        positions = nx.spring_layout(self.graph, seed=42) if self.graph.nodes else {}
        colors = {
            "Algorithm": "#2563eb",
            "DemandProfile": "#16a34a",
            "Metric": "#f59e0b",
            "ValidationRun": "#7c3aed",
            "RepairStrategy": "#dc2626",
        }

        def point(node: str) -> tuple[float, float]:
            x, y = positions[node]
            return 70 + (float(x) + 1) * (width - 140) / 2, 70 + (float(y) + 1) * (height - 140) / 2

        edges = []
        for source, target, attributes in self.graph.edges(data=True):
            x1, y1 = point(source)
            x2, y2 = point(target)
            relation = escape(str(attributes.get("relation", "")))
            edges.append(
                f'<g><title>{relation}</title><line x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" class="edge" '
                'marker-end="url(#arrow)" /></g>'
            )

        nodes = []
        for node, attributes in self.graph.nodes(data=True):
            x, y = point(node)
            node_type = str(attributes.get("type", "Unknown"))
            label = escape(str(attributes.get("name", node)))
            details = escape(json.dumps(attributes, ensure_ascii=False, default=str))
            color = colors.get(node_type, "#64748b")
            nodes.append(
                f'<g><title>{details}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="14" fill="{color}" />'
                f'<text x="{x + 18:.1f}" y="{y + 4:.1f}" class="label">{label}</text></g>'
            )

        legend = "".join(
            f'<span><i style="background:{color}"></i>{escape(node_type)}</span>'
            for node_type, color in colors.items()
        )
        document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Inventory Capability Knowledge Graph</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
header{{padding:18px 28px;background:#0f172a;color:white}} h1{{margin:0 0 6px;font-size:22px}}
.meta{{color:#cbd5e1}} .legend{{display:flex;gap:18px;flex-wrap:wrap;padding:14px 28px;background:white}}
.legend span{{display:flex;align-items:center;gap:6px}} .legend i{{width:11px;height:11px;border-radius:50%}}
svg{{display:block;width:100%;height:auto;background:white;border-top:1px solid #e2e8f0}}
.edge{{stroke:#94a3b8;stroke-width:1.2}} .label{{font-size:11px;fill:#0f172a}}
</style></head><body><header><h1>库存算法能力知识图谱</h1>
<div class="meta">schema {escape(self.SCHEMA_VERSION)} · {self.graph.number_of_nodes()} nodes · {self.graph.number_of_edges()} edges</div></header>
<div class="legend">{legend}</div><svg viewBox="0 0 {width} {height}" role="img" aria-label="Capability knowledge graph">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="19" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#94a3b8"/></marker></defs>
{''.join(edges)}{''.join(nodes)}</svg></body></html>"""
        output.write_text(document, encoding="utf-8")
        return output

    def save(
        self,
        json_path: str | Path,
        graphml_path: str | Path | None = None,
        html_path: str | Path | None = None,
    ) -> None:
        """Persist the graph as JSON and optionally GraphML and HTML."""

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
        if html_path:
            self.render_html(html_path)

    @classmethod
    def load(cls, path: str | Path) -> "CapabilityKnowledgeGraph":
        """Load a previously persisted JSON knowledge graph."""

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(json_graph.node_link_graph(payload, edges="edges", directed=True))
