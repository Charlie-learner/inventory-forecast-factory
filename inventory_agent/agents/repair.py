"""Repair invalid generated capabilities using a known-safe implementation contract."""

from __future__ import annotations

from pathlib import Path
import json
import hashlib

from inventory_agent.codegen.generator import GeneratedCapability, SafeCodeGenerator
from inventory_agent.domain import CapabilitySpec
from inventory_agent.llm.client import LLMClient, MockLLMClient
from inventory_agent.validation.failures import FailureAnalysis, FailureAnalyzer


class RepairAgent:
    """Regenerate a capability from the safe template after validation failure."""

    def __init__(
        self,
        generator: SafeCodeGenerator | None = None,
        llm: LLMClient | None = None,
    ):
        self.generator = generator or SafeCodeGenerator()
        self.llm = llm or MockLLMClient()
        self.failure_analyzer = FailureAnalyzer()

    def analyze(
        self, errors: tuple[str, ...], checks: dict[str, bool] | None = None
    ) -> FailureAnalysis:
        """Normalize a validation failure before selecting a repair strategy."""

        return self.failure_analyzer.analyze(errors, checks)

    @staticmethod
    def _source_from_response(response: str) -> str:
        """Strip an optional Markdown fence from an LLM code response."""

        source = response.strip()
        if source.startswith("```"):
            lines = source.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            source = "\n".join(lines).strip()
        if not source:
            raise ValueError("LLM repair returned empty source")
        return source + "\n"

    def repair(
        self,
        model: str,
        errors: tuple[str, ...],
        output_dir: str | Path,
        attempt: int = 1,
        current: GeneratedCapability | None = None,
        capability_spec: CapabilitySpec | None = None,
        prior_experience: list[dict] | None = None,
    ) -> tuple[GeneratedCapability, str]:
        """Regenerate the selected model and record this repair attempt."""

        if attempt <= 0:
            raise ValueError("repair attempt must be positive")
        analysis = self.analyze(errors)
        categories = [analysis.category]
        prior_experience = prior_experience or []
        use_llm_repair = attempt == 1 and current is not None and not isinstance(
            self.llm, MockLLMClient
        )
        strategy = "LLM 按错误修复源码" if use_llm_repair else "受约束安全模板回退"
        reason = (
            f"第 {attempt} 轮修复（{strategy}，错误类型={','.join(categories) or 'unknown'}）: "
            + "; ".join(errors)
        )
        reason += f" [failure_fingerprint={analysis.fingerprint}]"
        if prior_experience:
            reason += f" [reused_successful_repairs={len(prior_experience)}]"
        if use_llm_repair:
            try:
                response = self.llm.complete(
                    "你是代码修复 Agent。只返回完整 Python 源码，不要解释。保留 forecast(history, horizon) "
                    "和 build_inventory_target(history, horizon) 接口，不得访问文件、网络或环境变量。",
                    json.dumps(
                        {
                            "model": model,
                            "errors": errors,
                            "failure": analysis.__dict__,
                            "prior_successful_repairs": prior_experience,
                            "source": current.source,
                        },
                        ensure_ascii=False,
                    ),
                )
                source = self._source_from_response(response)
                output = Path(output_dir) / f"forecast_{model}.py"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(source, encoding="utf-8")
                return (
                    GeneratedCapability(
                        model,
                        source,
                        output,
                        "llm_repair",
                        current.spec_hash,
                        hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    ),
                    reason,
                )
            except Exception as exc:  # Provider failure must not break the repair loop.
                reason += f"；LLM 修复不可用（{type(exc).__name__}），改用安全模板"
        generated = (
            self.generator.generate_from_spec(capability_spec, output_dir)
            if capability_spec is not None
            else self.generator.generate(model, output_dir)
        )
        return generated, reason
