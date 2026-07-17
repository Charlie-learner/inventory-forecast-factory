"""NetworkX-backed knowledge graph for algorithms, metrics and validation experience."""

from __future__ import annotations

import json
import math
import hashlib
import re
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

    SCHEMA_VERSION = "1.5"

    def __init__(self, graph: nx.DiGraph | None = None):
        """Initialize a graph and attach the current schema version."""

        self.graph = graph or nx.DiGraph()
        self.graph.graph["schema_version"] = self.SCHEMA_VERSION

    @classmethod
    def bootstrap(cls, registry: ModelRegistry | None = None) -> "CapabilityKnowledgeGraph":
        """Build the base graph from registered algorithms and metrics."""

        registry = registry or default_registry()
        knowledge = cls()
        for demand_type in [
            "stable",
            "volatile",
            "intermittent",
            "weekly_seasonal",
            "trend",
            "dense",
        ]:
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
            for metric in ["inventory_cost", "wape", "rmse", "smape", "bias"]:
                knowledge.graph.add_edge(
                    model_node,
                    f"metric:{metric}",
                    relation="EVALUATED_BY",
                )
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
                source_title=capability.source_title,
                source_url=capability.source_url,
                source_license=capability.source_license,
                accessed_at=capability.accessed_at,
                confidence=capability.confidence,
                review_status=capability.review_status,
                evidence_refs=list(capability.evidence_refs),
                extraction_warnings=list(capability.extraction_warnings),
                implementation_kind=capability.implementation_kind,
                entrypoints=list(capability.entrypoints),
                internal_dependencies=list(capability.internal_dependencies),
                complexity=capability.complexity,
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
                source_path = self._normalized_source_ref(capability.source_ref)
                stale_sources = [
                    node
                    for node, attributes in self.graph.nodes(data=True)
                    if attributes.get("type") == "SourceArtifact"
                    and node != source_node
                    and self._normalized_source_ref(
                        str(attributes.get("source_ref", ""))
                    )
                    == source_path
                ]
                self.graph.remove_nodes_from(stale_sources)
                self.graph.add_node(
                    source_node,
                    type="SourceArtifact",
                    name=capability.source_title
                    or Path(source_path).name
                    or capability.source_ref,
                    source_type=capability.source_type,
                    source_ref=source_path,
                    source_hash=capability.source_hash,
                    extracted_by=capability.extracted_by,
                    source_url=capability.source_url,
                    source_license=capability.source_license,
                    accessed_at=capability.accessed_at,
                    review_status=capability.review_status,
                )
                self.graph.add_edge(model_node, source_node, relation="EXTRACTED_FROM")
            ingested.append(model_node)
        return ingested

    def ingest_research_evidence(self, research: dict) -> list[str]:
        """Link DOI-backed online evidence to registered algorithm nodes."""

        source_nodes = []
        recommended = research.get("analysis", {}).get("recommended_models", [])
        for record in research.get("records", []):
            identifier = str(record.get("doi") or record.get("url") or "").strip()
            if not identifier:
                continue
            source_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
            source_node = f"source:research:{source_hash[:16]}"
            self.graph.add_node(
                source_node,
                type="SourceArtifact",
                name=str(record.get("title", identifier)),
                source_type="online_research",
                source_ref=identifier,
                source_hash=source_hash,
                source_url=str(record.get("url", "")),
                source_license=str(record.get("license_url", "")),
                accessed_at=str(research.get("created_at", "")),
                extracted_by=str(
                    research.get("analysis", {}).get("analysis_mode", "deterministic")
                ),
                review_status="evidence_only",
                provider=str(research.get("provider", "")),
                relevance_score=float(record.get("relevance_score", 0.0)),
                doi=str(record.get("doi", "")),
            )
            source_nodes.append(source_node)
            for model in recommended:
                algorithm = f"algorithm:{model}"
                if self.graph.has_node(algorithm):
                    self.graph.add_edge(
                        algorithm,
                        source_node,
                        relation="SUPPORTED_BY_RESEARCH",
                    )
        return source_nodes

    @staticmethod
    def _normalized_source_ref(source_ref: str) -> str:
        """Remove a trailing Python line number from a source artifact path."""

        suffix = source_ref.rsplit(":", 1)[-1]
        return source_ref.rsplit(":", 1)[0] if suffix.isdigit() else source_ref

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
            source_title=str(attributes.get("source_title", "")),
            source_url=str(attributes.get("source_url", "")),
            source_license=str(attributes.get("source_license", "")),
            accessed_at=str(attributes.get("accessed_at", "")),
            confidence=float(attributes.get("confidence", 1.0)),
            review_status=str(attributes.get("review_status", "auto_extracted")),
            evidence_refs=tuple(attributes.get("evidence_refs", [])),
            extraction_warnings=tuple(
                attributes.get("extraction_warnings", [])
            ),
            implementation_kind=str(
                attributes.get("implementation_kind", "algorithm")
            ),
            entrypoints=tuple(attributes.get("entrypoints", [])),
            internal_dependencies=tuple(
                attributes.get("internal_dependencies", [])
            ),
            complexity=dict(attributes.get("complexity", {})),
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
            name=f"验证:{model}@{store_code}",
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
            version_attributes = self.graph.nodes[version_node]
            version_attributes["validation_status"] = status
            version_attributes["validation_count"] = int(
                version_attributes.get("validation_count", 0)
            ) + 1
            version_attributes["last_validated_at"] = recorded_at
            version_attributes["latest_metrics"] = json.dumps(
                metrics, sort_keys=True
            )
            version_attributes["latest_validation_checks"] = json.dumps(
                validation_checks or {}, sort_keys=True
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
                severity=str(failure.get("severity", "medium")),
                likely_stage=str(failure.get("likely_stage", "unknown")),
                root_cause=str(failure.get("root_cause", "")),
                recommended_actions=list(
                    failure.get("recommended_actions", [])
                ),
                occurrence_count=previous_count + 1,
                last_seen=recorded_at,
            )
            self.graph.add_edge(failure_node, model_node, relation="FAILURE_OF")
            self.graph.add_edge(run_id, failure_node, relation="OBSERVED_FAILURE")
            failure_nodes.append(failure_node)
        if repair:
            normalized_repair = " ".join(str(repair).lower().split())[:1000]
            normalized_repair = normalized_repair.replace("\\", "/")
            normalized_repair = re.sub(
                r"(?:[a-z]:)?/[\w./-]+\.py", "<path>.py", normalized_repair
            )
            normalized_repair = re.sub(
                r"\b\d+(?:\.\d+)?\b", "<n>", normalized_repair
            )
            strategy_key = hashlib.sha256(
                f"{model}|{normalized_repair}".encode("utf-8")
            ).hexdigest()[:16]
            repair_node = f"repair:{strategy_key}"
            previous_attempts = (
                int(self.graph.nodes[repair_node].get("attempt_count", 0))
                if self.graph.has_node(repair_node)
                else 0
            )
            previous_successes = (
                int(self.graph.nodes[repair_node].get("success_count", 0))
                if self.graph.has_node(repair_node)
                else 0
            )
            self.graph.add_node(
                repair_node,
                type="RepairStrategy",
                name=f"修复:{model}",
                description=repair,
                strategy_fingerprint=strategy_key,
                attempt_count=previous_attempts + 1,
                success_count=previous_successes + (1 if status == "success" else 0),
                last_used=recorded_at,
            )
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
                            "root_cause": attributes.get("root_cause", ""),
                            "recommended_actions": attributes.get(
                                "recommended_actions", []
                            ),
                            "strategy": repair.get("description", ""),
                            "strategy_fingerprint": repair.get(
                                "strategy_fingerprint", ""
                            ),
                            "attempt_count": int(
                                repair.get("attempt_count", 0)
                            ),
                            "success_count": int(
                                repair.get("success_count", 0)
                            ),
                            "success_rate": (
                                int(repair.get("success_count", 0))
                                / max(int(repair.get("attempt_count", 0)), 1)
                            ),
                            "run_id": run_node,
                            "timestamp": run.get("timestamp"),
                        }
                    )
        experiences.sort(
            key=lambda item: (
                float(item.get("success_rate", 0.0)),
                int(item.get("success_count", 0)),
                str(item.get("timestamp", "")),
            ),
            reverse=True,
        )
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
        """Compare provenance, metrics, validation, and lifecycle metadata."""

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
        def json_mapping(attributes: dict, key: str) -> dict:
            value = attributes.get(key, {})
            if isinstance(value, dict):
                return value
            try:
                parsed = json.loads(str(value))
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        left_metrics = json_mapping(left_attributes, "latest_metrics")
        right_metrics = json_mapping(right_attributes, "latest_metrics")
        metric_names = sorted(left_metrics.keys() | right_metrics.keys())
        metric_differences = {
            metric: {
                "left": left_metrics.get(metric),
                "right": right_metrics.get(metric),
                "delta": (
                    float(right_metrics[metric]) - float(left_metrics[metric])
                    if metric in left_metrics
                    and metric in right_metrics
                    and isinstance(left_metrics[metric], (int, float))
                    and isinstance(right_metrics[metric], (int, float))
                    else None
                ),
            }
            for metric in metric_names
            if left_metrics.get(metric) != right_metrics.get(metric)
        }
        return {
            "model": model,
            "left": left_node,
            "right": right_node,
            "differences": differences,
            "metric_differences": metric_differences,
            "validation": {
                "left": {
                    "status": left_attributes.get("validation_status"),
                    "checks": json_mapping(
                        left_attributes, "latest_validation_checks"
                    ),
                    "count": left_attributes.get("validation_count", 0),
                },
                "right": {
                    "status": right_attributes.get("validation_status"),
                    "checks": json_mapping(
                        right_attributes, "latest_validation_checks"
                    ),
                    "count": right_attributes.get("validation_count", 0),
                },
            },
            "lineage": {
                "left_parent": left_attributes.get("parent_version", ""),
                "right_parent": right_attributes.get("parent_version", ""),
            },
        }

    def version_events(self, model: str) -> list[dict]:
        """List auditable promote and rollback events for one model."""

        events = [
            {"id": node, **attributes}
            for node, attributes in self.graph.nodes(data=True)
            if attributes.get("type") == "VersionEvent"
            and attributes.get("model") == model
        ]
        events.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
        return events

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
        """Render a dependency-free layered SVG with filtering and node details."""

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
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
        lanes = [
            ("知识来源", ("SourceArtifact",)),
            ("算法能力", ("Algorithm",)),
            ("需求画像", ("DemandProfile",)),
            ("评价指标", ("Metric",)),
            (
                "运行与版本",
                (
                    "ValidationRun",
                    "FailureCase",
                    "RepairStrategy",
                    "CapabilityVersion",
                    "VersionEvent",
                ),
            ),
        ]
        active_lanes = [
            (title, node_types)
            for title, node_types in lanes
            if any(
                attributes.get("type") in node_types
                for _, attributes in self.graph.nodes(data=True)
            )
        ]
        lane_width = 300
        width = max(1120, 100 + lane_width * len(active_lanes))
        lane_nodes: list[tuple[str, tuple[str, ...], list[str]]] = []
        positions: dict[str, tuple[float, float]] = {}
        maximum_lane_size = 1
        for lane_index, (title, node_types) in enumerate(active_lanes):
            nodes_in_lane = sorted(
                (
                    node
                    for node, attributes in self.graph.nodes(data=True)
                    if attributes.get("type") in node_types
                ),
                key=lambda node: (
                    node_types.index(
                        str(self.graph.nodes[node].get("type", "Unknown"))
                    ),
                    str(self.graph.nodes[node].get("name", node)).casefold(),
                ),
            )
            maximum_lane_size = max(maximum_lane_size, len(nodes_in_lane))
            lane_nodes.append((title, node_types, nodes_in_lane))
            x = 95 + lane_index * lane_width
            for node_index, node in enumerate(nodes_in_lane):
                positions[node] = (x, 125 + node_index * 78)
        height = max(700, 205 + (maximum_lane_size - 1) * 78)

        relation_colors = {
            "EXTRACTED_FROM": "#0891b2",
            "SUITABLE_FOR": "#16a34a",
            "EVALUATED_BY": "#d97706",
            "VALIDATED": "#7c3aed",
            "VALIDATED_VERSION": "#db2777",
            "VERSION_OF": "#db2777",
            "OBSERVED_FAILURE": "#ea580c",
            "FAILURE_OF": "#ea580c",
            "REPAIRED_BY": "#dc2626",
            "ADDRESSES": "#dc2626",
            "ACTIVATED_VERSION": "#4f46e5",
        }

        lane_backgrounds = []
        lane_headers = []
        for lane_index, (title, _, _) in enumerate(lane_nodes):
            x = 12 + lane_index * lane_width
            lane_backgrounds.append(
                f'<rect x="{x}" y="62" width="{lane_width - 18}" '
                f'height="{height - 82}" rx="14" class="lane-bg lane-{lane_index % 2}" />'
            )
            lane_headers.append(
                f'<text x="{x + 16}" y="92" class="lane-title">{escape(title)}</text>'
            )

        edges = []
        for edge_index, (source, target, attributes) in enumerate(
            self.graph.edges(data=True)
        ):
            x1, y1 = positions[source]
            x2, y2 = positions[target]
            relation_value = str(attributes.get("relation", "RELATED_TO"))
            relation = escape(relation_value)
            stroke = relation_colors.get(relation_value, "#64748b")
            curve = 26 if edge_index % 2 else -26
            control_x = (x1 + x2) / 2
            control_y = (y1 + y2) / 2 + curve
            label_x = (x1 + 2 * control_x + x2) / 4
            label_y = (y1 + 2 * control_y + y2) / 4
            edges.append(
                f'<g class="edge-group" data-source="{escape(source)}" '
                f'data-target="{escape(target)}" data-relation="{relation}">'
                f'<title>{relation}</title>'
                f'<path d="M {x1:.1f} {y1:.1f} Q {control_x:.1f} {control_y:.1f} '
                f'{x2:.1f} {y2:.1f}" class="edge" stroke="{stroke}" '
                f'marker-end="url(#arrow)" />'
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" '
                f'class="edge-label">{relation}</text></g>'
            )

        label_occurrences: dict[str, int] = {}
        for node, attributes in self.graph.nodes(data=True):
            label = str(attributes.get("name", node))
            label_occurrences[label] = label_occurrences.get(label, 0) + 1

        nodes = []
        actual_types = set()
        for node, attributes in self.graph.nodes(data=True):
            x, y = positions[node]
            node_type = str(attributes.get("type", "Unknown"))
            actual_types.add(node_type)
            full_label = str(attributes.get("name", node))
            display_label = full_label
            if (
                node_type == "SourceArtifact"
                and label_occurrences.get(full_label, 0) > 1
            ):
                source_name = Path(
                    self._normalized_source_ref(
                        str(attributes.get("source_ref", "source"))
                    )
                ).name
                display_label = f"{source_name}: {full_label}"
            short_label = (
                f"{display_label[:27]}…"
                if len(display_label) > 28
                else display_label
            )
            details = escape(
                json.dumps(
                    {"id": node, **attributes},
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                )
            )
            search_text = escape(f"{node} {node_type} {full_label}".casefold())
            color = colors.get(node_type, "#64748b")
            nodes.append(
                f'<g class="node" data-node-id="{escape(node)}" '
                f'data-node-type="{escape(node_type)}" data-search="{search_text}" '
                f'data-details="{details}" tabindex="0">'
                f'<title>{escape(full_label)} · {escape(node_type)}</title>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="{color}" />'
                f'<text x="{x + 23:.1f}" y="{y + 5:.1f}" '
                f'class="node-label">{escape(short_label)}</text></g>'
            )

        type_order = [node_type for _, types in lanes for node_type in types]
        legend = "".join(
            f'<button type="button" class="legend-item" '
            f'data-filter-type="{escape(node_type)}">'
            f'<i style="background:{colors.get(node_type, "#64748b")}"></i>'
            f'{escape(node_type)}</button>'
            for node_type in type_order
            if node_type in actual_types
        )
        template = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inventory Capability Knowledge Graph</title>
