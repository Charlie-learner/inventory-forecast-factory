"""Static and runtime checks for generated algorithm modules."""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeValidationResult:
    """Summarize static checks and the generated module smoke test."""

    valid: bool
    checks: dict[str, bool]
    errors: tuple[str, ...]
    sample_output: tuple[float, ...] = ()
    sample_target_inventory: float | None = None


class GeneratedCodeValidator:
    """Validate generated code with static rules and an isolated smoke test."""

    ALLOWED_IMPORT_ROOTS = {"__future__", "pandas", "inventory_agent"}
    FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "input", "__import__"}

    def __init__(self, timeout_seconds: float = 10.0):
        """Configure the maximum runtime allowed for generated code."""

        self.timeout_seconds = timeout_seconds

    def validate(self, path: str | Path) -> CodeValidationResult:
        """Check syntax, imports, interfaces, and runtime output contracts."""

        module_path = Path(path)
        checks = {"syntax": False, "imports": False, "interface": False, "runtime": False}
        errors: list[str] = []
        sample: tuple[float, ...] = ()
        try:
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            checks["syntax"] = True
        except (OSError, SyntaxError) as exc:
            return CodeValidationResult(False, checks, (f"syntax: {exc}",))

        unsafe = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for name in names:
                    if name.split(".", 1)[0] not in self.ALLOWED_IMPORT_ROOTS:
                        unsafe.append(f"import {name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in self.FORBIDDEN_CALLS:
                    unsafe.append(f"call {node.func.id}")
        if unsafe:
            errors.append("unsafe constructs: " + ", ".join(sorted(set(unsafe))))
            return CodeValidationResult(False, checks, tuple(errors))
        checks["imports"] = True

        try:
            functions = {
                node.name: node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            expected = {"forecast", "build_inventory_target"}
            checks["interface"] = expected.issubset(functions) and all(
                [argument.arg for argument in functions[name].args.args] == ["history", "horizon"]
                and not functions[name].args.vararg
                and not functions[name].args.kwarg
                for name in expected
            )
            if not checks["interface"]:
                raise ValueError(
                    "generated module must define forecast() and build_inventory_target()"
                )
            child_env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"API_KEY", "OPENAI_API_KEY"}
            }
            completed = subprocess.run(
                [sys.executable, "-m", "inventory_agent.codegen.runner", str(module_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=child_env,
            )
            payload = json.loads(completed.stdout)
            values = payload["values"]
            if not isinstance(values, list) or len(values) != 14:
                raise ValueError("forecast must return a list matching horizon")
            numeric = tuple(float(value) for value in values)
            if any(not math.isfinite(value) or value < 0 for value in numeric):
                raise ValueError("forecast values must be finite and non-negative")
            inventory = payload["inventory"]
            target_inventory = float(inventory["target_inventory"])
            inventory_values = tuple(float(value) for value in inventory["daily_forecast"])
            if (
                inventory_values != numeric
                or not math.isfinite(target_inventory)
                or target_inventory < 0
            ):
                raise ValueError("inventory target must contain the validated daily forecast")
            if abs(target_inventory - sum(numeric)) > 1e-9:
                raise ValueError("target_inventory must equal the horizon forecast total")
            sample = numeric
            checks["runtime"] = True
        except Exception as exc:  # Validation must return errors, not crash the workflow.
            errors.append(f"runtime: {type(exc).__name__}: {exc}")
        return CodeValidationResult(
            all(checks.values()),
            checks,
            tuple(errors),
            sample,
            target_inventory if checks["runtime"] else None,
        )
