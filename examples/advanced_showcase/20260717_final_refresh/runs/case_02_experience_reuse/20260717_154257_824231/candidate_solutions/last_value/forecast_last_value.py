"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

import pandas as pd

CAPABILITY_NAME = 'last_value'
CAPABILITY_SPEC = {'name': 'last_value', 'task_type': 'inventory_forecasting', 'description': 'Repeat the latest observed demand as a transparent baseline.', 'template_name': 'last_value', 'input_contract': 'Non-negative daily demand history and a positive forecast horizon.', 'output_contract': 'Non-negative daily forecast and horizon-total target inventory.', 'suitable_for': ('short_history',), 'metrics': ('bias', 'inventory_cost', 'rmse', 'smape', 'wape'), 'dependencies': ('pandas',), 'parameters': {}, 'source_type': 'document', 'source_ref': 'F:\\AgentProjects\\TimeSeriesScientist\\examples\\capabilities\\last_value.md', 'source_hash': 'cc24b90807e0ed4eab7186734fcd6a208bc51baa25ce30e19c3993485fc2acc1', 'version': '1.1.0', 'extracted_by': 'deterministic', 'source_title': 'M5 accuracy competition results, findings, and conclusions', 'source_url': 'https://www.sciencedirect.com/science/article/pii/S0169207021001874', 'source_license': 'citation_only', 'accessed_at': '2026-07-16', 'confidence': 0.95, 'review_status': 'source_reviewed', 'evidence_refs': ('article benchmark discussion', 'inventory_agent/forecasting/models.py:12'), 'extraction_warnings': (), 'implementation_kind': 'algorithm', 'entrypoints': (), 'internal_dependencies': (), 'complexity': {}}
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
