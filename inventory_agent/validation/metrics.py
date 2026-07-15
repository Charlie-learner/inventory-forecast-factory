"""Forecast accuracy and inventory-oriented business metrics."""

from __future__ import annotations

import math

import numpy as np


def _arrays(actual: np.ndarray, forecast: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    if actual.shape != forecast.shape:
        raise ValueError(f"Shape mismatch: actual={actual.shape}, forecast={forecast.shape}")
    if actual.size == 0:
        raise ValueError("Metric inputs cannot be empty")
    if not np.isfinite(actual).all() or not np.isfinite(forecast).all():
        raise ValueError("Metric inputs must be finite")
    return actual, forecast


def forecast_metrics(
    actual: np.ndarray,
    forecast: np.ndarray,
    overstock_cost: float = 1.0,
    understock_cost: float = 1.0,
) -> dict[str, float]:
    actual, forecast = _arrays(actual, forecast)
    error = forecast - actual
    absolute = np.abs(error)
    denominator = np.abs(actual).sum()
    smape_denominator = np.abs(actual) + np.abs(forecast)
    asymmetric = np.where(error >= 0, error * overstock_cost, -error * understock_cost)
    return {
        "mae": float(absolute.mean()),
        "rmse": float(math.sqrt(np.mean(error**2))),
        "wape": float(absolute.sum() / denominator) if denominator else float(absolute.sum()),
        "smape": float(np.mean(np.divide(2 * absolute, smape_denominator, out=np.zeros_like(absolute), where=smape_denominator != 0))),
        "bias": float(error.mean()),
        "inventory_cost": float(asymmetric.sum()),
    }

