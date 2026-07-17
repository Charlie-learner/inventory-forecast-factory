"""Standalone capability replication, validation, and human-review manifest."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from inventory_agent.codegen.generator import SafeCodeGenerator
from inventory_agent.codegen.validator import GeneratedCodeValidator
from inventory_agent.domain import CapabilitySpec
from inventory_agent.execution import get_execution_profile
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.llm.client import LLMClient
from inventory_agent.services.performance import (
    analyze_generated_performance,
    write_performance_analysis,
)


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
        candidate_count: int = 3,
        max_workers: int | None = None,
    ) -> dict:
        """Generate multiple implementations, validate them, and persist a decision."""

        registered_models = set(default_registry().names())
        resolved_reference = reference_model
        if resolved_reference is None and spec.template_name in registered_models:
            resolved_reference = spec.template_name

        workers = max_workers or get_execution_profile("balanced").generation_workers
        generated_candidates = self.generator.generate_candidates_from_spec(
            spec,
            output_dir,
            llm=llm,
            candidate_count=candidate_count,
            max_workers=workers,
            generation_context={
                "workflow": "standalone_capability_replication",
                "reference_model": resolved_reference,
                "human_approval_requested": approved,
            },
        )
        def validate_candidate(generated_candidate):
            return generated_candidate, self.validator.validate(
                generated_candidate.path,
                reference_model=resolved_reference,
                reference_parameters=(spec.parameters if resolved_reference else None),
            )

        if len(generated_candidates) > 1:
            with ThreadPoolExecutor(
                max_workers=min(workers, len(generated_candidates)),
                thread_name_prefix="replication-validation",
            ) as executor:
                validation_results = list(
                    executor.map(validate_candidate, generated_candidates)
                )
        else:
            validation_results = [validate_candidate(generated_candidates[0])]
        candidate_records = []
        ranked = []
        for generated_candidate, candidate_validation in validation_results:
            record = {
                "variant_id": generated_candidate.variant_id,
                "strategy": generated_candidate.strategy,
                "path": str(generated_candidate.path),
                "mode": generated_candidate.generation_mode,
                "source_hash": generated_candidate.source_hash,
                "prompt_hash": generated_candidate.prompt_hash,
                "collaboration": generated_candidate.collaboration,
                "validation": asdict(candidate_validation),
                "selected": False,
            }
            candidate_records.append(record)
            if candidate_validation.valid:
                ranked.append(
                    (
                        float(
                            candidate_validation.mean_latency_ms
                            or float("inf")
                        ),
                        float(
                            candidate_validation.peak_memory_kb
                            or float("inf")
                        ),
                        len(generated_candidate.source),
                        generated_candidate.source_hash,
                        generated_candidate,
                        candidate_validation,
                    )
                )
        if ranked:
            ranked.sort(key=lambda item: item[:4])
            generated = ranked[0][4]
            validation = ranked[0][5]
        else:
            generated = generated_candidates[0]
            validation = self.validator.validate(
                generated.path,
                reference_model=resolved_reference,
                reference_parameters=(
                    spec.parameters if resolved_reference else None
                ),
            )
        for record in candidate_records:
            record["selected"] = record["source_hash"] == generated.source_hash
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
        performance = analyze_generated_performance(
            generated.path,
            asdict(validation),
            candidate_records,
        )
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
                "variant_id": generated.variant_id,
                "strategy": generated.strategy,
                "prompt_hash": generated.prompt_hash,
                "collaboration": generated.collaboration,
            },
            "multi_agent_collaboration": {
                "protocol": "architecture -> parallel implementation -> independent review -> validation",
                "roles": [
                    "CodeArchitectureAgent",
                    "CodeImplementationAgent",
                    "CodeReviewAgent",
                    "GeneratedCodeValidator",
                ],
                "blueprint_path": str(Path(output_dir) / "implementation_blueprint.json"),
                "manifest_path": str(Path(output_dir) / "multi_agent_collaboration.json"),
            },
            "implementation_candidates": candidate_records,
            "validation": asdict(validation),
            "performance_analysis": performance,
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
        performance_path = write_performance_analysis(
            performance,
            json_path.with_name(f"{json_path.stem}_performance.json"),
        )
        self._write_markdown(manifest, json_path.with_suffix(".md"))
        manifest["manifest_paths"] = {
            "json": str(json_path),
            "performance": str(performance_path),
            "markdown": str(json_path.with_suffix(".md")),
            "collaboration": str(
                Path(output_dir) / "multi_agent_collaboration.json"
            ),
            "blueprint": str(Path(output_dir) / "implementation_blueprint.json"),
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
        collaboration = manifest.get("multi_agent_collaboration", {})
        markdown = "\n".join(
            [
                "# 能力复刻审核清单",
                "",
                f"- 能力：{manifest['capability']['name']}:{manifest['capability']['version']}",
                f"- 生成方式：{generation['mode']}",
                f"- 生成文件：{generation['path']}",
                f"- 规格哈希：{generation['spec_hash']}",
                f"- 源码哈希：{generation['source_hash']}",
                f"- 实现候选：{len(manifest.get('implementation_candidates', []))}",
                f"- 选中候选：{generation.get('variant_id', '-')}",
                f"- 生成策略：{generation.get('strategy', '-')}",
                f"- 参考能力：{manifest['reference_model'] or '无'}",
                f"- 自动验证：{'通过' if validation['valid'] else '失败'}",
                f"- 检查项：{validation['checks']}",
                f"- 等价用例数：{validation['equivalence_cases']}",
                f"- 最大等价误差：{validation['equivalence_max_error']}",
                f"- 平均预测延迟：{validation.get('mean_latency_ms')} ms",
                f"- Python 内存峰值：{validation.get('peak_memory_kb')} KB",
                f"- 审核状态：{review['status']}",
                f"- 可注册：{review['registration_ready']}",
                f"- 判定依据：{review['reason']}",
                "",
                "## 多智能体协作",
                "",
                f"- 协作协议：{collaboration.get('protocol', '-')}",
                f"- 参与角色：{', '.join(collaboration.get('roles', [])) or '-'}",
                f"- 实现蓝图：{collaboration.get('blueprint_path', '-')}",
                f"- 完整协作记录：{collaboration.get('manifest_path', '-')}",
                "",
                "## 验证错误",
                "",
                *(f"- {error}" for error in validation["errors"]),
                "",
                "## 实现候选比较",
                "",
                "| 候选 | 策略 | 验证 | 平均延迟(ms) | 内存峰值(KB) | 选中 |",
                "|---|---|---|---:|---:|---|",
                *(
                    f"| {candidate['variant_id']} | {candidate['strategy']} | "
                    f"{'通过' if candidate['validation']['valid'] else '失败'} | "
                    f"{candidate['validation'].get('mean_latency_ms') or '-'} | "
                    f"{candidate['validation'].get('peak_memory_kb') or '-'} | "
                    f"{candidate['selected']} |"
                    for candidate in manifest.get(
                        "implementation_candidates", []
                    )
                ),
            ]
        )
        path.write_text(markdown + "\n", encoding="utf-8")
