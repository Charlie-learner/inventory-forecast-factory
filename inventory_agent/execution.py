"""Central runtime policies for execution cost, retention, and Web safety."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeAlias


ProgressEvent: TypeAlias = dict[str, Any]
ProgressCallback: TypeAlias = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class ExecutionProfile:
    """Configure expensive workflow work without scattering magic numbers."""

    name: str
    implementation_candidates: int
    generation_workers: int
    performance_iterations: int
    use_llm_explanation: bool


@dataclass(frozen=True)
class RuntimeLimits:
    """Configure operational limits without scattering magic numbers."""

    max_http_body_bytes: int = 140 * 1024 * 1024
    max_upload_file_bytes: int = 100 * 1024 * 1024
    max_job_history: int = 50
    max_concurrent_jobs: int = 1
    default_keep_runs: int = 10
    archive_member_preview: int = 30
    identifier_preview: int = 10

    def __post_init__(self) -> None:
        numeric_limits = {
            "max_http_body_bytes": self.max_http_body_bytes,
            "max_upload_file_bytes": self.max_upload_file_bytes,
            "max_job_history": self.max_job_history,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "default_keep_runs": self.default_keep_runs,
            "archive_member_preview": self.archive_member_preview,
            "identifier_preview": self.identifier_preview,
        }
        invalid = [name for name, value in numeric_limits.items() if value <= 0]
        if invalid:
            raise ValueError(f"runtime limits must be positive: {', '.join(invalid)}")
        if self.max_upload_file_bytes > self.max_http_body_bytes:
            raise ValueError("max_upload_file_bytes cannot exceed max_http_body_bytes")


DEFAULT_RUNTIME_LIMITS = RuntimeLimits()


def format_byte_limit(size: int) -> str:
    """Format a configured byte limit without losing small injected values."""

    for divisor, suffix in ((1024 * 1024, "MB"), (1024, "KB")):
        if size >= divisor:
            value = size / divisor
            return f"{value:g} {suffix}"
    return f"{size} B"


EXECUTION_PROFILES = {
    "fast": ExecutionProfile("fast", 1, 1, 10, False),
    "balanced": ExecutionProfile("balanced", 2, 2, 20, True),
    "thorough": ExecutionProfile("thorough", 3, 2, 40, True),
}


def get_execution_profile(name: str) -> ExecutionProfile:
    """Return a validated execution profile by public name."""

    try:
        return EXECUTION_PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(EXECUTION_PROFILES)
        raise ValueError(f"execution_mode must be one of: {choices}") from exc
