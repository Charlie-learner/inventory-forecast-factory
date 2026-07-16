"""Generate deterministic, Git-friendly multi-table inventory business data."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples/business_data"
START = pd.Timestamp("2025-01-01")
PERIODS = 180
STORES = ("1", "2", "3")
ITEMS = (
    (1001, "stable", START),
    (1002, "weekly_seasonal", START),
    (1003, "intermittent", START),
    (1004, "trend", START),
    (1005, "volatile", START),
    (1006, "cold_start", START + pd.Timedelta(days=120)),
)


def _demand(
    pattern: str,
    day: int,
    item_id: int,
    store_code: str,
    promotion: int,
    stockout: int,
) -> int:
    """Return one reproducible observed-demand value for a scenario."""

    store_factor = {"1": 1.0, "2": 0.75, "3": 1.2}[store_code]
    base = (12 + item_id % 7) * store_factor
    if pattern == "stable":
        value = base + 1.8 * math.sin(day / 9)
    elif pattern == "weekly_seasonal":
        weekly = (0.65, 0.75, 0.9, 1.0, 1.15, 1.35, 1.2)
        value = base * weekly[day % 7]
    elif pattern == "intermittent":
        value = base * (2.5 + (day % 3) * 0.25) if day % 5 == 0 else 0
    elif pattern == "trend":
        value = base + day * 0.11
    elif pattern == "volatile":
        value = base * (1 + 0.48 * math.sin(day * 1.7) + 0.25 * math.cos(day / 3))
    else:
        value = base * (0.8 + min(day, 40) / 100)
    if promotion:
        value *= 1.65
    if stockout:
        value *= 0.35
    return max(int(round(value)), 0)


def build_demand_history() -> pd.DataFrame:
    """Create demand with stable, seasonal, intermittent, trend and cold-start series."""

    rows = []
    dates = pd.date_range(START, periods=PERIODS, freq="D")
    for item_id, pattern, launch_date in ITEMS:
        for store_code in STORES:
            for date in dates:
                if date < launch_date:
                    continue
                day = int((date - launch_date).days)
                promotion = int(
                    (item_id == 1002 and 45 <= (date - START).days <= 49)
                    or (item_id == 1005 and 90 <= (date - START).days <= 94)
                    or (item_id == 1006 and 145 <= (date - START).days <= 149)
                )
                holiday = int((date - START).days in {30, 60, 120, 150})
                stockout = int(
                    item_id == 1005
                    and store_code == "2"
                    and 100 <= (date - START).days <= 102
                )
                rows.append(
                    {
                        "date": date.date().isoformat(),
                        "item_id": item_id,
                        "store_code": store_code,
                        "qty_alipay_njhs": _demand(
                            pattern,
                            day,
                            item_id,
                            store_code,
                            promotion,
                            stockout,
                        ),
                        "unit_price": round(18 + item_id % 11 + int(store_code) * 0.5, 2),
                        "promotion_flag": promotion,
                        "holiday_flag": holiday,
                        "stockout_flag": stockout,
                    }
                )
    return pd.DataFrame(rows)


def build_item_master() -> pd.DataFrame:
    """Create product hierarchy and cold-start metadata."""

    rows = []
    for index, (item_id, pattern, launch_date) in enumerate(ITEMS):
        rows.append(
            {
                "item_id": item_id,
                "item_name": f"demo_sku_{item_id}",
                "category_id": 10 + index // 2,
                "brand_id": 200 + index % 3,
                "supplier_id": 300 + index % 2,
                "launch_date": launch_date.date().isoformat(),
                "demand_pattern": pattern,
                "unit_of_measure": "piece",
            }
        )
    return pd.DataFrame(rows)


def build_inventory_snapshot() -> pd.DataFrame:
    """Create one current inventory position for every item and warehouse."""

    rows = []
    snapshot_date = (START + pd.Timedelta(days=PERIODS)).date().isoformat()
    for item_id, pattern, _ in ITEMS:
        for store_code in STORES:
            location = int(store_code)
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "item_id": item_id,
                    "store_code": store_code,
                    "on_hand": 45 + item_id % 13 + location * 6,
                    "on_order": 12 + location * 3,
                    "backorder": 4 if pattern in {"volatile", "cold_start"} else 0,
                    "lead_time_days": 3 + location * 2,
                    "safety_stock": 15 + location * 4,
                    "min_order_qty": 12,
                    "pack_size": 6,
                    "warehouse_capacity": 500 + location * 150,
                }
            )
    return pd.DataFrame(rows)


def build_replenishment_policy() -> pd.DataFrame:
    """Create cost and service-level policies by item and warehouse."""

    rows = []
    for item_id, pattern, _ in ITEMS:
        for store_code in STORES:
            shortage_cost = 6.0 if pattern in {"volatile", "cold_start"} else 3.5
            rows.append(
                {
                    "item_id": item_id,
                    "store_code": store_code,
                    "understock_cost": shortage_cost,
                    "overstock_cost": 1.5 if pattern != "intermittent" else 3.0,
                    "holding_cost_per_day": 0.08 + int(store_code) * 0.01,
                    "target_service_level": 0.98
                    if pattern in {"volatile", "cold_start"}
                    else 0.95,
                    "review_period_days": 7,
                    "replenishment_mode": "purchase"
                    if item_id % 2
                    else "transfer",
                }
            )
    return pd.DataFrame(rows)


def build_demand_events() -> pd.DataFrame:
    """Describe the business events encoded in the demand table."""

    return pd.DataFrame(
        [
            {
                "event_id": "promotion_1002",
                "event_type": "promotion",
                "item_id": 1002,
                "store_code": "all",
                "start_date": "2025-02-15",
                "end_date": "2025-02-19",
                "expected_effect": "demand uplift",
            },
            {
                "event_id": "promotion_1005",
                "event_type": "promotion",
                "item_id": 1005,
                "store_code": "all",
                "start_date": "2025-04-01",
                "end_date": "2025-04-05",
                "expected_effect": "demand uplift",
            },
            {
                "event_id": "stockout_1005_2",
                "event_type": "stockout",
                "item_id": 1005,
                "store_code": "2",
                "start_date": "2025-04-11",
                "end_date": "2025-04-13",
                "expected_effect": "observed sales lower than latent demand",
            },
            {
                "event_id": "launch_1006",
                "event_type": "new_product_launch",
                "item_id": 1006,
                "store_code": "all",
                "start_date": "2025-05-01",
                "end_date": "2025-05-01",
                "expected_effect": "cold-start history begins",
            },
            {
                "event_id": "promotion_1006",
                "event_type": "promotion",
                "item_id": 1006,
                "store_code": "all",
                "start_date": "2025-05-26",
                "end_date": "2025-05-30",
                "expected_effect": "new-product demand uplift",
            },
        ]
    )


def main() -> int:
    """Write all tables and their provenance metadata."""

    OUTPUT.mkdir(parents=True, exist_ok=True)
    tables = {
        "demand_history.csv": build_demand_history(),
        "item_master.csv": build_item_master(),
        "inventory_snapshot.csv": build_inventory_snapshot(),
        "replenishment_policy.csv": build_replenishment_policy(),
        "demand_events.csv": build_demand_events(),
    }
    for name, frame in tables.items():
        frame.to_csv(OUTPUT / name, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "1.0",
        "dataset_name": "Synthetic multi-item multi-warehouse inventory planning demo",
        "source_type": "deterministic_synthetic",
        "license": "MIT project example",
        "generated_by": "scripts/generate_business_demo.py",
        "generated_at": "2026-07-16",
        "contains_third_party_raw_records": False,
        "inspired_by": [
            "AWS Supply Chain Demand Planning data entities",
            "Microsoft Forecast-to-plan business process",
            "Oracle Inventory Policy Planning",
            "Cainiao demand forecasting and warehouse allocation field semantics",
        ],
        "tables": {
            name: {"rows": len(frame), "columns": list(frame.columns)}
            for name, frame in tables.items()
        },
        "limitations": [
            "Values are synthetic and must not be interpreted as real commercial performance.",
            "The forecasting workflow consumes demand_history.csv; other tables document downstream replenishment inputs.",
        ],
    }
    (OUTPUT / "source_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "Generated business demo:",
        ", ".join(f"{name}={len(frame)}" for name, frame in tables.items()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
