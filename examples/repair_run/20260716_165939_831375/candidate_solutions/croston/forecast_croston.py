"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

import pandas as pd

CAPABILITY_NAME = 'croston'
CAPABILITY_SPEC = {'name': 'croston', 'task_type': 'inventory_forecasting', 'description': 'Estimate non-zero demand size and the interval between demands separately.', 'template_name': 'croston', 'input_contract': 'Non-negative daily demand history with possible zero-demand periods.', 'output_contract': 'Non-negative daily forecast and horizon-total target inventory.', 'suitable_for': ('intermittent', 'many_zeros'), 'metrics': ('inventory_cost', 'rmse', 'wape'), 'dependencies': ('pandas',), 'parameters': {'alpha': 0.1}, 'source_type': 'document', 'source_ref': 'examples\\capabilities\\croston.md', 'source_hash': '6ad85105ef03db150bc00094f17137a4f3dec60db53e2bd0a9f209d25b5cd35b', 'version': '1.1.0', 'extracted_by': 'deterministic', 'source_title': 'Forecasting and Stock Control for Intermittent Demands', 'source_url': 'https://doi.org/10.1057/jors.1972.50', 'source_license': 'citation_only', 'accessed_at': '2026-07-16', 'confidence': 0.9, 'review_status': 'source_reviewed', 'evidence_refs': ('Croston 1972 method description', 'inventory_agent/forecasting/models.py:52'), 'extraction_warnings': ('This implementation is classic Croston rather than the Syntetos-Boylan adjustment.',)}
PARAMETERS = {'alpha': 0.1}


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
    alpha = float(PARAMETERS.get("alpha", 0.1))
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    values = series.tolist()
    nonzero_positions = [index for index, value in enumerate(values) if value > 0]
    if not nonzero_positions:
        return [0.0] * horizon
    first = nonzero_positions[0]
    demand_estimate = values[first]
    interval_estimate = float(first + 1)
    interval = 1
    for value in values[first + 1:]:
        if value > 0:
            demand_estimate += alpha * (value - demand_estimate)
            interval_estimate += alpha * (interval - interval_estimate)
            interval = 1
        else:
            interval += 1
    value = max(float(demand_estimate / max(interval_estimate, 1e-12)), 0.0)
    return [value] * horizon


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
