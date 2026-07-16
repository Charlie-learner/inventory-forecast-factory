from dataclasses import replace
from pathlib import Path

from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph


class _GenerationLLM:
    def complete(self, system: str, user: str) -> str:
        del system, user
        return """```python
def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    value = max(float(history[-1]), 0.0)
    return [value] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
```"""


def test_generated_capability_passes_validation(tmp_path: Path):
    generated = SafeCodeGenerator().generate("moving_average", tmp_path)
    result = GeneratedCodeValidator().validate(generated.path)
    assert result.valid
    assert len(result.sample_output) == 14
    assert result.sample_target_inventory == sum(result.sample_output)
    assert result.checks["stability"]
    assert result.runtime_seconds is not None
    assert result.runtime_seconds > 0


def test_spec_templates_replicate_every_registered_reference_model(tmp_path: Path):
    graph = CapabilityKnowledgeGraph.bootstrap()
    generator = SafeCodeGenerator()
    validator = GeneratedCodeValidator()
    for model in [
        "last_value",
        "moving_average",
        "seasonal_naive",
        "croston",
        "ridge_lag",
    ]:
        generated = generator.generate_from_spec(graph.capability_spec(model), tmp_path)
        result = validator.validate(generated.path, reference_model=model)
        assert result.valid, (model, result.errors)
        assert result.checks["equivalence"]
        assert result.equivalence_max_error is not None
        assert result.equivalence_max_error < 1e-7
        assert result.equivalence_cases == 4
        assert "from inventory_agent.forecasting.registry" not in generated.source


def test_generation_and_equivalence_follow_extracted_parameters(tmp_path: Path):
    base_spec = CapabilityKnowledgeGraph.bootstrap().capability_spec("moving_average")
    spec = replace(base_spec, parameters={"window": 21}, version="1.1.0")

    generated = SafeCodeGenerator().generate_from_spec(spec, tmp_path)
    result = GeneratedCodeValidator().validate(
        generated.path,
        reference_model="moving_average",
        reference_parameters=spec.parameters,
    )

    assert result.valid, result.errors
    assert result.checks["equivalence"]
    assert "'window': 21" in generated.source


def test_equivalence_check_rejects_behaviorally_wrong_replica(tmp_path: Path):
    path = tmp_path / "wrong_replica.py"
    path.write_text(
        "def forecast(history, horizon):\n    return [0.0] * horizon\n\n"
        "def build_inventory_target(history, horizon):\n"
        "    values = forecast(history, horizon)\n"
        "    return {'daily_forecast': values, 'target_inventory': sum(values)}\n",
        encoding="utf-8",
    )
    result = GeneratedCodeValidator().validate(path, reference_model="last_value")
    assert not result.valid
    assert result.checks["runtime"]
    assert not result.checks["equivalence"]
    assert "does not match" in result.errors[0]


def test_api_mode_can_generate_initial_code_from_capability_spec(tmp_path: Path):
    spec = CapabilityKnowledgeGraph.bootstrap().capability_spec("last_value")
    generated = SafeCodeGenerator().generate_from_spec(
        spec, tmp_path, llm=_GenerationLLM()
    )
    result = GeneratedCodeValidator().validate(
        generated.path, reference_model="last_value"
    )
    assert generated.generation_mode == "llm_generation"
    assert result.valid
    assert result.checks["equivalence"]


def test_validator_rejects_unsafe_import(tmp_path: Path):
    path = tmp_path / "unsafe.py"
    path.write_text("import os\n\ndef forecast(history, horizon):\n    return [0] * horizon\n", encoding="utf-8")
    result = GeneratedCodeValidator().validate(path)
    assert not result.valid
    assert "unsafe constructs" in result.errors[0]


def test_validator_rejects_file_access_through_allowed_library(tmp_path: Path):
    path = tmp_path / "unsafe_pandas.py"
    path.write_text(
        "import pandas as pd\n\n"
        "def forecast(history, horizon):\n"
        "    pd.read_csv('secret.csv')\n"
        "    return [0.0] * horizon\n\n"
        "def build_inventory_target(history, horizon):\n"
        "    values = forecast(history, horizon)\n"
        "    return {'daily_forecast': values, 'target_inventory': sum(values)}\n",
        encoding="utf-8",
    )
    result = GeneratedCodeValidator().validate(path)
    assert not result.valid
    assert "attribute call read_csv" in result.errors[0]


def test_validator_rejects_dunder_introspection(tmp_path: Path):
    path = tmp_path / "unsafe_dunder.py"
    path.write_text(
        "def forecast(history, horizon):\n"
        "    history.__class__\n"
        "    return [0.0] * horizon\n\n"
        "def build_inventory_target(history, horizon):\n"
        "    values = forecast(history, horizon)\n"
        "    return {'daily_forecast': values, 'target_inventory': sum(values)}\n",
        encoding="utf-8",
    )
    result = GeneratedCodeValidator().validate(path)
    assert not result.valid
    assert "dunder attribute __class__" in result.errors[0]


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
