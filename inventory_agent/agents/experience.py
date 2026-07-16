"""Persist validation outcomes as reusable knowledge graph experience."""

from __future__ import annotations

from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class ExperienceAgent:
    """Write validation outcomes back to the capability graph."""

    def write_back(
        self,
        knowledge: CapabilityKnowledgeGraph,
        item_id: int,
        store_code: str,
        model: str,
        metrics: dict[str, float],
        repairs: list[str],
        status: str = "success",
        validation_checks: dict[str, bool] | None = None,
        capability_version: dict | None = None,
        failure_history: list[dict] | None = None,
    ) -> str:
        """Persist metrics, status, and optional repair history for a validation run."""

        return knowledge.record_validation(
            item_id,
            store_code,
            model,
            metrics,
            status=status,
            repair=" | ".join(repairs) if repairs else None,
            validation_checks=validation_checks,
            capability_version=capability_version,
            failure_history=failure_history,
        )
