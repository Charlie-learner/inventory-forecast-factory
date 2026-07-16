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
        elif checks.get("interface") is False or "interface" in lowered:
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
        return FailureAnalysis(
            category=category,
            fingerprint=fingerprint,
            normalized_error=normalized,
            retryable=category != "safety",
        )

    @staticmethod
    def _normalize(error: str) -> str:
        text = error.lower().replace("\\", "/")
        text = re.sub(r"(?:[a-z]:)?/[\w./-]+\.py", "<path>.py", text)
        text = re.sub(r"0x[0-9a-f]+", "<hex>", text)
        text = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", text)
        return " ".join(text.split())[:500]
