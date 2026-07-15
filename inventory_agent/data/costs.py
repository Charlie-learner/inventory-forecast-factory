"""Cainiao inventory-cost semantics and strict item/location lookup."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from inventory_agent.data.schema import COST_A_COLUMN, COST_B_COLUMN, NATIONAL_SCOPE


@dataclass(frozen=True)
class InventoryCostWeights:
    """A penalizes shortage; B penalizes excess target inventory."""

    understock_cost: float
    overstock_cost: float
    source: str = "config2.csv"

    def __post_init__(self) -> None:
        values = np.asarray([self.understock_cost, self.overstock_cost], dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Inventory costs must be finite and non-negative")

    @property
    def critical_fractile(self) -> float:
        total = self.understock_cost + self.overstock_cost
        return self.understock_cost / total if total else 0.5

    def as_dict(self) -> dict[str, float | str]:
        return {**asdict(self), "critical_fractile": self.critical_fractile}


UNIT_COSTS = InventoryCostWeights(1.0, 1.0, source="unit_default")


def normalize_store_code(store_code: int | str) -> str:
    value = str(store_code).strip().lower()
    return NATIONAL_SCOPE if value in {NATIONAL_SCOPE, "全国"} else value


def resolve_inventory_costs(
    costs: pd.DataFrame,
    item_id: int,
    store_code: int | str,
) -> InventoryCostWeights:
    """Return the unique A/B cost pair for one scored item/location key."""

    required = {"item_id", "store_code", COST_A_COLUMN, COST_B_COLUMN}
    missing = required.difference(costs.columns)
    if missing:
        raise ValueError(f"Missing cost columns: {sorted(missing)}")
    location = normalize_store_code(store_code)
    selected = costs[
        (costs["item_id"] == item_id)
        & (costs["store_code"].astype(str).str.lower() == location)
    ]
    if len(selected) != 1:
        raise ValueError(
            f"Expected one cost row for item={item_id}, store={location}, found {len(selected)}"
        )
    row = selected.iloc[0]
    return InventoryCostWeights(float(row[COST_A_COLUMN]), float(row[COST_B_COLUMN]))
