"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

import pandas as pd

CAPABILITY_NAME = 'seasonal_naive'
CAPABILITY_SPEC = {'name': 'seasonal_naive', 'task_type': 'inventory_forecasting', 'description': 'Repeat the latest weekly pattern over the forecast horizon.', 'template_name': 'seasonal_naive', 'input_contract': 'Non-negative daily demand history and a positive forecast horizon.', 'output_contract': 'Non-negative daily forecast and horizon-total target inventory.', 'suitable_for': ('stable', 'weekly_seasonal'), 'metrics': ('bias', 'inventory_cost', 'rmse', 'smape', 'wape'), 'dependencies': ('pandas',), 'parameters': {'period': 7}, 'source_type': 'document', 'source_ref': 'examples\\capabilities\\seasonal_naive.md', 'source_hash': '0d2b62ba65897f56e5124fb51b582f9f6256947ccdda3e2ef2bbf2c2bb9abcb3', 'version': '1.1.0', 'extracted_by': 'deterministic', 'source_title': 'M5 accuracy competition results, findings, and conclusions', 'source_url': 'https://www.sciencedirect.com/science/article/pii/S0169207021001874', 'source_license': 'citation_only', 'accessed_at': '2026-07-16', 'confidence': 0.95, 'review_status': 'source_reviewed', 'evidence_refs': ('article seasonal-naive benchmark discussion', 'inventory_agent/forecasting/models.py:36'), 'extraction_warnings': (), 'implementation_kind': 'algorithm', 'entrypoints': (), 'internal_dependencies': (), 'complexity': {}}
PARAMETERS = {'period': 7}


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
    period = int(PARAMETERS.get("period", 7))
    if period <= 0:
        raise ValueError("period must be positive")
    if len(series) < period:
        return [float(series.mean())] * horizon
    pattern = series.iloc[-period:].tolist()
    return [float(pattern[index % period]) for index in range(horizon)]


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
