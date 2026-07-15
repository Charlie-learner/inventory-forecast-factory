from pathlib import Path

from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator


def test_generated_capability_passes_validation(tmp_path: Path):
    generated = SafeCodeGenerator().generate("moving_average", tmp_path)
    result = GeneratedCodeValidator().validate(generated.path)
    assert result.valid
    assert len(result.sample_output) == 14
    assert result.sample_target_inventory == sum(result.sample_output)
    assert result.checks["stability"]
    assert result.runtime_seconds is not None
    assert result.runtime_seconds > 0


def test_validator_rejects_unsafe_import(tmp_path: Path):
    path = tmp_path / "unsafe.py"
    path.write_text("import os\n\ndef forecast(history, horizon):\n    return [0] * horizon\n", encoding="utf-8")
    result = GeneratedCodeValidator().validate(path)
    assert not result.valid
    assert "unsafe constructs" in result.errors[0]


def test_validator_rejects_wrong_inventory_interface(tmp_path: Path):
    path = tmp_path / "wrong_interface.py"
    path.write_text(
        "def forecast(history):\n    return history\n\n"
        "def build_inventory_target(history, horizon):\n"
        "    return {'daily_forecast': [], 'target_inventory': 0}\n",
        encoding="utf-8",
    )
    result = GeneratedCodeValidator().validate(path)
    assert not result.valid
    assert not result.checks["interface"]
