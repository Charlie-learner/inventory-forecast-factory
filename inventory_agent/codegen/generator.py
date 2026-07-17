"""Generate auditable capability modules from extracted algorithm specifications."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from inventory_agent.agents.code_collaboration import (
    CodeArchitectureAgent,
    CodeImplementationAgent,
    CodeReviewAgent,
)
from inventory_agent.domain import CapabilitySpec
from inventory_agent.llm.client import LLMClient, MockLLMClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedCapability:
    """Describe generated source, provenance hashes, and its output location."""

    model: str
    source: str
    path: Path
    generation_mode: str = "spec_template"
    spec_hash: str = ""
    source_hash: str = ""
    variant_id: str = "primary"
    strategy: str = "specification_fidelity"
    prompt_hash: str = ""
    collaboration: dict = field(default_factory=dict)


class SafeCodeGenerator:
    """Generate self-contained implementations from approved capability templates or an LLM."""

    TEMPLATE_BODIES = {
        "last_value": """    return [float(series.iloc[-1])] * horizon""",
        "moving_average": """    window = int(PARAMETERS.get("window", 14))
    if window <= 0:
        raise ValueError("window must be positive")
    window = min(window, len(series))
    return [float(series.iloc[-window:].mean())] * horizon""",
        "seasonal_naive": """    period = int(PARAMETERS.get("period", 7))
    if period <= 0:
        raise ValueError("period must be positive")
    if len(series) < period:
        return [float(series.mean())] * horizon
    pattern = series.iloc[-period:].tolist()
    return [float(pattern[index % period]) for index in range(horizon)]""",
        "croston": """    alpha = float(PARAMETERS.get("alpha", 0.1))
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    values = series.tolist()
    nonzero_positions = [index for index, value in enumerate(values) if value > 0]
    if not nonzero_positions:
        return [0.0] * horizon
    first = nonzero_positions[0]
    demand_estimate = values[first]
    interval_estimate = float(first + 1)
    interval = 1
    for value in values[first + 1:]:
        if value > 0:
            demand_estimate += alpha * (value - demand_estimate)
            interval_estimate += alpha * (interval - interval_estimate)
            interval = 1
        else:
            interval += 1
    value = max(float(demand_estimate / max(interval_estimate, 1e-12)), 0.0)
    return [value] * horizon""",
        "ridge_lag": """    lags = int(PARAMETERS.get("lags", 14))
    alpha = float(PARAMETERS.get("alpha", 1.0))
    if lags <= 0 or alpha < 0:
        raise ValueError("lags must be positive and alpha non-negative")
    if len(series) <= lags + 2:
        window = min(14, len(series))
        return [float(series.iloc[-window:].mean())] * horizon
    values = series.to_numpy(dtype=float)
    features = np.array([values[index - lags:index] for index in range(lags, len(values))])
    target = values[lags:]
    model = Ridge(alpha=alpha)
    model.fit(features, target)
    buffer = values.tolist()
    predictions = []
    for _ in range(horizon):
        feature = np.asarray(buffer[-lags:], dtype=float).reshape(1, -1)
        prediction = max(float(model.predict(feature)[0]), 0.0)
        predictions.append(prediction)
        buffer.append(prediction)
    return predictions""",
    }

    BASE_TEMPLATE = '''"""Generated from a source-traceable algorithm capability specification."""

from __future__ import annotations

__EXTRA_IMPORTS__import pandas as pd

CAPABILITY_NAME = __CAPABILITY_NAME__
CAPABILITY_SPEC = __CAPABILITY_SPEC__
PARAMETERS = __PARAMETERS__


def _clean_history(history: list[float], horizon: int) -> pd.Series:
    """Validate the shared forecasting input contract."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    series = pd.to_numeric(pd.Series(history), errors="coerce").dropna().astype(float)
    if series.empty:
        raise ValueError("history must contain at least one numeric observation")
    return series.clip(lower=0)


def forecast(history: list[float], horizon: int) -> list[float]:
    """Replicate the extracted capability as non-negative daily forecasts."""
    series = _clean_history(history, horizon)
__FORECAST_BODY__


def build_inventory_target(history: list[float], horizon: int) -> dict[str, object]:
    """Return daily demand and the horizon-total target inventory."""
    daily_forecast = forecast(history, horizon)
    return {
        "daily_forecast": daily_forecast,
        "target_inventory": float(sum(daily_forecast)),
    }
