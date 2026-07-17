"""Static and runtime checks for generated algorithm modules."""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from inventory_agent.forecasting.registry import default_registry
from inventory_agent.services.performance import PerformanceBenchmarkConfig


@dataclass(frozen=True)
class CodeValidationResult:
    """Summarize static checks and the generated module smoke test."""

    valid: bool
    checks: dict[str, bool]
    errors: tuple[str, ...]
    sample_output: tuple[float, ...] = ()
    sample_target_inventory: float | None = None
    runtime_seconds: float | None = None
    equivalence_max_error: float | None = None
    equivalence_cases: int = 0
    performance_iterations: int = 0
    mean_latency_ms: float | None = None
    cpu_time_ms: float | None = None
    peak_memory_kb: float | None = None
    throughput_calls_per_second: float | None = None


class GeneratedCodeValidator:
    """Validate generated code with static rules and an isolated smoke test."""

    ALLOWED_IMPORT_ROOTS = {
        "__future__",
        "numpy",
        "pandas",
        "sklearn",
    }
    FORBIDDEN_CALLS = {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
    FORBIDDEN_ATTRIBUTE_CALLS = {
        "connect",
        "dump",
        "load",
        "open",
        "popen",
        "Popen",
        "read_csv",
        "read_json",
        "read_pickle",
        "read_table",
        "request",
        "run",
        "save",
        "savez",
        "socket",
        "system",
        "to_csv",
        "to_json",
        "to_pickle",
        "urlopen",
    }

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        performance_iterations: int = 20,
        benchmark_config: PerformanceBenchmarkConfig | None = None,
    ):
        """Configure the maximum runtime allowed for generated code."""

        self.timeout_seconds = timeout_seconds
        if not 1 <= performance_iterations <= 500:
            raise ValueError("performance_iterations must be between 1 and 500")
        self.performance_iterations = performance_iterations
        self.benchmark_config = benchmark_config or PerformanceBenchmarkConfig()

    def validate(
        self,
        path: str | Path,
        reference_model: str | None = None,
        reference_parameters: dict | None = None,
    ) -> CodeValidationResult:
        """Check safety, contracts, runtime stability, and optional replication equivalence."""

        module_path = Path(path)
        checks = {
            "syntax": False,
            "imports": False,
            "interface": False,
            "runtime": False,
            "stability": False,
        }
        if reference_model is not None:
            checks["equivalence"] = False
        errors: list[str] = []
        sample: tuple[float, ...] = ()
        runtime_seconds: float | None = None
        equivalence_max_error: float | None = None
        equivalence_cases = 0
        performance: dict = {}
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
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in self.FORBIDDEN_ATTRIBUTE_CALLS:
                    unsafe.append(f"attribute call {node.func.attr}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                unsafe.append(f"dunder attribute {node.attr}")
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
            child_env["PYTHONDONTWRITEBYTECODE"] = "1"
            started = time.perf_counter()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "inventory_agent.codegen.runner",
                    str(module_path),
                    str(self.performance_iterations),
                    str(self.benchmark_config.history_points),
                    str(self.benchmark_config.horizon),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=child_env,
            )
            runtime_seconds = time.perf_counter() - started
            if completed.returncode != 0:
                diagnostic = completed.stderr.strip().splitlines()
                detail = diagnostic[-1] if diagnostic else "child process failed"
                raise RuntimeError(detail)
            payload = json.loads(completed.stdout)
            performance = payload.get("performance", {})
            values = payload["values"]
            if not isinstance(values, list) or len(values) != 14:
                raise ValueError("forecast must return a list matching horizon")
            numeric = tuple(float(value) for value in values)
            if any(not math.isfinite(value) or value < 0 for value in numeric):
                raise ValueError("forecast values must be finite and non-negative")
            repeated = tuple(float(value) for value in payload["repeated_values"])
            edge_values = tuple(float(value) for value in payload["edge_values"])
            if repeated != numeric:
                raise ValueError("forecast must be deterministic for identical inputs")
            if len(edge_values) != 1 or any(
                not math.isfinite(value) or value < 0 for value in edge_values
            ):
                raise ValueError("forecast must handle an all-zero history and horizon=1")
            checks["stability"] = True
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
            if reference_model is not None:
                reference = default_registry().create(reference_model)
                for name, value in (reference_parameters or {}).items():
                    if not hasattr(reference, name):
                        raise ValueError(
                            f"reference capability {reference_model!r} has no parameter {name!r}"
                        )
                    setattr(reference, name, value)
                max_errors = []
                for index, case in enumerate(payload["equivalence_cases"], start=1):
                    horizon = int(case["horizon"])
                    generated_values = np.asarray(case["values"], dtype=float)
                    if (
                        len(generated_values) != horizon
                        or not np.all(np.isfinite(generated_values))
                        or np.any(generated_values < 0)
                    ):
                        raise ValueError(
                            f"equivalence case {index} returned invalid forecast values"
                        )
                    history = pd.Series(case["history"], dtype=float)
                    expected = reference.predict(history, horizon)
                    case_error = float(np.max(np.abs(generated_values - expected)))
                    max_errors.append(case_error)
                    if not np.allclose(
                        generated_values, expected, rtol=1e-7, atol=1e-9
                    ):
                        raise ValueError(
                            "generated forecast does not match the referenced capability; "
                            f"case={index}, max_error={case_error:.6g}"
                        )
                equivalence_cases = len(max_errors)
                equivalence_max_error = max(max_errors, default=0.0)
                checks["equivalence"] = True
        except Exception as exc:  # Validation must return errors, not crash the workflow.
            errors.append(f"runtime: {type(exc).__name__}: {exc}")
        return CodeValidationResult(
            all(checks.values()),
            checks,
            tuple(errors),
            sample,
            target_inventory if checks["runtime"] else None,
            runtime_seconds,
            equivalence_max_error,
            equivalence_cases,
            int(performance.get("iterations", 0)),
            (
                float(performance["mean_latency_ms"])
                if performance.get("mean_latency_ms") is not None
                else None
            ),
            (
                float(performance["cpu_time_ms"])
                if performance.get("cpu_time_ms") is not None
                else None
            ),
            (
                float(performance["peak_memory_kb"])
                if performance.get("peak_memory_kb") is not None
                else None
            ),
            (
                float(performance["throughput_calls_per_second"])
                if performance.get("throughput_calls_per_second") is not None
                else None
            ),
        )
