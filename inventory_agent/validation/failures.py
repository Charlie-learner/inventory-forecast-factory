"""Classify validation failures into reusable, privacy-safe experience records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureAnalysis:
    """Describe one normalized failure independently of paths and run-specific values."""

    category: str
    fingerprint: str
    normalized_error: str
    retryable: bool
    severity: str
    likely_stage: str
    root_cause: str
    recommended_actions: tuple[str, ...]


class FailureAnalyzer:
    """Create stable failure fingerprints used to retrieve prior repair experience."""

    def analyze(
        self,
        errors: tuple[str, ...],
        checks: dict[str, bool] | None = None,
    ) -> FailureAnalysis:
        """Classify errors with failed validation checks taking precedence over wording."""

        checks = checks or {}
        combined = " | ".join(errors).strip() or "unknown validation failure"
        lowered = combined.lower()
        if checks.get("syntax") is False or "syntax" in lowered:
            category = "syntax"
        elif checks.get("imports") is False or "unsafe constructs" in lowered:
            category = "safety"
        elif (
            checks.get("interface") is False
            or "interface" in lowered
            or "must return python list" in lowered
            or "build_inventory_target must return" in lowered
            or "must contain daily_forecast" in lowered
        ):
            category = "interface"
        elif "timed out" in lowered or "timeout" in lowered:
            category = "timeout"
        elif checks.get("equivalence") is False or "does not match" in lowered:
            category = "equivalence"
        elif checks.get("stability") is False or "deterministic" in lowered:
            category = "stability"
        elif checks.get("runtime") is False or "runtime" in lowered:
            category = "runtime"
        else:
            category = "unknown"

        normalized = self._normalize(combined)
        fingerprint = hashlib.sha256(
            f"{category}|{normalized}".encode("utf-8")
        ).hexdigest()[:16]
        root_cause, actions, stage, severity = self._guidance(category)
        return FailureAnalysis(
            category=category,
            fingerprint=fingerprint,
            normalized_error=normalized,
            retryable=category != "safety",
            severity=severity,
            likely_stage=stage,
            root_cause=root_cause,
            recommended_actions=actions,
        )

    @staticmethod
    def _guidance(
        category: str,
    ) -> tuple[str, tuple[str, ...], str, str]:
        """Map normalized categories to reusable root-cause guidance."""

        guidance = {
            "syntax": (
                "生成源码不符合 Python 语法，常见于代码截断、缩进或括号不完整。",
                ("重新解析源码语法树", "使用完整安全模板重新生成", "保留失败源码快照"),
                "code_generation",
                "high",
            ),
            "safety": (
                "生成代码包含未授权导入或文件、网络、进程等危险调用。",
                ("停止自动执行", "移除危险调用", "转为人工安全审核"),
                "security_validation",
                "critical",
            ),
            "interface": (
                "生成模块未满足 forecast/build_inventory_target 统一接口契约。",
                ("按接口签名重新生成", "补齐返回字段", "运行契约测试"),
                "contract_validation",
                "high",
            ),
            "timeout": (
                "算法执行时间超过限制，可能存在死循环或高复杂度计算。",
                ("检查循环终止条件", "降低输入规模或复杂度", "回退轻量基线"),
                "runtime_validation",
                "high",
            ),
            "equivalence": (
                "复刻实现与参考算法在标准用例上的数值行为不一致。",
                ("核对公式与参数", "比较边界用例", "使用参考模板重新生成"),
                "behavior_validation",
                "medium",
            ),
            "stability": (
                "相同输入产生不同结果或边界输入输出不稳定。",
                ("固定随机性", "移除隐式外部状态", "补充零需求边界测试"),
                "stability_validation",
                "medium",
            ),
            "runtime": (
                "代码可解析但运行时发生异常，通常由类型、形状或边界条件触发。",
                ("定位异常类型", "补充输入清洗", "复用同类成功修复策略"),
                "runtime_validation",
                "high",
            ),
            "unknown": (
                "错误信息不足，暂时无法归入已知失败类别。",
                ("保留完整日志", "增加诊断检查", "转人工分析"),
                "unknown",
                "medium",
            ),
        }
        return guidance[category]

    @staticmethod
    def _normalize(error: str) -> str:
        text = error.lower().replace("\\", "/")
        text = re.sub(r"(?:[a-z]:)?/[\w./-]+\.py", "<path>.py", text)
        text = re.sub(r"0x[0-9a-f]+", "<hex>", text)
        text = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", text)
        return " ".join(text.split())[:500]
