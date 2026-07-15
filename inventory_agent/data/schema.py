"""Canonical schema for the headerless Cainiao Part II CSV files."""

from __future__ import annotations

ID_COLUMNS = ["date", "item_id", "cate_id", "cate_level_id", "brand_id", "supplier_id"]

BEHAVIOR_COLUMNS = [
    "pv_ipv",
    "pv_uv",
    "cart_ipv",
    "cart_uv",
    "collect_uv",
    "num_gmv",
    "amt_gmv",
    "qty_gmv",
    "unum_gmv",
    "amt_alipay",
    "num_alipay",
    "qty_alipay",
    "unum_alipay",
    "ztc_pv_ipv",
    "tbk_pv_ipv",
    "ss_pv_ipv",
    "jhs_pv_ipv",
    "ztc_pv_uv",
    "tbk_pv_uv",
    "ss_pv_uv",
    "jhs_pv_uv",
    "num_alipay_njhs",
    "amt_alipay_njhs",
    "qty_alipay_njhs",
    "unum_alipay_njhs",
]

NATIONAL_COLUMNS = ID_COLUMNS + BEHAVIOR_COLUMNS
STORE_COLUMNS = ["date", "item_id", "store_code"] + ID_COLUMNS[2:] + BEHAVIOR_COLUMNS
TARGET_COLUMN = "qty_alipay_njhs"
NATIONAL_SCOPE = "all"
COST_COLUMNS = ["item_id", "store_code", "cost_pair"]

# Competition semantics from the published evaluation formula:
# A * max(actual demand - target inventory, 0) +
# B * max(target inventory - actual demand, 0).
COST_A_COLUMN = "understock_cost"
COST_B_COLUMN = "overstock_cost"

ZIP_MEMBERS = {
    "national": "item_feature2.csv",
    "store": "item_store_feature2.csv",
    "cost": "config2.csv",
}
