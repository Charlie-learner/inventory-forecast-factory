"""Benchmark candidate algorithms for one Cainiao item/warehouse series."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from inventory_agent.data.costs import InventoryCostWeights, UNIT_COSTS, normalize_store_code
from inventory_agent.data.panel import demand_series, profile_series
from inventory_agent.forecasting.registry import ModelRegistry, default_registry
from inventory_agent.validation.backtest import RollingBacktester
from inventory_agent.validation.profiles import ValidationProfile, default_validation_profiles
from inventory_agent.validation.metrics import MetricRegistry


def benchmark_series(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
    model_names: list[str] | None = None,
    horizon: int = 14,
    folds: int | None = None,
    registry: ModelRegistry | None = None,
    costs: InventoryCostWeights | None = None,
    allow_missing: bool = False,
    validation_profile: ValidationProfile | None = None,
    metric_registry: MetricRegistry | None = None,
    model_parameters: dict[str, dict] | None = None,
) -> dict:
    """Backtest candidates and forecast inventory for one item/location."""

    registry = registry or default_registry()
    costs = costs or UNIT_COSTS
    validation_profile = validation_profile or default_validation_profiles().get(
        "inventory_target"
    )
    location = normalize_store_code(store_code)
    names = model_names or registry.names()
    series = demand_series(frame, item_id, location, allow_missing=allow_missing)
    backtester = RollingBacktester(
        horizon=horizon,
        folds=validation_profile.folds if folds is None else folds,
        min_history=max(validation_profile.min_history_days, horizon * 2),
        metric_registry=metric_registry,
    )

    def configured_model(name: str):
        model = registry.create(name)
        for parameter, value in (model_parameters or {}).get(name, {}).items():
            if not hasattr(model, parameter):
                raise ValueError(
                    f"Forecast capability {name!r} has no parameter {parameter!r}"
                )
            setattr(model, parameter, value)
        return model

    results = [
        backtester.evaluate(
            configured_model(name),
            series,
            overstock_cost=costs.overstock_cost,
            understock_cost=costs.understock_cost,
        )
        for name in names
    ]
    best = backtester.select_best(results, validation_profile.ranking_metrics)
    final_forecast = configured_model(best.model).predict(series, horizon)
    return {
        "item_id": int(item_id),
        "store_code": location,
        "profile": profile_series(series),
        "horizon": horizon,
        "evaluation_unit": "horizon_total",
        "validation_profile": asdict(validation_profile),
        "costs": costs.as_dict(),
        "candidates": [asdict(result) for result in results],
        "selected_model": best.model,
        "forecast": final_forecast.tolist(),
        "forecast_total": float(final_forecast.sum()),
        "target_inventory": float(final_forecast.sum()),
    }
