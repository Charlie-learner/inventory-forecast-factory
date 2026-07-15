import pandas as pd
import pytest

from inventory_agent.data.panel import demand_series, profile_series


def test_demand_series_fills_missing_dates_with_zero():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-03"]),
            "item_id": [1, 1],
            "store_code": [2, 2],
            "qty_alipay_njhs": [3, 5],
        }
    )
    series = demand_series(frame, 1, 2)
    assert series.tolist() == [3.0, 0.0, 5.0]


def test_profile_detects_intermittent_demand():
    profile = profile_series(pd.Series([0, 0, 0, 4, 0, 2]))
    assert profile["demand_type"] == "intermittent"
    assert profile["zero_ratio"] == 4 / 6


def test_national_series_without_store_column_uses_global_calendar():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "item_id": [1, 2, 1],
            "qty_alipay_njhs": [3, 9, 5],
        }
    )
    series = demand_series(frame, 1, "all")
    assert series.tolist() == [3.0, 0.0, 5.0]


def test_configured_missing_store_series_can_fall_back_to_zeros():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-03"]),
            "item_id": [1, 1],
            "store_code": [1, 1],
            "qty_alipay_njhs": [3, 5],
        }
    )
    series = demand_series(frame, 2, 3, allow_missing=True)
    assert series.tolist() == [0.0, 0.0, 0.0]


def test_nationwide_request_does_not_sum_warehouse_rows():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "item_id": [1, 1],
            "store_code": [1, 2],
            "qty_alipay_njhs": [3, 5],
        }
    )
    with pytest.raises(ValueError, match="No observations"):
        demand_series(frame, 1, "all")
