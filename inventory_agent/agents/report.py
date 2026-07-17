"""Create transparent JSON and Markdown validation reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from inventory_agent.llm.client import LLMClient, MockLLMClient


logger = logging.getLogger(__name__)


class ReportAgent:
    """Render machine-readable and human-readable validation reports."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or MockLLMClient()

    @staticmethod
    def _metric(value: object, digits: int = 4) -> str:
        if value is None:
            return "-"
        return f"{float(value):.{digits}f}"

    @staticmethod
    def _model_name(name: str) -> str:
        """Return a business-friendly model label."""

        return {
            "last_value": "最近一期需求延续法",
            "moving_average": "近期平均需求法",
            "seasonal_naive": "同期季节规律法",
            "croston": "间歇性需求预测法",
            "ridge_lag": "历史滞后特征回归法",
        }.get(name, name)

    def _business_markdown(self, payload: dict) -> str:
        """Create a plain-language decision report for business users."""

        request = payload["request"]
        benchmark = payload["benchmark"]
        selected = next(
            candidate
            for candidate in benchmark["candidates"]
            if candidate["model"] == benchmark["selected_model"]
        )
        metrics = selected["metrics"]
        forecast = [float(value) for value in benchmark.get("forecast", [])]
        target = float(benchmark["target_inventory"])
        horizon = int(request["horizon"])
        average = target / max(horizon, 1)
        peak = max(forecast, default=0.0)
        wape = metrics.get("wape")
        profile = payload.get("profile", {})
        replenishment = payload.get("replenishment", {})
        history_status = profile.get("history_status", "observed")
        wape_text = (
            "不适用（历史需求全为 0）"
            if history_status in {"all_zero_history", "zero_history_fallback"}
            else f"{float(wape):.1%}"
            if wape is not None
            else "本次未计算"
        )
        risk_notes = list(payload.get("plan", {}).get("risks", []))
        selection = payload.get("selection_explanation", {})
        rejected = selection.get("data_facts", {}).get("alternatives", [])
        if history_status == "zero_history_fallback":
            risk_notes.insert(0, "该商品在目标仓库缺少有效历史销量，本结果仅适合作为冷启动参考。")
        elif history_status == "all_zero_history":
            risk_notes.insert(
                0,
                "该商品在目标仓库的历史目标销量全部为 0。预测为 0 只表示数据中没有需求证据，"
                "不能直接理解为未来一定无需备货；请核查商品是否未上架、长期断货或销量口径不完整。",
            )
        if not risk_notes:
            risk_notes.append("预测会受促销、断货、价格变化和供应延迟影响，请结合最新业务信息复核。")
        daily_rows = [
            "| 天数 | 建议需求量 |",
            "|---:|---:|",
            *[
                f"| 第 {index} 天 | {value:.2f} |"
                for index, value in enumerate(forecast, start=1)
            ],
        ]
        if replenishment.get("available"):
            replenishment_lines = [
                (
                    f"- 当前现货 / 在途 / 欠单：**{replenishment['on_hand']:.2f} / "
                    f"{replenishment['on_order']:.2f} / "
                    f"{replenishment['backorder']:.2f} 件**。"
                ),
                f"- 安全库存：**{replenishment['safety_stock']:.2f} 件**。",
                (
                    f"- 库存位置（现货 + 在途 - 欠单）："
                    f"**{replenishment['inventory_position']:.2f} 件**。"
                ),
                (
                    f"- 应用最小订货量、包装倍数和仓容后，建议补货："
                    f"**{replenishment['recommended_order_qty']:.2f} 件**。"
                ),
                (
                    f"- 供应提前期：约 **{replenishment['lead_time_days']:.0f} 天**；"
                    f"仓库剩余容量：**{replenishment['remaining_capacity']:.2f} 件**。"
                ),
            ]
            if replenishment.get("capacity_limited"):
                replenishment_lines.append(
                    "- 当前建议受到仓容限制，应考虑跨仓调拨、分批到货或人工调整。"
                )
        else:
            replenishment_lines = [
                (
                    "- 建议补货量："
                    "**max(目标库存 + 安全库存 + 欠单 - 当前可用库存 - 已下单在途库存, 0)**。"
                ),
                f"- 暂未计算具体下单量：{replenishment.get('reason', '缺少库存快照。')}",
            ]
        return "\n".join(
            [
                "# 库存预测业务建议",
                "",
                "## 一句话结论",
                "",
                (
                    f"商品 **{request['item_id']}** 在仓库 **{request['store_code']}** "
                    f"未来 **{horizon} 天**建议准备约 **{target:.2f} 件**库存。"
                ),
                "",
                "## 建议怎么做",
                "",
                f"- 预测期目标库存：**{target:.2f} 件**。",
                f"- 日均预计需求：约 **{average:.2f} 件/天**。",
                f"- 单日最高预计需求：约 **{peak:.2f} 件**。",
                *replenishment_lines,
                "- 如果供应提前期较长，应在上述补货量之外结合安全库存和供应稳定性适当上调。",
                "- 若存在大促、价格调整、断货或新品活动，应人工修正后再下单。",
                "",
                "## 为什么采用这个结果",
                "",
                (
                    f"系统比较了 {len(benchmark['candidates'])} 种方法，最终采用"
                    f"“**{self._model_name(benchmark['selected_model'])}**”。"
                    "选择依据是历史回测中综合缺货损失和库存积压后表现更合适。"
                ),
                *[
                    f"- 未采用“{self._model_name(item['model'])}”："
                    f"{item['reason_not_selected']}。"
                    for item in rejected
                ],
                f"- 使用边界：{selection.get('business_boundary', '仍需结合业务信息复核。')}",
                "",
                "## 结果可信度怎么理解",
                "",
                (
                    f"- 历史回测的加权误差约为 **{wape_text}**。"
                    "该数值越低越好；它用于比较方案，不代表未来一定出现同样误差。"
                ),
                (
                    f"- 历史回测中的库存损失评分为 **"
                    f"{self._metric(metrics.get('inventory_cost'), 2)}**，越低越好。"
                ),
                (
                    "- 当历史需求全部为 0 时，误差和库存损失也可能同时为 0；"
                    "这不是高准确率证明，而是缺少可学习需求的信号。"
                    if history_status in {"all_zero_history", "zero_history_fallback"}
                    else "- 回测结果只反映历史数据中的相对表现，不能替代业务复核。"
                ),
                "- 目标库存是预测期需求建议，不等同于最终采购订单。",
                "",
                "## 需要注意的风险",
                "",
                *[f"- {note}" for note in risk_notes],
                "",
                "## 每日需求预测",
                "",
                *daily_rows,
                "",
                "## 查看技术细节",
                "",
                "算法比较、WAPE、库存成本公式、代码验证、修复记录和 Agent 调用过程，"
                "请查看同一运行目录下的《技术验证报告》和详细 Trace。",
            ]
        )

    def create(
        self,
        payload: dict,
        output_dir: str | Path,
        *,
        use_llm_explanation: bool = True,
    ) -> dict[str, str]:
        """Write JSON and a teacher-readable Markdown evidence report."""

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "validation_report.json"
        markdown_path = output / "validation_report.md"
        business_path = output / "business_report.md"
        compact_evidence = {
            "request": payload["request"],
            "demand_profile": payload.get("profile", {}),
            "selected_model": payload["benchmark"]["selected_model"],
            "target_inventory": payload["benchmark"]["target_inventory"],
            "candidate_metrics": [
                {"model": item["model"], "metrics": item["metrics"]}
                for item in payload["benchmark"]["candidates"]
            ],
            "plan": payload.get("plan", {}),
            "selection_explanation": payload.get("selection_explanation", {}),
            "performance": payload.get("performance_analysis", {}).get(
                "measurements", {}
            ),
            "repair_count": len(payload.get("repairs", [])),
        }
        llm_summary = payload.get("plan", {}).get(
            "rationale", "系统已依据需求画像、回测和代码验证形成方案。"
        )
        summary_mode = "deterministic"
        if use_llm_explanation:
            try:
                llm_response = self.llm.complete(
                    (
                        "你是库存预测方案解释 Agent。面向非计算机专业用户，用简洁中文说明："
                        "为什么选中该方法、其他候选为何未选、性能与资源消耗、主要不确定性、"
                        "目标库存如何使用。区分数据事实、系统推断和业务建议，不使用未提供证据。"
                        "只返回 JSON：{\"summary\": \"...\"}。"
                    ),
                    json.dumps(compact_evidence, ensure_ascii=False, default=str),
                )
                llm_payload = json.loads(llm_response)
                llm_summary = str(llm_payload.get("summary", llm_response))
                summary_mode = str(llm_payload.get("mode", "api"))
            except (json.JSONDecodeError, AttributeError):
                llm_summary = llm_response.strip()
                summary_mode = "api"
            except Exception as exc:
                logger.warning("Report explanation fallback: %s", type(exc).__name__)
                summary_mode = "deterministic_fallback"
                llm_summary += f"（外部解释服务暂不可用：{type(exc).__name__}）"
        payload["design_explanation"] = {
            "mode": summary_mode,
            "summary": llm_summary,
            "evidence_scope": (
                "由任务、需求画像、候选回测、代码验证和资源基准构成；不替代业务审批。"
            ),
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        candidates = payload["benchmark"]["candidates"]
        costs = payload["benchmark"]["costs"]
        profile = payload["validation_profile"]
        plan = payload.get("plan", {})
        basis = plan.get("design_basis", {})
        validation = payload["code_validation"]
        failures = payload.get("failure_history", [])
        research = payload.get("online_research", {})
        performance = payload.get("performance_analysis", {})
        measurements = performance.get("measurements", {})
        collaboration = payload.get("multi_agent_collaboration", {})
        selected_collaboration = collaboration.get("selected_candidate", {})
        architecture = selected_collaboration.get("architecture", {})
        code_review = selected_collaboration.get("review", {})

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

        research_rows = [
            "| 在线资料 | DOI / URL | 相关度 |",
            "|---|---|---:|",
        ]
        for record in research.get("records", [])[:5]:
            identifier = record.get("doi") or record.get("url") or "-"
            research_rows.append(
                f"| {record.get('title', '-')} | {identifier} | "
                f"{self._metric(record.get('relevance_score'), 3)} |"
            )
        if len(research_rows) == 2:
            research_rows.append("| 未启用或未检索到资料 | - | - |")

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

        implementation_rows = [
            "| 实现候选 | 生成策略 | 生成方式 | 自动验证 | 运行耗时 | 结果 |",
            "|---|---|---|---|---:|---|",
        ]
        for implementation in payload.get("implementation_candidates", []):
            implementation_validation = implementation["validation"]
            runtime_seconds = implementation_validation.get("runtime_seconds")
            implementation_rows.append(
                f"| {implementation.get('variant_id', '-')} | "
                f"{implementation.get('strategy', '-')} | "
                f"{implementation.get('generation_mode', '-')} | "
                f"{'通过' if implementation_validation.get('valid') else '失败'} | "
                f"{self._metric(runtime_seconds, 4)} | "
                f"{'选中' if implementation.get('selected') else '未选中'} |"
            )
        if len(implementation_rows) == 2:
            implementation_rows.append("| primary | 规格忠实实现 | - | - | - | 选中 |")

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
        capability_version = payload.get("capability_version", {})
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
                "## 联网行业研究与知识抽取",
                "",
                f"- 状态：{research.get('status', 'disabled')}",
                f"- 提供方：{research.get('provider', '-')}",
                f"- 查询：{research.get('query', '-')}",
                f"- 分析方式：{research.get('analysis', {}).get('analysis_mode', '-')}",
                f"- 抽取文件：{research.get('result_path', '-')}",
                "- 使用原则：外部资料只影响候选优先级和实现上下文，最终结果由本地回测与代码门禁裁决。",
                "",
                *research_rows,
                "",
                "## 候选模型自动比较",
                "",
                *candidate_rows,
                "",
                "## 候选代码生成与验证",
                "",
                *code_rows,
                "",
                "## 同一能力的多实现代码候选",
                "",
                (
                    "API 模式会根据不同实现策略生成多份独立源码，逐份通过安全、接口、"
                    "稳定性和参考行为验证，再从合格实现中选择运行耗时更低且代码更精简的版本。"
                    "Mock 模式为保持完全可复现，只生成一份安全模板实现。"
                ),
                "",
                *implementation_rows,
                "",
                "## 多智能体代码协作证据",
                "",
                "本次代码不是由单次提示直接决定，而是经过相互独立的设计、实现、审查和验证角色。",
                "",
                f"- 协作协议：{collaboration.get('protocol', '-')}",
                f"- 参与角色：{', '.join(collaboration.get('roles', [])) or '-'}",
                f"- 架构设计方式：{architecture.get('mode', '-')}",
                f"- 实现策略：{selected_collaboration.get('implementation', {}).get('strategy', '-')}",
                f"- 独立审查方式：{code_review.get('mode', '-')}",
                f"- 审查结论：{'通过' if code_review.get('approved') else '需要验证门禁裁决'}",
                f"- 审查修订代码：{'是' if code_review.get('revision_applied') else '否'}",
                f"- 审查发现：{'；'.join(code_review.get('findings', [])) or '未发现问题'}",
                f"- 完整协作记录：{collaboration.get('artifacts', {}).get('manifest', '-')}",
                f"- 实现蓝图：{collaboration.get('artifacts', {}).get('blueprint', '-')}",
                "",
                "## 失败分析与多轮修复",
                "",
                *repair_rows,
                "",
                f"- 复用历史修复经验："
                f"{len(payload.get('repair_experience_used', []))} 条",
                "",
                "## 性能与资源消耗分析",
                "",
                f"- 微基准迭代次数：{measurements.get('iterations', 0)}",
                f"- 单次预测平均延迟：{self._metric(measurements.get('mean_latency_ms'), 4)} ms",
                f"- 吞吐量：{self._metric(measurements.get('throughput_calls_per_second'), 2)} 次/秒",
                f"- Python 分配内存峰值：{self._metric(measurements.get('peak_memory_kb'), 2)} KB",
                f"- 源码规模：{performance.get('source_lines', '-')} 行 / "
                f"{performance.get('source_bytes', '-')} 字节",
                *[
                    f"- 优化建议：{recommendation}"
                    for recommendation in performance.get("recommendations", [])
                ],
                "- 说明：该微基准用于候选间相对比较，不能替代生产环境压测。",
                "",
                "## 插件与验证配置",
                "",
                *plugin_rows,
                "",
                "## 最终代码与版本证据",
                "",
                f"- 自动分配语义版本：{capability_version.get('capability_version', '-')}",
                f"- 父版本：{capability_version.get('parent_version', '-') or '-'}",
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
        business_path.write_text(
            self._business_markdown(payload),
            encoding="utf-8",
        )
        return {
            "json": str(json_path),
            "markdown": str(markdown_path),
            "business_markdown": str(business_path),
        }
