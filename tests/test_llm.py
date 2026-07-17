from inventory_agent.config import Settings
from inventory_agent.llm.client import verify_llm_connection


class _LiveClient:
    def complete(self, system: str, user: str) -> str:
        assert "connectivity checker" in system
        assert "INVENTORY_LLM_OK" in user
        return "INVENTORY_LLM_OK"


def test_live_llm_verification_is_secret_safe():
    settings = Settings(
        llm_mode="api",
        model="provider-model",
        base_url="https://provider.example/v1",
        api_key="never-output-this-secret",
    )

    result = verify_llm_connection(settings, client=_LiveClient())

    assert result["status"] == "passed"
    assert result["api_key_exposed"] is False
    assert "never-output-this-secret" not in str(result)
    assert result["latency_ms"] >= 0
