"""Forecast accuracy and inventory-oriented business metrics."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


MetricFunction = Callable[[np.ndarray, np.ndarray, float, float], float]


class MetricRegistry:
    """Register evaluation metrics behind one stable callable contract."""

    def __init__(self) -> None:
        self._metrics: dict[str, MetricFunction] = {}

    def register(self, name: str, function: MetricFunction) -> None:
        """Register a metric without silently replacing an existing one."""

        if not name.strip():
            raise ValueError("metric name cannot be empty")
        if name in self._metrics:
            raise ValueError(f"Metric already registered: {name}")
        self._metrics[name] = function

    def evaluate(
        self,
        actual: np.ndarray,
        forecast: np.ndarray,
        overstock_cost: float,
        understock_cost: float,
    ) -> dict[str, float]:
        """Evaluate metrics in registration order and reject invalid outputs."""

        results = {}
        for name, function in self._metrics.items():
            value = float(function(actual, forecast, overstock_cost, understock_cost))
            if not math.isfinite(value):
                raise ValueError(f"Metric {name!r} returned a non-finite value")
            results[name] = value
        return results

    def names(self) -> list[str]:
        """List metric plugin names in registration order."""

        return list(self._metrics)


def _arrays(actual: np.ndarray, forecast: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert metric inputs to compatible finite arrays."""

    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    if actual.shape != forecast.shape:
        raise ValueError(f"Shape mismatch: actual={actual.shape}, forecast={forecast.shape}")
    if actual.size == 0:
        raise ValueError("Metric inputs cannot be empty")
    if not np.isfinite(actual).all() or not np.isfinite(forecast).all():
        raise ValueError("Metric inputs must be finite")
    return actual, forecast


def cainiao_inventory_cost(
    actual_total: float,
    target_inventory: float,
    understock_cost: float,
    overstock_cost: float,
) -> float:
    """Score one item/location target over the complete forecast horizon."""

    values = np.asarray(
        [actual_total, target_inventory, understock_cost, overstock_cost], dtype=float
    )
    if not np.isfinite(values).all():
        raise ValueError("Inventory cost inputs must be finite")
    if understock_cost < 0 or overstock_cost < 0:
        raise ValueError("Inventory cost weights must be non-negative")
    return float(
        understock_cost * max(actual_total - target_inventory, 0.0)
        + overstock_cost * max(target_inventory - actual_total, 0.0)
    )


def default_metric_registry() -> MetricRegistry:
    """Build the standard accuracy and inventory-cost metric plugins."""

    registry = MetricRegistry()
    registry.register(
        "mae", lambda actual, forecast, _over, _under: np.abs(forecast - actual).mean()
    )
    registry.register(
        "rmse",
        lambda actual, forecast, _over, _under: math.sqrt(
            np.mean((forecast - actual) ** 2)
        ),
    )
    registry.register(
        "wape",
        lambda actual, forecast, _over, _under: (
            np.abs(forecast - actual).sum() / np.abs(actual).sum()
            if np.abs(actual).sum()
            else np.abs(forecast - actual).sum()
        ),
    )

    def smape(
        actual: np.ndarray,
        forecast: np.ndarray,
        _overstock_cost: float,
        _understock_cost: float,
    ) -> float:
        absolute = np.abs(forecast - actual)
        denominator = np.abs(actual) + np.abs(forecast)
        return float(
            np.mean(
                np.divide(
                    2 * absolute,
                    denominator,
                    out=np.zeros_like(absolute),
                    where=denominator != 0,
                )
            )
        )

    registry.register("smape", smape)
    registry.register(
        "bias", lambda actual, forecast, _over, _under: (forecast - actual).mean()
    )
    registry.register(
        "inventory_cost",
        lambda actual, forecast, overstock_cost, understock_cost: cainiao_inventory_cost(
            float(actual.sum()),
            float(forecast.sum()),
            understock_cost,
            overstock_cost,
        ),
    )
    registry.register(
        "actual_total", lambda actual, _forecast, _over, _under: actual.sum()
    )
    registry.register(
        "target_inventory", lambda _actual, forecast, _over, _under: forecast.sum()
    )
    return registry


def forecast_metrics(
    actual: np.ndarray,
    forecast: np.ndarray,
    overstock_cost: float = 1.0,
    understock_cost: float = 1.0,
    registry: MetricRegistry | None = None,
) -> dict[str, float]:
    """Compute registered metrics after validating common array contracts."""

    actual, forecast = _arrays(actual, forecast)
    registry = registry or default_metric_registry()
    return registry.evaluate(actual, forecast, overstock_cost, understock_cost)
