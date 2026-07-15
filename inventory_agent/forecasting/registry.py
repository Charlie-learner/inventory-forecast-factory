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
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ForecastModel]] = {}
        self._metadata: dict[str, ModelMetadata] = {}

    def register(
        self,
        metadata: ModelMetadata,
        factory: Callable[[], ForecastModel],
    ) -> None:
        if metadata.name in self._factories:
            raise ValueError(f"Model already registered: {metadata.name}")
        self._factories[metadata.name] = factory
        self._metadata[metadata.name] = metadata

    def create(self, name: str) -> ForecastModel:
        try:
            return self._factories[name]()
        except KeyError as exc:
            raise KeyError(f"Unknown model {name!r}; available={self.names()}") from exc

    def metadata(self, name: str) -> ModelMetadata:
        return self._metadata[name]

    def names(self) -> list[str]:
        return sorted(self._factories)


def default_registry() -> ModelRegistry:
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
