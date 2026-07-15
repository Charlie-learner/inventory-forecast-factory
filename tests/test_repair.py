from pathlib import Path

from inventory_agent.agents.repair import RepairAgent
from inventory_agent.codegen.validator import GeneratedCodeValidator


def test_repair_agent_replaces_invalid_capability(tmp_path: Path):
    generated, reason = RepairAgent().repair("moving_average", ("syntax error",), tmp_path)
    assert "syntax error" in reason
    assert GeneratedCodeValidator().validate(generated.path).valid

