from pathlib import Path

import numpy as np
import pandas as pd

from inventory_agent.config import Settings
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


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

