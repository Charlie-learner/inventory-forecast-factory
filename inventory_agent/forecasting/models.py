"""Lightweight forecasting models suitable for a reproducible local demo."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from inventory_agent.forecasting.base import ForecastModel


class LastValueModel(ForecastModel):
    name = "last_value"

    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        clean = self.validate_input(history, horizon)
        return np.repeat(clean.iloc[-1], horizon)


class MovingAverageModel(ForecastModel):
    name = "moving_average"

    def __init__(self, window: int = 14):
        self.window = window

    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        clean = self.validate_input(history, horizon)
        window = min(self.window, len(clean))
        return np.repeat(float(clean.iloc[-window:].mean()), horizon)


class SeasonalNaiveModel(ForecastModel):
    name = "seasonal_naive"

    def __init__(self, period: int = 7):
        self.period = period

    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        clean = self.validate_input(history, horizon)
        if len(clean) < self.period:
            return np.repeat(float(clean.mean()), horizon)
        pattern = clean.iloc[-self.period :].to_numpy(dtype=float)
        return np.resize(pattern, horizon).clip(min=0)


class CrostonModel(ForecastModel):
    """Classic Croston forecast for intermittent demand."""

    name = "croston"

    def __init__(self, alpha: float = 0.1):
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha

    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        clean = self.validate_input(history, horizon)
        values = clean.to_numpy(dtype=float)
        nonzero_positions = np.flatnonzero(values > 0)
        if len(nonzero_positions) == 0:
            return np.zeros(horizon)

        first = int(nonzero_positions[0])
        demand_estimate = values[first]
        interval_estimate = float(first + 1)
        interval = 1
        for value in values[first + 1 :]:
            if value > 0:
                demand_estimate += self.alpha * (value - demand_estimate)
                interval_estimate += self.alpha * (interval - interval_estimate)
                interval = 1
            else:
                interval += 1
        forecast = demand_estimate / max(interval_estimate, 1e-12)
        return np.repeat(max(float(forecast), 0.0), horizon)


class RidgeLagModel(ForecastModel):
    """Autoregressive ridge model using leakage-safe lag features."""

    name = "ridge_lag"

    def __init__(self, lags: int = 14, alpha: float = 1.0):
        self.lags = lags
        self.alpha = alpha

    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        clean = self.validate_input(history, horizon)
        if len(clean) <= self.lags + 2:
            return MovingAverageModel(window=min(14, len(clean))).predict(clean, horizon)

        values = clean.to_numpy(dtype=float)
        features = np.array([values[i - self.lags : i] for i in range(self.lags, len(values))])
        target = values[self.lags :]
        model = Ridge(alpha=self.alpha)
        model.fit(features, target)

        buffer = values.tolist()
        predictions: list[float] = []
        for _ in range(horizon):
            feature = np.asarray(buffer[-self.lags :], dtype=float).reshape(1, -1)
            prediction = max(float(model.predict(feature)[0]), 0.0)
            predictions.append(prediction)
            buffer.append(prediction)
        return np.asarray(predictions)

