"""Knowledge-augmented candidate algorithm planning."""

from __future__ import annotations

from collections.abc import Collection

from inventory_agent.domain import AlgorithmPlan, CapabilityRequest
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class PlanningAgent:
    """Plan candidate algorithms with demand profiles and graph knowledge."""

    def plan(
        self,
        request: CapabilityRequest,
        profile: dict,
        knowledge: CapabilityKnowledgeGraph,
        available_models: Collection[str] | None = None,
    ) -> AlgorithmPlan:
        """Retrieve suitable models and return a bounded validation plan."""

        retrieval_limit = (
            request.candidate_count
            if available_models is None
            else max(request.candidate_count, len(knowledge.graph))
        )
        retrieved = knowledge.retrieve_algorithms(
            str(profile["demand_type"]), limit=retrieval_limit
        )
        allowed = set(available_models) if available_models is not None else None
        names = [
            record["name"]
            for record in retrieved
            if allowed is None or record["name"] in allowed
        ]
        if "last_value" not in names and (allowed is None or "last_value" in allowed):
            names.append("last_value")
        names = names[: request.candidate_count]
        if not names:
            raise ValueError("No executable forecasting capability is available")
        rationale = (
            f"需求类型={profile['demand_type']}，零需求比例={profile['zero_ratio']:.2%}；"
            f"从能力图谱检索 {', '.join(names)}，使用 {request.objective} 滚动验证。"
        )
        return AlgorithmPlan(tuple(names), rationale, request.objective)
