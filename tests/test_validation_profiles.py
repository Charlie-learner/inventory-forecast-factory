import pytest

from inventory_agent.validation.backtest import BacktestResult, RollingBacktester
from inventory_agent.validation.profiles import (
    ValidationProfile,
    ValidationProfileRegistry,
    default_validation_profiles,
)


def test_default_profiles_rank_different_task_objectives():
    profiles = default_validation_profiles()
    assert profiles.get("inventory_target").ranking_metrics[0] == "inventory_cost"
    assert profiles.get("demand_forecast").ranking_metrics[0] == "wape"
    intermittent = profiles.get("intermittent_demand")
    assert intermittent.ranking_metrics[0] == "mae"
    assert intermittent.folds == 4
    assert intermittent.min_history_days == 42

    low_cost = BacktestResult(
        "low_cost", 1, {"inventory_cost": 1.0, "wape": 0.5, "rmse": 5.0}, ()
    )
    high_accuracy = BacktestResult(
        "high_accuracy", 1, {"inventory_cost": 5.0, "wape": 0.1, "rmse": 1.0}, ()
    )
    results = [low_cost, high_accuracy]
    assert (
        RollingBacktester.select_best(
            results, profiles.get("inventory_target").ranking_metrics
        ).model
        == "low_cost"
    )
    assert (
        RollingBacktester.select_best(
            results, profiles.get("demand_forecast").ranking_metrics
        ).model
        == "high_accuracy"
    )


def test_validation_profile_registry_supports_plugins():
    registry = ValidationProfileRegistry()
    registry.register(ValidationProfile("custom", "smape", ("rmse",)))
    assert registry.get("custom").primary_metric == "smape"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ValidationProfile("custom", "wape", ()))
