"""Panel time-series helpers for Cainiao item/warehouse demand."""

from __future__ import annotations

import math

import pandas as pd

from inventory_agent.data.costs import normalize_store_code
from inventory_agent.data.schema import TARGET_COLUMN


def _lag_correlation(series: pd.Series, lag: int) -> float:
    """Return a finite lag correlation without warning on constant slices."""

    if len(series) <= lag:
        return 0.0
    current = series.iloc[lag:].reset_index(drop=True)
    previous = series.iloc[:-lag].reset_index(drop=True)
    if current.nunique() <= 1 or previous.nunique() <= 1:
        return 0.0
    value = float(current.corr(previous))
    return value if math.isfinite(value) else 0.0


def location_has_observations(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
) -> bool:
    """Check whether an official item/location series has any source rows."""

    location = normalize_store_code(store_code)
    selected = frame[frame["item_id"] == item_id]
    if location == "all" and "store_code" in frame.columns:
        selected = selected[selected["store_code"].astype(str).str.lower() == "all"]
    elif location != "all":
        selected = selected[selected["store_code"].astype(str) == location]
    return not selected.empty


def demand_series(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
    target: str = TARGET_COLUMN,
    allow_missing: bool = False,
) -> pd.Series:
    """Build a complete daily demand series for one item and location."""

    location = normalize_store_code(store_code)
    required = {"date", "item_id", target}
    if location != "all":
        required.add("store_code")
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing panel columns: {sorted(missing)}")
    selected = frame[frame["item_id"] == item_id]
    if location == "all" and "store_code" in frame.columns:
        selected = selected[selected["store_code"].astype(str).str.lower() == "all"]
    elif location != "all":
        selected = selected[selected["store_code"].astype(str) == location]
    if selected.empty and not allow_missing:
        raise ValueError(f"No observations for item={item_id}, store={store_code}")
    calendar = pd.to_datetime(frame["date"], errors="raise")
    if calendar.empty:
        raise ValueError("Panel data cannot be empty")
    full_index = pd.date_range(calendar.min(), calendar.max(), freq="D")
    if selected.empty:
        return pd.Series(0.0, index=full_index, name="demand")
    daily = selected.groupby("date", sort=True)[target].sum()
    return daily.reindex(full_index, fill_value=0).astype(float).rename("demand")


def profile_series(series: pd.Series) -> dict[str, float | int | str]:
    """Summarize demand density, trend, seasonality, and volatility."""

    clean = pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0)
    zero_ratio = float((clean == 0).mean())
    nonzero = clean[clean > 0]
    mean = float(clean.mean())
    coefficient_of_variation = float(clean.std() / mean) if mean else 0.0
    time_index = pd.Series(range(len(clean)), index=clean.index, dtype=float)
    trend_strength = (
        float(clean.corr(time_index))
        if len(clean) >= 3 and clean.nunique() > 1
        else 0.0
    )
    lag_1_correlation = _lag_correlation(clean, 1)
    lag_7_correlation = _lag_correlation(clean, 7)
    trend_strength = trend_strength if math.isfinite(trend_strength) else 0.0
    lag_1_correlation = (
        lag_1_correlation if math.isfinite(lag_1_correlation) else 0.0
    )
    lag_7_correlation = (
        lag_7_correlation if math.isfinite(lag_7_correlation) else 0.0
    )
    if zero_ratio >= 0.5:
        demand_type = "intermittent"
    elif abs(trend_strength) >= 0.7:
        demand_type = "trend"
    elif (
        len(clean) >= 21
        and lag_7_correlation >= 0.6
        and lag_7_correlation - lag_1_correlation >= 0.2
    ):
        demand_type = "weekly_seasonal"
    elif coefficient_of_variation >= 0.35:
        demand_type = "volatile"
    else:
        demand_type = "stable"
    return {
        "observations": int(len(clean)),
        "nonzero_observations": int(len(nonzero)),
        "zero_ratio": zero_ratio,
        "mean": mean,
        "coefficient_of_variation": coefficient_of_variation,
        "trend_strength": trend_strength,
        "lag_1_correlation": lag_1_correlation,
        "lag_7_correlation": lag_7_correlation,
        "demand_type": demand_type,
    }
