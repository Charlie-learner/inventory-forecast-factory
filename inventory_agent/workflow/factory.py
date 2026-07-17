"""End-to-end Agent workflow required by the capability-factory assignment."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import traceback
from typing import Any

from langgraph.graph import END, StateGraph

from inventory_agent.agents.experience import ExperienceAgent
from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.agents.planner import PlanningAgent
from inventory_agent.agents.repair import RepairAgent
from inventory_agent.agents.research import IndustryResearchAgent
from inventory_agent.agents.report import ReportAgent
from inventory_agent.agents.requirement import RequirementAgent
from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import (
    create_cainiao_loader,
    load_location_frame,
    load_panel_csv,
)
from inventory_agent.data.panel import demand_series, location_has_observations, profile_series
from inventory_agent.execution import (
    DEFAULT_RUNTIME_LIMITS,
    ProgressCallback,
    get_execution_profile,
)
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.llm.client import create_llm
from inventory_agent.observability.trace import RunRetentionManager, RunTraceRecorder
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.services.replenishment import (
    calculate_replenishment,
    load_business_costs,
)
from inventory_agent.services.performance import (
    analyze_generated_performance,
    write_performance_analysis,
)
from inventory_agent.services.versioning import next_capability_version
from inventory_agent.validation.metrics import default_metric_registry
from inventory_agent.validation.profiles import default_validation_profiles


logger = logging.getLogger(__name__)


class InventoryCapabilityWorkflow:
    """Orchestrate requirement understanding through reusable knowledge writeback."""

    STAGE_TASK_IDS = {
        "requirement_understanding": "understand",
        "capability_extraction": "extract",
        "data_profiling": "profile",
        "online_industry_research": "research",
        "implementation_planning": "plan",
        "candidate_comparison": "compare",
        "code_generation": "generate",
        "code_validation": "validate",
        "code_repair": "validate",
        "report_generation": "deposit",
        "completed": "deposit",
    }

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
        self.research_agent = IndustryResearchAgent(self.llm)
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

    @classmethod
    def _notify_progress(
        cls,
        state: dict[str, Any], stage: str, percent: int, message: str
    ) -> None:
        """Publish progress with the Planner Agent's user-visible task position."""

        callback = state.get("_progress_callback")
        if callback is not None:
            tasks = list(state.get("execution_tasks", []))
            task_id = cls.STAGE_TASK_IDS.get(stage, "")
            task_index = next(
                (
                    index
                    for index, task in enumerate(tasks, start=1)
                    if task.get("task_id") == task_id
                ),
                0,
            )
            active = tasks[task_index - 1] if task_index else {}
            planned_percent = percent
            if task_index and tasks:
                task_floor = int((task_index - 1) * 100 / len(tasks))
                task_ceiling = int(task_index * 100 / len(tasks))
                planned_percent = max(task_floor, min(percent, task_ceiling))
                if stage == "completed":
                    planned_percent = 100
            callback(
                {
                    "stage": stage,
                    "percent": planned_percent,
                    "stage_percent": percent,
                    "message": message,
                    "task_id": task_id,
                    "task_index": task_index,
                    "task_total": len(tasks),
                    "task_title": active.get("title", message),
                    "task_description": active.get("description", ""),
                    "execution_tasks": tasks,
                }
            )

    def _parse(self, state: dict[str, Any]) -> dict[str, Any]:
        """Parse the natural-language request into a capability contract."""

        self._notify_progress(state, "requirement_understanding", 5, "正在理解自然语言任务")
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

        self._notify_progress(state, "data_profiling", 20, "正在加载并诊断需求数据")
        request = state["request"]
        source = Path(state["data_path"])
        is_raw_source = source.is_dir() or source.suffix.lower() == ".zip"
        if is_raw_source:
            frame = load_location_frame(source, request.store_code)
            cost_frame = create_cainiao_loader(source).load_costs()
            costs = resolve_inventory_costs(cost_frame, request.item_id, request.store_code)
        else:
            frame = load_panel_csv(source)
            costs = (
                load_business_costs(
                    source,
                    request.item_id,
                    request.store_code,
                )
                or UNIT_COSTS
            )
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
        has_source_rows = location_has_observations(
            frame, request.item_id, request.store_code
        )
        if not has_source_rows:
            history_status = "zero_history_fallback"
        elif float(series.sum()) <= 0:
            history_status = "all_zero_history"
        else:
            history_status = "observed"
        state["profile"]["history_status"] = history_status
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

        self._notify_progress(state, "capability_extraction", 12, "正在检索和抽取算法能力")
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

        self._notify_progress(state, "implementation_planning", 35, "正在形成候选方案和设计依据")
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
            research_evidence=state.get("online_research_result"),
        )
        state["execution_tasks"] = [
            asdict(task) for task in state["plan"].execution_tasks
        ]
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
        self._notify_progress(
            state,
            "implementation_planning",
            38,
            "Planner Agent 已完成任务拆解，准备比较候选算法",
        )
        return state

    def _research(self, state: dict[str, Any]) -> dict[str, Any]:
        """Optionally retrieve and persist source-traceable industry evidence."""

        self._notify_progress(state, "online_industry_research", 28, "正在处理行业研究证据")
        if not state.get("online_research"):
            state["online_research_result"] = {
                "status": "disabled",
                "provider": "crossref",
                "records": [],
                "analysis": {"recommended_models": [], "findings": [], "risks": []},
            }
            self._record_trace(
                state,
                stage="online_industry_research",
                component="IndustryResearchAgent",
                component_type="agent",
                action="search_and_extract",
                status="skipped",
                inputs={"enabled": False},
                outputs={"status": "disabled"},
            )
            return state
        result_path = Path(state["run_dir"]) / "online_knowledge_extraction.json"
        result = self.research_agent.research(
            state["description"],
            state["profile"],
            result_path,
            limit=5,
        )
        state["online_research_result"] = result
        source_nodes = self.knowledge.ingest_research_evidence(result)
        self._record_trace(
            state,
            stage="online_industry_research",
            component="IndustryResearchAgent",
            component_type="agent",
            action="search_rank_analyze_and_extract",
            status=("success" if result["status"] == "success" else "degraded"),
            inputs={
                "enabled": True,
                "provider": result["provider"],
                "query": result["query"],
            },
            outputs={
                "status": result["status"],
                "record_count": len(result["records"]),
                "recommended_models": result["analysis"]["recommended_models"],
                "knowledge_source_nodes": source_nodes,
                "warnings": result["warnings"],
            },
            artifacts=[result_path],
        )
        return state

    def _benchmark(self, state: dict[str, Any]) -> dict[str, Any]:
        """Backtest candidate algorithms and retain the selected model."""

        self._notify_progress(state, "candidate_comparison", 45, "正在执行无时间泄漏滚动回测")
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
        primary_metric = state["benchmark"]["validation_profile"]["primary_metric"]
        selected_record = next(
            item
            for item in state["benchmark"]["candidates"]
            if item["model"] == state["selected_model"]
        )
        selected_value = selected_record["metrics"].get(primary_metric)
        alternatives = []
        for item in state["benchmark"]["candidates"]:
            if item["model"] == state["selected_model"]:
                continue
            value = item["metrics"].get(primary_metric)
            delta = (
                float(value) - float(selected_value)
                if value is not None and selected_value is not None
                else None
            )
            alternatives.append(
                {
                    "model": item["model"],
                    "primary_metric": primary_metric,
                    "value": value,
                    "difference_from_selected": delta,
                    "reason_not_selected": (
                        f"主指标比选中方案高 {delta:.4f}（越低越好）"
                        if delta is not None and delta > 0
                        else "主指标接近，由验证配置的决胜指标和确定性排序决定"
                    ),
                }
            )
        state["selection_explanation"] = {
            "data_facts": {
                "selected_model": state["selected_model"],
                "primary_metric": primary_metric,
                "selected_value": selected_value,
                "alternatives": alternatives,
            },
            "system_inference": (
                "选中方案在相同历史窗口、相同成本和相同预测周期下综合表现最佳。"
            ),
            "business_boundary": (
                "该结论是历史数据上的相对比较；促销、断货和供应变化仍需人工复核。"
            ),
        }
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

        self._notify_progress(state, "code_generation", 58, "正在生成并比较独立代码实现")
        execution = get_execution_profile(state["execution_mode"])
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
        research = state.get("online_research_result", {})
        compact_research = {
            "status": research.get("status", "disabled"),
            "provider": research.get("provider"),
            "query": research.get("query"),
            "analysis": research.get("analysis", {}),
            "sources": [
                {
                    "title": record.get("title"),
                    "doi": record.get("doi"),
                    "relevance_score": record.get("relevance_score"),
                }
                for record in research.get("records", [])[:5]
            ],
        }
        generated_candidates = self.generator.generate_candidates_from_spec(
            capability_spec,
            generated_dir,
            llm=self.llm,
            candidate_count=execution.implementation_candidates,
            max_workers=execution.generation_workers,
            generation_context={
                "request": asdict(state["request"]),
                "demand_profile": state["profile"],
                "plan_rationale": state["plan"].rationale,
                "validation_metric": state["plan"].validation_metric,
                "online_research": compact_research,
            },
        )
        state["collaboration_paths"] = {
            "blueprint": str(generated_dir / "implementation_blueprint.json"),
            "manifest": str(generated_dir / "multi_agent_collaboration.json"),
        }
        implementation_candidates = []
        ranked_candidates = []
        preselection_validator = GeneratedCodeValidator(
            performance_iterations=execution.performance_iterations
        )

        def validate_candidate(generated: Any) -> tuple[Any, Any]:
            return generated, preselection_validator.validate(
                generated.path,
                reference_model=capability_spec.template_name,
                reference_parameters=capability_spec.parameters,
            )

        if len(generated_candidates) > 1:
            with ThreadPoolExecutor(
                max_workers=min(execution.generation_workers, len(generated_candidates)),
                thread_name_prefix="capability-validation",
            ) as executor:
                validation_results = list(
                    executor.map(validate_candidate, generated_candidates)
                )
        else:
            validation_results = [
                validate_candidate(generated) for generated in generated_candidates
            ]
        for generated, validation in validation_results:
            record = {
                "variant_id": generated.variant_id,
                "strategy": generated.strategy,
                "generation_mode": generated.generation_mode,
                "path": str(generated.path),
                "spec_hash": generated.spec_hash,
                "source_hash": generated.source_hash,
                "prompt_hash": generated.prompt_hash,
                "source_lines": len(generated.source.splitlines()),
                "collaboration": generated.collaboration,
                "validation": asdict(validation),
                "selected": False,
            }
            implementation_candidates.append(record)
            if validation.valid:
                ranked_candidates.append(
                    (
                        float(validation.mean_latency_ms or float("inf")),
                        float(validation.peak_memory_kb or float("inf")),
                        len(generated.source),
                        generated.source_hash,
                        generated,
                    )
                )
        if ranked_candidates:
            ranked_candidates.sort(key=lambda item: item[:4])
            state["generated"] = ranked_candidates[0][4]
        else:
            state["generated"] = generated_candidates[0]
        for record in implementation_candidates:
            record["selected"] = (
                record["source_hash"] == state["generated"].source_hash
            )
        state["implementation_candidates"] = implementation_candidates
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
            stage="multi_agent_code_collaboration",
            component="CodeArchitectureAgent+CodeImplementationAgent+CodeReviewAgent",
            component_type="agent_team",
            action="design_implement_and_review",
            inputs={"capability_spec": asdict(capability_spec)},
            outputs={
                "selected_collaboration": state["generated"].collaboration,
                "collaboration_paths": state["collaboration_paths"],
            },
            artifacts=list(state["collaboration_paths"].values()),
        )
        self._record_trace(
            state,
            stage="selected_code_generation",
            component="SafeCodeGenerator",
            component_type="tool",
            action="validate_rank_and_select_implementations",
            inputs={
                "capability_spec": asdict(capability_spec),
                "candidate_count_requested": execution.implementation_candidates,
                "parallel_workers": execution.generation_workers,
                "generation_context": {
                    "request": asdict(state["request"]),
                    "profile": state["profile"],
                    "validation_metric": state["plan"].validation_metric,
                },
            },
            outputs={
                "model": state["generated"].model,
                "path": state["generated"].path,
                "generation_mode": state["generated"].generation_mode,
                "spec_hash": state["generated"].spec_hash,
                "source_hash": state["generated"].source_hash,
                "variant_id": state["generated"].variant_id,
                "strategy": state["generated"].strategy,
                "collaboration": state["generated"].collaboration,
                "collaboration_paths": state["collaboration_paths"],
                "implementation_candidates": implementation_candidates,
            },
            artifacts=[
                *[candidate.path for candidate in generated_candidates],
                *state["collaboration_paths"].values(),
                *[path for path in [snapshot] if path],
            ],
        )
        state.setdefault("repairs", [])
        state.setdefault("failure_history", [])
        state.setdefault("repair_experience_used", [])
        return state

    def _validate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate the generated module against safety and output contracts."""

        self._notify_progress(state, "code_validation", 82, "正在验证安全、结果一致性和资源消耗")
        execution = get_execution_profile(state["execution_mode"])
        validator = (
            GeneratedCodeValidator(
                timeout_seconds=self.validator.timeout_seconds,
                performance_iterations=execution.performance_iterations,
            )
            if type(self.validator) is GeneratedCodeValidator
            else self.validator
        )
        state["code_validation"] = validator.validate(
            state["generated"].path,
            reference_model=state["capability_spec"].template_name,
            reference_parameters=state["capability_spec"].parameters,
        )
        implementation_candidates = state.setdefault(
            "implementation_candidates", []
        )
        matched = False
        for candidate in implementation_candidates:
            candidate["selected"] = (
                candidate.get("source_hash")
                == state["generated"].source_hash
            )
            if candidate["selected"]:
                candidate["validation"] = asdict(state["code_validation"])
                matched = True
        if not matched:
            implementation_candidates.append(
                {
                    "variant_id": state["generated"].variant_id,
                    "strategy": state["generated"].strategy,
                    "generation_mode": state["generated"].generation_mode,
                    "path": str(state["generated"].path),
                    "spec_hash": state["generated"].spec_hash,
                    "source_hash": state["generated"].source_hash,
                    "prompt_hash": state["generated"].prompt_hash,
                    "source_lines": len(
                        state["generated"].source.splitlines()
                    ),
                    "validation": asdict(state["code_validation"]),
                    "selected": True,
                }
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

        self._notify_progress(state, "code_repair", 88, "正在分析失败原因并检索可复用修复经验")
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
            research_guidance=state.get("online_research_result"),
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
        allocated_version = (
            str(same_version.get("capability_version", spec.version))
            if same_version
            else next_capability_version(
                spec.version,
                [str(item.get("capability_version", "")) for item in existing_versions],
            )
        )
        return {
            "capability_version": allocated_version,
            "generation_mode": generated.generation_mode,
            "variant_id": generated.variant_id,
            "generation_strategy": generated.strategy,
            "prompt_hash": generated.prompt_hash,
            "spec_hash": generated.spec_hash,
            "source_hash": generated.source_hash,
            "source_ref": spec.source_ref,
            "generated_path": str(generated.path),
            "collaboration": {
                "protocol": "architecture-implementation-review-validation",
                "architecture_mode": generated.collaboration.get(
                    "architecture", {}
                ).get("mode", ""),
                "review_mode": generated.collaboration.get("review", {}).get(
                    "mode", ""
                ),
                "revision_applied": generated.collaboration.get(
                    "review", {}
                ).get("revision_applied", False),
            },
            "parent_version": (
                same_version.get("parent_version", "")
                if same_version
                else parent["id"] if parent else ""
            ),
            "repair_count": len(state.get("repairs", [])),
            "validation_profile": state["request"].task_type,
            "performance": {
                "mean_latency_ms": state["code_validation"].mean_latency_ms,
                "peak_memory_kb": state["code_validation"].peak_memory_kb,
                "throughput_calls_per_second": (
                    state["code_validation"].throughput_calls_per_second
                ),
            },
        }

    def _failed(self, state: dict[str, Any]) -> dict[str, Any]:
        """Stop execution after the configured repair budget is exhausted."""

        errors = "; ".join(state["code_validation"].errors)
        selected = next(
            candidate
            for candidate in state["benchmark"]["candidates"]
            if candidate["model"] == state["selected_model"]
        )
        capability_version = self._capability_version(state)
        run_id = self.experience_agent.write_back(
            self.knowledge,
            state["request"].item_id,
            state["request"].store_code,
            state["selected_model"],
            selected["metrics"],
            [*state["repairs"], f"最终失败: {errors}"],
            status="failure",
            validation_checks=state["code_validation"].checks,
            capability_version=capability_version,
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

        self._notify_progress(state, "report_generation", 94, "正在生成业务报告、技术报告和能力版本")
        selected = next(
            candidate
            for candidate in state["benchmark"]["candidates"]
            if candidate["model"] == state["selected_model"]
        )
        capability_version = self._capability_version(state)
        run_id = self.experience_agent.write_back(
            self.knowledge,
            state["request"].item_id,
            state["request"].store_code,
            state["selected_model"],
            selected["metrics"],
            state["repairs"],
            validation_checks=state["code_validation"].checks,
            capability_version=capability_version,
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
        reusable_experience = {
            "schema_version": "1.0",
            "run_id": run_id,
            "model": state["selected_model"],
            "failures": state.get("failure_history", []),
            "repairs_applied": state.get("repairs", []),
            "prior_experience_reused": state.get("repair_experience_used", []),
            "indexed_in_knowledge_graph": True,
        }
        experience_path = Path(state["run_dir"]) / "failure_experience.json"
        experience_path.write_text(
            json.dumps(reusable_experience, ensure_ascii=False, indent=2),
            encoding="utf-8",
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
        performance_analysis = analyze_generated_performance(
            state["generated"].path,
            asdict(state["code_validation"]),
            state.get("implementation_candidates", []),
        )
        performance_path = write_performance_analysis(
            performance_analysis,
            Path(state["run_dir"]) / "performance_analysis.json",
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
            "online_research": state.get("online_research_result", {}),
            "capability_spec": asdict(state["capability_spec"]),
            "benchmark": state["benchmark"],
            "selection_explanation": state.get("selection_explanation", {}),
            "replenishment": calculate_replenishment(
                state["data_path"],
                state["request"].item_id,
                state["request"].store_code,
                state["benchmark"]["target_inventory"],
            ),
            "candidate_code_solutions": state.get("candidate_code_solutions", []),
            "implementation_candidates": state.get(
                "implementation_candidates", []
            ),
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
                "variant_id": state["generated"].variant_id,
                "strategy": state["generated"].strategy,
                "prompt_hash": state["generated"].prompt_hash,
                "spec_hash": state["generated"].spec_hash,
                "source_hash": state["generated"].source_hash,
                "collaboration": state["generated"].collaboration,
            },
            "multi_agent_collaboration": {
                "protocol": "architecture -> parallel implementation -> independent review -> validation",
                "roles": [
                    "CodeArchitectureAgent",
                    "CodeImplementationAgent",
                    "CodeReviewAgent",
                    "GeneratedCodeValidator",
                ],
                "selected_candidate": state["generated"].collaboration,
                "artifacts": state.get("collaboration_paths", {}),
            },
            "capability_version": capability_version,
            "code_validation": asdict(state["code_validation"]),
            "performance_analysis": {
                **performance_analysis,
                "result_path": str(performance_path),
            },
            "repairs": state["repairs"],
            "failure_history": state.get("failure_history", []),
            "repair_experience_used": state.get("repair_experience_used", []),
            "failure_experience": {
                **reusable_experience,
                "result_path": str(experience_path),
            },
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
        execution = get_execution_profile(state["execution_mode"])
        state["report_paths"] = self.report_agent.create(
            payload,
            state["run_dir"],
            use_llm_explanation=execution.use_llm_explanation,
        )
        state["report_paths"]["performance"] = str(performance_path)
        state["report_paths"]["failure_experience"] = str(experience_path)
        state["report_paths"].update(state.get("collaboration_paths", {}))
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
        workflow.add_node("research", self._research)
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
        workflow.add_edge("profile", "research")
        workflow.add_edge("research", "plan")
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
        keep_runs: int = DEFAULT_RUNTIME_LIMITS.default_keep_runs,
        task_type_override: str | None = None,
        online_research: bool = False,
        execution_mode: str = "balanced",
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run the capability factory for one natural-language request."""

        if trace_level not in {"off", "basic", "full"}:
            raise ValueError("trace_level must be one of: off, basic, full")
        if keep_runs <= 0:
            raise ValueError("keep_runs must be positive")
        execution_profile = get_execution_profile(execution_mode)
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
                "online_research": online_research,
                "execution_mode": execution_mode,
                "execution_profile": asdict(execution_profile),
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
            "online_research": online_research,
            "execution_mode": execution_mode,
            "execution_tasks": [
                asdict(task)
                for task in self.planning_agent.provisional_tasks(
                    online_research=online_research
                )
            ],
            "_trace_recorder": trace,
            "_progress_callback": progress_callback,
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
            result.pop("_progress_callback", None)
            self._notify_progress(
                {
                    "_progress_callback": progress_callback,
                    "execution_tasks": result.get("execution_tasks", []),
                },
                "completed",
                100,
                "工作流完成，报告已生成",
            )
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
