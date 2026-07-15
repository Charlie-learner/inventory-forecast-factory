from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from inventory_agent.data.loader import CainiaoZipLoader
from inventory_agent.data.schema import NATIONAL_COLUMNS, STORE_COLUMNS, TARGET_COLUMN


def _row(width: int, target_index: int, date: int = 20151227) -> list[int]:
    values = list(range(width))
    values[0] = date
    values[target_index] = 7
    return values


@pytest.fixture
def tiny_zip(tmp_path: Path) -> Path:
    archive_path = tmp_path / "cainiao.zip"
    national = pd.DataFrame([_row(len(NATIONAL_COLUMNS), NATIONAL_COLUMNS.index(TARGET_COLUMN))])
    store = pd.DataFrame([_row(len(STORE_COLUMNS), STORE_COLUMNS.index(TARGET_COLUMN))])
    costs = pd.DataFrame([[1, "all", "2.5_3.5"]])
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("data/item_feature2.csv", national.to_csv(index=False, header=False))
        archive.writestr("data/item_store_feature2.csv", store.to_csv(index=False, header=False))
        archive.writestr("data/config2.csv", costs.to_csv(index=False, header=False))
    return archive_path


def test_loader_assigns_schema_and_parses_dates(tiny_zip: Path):
    bundle = CainiaoZipLoader(tiny_zip).load()
    assert list(bundle.national.columns) == NATIONAL_COLUMNS
    assert list(bundle.store.columns) == STORE_COLUMNS
    assert bundle.store.iloc[0][TARGET_COLUMN] == 7
    assert str(bundle.store.iloc[0]["date"].date()) == "2015-12-27"
    assert bundle.costs.iloc[0]["cost_a"] == 2.5
    assert bundle.costs.iloc[0]["cost_b"] == 3.5


def test_loader_rejects_wrong_column_count(tmp_path: Path):
    archive_path = tmp_path / "bad.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("item_feature2.csv", "20151227,1\n")
    with pytest.raises(ValueError, match="Expected 31 columns"):
        CainiaoZipLoader(archive_path).load_national()

