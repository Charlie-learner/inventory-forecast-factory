"""Generate auditable capability modules from extracted algorithm specifications."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from inventory_agent.domain import CapabilitySpec
from inventory_agent.llm.client import LLMClient, MockLLMClient


@dataclass(frozen=True)
class GeneratedCapability:
    """Describe generated source, provenance hashes, and its output location."""

    model: str
    source: str
    path: Path
    generation_mode: str = "spec_template"
    spec_hash: str = ""
    source_hash: str = ""


class SafeCodeGenerator:
    """Generate self-contained implementations from approved capability templates or an LLM."""

    TEMPLATE_BODIES = {
        "last_value": """    return [float(series.iloc[-1])] * horizon""",
        "moving_average": """    window = int(PARAMETERS.get("window", 14))
    if window <= 0:
        raise ValueError("window must be positive")
    window = min(window, len(series))
    return [float(series.iloc[-window:].mean())] * horizon""",
        "seasonal_naive": """    period = int(PARAMETERS.get("period", 7))
    if period <= 0:
        raise ValueError("period must be positive")
    if len(series) < period:
        return [float(series.mean())] * horizon
    pattern = series.iloc[-period:].tolist()
    return [float(pattern[index % period]) for index in range(horizon)]""",
        "croston": """    alpha = float(PARAMETERS.get("alpha", 0.1))
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    values = series.tolist()
    nonzero_positions = [index for index, value in enumerate(values) if value > 0]
    if not nonzero_positions:
        return [0.0] * horizon
    first = nonzero_positions[0]
    demand_estimate = values[first]
    interval_estimate = float(first + 1)
    interval = 1
    for value in values[first + 1:]:
        if value > 0:
            demand_estimate += alpha * (value - demand_estimate)
            interval_estimate += alpha * (interval - interval_estimate)
            interval = 1
        else:
            interval += 1
    value = max(float(demand_estimate / max(interval_estimate, 1e-12)), 0.0)
    return [value] * horizon""",
        "ridge_lag": """    lags = int(PARAMETERS.get("lags", 14))
    alpha = float(PARAMETERS.get("alpha", 1.0))
    if lags <= 0 or alpha < 0:
        raise ValueError("lags must be positive and alpha non-negative")
    if len(series) <= lags + 2:
        window = min(14, len(series))
        return [float(series.iloc[-window:].mean())] * horizon
    values = series.to_numpy(dtype=float)
    features = np.array([values[index - lags:index] for index in range(lags, len(values))])
    target = values[lags:]
    model = Ridge(alpha=alpha)
    model.fit(features, target)
    buffer = values.tolist()
    predictions = []
    for _ in range(horizon):
        feature = np.asarray(buffer[-lags:], dtype=float).reshape(1, -1)
        prediction = max(float(model.predict(feature)[0]), 0.0)
        predictions.append(prediction)
        buffer.append(prediction)
    return predictions""",
    }

    BASE_TEMPLATE = '''"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

__EXTRA_IMPORTS__import pandas as pd

CAPABILITY_NAME = __CAPABILITY_NAME__
CAPABILITY_SPEC = __CAPABILITY_SPEC__
PARAMETERS = __PARAMETERS__


def _clean_history(history: list[float], horizon: int) -> pd.Series:
    """Validate the shared forecasting input contract."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    series = pd.to_numeric(pd.Series(history), errors="coerce").dropna().astype(float)
    if series.empty:
        raise ValueError("history must contain at least one numeric observation")
    return series.clip(lower=0)


def forecast(history: list[float], horizon: int) -> list[float]:
    """Replicate the extracted capability as non-negative daily forecasts."""
    series = _clean_history(history, horizon)
__FORECAST_BODY__


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
'''

    @staticmethod
    def _safe_name(name: str) -> str:
        safe_name = "".join(
            character for character in name if character.isalnum() or character == "_"
        )
        if safe_name != name or not safe_name:
            raise ValueError(f"Unsafe model name: {name!r}")
        return safe_name

    @staticmethod
    def _strip_code_fence(response: str) -> str:
        source = response.strip()
        if source.startswith("```"):
            lines = source.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            source = "\n".join(lines).strip()
        if not source:
            raise ValueError("LLM generation returned empty source")
        return source + "\n"

    def _render_spec_template(self, spec: CapabilitySpec) -> str:
        try:
            body = self.TEMPLATE_BODIES[spec.template_name]
        except KeyError as exc:
            raise KeyError(
                f"No safe template for {spec.template_name!r}; "
                f"available={sorted(self.TEMPLATE_BODIES)}"
            ) from exc
        extra_imports = ""
        if spec.template_name == "ridge_lag":
            extra_imports = "import numpy as np\nfrom sklearn.linear_model import Ridge\n\n"
        spec_payload = asdict(spec)
        return (
            self.BASE_TEMPLATE.replace("__EXTRA_IMPORTS__", extra_imports)
            .replace("__CAPABILITY_NAME__", repr(spec.name))
            .replace("__CAPABILITY_SPEC__", repr(spec_payload))
            .replace("__PARAMETERS__", repr(spec.parameters))
            .replace("__FORECAST_BODY__", body)
        )

    def generate_from_spec(
        self,
        spec: CapabilitySpec,
        output_dir: str | Path,
        llm: LLMClient | None = None,
    ) -> GeneratedCapability:
        """Generate initial code with an LLM when configured, otherwise use a safe template."""

        safe_name = self._safe_name(spec.name)
        spec_json = json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True, default=str)
        spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
        generation_mode = "spec_template"
        source = ""
        if llm is not None and not isinstance(llm, MockLLMClient):
            try:
                response = llm.complete(
                    "你是算法能力复刻 Agent。只返回完整 Python 源码。严格实现给定 CapabilitySpec，"
                    "必须提供 forecast(history, horizon) 和 build_inventory_target(history, horizon)，"
                    "不得访问文件、网络、环境变量或执行动态代码。",
                    spec_json,
                )
                source = self._strip_code_fence(response)
                generation_mode = "llm_generation"
            except Exception:
                generation_mode = "spec_template_fallback"
        if not source:
            source = self._render_spec_template(spec)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        output = Path(output_dir) / f"forecast_{safe_name}.py"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(source, encoding="utf-8")
        return GeneratedCapability(
            spec.name,
            source,
            output,
            generation_mode,
            spec_hash,
            source_hash,
        )

    def generate(self, model: str, output_dir: str | Path) -> GeneratedCapability:
        """Generate from a minimal registered-model spec for backwards compatibility."""

        spec = CapabilitySpec(
            name=model,
            task_type="inventory_forecasting",
            description=f"Registered forecasting capability {model}",
            template_name=model,
            input_contract="non-negative daily demand history and positive horizon",
            output_contract="non-negative daily forecast and horizon-total target inventory",
        )
        return self.generate_from_spec(spec, output_dir)
