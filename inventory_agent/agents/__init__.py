"""Specialized agents exposed lazily to avoid cross-stage import cycles."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "CapabilityExtractionAgent",
    "CodeArchitectureAgent",
    "CodeImplementationAgent",
    "CodeReviewAgent",
    "IndustryResearchAgent",
    "PlanningAgent",
    "RepairAgent",
    "RequirementAgent",
]

_MODULE_BY_AGENT = {
    "CapabilityExtractionAgent": "inventory_agent.agents.extraction",
    "CodeArchitectureAgent": "inventory_agent.agents.code_collaboration",
    "CodeImplementationAgent": "inventory_agent.agents.code_collaboration",
    "CodeReviewAgent": "inventory_agent.agents.code_collaboration",
    "IndustryResearchAgent": "inventory_agent.agents.research",
    "PlanningAgent": "inventory_agent.agents.planner",
    "RepairAgent": "inventory_agent.agents.repair",
    "RequirementAgent": "inventory_agent.agents.requirement",
}


def __getattr__(name: str) -> Any:
    """Load an agent class only when the public attribute is requested."""

    try:
        module_name = _MODULE_BY_AGENT[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
