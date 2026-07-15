"""Rolling-origin backtesting and deterministic model selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from inventory_agent.forecasting.base import ForecastModel
from inventory_agent.validation.metrics import forecast_metrics


@dataclass(frozen=True)
class BacktestResult:
    model: str
    folds: int
    metrics: dict[str, float]
    fold_metrics: tuple[dict[str, float], ...]


class RollingBacktester:
    def __init__(self, horizon: int = 14, folds: int = 3, min_history: int = 28):
        if horizon <= 0 or folds <= 0 or min_history <= 0:
            raise ValueError("horizon, folds and min_history must be positive")
        self.horizon = horizon
        self.folds = folds
        self.min_history = min_history

    def evaluate(
        self,
        model: ForecastModel,
        series: pd.Series,
        overstock_cost: float = 1.0,
        understock_cost: float = 1.0,
    ) -> BacktestResult:
        clean = pd.to_numeric(series, errors="coerce").dropna().astype(float).clip(lower=0)
        required = self.min_history + self.horizon
        if len(clean) < required:
            raise ValueError(f"Need at least {required} observations, got {len(clean)}")

        available_folds = min(self.folds, (len(clean) - self.min_history) // self.horizon)
        fold_results: list[dict[str, float]] = []
        for fold_index in range(available_folds, 0, -1):
            test_end = len(clean) - (fold_index - 1) * self.horizon
            train_end = test_end - self.horizon
            train = clean.iloc[:train_end]
            actual = clean.iloc[train_end:test_end].to_numpy(dtype=float)
            prediction = model.predict(train, self.horizon)
            fold_results.append(
                forecast_metrics(actual, prediction, overstock_cost, understock_cost)
            )

        aggregated = {}
        for key in fold_results[0]:
            output_key = f"mean_{key}" if key in {"actual_total", "target_inventory"} else key
            aggregated[output_key] = float(np.mean([fold[key] for fold in fold_results]))
        return BacktestResult(model.name, available_folds, aggregated, tuple(fold_results))

    @staticmethod
    def select_best(results: list[BacktestResult]) -> BacktestResult:
        if not results:
            raise ValueError("At least one backtest result is required")
        return min(results, key=lambda item: (item.metrics["inventory_cost"], item.metrics["wape"], item.model))
