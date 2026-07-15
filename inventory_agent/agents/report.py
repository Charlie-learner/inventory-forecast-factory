"""Create transparent JSON and Markdown validation reports."""

from __future__ import annotations

import json
from pathlib import Path

from inventory_agent.llm.client import LLMClient, MockLLMClient


class ReportAgent:
    """Render machine-readable and human-readable validation reports."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    def create(self, payload: dict, output_dir: str | Path) -> dict[str, str]:
        """Write JSON and Markdown reports and return their file paths."""

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "validation_report.json"
        markdown_path = output / "validation_report.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        llm_summary = self.llm.complete(
            "你是库存预测验证报告 Agent。简洁说明模型选择、主要指标、风险和补货使用边界。",
            json.dumps(payload, ensure_ascii=False, default=str),
        )
        candidates = payload["benchmark"]["candidates"]
        costs = payload["benchmark"]["costs"]
        rows = [
            "| 模型 | WAPE | sMAPE | Bias | 平均单折库存成本 |",
            "|---|---:|---:|---:|---:|",
        ]
        for candidate in candidates:
            metrics = candidate["metrics"]
            rows.append(
                f"| {candidate['model']} | {metrics['wape']:.4f} | {metrics['smape']:.4f} | "
                f"{metrics['bias']:.4f} | {metrics['inventory_cost']:.2f} |"
            )
        markdown = "\n".join(
            [
                "# 库存预测能力验证报告",
                "",
                f"- 能力描述：{payload['request']['description']}",
                f"- 商品：{payload['request']['item_id']}",
                f"- 仓库：{payload['request']['store_code']}",
                f"- 预测周期：{payload['request']['horizon']} 天",
                f"- 需求类型：{payload['profile']['demand_type']}",
                f"- 历史状态：{payload['profile']['history_status']}",
                f"- 选中模型：{payload['benchmark']['selected_model']}",
                f"- 未来 {payload['request']['horizon']} 天目标库存："
                f"{payload['benchmark']['target_inventory']:.2f}",
                f"- 成本 A（补少/缺货）：{costs['understock_cost']:.2f}",
                f"- 成本 B（补多/积压）：{costs['overstock_cost']:.2f}",
                f"- 成本来源：{costs['source']}",
                f"- 成本口径：{payload['benchmark']['evaluation_unit']}",
                "",
                "## 候选模型验证",
                "",
                *rows,
                "",
                "## 生成代码验证",
                "",
                f"- 生成方式：{payload['generated']['generation_mode']}",
                f"- 语法、导入、接口、运行检查：{payload['code_validation']['checks']}",
                f"- 修复次数：{len(payload['repairs'])}",
                "",
                "## Agent 总结",
                "",
                llm_summary,
                "",
                "## 使用边界",
                "",
                "目标库存 T 是预测周期内非聚划算需求总量。实际下单量仍需结合现货、在途库存、提前期和安全库存。",
            ]
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}
