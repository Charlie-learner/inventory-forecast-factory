"""Small LLM abstraction that keeps API credentials out of logs and artifacts."""

from __future__ import annotations

import json
from typing import Protocol

from inventory_agent.config import Settings


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """Deterministic offline adapter used by tests and the default demo."""

    def complete(self, system: str, user: str) -> str:
        del system
        return json.dumps(
            {
                "mode": "mock",
                "summary": "使用可复现规则完成需求理解、模型检索与验证。",
                "input_excerpt": user[:120],
            },
            ensure_ascii=False,
        )


class OpenAICompatibleClient:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise ValueError("API key is required for API mode")
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._model = settings.model

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


def create_llm(settings: Settings) -> LLMClient:
    if settings.llm_mode == "api":
        return OpenAICompatibleClient(settings)
    return MockLLMClient()
