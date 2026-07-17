import json
from dataclasses import asdict
from pathlib import Path

from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.services.performance import (
    PerformanceBenchmarkConfig,
    analyze_generated_performance,
    write_performance_analysis,
)


def test_generated_code_performance_analysis_is_persisted(tmp_path: Path):
    generated = SafeCodeGenerator().generate("moving_average", tmp_path / "code")
    validation = GeneratedCodeValidator(
        performance_iterations=5,
        benchmark_config=PerformanceBenchmarkConfig(history_points=70, horizon=7),
    ).validate(
        generated.path,
        reference_model="moving_average",
    )

    analysis = analyze_generated_performance(
        generated.path,
        asdict(validation),
        [{"variant_id": "primary", "selected": True, "validation": asdict(validation)}],
    )
    output = write_performance_analysis(analysis, tmp_path / "performance.json")

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["measurements"]["iterations"] == 5
    assert saved["measurements"]["mean_latency_ms"] >= 0
    assert saved["measurements"]["peak_memory_kb"] >= 0
    assert saved["candidate_profiles"][0]["selected"] is True
    assert saved["recommendations"]
