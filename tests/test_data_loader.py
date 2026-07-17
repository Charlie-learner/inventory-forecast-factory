from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from inventory_agent.data.costs import resolve_inventory_costs
from inventory_agent.data.loader import (
    CainiaoDirectoryLoader,
    CainiaoZipLoader,
    inspect_csv,
    load_cost_csv,
    load_panel_csv,
    normalize_mapped_panel_csv,
)
from inventory_agent.data.schema import (
    COST_A_COLUMN,
    COST_B_COLUMN,
    NATIONAL_COLUMNS,
    STORE_COLUMNS,
    TARGET_COLUMN,
)


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
    assert bundle.costs.iloc[0][COST_A_COLUMN] == 2.5
    assert bundle.costs.iloc[0][COST_B_COLUMN] == 3.5


def test_directory_loader_and_cost_semantics(tmp_path: Path):
    pd.DataFrame([_row(len(NATIONAL_COLUMNS), NATIONAL_COLUMNS.index(TARGET_COLUMN))]).to_csv(
        tmp_path / "item_feature2.csv", index=False, header=False
    )
    pd.DataFrame([_row(len(STORE_COLUMNS), STORE_COLUMNS.index(TARGET_COLUMN))]).to_csv(
        tmp_path / "item_store_feature2.csv", index=False, header=False
    )
    pd.DataFrame([[1, "all", "2.5_3.5"]]).to_csv(
        tmp_path / "config2.csv", index=False, header=False
    )
    bundle = CainiaoDirectoryLoader(tmp_path).load()
    weights = resolve_inventory_costs(bundle.costs, 1, "all")
    assert weights.understock_cost == 2.5
    assert weights.overstock_cost == 3.5
    assert weights.critical_fractile == pytest.approx(2.5 / 6.0)


def test_loader_rejects_wrong_column_count(tmp_path: Path):
    archive_path = tmp_path / "bad.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("item_feature2.csv", "20151227,1\n")
    with pytest.raises(ValueError, match="Expected 31 columns"):
        CainiaoZipLoader(archive_path).load_national()


def test_directory_loader_rejects_non_finite_costs(tmp_path: Path):
    pd.DataFrame([[1, "all", "inf_3.5"]]).to_csv(
        tmp_path / "config2.csv", index=False, header=False
    )
    with pytest.raises(ValueError, match="finite and non-negative"):
        CainiaoDirectoryLoader(tmp_path).load_costs()


def test_user_panel_csv_normalizes_common_column_aliases(tmp_path: Path):
    source = tmp_path / "user_sales.csv"
    pd.DataFrame(
        {
            "ds": ["2026-01-01", "2026-01-02"],
            "sku_id": [101, 101],
            "warehouse_id": ["WH-A", "WH-A"],
            "sales": [3, 5],
        }
    ).to_csv(source, index=False)

    frame = load_panel_csv(source)

    assert {"date", "item_id", "store_code", TARGET_COLUMN} <= set(frame.columns)
    assert frame["item_id"].tolist() == [101, 101]
    assert frame["store_code"].tolist() == ["WH-A", "WH-A"]
    assert frame[TARGET_COLUMN].tolist() == [3, 5]


def test_headerless_cainiao_national_csv_is_detected_as_nationwide_panel(
    tmp_path: Path,
):
    source = tmp_path / "item_feature2.csv"
    pd.DataFrame(
        [
            _row(
                len(NATIONAL_COLUMNS),
                NATIONAL_COLUMNS.index(TARGET_COLUMN),
                date=20151226,
            ),
            _row(
                len(NATIONAL_COLUMNS),
                NATIONAL_COLUMNS.index(TARGET_COLUMN),
                date=20151227,
            ),
        ]
    ).to_csv(source, index=False, header=False)

    frame = load_panel_csv(source)

    assert list(frame.columns[:3]) == ["date", "item_id", "store_code"]
    assert frame["store_code"].tolist() == ["all", "all"]
    assert frame[TARGET_COLUMN].tolist() == [7, 7]
    assert len(frame) == 2


def test_headerless_cainiao_store_csv_is_detected_with_store_codes(tmp_path: Path):
    source = tmp_path / "item_store_feature2.csv"
    pd.DataFrame(
        [
            _row(
                len(STORE_COLUMNS),
                STORE_COLUMNS.index(TARGET_COLUMN),
                date=20151226,
            ),
            _row(
                len(STORE_COLUMNS),
                STORE_COLUMNS.index(TARGET_COLUMN),
                date=20151227,
            ),
        ]
    ).to_csv(source, index=False, header=False)

    frame = load_panel_csv(source)

    assert "store_code" in frame.columns
    assert frame[TARGET_COLUMN].tolist() == [7, 7]
    assert len(frame) == 2


def test_standalone_cost_config_is_recognized(tmp_path: Path):
    source = tmp_path / "config2.csv"
    pd.DataFrame([[3424, "all", "10.44_20.88"]]).to_csv(
        source, index=False, header=False
    )

    costs = load_cost_csv(source)

    assert costs.iloc[0]["item_id"] == 3424
    assert costs.iloc[0]["store_code"] == "all"
    assert costs.iloc[0][COST_A_COLUMN] == 10.44
    assert costs.iloc[0][COST_B_COLUMN] == 20.88


def test_user_panel_csv_normalizes_common_chinese_column_aliases(tmp_path: Path):
    source = tmp_path / "业务销量.csv"
    pd.DataFrame(
        {
            "日期": ["2026-01-01", "2026-01-02"],
            "商品编号": [1001, 1001],
            "仓库编号": ["WH-A", "WH-A"],
            "销量": [3, 5],
        }
    ).to_csv(source, index=False)

    frame = load_panel_csv(source)

    assert frame["item_id"].tolist() == [1001, 1001]
    assert frame["store_code"].tolist() == ["WH-A", "WH-A"]
    assert frame[TARGET_COLUMN].tolist() == [3, 5]


def test_unrecognized_csv_can_be_inspected_and_mapped(tmp_path: Path):
    source = tmp_path / "custom.csv"
    output = tmp_path / "normalized.csv"
    pd.DataFrame(
        {
            "period": ["2026-01-01", "2026-01-02"],
            "material": [1001, 1001],
            "site": ["WH-A", "WH-A"],
            "units": [3, 5],
        }
    ).to_csv(source, index=False)

    inspection = inspect_csv(source)
    frame = normalize_mapped_panel_csv(
        source,
        output,
        {
            "date": "period",
            "item_id": "material",
            "store_code": "site",
            TARGET_COLUMN: "units",
        },
    )

    assert inspection["columns"] == ["period", "material", "site", "units"]
    assert inspection["preview"][0]["material"] == 1001
    assert output.exists()
    assert frame[TARGET_COLUMN].tolist() == [3, 5]


def test_alphanumeric_item_ids_return_actionable_error(tmp_path: Path):
    source = tmp_path / "alpha-sku.csv"
    pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "item_id": ["SKU-A"],
            "sales": [3],
        }
    ).to_csv(source, index=False)

    with pytest.raises(ValueError, match="商品 ID 当前必须是整数"):
        load_panel_csv(source)
