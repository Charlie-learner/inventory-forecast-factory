from pathlib import Path

from inventory_agent.agents.repair import RepairAgent
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.codegen.generator import GeneratedCapability


class _RepairLLM:
    def complete(self, system: str, user: str) -> str:
        del system, user
        return """```python
def forecast(history, horizon):
    return [float(history[-1])] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": sum(values)}
```"""


class _FailingRepairLLM:
    def complete(self, system: str, user: str) -> str:
        del system, user
        raise ConnectionError("provider unavailable")


def test_repair_agent_replaces_invalid_capability(tmp_path: Path):
    generated, reason = RepairAgent().repair(
        "moving_average", ("syntax error",), tmp_path, attempt=2
    )
    assert "syntax error" in reason
    assert "第 2 轮修复" in reason
    assert GeneratedCodeValidator().validate(generated.path).valid


def test_first_api_repair_uses_llm_source_before_safe_fallback(tmp_path: Path):
    current_path = tmp_path / "forecast_moving_average.py"
    current_path.write_text("def broken(:\n", encoding="utf-8")
    current = GeneratedCapability(
        "moving_average", current_path.read_text(encoding="utf-8"), current_path
    )
    generated, reason = RepairAgent(llm=_RepairLLM()).repair(
        "moving_average",
        ("syntax: invalid syntax",),
        tmp_path,
        attempt=1,
        current=current,
    )
    assert generated.generation_mode == "llm_repair"
    assert "LLM 按错误修复源码" in reason
    assert GeneratedCodeValidator().validate(generated.path).valid


def test_provider_failure_falls_back_to_safe_template(tmp_path: Path):
    current = GeneratedCapability("moving_average", "broken", tmp_path / "broken.py")
    generated, reason = RepairAgent(llm=_FailingRepairLLM()).repair(
        "moving_average",
        ("runtime: provider test",),
        tmp_path,
        current=current,
    )
    assert generated.generation_mode == "constrained_template"
    assert "ConnectionError" in reason
    assert GeneratedCodeValidator().validate(generated.path).valid
