"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

import pandas as pd

CAPABILITY_NAME = 'moving_average'
CAPABILITY_SPEC = {'name': 'moving_average', 'task_type': 'inventory_forecasting', 'description': 'Forecast stable demand with the mean of the most recent observations.', 'template_name': 'moving_average', 'input_contract': 'Non-negative daily demand history and a positive forecast horizon.', 'output_contract': 'Non-negative daily forecast and horizon-total target inventory.', 'suitable_for': ('stable', 'short_history'), 'metrics': ('inventory_cost', 'wape', 'rmse'), 'dependencies': ('pandas',), 'parameters': {'window': 14}, 'source_type': 'document', 'source_ref': 'examples\\capabilities\\moving_average.md', 'source_hash': 'd0a66653269bec0725df3862cc246ca63ed106b231de5804b7d6889019f5c3d2', 'version': '1.1.0', 'extracted_by': 'deterministic', 'source_title': 'The accuracy of intermittent demand estimates', 'source_url': 'https://www.sciencedirect.com/science/article/pii/S0169207004000792', 'source_license': 'citation_only', 'accessed_at': '2026-07-16', 'confidence': 0.9, 'review_status': 'source_reviewed', 'evidence_refs': ('SMA benchmark description', 'inventory_agent/forecasting/models.py:22'), 'extraction_warnings': ()}
PARAMETERS = {'window': 14}


def _clean_history(history: list[float], horizon: int) -> pd.Series:
    """Validate the shared forecasting input contract."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    series = pd.to_numeric(pd.Series(history), errors="coerce").dropna().astype(float)
    if series.empty:
        raise ValueError("history must contain at least one numeric observation")
    return series.clip(lower=0)


def forecast(history: list[float], horizon: int) -> list[float]:
    """Replicate the extracted capability as non-negative daily forecasts."""
    series = _clean_history(history, horizon)
    window = int(PARAMETERS.get("window", 14))
    if window <= 0:
        raise ValueError("window must be positive")
    window = min(window, len(series))
    return [float(series.iloc[-window:].mean())] * horizon


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
