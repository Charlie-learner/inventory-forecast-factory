from pathlib import Path

import pandas as pd

from inventory_agent.services.replenishment import (
    calculate_replenishment,
    load_business_costs,
)


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_DATA = ROOT / "examples/business_data"


def test_business_policy_costs_are_used_for_generic_inventory_data():
    costs = load_business_costs(
        BUSINESS_DATA / "demand_history.csv",
        item_id=1001,
        store_code="1",
    )

    assert costs is not None
    assert costs.understock_cost == 3.5
    assert costs.overstock_cost == 1.5
    assert costs.source == "replenishment_policy.csv"


def test_replenishment_applies_inventory_position_moq_pack_and_capacity():
    advice = calculate_replenishment(
        BUSINESS_DATA / "demand_history.csv",
        item_id=1001,
        store_code="1",
        target_inventory=174,
    )

    assert advice["available"] is True
    assert advice["production_target_inventory"] == 193
    assert advice["inventory_position"] == 66
    assert advice["unconstrained_order_qty"] == 127
    assert advice["rounded_order_qty"] == 132
    assert advice["recommended_order_qty"] == 132
    assert advice["capacity_limited"] is False
    assert advice["status"] == "recommended"


def test_replenishment_reports_capacity_limited_order(tmp_path: Path):
    pd.DataFrame(
        [
            {
                "item_id": 1,
                "store_code": 1,
                "on_hand": 8,
                "on_order": 0,
                "backorder": 0,
                "lead_time_days": 5,
                "safety_stock": 5,
                "min_order_qty": 12,
                "pack_size": 6,
                "warehouse_capacity": 20,
            }
        ]
    ).to_csv(tmp_path / "inventory_snapshot.csv", index=False)
    data_path = tmp_path / "demand.csv"
    data_path.write_text("date,item_id,demand\n2026-01-01,1,1\n", encoding="utf-8")

    advice = calculate_replenishment(
        data_path,
        item_id=1,
        store_code="1",
        target_inventory=30,
    )

    assert advice["rounded_order_qty"] == 30
    assert advice["remaining_capacity"] == 12
    assert advice["recommended_order_qty"] == 12
    assert advice["capacity_limited"] is True
    assert advice["status"] == "capacity_limited"


def test_replenishment_falls_back_honestly_without_inventory_snapshot(
    tmp_path: Path,
):
    data_path = tmp_path / "demand.csv"
    data_path.write_text("date,item_id,demand\n2026-01-01,1,1\n", encoding="utf-8")

    advice = calculate_replenishment(
        data_path,
        item_id=1,
        store_code="all",
        target_inventory=10,
    )

    assert advice["available"] is False
    assert "未找到 inventory_snapshot.csv" in advice["reason"]
