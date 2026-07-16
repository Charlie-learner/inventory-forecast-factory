"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

import pandas as pd

CAPABILITY_NAME = 'last_value'
CAPABILITY_SPEC = {'name': 'last_value', 'task_type': 'inventory_forecasting', 'description': 'Repeats the last observed demand.', 'template_name': 'last_value', 'input_contract': 'non-negative daily qty_alipay_njhs history', 'output_contract': 'daily forecast plus horizon-total target inventory', 'suitable_for': ('short_history',), 'metrics': ('inventory_cost', 'wape'), 'dependencies': (), 'parameters': {}, 'source_type': 'knowledge_graph', 'source_ref': '', 'source_hash': '', 'version': '1.0.0', 'extracted_by': 'knowledge_graph', 'source_title': '', 'source_url': '', 'source_license': '', 'accessed_at': '', 'confidence': 1.0, 'review_status': 'auto_extracted', 'evidence_refs': (), 'extraction_warnings': ()}
PARAMETERS = {}


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
    return [float(series.iloc[-1])] * horizon


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
