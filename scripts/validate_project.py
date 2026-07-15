"""One-command project validation used before submission."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from inventory_agent.config import Settings
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run([sys.executable, "-m", "pytest"])
    run([sys.executable, "-m", "ruff", "check", "inventory_agent", "tests", "scripts"])
    with tempfile.TemporaryDirectory(prefix="inventory-agent-validation-") as temp:
        output = Path(temp)
        result = InventoryCapabilityWorkflow(
            settings=Settings(llm_mode="mock"),
            knowledge_path=output / "knowledge.json",
        ).run(
            "为商品 3424 在仓库 1 预测未来14天需求",
            ROOT / "examples/data/cainiao_demo.csv",
            output / "runs",
        )
        if not result["code_validation"].valid:
            raise RuntimeError("Generated capability did not pass validation")
        if not result["code_validation"].checks.get("stability"):
            raise RuntimeError("Generated capability stability check did not run")
        graph_html = output / "knowledge.html"
        if not graph_html.exists() or "库存算法能力知识图谱" not in graph_html.read_text(
            encoding="utf-8"
        ):
            raise RuntimeError("Knowledge graph HTML visualization was not generated")
        print(
            "E2E OK:",
            result["selected_model"],
            f"target_inventory={result['benchmark']['target_inventory']:.2f}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
