"""Knowledge-augmented candidate planning with explainable design evidence."""

from __future__ import annotations

from collections.abc import Collection

from inventory_agent.domain import AlgorithmPlan, CapabilityRequest, ExecutionTask
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class PlanningAgent:
    """Plan candidate algorithms and explain the evidence behind the design."""

    @staticmethod
    def provisional_tasks(online_research: bool = False) -> tuple[ExecutionTask, ...]:
        """Return the stable task skeleton used before data-aware planning finishes."""

        research_action = "检索联网行业资料" if online_research else "确认本地知识证据"
        return (
            ExecutionTask("understand", "理解业务要求", "从自然语言提取商品、仓库、周期和目标。"),
            ExecutionTask("extract", "检索与抽取算法能力", "读取能力文档、代码和知识图谱。"),
            ExecutionTask("profile", "诊断需求数据", "加载数据并识别需求画像和数据风险。"),
            ExecutionTask("research", research_action, "形成可追溯的行业知识证据。"),
            ExecutionTask("plan", "设计执行方案", "Planner Agent 确定候选、验证指标和发布门禁。"),
            ExecutionTask("compare", "比较候选算法", "执行无时间泄漏的历史滚动回测。"),
            ExecutionTask("generate", "生成并审查代码", "多个实现 Agent 生成候选，审查 Agent 独立复核。"),
            ExecutionTask("validate", "验证与必要时修复", "检查接口、安全、稳定性、等价性和资源消耗。"),
            ExecutionTask("deposit", "生成报告并沉淀知识", "输出报告，回写验证、失败、修复策略和版本。"),
        )

    def plan(
        self,
        request: CapabilityRequest,
        profile: dict,
        knowledge: CapabilityKnowledgeGraph,
        available_models: Collection[str] | None = None,
        research_evidence: dict | None = None,
    ) -> AlgorithmPlan:
        """Retrieve suitable models and return an evidence-backed validation plan."""

        retrieval_limit = (
            request.candidate_count
            if available_models is None
            else max(request.candidate_count, len(knowledge.graph))
        )
        retrieved = knowledge.retrieve_algorithms(
            str(profile["demand_type"]), limit=retrieval_limit
        )
        allowed = set(available_models) if available_models is not None else None
        selected_records = [
            record
            for record in retrieved
            if allowed is None or record["name"] in allowed
        ]
        research_evidence = research_evidence or {}
        research_models = list(
            research_evidence.get("analysis", {}).get("recommended_models", [])
        )
        research_order = {
            name: index for index, name in enumerate(research_models)
        }
        selected_records.sort(
            key=lambda record: research_order.get(
                record["name"], len(research_order)
            )
        )
        names = [record["name"] for record in selected_records]
        if "last_value" not in names and (allowed is None or "last_value" in allowed):
            names.append("last_value")
            selected_records.append(
                {
                    "name": "last_value",
                    "description": "以最后一个观测值作为可解释的保底基线。",
                    "validation_count": 0,
                    "success_rate": None,
                    "mean_inventory_cost": None,
                }
            )
        names = names[: request.candidate_count]
        selected_records = [
            record for record in selected_records if record["name"] in names
        ]
        if not names:
            raise ValueError("No executable forecasting capability is available")

        zero_ratio = float(profile.get("zero_ratio", 0.0))
        demand_type = str(profile.get("demand_type", "unknown"))
        history_points = int(profile.get("observations", 0))
        risks = []
        if zero_ratio >= 0.5:
            risks.append("零需求比例较高，普通均值模型可能持续高估需求。")
        if history_points < max(request.horizon * 3, 42):
            risks.append("历史样本较短，复杂模型的参数稳定性有限。")
        if demand_type == "volatile":
            risks.append("需求波动较大，单一模型在不同回测窗口可能表现不一致。")
        if demand_type == "weekly_seasonal":
            risks.append("周周期较明显，节假日或促销变化可能破坏历史周期。")
        if demand_type == "trend":
            risks.append("历史趋势较明显，长期外推需防止趋势反转或增速变化。")
        if not risks:
            risks.append("历史回测只能反映样本内表现，仍需监控未来分布漂移。")

        candidate_evidence = []
        for record in selected_records:
            history = (
                f"已有 {record.get('validation_count', 0)} 次历史验证"
                if record.get("validation_count")
                else "暂无历史验证，作为待比较候选"
            )
            if record.get("success_rate") is not None:
                history += f"，成功率 {float(record['success_rate']):.0%}"
            if record.get("mean_inventory_cost") is not None:
                history += (
                    f"，历史平均库存成本 "
                    f"{float(record['mean_inventory_cost']):.2f}"
                )
            candidate_evidence.append(
                {
                    "name": record["name"],
                    "description": record.get("description", ""),
                    "history_evidence": history,
                    "matched_demand_type": demand_type,
                }
            )

        rationale = (
            f"该任务要求为商品 {request.item_id} 在仓库 {request.store_code} "
            f"预测未来 {request.horizon} 天，并以 {request.objective} 为主要目标。"
            f"历史序列被识别为 {demand_type}，共有 {history_points} 个观测，"
            f"零需求比例为 {zero_ratio:.2%}。因此先从知识图谱检索与该需求画像"
            f"匹配的能力，再保留可解释基线，形成 {', '.join(names)} 三类候选。"
            f"最终不由语言模型主观决定，而是使用 {request.objective} 及决胜指标"
            "执行无时间泄漏滚动回测；生成代码还必须通过安全、接口、稳定性和"
            "参考行为等价验证后才允许沉淀为新版本。"
        )
        if research_evidence.get("status") == "success":
            rationale += (
                f"联网研究从 {research_evidence.get('provider', '外部来源')} 检索到 "
                f"{len(research_evidence.get('records', []))} 条可追溯资料，"
                "其建议只用于调整候选优先级，不替代本地回测。"
            )
        design_basis = {
            "business_goal": {
                "item_id": request.item_id,
                "store_code": request.store_code,
                "horizon": request.horizon,
                "task_type": request.task_type,
                "objective": request.objective,
            },
            "demand_evidence": {
                "demand_type": demand_type,
                "observations": history_points,
                "zero_ratio": zero_ratio,
                "coefficient_of_variation": profile.get(
                    "coefficient_of_variation"
                ),
                "trend_strength": profile.get("trend_strength"),
                "lag_7_correlation": profile.get("lag_7_correlation"),
            },
            "knowledge_evidence": candidate_evidence,
            "online_research": {
                "status": research_evidence.get("status", "disabled"),
                "provider": research_evidence.get("provider"),
                "query": research_evidence.get("query"),
                "record_count": len(research_evidence.get("records", [])),
                "recommended_models": research_models,
                "result_path": research_evidence.get("result_path"),
            },
            "selection_rule": (
                f"按 {request.objective} 排序，使用验证配置中的 tie-breakers 决胜；"
                "模型名仅用于完全相同时的确定性排序。"
            ),
            "release_gate": (
                "语法、导入安全、统一接口、受限运行、确定性、边界输入和数值等价。"
            ),
        }
        execution_tasks = list(
            self.provisional_tasks(
                online_research=research_evidence.get("status") != "disabled"
            )
        )
        execution_tasks[5] = ExecutionTask(
            "compare",
            f"比较 {len(names)} 个候选算法",
            f"对 {', '.join(names)} 执行滚动回测，并按 {request.objective} 选优。",
        )
        execution_tasks[6] = ExecutionTask(
            "generate",
            "生成并审查独立代码实现",
            "根据胜出能力生成不同策略的源码候选，再由 CodeReviewAgent 审查。",
        )
        return AlgorithmPlan(
            tuple(names),
            rationale,
            request.objective,
            design_basis=design_basis,
            risks=tuple(risks),
            execution_tasks=tuple(execution_tasks),
        )
