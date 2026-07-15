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
    values = forecast([1, 2, 3, 4, 5, 6, 7] * 8, 14)
    build_inventory_target = getattr(module, "build_inventory_target")
    inventory = build_inventory_target([1, 2, 3, 4, 5, 6, 7] * 8, 14)
    print(json.dumps({"values": values, "inventory": inventory}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
