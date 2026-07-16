"""Standalone capability replication, validation, and human-review manifest."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.domain import CapabilitySpec
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.llm.client import LLMClient


class CapabilityReplicator:
    """Turn one extracted specification into validated code outside the business workflow."""

    def __init__(
        self,
        generator: SafeCodeGenerator | None = None,
        validator: GeneratedCodeValidator | None = None,
    ) -> None:
        self.generator = generator or SafeCodeGenerator()
        self.validator = validator or GeneratedCodeValidator()

    def replicate(
        self,
        spec: CapabilitySpec,
        output_dir: str | Path,
        manifest_path: str | Path,
        *,
        llm: LLMClient | None = None,
        reference_model: str | None = None,
        approved: bool = False,
    ) -> dict:
        """Generate code, validate it, and persist an auditable registration decision."""

        registered_models = set(default_registry().names())
        resolved_reference = reference_model
        if resolved_reference is None and spec.template_name in registered_models:
            resolved_reference = spec.template_name

        generated = self.generator.generate_from_spec(spec, output_dir, llm=llm)
        validation = self.validator.validate(
            generated.path,
            reference_model=resolved_reference,
            reference_parameters=spec.parameters if resolved_reference else None,
        )
        equivalent = validation.checks.get("equivalence", False)
        if not validation.valid:
            review_status = "rejected"
        elif approved:
            review_status = "approved"
        elif equivalent:
            review_status = "auto_validated"
        else:
            review_status = "review_required"

        registration_ready = validation.valid and (approved or equivalent)
        manifest = {
            "schema_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "capability": asdict(spec),
            "generation": {
                "model": generated.model,
                "path": str(generated.path),
                "mode": generated.generation_mode,
                "spec_hash": generated.spec_hash,
                "source_hash": generated.source_hash,
            },
            "validation": asdict(validation),
            "reference_model": resolved_reference,
            "review": {
                "status": review_status,
                "approved_by_user": approved,
                "registration_ready": registration_ready,
                "reason": self._review_reason(
                    validation.valid, equivalent, approved, resolved_reference
                ),
            },
        }
        json_path = Path(manifest_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._write_markdown(manifest, json_path.with_suffix(".md"))
        manifest["manifest_paths"] = {
            "json": str(json_path),
            "markdown": str(json_path.with_suffix(".md")),
        }
        return manifest

    @staticmethod
    def _review_reason(
        valid: bool,
        equivalent: bool,
        approved: bool,
        reference_model: str | None,
    ) -> str:
        if not valid:
            return "Generated implementation failed automated validation."
        if approved:
            return "Automated validation passed and a user explicitly approved registration."
        if equivalent:
            return f"Behavior matches registered reference capability {reference_model}."
        return "Safety and runtime checks passed, but semantic review is still required."

    @staticmethod
    def _write_markdown(manifest: dict, path: Path) -> None:
        validation = manifest["validation"]
        review = manifest["review"]
        generation = manifest["generation"]
        markdown = "\n".join(
            [
                "# 能力复刻审核清单",
                "",
                f"- 能力：{manifest['capability']['name']}:{manifest['capability']['version']}",
                f"- 生成方式：{generation['mode']}",
                f"- 生成文件：{generation['path']}",
                f"- 规格哈希：{generation['spec_hash']}",
                f"- 源码哈希：{generation['source_hash']}",
                f"- 参考能力：{manifest['reference_model'] or '无'}",
                f"- 自动验证：{'通过' if validation['valid'] else '失败'}",
                f"- 检查项：{validation['checks']}",
                f"- 等价用例数：{validation['equivalence_cases']}",
                f"- 最大等价误差：{validation['equivalence_max_error']}",
                f"- 审核状态：{review['status']}",
                f"- 可注册：{review['registration_ready']}",
                f"- 判定依据：{review['reason']}",
                "",
                "## 验证错误",
                "",
                *(f"- {error}" for error in validation["errors"]),
            ]
        )
        path.write_text(markdown + "\n", encoding="utf-8")
