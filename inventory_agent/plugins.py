"""Explicit, auditable loading of trusted local capability-factory plugins."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from inventory_agent.validation.metrics import MetricFunction, MetricRegistry
from inventory_agent.validation.profiles import (
    ValidationProfile,
    ValidationProfileRegistry,
)


@dataclass(frozen=True)
class LoadedPlugin:
    """Describe the registrations contributed by one plugin."""

    spec: str
    module: str
    callable_name: str
    metrics_added: tuple[str, ...]
    validation_profiles_added: tuple[str, ...]


class PluginContext:
    """Expose only the supported extension points to plugin registration code."""

    def __init__(
        self,
        metric_registry: MetricRegistry,
        validation_profiles: ValidationProfileRegistry,
    ) -> None:
        self.metric_registry = metric_registry
        self.validation_profiles = validation_profiles

    def register_metric(self, name: str, function: MetricFunction) -> None:
        """Register a metric that follows the standard four-argument contract."""

        self.metric_registry.register(name, function)

    def register_validation_profile(self, profile: ValidationProfile) -> None:
        """Register a task-specific ranking and backtesting policy."""

        self.validation_profiles.register(profile)


def _load_module(reference: str) -> ModuleType:
    """Import a dotted module or load a local Python file."""

    path = Path(reference)
    if path.suffix.lower() == ".py" or path.exists():
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Plugin file not found: {resolved}")
        digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
        module_name = f"inventory_agent_local_plugin_{digest}"
        module_spec = importlib.util.spec_from_file_location(module_name, resolved)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"Cannot load plugin module from {resolved}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return module
    return importlib.import_module(reference)


def load_plugins(
    specs: list[str] | tuple[str, ...] | None,
    metric_registry: MetricRegistry,
    validation_profiles: ValidationProfileRegistry,
) -> list[LoadedPlugin]:
    """Load explicit ``module:callable`` plugins and report their registrations.

    Plugins execute normal Python code and therefore must come from a trusted local
    source. Automatic remote discovery is intentionally not performed.
    """

    loaded: list[LoadedPlugin] = []
    context = PluginContext(metric_registry, validation_profiles)
    for raw_spec in specs or []:
        reference, separator, callable_name = raw_spec.rpartition(":")
        if not separator:
            reference, callable_name = raw_spec, "register"
        if not reference or not callable_name:
            raise ValueError(
                f"Invalid plugin specification {raw_spec!r}; "
                "expected module:callable or path.py:callable"
            )
        before_metrics = set(metric_registry.names())
        before_profiles = set(validation_profiles.names())
        module = _load_module(reference)
        registration = getattr(module, callable_name, None)
        if not callable(registration):
            raise AttributeError(
                f"Plugin {raw_spec!r} has no callable {callable_name!r}"
            )
        result: Any = registration(context)
        if result is not None:
            raise TypeError(
                f"Plugin {raw_spec!r} must return None; got {type(result).__name__}"
            )
        loaded.append(
            LoadedPlugin(
                spec=raw_spec,
                module=module.__name__,
                callable_name=callable_name,
                metrics_added=tuple(
                    name for name in metric_registry.names() if name not in before_metrics
                ),
                validation_profiles_added=tuple(
                    name
                    for name in validation_profiles.names()
                    if name not in before_profiles
                ),
            )
        )
    return loaded


def plugin_manifest(plugins: list[LoadedPlugin]) -> list[dict[str, Any]]:
    """Convert loaded plugin records into JSON-safe report entries."""

    return [asdict(plugin) for plugin in plugins]
