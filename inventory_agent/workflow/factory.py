"""End-to-end Agent workflow required by the capability-factory assignment."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging
from pathlib import Path
import traceback
from typing import Any

import pandas as pd
from langgraph.graph import END, StateGraph

from inventory_agent.agents.experience import ExperienceAgent
from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.agents.planner import PlanningAgent
from inventory_agent.agents.repair import RepairAgent
from inventory_agent.agents.report import ReportAgent
from inventory_agent.agents.requirement import RequirementAgent
from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import create_cainiao_loader, load_location_frame
from inventory_agent.data.panel import demand_series, location_has_observations, profile_series
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.llm.client import create_llm
from inventory_agent.observability.trace import RunRetentionManager, RunTraceRecorder
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.validation.metrics import default_metric_registry
from inventory_agent.validation.profiles import default_validation_profiles


logger = logging.getLogger(__name__)


class InventoryCapabilityWorkflow:
    """Orchestrate requirement understanding through reusable knowledge writeback."""

    def __init__(
        self,
        settings: Settings | None = None,
        knowledge_path: str | Path = "artifacts/knowledge/capability_graph.json",
        plugin_specs: list[str] | tuple[str, ...] | None = None,
    ):
        """Initialize agents, model registry, knowledge graph, and workflow."""

        self.settings = settings or Settings.from_env()
        self.llm = create_llm(self.settings)
        self.requirement_agent = RequirementAgent(self.llm)
        self.extraction_agent = CapabilityExtractionAgent(self.llm)
        self.planning_agent = PlanningAgent()
        self.generator = SafeCodeGenerator()
        self.validator = GeneratedCodeValidator()
        self.repair_agent = RepairAgent(self.generator, self.llm)
        self.experience_agent = ExperienceAgent()
        self.report_agent = ReportAgent(self.llm)
        self.registry = default_registry()
        self.metric_registry = default_metric_registry()
        self.validation_profiles = default_validation_profiles()
        self.loaded_plugins = load_plugins(
            plugin_specs,
            self.metric_registry,
            self.validation_profiles,
        )
        self.knowledge_path = Path(knowledge_path)
        self.knowledge = (
            CapabilityKnowledgeGraph.load(self.knowledge_path)
            if self.knowledge_path.exists()
            else CapabilityKnowledgeGraph.bootstrap(self.registry)
        )
        self.graph = self._build_graph()

    @staticmethod
    def _record_trace(state: dict[str, Any], **event: Any) -> None:
        """Record one workflow event when tracing is enabled."""

        recorder = state.get("_trace_recorder")
        if recorder is not None:
            recorder.record(**event)

    def _parse(self, state: dict[str, Any]) -> dict[str, Any]:
        """Parse the natural-language request into a capability contract."""

        request = self.requirement_agent.parse(state["description"])
        task_type_override = state.get("task_type_override")
        if task_type_override:
            profile = self.validation_profiles.get(task_type_override)
            request = replace(
                request,
                task_type=profile.name,
                objective=profile.primary_metric,
            )
        state["request"] = request
        self._record_trace(
            state,
            stage="requirement_understanding",
            component="RequirementAgent",
            component_type="agent",
            action="parse",
            inputs={"description": state["description"]},
            outputs=asdict(state["request"]),
        )
        logger.info("Parsed request for item=%s store=%s", state["request"].item_id, state["request"].store_code)
        return state

    def _profile(self, state: dict[str, Any]) -> dict[str, Any]:
        """Load demand history, costs, and the series demand profile."""

        request = state["request"]
        source = Path(state["data_path"])
        is_raw_source = source.is_dir() or source.suffix.lower() == ".zip"
        if is_raw_source:
            frame = load_location_frame(source, request.store_code)
            cost_frame = create_cainiao_loader(source).load_costs()
            costs = resolve_inventory_costs(cost_frame, request.item_id, request.store_code)
        else:
            frame = pd.read_csv(source, parse_dates=["date"])
            costs = UNIT_COSTS
        series = demand_series(
            frame,
            request.item_id,
            request.store_code,
            allow_missing=is_raw_source,
        )
        state["frame"] = frame
        state["series"] = series
        state["costs"] = costs
        state["raw_data_source"] = is_raw_source
        state["profile"] = profile_series(series)
        state["profile"]["history_status"] = (
            "observed"
            if location_has_observations(frame, request.item_id, request.store_code)
            else "zero_history_fallback"
        )
        self._record_trace(
            state,
            stage="data_profiling",
            component="data_loader_and_profiler",
            component_type="tool",
            action="load_and_profile",
            inputs={
                "data_path": source,
                "item_id": request.item_id,
                "store_code": request.store_code,
            },
            outputs={
                "rows": len(frame),
                "history_points": len(series),
                "profile": state["profile"],
                "costs": costs.as_dict(),
                "raw_data_source": is_raw_source,
            },
        )
        return state

    def _extract(self, state: dict[str, Any]) -> dict[str, Any]:
        """Extract optional document/code capabilities and merge them into knowledge."""

        sources = [Path(source) for source in state.get("capability_sources", [])]
        if not sources:
            state["extracted_capabilities"] = []
            state["extraction_result_path"] = None
            self._record_trace(
                state,
                stage="capability_extraction",
                component="CapabilityExtractionAgent",
                component_type="agent",
                action="extract_sources",
                inputs={"sources": []},
                outputs={"count": 0, "message": "using existing knowledge graph"},
            )
            return state
        capabilities = self.extraction_agent.extract_sources(sources)
        self.knowledge.ingest_capabilities(capabilities)
        result_path = self.extraction_agent.write_result(
            capabilities,
            Path(state["run_dir"]) / "extracted_capabilities.json",
            self.extraction_agent.scan_reports,
        )
        state["extracted_capabilities"] = capabilities
        state["extraction_scan_reports"] = self.extraction_agent.scan_reports
        state["extraction_result_path"] = str(result_path)
        self._record_trace(
            state,
            stage="capability_extraction",
            component="CapabilityExtractionAgent",
            component_type="agent",
            action="extract_sources",
            inputs={"sources": sources},
            outputs={
                "count": len(capabilities),
                "capabilities": [asdict(capability) for capability in capabilities],
                "scan_reports": self.extraction_agent.scan_reports,
            },
            artifacts=[result_path],
        )
        logger.info(
            "Extracted capabilities=%s from sources=%s",
            len(capabilities),
            len(sources),
        )
        return state

    def _plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """Select candidate algorithms using the request and knowledge graph."""

        retrieved = self.knowledge.retrieve_algorithms(
            str(state["profile"]["demand_type"]),
            limit=len(self.registry.names()),
        )
        self._record_trace(
            state,
            stage="knowledge_retrieval",
            component="CapabilityKnowledgeGraph",
            component_type="tool",
            action="retrieve_algorithms",
            inputs={"demand_type": state["profile"]["demand_type"]},
            outputs={"retrieved": retrieved},
        )
        state["plan"] = self.planning_agent.plan(
            state["request"],
            state["profile"],
            self.knowledge,
            available_models=self.registry.names(),
        )
        self._record_trace(
            state,
            stage="implementation_planning",
            component="PlanningAgent",
            component_type="agent",
            action="plan",
            inputs={
                "request": asdict(state["request"]),
                "profile": state["profile"],
            },
            outputs=asdict(state["plan"]),
        )
        return state

    def _benchmark(self, state: dict[str, Any]) -> dict[str, Any]:
        """Backtest candidate algorithms and retain the selected model."""

        request = state["request"]
        model_parameters = {
            name: self.knowledge.capability_spec(name).parameters
            for name in state["plan"].candidates
        }
        state["benchmark"] = benchmark_series(
            state["frame"],
            request.item_id,
            request.store_code,
            list(state["plan"].candidates),
            request.horizon,
            registry=self.registry,
            costs=state["costs"],
            allow_missing=state["raw_data_source"],
            validation_profile=self.validation_profiles.get(request.task_type),
            metric_registry=self.metric_registry,
            model_parameters=model_parameters,
        )
        state["selected_model"] = state["benchmark"]["selected_model"]
        self._record_trace(
            state,
            stage="candidate_comparison",
            component="rolling_backtest",
            component_type="tool",
            action="benchmark_candidates",
            inputs={
                "candidates": list(state["plan"].candidates),
                "model_parameters": model_parameters,
                "validation_profile": request.task_type,
            },
            outputs=state["benchmark"],
        )
        logger.info(
            "Selected model=%s using profile=%s",
            state["selected_model"],
            request.task_type,
        )
        return state

    def _generate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate a reusable module from the selected graph capability spec."""

        state["candidate_code_solutions"] = []
        if state.get("trace_level") == "full":
            benchmark_by_model = {
                candidate["model"]: candidate
                for candidate in state["benchmark"]["candidates"]
            }
            for model in state["plan"].candidates:
                proposal_spec = self.knowledge.capability_spec(model)
                proposal = self.generator.generate_from_spec(
                    proposal_spec,
                    Path(state["run_dir"]) / "candidate_solutions" / model,
                )
                proposal_validation = self.validator.validate(
                    proposal.path,
                    reference_model=proposal_spec.template_name,
                    reference_parameters=proposal_spec.parameters,
                )
                proposal_record = {
                    "model": model,
                    "selected": model == state["selected_model"],
                    "benchmark": benchmark_by_model.get(model),
                    "capability_spec": asdict(proposal_spec),
                    "generated": {
                        "path": str(proposal.path),
                        "generation_mode": proposal.generation_mode,
                        "spec_hash": proposal.spec_hash,
                        "source_hash": proposal.source_hash,
                    },
                    "code_validation": asdict(proposal_validation),
                }
                state["candidate_code_solutions"].append(proposal_record)
                self._record_trace(
                    state,
                    stage="candidate_code_generation",
                    component="SafeCodeGenerator",
                    component_type="tool",
                    action="generate_and_validate_candidate",
                    inputs={"model": model, "spec": asdict(proposal_spec)},
                    outputs=proposal_record,
                    artifacts=[proposal.path],
                )

        generated_dir = Path(state["run_dir"]) / "generated"
        capability_spec = self.knowledge.capability_spec(state["selected_model"])
        state["capability_spec"] = capability_spec
        state["generated"] = self.generator.generate_from_spec(
            capability_spec,
            generated_dir,
            llm=self.llm,
        )
        recorder = state.get("_trace_recorder")
        snapshot = (
            recorder.snapshot_code(
                state["generated"].source,
                "initial",
                state["generated"].model,
            )
            if recorder is not None
            else None
        )
        self._record_trace(
            state,
            stage="selected_code_generation",
            component="SafeCodeGenerator",
            component_type="tool",
            action="generate_from_spec",
            inputs={"capability_spec": asdict(capability_spec)},
            outputs={
                "model": state["generated"].model,
                "path": state["generated"].path,
                "generation_mode": state["generated"].generation_mode,
                "spec_hash": state["generated"].spec_hash,
                "source_hash": state["generated"].source_hash,
            },
            artifacts=[path for path in [state["generated"].path, snapshot] if path],
        )
        state.setdefault("repairs", [])
        state.setdefault("failure_history", [])
        state.setdefault("repair_experience_used", [])
        return state

    def _validate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate the generated module against safety and output contracts."""

        state["code_validation"] = self.validator.validate(
            state["generated"].path,
            reference_model=state["capability_spec"].template_name,
            reference_parameters=state["capability_spec"].parameters,
        )
        if not state["code_validation"].valid:
            analysis = self.repair_agent.analyze(
                state["code_validation"].errors,
                state["code_validation"].checks,
            )
            state["failure_history"].append(asdict(analysis))
        self._record_trace(
            state,
            stage="code_validation",
            component="GeneratedCodeValidator",
            component_type="tool",
            action="validate",
            status="success" if state["code_validation"].valid else "failed",
            inputs={
                "path": state["generated"].path,
                "reference_model": state["capability_spec"].template_name,
                "reference_parameters": state["capability_spec"].parameters,
                "attempt": len(state["repairs"]),
            },
            outputs=asdict(state["code_validation"]),
        )
        logger.info(
            "Validated generated code valid=%s errors=%s",
            state["code_validation"].valid,
            len(state["code_validation"].errors),
        )
        return state

    @staticmethod
    def _validation_route(state: dict[str, Any]) -> str:
        """Route validation to reporting, repair, or terminal failure."""

        if state["code_validation"].valid:
            return "report"
        if len(state["repairs"]) < state["plan"].max_repairs:
            return "repair"
        return "failed"

    def _repair(self, state: dict[str, Any]) -> dict[str, Any]:
        """Regenerate a safe capability and record the repair reason."""

        current_failure = state["failure_history"][-1]
        prior_experience = self.knowledge.repair_experience(
            state["selected_model"], current_failure["category"]
        )
        generated, reason = self.repair_agent.repair(
            state["selected_model"],
            state["code_validation"].errors,
            Path(state["run_dir"]) / "generated",
            attempt=len(state["repairs"]) + 1,
            current=state["generated"],
            capability_spec=state["capability_spec"],
            prior_experience=prior_experience,
        )
        state["generated"] = generated
        state["repairs"].append(reason)
        state["repair_experience_used"].extend(prior_experience)
        recorder = state.get("_trace_recorder")
        snapshot = (
            recorder.snapshot_code(
                generated.source,
                f"repair_{len(state['repairs'])}",
                generated.model,
            )
            if recorder is not None
            else None
        )
        self._record_trace(
            state,
            stage="code_repair",
            component="RepairAgent",
            component_type="agent",
            action="repair",
            inputs={
                "errors": state["code_validation"].errors,
                "failure": current_failure,
                "prior_experience": prior_experience,
                "attempt": len(state["repairs"]),
            },
            outputs={
                "reason": reason,
                "generation_mode": generated.generation_mode,
                "source_hash": generated.source_hash,
            },
            artifacts=[path for path in [generated.path, snapshot] if path],
        )
        logger.warning("Repair attempt=%s reason=%s", len(state["repairs"]), reason)
        return state

    def _capability_version(self, state: dict[str, Any]) -> dict[str, Any]:
        """Build lineage metadata for the generated implementation version."""

        generated = state["generated"]
        spec = state["capability_spec"]
        existing_versions = self.knowledge.capability_versions(
            state["selected_model"]
        )
        same_version = next(
            (
                version
                for version in existing_versions
                if version.get("source_hash") == generated.source_hash
            ),
            None,
        )
        parent = (
            None
            if same_version
            else next(
                (
                    version
                    for version in existing_versions
                    if version.get("lifecycle_status") == "active"
                ),
                existing_versions[0] if existing_versions else None,
            )
        )
        return {
            "capability_version": spec.version,
            "generation_mode": generated.generation_mode,
            "spec_hash": generated.spec_hash,
            "source_hash": generated.source_hash,
            "source_ref": spec.source_ref,
            "generated_path": str(generated.path),
            "parent_version": (
                same_version.get("parent_version", "")
                if same_version
                else parent["id"] if parent else ""
            ),
            "repair_count": len(state.get("repairs", [])),
            "validation_profile": state["request"].task_type,
        }

    def _failed(self, state: dict[str, Any]) -> dict[str, Any]:
        """Stop execution after the configured repair budget is exhausted."""

        errors = "; ".join(state["code_validation"].errors)
        selected = next(
            candidate
            for candidate in state["benchmark"]["candidates"]
            if candidate["model"] == state["selected_model"]
        )
        run_id = self.experience_agent.write_back(
            self.knowledge,
            state["request"].item_id,
            state["request"].store_code,
            state["selected_model"],
            selected["metrics"],
            [*state["repairs"], f"最终失败: {errors}"],
            status="failure",
            validation_checks=state["code_validation"].checks,
            capability_version=self._capability_version(state),
            failure_history=state.get("failure_history", []),
        )
        knowledge_paths = self._save_knowledge()
        self._record_trace(
            state,
            stage="experience_deposition",
            component="ExperienceAgent",
            component_type="agent",
            action="write_failure",
            status="failed",
            inputs={
                "model": state["selected_model"],
                "repairs": state["repairs"],
                "failure_history": state.get("failure_history", []),
            },
            outputs={"run_id": run_id, "knowledge_graph": knowledge_paths},
            artifacts=list(knowledge_paths.values()),
        )
        logger.error("Capability failed after repair budget: %s", errors)
        raise RuntimeError(f"Generated capability failed after repair budget: {errors}")

    def _save_knowledge(self) -> dict[str, str]:
        """Persist machine-readable and directly viewable graph formats."""

        graphml_path = self.knowledge_path.with_suffix(".graphml")
        html_path = self.knowledge_path.with_suffix(".html")
        self.knowledge.save(self.knowledge_path, graphml_path, html_path)
        return {
            "json": str(self.knowledge_path),
            "graphml": str(graphml_path),
            "html": str(html_path),
        }

    def _report(self, state: dict[str, Any]) -> dict[str, Any]:
        """Persist experience and produce the final validation reports."""

        selected = next(
            candidate
            for candidate in state["benchmark"]["candidates"]
            if candidate["model"] == state["selected_model"]
        )
        run_id = self.experience_agent.write_back(
            self.knowledge,
            state["request"].item_id,
            state["request"].store_code,
            state["selected_model"],
            selected["metrics"],
            state["repairs"],
            validation_checks=state["code_validation"].checks,
            capability_version=self._capability_version(state),
            failure_history=state.get("failure_history", []),
        )
        self._record_trace(
            state,
            stage="experience_deposition",
            component="ExperienceAgent",
            component_type="agent",
            action="write_success",
            inputs={
                "model": state["selected_model"],
                "metrics": selected["metrics"],
                "repairs": state["repairs"],
                "failure_history": state.get("failure_history", []),
            },
            outputs={"run_id": run_id},
        )
        knowledge_paths = self._save_knowledge()
        self._record_trace(
            state,
            stage="knowledge_persistence",
            component="CapabilityKnowledgeGraph",
            component_type="tool",
            action="save",
            inputs={"schema_version": self.knowledge.SCHEMA_VERSION},
            outputs=knowledge_paths,
            artifacts=list(knowledge_paths.values()),
        )
        recorder = state.get("_trace_recorder")
        trace_paths = (
            recorder.paths()
            if recorder is not None and recorder.enabled
            else None
        )
        payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request": asdict(state["request"]),
            "profile": state["profile"],
            "plan": asdict(state["plan"]),
            "capability_extraction": {
                "sources": state.get("capability_sources", []),
                "result_path": state.get("extraction_result_path"),
                "count": len(state.get("extracted_capabilities", [])),
                "scan_reports": state.get("extraction_scan_reports", []),
                "capabilities": [
                    asdict(capability)
                    for capability in state.get("extracted_capabilities", [])
                ],
            },
            "capability_spec": asdict(state["capability_spec"]),
            "benchmark": state["benchmark"],
            "candidate_code_solutions": state.get("candidate_code_solutions", []),
            "business_definition": {
                "target": "未来预测周期内非聚划算支付件数的总和",
                "cost_formula": "A*max(D-T,0) + B*max(T-D,0)",
                "cost_a": "补少/缺货成本",
                "cost_b": "补多/积压成本",
            },
            "validation_profile": state["benchmark"]["validation_profile"],
            "plugins": {
                "loaded": plugin_manifest(self.loaded_plugins),
                "available_metrics": self.metric_registry.names(),
                "available_validation_profiles": self.validation_profiles.names(),
            },
            "generated": {
                "model": state["generated"].model,
                "path": str(state["generated"].path),
                "generation_mode": state["generated"].generation_mode,
                "spec_hash": state["generated"].spec_hash,
                "source_hash": state["generated"].source_hash,
            },
            "code_validation": asdict(state["code_validation"]),
            "repairs": state["repairs"],
            "failure_history": state.get("failure_history", []),
            "repair_experience_used": state.get("repair_experience_used", []),
            "execution_trace": {
                "level": state.get("trace_level", "off"),
                "paths": trace_paths,
                "events_recorded_before_report": (
                    len(recorder.events) if recorder is not None and recorder.enabled else 0
                ),
            },
            "knowledge_graph": {
                **knowledge_paths,
            },
        }
        state["report_paths"] = self.report_agent.create(payload, state["run_dir"])
        self._record_trace(
            state,
            stage="report_generation",
            component="ReportAgent",
            component_type="agent",
            action="create",
            inputs={"run_id": run_id, "report_sections": list(payload)},
            outputs=state["report_paths"],
            artifacts=list(state["report_paths"].values()),
        )
        state["report"] = payload
        state.pop("frame", None)
        state.pop("series", None)
        state.pop("costs", None)
        return state

    def _build_graph(self):
        """Compile the LangGraph workflow and its validation repair loop."""

        workflow = StateGraph(dict)
        workflow.add_node("parse", self._parse)
        workflow.add_node("extract", self._extract)
        workflow.add_node("profile", self._profile)
        workflow.add_node("plan", self._plan)
        workflow.add_node("benchmark", self._benchmark)
        workflow.add_node("generate", self._generate)
        workflow.add_node("validate", self._validate)
        workflow.add_node("repair", self._repair)
        workflow.add_node("failed", self._failed)
        workflow.add_node("report", self._report)
        workflow.set_entry_point("parse")
        workflow.add_edge("parse", "extract")
        workflow.add_edge("extract", "profile")
        workflow.add_edge("profile", "plan")
        workflow.add_edge("plan", "benchmark")
        workflow.add_edge("benchmark", "generate")
        workflow.add_edge("generate", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._validation_route,
            {"report": "report", "repair": "repair", "failed": "failed"},
        )
        workflow.add_edge("repair", "validate")
        workflow.add_edge("report", END)
        return workflow.compile()

    def run(
        self,
        description: str,
        data_path: str | Path,
        output_root: str | Path = "artifacts/runs",
        capability_sources: list[str | Path] | None = None,
        trace_level: str = "basic",
        keep_runs: int = 10,
        task_type_override: str | None = None,
    ) -> dict[str, Any]:
        """Run the capability factory for one natural-language request."""

        if trace_level not in {"off", "basic", "full"}:
            raise ValueError("trace_level must be one of: off, basic, full")
        if keep_runs <= 0:
            raise ValueError("keep_runs must be positive")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = Path(output_root) / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)
        trace = RunTraceRecorder(run_dir, enabled=trace_level != "off")
        deleted_runs = RunRetentionManager.cleanup(output_root, keep_runs)
        trace.record(
            stage="run",
            component="InventoryCapabilityWorkflow",
            component_type="workflow",
            action="run_started",
            inputs={
                "description": description,
                "data_path": data_path,
                "capability_sources": capability_sources or [],
                "trace_level": trace_level,
                "keep_runs": keep_runs,
                "task_type_override": task_type_override,
                "plugins": plugin_manifest(self.loaded_plugins),
            },
            outputs={
                "run_dir": run_dir,
                "deleted_old_run_directories": deleted_runs,
            },
        )
        if hasattr(self.llm, "set_trace_recorder"):
            self.llm.set_trace_recorder(trace if trace.enabled else None)
        initial = {
            "description": description,
            "data_path": str(data_path),
            "run_dir": str(run_dir),
            "repairs": [],
            "capability_sources": [str(source) for source in capability_sources or []],
            "trace_level": trace_level,
            "task_type_override": task_type_override,
            "_trace_recorder": trace,
        }
        logger.info("Starting capability workflow run_dir=%s", run_dir)
        try:
            result = self.graph.invoke(initial)
            trace_paths = trace.finalize(
                "success",
                {
                    "selected_model": result["selected_model"],
                    "target_inventory": result["benchmark"]["target_inventory"],
                    "report_paths": result["report_paths"],
                    "candidate_code_solutions": len(
                        result.get("candidate_code_solutions", [])
                    ),
                },
            )
            result["trace_paths"] = trace_paths
            result.pop("_trace_recorder", None)
            return result
        except Exception as exc:
            trace.finalize(
                "failed",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
            )
            raise
        finally:
            if hasattr(self.llm, "set_trace_recorder"):
                self.llm.set_trace_recorder(None)
