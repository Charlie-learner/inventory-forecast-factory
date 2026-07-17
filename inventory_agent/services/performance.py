"""Interpret generated-code timing and memory evidence for release decisions."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PerformancePolicy:
    """Thresholds used to turn measurements into maintainable recommendations."""

    latency_warning_ms: float = 5.0
    peak_memory_warning_kb: float = 32_768.0
    minimum_throughput: float = 100.0


@dataclass(frozen=True)
class PerformanceBenchmarkConfig:
    """Workload shape shared by the validator and isolated child runner."""

    history_points: int = 364
    horizon: int = 28

    def __post_init__(self) -> None:
        if self.history_points <= 0 or self.horizon <= 0:
            raise ValueError("performance workload dimensions must be positive")


def analyze_generated_performance(
    path: str | Path,
    validation: dict[str, Any],
    implementations: list[dict[str, Any]] | None = None,
    policy: PerformancePolicy | None = None,
) -> dict[str, Any]:
    """Create a resource profile and conservative optimization advice."""

    policy = policy or PerformancePolicy()
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    loop_count = sum(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))
    call_count = sum(isinstance(node, ast.Call) for node in ast.walk(tree))
    latency = validation.get("mean_latency_ms")
    peak_memory = validation.get("peak_memory_kb")
    throughput = validation.get("throughput_calls_per_second")
    recommendations = []
    if latency is not None and float(latency) > policy.latency_warning_ms:
        recommendations.append("单次预测延迟偏高，可优先减少重复计算并对批量数值运算进行向量化。")
    if peak_memory is not None and float(peak_memory) > policy.peak_memory_warning_kb:
        recommendations.append("Python 内存峰值偏高，应避免复制完整历史序列并复用中间数组。")
    if throughput is not None and float(throughput) < policy.minimum_throughput:
        recommendations.append("吞吐量低于策略阈值，批量商品场景建议缓存不变参数或并行调度。")
    if loop_count > 2:
        recommendations.append("源码包含多层显式循环；优化前应先用相同数据做基准测试，避免改变算法语义。")
    if not recommendations:
        recommendations.append("当前基准未触发资源告警；继续保留回归基准，避免无证据的过早优化。")
    candidate_profiles = []
    for item in implementations or []:
        result = item.get("validation", {})
        candidate_profiles.append(
            {
                "variant_id": item.get("variant_id"),
                "selected": bool(item.get("selected")),
                "valid": bool(result.get("valid")),
                "mean_latency_ms": result.get("mean_latency_ms"),
                "peak_memory_kb": result.get("peak_memory_kb"),
                "throughput_calls_per_second": result.get(
                    "throughput_calls_per_second"
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "measurement_scope": (
            "Isolated deterministic micro-benchmark; tracemalloc covers Python "
            "allocations and may not include all native-library memory."
        ),
        "selected_source": str(source_path),
        "source_bytes": len(source.encode("utf-8")),
        "source_lines": len(source.splitlines()),
        "ast_loop_count": loop_count,
        "ast_call_count": call_count,
        "measurements": {
            "iterations": validation.get("performance_iterations", 0),
            "mean_latency_ms": latency,
            "cpu_time_ms": validation.get("cpu_time_ms"),
            "peak_memory_kb": peak_memory,
            "throughput_calls_per_second": throughput,
        },
        "policy": asdict(policy),
        "recommendations": recommendations,
        "candidate_profiles": candidate_profiles,
    }


def write_performance_analysis(payload: dict[str, Any], path: str | Path) -> Path:
    """Persist one reviewable performance artifact."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
