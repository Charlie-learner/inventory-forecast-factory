"""Persist validation outcomes as reusable knowledge graph experience."""

from __future__ import annotations

from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class ExperienceAgent:
    """Write successful validation outcomes back to the capability graph."""

    def write_back(
        self,
        knowledge: CapabilityKnowledgeGraph,
        item_id: int,
        store_code: str,
        model: str,
        metrics: dict[str, float],
        repairs: list[str],
    ) -> str:
        """Persist model metrics and optional repair history for a validation run."""

        return knowledge.record_validation(
            item_id,
            store_code,
            model,
            metrics,
            status="success",
            repair=" | ".join(repairs) if repairs else None,
        )
