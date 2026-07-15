"""Small LLM abstraction that keeps API credentials out of logs and artifacts."""

from __future__ import annotations

import json
from typing import Protocol

from inventory_agent.config import Settings


class LLMClient(Protocol):
    """Define the completion interface shared by offline and API adapters."""

    def complete(self, system: str, user: str) -> str:
        """Return a text completion for system and user messages."""

        ...


class MockLLMClient:
    """Deterministic offline adapter used by tests and the default demo."""

    def complete(self, system: str, user: str) -> str:
        """Return a deterministic JSON response without making a network request."""

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
    """Call an OpenAI-compatible chat completion endpoint."""

    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise ValueError("API key is required for API mode")
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._model = settings.model

    def complete(self, system: str, user: str) -> str:
        """Submit one chat completion request and return its text content."""

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


def create_llm(settings: Settings) -> LLMClient:
    """Create the configured API client or the deterministic mock client."""

    if settings.llm_mode == "api":
        return OpenAICompatibleClient(settings)
    return MockLLMClient()
