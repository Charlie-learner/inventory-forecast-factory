"""Forecast accuracy and inventory-oriented business metrics."""

from __future__ import annotations

import math

import numpy as np


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


def forecast_metrics(
    actual: np.ndarray,
    forecast: np.ndarray,
    overstock_cost: float = 1.0,
    understock_cost: float = 1.0,
) -> dict[str, float]:
    """Compute daily accuracy metrics and horizon-level inventory cost."""

    actual, forecast = _arrays(actual, forecast)
    error = forecast - actual
    absolute = np.abs(error)
    denominator = np.abs(actual).sum()
    smape_denominator = np.abs(actual) + np.abs(forecast)
    actual_total = float(actual.sum())
    target_total = float(forecast.sum())
    inventory_cost = cainiao_inventory_cost(
        actual_total,
        target_total,
        understock_cost,
        overstock_cost,
    )
    return {
        "mae": float(absolute.mean()),
        "rmse": float(math.sqrt(np.mean(error**2))),
        "wape": float(absolute.sum() / denominator) if denominator else float(absolute.sum()),
        "smape": float(np.mean(np.divide(2 * absolute, smape_denominator, out=np.zeros_like(absolute), where=smape_denominator != 0))),
        "bias": float(error.mean()),
        # The selected inventory scenario scores one target value for the
        # complete horizon, so cost is computed after aggregating the fold.
        "inventory_cost": float(inventory_cost),
        "actual_total": actual_total,
        "target_inventory": target_total,
    }
