"""Panel time-series helpers for Cainiao item/warehouse demand."""

from __future__ import annotations

import pandas as pd

from inventory_agent.data.schema import TARGET_COLUMN


def demand_series(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
    target: str = TARGET_COLUMN,
) -> pd.Series:
    required = {"date", "item_id", "store_code", target}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing panel columns: {sorted(missing)}")
    selected = frame[(frame["item_id"] == item_id) & (frame["store_code"].astype(str) == str(store_code))]
    if selected.empty:
        raise ValueError(f"No observations for item={item_id}, store={store_code}")
    daily = selected.groupby("date", sort=True)[target].sum()
    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
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

