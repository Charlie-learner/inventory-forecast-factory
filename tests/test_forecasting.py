import numpy as np
import pandas as pd
import pytest

from inventory_agent.forecasting.models import CrostonModel, RidgeLagModel, SeasonalNaiveModel
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.validation.backtest import RollingBacktester
from inventory_agent.validation.metrics import forecast_metrics


def test_seasonal_naive_repeats_week():
    series = pd.Series(np.arange(1, 15, dtype=float))
    prediction = SeasonalNaiveModel(period=7).predict(series, horizon=10)
    assert prediction.tolist() == [8, 9, 10, 11, 12, 13, 14, 8, 9, 10]


def test_croston_handles_all_zero_series():
    prediction = CrostonModel().predict(pd.Series(np.zeros(40)), 14)
    assert np.all(prediction == 0)


def test_ridge_forecast_is_non_negative():
    prediction = RidgeLagModel(lags=7).predict(pd.Series(np.arange(50)), 14)
    assert len(prediction) == 14
    assert np.all(prediction >= 0)


def test_inventory_cost_penalizes_under_forecast():
    metrics = forecast_metrics(
        np.array([10.0]),
        np.array([6.0]),
        overstock_cost=1.0,
        understock_cost=3.0,
    )
    assert metrics["inventory_cost"] == 12.0
    assert metrics["bias"] == -4.0


def test_rolling_backtest_selects_result():
    series = pd.Series(np.tile([1, 2, 3, 4, 5, 6, 7], 20), dtype=float)
    registry = default_registry()
    backtester = RollingBacktester(horizon=14, folds=3, min_history=28)
    results = [backtester.evaluate(registry.create(name), series) for name in registry.names()]
    selected = backtester.select_best(results)
    assert selected.model in registry.names()
    assert selected.folds == 3


def test_backtest_rejects_short_history():
    with pytest.raises(ValueError, match="Need at least"):
        RollingBacktester(horizon=14, min_history=28).evaluate(
            SeasonalNaiveModel(), pd.Series([1, 2, 3])
        )

