from inventory_agent.config import Settings


def test_mock_mode_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings.from_env(load_dotenv=False)
    assert settings.validate() == []


def test_api_mode_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "api")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings.from_env(load_dotenv=False)
    assert "API_KEY is required when LLM_MODE=api." in settings.validate()


def test_llm_timeout_is_bounded():
    settings = Settings(llm_timeout_seconds=0)

    assert "LLM_TIMEOUT_SECONDS must be between 1 and 300." in settings.validate()
