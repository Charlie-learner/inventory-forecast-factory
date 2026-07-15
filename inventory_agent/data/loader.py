"""Load and normalize Cainiao Part II data directly from its ZIP archive."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from inventory_agent.data.schema import (
    COST_A_COLUMN,
    COST_B_COLUMN,
    COST_COLUMNS,
    NATIONAL_COLUMNS,
    NATIONAL_SCOPE,
    STORE_COLUMNS,
    TARGET_COLUMN,
    ZIP_MEMBERS,
)


@dataclass
class CainiaoDataBundle:
    """Normalized national, warehouse, and inventory-cost tables."""

    national: pd.DataFrame
    store: pd.DataFrame
    costs: pd.DataFrame


def _normalize_features(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Apply the canonical schema and validate feature-table keys."""

    if frame.shape[1] != len(columns):
        raise ValueError(f"Expected {len(columns)} columns, got {frame.shape[1]}")
    result = frame.copy()
    result.columns = columns
    result["date"] = pd.to_datetime(result["date"].astype(str), format="%Y%m%d", errors="raise")
    result[TARGET_COLUMN] = pd.to_numeric(result[TARGET_COLUMN], errors="raise").clip(lower=0)
    keys = [column for column in ["item_id", "store_code", "date"] if column in result.columns]
    if result.duplicated(keys).any():
        raise ValueError(f"Duplicate feature keys detected for {keys}")
    return result.sort_values(keys)


def _normalize_costs(frame: pd.DataFrame) -> pd.DataFrame:
    """Parse and validate the official A_B inventory-cost pairs."""

    if frame.shape[1] != len(COST_COLUMNS):
        raise ValueError(f"Expected {len(COST_COLUMNS)} cost columns, got {frame.shape[1]}")
    result = frame.copy()
    result.columns = COST_COLUMNS
    result["store_code"] = result["store_code"].astype(str).str.strip().str.lower()
    pairs = result["cost_pair"].astype(str).str.split("_", n=1, expand=True)
    if pairs.shape[1] != 2 or pairs.isna().any().any():
        raise ValueError("config2.csv cost_pair must contain two underscore-separated costs")
    result["cost_a"] = pd.to_numeric(pairs[0], errors="raise")
    result["cost_b"] = pd.to_numeric(pairs[1], errors="raise")
    result[COST_A_COLUMN] = result["cost_a"]
    result[COST_B_COLUMN] = result["cost_b"]
    cost_values = result[[COST_A_COLUMN, COST_B_COLUMN]].to_numpy(dtype=float)
    if not np.isfinite(cost_values).all() or (cost_values < 0).any():
        raise ValueError("Inventory costs must be finite and non-negative")
    if result.duplicated(["item_id", "store_code"]).any():
        raise ValueError("Duplicate item/store rows in config2.csv")
    return result.sort_values(["item_id", "store_code"])


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
        return _normalize_features(frame, columns)

    def load_national(self) -> pd.DataFrame:
        """Load and normalize the nationwide item feature table."""

        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["national"])
            raw = pd.read_csv(archive.open(member), header=None)
        return self._normalize_features(raw, NATIONAL_COLUMNS)

    def load_store(self) -> pd.DataFrame:
        """Load and normalize the item-by-warehouse feature table."""

        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["store"])
            raw = pd.read_csv(archive.open(member), header=None)
        return self._normalize_features(raw, STORE_COLUMNS)

    def load_costs(self) -> pd.DataFrame:
        """Load and normalize inventory-cost configuration."""

        with ZipFile(self.zip_path) as archive:
            member = self._find_member(archive, ZIP_MEMBERS["cost"])
            raw = pd.read_csv(archive.open(member), header=None)
        return _normalize_costs(raw)

    def load(self) -> CainiaoDataBundle:
        """Load all three source tables as one data bundle."""

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


class CainiaoDirectoryLoader:
    """Load the three extracted, headerless competition CSV files from a directory."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        if not self.data_dir.is_dir():
            raise NotADirectoryError(f"Cainiao data directory not found: {self.data_dir}")

    def _path(self, kind: str) -> Path:
        path = self.data_dir / ZIP_MEMBERS[kind]
        if not path.is_file():
            raise FileNotFoundError(f"Cainiao data file not found: {path}")
        return path

    def load_national(self) -> pd.DataFrame:
        """Load nationwide features from the extracted data directory."""

        return _normalize_features(pd.read_csv(self._path("national"), header=None), NATIONAL_COLUMNS)

    def load_store(self) -> pd.DataFrame:
        """Load warehouse features from the extracted data directory."""

        return _normalize_features(pd.read_csv(self._path("store"), header=None), STORE_COLUMNS)

    def load_costs(self) -> pd.DataFrame:
        """Load inventory costs from the extracted data directory."""

        return _normalize_costs(pd.read_csv(self._path("cost"), header=None))

    def load(self) -> CainiaoDataBundle:
        """Load all extracted source tables as one data bundle."""

        return CainiaoDataBundle(self.load_national(), self.load_store(), self.load_costs())


def create_cainiao_loader(source: str | Path) -> CainiaoZipLoader | CainiaoDirectoryLoader:
    """Create the loader matching an extracted directory or ZIP source."""

    path = Path(source)
    if path.is_dir():
        return CainiaoDirectoryLoader(path)
    return CainiaoZipLoader(path)


def load_location_frame(source: str | Path, store_code: int | str) -> pd.DataFrame:
    """Load nationwide data for ``all`` or warehouse data for locations 1-5."""

    loader = create_cainiao_loader(source)
    location = str(store_code).strip().lower()
    if location in {NATIONAL_SCOPE, "全国"}:
        frame = loader.load_national()
        frame.insert(2, "store_code", NATIONAL_SCOPE)
        return frame
    return loader.load_store()
