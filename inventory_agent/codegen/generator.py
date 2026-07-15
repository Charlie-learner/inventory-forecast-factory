"""Generate auditable Python capability modules from validated model plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedCapability:
    model: str
    source: str
    path: Path
    generation_mode: str = "constrained_template"


class SafeCodeGenerator:
    """Template-constrained generator; model choice comes from the Agent plan."""

    TEMPLATE = '''"""Generated inventory forecasting capability. Do not edit manually."""

from __future__ import annotations

import pandas as pd

from inventory_agent.forecasting.registry import default_registry

MODEL_NAME = {model_name!r}


def forecast(history: list[float], horizon: int) -> list[float]:
    """Forecast non-negative daily demand through the standard model registry."""
    series = pd.Series(history, dtype=float)
    model = default_registry().create(MODEL_NAME)
    return model.predict(series, horizon).tolist()


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return explainable daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {{
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }}
'''

    def generate(self, model: str, output_dir: str | Path) -> GeneratedCapability:
        safe_name = "".join(character for character in model if character.isalnum() or character == "_")
        if safe_name != model or not safe_name:
            raise ValueError(f"Unsafe model name: {model!r}")
        source = self.TEMPLATE.format(model_name=model)
        output = Path(output_dir) / f"forecast_{safe_name}.py"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(source, encoding="utf-8")
        return GeneratedCapability(model, source, output)
