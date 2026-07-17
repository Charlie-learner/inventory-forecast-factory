from dataclasses import replace
import json
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


class _DiverseGenerationLLM:
    def complete(self, system: str, user: str) -> str:
        del system
        variant = json.loads(user)["implementation_variant"]
        return f'''"""Independent implementation {variant}."""

def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    value = max(float(history[-1]), 0.0)
    return [value] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {{"daily_forecast": values, "target_inventory": float(sum(values))}}
'''


class _CollaborativeGenerationLLM:
    def __init__(self):
        self.roles = []

    def complete(self, system: str, user: str) -> str:
        del system
        payload = json.loads(user)
        if "business_context" in payload:
            self.roles.append("architecture")
            return json.dumps(
                {
                    "algorithm_steps": ["use the latest valid observation"],
                    "required_contracts": ["forecast returns list[float]"],
                    "edge_cases": ["empty history"],
                    "allowed_dependencies": ["numpy"],
                    "performance_goal": "linear input validation",
                    "risks": [],
                }
            )
        if "implementation_variant" in payload:
            self.roles.append("implementation")
            return """import numpy as np

def forecast(history, horizon):
    return np.asarray([float(history[-1])] * horizon)

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(values.sum())}
"""
        self.roles.append("review")
        revised = """def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    return [max(float(history[-1]), 0.0)] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
"""
        return json.dumps(
            {
                "approved": True,
                "findings": ["converted ndarray output to list[float]"],
                "revised_source": revised,
            }
        )


def test_generated_capability_passes_validation(tmp_path: Path):
    generated = SafeCodeGenerator().generate("moving_average", tmp_path)
    result = GeneratedCodeValidator().validate(generated.path)
    assert result.valid
    assert len(result.sample_output) == 14
    assert result.sample_target_inventory == sum(result.sample_output)
    assert result.checks["stability"]
    assert result.runtime_seconds is not None
    assert result.runtime_seconds > 0
    assert result.performance_iterations == 20
    assert result.mean_latency_ms is not None
    assert result.mean_latency_ms >= 0
    assert result.peak_memory_kb is not None
    assert result.throughput_calls_per_second is not None


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
    assert generated.generation_mode == "llm_autonomous_generation"
    assert result.valid
    assert result.checks["equivalence"]


def test_api_mode_generates_and_validates_diverse_implementation_candidates(
    tmp_path: Path,
):
    spec = CapabilityKnowledgeGraph.bootstrap().capability_spec("last_value")
    generator = SafeCodeGenerator()

    candidates = generator.generate_candidates_from_spec(
        spec,
        tmp_path,
        llm=_DiverseGenerationLLM(),
        candidate_count=3,
        generation_context={"demand_type": "intermittent"},
    )

    assert len(candidates) == 3
    assert len({candidate.source_hash for candidate in candidates}) == 3
    assert {candidate.variant_id for candidate in candidates} == {
        "candidate_1",
        "candidate_2",
        "candidate_3",
    }
    for candidate in candidates:
        result = GeneratedCodeValidator().validate(
            candidate.path, reference_model="last_value"
        )
        assert result.valid, result.errors
        assert candidate.prompt_hash
        assert candidate.strategy


def test_multi_agent_generation_designs_implements_reviews_and_revises(tmp_path: Path):
    spec = CapabilityKnowledgeGraph.bootstrap().capability_spec("last_value")
    llm = _CollaborativeGenerationLLM()

    candidates = SafeCodeGenerator().generate_candidates_from_spec(
        spec,
        tmp_path,
        llm=llm,
        candidate_count=1,
    )

    candidate = candidates[0]
    result = GeneratedCodeValidator().validate(
        candidate.path, reference_model="last_value"
    )
    assert llm.roles == ["architecture", "implementation", "review"]
    assert candidate.generation_mode == "llm_multi_agent_revised"
    assert candidate.collaboration["architecture"]["mode"] == "llm_architecture"
    assert candidate.collaboration["review"]["revision_applied"]
    assert result.valid, result.errors
    assert (tmp_path / "implementation_blueprint.json").exists()
    assert (tmp_path / "multi_agent_collaboration.json").exists()


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


def test_validator_reports_generated_output_type_contract(tmp_path: Path):
    path = tmp_path / "wrong_return_type.py"
    path.write_text(
        "import numpy as np\n\n"
        "def forecast(history, horizon):\n"
        "    return np.zeros(horizon)\n\n"
        "def build_inventory_target(history, horizon):\n"
        "    return 0.0\n",
        encoding="utf-8",
    )

    result = GeneratedCodeValidator().validate(path)

    assert not result.valid
    assert "forecast must return Python list, got ndarray" in result.errors[0]
