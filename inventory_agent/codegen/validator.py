"""Static and runtime checks for generated algorithm modules."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeValidationResult:
    valid: bool
    checks: dict[str, bool]
    errors: tuple[str, ...]
    sample_output: tuple[float, ...] = ()


class GeneratedCodeValidator:
    ALLOWED_IMPORT_ROOTS = {"__future__", "pandas", "inventory_agent"}
    FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "input", "__import__"}

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def validate(self, path: str | Path) -> CodeValidationResult:
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
            checks["interface"] = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "forecast"
                for node in tree.body
            )
            if not checks["interface"]:
                raise ValueError("generated module must define forecast(history, horizon)")
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
            values = json.loads(completed.stdout)["values"]
            if not isinstance(values, list) or len(values) != 14:
                raise ValueError("forecast must return a list matching horizon")
            numeric = tuple(float(value) for value in values)
            if any(value < 0 for value in numeric):
                raise ValueError("forecast values must be non-negative")
            sample = numeric
            checks["runtime"] = True
        except Exception as exc:  # Validation must return errors, not crash the workflow.
            errors.append(f"runtime: {type(exc).__name__}: {exc}")
        return CodeValidationResult(all(checks.values()), checks, tuple(errors), sample)
