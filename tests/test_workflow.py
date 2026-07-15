from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inventory_agent.codegen.validator import CodeValidationResult
from inventory_agent.config import Settings
from inventory_agent.data.schema import NATIONAL_COLUMNS, STORE_COLUMNS, TARGET_COLUMN
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


class _AlwaysInvalidValidator:
    def validate(self, path: Path) -> CodeValidationResult:
        del path
        return CodeValidationResult(False, {}, ("runtime: forced failure",))


def test_end_to_end_mock_workflow(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=140, freq="D")
    data = pd.DataFrame(
        {
            "date": dates,
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 20),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天需求",
        data_path,
        tmp_path / "runs",
    )
    assert result["code_validation"].valid
    assert Path(result["report_paths"]["json"]).exists()
    assert Path(result["report_paths"]["markdown"]).exists()
    assert (tmp_path / "knowledge.graphml").exists()
    assert (tmp_path / "knowledge.html").exists()
    assert result["report"]["validation_profile"]["name"] == "inventory_target"


def test_end_to_end_raw_directory_nationwide_uses_competition_costs(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    national_rows = []
    store_rows = []
    for index, date in enumerate(dates):
        national = [0] * len(NATIONAL_COLUMNS)
        national[NATIONAL_COLUMNS.index("date")] = int(date.strftime("%Y%m%d"))
        national[NATIONAL_COLUMNS.index("item_id")] = 42
        national[NATIONAL_COLUMNS.index(TARGET_COLUMN)] = index % 7 + 1
        national_rows.append(national)

        store = [0] * len(STORE_COLUMNS)
        store[STORE_COLUMNS.index("date")] = int(date.strftime("%Y%m%d"))
        store[STORE_COLUMNS.index("item_id")] = 42
        store[STORE_COLUMNS.index("store_code")] = 1
        store[STORE_COLUMNS.index(TARGET_COLUMN)] = index % 7 + 1
        store_rows.append(store)

    pd.DataFrame(national_rows).to_csv(
        tmp_path / "item_feature2.csv", index=False, header=False
    )
    pd.DataFrame(store_rows).to_csv(
        tmp_path / "item_store_feature2.csv", index=False, header=False
    )
    pd.DataFrame([[42, "all", "3_7"], [42, "1", "2_5"]]).to_csv(
        tmp_path / "config2.csv", index=False, header=False
    )

    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    result = workflow.run(
        "为商品 42 预测全国未来14天目标库存",
        tmp_path,
        tmp_path / "runs",
    )
    assert result["benchmark"]["store_code"] == "all"
    assert result["benchmark"]["evaluation_unit"] == "horizon_total"
    assert result["benchmark"]["costs"]["understock_cost"] == 3.0
    assert result["benchmark"]["costs"]["overstock_cost"] == 7.0
    assert result["benchmark"]["target_inventory"] >= 0

    warehouse_result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天目标库存",
        tmp_path,
        tmp_path / "runs",
    )
    assert warehouse_result["benchmark"]["store_code"] == "1"
    assert warehouse_result["benchmark"]["costs"]["understock_cost"] == 2.0
    assert warehouse_result["benchmark"]["costs"]["overstock_cost"] == 5.0


def test_failed_workflow_records_two_repairs_and_failure_experience(tmp_path: Path):
    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=70, freq="D"),
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 10),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    knowledge_path = tmp_path / "knowledge.json"
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=knowledge_path,
    )
    workflow.validator = _AlwaysInvalidValidator()

    with pytest.raises(RuntimeError, match="failed after repair budget"):
        workflow.run(
            "为商品 42 在仓库 1 预测未来14天目标库存",
            data_path,
            tmp_path / "runs",
        )

    saved = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=knowledge_path,
    ).knowledge
    failures = [
        attributes
        for _, attributes in saved.graph.nodes(data=True)
        if attributes.get("type") == "ValidationRun"
    ]
    repairs = [
        attributes["description"]
        for _, attributes in saved.graph.nodes(data=True)
        if attributes.get("type") == "RepairStrategy"
    ]
    assert failures[0]["status"] == "failure"
    assert "第 1 轮修复" in repairs[0]
    assert "第 2 轮修复" in repairs[0]
