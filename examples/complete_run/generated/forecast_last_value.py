"""Generated inventory forecasting capability. Do not edit manually."""

from __future__ import annotations

import pandas as pd

from inventory_agent.forecasting.registry import default_registry

MODEL_NAME = 'last_value'


def forecast(history: list[float], horizon: int) -> list[float]:
    """Forecast non-negative daily demand through the standard model registry."""
    series = pd.Series(history, dtype=float)
    model = default_registry().create(MODEL_NAME)
    return model.predict(series, horizon).tolist()


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return explainable daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
