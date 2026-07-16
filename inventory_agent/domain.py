"""Shared domain objects for the capability factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilitySpec:
    """Structured, source-traceable algorithm capability extracted for replication."""

    name: str
    task_type: str
    description: str
    template_name: str
    input_contract: str
    output_contract: str
    suitable_for: tuple[str, ...] = field(default_factory=tuple)
    metrics: tuple[str, ...] = ("inventory_cost", "wape")
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    parameters: dict[str, Any] = field(default_factory=dict)
    source_type: str = "registry"
    source_ref: str = ""
    source_hash: str = ""
    version: str = "1.0.0"
    extracted_by: str = "deterministic"

    def __post_init__(self) -> None:
        """Reject incomplete specifications before graph ingestion or generation."""

        required = {
            "name": self.name,
            "task_type": self.task_type,
            "description": self.description,
            "template_name": self.template_name,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "version": self.version,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Capability specification fields cannot be empty: {missing}")
        safe_name = "".join(
            character
            for character in self.name
            if character.isalnum() or character == "_"
        )
        if safe_name != self.name:
            raise ValueError(f"Unsafe capability name: {self.name!r}")

    @property
    def capability_id(self) -> str:
        """Return a stable human-readable version identifier."""

        return f"{self.name}:{self.version}"

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
