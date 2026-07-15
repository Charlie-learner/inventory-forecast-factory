"""Benchmark candidate algorithms for one Cainiao item/warehouse series."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from inventory_agent.data.panel import demand_series, profile_series
from inventory_agent.forecasting.registry import ModelRegistry, default_registry
from inventory_agent.validation.backtest import RollingBacktester


def benchmark_series(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
    model_names: list[str] | None = None,
    horizon: int = 14,
    folds: int = 3,
    registry: ModelRegistry | None = None,
) -> dict:
    registry = registry or default_registry()
    names = model_names or registry.names()
    series = demand_series(frame, item_id, store_code)
    backtester = RollingBacktester(horizon=horizon, folds=folds, min_history=max(28, horizon * 2))
    results = [backtester.evaluate(registry.create(name), series) for name in names]
    best = backtester.select_best(results)
    final_forecast = registry.create(best.model).predict(series, horizon)
    return {
        "item_id": int(item_id),
        "store_code": str(store_code),
        "profile": profile_series(series),
        "horizon": horizon,
        "candidates": [asdict(result) for result in results],
        "selected_model": best.model,
        "forecast": final_forecast.tolist(),
        "forecast_total": float(final_forecast.sum()),
    }

