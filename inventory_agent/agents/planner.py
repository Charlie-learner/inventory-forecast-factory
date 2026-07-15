"""Knowledge-augmented candidate algorithm planning."""

from __future__ import annotations

from inventory_agent.domain import AlgorithmPlan, CapabilityRequest
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class PlanningAgent:
    def plan(
        self,
        request: CapabilityRequest,
        profile: dict,
        knowledge: CapabilityKnowledgeGraph,
    ) -> AlgorithmPlan:
        retrieved = knowledge.retrieve_algorithms(
            str(profile["demand_type"]), limit=request.candidate_count
        )
        names = [record["name"] for record in retrieved]
        if "last_value" not in names:
            names.append("last_value")
        names = names[: request.candidate_count]
        rationale = (
            f"需求类型={profile['demand_type']}，零需求比例={profile['zero_ratio']:.2%}；"
            f"从能力图谱检索 {', '.join(names)}，使用 {request.objective} 滚动验证。"
        )
        return AlgorithmPlan(tuple(names), rationale, request.objective)

