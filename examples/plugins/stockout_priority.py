"""Example trusted plugin for a shortage-sensitive inventory task."""

from __future__ import annotations

import numpy as np

from inventory_agent.plugins import PluginContext
from inventory_agent.validation.profiles import ValidationProfile


def underforecast_rate(
    actual: np.ndarray,
    forecast: np.ndarray,
    _overstock_cost: float,
    _understock_cost: float,
) -> float:
    """Return unmet demand as a fraction of total actual demand."""

    shortage = np.maximum(actual - forecast, 0.0).sum()
    denominator = max(float(np.abs(actual).sum()), 1.0)
    return float(shortage / denominator)


def register(context: PluginContext) -> None:
    """Register a custom metric and its task-specific validation policy."""

    context.register_metric("underforecast_rate", underforecast_rate)
    context.register_validation_profile(
        ValidationProfile(
            name="stockout_priority",
            primary_metric="underforecast_rate",
            tie_breakers=("inventory_cost", "wape"),
            folds=4,
            min_history_days=42,
            description="Prioritize avoiding unmet demand for high-service-level items.",
        )
    )
