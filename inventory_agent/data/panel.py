"""Panel time-series helpers for Cainiao item/warehouse demand."""

from __future__ import annotations

import pandas as pd

from inventory_agent.data.costs import normalize_store_code
from inventory_agent.data.schema import TARGET_COLUMN


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
    clean = pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0)
    zero_ratio = float((clean == 0).mean())
    nonzero = clean[clean > 0]
    mean = float(clean.mean())
    coefficient_of_variation = float(clean.std() / mean) if mean else 0.0
    if zero_ratio >= 0.5:
        demand_type = "intermittent"
    elif coefficient_of_variation >= 1.0:
        demand_type = "volatile"
    else:
        demand_type = "stable"
    return {
        "observations": int(len(clean)),
        "nonzero_observations": int(len(nonzero)),
        "zero_ratio": zero_ratio,
        "mean": mean,
        "coefficient_of_variation": coefficient_of_variation,
        "demand_type": demand_type,
    }
