# Cainiao Part II data schema

The supplied competition archive contains headerless CSV files. This project assigns the
canonical field names used by the original Cainiao demand forecasting task.

## Files

- `item_feature2.csv`: daily national item features, 31 columns.
- `item_store_feature2.csv`: daily item/warehouse features, 32 columns.
- `config2.csv`: item/location cost pairs used for cost-sensitive evaluation.
- `sample_submission.csv`: 1,000 items at `all` and five warehouse locations.

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

The two values in `config2.csv` are deliberately named `cost_a` and `cost_b` until their
overstock/understock direction is verified against the original competition documentation.
This avoids silently reversing the business loss function.

