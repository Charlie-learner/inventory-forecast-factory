"""Runtime configuration with secret-safe environment loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load a minimal .env file without adding another runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    """Application settings. API credentials are never serialized or logged."""

    llm_mode: str = "mock"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    cainiao_zip_path: Path | None = None
    sample_submission_path: Path | None = None

    @classmethod
    def from_env(cls, load_dotenv: bool = True) -> "Settings":
        if load_dotenv:
            _load_dotenv()
        zip_value = os.getenv("CAINIAO_ZIP_PATH")
        submission_value = os.getenv("SAMPLE_SUBMISSION_PATH")
        return cls(
            llm_mode=os.getenv("LLM_MODE", "mock").lower(),
            model=os.getenv("MODEL", "gpt-4o-mini"),
            base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY"),
            cainiao_zip_path=Path(zip_value) if zip_value else None,
            sample_submission_path=Path(submission_value) if submission_value else None,
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.llm_mode not in {"mock", "api"}:
            issues.append("LLM_MODE must be 'mock' or 'api'.")
        if self.llm_mode == "api" and not self.api_key:
            issues.append("API_KEY is required when LLM_MODE=api.")
        if self.cainiao_zip_path and not self.cainiao_zip_path.exists():
            issues.append(f"Cainiao ZIP not found: {self.cainiao_zip_path}")
        return issues

