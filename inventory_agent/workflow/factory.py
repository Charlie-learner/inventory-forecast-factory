"""End-to-end Agent workflow required by the capability-factory assignment."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from langgraph.graph import END, StateGraph

from inventory_agent.agents.experience import ExperienceAgent
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
from inventory_agent.services.benchmark import benchmark_series


class InventoryCapabilityWorkflow:
    """Orchestrate requirement understanding through reusable knowledge writeback."""

    def __init__(
        self,
        settings: Settings | None = None,
        knowledge_path: str | Path = "artifacts/knowledge/capability_graph.json",
    ):
        """Initialize agents, model registry, knowledge graph, and workflow."""

        self.settings = settings or Settings.from_env()
        self.llm = create_llm(self.settings)
        self.requirement_agent = RequirementAgent(self.llm)
        self.planning_agent = PlanningAgent()
        self.generator = SafeCodeGenerator()
        self.validator = GeneratedCodeValidator()
        self.repair_agent = RepairAgent(self.generator)
        self.experience_agent = ExperienceAgent()
        self.report_agent = ReportAgent(self.llm)
        self.registry = default_registry()
        self.knowledge_path = Path(knowledge_path)
        self.knowledge = (
            CapabilityKnowledgeGraph.load(self.knowledge_path)
            if self.knowledge_path.exists()
            else CapabilityKnowledgeGraph.bootstrap(self.registry)
        )
        self.graph = self._build_graph()

    def _parse(self, state: dict[str, Any]) -> dict[str, Any]:
        """Parse the natural-language request into a capability contract."""

        state["request"] = self.requirement_agent.parse(state["description"])
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
        return state

    def _plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """Select candidate algorithms using the request and knowledge graph."""

        state["plan"] = self.planning_agent.plan(
            state["request"], state["profile"], self.knowledge
        )
        return state

    def _benchmark(self, state: dict[str, Any]) -> dict[str, Any]:
        """Backtest candidate algorithms and retain the selected model."""

        request = state["request"]
        state["benchmark"] = benchmark_series(
            state["frame"],
            request.item_id,
            request.store_code,
            list(state["plan"].candidates),
            request.horizon,
            registry=self.registry,
            costs=state["costs"],
            allow_missing=state["raw_data_source"],
        )
        state["selected_model"] = state["benchmark"]["selected_model"]
        return state

    def _generate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate a reusable module for the selected forecasting model."""

        generated_dir = Path(state["run_dir"]) / "generated"
        state["generated"] = self.generator.generate(state["selected_model"], generated_dir)
        state.setdefault("repairs", [])
        return state

    def _validate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate the generated module against safety and output contracts."""

        state["code_validation"] = self.validator.validate(state["generated"].path)
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

        generated, reason = self.repair_agent.repair(
            state["selected_model"],
            state["code_validation"].errors,
            Path(state["run_dir"]) / "generated",
        )
        state["generated"] = generated
        state["repairs"].append(reason)
        return state

    @staticmethod
    def _failed(state: dict[str, Any]) -> dict[str, Any]:
        """Stop execution after the configured repair budget is exhausted."""

        errors = "; ".join(state["code_validation"].errors)
        raise RuntimeError(f"Generated capability failed after repair budget: {errors}")

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
        )
        graphml_path = self.knowledge_path.with_suffix(".graphml")
        self.knowledge.save(self.knowledge_path, graphml_path)
        payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request": asdict(state["request"]),
            "profile": state["profile"],
            "plan": asdict(state["plan"]),
            "benchmark": state["benchmark"],
            "business_definition": {
                "target": "未来预测周期内非聚划算支付件数的总和",
                "cost_formula": "A*max(D-T,0) + B*max(T-D,0)",
                "cost_a": "补少/缺货成本",
                "cost_b": "补多/积压成本",
            },
            "generated": {
                "model": state["generated"].model,
                "path": str(state["generated"].path),
                "generation_mode": state["generated"].generation_mode,
            },
            "code_validation": asdict(state["code_validation"]),
            "repairs": state["repairs"],
            "knowledge_graph": {
                "json": str(self.knowledge_path),
                "graphml": str(graphml_path),
            },
        }
        state["report_paths"] = self.report_agent.create(payload, state["run_dir"])
        state["report"] = payload
        state.pop("frame", None)
        state.pop("series", None)
        state.pop("costs", None)
        return state

    def _build_graph(self):
        """Compile the LangGraph workflow and its validation repair loop."""

        workflow = StateGraph(dict)
        workflow.add_node("parse", self._parse)
        workflow.add_node("profile", self._profile)
        workflow.add_node("plan", self._plan)
        workflow.add_node("benchmark", self._benchmark)
        workflow.add_node("generate", self._generate)
        workflow.add_node("validate", self._validate)
        workflow.add_node("repair", self._repair)
        workflow.add_node("failed", self._failed)
        workflow.add_node("report", self._report)
        workflow.set_entry_point("parse")
        workflow.add_edge("parse", "profile")
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
    ) -> dict[str, Any]:
        """Run the capability factory for one natural-language request."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = Path(output_root) / timestamp
        initial = {
            "description": description,
            "data_path": str(data_path),
            "run_dir": str(run_dir),
            "repairs": [],
        }
        return self.graph.invoke(initial)
