"""Plugin-style validation profiles for different forecasting objectives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationProfile:
    """Define how one task type is backtested and ranked."""

    name: str
    primary_metric: str
    tie_breakers: tuple[str, ...]
    folds: int = 3
    min_history_days: int = 28
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("validation profile name cannot be empty")
        if not self.primary_metric.strip():
            raise ValueError("primary_metric cannot be empty")
        if self.folds <= 0 or self.min_history_days <= 0:
            raise ValueError("folds and min_history_days must be positive")

    @property
    def ranking_metrics(self) -> tuple[str, ...]:
        """Return the primary metric followed by deterministic tie-breakers."""

        return (self.primary_metric, *self.tie_breakers)


class ValidationProfileRegistry:
    """Register validation policies without coupling them to the workflow."""

    def __init__(self) -> None:
        self._profiles: dict[str, ValidationProfile] = {}

    def register(self, profile: ValidationProfile) -> None:
        """Register one task profile and reject accidental replacement."""

        if profile.name in self._profiles:
            raise ValueError(f"Validation profile already registered: {profile.name}")
        self._profiles[profile.name] = profile

    def get(self, name: str) -> ValidationProfile:
        """Return a profile or explain which task types are available."""

        try:
            return self._profiles[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown validation profile {name!r}; available={self.names()}"
            ) from exc

    def names(self) -> list[str]:
        """List registered task types in stable order."""

        return sorted(self._profiles)


def default_validation_profiles() -> ValidationProfileRegistry:
    """Build profiles for inventory-cost and forecast-accuracy tasks."""

    registry = ValidationProfileRegistry()
    registry.register(
        ValidationProfile(
            name="inventory_target",
            primary_metric="inventory_cost",
            tie_breakers=("wape", "rmse"),
            description="Minimize asymmetric shortage and overstock cost.",
        )
    )
    registry.register(
        ValidationProfile(
            name="demand_forecast",
            primary_metric="wape",
            tie_breakers=("rmse", "inventory_cost"),
            description="Prioritize daily demand forecast accuracy.",
        )
    )
    return registry