'''

    GENERATION_STRATEGIES = (
        (
            "specification_fidelity",
            "优先忠实实现能力规格中的数学语义、参数和边界条件，保持实现直接且可审计。",
        ),
        (
            "robust_edge_cases",
            "在保持算法语义的前提下，重点增强空值、短历史、全零历史和极端数值处理。",
        ),
        (
            "minimal_dependency",
            "在保持算法语义的前提下，尽量减少依赖和状态，生成结构清晰的独立实现。",
        ),
        (
            "vectorized_implementation",
            "在保持算法语义的前提下，优先使用清晰的 NumPy/Pandas 向量化实现。",
        ),
        (
            "numerical_stability",
            "在保持算法语义的前提下，重点避免除零、非有限数值和递归预测漂移。",
        ),
    )

    @staticmethod
    def _safe_name(name: str) -> str:
        safe_name = "".join(
            character for character in name if character.isalnum() or character == "_"
        )
        if safe_name != name or not safe_name:
            raise ValueError(f"Unsafe model name: {name!r}")
        return safe_name

    @staticmethod
    def _strip_code_fence(response: str) -> str:
        source = response.strip()
        if source.startswith("```"):
            lines = source.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            source = "\n".join(lines).strip()
        if not source:
            raise ValueError("LLM generation returned empty source")
        return source + "\n"

    def _render_spec_template(self, spec: CapabilitySpec) -> str:
        try:
            body = self.TEMPLATE_BODIES[spec.template_name]
        except KeyError as exc:
            raise KeyError(
                f"No safe template for {spec.template_name!r}; "
                f"available={sorted(self.TEMPLATE_BODIES)}"
            ) from exc
        extra_imports = ""
        if spec.template_name == "ridge_lag":
            extra_imports = "import numpy as np\nfrom sklearn.linear_model import Ridge\n\n"
        spec_payload = asdict(spec)
        return (
            self.BASE_TEMPLATE.replace("__EXTRA_IMPORTS__", extra_imports)
            .replace("__CAPABILITY_NAME__", repr(spec.name))
            .replace("__CAPABILITY_SPEC__", repr(spec_payload))
            .replace("__PARAMETERS__", repr(spec.parameters))
            .replace("__FORECAST_BODY__", body)
        )

    def generate_from_spec(
        self,
        spec: CapabilitySpec,
        output_dir: str | Path,
        llm: LLMClient | None = None,
        *,
        variant_id: str = "primary",
        strategy: str = "specification_fidelity",
        generation_context: dict | None = None,
    ) -> GeneratedCapability:
        """Generate initial code with an LLM when configured, otherwise use a safe template."""

        safe_name = self._safe_name(spec.name)
        safe_variant = self._safe_name(variant_id)
        spec_json = json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True, default=str)
        spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
        generation_mode = "spec_template"
        source = ""
        prompt_payload = json.dumps(
            {
                "capability_spec": asdict(spec),
                "implementation_variant": safe_variant,
                "strategy": strategy,
                "implementation_agent_instructions": (
                    CodeImplementationAgent.system_prompt()
                ),
                "business_and_data_context": generation_context or {},
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        prompt_hash = hashlib.sha256(prompt_payload.encode("utf-8")).hexdigest()
        if llm is not None and not isinstance(llm, MockLLMClient):
            try:
                response = llm.complete(
                    "你是算法代码自主生成 Agent。只返回完整 Python 源码，不要返回解释或 Markdown。"
                    "请根据 CapabilitySpec、实现策略及需求画像，从算法原理出发编写独立实现，"
                    "不得导入或调用 inventory_agent 内部注册表、现有模型实现或生成代码。"
                    "必须提供 forecast(history, horizon) 和 "
                    "build_inventory_target(history, horizon)；输出必须确定、有限、非负。"
                    "forecast 必须返回 Python 内置 list[float]，不得返回 ndarray 或 Series；"
                    "build_inventory_target 必须返回包含 daily_forecast 列表和 "
                    "target_inventory 浮点数的 dict，且目标库存等于预测列表之和。"
                    "仅允许使用 Python 标准语法、numpy、pandas、sklearn；不得访问文件、网络、"
                    "环境变量、进程或动态执行代码。不要通过硬编码验证样例来通过测试。",
                    prompt_payload,
                )
                source = self._strip_code_fence(response)
                generation_mode = "llm_autonomous_generation"
            except Exception as exc:
                logger.warning(
                    "Autonomous code generation fallback for %s: %s",
                    spec.name,
                    type(exc).__name__,
                )
                generation_mode = "spec_template_fallback"
        if not source:
            source = self._render_spec_template(spec)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        suffix = "" if safe_variant == "primary" else f"_{safe_variant}"
        output = Path(output_dir) / f"forecast_{safe_name}{suffix}.py"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(source, encoding="utf-8")
        return GeneratedCapability(
            spec.name,
            source,
            output,
            generation_mode,
            spec_hash,
            source_hash,
            safe_variant,
            strategy,
            prompt_hash,
        )

    def generate_candidates_from_spec(
        self,
        spec: CapabilitySpec,
        output_dir: str | Path,
        *,
        llm: LLMClient | None = None,
        candidate_count: int = 3,
        generation_context: dict | None = None,
        max_workers: int = 1,
        collaborative: bool = True,
    ) -> list[GeneratedCapability]:
        """Generate diverse implementation candidates for one capability specification."""

        if candidate_count <= 0 or candidate_count > len(self.GENERATION_STRATEGIES):
            raise ValueError(
                f"candidate_count must be between 1 and "
                f"{len(self.GENERATION_STRATEGIES)}"
            )
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        collaboration_llm = llm or MockLLMClient()
        blueprint = CodeArchitectureAgent(collaboration_llm).design(
            spec, generation_context or {}
        )
        collaborative_context = {
            **(generation_context or {}),
            "implementation_blueprint": blueprint,
        }
        if llm is None or isinstance(llm, MockLLMClient):
            generated = [
                self.generate_from_spec(
                    spec,
                    output_dir,
                    llm=llm,
                    generation_context=collaborative_context,
                )
            ]
        else:
            requests = [
                (index, strategy_name, strategy_text)
                for index, (strategy_name, strategy_text) in enumerate(
                    self.GENERATION_STRATEGIES[:candidate_count], start=1
                )
            ]

            def generate_one(request: tuple[int, str, str]) -> GeneratedCapability:
                index, strategy_name, strategy_text = request
                return self.generate_from_spec(
                    spec,
                    output_dir,
                    llm=llm,
                    variant_id=f"candidate_{index}",
                    strategy=f"{strategy_name}: {strategy_text}",
                    generation_context=collaborative_context,
                )

            if max_workers == 1 or candidate_count == 1:
                generated = [generate_one(request) for request in requests]
            else:
                with ThreadPoolExecutor(
                    max_workers=min(max_workers, candidate_count),
                    thread_name_prefix="capability-codegen",
                ) as executor:
                    generated = list(executor.map(generate_one, requests))
        reviewer = CodeReviewAgent(collaboration_llm)

        def review_one(candidate: GeneratedCapability) -> GeneratedCapability:
            if not collaborative:
                return candidate
            reviewed_source, review = reviewer.review(
                spec,
                candidate.source,
                blueprint,
                candidate.variant_id,
            )
            candidate.path.write_text(reviewed_source, encoding="utf-8")
            source_hash = hashlib.sha256(reviewed_source.encode("utf-8")).hexdigest()
            mode = candidate.generation_mode
            if review.get("mode") == "llm_review" and mode.startswith("llm_"):
                mode = (
                    "llm_multi_agent_revised"
                    if review.get("revision_applied")
                    else "llm_multi_agent_generation"
                )
            return replace(
                candidate,
                source=reviewed_source,
                source_hash=source_hash,
                generation_mode=mode,
                collaboration={
                    "architecture": blueprint,
                    "implementation": {
                        "agent": "CodeImplementationAgent",
                        "strategy": candidate.strategy,
                        "variant_id": candidate.variant_id,
                    },
                    "review": review,
                },
            )

        if collaborative and len(generated) > 1 and max_workers > 1:
            with ThreadPoolExecutor(
                max_workers=min(max_workers, len(generated)),
                thread_name_prefix="capability-review",
            ) as executor:
                generated = list(executor.map(review_one, generated))
        else:
            generated = [review_one(candidate) for candidate in generated]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "implementation_blueprint.json").write_text(
            json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        collaboration_manifest = {
            "schema_version": "1.0",
            "protocol": "architecture -> parallel implementation -> independent review",
            "roles": [
                "CodeArchitectureAgent",
                "CodeImplementationAgent",
                "CodeReviewAgent",
                "GeneratedCodeValidator",
            ],
            "blueprint": blueprint,
            "candidates": [
                {
                    "variant_id": item.variant_id,
                    "strategy": item.strategy,
                    "path": str(item.path),
                    "source_hash": item.source_hash,
                    "generation_mode": item.generation_mode,
                    "review": item.collaboration.get("review", {}),
                }
                for item in generated
            ],
        }
        (output_path / "multi_agent_collaboration.json").write_text(
            json.dumps(collaboration_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        candidates = []
        seen_hashes = set()
        for candidate in generated:
            if candidate.source_hash in seen_hashes:
                continue
            seen_hashes.add(candidate.source_hash)
            candidates.append(candidate)
        if not candidates:
            raise ValueError("No distinct code candidates were generated")
        return candidates

    def generate(self, model: str, output_dir: str | Path) -> GeneratedCapability:
        """Generate from a minimal registered-model spec for backwards compatibility."""

        spec = CapabilitySpec(
            name=model,
            task_type="inventory_forecasting",
            description=f"Registered forecasting capability {model}",
            template_name=model,
            input_contract="non-negative daily demand history and positive horizon",
            output_contract="non-negative daily forecast and horizon-total target inventory",
        )
        return self.generate_from_spec(spec, output_dir)
