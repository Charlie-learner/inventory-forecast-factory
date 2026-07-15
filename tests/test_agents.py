from inventory_agent.agents.planner import PlanningAgent
from inventory_agent.agents.requirement import RequirementAgent
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
