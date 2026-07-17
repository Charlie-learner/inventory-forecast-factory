"""Agent that converts source artifacts into auditable capability specifications."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from inventory_agent.domain import CapabilitySpec
from inventory_agent.extraction.extractor import CapabilityExtractor
from inventory_agent.llm.client import LLMClient, MockLLMClient


logger = logging.getLogger(__name__)


class CapabilityExtractionAgent:
    """Use deterministic parsers and optional LLM normalization for source knowledge."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        extractor: CapabilityExtractor | None = None,
    ) -> None:
        self.llm = llm or MockLLMClient()
        self.extractor = extractor or CapabilityExtractor()
        self.scan_reports: list[dict] = []

    def extract_sources(self, sources: list[str | Path]) -> list[CapabilitySpec]:
        """Extract every source while retaining per-file provenance and extraction mode."""

        capabilities = []
        self.scan_reports = []
        for source in sources:
            path = Path(source)
            if path.suffix.lower() in {".md", ".txt"} and not isinstance(
                self.llm, MockLLMClient
            ):
                try:
                    capabilities.extend(self._extract_document_with_llm(path))
                    self.scan_reports.append(
                        {
                            "source": str(path),
                            "source_kind": "file",
                            "files_scanned": 1,
                            "files_matched": 1,
                            "errors": [],
                            "extracted_by": "llm",
                        }
                    )
                    continue
                except Exception as exc:
                    # Deterministic extraction keeps the offline and provider-failure path usable.
                    logger.warning(
                        "LLM extraction failed for %s; using deterministic parser: %s",
                        path,
                        type(exc).__name__,
                    )
            capabilities.extend(self.extractor.extract(path))
            self.scan_reports.append(dict(self.extractor.last_scan_report))
        return capabilities

    def _extract_document_with_llm(self, path: Path) -> list[CapabilitySpec]:
        text = path.read_text(encoding="utf-8")
        response = self.llm.complete(
            "你是算法能力抽取 Agent。只返回 JSON。提取 name、task_type、description、"
            "template_name、input_contract、output_contract、suitable_for、metrics、"
            "dependencies、parameters、version、source_title、source_url、source_license、"
            "accessed_at、confidence、review_status、evidence_refs 和 extraction_warnings。"
            "数组字段必须返回 JSON 数组。",
            text,
        )
        payload_text = response.strip()
        if payload_text.startswith("```"):
            lines = payload_text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            payload_text = "\n".join(lines)
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return self.extractor.from_payload(
            json.loads(payload_text),
            source_ref=str(path),
            source_hash=source_hash,
            source_type="document",
            extracted_by="llm",
        )

    @staticmethod
    def write_result(
        capabilities: list[CapabilitySpec],
        output: str | Path,
        scan_reports: list[dict] | None = None,
    ) -> Path:
        """Write a reviewable knowledge-extraction result artifact."""

        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "count": len(capabilities),
            "scan_reports": scan_reports or [],
            "capabilities": [asdict(capability) for capability in capabilities],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
