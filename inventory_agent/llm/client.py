"""Small LLM abstraction that keeps API credentials out of logs and artifacts."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from inventory_agent.config import Settings


logger = logging.getLogger(__name__)


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

        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
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
            logger.warning("LLM completion failed: %s", type(exc).__name__)
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


def verify_llm_connection(
    settings: Settings,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Make one minimal completion request and return secret-safe evidence."""

    if settings.llm_mode != "api":
        raise ValueError("Live LLM verification requires LLM_MODE=api")
    issues = settings.validate()
    if issues:
        raise ValueError("; ".join(issues))
    llm = client or create_llm(settings)
    started = time.perf_counter()
    response = llm.complete(
        "You are a connectivity checker. Follow the response format exactly.",
        "Reply with exactly: INVENTORY_LLM_OK",
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    normalized = response.strip()
    return {
        "status": "passed" if "INVENTORY_LLM_OK" in normalized else "unexpected_response",
        "provider_type": "openai_compatible",
        "model": settings.model,
        "base_url": settings.base_url,
        "latency_ms": latency_ms,
        "response_excerpt": normalized[:120],
        "api_key_exposed": False,
    }
