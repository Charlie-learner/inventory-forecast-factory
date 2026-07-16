import json
from dataclasses import replace
from pathlib import Path

from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.extraction.extractor import CapabilityExtractor


ROOT = Path(__file__).resolve().parents[1]


class _NovelGenerationLLM:
    def complete(self, system: str, user: str) -> str:
        del system, user
        return """```python
def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    return [max(float(history[-1]), 0.0)] * horizon

def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
```"""


def test_standalone_replication_auto_validates_registered_reference(tmp_path: Path):
    spec = CapabilityExtractor().extract(
        ROOT / "examples/capabilities/moving_average.md"
    )[0]
    manifest_path = tmp_path / "review.json"

    manifest = CapabilityReplicator().replicate(
        spec,
        tmp_path / "generated",
        manifest_path,
    )

    assert manifest["validation"]["valid"]
    assert manifest["validation"]["equivalence_cases"] == 4
    assert manifest["review"]["status"] == "auto_validated"
    assert manifest["review"]["registration_ready"]
    assert manifest_path.exists()
    assert manifest_path.with_suffix(".md").exists()
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["generation"]["source_hash"] == manifest["generation"]["source_hash"]


def test_novel_llm_replica_requires_semantic_human_review(tmp_path: Path):
    base = CapabilityExtractor().extract(
        ROOT / "examples/capabilities/moving_average.md"
    )[0]
    spec = replace(
        base,
        name="novel_inventory_forecaster",
        template_name="novel_inventory_forecaster",
    )

    manifest = CapabilityReplicator().replicate(
        spec,
        tmp_path / "generated",
        tmp_path / "review.json",
        llm=_NovelGenerationLLM(),
    )

    assert manifest["validation"]["valid"]
    assert "equivalence" not in manifest["validation"]["checks"]
    assert manifest["review"]["status"] == "review_required"
    assert not manifest["review"]["registration_ready"]
