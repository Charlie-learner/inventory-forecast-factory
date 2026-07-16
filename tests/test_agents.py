from inventory_agent.agents.planner import PlanningAgent
from inventory_agent.agents.requirement import RequirementAgent
from inventory_agent.domain import CapabilitySpec
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class _UnknownTaskLLM:
    def complete(self, system: str, user: str) -> str:
        del system, user
        return '{"task_type": "unknown", "objective": "unsafe"}'


def test_requirement_agent_parses_chinese_description():
    request = RequirementAgent().parse("为商品 3424 在仓库 1 预测未来14天需求")
    assert request.item_id == 3424
    assert request.store_code == "1"
    assert request.horizon == 14


def test_requirement_agent_understands_nationwide_scope():
    request = RequirementAgent().parse("为商品 3424 预测全国未来14天需求")
    assert request.store_code == "all"


def test_requirement_agent_selects_accuracy_validation_profile():
    request = RequirementAgent().parse(
        "为商品 3424 在仓库 1 预测未来14天日需求，重点比较 WAPE 精度"
    )
    assert request.task_type == "demand_forecast"
    assert request.objective == "wape"


def test_requirement_agent_selects_intermittent_validation_profile():
    request = RequirementAgent().parse(
        "为商品 3424 在仓库 1 预测未来14天间歇性备件需求，大量日期为零需求"
    )
    assert request.task_type == "intermittent_demand"
    assert request.objective == "mae"


def test_requirement_agent_rejects_unknown_llm_task_profile():
    request = RequirementAgent(_UnknownTaskLLM()).parse(
        "为商品 3424 在仓库 1 预测未来14天目标库存"
    )
    assert request.task_type == "inventory_target"
    assert request.objective == "inventory_cost"


def test_planner_uses_demand_profile_and_baseline():
    request = RequirementAgent().parse("预测 SKU 3424 在 store 1 未来14天需求")
    plan = PlanningAgent().plan(
        request,
        {"demand_type": "intermittent", "zero_ratio": 0.7},
        CapabilityKnowledgeGraph.bootstrap(),
    )
    assert "croston" in plan.candidates
    assert "last_value" in plan.candidates
    assert "滚动回测" in plan.rationale
    assert plan.design_basis["business_goal"]["objective"] == request.objective
    assert plan.design_basis["knowledge_evidence"]
    assert plan.risks


def test_planner_keeps_non_executable_extraction_out_of_automatic_benchmark():
    knowledge = CapabilityKnowledgeGraph.bootstrap()
    knowledge.ingest_capabilities(
        [
            CapabilitySpec(
                name="novel_research_model",
                task_type="inventory_forecasting",
                description="Extracted research algorithm awaiting local integration",
                template_name="novel_research_model",
                input_contract="daily demand history",
                output_contract="daily forecast",
                suitable_for=("stable",),
            )
        ]
    )
    request = RequirementAgent().parse("预测 SKU 3424 在 store 1 未来14天需求")

    plan = PlanningAgent().plan(
        request,
        {"demand_type": "stable", "zero_ratio": 0.0},
        knowledge,
        available_models={"last_value", "moving_average"},
    )

    assert "novel_research_model" not in plan.candidates
    assert set(plan.candidates) <= {"last_value", "moving_average"}
