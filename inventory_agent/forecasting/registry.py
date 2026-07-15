"""Plugin-style registry for forecast algorithms."""

from __future__ import annotations

from collections.abc import Callable

from inventory_agent.forecasting.base import ForecastModel, ModelMetadata
from inventory_agent.forecasting.models import (
    CrostonModel,
    LastValueModel,
    MovingAverageModel,
    RidgeLagModel,
    SeasonalNaiveModel,
)


class ModelRegistry:
    """Register forecast plugins and create fresh model instances by name."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ForecastModel]] = {}
        self._metadata: dict[str, ModelMetadata] = {}

    def register(
        self,
        metadata: ModelMetadata,
        factory: Callable[[], ForecastModel],
    ) -> None:
        """Register one model factory together with its capability metadata."""

        if metadata.name in self._factories:
            raise ValueError(f"Model already registered: {metadata.name}")
        self._factories[metadata.name] = factory
        self._metadata[metadata.name] = metadata

    def create(self, name: str) -> ForecastModel:
        """Create a model instance or report the available plugin names."""

        try:
            return self._factories[name]()
        except KeyError as exc:
            raise KeyError(f"Unknown model {name!r}; available={self.names()}") from exc

    def metadata(self, name: str) -> ModelMetadata:
        return self._metadata[name]

    def names(self) -> list[str]:
        return sorted(self._factories)


def default_registry() -> ModelRegistry:
    """Build the inventory scenario's default forecast plugin registry."""

    registry = ModelRegistry()
    registry.register(
        ModelMetadata("last_value", "Repeats the last observed demand.", ("short_history",), 1),
        LastValueModel,
    )
    registry.register(
        ModelMetadata(
            "moving_average",
            "Uses the recent 14-day demand average.",
            ("stable", "short_history"),
            7,
        ),
        MovingAverageModel,
    )
    registry.register(
        ModelMetadata(
            "seasonal_naive",
            "Repeats the most recent weekly demand pattern.",
            ("weekly_seasonal", "stable"),
            14,
        ),
        SeasonalNaiveModel,
    )
    registry.register(
        ModelMetadata(
            "croston",
            "Estimates demand size and interval separately.",
            ("intermittent", "many_zeros"),
            14,
        ),
        CrostonModel,
    )
    registry.register(
        ModelMetadata(
            "ridge_lag",
            "Regularized autoregression over the last 14 days.",
            ("trend", "dense", "volatile"),
            30,
            ("scikit-learn",),
        ),
        RidgeLagModel,
    )
    return registry
