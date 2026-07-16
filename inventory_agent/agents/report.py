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

        llm_response = self.llm.complete(
            "你是库存预测验证报告 Agent。简洁说明模型选择、主要指标、风险和补货使用边界。",
            json.dumps(payload, ensure_ascii=False, default=str),
        )
        try:
            llm_payload = json.loads(llm_response)
            llm_summary = str(llm_payload.get("summary", llm_response))
            summary_mode = str(llm_payload.get("mode", "api"))
        except (json.JSONDecodeError, AttributeError):
            llm_summary = llm_response.strip()
            summary_mode = "api"
        candidates = payload["benchmark"]["candidates"]
        costs = payload["benchmark"]["costs"]
        scanned_files = sum(
            int(report.get("files_scanned", 0))
            for report in payload["capability_extraction"].get("scan_reports", [])
        )
        failure_count = len(payload.get("failure_history", []))
        reused_experience_count = len(payload.get("repair_experience_used", []))
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
        code_rows = [
            "| 代码方案 | 回测选中 | 生成方式 | 代码验证 | 等价误差 | 文件 |",
            "|---|---|---|---|---:|---|",
        ]
        for solution in payload.get("candidate_code_solutions", []):
            validation = solution["code_validation"]
            generated = solution["generated"]
            code_rows.append(
                f"| {solution['model']} | {solution['selected']} | "
                f"{generated['generation_mode']} | {validation['valid']} | "
                f"{validation['equivalence_max_error']} | `{generated['path']}` |"
            )
        if len(code_rows) == 2:
            code_rows.append("| 未启用完整追踪 | - | - | - | - | - |")
        trace_path = (
            payload.get("execution_trace", {}).get("paths") or {}
        ).get("markdown")
        markdown = "\n".join(
            [
                "# 库存预测能力验证报告",
                "",
                f"- 能力描述：{payload['request']['description']}",
                f"- 商品：{payload['request']['item_id']}",
                f"- 仓库：{payload['request']['store_code']}",
                f"- 预测周期：{payload['request']['horizon']} 天",
                f"- 任务类型：{payload['request']['task_type']}",
                f"- 主验证指标：{payload['validation_profile']['primary_metric']}",
                f"- 需求类型：{payload['profile']['demand_type']}",
                f"- 历史状态：{payload['profile']['history_status']}",
                f"- 选中模型：{payload['benchmark']['selected_model']}",
                f"- 未来 {payload['request']['horizon']} 天目标库存："
                f"{payload['benchmark']['target_inventory']:.2f}",
                f"- 成本 A（补少/缺货）：{costs['understock_cost']:.2f}",
                f"- 成本 B（补多/积压）：{costs['overstock_cost']:.2f}",
                f"- 成本来源：{costs['source']}",
                f"- 成本口径：{payload['benchmark']['evaluation_unit']}",
                f"- 能力抽取数量：{payload['capability_extraction']['count']}",
                f"- 能力来源扫描文件数：{scanned_files}",
                f"- 能力来源：{payload['capability_spec']['source_ref'] or '内置能力图谱'}",
                "",
                "## 候选模型验证",
                "",
                *rows,
                "",
                "## 候选代码方案生成与比较",
                "",
                *code_rows,
                "",
                "## 生成代码验证",
                "",
                f"- 生成方式：{payload['generated']['generation_mode']}",
                f"- 能力规格哈希：{payload['generated']['spec_hash'][:16]}",
                f"- 生成源码哈希：{payload['generated']['source_hash'][:16]}",
                f"- 语法、导入、接口、运行、稳定性检查：{payload['code_validation']['checks']}",
                f"- 与参考能力最大误差：{payload['code_validation']['equivalence_max_error']}",
                f"- 等价性验证用例数：{payload['code_validation']['equivalence_cases']}",
                f"- 受限运行耗时：{payload['code_validation']['runtime_seconds']:.3f} 秒",
                f"- 修复次数：{len(payload['repairs'])}",
                f"- 结构化失败记录数：{failure_count}",
                f"- 复用历史修复经验数：{reused_experience_count}",
                f"- 详细中间过程：{trace_path or '未启用'}",
                "",
                "## Agent 总结",
                "",
                f"[{summary_mode}] {llm_summary}",
                "",
                "## 使用边界",
                "",
                "目标库存 T 是预测周期内非聚划算需求总量。实际下单量仍需结合现货、在途库存、提前期和安全库存。",
            ]
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}