<style>
*{box-sizing:border-box} body{font-family:Inter,ui-sans-serif,system-ui,sans-serif;margin:0;
background:#f1f5f9;color:#0f172a} header{padding:18px 28px;background:#0f172a;color:white}
h1{margin:0 0 6px;font-size:23px}.meta{color:#cbd5e1}.toolbar,.legend{display:flex;
align-items:center;gap:10px;flex-wrap:wrap;padding:10px 20px;background:white;
border-bottom:1px solid #e2e8f0}.toolbar input[type="search"]{min-width:280px;padding:8px 10px;
border:1px solid #cbd5e1;border-radius:8px}.toolbar button,.legend-item{border:1px solid #cbd5e1;
background:white;border-radius:8px;padding:7px 10px;cursor:pointer}.toolbar button:hover,
.legend-item:hover{background:#f8fafc}.legend-item{display:flex;align-items:center;gap:6px}
.toolbar label{display:flex;align-items:center;gap:6px}
.legend-item i{width:11px;height:11px;border-radius:50%}.legend-item.is-off{opacity:.38;
text-decoration:line-through}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 330px;
min-height:680px}.graph-shell{overflow:auto;background:white}.details{border-left:1px solid #e2e8f0;
background:#f8fafc;padding:18px;overflow:auto}.details h2{margin:0 0 8px;font-size:17px}
.details p{color:#64748b;font-size:13px}.details pre{white-space:pre-wrap;word-break:break-word;
font-size:12px;line-height:1.45;background:#0f172a;color:#e2e8f0;padding:12px;border-radius:9px}
svg{display:block;min-width:1100px;width:100%;height:auto;background:white;cursor:grab}
svg.is-dragging{cursor:grabbing}.lane-bg{fill:#f8fafc;stroke:#e2e8f0}.lane-1{fill:#f1f5f9}
.lane-title{font-size:13px;font-weight:700;fill:#475569}.edge{fill:none;stroke-width:1.45;
opacity:.42}.edge-group.is-connected .edge{stroke-width:2.8;opacity:1}.edge-label{display:none;
font-size:8px;fill:#475569;paint-order:stroke;stroke:white;stroke-width:3px}
body.show-relations .edge-label{display:block}.node{cursor:pointer}.node circle{stroke:white;
stroke-width:2.5;filter:drop-shadow(0 2px 2px rgb(15 23 42 / .15))}
.node:hover circle,.node.is-selected circle{stroke:#0f172a;stroke-width:4}
.node:focus{outline:none}.node:focus-visible circle{stroke:#0f172a;stroke-width:4}
.node-label{font-size:11px;fill:#0f172a;paint-order:stroke;stroke:white;stroke-width:3px;
stroke-linejoin:round}.node.is-dimmed,.edge-group.is-dimmed{opacity:.1}
@media(max-width:900px){.workspace{grid-template-columns:1fr}.details{border-left:0;
border-top:1px solid #e2e8f0}.toolbar input[type="search"]{min-width:180px;flex:1}}
</style></head><body>
<header><h1>库存算法能力知识图谱</h1>
<div class="meta">schema __SCHEMA__ · __NODE_COUNT__ nodes · __EDGE_COUNT__ edges · 分层可交互视图</div>
</header>
<div class="toolbar">
<input id="graph-search" type="search" placeholder="搜索节点名称、类型或ID">
<button type="button" id="zoom-in">放大</button><button type="button" id="zoom-out">缩小</button>
<button type="button" id="reset-view">重置</button>
<label><input id="toggle-relations" type="checkbox"> 显示关系名称</label>
</div>
<div class="legend">__LEGEND__</div>
<div class="workspace"><div class="graph-shell">
<svg id="graph" viewBox="0 0 __WIDTH__ __HEIGHT__" role="img"
aria-label="Capability knowledge graph">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="19" refY="3"
orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#64748b"/></marker></defs>
<g id="viewport">__LANES____HEADERS____EDGES____NODES__</g></svg></div>
<aside class="details" id="details-panel"><h2>节点详情</h2>
<p>点击任一节点查看完整属性；点击图例可筛选节点类型。</p>
<pre id="details-content">尚未选择节点</pre></aside></div>
<script>
const svg=document.getElementById("graph"),viewport=document.getElementById("viewport");
const nodes=[...document.querySelectorAll(".node")],edges=[...document.querySelectorAll(".edge-group")];
const disabledTypes=new Set();let scale=1,tx=0,ty=0,dragging=false,lastX=0,lastY=0;
function transform(){viewport.setAttribute("transform",`translate(${tx} ${ty}) scale(${scale})`)}
function refreshVisibility(){
  const query=document.getElementById("graph-search").value.trim().toLowerCase();
  const visible=new Set();
  nodes.forEach(node=>{
    const typeOff=disabledTypes.has(node.dataset.nodeType);
    const matched=!query||node.dataset.search.includes(query);
    node.style.display=typeOff?"none":"";
    node.classList.toggle("is-dimmed",!matched);
    if(!typeOff)visible.add(node.dataset.nodeId);
  });
  edges.forEach(edge=>{
    const shown=visible.has(edge.dataset.source)&&visible.has(edge.dataset.target);
    edge.style.display=shown?"":"none";
    const source=document.querySelector(`[data-node-id="${CSS.escape(edge.dataset.source)}"]`);
    const target=document.querySelector(`[data-node-id="${CSS.escape(edge.dataset.target)}"]`);
    edge.classList.toggle("is-dimmed",!!query&&source?.classList.contains("is-dimmed")
      &&target?.classList.contains("is-dimmed"));
  });
}
function selectNode(node){
  nodes.forEach(item=>item.classList.toggle("is-selected",item===node));
  edges.forEach(edge=>edge.classList.toggle("is-connected",
    edge.dataset.source===node.dataset.nodeId||edge.dataset.target===node.dataset.nodeId));
  document.getElementById("details-content").textContent=node.dataset.details;
}
nodes.forEach(node=>{node.addEventListener("click",()=>selectNode(node));
node.addEventListener("keydown",event=>{if(event.key==="Enter")selectNode(node)})});
document.querySelectorAll(".legend-item").forEach(button=>button.addEventListener("click",()=>{
  const type=button.dataset.filterType;
  disabledTypes.has(type)?disabledTypes.delete(type):disabledTypes.add(type);
  button.classList.toggle("is-off");refreshVisibility();
}));
document.getElementById("graph-search").addEventListener("input",refreshVisibility);
document.getElementById("toggle-relations").addEventListener("change",event=>
  document.body.classList.toggle("show-relations",event.target.checked));
document.getElementById("zoom-in").addEventListener("click",()=>{scale=Math.min(2.5,scale*1.2);transform()});
document.getElementById("zoom-out").addEventListener("click",()=>{scale=Math.max(.55,scale/1.2);transform()});
document.getElementById("reset-view").addEventListener("click",()=>{
  scale=1;tx=0;ty=0;disabledTypes.clear();transform();
  document.getElementById("graph-search").value="";
  document.querySelectorAll(".legend-item").forEach(item=>item.classList.remove("is-off"));
  nodes.forEach(item=>item.classList.remove("is-selected"));
  edges.forEach(item=>item.classList.remove("is-connected"));refreshVisibility();
});
svg.addEventListener("wheel",event=>{event.preventDefault();
  scale=Math.max(.55,Math.min(2.5,scale*(event.deltaY<0?1.1:.9)));transform()},{passive:false});
svg.addEventListener("pointerdown",event=>{if(event.target.closest(".node"))return;
  dragging=true;lastX=event.clientX;lastY=event.clientY;svg.classList.add("is-dragging");
  svg.setPointerCapture(event.pointerId)});
svg.addEventListener("pointermove",event=>{if(!dragging)return;
  const ratio=__WIDTH__/svg.getBoundingClientRect().width;
  tx+=(event.clientX-lastX)*ratio;ty+=(event.clientY-lastY)*ratio;
  lastX=event.clientX;lastY=event.clientY;transform()});
svg.addEventListener("pointerup",()=>{dragging=false;svg.classList.remove("is-dragging")});
</script></body></html>"""
        document = (
            template.replace("__SCHEMA__", escape(self.SCHEMA_VERSION))
            .replace("__NODE_COUNT__", str(self.graph.number_of_nodes()))
            .replace("__EDGE_COUNT__", str(self.graph.number_of_edges()))
            .replace("__LEGEND__", legend)
            .replace("__WIDTH__", str(width))
            .replace("__HEIGHT__", str(height))
            .replace("__LANES__", "".join(lane_backgrounds))
            .replace("__HEADERS__", "".join(lane_headers))
            .replace("__EDGES__", "".join(edges))
            .replace("__NODES__", "".join(nodes))
        )
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
