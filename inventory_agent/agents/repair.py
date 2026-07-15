"""Repair invalid generated capabilities using a known-safe implementation contract."""

from __future__ import annotations

from pathlib import Path

from inventory_agent.codegen.generator import GeneratedCapability, SafeCodeGenerator


class RepairAgent:
    def __init__(self, generator: SafeCodeGenerator | None = None):
        self.generator = generator or SafeCodeGenerator()

    def repair(
        self,
        model: str,
        errors: tuple[str, ...],
        output_dir: str | Path,
    ) -> tuple[GeneratedCapability, str]:
        reason = "根据验证错误重新生成受约束实现: " + "; ".join(errors)
        generated = self.generator.generate(model, output_dir)
        return generated, reason

