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
        if value is None:
            return "-"
        return f"{float(value):.{digits}f}"

    def create(self, payload: dict, output_dir: str | Path) -> dict[str, str]:
        """Write JSON and a teacher-readable Markdown evidence report."""

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "validation_report.json"
        markdown_path = output / "validation_report.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        llm_response = self.llm.complete(
            (
                "你是库存预测验证报告 Agent。请简洁说明模型选择、主要指标、"
                "设计依据、风险以及目标库存的使用边界。"
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
        profile = payload["validation_profile"]
        plan = payload.get("plan", {})
        basis = plan.get("design_basis", {})
        validation = payload["code_validation"]
        failures = payload.get("failure_history", [])

        candidate_rows = [
            "| 模型 | WAPE | sMAPE | Bias | MAE | 库存成本 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for candidate in candidates:
            metrics = candidate["metrics"]
            candidate_rows.append(
                f"| {candidate['model']} | {self._metric(metrics.get('wape'))} | "
                f"{self._metric(metrics.get('smape'))} | "
                f"{self._metric(metrics.get('bias'))} | "
                f"{self._metric(metrics.get('mae'))} | "
                f"{self._metric(metrics.get('inventory_cost'), 2)} |"
            )

        design_rows = [
            "| 候选能力 | 能力说明 | 历史验证证据 |",
            "|---|---|---|",
        ]
        for record in basis.get("knowledge_evidence", []):
            design_rows.append(
                f"| {record.get('name', '-')} | "
                f"{record.get('description', '-')} | "
                f"{record.get('history_evidence', '-')} |"
            )
        if len(design_rows) == 2:
            design_rows.append("| - | 未记录结构化候选依据 | - |")

        code_rows = [
            "| 代码方案 | 回测选中 | 生成方式 | 验证通过 | 等价误差 |",
            "|---|---|---|---|---:|",
        ]
        for solution in payload.get("candidate_code_solutions", []):
            code_validation = solution["code_validation"]
            code_rows.append(
                f"| {solution['model']} | {solution['selected']} | "
                f"{solution['generated']['generation_mode']} | "
                f"{code_validation['valid']} | "
                f"{self._metric(code_validation.get('equivalence_max_error'), 8)} |"
            )
        if len(code_rows) == 2:
            code_rows.append("| 未启用完整追踪 | - | - | - | - |")

        repair_rows = [
            "| 轮次 | 失败根因 | 建议动作 | 修复策略 |",
            "|---:|---|---|---|",
        ]
        for index, repair in enumerate(payload.get("repairs", []), start=1):
            failure = failures[index - 1] if index <= len(failures) else {}
            repair_rows.append(
                f"| {index} | {failure.get('root_cause', '-')} | "
                f"{' / '.join(failure.get('recommended_actions', [])) or '-'} | "
                f"{repair} |"
            )
        if len(repair_rows) == 2:
            repair_rows.append("| 0 | 首次验证通过 | - | 无需修复 |")

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

        runtime = validation.get("runtime_seconds")
        trace_path = (payload.get("execution_trace", {}).get("paths") or {}).get(
            "markdown"
        )
        version = payload.get("generated", {})
        scanned_files = sum(
            int(report.get("files_scanned", 0))
            for report in payload["capability_extraction"].get("scan_reports", [])
        )
        markdown = "\n".join(
            [
                "# 库存预测能力验证报告",
                "",
                f"- 任务：{payload['request']['description']}",
                f"- 商品 / 仓库：{payload['request']['item_id']} / "
                f"{payload['request']['store_code']}",
                f"- 预测周期：{payload['request']['horizon']} 天",
                f"- 任务类型：{payload['request']['task_type']}",
                f"- 需求画像：{payload['profile']['demand_type']}，"
                f"零需求比例 {payload['profile']['zero_ratio']:.2%}",
                f"- 选中模型：{payload['benchmark']['selected_model']}",
                f"- 目标库存：{payload['benchmark']['target_inventory']:.2f}",
                f"- 主验证指标：{profile['primary_metric']}",
                f"- 决胜指标：{', '.join(profile['tie_breakers']) or '-'}",
                f"- 缺货 / 积压成本：{costs['understock_cost']:.2f} / "
                f"{costs['overstock_cost']:.2f}",
                f"- 能力来源扫描文件数：{scanned_files}",
                "",
                "## 方案设计依据",
                "",
                plan.get("rationale", "未记录自然语言设计依据。"),
                "",
                *design_rows,
                "",
                f"- 选择规则：{basis.get('selection_rule', '-')}",
                f"- 发布门禁：{basis.get('release_gate', '-')}",
                f"- 主要风险：{'；'.join(plan.get('risks', [])) or '-'}",
                "",
                "## 候选模型自动比较",
                "",
                *candidate_rows,
                "",
                "## 候选代码生成与验证",
                "",
                *code_rows,
                "",
                "## 失败分析与多轮修复",
                "",
                *repair_rows,
                "",
                f"- 复用历史修复经验："
                f"{len(payload.get('repair_experience_used', []))} 条",
                "",
                "## 插件与验证配置",
                "",
                *plugin_rows,
                "",
                "## 最终代码与版本证据",
                "",
                f"- 生成方式：{version.get('generation_mode', '-')}",
                f"- 能力规格哈希：{version.get('spec_hash', '')[:16]}",
                f"- 生成源码哈希：{version.get('source_hash', '')[:16]}",
                f"- 验证矩阵：{validation.get('checks', {})}",
                f"- 等价性用例数：{validation.get('equivalence_cases', 0)}",
                f"- 受限运行耗时：{runtime:.3f} 秒" if runtime is not None else "- 受限运行耗时：-",
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
                    "现货、在途库存、供应提前期、安全库存和服务水平约束。"
                ),
            ]
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}
