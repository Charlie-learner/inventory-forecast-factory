# Cainiao Part II data schema

The supplied competition archive contains headerless CSV files. This project assigns the
canonical field names used by the original Cainiao demand forecasting task.

## Files

- `item_feature2.csv`: daily national item features, 31 columns.
- `item_store_feature2.csv`: daily item/warehouse features, 32 columns.
- `config2.csv`: item/location cost pairs used for cost-sensitive evaluation.
- The competition documentation separately defines a `sample_submission.csv` template. The
  three uploaded training/configuration files do not include a matching template, so this
  project does not synthesize one or silently reuse an unrelated download.

The primary target is `qty_alipay_njhs`, the paid item quantity excluding Juhuasuan activity.
The target horizon is 14 days.

## Identifiers

| Field | Meaning |
|---|---|
| `date` | Observation date (`YYYYMMDD` in the raw file) |
| `item_id` | Anonymized product identifier |
| `store_code` | Warehouse/region code, 1-5; national data has no store column |
| `cate_id` | Category identifier |
| `cate_level_id` | Category level identifier |
| `brand_id` | Anonymized brand identifier |
| `supplier_id` | Anonymized supplier identifier |

Behavioral columns cover page views, visitors, carts, collections, GMV, Alipay activity,
traffic sources, and their non-Juhuasuan counterparts. The full ordered schema lives in
`inventory_agent/data/schema.py` and is validated against the raw column count on load.

The two values in `config2.csv` follow the published competition formula:

- `cost_a` / `understock_cost`: shortage cost, applied to `max(D - T, 0)`.
- `cost_b` / `overstock_cost`: excess-inventory cost, applied to `max(T - D, 0)`.

`D` and `T` are totals for the future 14-day horizon, not individual daily values. See
[inventory_evaluation.md](inventory_evaluation.md) for the complete output and metric contract.

## Extracted directory layout

The loader accepts either the original ZIP or an extracted directory containing:

```text
data/
├── item_feature2.csv
├── item_store_feature2.csv
└── config2.csv
```

These large raw CSV files are ignored by Git. The checked-in demo remains the small, headed
panel file under `examples/data/`.
