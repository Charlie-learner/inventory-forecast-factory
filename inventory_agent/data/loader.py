"""Load and normalize Cainiao Part II data directly from its ZIP archive."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from inventory_agent.data.schema import (
    NATIONAL_COLUMNS,
    STORE_COLUMNS,
    TARGET_COLUMN,
    ZIP_MEMBERS,
)


@dataclass
class CainiaoDataBundle:
    national: pd.DataFrame
    store: pd.DataFrame
    costs: pd.DataFrame


class CainiaoZipLoader:
    """Reader for the headerless competition archive supplied with the exercise."""

    def __init__(self, zip_path: str | Path):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Cainiao ZIP not found: {self.zip_path}")

    @staticmethod
    def _find_member(archive: ZipFile, suffix: str) -> str:
        matches = [name for name in archive.namelist() if name.endswith(suffix) and "__MACOSX" not in name]
        if len(matches) != 1:
            raise ValueError(f"Expected one ZIP member ending with {suffix!r}, found {matches}")
        return matches[0]

    @staticmethod
    def _normalize_features(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        if frame.shape[1] != len(columns):
            raise ValueError(f"Expected {len(columns)} columns, got {frame.shape[1]}")
        result = frame.copy()
        result.columns = columns
        result["date"] = pd.to_datetime(result["date"].astype(str), format="%Y%m%d", errors="raise")
        result[TARGET_COLUMN] = pd.to_numeric(result[TARGET_COLUMN], errors="raise").clip(lower=0)
        return result.sort_values([c for c in ["item_id", "store_code", "date"] if c in result.columns])

    def load_national(self) -> pd.DataFrame:
        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["national"])
            raw = pd.read_csv(archive.open(member), header=None)
        return self._normalize_features(raw, NATIONAL_COLUMNS)

    def load_store(self) -> pd.DataFrame:
        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["store"])
            raw = pd.read_csv(archive.open(member), header=None)
        return self._normalize_features(raw, STORE_COLUMNS)

    def load_costs(self) -> pd.DataFrame:
        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["cost"])
            raw = pd.read_csv(archive.open(member), header=None, names=["item_id", "store_code", "cost_pair"])
        costs = raw["cost_pair"].astype(str).str.split("_", n=1, expand=True)
        if costs.shape[1] != 2:
            raise ValueError("config2.csv cost_pair must contain two underscore-separated costs")
        raw["cost_a"] = pd.to_numeric(costs[0], errors="raise")
        raw["cost_b"] = pd.to_numeric(costs[1], errors="raise")
        return raw

    def load(self) -> CainiaoDataBundle:
        return CainiaoDataBundle(
            national=self.load_national(),
            store=self.load_store(),
            costs=self.load_costs(),
        )

    def prepare_sample(self, output_path: str | Path, item_limit: int = 20) -> pd.DataFrame:
        """Create a deterministic, Git-friendly panel sample for local demos and tests."""
        if item_limit <= 0:
            raise ValueError("item_limit must be positive")
        store = self.load_store()
        counts = store.groupby("item_id", sort=True).size().sort_values(ascending=False)
        selected = sorted(counts.head(item_limit).index.tolist())
        sample = store[store["item_id"].isin(selected)].copy()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        sample.to_csv(output, index=False)
        return sample

