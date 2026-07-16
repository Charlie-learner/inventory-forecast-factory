"""Leakage-safe forecasting validation."""

from inventory_agent.validation.backtest import BacktestResult, RollingBacktester
from inventory_agent.validation.failures import FailureAnalysis, FailureAnalyzer
from inventory_agent.validation.metrics import MetricRegistry, default_metric_registry
from inventory_agent.validation.profiles import (
    ValidationProfile,
    ValidationProfileRegistry,
    default_validation_profiles,
)

__all__ = [
    "BacktestResult",
    "FailureAnalysis",
    "FailureAnalyzer",
    "MetricRegistry",
    "RollingBacktester",
    "ValidationProfile",
    "ValidationProfileRegistry",
    "default_metric_registry",
    "default_validation_profiles",
]
