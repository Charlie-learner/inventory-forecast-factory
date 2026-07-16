"""Create transparent JSON and Markdown validation reports."""

from __future__ import annotations

import json
from pathlib import Path

from inventory_agent.llm.client import LLMClient, MockLLMClient


class ReportAgent:
    """Render machine-readable and human-readable validation reports."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    @staticmethod
    def _metric(value: object, digits: int = 4) -> str:
        """Format an optional numeric metric without hiding missing evidence."""

        if value is None:
            return "-"
        return f"{float(value):.{digits}f}"

    def create(self, payload: dict, output_dir: str | Path) -> dict[str, str]:
        """Write JSON and Markdown reports and return their file paths."""

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "validation_report.json"
        markdown_path = output / "validation_report.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        llm_response = self.llm.complete(
            (
                "你是库存预测验证报告 Agent。请简洁说明模型选择、主要指标、"
                "风险，以及目标库存的使用边界。"
            ),
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
        rows = [
            "| 模型 | WAPE | sMAPE | Bias | MAE | 库存成本 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for candidate in candidates:
            metrics = candidate["metrics"]
            rows.append(
                f"| {candidate['model']} | {self._metric(metrics.get('wape'))} | "
                f"{self._metric(metrics.get('smape'))} | "
                f"{self._metric(metrics.get('bias'))} | "
                f"{self._metric(metrics.get('mae'))} | "
                f"{self._metric(metrics.get('inventory_cost'), 2)} |"
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
                f"{self._metric(validation.get('equivalence_max_error'), 8)} | "
                f"`{generated['path']}` |"
            )
        if len(code_rows) == 2:
            code_rows.append("| 未启用完整追踪 | - | - | - | - | - |")

        repair_rows = [
            "| 轮次 | 修复策略 | 对应失败 |",
            "|---:|---|---|",
        ]
        failures = payload.get("failure_history", [])
        for index, repair in enumerate(payload.get("repairs", []), start=1):
            failure = failures[index - 1] if index <= len(failures) else {}
            failure_text = failure.get("category") or failure.get("fingerprint") or "-"
            repair_rows.append(f"| {index} | {repair} | {failure_text} |")
        if len(repair_rows) == 2:
            repair_rows.append("| 0 | 无需修复，首次验证通过 | - |")

        plugin_rows = [
            "| 插件 | 新增指标 | 新增验证配置 |",
            "|---|---|---|",
        ]
        for plugin in payload.get("plugins", {}).get("loaded", []):
            plugin_rows.append(
                f"| `{plugin['spec']}` | "
                f"{', '.join(plugin['metrics_added']) or '-'} | "
                f"{', '.join(plugin['validation_profiles_added']) or '-'} |"
            )
        if len(plugin_rows) == 2:
            plugin_rows.append("| 内置注册表 | 无外部插件 | 无外部插件 |")

        trace_path = (payload.get("execution_trace", {}).get("paths") or {}).get(
            "markdown"
        )
        validation = payload["code_validation"]
        runtime = validation.get("runtime_seconds")
        runtime_text = f"{runtime:.3f} 秒" if runtime is not None else "-"
        profile = payload["validation_profile"]
        markdown = "\n".join(
            [
                "# 库存预测能力验证报告",
                "",
                f"- 能力描述：{payload['request']['description']}",
                f"- 商品：{payload['request']['item_id']}",
                f"- 仓库：{payload['request']['store_code']}",
                f"- 预测周期：{payload['request']['horizon']} 天",
                f"- 任务类型：{payload['request']['task_type']}",
                f"- 主验证指标：{profile['primary_metric']}",
                f"- 决胜指标：{', '.join(profile['tie_breakers']) or '-'}",
                f"- 回测折数：{profile['folds']}",
                f"- 最短历史：{profile['min_history_days']} 天",
                f"- 需求类型：{payload['profile']['demand_type']}",
                f"- 历史状态：{payload['profile']['history_status']}",
                f"- 选中模型：{payload['benchmark']['selected_model']}",
                f"- 未来 {payload['request']['horizon']} 天目标库存："
                f"{payload['benchmark']['target_inventory']:.2f}",
                f"- 成本 A（缺货）：{costs['understock_cost']:.2f}",
                f"- 成本 B（积压）：{costs['overstock_cost']:.2f}",
                f"- 成本来源：{costs['source']}",
                f"- 评价口径：{payload['benchmark']['evaluation_unit']}",
                f"- 能力抽取数量：{payload['capability_extraction']['count']}",
                f"- 能力来源扫描文件数：{scanned_files}",
                f"- 能力来源：{payload['capability_spec']['source_ref'] or '内置能力图谱'}",
                "",
                "## 候选模型自动比较",
                "",
                *rows,
                "",
                "## 候选代码方案生成与比较",
                "",
                *code_rows,
                "",
                "## 多轮修复记录",
                "",
                *repair_rows,
                "",
                "## 插件与验证配置",
                "",
                *plugin_rows,
                "",
                f"- 可用指标：{', '.join(payload.get('plugins', {}).get('available_metrics', []))}",
                "- 可用验证配置："
                f"{', '.join(payload.get('plugins', {}).get('available_validation_profiles', []))}",
                "",
                "## 生成代码验证",
                "",
                f"- 生成方式：{payload['generated']['generation_mode']}",
                f"- 能力规格哈希：{payload['generated']['spec_hash'][:16]}",
                f"- 生成源码哈希：{payload['generated']['source_hash'][:16]}",
                f"- 语法、导入、接口、运行、稳定性检查：{validation['checks']}",
                f"- 与参考能力最大误差：{validation['equivalence_max_error']}",
                f"- 等价性验证用例数：{validation['equivalence_cases']}",
                f"- 受限运行耗时：{runtime_text}",
                f"- 修复次数：{len(payload.get('repairs', []))}",
                f"- 结构化失败记录数：{len(failures)}",
                f"- 复用历史修复经验数：{len(payload.get('repair_experience_used', []))}",
                f"- 详细中间过程：{trace_path or '未启用'}",
                "",
                "## Agent 总结",
                "",
                f"[{summary_mode}] {llm_summary}",
                "",
                "## 使用边界",
                "",
                (
                    "目标库存 T 是预测周期内非聚划算需求总量。实际补货量仍需结合"
                    "现货、在途库存、供应提前期、安全库存和业务服务水平约束。"
                ),
            ]
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}
