"""NetworkX-backed knowledge graph for algorithms, metrics and validation experience."""

from __future__ import annotations

import json
import math
import hashlib
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import networkx as nx
from networkx.readwrite import json_graph

from inventory_agent.forecasting.registry import ModelRegistry, default_registry
from inventory_agent.domain import CapabilitySpec


class CapabilityKnowledgeGraph:
    """Store algorithm metadata and validation experience in a directed graph."""

    SCHEMA_VERSION = "1.3"

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
            source_ref = "inventory_agent.forecasting.registry:default_registry"
            source_hash = hashlib.sha256(
                f"{name}|{metadata.description}|{metadata.suitable_for}".encode("utf-8")
            ).hexdigest()
            knowledge.graph.add_node(
                model_node,
                type="Algorithm",
                name=name,
                task_type="inventory_forecasting",
                description=metadata.description,
                template_name=name,
                min_history=metadata.min_history,
                dependencies=list(metadata.dependencies),
                input_contract="non-negative daily qty_alipay_njhs history",
                output_contract="daily forecast plus horizon-total target inventory",
                locations=["all", "1", "2", "3", "4", "5"],
                parameters={},
                source_type="registry",
                source_ref=source_ref,
                source_hash=source_hash,
                version="1.0.0",
                extracted_by="registry_bootstrap",
            )
            knowledge.graph.add_edge(model_node, "metric:inventory_cost", relation="EVALUATED_BY")
            knowledge.graph.add_edge(model_node, "metric:wape", relation="EVALUATED_BY")
            for profile in metadata.suitable_for:
                profile_node = f"profile:{profile}"
                if not knowledge.graph.has_node(profile_node):
                    knowledge.graph.add_node(profile_node, type="DemandProfile", name=profile)
                knowledge.graph.add_edge(model_node, profile_node, relation="SUITABLE_FOR")
        return knowledge

    def ingest_capabilities(self, capabilities: list[CapabilitySpec]) -> list[str]:
        """Merge extracted capability specs and their provenance into the graph."""

        ingested = []
        for capability in capabilities:
            model_node = f"algorithm:{capability.name}"
            self.graph.add_node(
                model_node,
                type="Algorithm",
                name=capability.name,
                task_type=capability.task_type,
                description=capability.description,
                template_name=capability.template_name,
                dependencies=list(capability.dependencies),
                input_contract=capability.input_contract,
                output_contract=capability.output_contract,
                parameters=capability.parameters,
                source_type=capability.source_type,
                source_ref=capability.source_ref,
                source_hash=capability.source_hash,
                version=capability.version,
                extracted_by=capability.extracted_by,
            )
            for metric in capability.metrics:
                metric_node = f"metric:{metric}"
                if not self.graph.has_node(metric_node):
                    self.graph.add_node(metric_node, type="Metric", name=metric)
                self.graph.add_edge(model_node, metric_node, relation="EVALUATED_BY")
            for profile in capability.suitable_for:
                profile_node = f"profile:{profile}"
                if not self.graph.has_node(profile_node):
                    self.graph.add_node(
                        profile_node, type="DemandProfile", name=profile
                    )
                self.graph.add_edge(model_node, profile_node, relation="SUITABLE_FOR")
            if capability.source_ref:
                source_key = capability.source_hash[:16] or hashlib.sha256(
                    capability.source_ref.encode("utf-8")
                ).hexdigest()[:16]
                source_node = f"source:{source_key}"
                source_path = capability.source_ref
                suffix = source_path.rsplit(":", 1)[-1]
                if suffix.isdigit():
                    source_path = source_path.rsplit(":", 1)[0]
                self.graph.add_node(
                    source_node,
                    type="SourceArtifact",
                    name=Path(source_path).name or capability.source_ref,
                    source_type=capability.source_type,
                    source_ref=capability.source_ref,
                    source_hash=capability.source_hash,
                    extracted_by=capability.extracted_by,
                )
                self.graph.add_edge(model_node, source_node, relation="EXTRACTED_FROM")
            ingested.append(model_node)
        return ingested

    def capability_spec(self, name: str) -> CapabilitySpec:
        """Reconstruct a generation-ready specification from graph knowledge."""

        node = f"algorithm:{name}"
        if not self.graph.has_node(node):
            raise KeyError(f"Capability not found in knowledge graph: {name}")
        attributes = self.graph.nodes[node]
        suitable_for = []
        metrics = []
        for _, target, edge in self.graph.out_edges(node, data=True):
            relation = edge.get("relation")
            if relation == "SUITABLE_FOR":
                suitable_for.append(str(self.graph.nodes[target].get("name", target)))
            elif relation == "EVALUATED_BY":
                metrics.append(str(self.graph.nodes[target].get("name", target)))
        parameters = attributes.get("parameters", {})
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {}
        dependencies = attributes.get("dependencies", [])
        if isinstance(dependencies, str):
            try:
                dependencies = json.loads(dependencies)
            except json.JSONDecodeError:
                dependencies = [dependencies] if dependencies else []
        return CapabilitySpec(
            name=name,
            task_type=str(attributes.get("task_type", "inventory_forecasting")),
            description=str(attributes.get("description", f"Forecast capability {name}")),
            template_name=str(attributes.get("template_name", name)),
            input_contract=str(
                attributes.get("input_contract", "non-negative daily demand history")
            ),
            output_contract=str(
                attributes.get(
                    "output_contract",
                    "non-negative daily forecast and horizon-total target inventory",
                )
            ),
            suitable_for=tuple(sorted(suitable_for)),
            metrics=tuple(sorted(metrics)) or ("inventory_cost", "wape"),
            dependencies=tuple(dependencies),
            parameters=dict(parameters) if isinstance(parameters, dict) else {},
            source_type=str(attributes.get("source_type", "knowledge_graph")),
            source_ref=str(attributes.get("source_ref", "")),
            source_hash=str(attributes.get("source_hash", "")),
            version=str(attributes.get("version", "1.0.0")),
            extracted_by=str(attributes.get("extracted_by", "knowledge_graph")),
        )

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
        validation_checks: dict[str, bool] | None = None,
        capability_version: dict | None = None,
        failure_history: list[dict] | None = None,
    ) -> str:
        """Record one model validation and any repair strategy used."""

        run_id = f"run:{uuid4().hex[:12]}"
        recorded_at = datetime.now(timezone.utc).isoformat()
        self.graph.add_node(
            run_id,
            type="ValidationRun",
            item_id=int(item_id),
            store_code=str(store_code),
            status=status,
            metrics=json.dumps(metrics, sort_keys=True),
            validation_checks=json.dumps(validation_checks or {}, sort_keys=True),
            timestamp=recorded_at,
        )
        model_node = f"algorithm:{model}"
        if not self.graph.has_node(model_node):
            self.graph.add_node(model_node, type="Algorithm", name=model)
        self.graph.add_edge(run_id, model_node, relation="VALIDATED")
        if capability_version:
            source_hash = str(capability_version.get("source_hash", ""))
            version_key = source_hash[:12] or uuid4().hex[:12]
            version_node = f"version:{model}:{version_key}"
            lifecycle_status = (
                self.graph.nodes[version_node].get("lifecycle_status", "candidate")
                if self.graph.has_node(version_node)
                else ("candidate" if status == "success" else "rejected")
            )
            version_created_at = (
                self.graph.nodes[version_node].get("created_at", recorded_at)
                if self.graph.has_node(version_node)
                else recorded_at
            )
            self.graph.add_node(
                version_node,
                type="CapabilityVersion",
                name=f"{model}@{version_key}",
                created_at=version_created_at,
                lifecycle_status=lifecycle_status,
                **capability_version,
            )
            self.graph.add_edge(version_node, model_node, relation="VERSION_OF")
            self.graph.add_edge(run_id, version_node, relation="VALIDATED_VERSION")
        failure_nodes = []
        for failure in failure_history or []:
            fingerprint = str(failure.get("fingerprint", "unknown"))
            category = str(failure.get("category", "unknown"))
            failure_node = f"failure:{fingerprint}"
            previous_count = int(
                self.graph.nodes[failure_node].get("occurrence_count", 0)
            ) if self.graph.has_node(failure_node) else 0
            self.graph.add_node(
                failure_node,
                type="FailureCase",
                name=f"{category}:{fingerprint}",
                category=category,
                fingerprint=fingerprint,
                normalized_error=str(failure.get("normalized_error", "")),
                retryable=bool(failure.get("retryable", True)),
                occurrence_count=previous_count + 1,
                last_seen=recorded_at,
            )
            self.graph.add_edge(failure_node, model_node, relation="FAILURE_OF")
            self.graph.add_edge(run_id, failure_node, relation="OBSERVED_FAILURE")
            failure_nodes.append(failure_node)
        if repair:
            repair_node = f"repair:{uuid4().hex[:10]}"
            self.graph.add_node(repair_node, type="RepairStrategy", description=repair)
            self.graph.add_edge(run_id, repair_node, relation="REPAIRED_BY")
            for failure_node in failure_nodes:
                self.graph.add_edge(repair_node, failure_node, relation="ADDRESSES")
        return run_id

    def repair_experience(
        self, model: str, category: str, limit: int = 3
    ) -> list[dict]:
        """Retrieve repair strategies from successful runs with the same failure category."""

        if limit <= 0:
            return []
        model_node = f"algorithm:{model}"
        experiences = []
        for failure_node, attributes in self.graph.nodes(data=True):
            if (
                attributes.get("type") != "FailureCase"
                or attributes.get("category") != category
                or not self.graph.has_edge(failure_node, model_node)
            ):
                continue
            for run_node in self.graph.predecessors(failure_node):
                run = self.graph.nodes[run_node]
                if run.get("type") != "ValidationRun" or run.get("status") != "success":
                    continue
                for repair_node in self.graph.successors(run_node):
                    repair = self.graph.nodes[repair_node]
                    if repair.get("type") != "RepairStrategy":
                        continue
                    experiences.append(
                        {
                            "category": category,
                            "fingerprint": attributes.get("fingerprint"),
                            "strategy": repair.get("description", ""),
                            "run_id": run_node,
                            "timestamp": run.get("timestamp"),
                        }
                    )
        experiences.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
        return experiences[:limit]

    def capability_versions(self, model: str) -> list[dict]:
        """List generated versions with lifecycle and validation evidence."""

        model_node = f"algorithm:{model}"
        versions = []
        for node, attributes in self.graph.nodes(data=True):
            if (
                attributes.get("type") != "CapabilityVersion"
                or not self.graph.has_edge(node, model_node)
            ):
                continue
            validation_runs = [
                predecessor
                for predecessor in self.graph.predecessors(node)
                if self.graph.nodes[predecessor].get("type") == "ValidationRun"
            ]
            versions.append(
                {
                    "id": node,
                    **attributes,
                    "validation_runs": validation_runs,
                    "validated": any(
                        self.graph.nodes[run].get("status") == "success"
                        for run in validation_runs
                    ),
                }
            )
        versions.sort(
            key=lambda item: (str(item.get("created_at", "")), item["id"]),
            reverse=True,
        )
        return versions

    def compare_versions(self, model: str, left: str, right: str) -> dict:
        """Compare provenance, generation, and lifecycle metadata for two versions."""

        left_node = self._resolve_version_node(model, left)
        right_node = self._resolve_version_node(model, right)
        left_attributes = dict(self.graph.nodes[left_node])
        right_attributes = dict(self.graph.nodes[right_node])
        ignored = {"name", "type"}
        keys = sorted((left_attributes.keys() | right_attributes.keys()) - ignored)
        differences = {
            key: {
                "left": left_attributes.get(key),
                "right": right_attributes.get(key),
            }
            for key in keys
            if left_attributes.get(key) != right_attributes.get(key)
        }
        return {
            "model": model,
            "left": left_node,
            "right": right_node,
            "differences": differences,
        }

    def promote_version(self, model: str, selector: str) -> str:
        """Mark one successfully validated version active and supersede the prior active one."""

        return self._activate_version(model, selector, action="promote")

    def rollback_version(self, model: str, selector: str) -> str:
        """Restore a previously validated version as the active implementation."""

        return self._activate_version(model, selector, action="rollback")

    def _activate_version(self, model: str, selector: str, action: str) -> str:
        selected = self._resolve_version_node(model, selector)
        versions = self.capability_versions(model)
        selected_record = next(item for item in versions if item["id"] == selected)
        if not selected_record["validated"]:
            raise ValueError(f"Cannot activate unvalidated capability version: {selected}")
        previous_active = None
        for version in versions:
            node = version["id"]
            if self.graph.nodes[node].get("lifecycle_status") == "active":
                previous_active = node
                self.graph.nodes[node]["lifecycle_status"] = "superseded"
        self.graph.nodes[selected]["lifecycle_status"] = "active"
        event_node = f"version_event:{uuid4().hex[:12]}"
        self.graph.add_node(
            event_node,
            type="VersionEvent",
            name=f"{action}:{model}",
            action=action,
            model=model,
            previous_active=previous_active or "",
            selected_version=selected,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.graph.add_edge(event_node, selected, relation="ACTIVATED_VERSION")
        return event_node

    def _resolve_version_node(self, model: str, selector: str) -> str:
        matches = []
        for version in self.capability_versions(model):
            source_hash = str(version.get("source_hash", ""))
            if (
                version["id"] == selector
                or version["id"].endswith(f":{selector}")
                or source_hash.startswith(selector)
            ):
                matches.append(version["id"])
        if len(matches) != 1:
            raise ValueError(
                f"Expected one version of {model!r} matching {selector!r}; "
                f"found {len(matches)}"
            )
        return matches[0]

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
            "SourceArtifact": "#0891b2",
            "CapabilityVersion": "#db2777",
            "FailureCase": "#ea580c",
            "VersionEvent": "#4f46e5",
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
