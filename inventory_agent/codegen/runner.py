"""Isolated child-process runner for generated capability smoke tests."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import tracemalloc
from pathlib import Path

from inventory_agent.services.performance import PerformanceBenchmarkConfig


def _forecast_list(value: object, horizon: int, label: str) -> list[float]:
    """Enforce the public list contract before serializing child output."""

    if not isinstance(value, list):
        raise TypeError(f"{label} must return Python list, got {type(value).__name__}")
    if len(value) != horizon:
        raise ValueError(f"{label} must return {horizon} values, got {len(value)}")
    return [float(item) for item in value]


def main(argv: list[str] | None = None) -> int:
    """Load a generated module and emit smoke-test results as JSON."""

    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) not in {1, 2, 4}:
        raise SystemExit(
            "Usage: python -m inventory_agent.codegen.runner "
            "GENERATED_MODULE [PERFORMANCE_ITERATIONS [HISTORY_POINTS HORIZON]]"
        )
    performance_iterations = int(arguments[1]) if len(arguments) >= 2 else 20
    if len(arguments) == 4:
        benchmark_config = PerformanceBenchmarkConfig(
            history_points=int(arguments[2]),
            horizon=int(arguments[3]),
        )
    else:
        benchmark_config = PerformanceBenchmarkConfig()
    if not 1 <= performance_iterations <= 500:
        raise ValueError("PERFORMANCE_ITERATIONS must be between 1 and 500")
    module_path = Path(arguments[0]).resolve()
    spec = importlib.util.spec_from_file_location("generated_inventory_capability", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forecast = getattr(module, "forecast")
    history = [1, 2, 3, 4, 5, 6, 7] * 8
    values = _forecast_list(forecast(history, 14), 14, "forecast")
    repeated_values = _forecast_list(forecast(history, 14), 14, "forecast")
    edge_values = _forecast_list(forecast([0] * 56, 1), 1, "forecast")
    equivalence_inputs = [
        {"history": history, "horizon": 14},
        {"history": [0, 0, 0, 5, 0, 0, 0, 0] * 7, "horizon": 8},
        {"history": list(range(1, 57)), "horizon": 7},
        {"history": [0] * 56, "horizon": 3},
    ]
    equivalence_cases = [
        {
            **case,
            "values": _forecast_list(
                forecast(case["history"], case["horizon"]),
                case["horizon"],
                "forecast",
            ),
        }
        for case in equivalence_inputs
    ]
    build_inventory_target = getattr(module, "build_inventory_target")
    inventory = build_inventory_target([1, 2, 3, 4, 5, 6, 7] * 8, 14)
    if not isinstance(inventory, dict):
        raise TypeError(
            "build_inventory_target must return dict, "
            f"got {type(inventory).__name__}"
        )
    if "daily_forecast" not in inventory or "target_inventory" not in inventory:
        raise ValueError(
            "build_inventory_target must contain daily_forecast and target_inventory"
        )
    inventory = {
        "daily_forecast": _forecast_list(
            inventory["daily_forecast"], 14, "inventory daily_forecast"
        ),
        "target_inventory": float(inventory["target_inventory"]),
    }
    benchmark_history = [
        float((index % 11) == 0) * 5.0
        for index in range(benchmark_config.history_points)
    ]
    tracemalloc.start()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    for _ in range(performance_iterations):
        _forecast_list(
            forecast(benchmark_history, benchmark_config.horizon),
            benchmark_config.horizon,
            "forecast",
        )
    cpu_time_ms = (time.process_time() - cpu_started) * 1000
    wall_time_ms = (time.perf_counter() - wall_started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    mean_latency_ms = wall_time_ms / performance_iterations
    performance = {
        "iterations": performance_iterations,
        "history_points": len(benchmark_history),
        "horizon": benchmark_config.horizon,
        "wall_time_ms": wall_time_ms,
        "cpu_time_ms": cpu_time_ms,
        "mean_latency_ms": mean_latency_ms,
        "throughput_calls_per_second": (
            performance_iterations / max(wall_time_ms / 1000, 1e-12)
        ),
        "peak_memory_kb": peak_bytes / 1024,
    }
    print(
        json.dumps(
            {
                "values": values,
                "repeated_values": repeated_values,
                "edge_values": edge_values,
                "inventory": inventory,
                "equivalence_cases": equivalence_cases,
                "performance": performance,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
