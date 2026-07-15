"""Common forecast model contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


class ForecastModel(ABC):
    """Small, deterministic interface used by generated capability modules."""

    name: str

    @abstractmethod
    def predict(self, history: pd.Series, horizon: int) -> np.ndarray:
        """Return non-negative daily demand predictions."""

    @staticmethod
    def validate_input(history: pd.Series, horizon: int) -> pd.Series:
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        clean = pd.to_numeric(history, errors="coerce").dropna().astype(float)
        if clean.empty:
            raise ValueError("history must contain at least one numeric observation")
        return clean.clip(lower=0)


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    description: str
    suitable_for: tuple[str, ...]
    min_history: int
    dependencies: tuple[str, ...] = field(default_factory=tuple)

