"""Shared domain objects for the capability factory."""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class CapabilityRequest:
    """Describe the algorithm capability requested by a user."""

    description: str
    item_id: int
    store_code: str
    horizon: int = 14
    candidate_count: int = 3
    task_type: str = "inventory_target"
    objective: str = "inventory_cost"
    constraints: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Reject requests with missing or invalid core fields."""

        if not self.description.strip():
            raise ValueError("description cannot be empty")
        if self.item_id < 0:
            raise ValueError("item_id must be non-negative")
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.candidate_count <= 0:
            raise ValueError("candidate_count must be positive")
        if not self.task_type.strip():
            raise ValueError("task_type cannot be empty")


@dataclass(frozen=True)
class AlgorithmPlan:
    """Represent the candidate algorithm plan produced by the planning agent."""

    candidates: tuple[str, ...]
    rationale: str
    validation_metric: str = "inventory_cost"
    max_repairs: int = 2
