"""Isolated child-process runner for generated capability smoke tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Load a generated module and emit smoke-test results as JSON."""

    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) != 1:
        raise SystemExit("Usage: python -m inventory_agent.codegen.runner GENERATED_MODULE")
    module_path = Path(arguments[0]).resolve()
    spec = importlib.util.spec_from_file_location("generated_inventory_capability", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forecast = getattr(module, "forecast")
    history = [1, 2, 3, 4, 5, 6, 7] * 8
    values = forecast(history, 14)
    repeated_values = forecast(history, 14)
    edge_values = forecast([0] * 56, 1)
    equivalence_inputs = [
        {"history": history, "horizon": 14},
        {"history": [0, 0, 0, 5, 0, 0, 0, 0] * 7, "horizon": 8},
        {"history": list(range(1, 57)), "horizon": 7},
        {"history": [0] * 56, "horizon": 3},
    ]
    equivalence_cases = [
        {
            **case,
            "values": forecast(case["history"], case["horizon"]),
        }
        for case in equivalence_inputs
    ]
    build_inventory_target = getattr(module, "build_inventory_target")
    inventory = build_inventory_target([1, 2, 3, 4, 5, 6, 7] * 8, 14)
    print(
        json.dumps(
            {
                "values": values,
                "repeated_values": repeated_values,
                "edge_values": edge_values,
                "inventory": inventory,
                "equivalence_cases": equivalence_cases,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
