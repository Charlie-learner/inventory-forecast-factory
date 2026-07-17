"""Turn a forecast target into an auditable replenishment recommendation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from inventory_agent.data.costs import InventoryCostWeights, normalize_store_code


def _business_directory(data_path: str | Path) -> Path:
    """Return the directory that may contain companion inventory tables."""

    path = Path(data_path)
    return path if path.is_dir() else path.parent


def _selected_rows(
    frame: pd.DataFrame,
    item_id: int,
    store_code: int | str,
) -> pd.DataFrame:
    """Select an item/location row or all item rows for nationwide aggregation."""

    location = normalize_store_code(store_code)
    selected = frame[frame["item_id"] == item_id]
    if location != "all":
        selected = selected[selected["store_code"].astype(str) == location]
    return selected


def load_business_costs(
    data_path: str | Path,
    item_id: int,
    store_code: int | str,
) -> InventoryCostWeights | None:
    """Load optional shortage/excess costs from a companion policy table."""

    policy_path = _business_directory(data_path) / "replenishment_policy.csv"
    if not policy_path.is_file():
        return None
    policies = pd.read_csv(policy_path)
    required = {
        "item_id",
        "store_code",
        "understock_cost",
        "overstock_cost",
    }
    missing = required.difference(policies.columns)
    if missing:
        raise ValueError(
            f"replenishment_policy.csv missing columns: {sorted(missing)}"
        )
    selected = _selected_rows(policies, item_id, store_code)
    if selected.empty:
        return None
    if normalize_store_code(store_code) == "all":
        understock = float(selected["understock_cost"].mean())
        overstock = float(selected["overstock_cost"].mean())
    elif len(selected) == 1:
        understock = float(selected.iloc[0]["understock_cost"])
        overstock = float(selected.iloc[0]["overstock_cost"])
    else:
        raise ValueError(
            f"Duplicate replenishment policies for item={item_id}, "
            f"store={store_code}"
        )
    return InventoryCostWeights(
        understock,
        overstock,
        source="replenishment_policy.csv",
    )


def calculate_replenishment(
    data_path: str | Path,
    item_id: int,
    store_code: int | str,
    target_inventory: float,
) -> dict[str, Any]:
    """Apply inventory position, safety stock, MOQ, pack, and capacity rules."""

    formula = "max(目标库存 + 安全库存 + 欠单 - 现货 - 在途库存, 0)"
    snapshot_path = _business_directory(data_path) / "inventory_snapshot.csv"
    if not snapshot_path.is_file():
        return {
            "available": False,
            "source": None,
            "formula": formula,
            "reason": "未找到 inventory_snapshot.csv，无法计算具体补货量。",
        }
    snapshots = pd.read_csv(snapshot_path)
    required = {
        "item_id",
        "store_code",
        "on_hand",
        "on_order",
        "backorder",
        "lead_time_days",
        "safety_stock",
        "min_order_qty",
        "pack_size",
        "warehouse_capacity",
    }
    missing = required.difference(snapshots.columns)
    if missing:
        raise ValueError(
            f"inventory_snapshot.csv missing columns: {sorted(missing)}"
        )
    selected = _selected_rows(snapshots, item_id, store_code)
    if selected.empty:
        return {
            "available": False,
            "source": str(snapshot_path),
            "formula": formula,
            "reason": (
                f"库存快照中没有 item={item_id}, store={store_code}。"
            ),
        }
    location = normalize_store_code(store_code)
    if location == "all":
        values = {
            "on_hand": float(selected["on_hand"].sum()),
            "on_order": float(selected["on_order"].sum()),
            "backorder": float(selected["backorder"].sum()),
            "safety_stock": float(selected["safety_stock"].sum()),
            "warehouse_capacity": float(
                selected["warehouse_capacity"].sum()
            ),
            "lead_time_days": float(selected["lead_time_days"].max()),
            "min_order_qty": float(selected["min_order_qty"].sum()),
            "pack_size": 1.0,
        }
        scope = "nationwide_aggregate"
    elif len(selected) == 1:
        row = selected.iloc[0]
        values = {
            name: float(row[name])
            for name in [
                "on_hand",
                "on_order",
                "backorder",
                "safety_stock",
                "warehouse_capacity",
                "lead_time_days",
                "min_order_qty",
                "pack_size",
            ]
        }
        scope = "warehouse"
    else:
        raise ValueError(
            f"Duplicate inventory snapshots for item={item_id}, "
            f"store={store_code}"
        )

    production_target = max(
        float(target_inventory) + values["safety_stock"],
        0.0,
    )
    inventory_position = (
        values["on_hand"] + values["on_order"] - values["backorder"]
    )
    unconstrained = max(production_target - inventory_position, 0.0)
    if unconstrained <= 0:
        rounded = 0.0
    else:
        minimum_applied = max(unconstrained, values["min_order_qty"])
        pack_size = max(values["pack_size"], 1.0)
        rounded = math.ceil(minimum_applied / pack_size) * pack_size
    remaining_capacity = max(
        values["warehouse_capacity"]
        - values["on_hand"]
        - values["on_order"],
        0.0,
    )
    if location == "all":
        capacity_constrained = min(rounded, remaining_capacity)
    else:
        pack_size = max(values["pack_size"], 1.0)
        capacity_constrained = min(
            rounded,
            math.floor(remaining_capacity / pack_size) * pack_size,
        )
    capacity_limited = capacity_constrained + 1e-9 < rounded
    return {
        "available": True,
        "source": str(snapshot_path),
        "scope": scope,
        "formula": formula,
        "target_inventory": float(target_inventory),
        "production_target_inventory": production_target,
        "inventory_position": inventory_position,
        "on_hand": values["on_hand"],
        "on_order": values["on_order"],
        "backorder": values["backorder"],
        "safety_stock": values["safety_stock"],
        "lead_time_days": values["lead_time_days"],
        "min_order_qty": values["min_order_qty"],
        "pack_size": values["pack_size"],
        "warehouse_capacity": values["warehouse_capacity"],
        "remaining_capacity": remaining_capacity,
        "unconstrained_order_qty": unconstrained,
        "rounded_order_qty": rounded,
        "recommended_order_qty": capacity_constrained,
        "capacity_limited": capacity_limited,
        "status": (
            "no_order_needed"
            if capacity_constrained <= 0
            else "capacity_limited"
            if capacity_limited
            else "recommended"
        ),
    }
