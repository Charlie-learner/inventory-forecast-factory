"""Multi-agent protocol for planning and reviewing generated algorithm code."""

from __future__ import annotations

import ast
import json
import logging
from dataclasses import asdict
from typing import Any

from inventory_agent.domain import CapabilitySpec
from inventory_agent.llm.client import LLMClient, MockLLMClient


logger = logging.getLogger(__name__)


def _json_payload(response: str) -> dict[str, Any]:
    """Parse one JSON object, tolerating a single Markdown fence."""

    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("agent response must be a JSON object")
    return value


class CodeArchitectureAgent:
    """Convert a capability specification into a constrained implementation blueprint."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def design(self, spec: CapabilitySpec, context: dict[str, Any]) -> dict[str, Any]:
        """Return a reviewable blueprint with deterministic provider fallback."""

        blueprint = {
            "agent": "CodeArchitectureAgent",
            "mode": "deterministic",
            "algorithm": spec.template_name,
            "algorithm_steps": [
                "normalize history to finite non-negative numeric observations",
                f"apply {spec.template_name} semantics using declared parameters",
                "produce exactly horizon non-negative float values",
                "sum the daily forecast into target_inventory",
            ],
            "required_contracts": [
                "forecast(history, horizon) -> list[float]",
                "build_inventory_target(history, horizon) -> dict",
                "target_inventory == sum(daily_forecast)",
            ],
            "edge_cases": ["empty history", "non-positive horizon", "all-zero history"],
            "allowed_dependencies": list(spec.dependencies),
            "performance_goal": "avoid repeated full-history copies and unnecessary nested loops",
            "risks": list(spec.extraction_warnings),
        }
        if isinstance(self.llm, MockLLMClient):
            return blueprint
        try:
            response = self.llm.complete(
                "你是算法架构 Agent。只返回 JSON 对象，字段为 algorithm_steps、"
                "required_contracts、edge_cases、allowed_dependencies、performance_goal、"
                "risks。根据能力规格设计实现蓝图，不输出 Python 代码，不改变算法语义。",
                json.dumps(
                    {"capability_spec": asdict(spec), "business_context": context},
                    ensure_ascii=False,
                    default=str,
                ),
            )
            proposed = _json_payload(response)
            for key in (
                "algorithm_steps",
                "required_contracts",
                "edge_cases",
                "allowed_dependencies",
                "risks",
            ):
                value = proposed.get(key)
                if isinstance(value, list):
                    blueprint[key] = [str(item) for item in value][:12]
            if proposed.get("performance_goal"):
                blueprint["performance_goal"] = str(proposed["performance_goal"])
            blueprint["mode"] = "llm_architecture"
        except Exception as exc:
            logger.warning("Architecture Agent fallback: %s", type(exc).__name__)
            blueprint["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        return blueprint


class CodeImplementationAgent:
    """Define the bounded implementation role used for each code candidate."""

    @staticmethod
    def system_prompt() -> str:
        """Return stable role instructions shared by independently generated variants."""

        return (
            "You are the implementation member of a multi-agent algorithm engineering team. "
            "Return only a complete Python module, with no Markdown or explanation. Implement "
            "the supplied CapabilitySpec and architecture blueprint independently; do not import "
            "inventory_agent internals or copy a registered implementation. Provide "
            "forecast(history, horizon) returning a built-in list[float], and "
            "build_inventory_target(history, horizon) returning a dict whose target_inventory "
            "equals the sum of daily_forecast. Outputs must be deterministic, finite and "
            "non-negative. Only Python, numpy, pandas and sklearn are allowed. Never access "
            "files, networks, environment variables, processes, dynamic code execution, or "
            "hard-coded validation examples. Follow the assigned strategy without weakening "
            "the shared contracts."
        )


class CodeReviewAgent:
    """Review one implementation against the blueprint and optionally revise it."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    @staticmethod
    def _static_findings(source: str) -> list[str]:
        findings = []
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return [f"syntax error: {exc.msg}"]
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for expected in ("forecast", "build_inventory_target"):
            if expected not in functions:
                findings.append(f"missing required function: {expected}")
        if "forecast" in functions:
            arguments = [item.arg for item in functions["forecast"].args.args]
            if arguments != ["history", "horizon"]:
                findings.append("forecast signature must be (history, horizon)")
        return findings

    def review(
        self,
        spec: CapabilitySpec,
        source: str,
        blueprint: dict[str, Any],
        variant_id: str,
    ) -> tuple[str, dict[str, Any]]:
        """Return reviewed source and an auditable review decision."""

        static_findings = self._static_findings(source)
        review = {
            "agent": "CodeReviewAgent",
            "variant_id": variant_id,
            "mode": "deterministic",
            "approved": not static_findings,
            "findings": static_findings,
            "revision_applied": False,
        }
        if isinstance(self.llm, MockLLMClient):
            return source, review
        try:
            response = self.llm.complete(
                "你是独立代码审查与修订 Agent。只返回 JSON：approved(bool)、findings(array)、"
                "revised_source(string)。逐项核对架构蓝图、算法语义和接口。特别检查 forecast "
                "必须返回 Python list[float]，不能返回 ndarray、Series 或标量；"
                "build_inventory_target 必须返回含 daily_forecast 列表和 target_inventory 浮点数"
                "的 dict。若发现任何问题，revised_source 必须给出修复后的完整 Python 源码；"
                "若无问题可原样返回。不得弱化安全限制或硬编码测试数据。",
                json.dumps(
                    {
                        "capability_spec": asdict(spec),
                        "blueprint": blueprint,
                        "variant_id": variant_id,
                        "static_findings": static_findings,
                        "source": source,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            proposed = _json_payload(response)
            revised = str(proposed.get("revised_source", "")).strip()
            if revised.startswith("```"):
                lines = revised.splitlines()[1:]
                if lines and lines[-1].strip() == "```":
                    lines.pop()
                revised = "\n".join(lines).strip()
            findings = proposed.get("findings", static_findings)
            review.update(
                {
                    "mode": "llm_review",
                    "approved": bool(proposed.get("approved", False)),
                    "findings": (
                        [str(item) for item in findings][:12]
                        if isinstance(findings, list)
                        else static_findings
                    ),
                }
            )
            if revised:
                revised = revised + ("" if revised.endswith("\n") else "\n")
                review["revision_applied"] = revised != source
                source = revised
        except Exception as exc:
            logger.warning(
                "Code review Agent fallback for %s: %s",
                variant_id,
                type(exc).__name__,
            )
            review["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        review["post_review_static_findings"] = self._static_findings(source)
        return source, review
