"""Application services exposed by the local Web interface."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import create_cainiao_loader, load_location_frame
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.llm.client import create_llm
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.validation.metrics import default_metric_registry
from inventory_agent.validation.profiles import default_validation_profiles
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


class WebRequestError(ValueError):
    """Represent a user-facing Web request failure."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class WebApplication:
    """Bridge JSON Web requests to the existing capability-factory services."""

    def __init__(
        self,
        workspace: str | Path = ".",
        settings: Settings | None = None,
        output_root: str | Path = "artifacts/runs",
        knowledge_path: str | Path = "artifacts/knowledge/capability_graph.json",
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.settings = settings or Settings.from_env()
        self.output_root = self._path(output_root)
        self.knowledge_path = self._path(knowledge_path)
        self._run_lock = threading.Lock()

    def _path(self, value: str | Path, *, must_exist: bool = False) -> Path:
        """Resolve one path and keep Web operations inside the project workspace."""

        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise WebRequestError(f"路径必须位于项目目录内：{value}")
        if must_exist and not resolved.exists():
            raise WebRequestError(f"路径不存在：{value}")
        return resolved

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return [item.strip() for item in value if item.strip()]
        raise WebRequestError("列表字段必须是字符串数组或按行分隔的文本。")

    def _plugin_specs(self, value: Any) -> list[str]:
        specs = self._string_list(value)
        for spec in specs:
            reference = spec.rpartition(":")[0] or spec
            if reference.lower().endswith(".py"):
                self._path(reference, must_exist=True)
        return specs

    def overview(self) -> dict[str, Any]:
        """Return dashboard data without exposing API credentials."""

        metrics = default_metric_registry()
        profiles = default_validation_profiles()
        registry = default_registry()
        runs = self.list_runs(limit=8)
        graph_path = self._available_graph_path()
        graph = (
            CapabilityKnowledgeGraph.load(graph_path)
            if graph_path and graph_path.suffix.lower() == ".json"
            else CapabilityKnowledgeGraph.bootstrap(registry)
        )
        node_types: dict[str, int] = {}
        for _, attributes in graph.graph.nodes(data=True):
            node_type = str(attributes.get("type", "Unknown"))
            node_types[node_type] = node_types.get(node_type, 0) + 1
        return {
            "project": {
                "name": "库存算法能力工厂",
                "subtitle": "AI Agent · 能力抽取—复刻—验证—沉淀",
                "llm_mode": self.settings.llm_mode,
                "model": self.settings.model,
                "configuration_issues": self.settings.validate(),
            },
            "counts": {
                "algorithms": len(registry.names()),
                "metrics": len(metrics.names()),
                "validation_profiles": len(profiles.names()),
                "runs": len(self.list_runs(limit=None)),
                "graph_nodes": graph.graph.number_of_nodes(),
                "graph_edges": graph.graph.number_of_edges(),
            },
            "algorithms": [
                asdict(registry.metadata(name)) for name in registry.names()
            ],
            "metrics": metrics.names(),
            "validation_profiles": [
                asdict(profiles.get(name)) for name in profiles.names()
            ],
            "graph_node_types": node_types,
            "recent_runs": runs,
        }

    def list_runs(self, limit: int | None = 20) -> list[dict[str, Any]]:
        """List timestamped workflow runs with concise evidence summaries."""

        if not self.output_root.exists():
            return []
        run_dirs = sorted(
            (
                path
                for path in self.output_root.iterdir()
                if path.is_dir()
                and (
                    (path / "run_manifest.json").exists()
                    or (path / "validation_report.json").exists()
                )
            ),
            key=lambda path: path.name,
            reverse=True,
        )
        if limit is not None:
            run_dirs = run_dirs[:limit]
        results = []
        for run_dir in run_dirs:
            manifest = self._read_json(run_dir / "run_manifest.json")
            report = self._read_json(run_dir / "validation_report.json")
            request = report.get("request", {})
            benchmark = report.get("benchmark", {})
            results.append(
                {
                    "id": run_dir.name,
                    "status": manifest.get("status", "unknown"),
                    "started_at": manifest.get("started_at"),
                    "finished_at": manifest.get("finished_at"),
                    "event_count": manifest.get("event_count", 0),
                    "description": request.get("description", ""),
                    "task_type": request.get("task_type", ""),
                    "item_id": request.get("item_id"),
                    "store_code": request.get("store_code"),
                    "selected_model": benchmark.get("selected_model"),
                    "target_inventory": benchmark.get("target_inventory"),
                    "repairs": len(report.get("repairs", [])),
                    "candidate_count": len(benchmark.get("candidates", [])),
                }
            )
        return results

    def run_detail(self, run_id: str) -> dict[str, Any]:
        """Return report, manifest, and structured trace events for one run."""

        if Path(run_id).name != run_id:
            raise WebRequestError("非法运行 ID。")
        run_dir = self._path(self.output_root / run_id, must_exist=True)
        report = self._read_json(run_dir / "validation_report.json")
        manifest = self._read_json(run_dir / "run_manifest.json")
        events = []
        trace_path = run_dir / "detailed_trace.jsonl"
        if trace_path.exists():
            for line in trace_path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if not report and not manifest:
            raise WebRequestError("运行产物不完整或无法读取。", 404)
        return {
            "id": run_id,
            "manifest": manifest,
            "report": report,
            "events": events,
        }

    def run_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the complete Agent workflow from a Web form."""

        description = str(payload.get("description", "")).strip()
        if not description:
            raise WebRequestError("请输入自然语言任务描述。")
        data_path = self._path(
            str(payload.get("data_path", "examples/data/cainiao_demo.csv")),
            must_exist=True,
        )
        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("capability_sources"))
        ]
        plugins = self._plugin_specs(payload.get("plugins"))
        trace_level = str(payload.get("trace_level", "full"))
        task_type = str(payload.get("task_type", "")).strip() or None
        keep_runs = int(payload.get("keep_runs", 10))
        with self._run_lock:
            workflow = InventoryCapabilityWorkflow(
                settings=self.settings,
                knowledge_path=self.knowledge_path,
                plugin_specs=plugins,
            )
            result = workflow.run(
                description,
                data_path,
                self.output_root,
                capability_sources=sources,
                trace_level=trace_level,
                keep_runs=keep_runs,
                task_type_override=task_type,
            )
        report_path = Path(result["report_paths"]["json"])
        if not report_path.is_absolute():
            report_path = self.workspace / report_path
        run_id = report_path.parent.name
        return {
            "run_id": run_id,
            "selected_model": result["selected_model"],
            "target_inventory": result["benchmark"]["target_inventory"],
            "forecast_total": result["benchmark"]["forecast_total"],
            "candidate_count": len(result["benchmark"]["candidates"]),
            "candidate_code_solutions": len(
                result.get("candidate_code_solutions", [])
            ),
            "repairs": len(result.get("repairs", [])),
            "code_validation": asdict(result["code_validation"]),
            "detail": self.run_detail(run_id),
        }

    def benchmark(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run task-configured candidate comparison without the full workflow."""

        source = self._path(
            str(payload.get("data_path", "examples/data/cainiao_demo.csv")),
            must_exist=True,
        )
        item_id = int(payload.get("item_id"))
        store_code = str(payload.get("store_code", "")).strip()
        if not store_code:
            raise WebRequestError("请输入仓库编码。")
        model_names = self._string_list(payload.get("models")) or None
        plugins = self._plugin_specs(payload.get("plugins"))
        metrics = default_metric_registry()
        profiles = default_validation_profiles()
        loaded = load_plugins(plugins, metrics, profiles)
        task_type = str(payload.get("task_type", "inventory_target"))
        is_raw_source = source.is_dir() or source.suffix.lower() == ".zip"
        if is_raw_source:
            frame = load_location_frame(source, store_code)
            costs = resolve_inventory_costs(
                create_cainiao_loader(source).load_costs(),
                item_id,
                store_code,
            )
        else:
            frame = pd.read_csv(source, parse_dates=["date"])
            costs = UNIT_COSTS
        result = benchmark_series(
            frame,
            item_id=item_id,
            store_code=store_code,
            model_names=model_names,
            horizon=int(payload.get("horizon", 14)),
            folds=(
                int(payload["folds"])
                if payload.get("folds") not in (None, "")
                else None
            ),
            costs=costs,
            allow_missing=is_raw_source,
            validation_profile=profiles.get(task_type),
            metric_registry=metrics,
        )
        result["plugins"] = plugin_manifest(loaded)
        return result

    def extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract capabilities from local documents or code and update knowledge."""

        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("sources"))
        ]
        if not sources:
            raise WebRequestError("请至少提供一个能力来源。")
        output = self._path(
            str(
                payload.get(
                    "output",
                    "artifacts/web/extraction/extracted_capabilities.json",
                )
            )
        )
        agent = CapabilityExtractionAgent(create_llm(self.settings))
        capabilities = agent.extract_sources(sources)
        result_path = agent.write_result(capabilities, output, agent.scan_reports)
        knowledge_paths = None
        if bool(payload.get("update_knowledge", True)):
            knowledge = (
                CapabilityKnowledgeGraph.load(self.knowledge_path)
                if self.knowledge_path.exists()
                else CapabilityKnowledgeGraph.bootstrap()
            )
            knowledge.ingest_capabilities(capabilities)
            knowledge.save(
                self.knowledge_path,
                self.knowledge_path.with_suffix(".graphml"),
                self.knowledge_path.with_suffix(".html"),
            )
            knowledge_paths = {
                "json": str(self.knowledge_path),
                "graphml": str(self.knowledge_path.with_suffix(".graphml")),
                "html": str(self.knowledge_path.with_suffix(".html")),
            }
        return {
            "count": len(capabilities),
            "capabilities": [asdict(capability) for capability in capabilities],
            "scan_reports": agent.scan_reports,
            "result_path": str(result_path),
            "knowledge_graph": knowledge_paths,
        }

    def replicate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Replicate and validate one extracted capability."""

        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("sources"))
        ]
        if not sources:
            raise WebRequestError("请至少提供一个能力来源。")
        agent = CapabilityExtractionAgent(create_llm(self.settings))
        capabilities = agent.extract_sources(sources)
        capability_name = str(payload.get("capability", "")).strip()
        if capability_name:
            matches = [
                capability
                for capability in capabilities
                if capability.name == capability_name
            ]
            if len(matches) != 1:
                raise WebRequestError(
                    f"未找到唯一能力 {capability_name!r}，匹配数量为 {len(matches)}。"
                )
            spec = matches[0]
        elif len(capabilities) == 1:
            spec = capabilities[0]
        else:
            raise WebRequestError("来源包含多个能力，请填写要复刻的能力名称。")
        output_dir = self._path(
            str(payload.get("output_dir", "artifacts/web/replication/generated"))
        )
        manifest = self._path(
            str(
                payload.get(
                    "manifest",
                    "artifacts/web/replication/review_manifest.json",
                )
            )
        )
        result = CapabilityReplicator().replicate(
            spec,
            output_dir,
            manifest,
            llm=create_llm(self.settings),
            reference_model=(
                str(payload.get("reference_model", "")).strip() or None
            ),
            approved=bool(payload.get("approved", False)),
        )
        return result

    def versions(self, model: str) -> dict[str, Any]:
        """Return capability versions and lifecycle events for one model."""

        if not model.strip():
            raise WebRequestError("请提供模型名称。")
        if not self.knowledge_path.exists():
            return {"model": model, "versions": [], "events": []}
        knowledge = CapabilityKnowledgeGraph.load(self.knowledge_path)
        return {
            "model": model,
            "versions": knowledge.capability_versions(model),
            "events": knowledge.version_events(model),
        }

    def manage_version(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compare, promote, or roll back validated capability versions."""

        if not self.knowledge_path.exists():
            raise WebRequestError("运行知识图谱尚不存在，请先执行一次完整工作流。")
        model = str(payload.get("model", "")).strip()
        action = str(payload.get("action", "")).strip()
        if not model:
            raise WebRequestError("请提供模型名称。")
        knowledge = CapabilityKnowledgeGraph.load(self.knowledge_path)
        if action == "compare":
            result = knowledge.compare_versions(
                model,
                str(payload.get("left", "")),
                str(payload.get("right", "")),
            )
        elif action == "promote":
            result = {
                "event": knowledge.promote_version(
                    model, str(payload.get("version", ""))
                )
            }
        elif action == "rollback":
            result = {
                "event": knowledge.rollback_version(
                    model, str(payload.get("version", ""))
                )
            }
        else:
            raise WebRequestError("版本操作必须是 compare、promote 或 rollback。")
        knowledge.save(
            self.knowledge_path,
            self.knowledge_path.with_suffix(".graphml"),
            self.knowledge_path.with_suffix(".html"),
        )
        return {
            "action": action,
            "result": result,
            **self.versions(model),
        }

    def _available_graph_path(self) -> Path | None:
        candidates = [
            self.knowledge_path,
            self.workspace / "knowledge/base_capability_graph.json",
        ]
        return next((path for path in candidates if path.exists()), None)

    def graph_html(self) -> bytes:
        """Return the newest available interactive graph visualization."""

        candidates = [
            self.knowledge_path.with_suffix(".html"),
            self.workspace / "knowledge/base_capability_graph.html",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            graph = CapabilityKnowledgeGraph.bootstrap()
            path = self.workspace / "artifacts/web/capability_graph.html"
            graph.render_html(path)
        return path.read_bytes()
