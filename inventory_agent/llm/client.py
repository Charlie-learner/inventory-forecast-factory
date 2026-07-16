"""Small LLM abstraction that keeps API credentials out of logs and artifacts."""

from __future__ import annotations

import json
from typing import Any, Protocol

from inventory_agent.config import Settings


class LLMClient(Protocol):
    """Define the completion interface shared by offline and API adapters."""

    def complete(self, system: str, user: str) -> str:
        """Return a text completion for system and user messages."""

        ...


class _TraceableClient:
    """Attach a per-run recorder without changing the LLM completion contract."""

    def __init__(self) -> None:
        self._trace_recorder: Any = None

    def set_trace_recorder(self, recorder: Any) -> None:
        """Enable or clear detailed call recording for the current workflow run."""

        self._trace_recorder = recorder

    def _record_completion(
        self,
        system: str,
        user: str,
        *,
        status: str,
        response: str | None = None,
        error: str | None = None,
    ) -> None:
        if self._trace_recorder is None:
            return
        self._trace_recorder.record(
            stage="llm",
            component=type(self).__name__,
            component_type="tool",
            action="complete",
            status=status,
            inputs={"system_prompt": system, "user_prompt": user},
            outputs={"response": response, "error": error},
        )


class MockLLMClient(_TraceableClient):
    """Deterministic offline adapter used by tests and the default demo."""

    def __init__(self) -> None:
        super().__init__()

    def complete(self, system: str, user: str) -> str:
        """Return a deterministic JSON response without making a network request."""

        response = json.dumps(
            {
                "mode": "mock",
                "summary": "使用可复现规则完成需求理解、模型检索与验证。",
                "input_excerpt": user[:120],
            },
            ensure_ascii=False,
        )
        self._record_completion(system, user, status="success", response=response)
        return response


class OpenAICompatibleClient(_TraceableClient):
    """Call an OpenAI-compatible chat completion endpoint."""

    def __init__(self, settings: Settings):
        super().__init__()
        if not settings.api_key:
            raise ValueError("API key is required for API mode")
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._model = settings.model

    def complete(self, system: str, user: str) -> str:
        """Submit one chat completion request and return its text content."""

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = response.choices[0].message.content or ""
            self._record_completion(system, user, status="success", response=content)
            return content
        except Exception as exc:
            self._record_completion(
                system,
                user,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise


def create_llm(settings: Settings) -> LLMClient:
    """Create the configured API client or the deterministic mock client."""

    if settings.llm_mode == "api":
        return OpenAICompatibleClient(settings)
    return MockLLMClient()
