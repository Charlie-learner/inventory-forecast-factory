"""Deterministically extract algorithm capability specifications from source artifacts."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from inventory_agent.domain import CapabilitySpec


class CapabilityExtractor:
    """Extract auditable capability specs from JSON, Markdown, text, or Python."""

    SUPPORTED_SUFFIXES = {".json", ".md", ".txt", ".py"}
    IGNORED_DIRECTORY_NAMES = {
        ".git",
        ".agents",
        ".codex",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".uv-cache",
        ".venv",
        "__pycache__",
        "build",
        "candidate_solutions",
        "dist",
        "generated",
        "generated_versions",
        "node_modules",
        "artifacts",
        "tests",
    }

    def __init__(self, max_repository_files: int = 1000) -> None:
        """Limit recursive scans and expose diagnostics for the latest source."""

        if max_repository_files <= 0:
            raise ValueError("max_repository_files must be positive")
        self.max_repository_files = max_repository_files
        self.last_scan_report: dict[str, Any] = {}

    def extract(self, source: str | Path) -> list[CapabilitySpec]:
        """Dispatch extraction by source type and attach stable provenance."""

        path = Path(source)
        if path.is_dir():
            return self._extract_repository(path)
        if not path.is_file():
            raise FileNotFoundError(f"Capability source not found: {path}")
        if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported capability source {path.suffix!r}; "
                f"supported={sorted(self.SUPPORTED_SUFFIXES)}"
            )
        text = path.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        suffix = path.suffix.lower()
        self.last_scan_report = {
            "source": str(path),
            "source_kind": "file",
            "files_scanned": 1,
            "files_matched": 1,
            "errors": [],
        }
        if suffix == ".json":
            return self.from_payload(
                json.loads(text),
                source_ref=str(path),
                source_hash=source_hash,
                source_type="json",
            )
        if suffix == ".py":
            return self._extract_python(
                path,
                text,
                source_hash,
                function_prefix=path.stem,
            )
        return self._extract_document(path, text, source_hash)

    def _extract_repository(self, root: Path) -> list[CapabilitySpec]:
        """Recursively scan a local repository for classes and public functions."""

        candidates = []
        for path in root.rglob("*.py"):
            relative_parts = path.relative_to(root).parts[:-1]
            if any(
                part.casefold() in self.IGNORED_DIRECTORY_NAMES
                for part in relative_parts
            ):
                continue
            candidates.append(path)
            if len(candidates) > self.max_repository_files:
                raise ValueError(
                    f"Repository scan exceeds {self.max_repository_files} Python files: {root}"
                )

        capabilities: list[CapabilitySpec] = []
        errors = []
        matched_files = 0
        function_count = 0
        class_count = 0
        dependency_edges = 0
        for path in sorted(candidates):
            try:
                text = path.read_text(encoding="utf-8")
                source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                module_prefix = "__".join(path.relative_to(root).with_suffix("").parts)
                extracted = self._extract_python(
                    path,
                    text,
                    source_hash,
                    function_prefix=module_prefix,
                )
            except ValueError as exc:
                if str(exc).startswith("No extractable Python capabilities found"):
                    continue
                errors.append({"path": str(path), "error": f"ValueError: {exc}"})
                continue
            except (OSError, SyntaxError, UnicodeError) as exc:
                errors.append(
                    {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            matched_files += 1
            function_count += sum(
                item.implementation_kind == "function" for item in extracted
            )
            class_count += sum(
                item.implementation_kind == "forecast_model" for item in extracted
            )
            dependency_edges += sum(
                len(item.internal_dependencies) for item in extracted
            )
            capabilities.extend(extracted)

        self.last_scan_report = {
            "source": str(root),
            "source_kind": "repository",
            "files_scanned": len(candidates),
            "files_matched": matched_files,
            "capabilities_found": len(capabilities),
            "functions_found": function_count,
            "forecast_models_found": class_count,
            "internal_dependency_edges": dependency_edges,
            "errors": errors,
        }
        if not capabilities:
            raise ValueError(f"No forecast capabilities found in repository: {root}")
        return capabilities

    def from_payload(
        self,
        payload: Any,
        *,
        source_ref: str,
        source_hash: str,
        source_type: str,
        extracted_by: str = "deterministic",
    ) -> list[CapabilitySpec]:
        """Normalize one JSON-like extraction payload into domain specifications."""

        if isinstance(payload, dict) and "capabilities" in payload:
            records = payload["capabilities"]
        elif isinstance(payload, list):
            records = payload
        else:
            records = [payload]
        if not isinstance(records, list) or not records:
            raise ValueError("Capability extraction payload must contain at least one record")
        return [
            self._spec_from_mapping(
                record,
                source_ref=source_ref,
                source_hash=source_hash,
                source_type=source_type,
                extracted_by=extracted_by,
            )
            for record in records
        ]

    @staticmethod
    def _string_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        raise TypeError(f"Expected string or list, got {type(value).__name__}")

    def _spec_from_mapping(
        self,
        record: Any,
        *,
        source_ref: str,
        source_hash: str,
        source_type: str,
        extracted_by: str,
    ) -> CapabilitySpec:
        if not isinstance(record, dict):
            raise TypeError("Each capability extraction record must be an object")
        name = str(record.get("name", "")).strip()
        parameters = record.get("parameters", {})
        if isinstance(parameters, str):
            parameters = json.loads(parameters) if parameters.strip() else {}
        if not isinstance(parameters, dict):
            raise TypeError("Capability parameters must be a JSON object")
        confidence = float(record.get("confidence", 1.0))
        return CapabilitySpec(
            name=name,
            task_type=str(record.get("task_type", "inventory_forecasting")).strip(),
            description=str(record.get("description", "")).strip(),
            template_name=str(record.get("template_name", name)).strip(),
            input_contract=str(
                record.get("input_contract", "non-negative daily demand history")
            ).strip(),
            output_contract=str(
                record.get(
                    "output_contract",
                    "non-negative daily forecast and horizon-total target inventory",
                )
            ).strip(),
            suitable_for=self._string_tuple(record.get("suitable_for")),
            metrics=self._string_tuple(record.get("metrics"))
            or ("inventory_cost", "wape"),
            dependencies=self._string_tuple(record.get("dependencies")),
            parameters=parameters,
            source_type=source_type,
            source_ref=source_ref,
            source_hash=source_hash,
            version=str(record.get("version", "1.0.0")).strip(),
            extracted_by=extracted_by,
            source_title=str(record.get("source_title", "")).strip(),
            source_url=str(record.get("source_url", "")).strip(),
            source_license=str(record.get("source_license", "")).strip(),
            accessed_at=str(record.get("accessed_at", "")).strip(),
            confidence=confidence,
            review_status=str(
                record.get("review_status", "auto_extracted")
            ).strip(),
            evidence_refs=self._string_tuple(record.get("evidence_refs")),
            extraction_warnings=self._string_tuple(
                record.get("extraction_warnings")
            ),
            implementation_kind=str(
                record.get("implementation_kind", "algorithm")
            ).strip(),
            entrypoints=self._string_tuple(record.get("entrypoints")),
            internal_dependencies=self._string_tuple(
                record.get("internal_dependencies")
            ),
            complexity={
                str(key): int(value)
                for key, value in dict(record.get("complexity", {})).items()
            },
        )

    def _extract_document(
        self, path: Path, text: str, source_hash: str
    ) -> list[CapabilitySpec]:
        fields: dict[str, Any] = {}
        heading = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and not heading:
                heading = stripped.lstrip("#").strip()
            match = re.match(r"^[-*]?\s*([A-Za-z_][\w-]*)\s*:\s*(.+)$", stripped)
            if match:
                fields[match.group(1).replace("-", "_")] = match.group(2).strip()
        if "name" not in fields:
            raise ValueError(
                f"Structured capability document {path} must define at least 'name:'"
            )
        fields.setdefault("description", heading or fields["name"])
        return self.from_payload(
            fields,
            source_ref=str(path),
            source_hash=source_hash,
            source_type="document",
        )

    def _extract_python(
        self,
        path: Path,
        text: str,
        source_hash: str,
        function_prefix: str,
    ) -> list[CapabilitySpec]:
        tree = ast.parse(text)
        import_roots = self._import_roots(tree)
        local_function_nodes = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        local_functions = set(local_function_nodes)

        def transitive_dependencies(
            function_name: str, visited: set[str] | None = None
        ) -> tuple[str, ...]:
            visited = set(visited or ())
            if function_name in visited:
                return ()
            visited.add(function_name)
            function_node = local_function_nodes[function_name]
            dependencies = set(
                self._node_dependencies(function_node, import_roots)
            )
            for called in self._internal_calls(
                function_node, local_functions - {function_name}
            ):
                dependencies.update(transitive_dependencies(called, visited))
            return tuple(sorted(dependencies))
        specs = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not self._is_forecast_model(node):
                continue
            name = self._class_model_name(node)
            if not name:
                continue
            specs.append(
                CapabilitySpec(
                    name=name,
                    task_type="inventory_forecasting",
                    description=ast.get_docstring(node) or f"Forecast capability {name}",
                    template_name=name,
                    input_contract="non-negative daily demand history and positive horizon",
                    output_contract="non-negative daily forecast and horizon-total target inventory",
                    suitable_for=self._class_string_tuple(node, "suitable_for"),
                    metrics=("inventory_cost", "wape", "rmse", "smape", "bias"),
                    dependencies=self._class_dependencies(node, import_roots),
                    parameters=self._constructor_defaults(node),
                    source_type="python",
                    source_ref=f"{path}:{node.lineno}",
                    source_hash=source_hash,
                    extracted_by="python_ast",
                    source_title=path.name,
                    confidence=0.95,
                    review_status="auto_extracted",
                    evidence_refs=(
                        f"{path}:{node.lineno}",
                        f"{path}:{node.end_lineno or node.lineno}",
                    ),
                    implementation_kind="forecast_model",
                    entrypoints=tuple(
                        f"{node.name}.{method.name}"
                        for method in node.body
                        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and method.name != "__init__"
                        and not method.name.startswith("_")
                    ),
                    internal_dependencies=self._internal_calls(
                        node,
                        {
                            method.name
                            for method in node.body
                            if isinstance(
                                method, (ast.FunctionDef, ast.AsyncFunctionDef)
                            )
                        },
                    ),
                    complexity=self._complexity(node),
                )
            )
        for node in tree.body:
            if (
                not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                or node.name.startswith("_")
                or not ast.get_docstring(node)
            ):
                continue
            capability_name = self._safe_symbol_name(
                f"{function_prefix}__{node.name}"
            )
            signature = self._function_signature(node)
            return_contract = self._return_contract(node)
            specs.append(
                CapabilitySpec(
                    name=capability_name,
                    task_type="repository_function",
                    description=self._function_description(node),
                    template_name="manual_integration",
                    input_contract=signature,
                    output_contract=return_contract,
                    suitable_for=(),
                    metrics=(),
                    dependencies=transitive_dependencies(node.name),
                    parameters=self._function_defaults(node),
                    source_type="python",
                    source_ref=f"{path}:{node.lineno}",
                    source_hash=source_hash,
                    extracted_by="python_ast",
                    source_title=path.name,
                    confidence=0.85,
                    review_status="review_required",
                    evidence_refs=(
                        f"{path}:{node.lineno}",
                        f"{path}:{node.end_lineno or node.lineno}",
                    ),
                    extraction_warnings=(
                        "Repository function requires capability review before execution.",
                    ),
                    implementation_kind="function",
                    entrypoints=(node.name,),
                    internal_dependencies=self._internal_calls(
                        node, local_functions - {node.name}
                    ),
                    complexity=self._complexity(node),
                )
            )
        if not specs:
            raise ValueError(f"No extractable Python capabilities found in {path}")
        return specs

    @staticmethod
    def _safe_symbol_name(value: str) -> str:
        """Convert a repository-qualified symbol into a domain-safe identifier."""

        safe = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
        return safe or "repository_function"

    @staticmethod
    def _node_dependencies(
        node: ast.AST, import_roots: dict[str, str]
    ) -> tuple[str, ...]:
        used_names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        return tuple(
            sorted(
                {
                    import_roots[name]
                    for name in used_names
                    if name in import_roots
                }
            )
        )

    @staticmethod
    def _internal_calls(node: ast.AST, local_symbols: set[str]) -> tuple[str, ...]:
        calls = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if isinstance(child.func, ast.Name) and child.func.id in local_symbols:
                calls.add(child.func.id)
            elif (
                isinstance(child.func, ast.Attribute)
                and child.func.attr in local_symbols
            ):
                calls.add(child.func.attr)
        return tuple(sorted(calls))

    @staticmethod
    def _complexity(node: ast.AST) -> dict[str, int]:
        """Return small static indicators useful during capability review."""

        branches = sum(
            isinstance(child, (ast.If, ast.IfExp, ast.Match)) for child in ast.walk(node)
        )
        loops = sum(
            isinstance(child, (ast.For, ast.AsyncFor, ast.While))
            for child in ast.walk(node)
        )
        calls = sum(isinstance(child, ast.Call) for child in ast.walk(node))
        return {
            "lines": max(
                int(getattr(node, "end_lineno", node.lineno)) - int(node.lineno) + 1,
                1,
            ),
            "branches": branches,
            "loops": loops,
            "calls": calls,
        }

    @staticmethod
    def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        arguments = []
        positional = [*node.args.posonlyargs, *node.args.args]
        for argument in positional:
            annotation = (
                ast.unparse(argument.annotation) if argument.annotation else "Any"
            )
            arguments.append(f"{argument.arg}: {annotation}")
        if node.args.vararg:
            arguments.append(f"*{node.args.vararg.arg}")
        for argument in node.args.kwonlyargs:
            annotation = (
                ast.unparse(argument.annotation) if argument.annotation else "Any"
            )
            arguments.append(f"{argument.arg}: {annotation}")
        if node.args.kwarg:
            arguments.append(f"**{node.args.kwarg.arg}")
        return f"{node.name}({', '.join(arguments)})"

    @staticmethod
    def _return_contract(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        if node.returns:
            return f"Returns {ast.unparse(node.returns)}"
        returns_value = any(
            isinstance(child, ast.Return) and child.value is not None
            for child in ast.walk(node)
        )
        return "Returns an implementation-defined value" if returns_value else "Returns None"

    @staticmethod
    def _function_description(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        docstring = ast.get_docstring(node) or ""
        summary = docstring.strip().splitlines()[0].strip()
        kind = "Asynchronous function" if isinstance(node, ast.AsyncFunctionDef) else "Function"
        return summary or f"{kind} {node.name} extracted from a real code repository."

    @staticmethod
    def _function_defaults(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> dict[str, Any]:
        names = [argument.arg for argument in [*node.args.posonlyargs, *node.args.args]]
        offset = len(names) - len(node.args.defaults)
        values: dict[str, Any] = {}
        for index, default in enumerate(node.args.defaults, start=offset):
            try:
                values[names[index]] = ast.literal_eval(default)
            except (ValueError, TypeError):
                values[names[index]] = ast.unparse(default)
        for argument, default in zip(
            node.args.kwonlyargs, node.args.kw_defaults, strict=True
        ):
            if default is None:
                continue
            try:
                values[argument.arg] = ast.literal_eval(default)
            except (ValueError, TypeError):
                values[argument.arg] = ast.unparse(default)
        return values

    @staticmethod
    def _import_roots(tree: ast.Module) -> dict[str, str]:
        """Map imported aliases to their top-level dependency package."""

        aliases: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    aliases[alias.asname or root] = root
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                for alias in node.names:
                    aliases[alias.asname or alias.name] = root
        return {
            alias: root
            for alias, root in aliases.items()
            if root not in {"__future__", "inventory_agent"}
        }

    @staticmethod
    def _class_dependencies(
        node: ast.ClassDef, import_roots: dict[str, str]
    ) -> tuple[str, ...]:
        """Return only packages referenced inside one model class."""

        used_names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        return tuple(
            sorted(
                {
                    import_roots[name]
                    for name in used_names
                    if name in import_roots
                }
            )
        )

    @staticmethod
    def _class_string_tuple(node: ast.ClassDef, field_name: str) -> tuple[str, ...]:
        """Read a literal class-level tuple/list used as capability metadata."""

        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == field_name
                for target in statement.targets
            ):
                continue
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError):
                return ()
            if isinstance(value, str):
                return (value,)
            if isinstance(value, (list, tuple)):
                return tuple(str(item) for item in value)
        return ()

    @staticmethod
    def _is_forecast_model(node: ast.ClassDef) -> bool:
        return any(
            (isinstance(base, ast.Name) and base.id == "ForecastModel")
            or (isinstance(base, ast.Attribute) and base.attr == "ForecastModel")
            for base in node.bases
        )

    @staticmethod
    def _class_model_name(node: ast.ClassDef) -> str | None:
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == "name" for target in statement.targets):
                    try:
                        value = ast.literal_eval(statement.value)
                    except (ValueError, TypeError):
                        return None
                    return str(value)
        return None

    @staticmethod
    def _constructor_defaults(node: ast.ClassDef) -> dict[str, Any]:
        for statement in node.body:
            if isinstance(statement, ast.FunctionDef) and statement.name == "__init__":
                names = [argument.arg for argument in statement.args.args[1:]]
                defaults = statement.args.defaults
                offset = len(names) - len(defaults)
                values = {}
                for index, default in enumerate(defaults, start=offset):
                    try:
                        values[names[index]] = ast.literal_eval(default)
                    except (ValueError, TypeError):
                        continue
                return values
        return {}
