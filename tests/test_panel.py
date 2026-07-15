import pandas as pd

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

