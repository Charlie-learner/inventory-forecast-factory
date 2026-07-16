import json
from pathlib import Path

import numpy as np

from inventory_agent.cli import main
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.validation.metrics import default_metric_registry, forecast_metrics
from inventory_agent.validation.profiles import default_validation_profiles


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "examples/plugins/stockout_priority.py"


def test_local_plugin_registers_metric_and_validation_profile():
    metrics = default_metric_registry()
    profiles = default_validation_profiles()

    loaded = load_plugins(
        [f"{PLUGIN}:register"],
        metrics,
        profiles,
    )

    assert loaded[0].metrics_added == ("underforecast_rate",)
    assert loaded[0].validation_profiles_added == ("stockout_priority",)
    assert profiles.get("stockout_priority").primary_metric == "underforecast_rate"
    result = forecast_metrics(
        np.array([10.0, 5.0]),
        np.array([7.0, 6.0]),
        registry=metrics,
    )
    assert result["underforecast_rate"] == 0.2
    assert plugin_manifest(loaded)[0]["spec"].endswith(":register")


def test_plugins_cli_prints_auditable_registry(capsys, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")

    exit_code = main(["plugins", "--plugin", f"{PLUGIN}:register"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "underforecast_rate" in payload["metrics"]
    assert "stockout_priority" in payload["validation_profiles"]
    assert payload["loaded_plugins"][0]["metrics_added"] == ["underforecast_rate"]
