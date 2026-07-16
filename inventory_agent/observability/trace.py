"""Persist a teacher-readable and machine-readable trace for one workflow run."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunTraceRecorder:
    """Append workflow events immediately so intermediate evidence survives failures."""

    MAX_STRING_LENGTH = 20_000

    def __init__(self, run_dir: str | Path, enabled: bool = True) -> None:
        self.run_dir = Path(run_dir)
        self.enabled = enabled
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.events: list[dict[str, Any]] = []
        self.artifacts: list[str] = []
        self._snapshot_count = 0
        self.jsonl_path = self.run_dir / "detailed_trace.jsonl"
        self.markdown_path = self.run_dir / "detailed_trace.md"
        self.manifest_path = self.run_dir / "run_manifest.json"
        if enabled:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.jsonl_path.write_text("", encoding="utf-8")
            self.markdown_path.write_text(
                "# AI Agent 能力工厂详细运行过程\n\n"
                f"- 开始时间：{self.started_at}\n"
                f"- 运行目录：`{self.run_dir}`\n\n",
                encoding="utf-8",
            )

    def record(
        self,
        *,
        stage: str,
        component: str,
        component_type: str,
        action: str,
        status: str = "success",
        inputs: Any = None,
        outputs: Any = None,
        artifacts: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        """Append one numbered event to JSONL and Markdown trace files."""

        if not self.enabled:
            return {}
        artifact_paths = [str(Path(path)) for path in artifacts or []]
        for path in artifact_paths:
            if path not in self.artifacts:
                self.artifacts.append(path)
        event = {
            "sequence": len(self.events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "component": component,
            "component_type": component_type,
            "action": action,
            "status": status,
            "inputs": self._jsonable(inputs),
            "outputs": self._jsonable(outputs),
            "artifacts": artifact_paths,
        }
        self.events.append(event)
        with self.jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        with self.markdown_path.open("a", encoding="utf-8") as stream:
            stream.write(self._markdown_event(event))
        return event

    def snapshot_code(self, source: str, label: str, model: str) -> Path | None:
        """Save one immutable generated-code version for review and comparison."""

        if not self.enabled:
            return None
        safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_") or "version"
        safe_model = re.sub(r"[^A-Za-z0-9_]+", "_", model).strip("_") or "model"
        self._snapshot_count += 1
        output = self.run_dir / "generated_versions" / (
            f"{self._snapshot_count:02d}_{safe_label}_{safe_model}.py"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(source, encoding="utf-8")
        path = str(output)
        if path not in self.artifacts:
            self.artifacts.append(path)
        return output

    def finalize(self, status: str, summary: Any = None) -> dict[str, str] | None:
        """Record terminal state and write a manifest indexing all trace artifacts."""

        if not self.enabled:
            return None
        self.record(
            stage="run",
            component="InventoryCapabilityWorkflow",
            component_type="workflow",
            action="run_finished",
            status=status,
            outputs=summary,
        )
        finished_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": "1.0",
            "status": status,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "event_count": len(self.events),
            "trace": {
                "jsonl": str(self.jsonl_path),
                "markdown": str(self.markdown_path),
            },
            "artifacts": self.artifacts,
            "summary": self._jsonable(summary),
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with self.markdown_path.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n## 运行清单\n\n"
                f"- 最终状态：`{status}`\n"
                f"- 事件数量：{len(self.events)}\n"
                f"- 结束时间：{finished_at}\n"
                f"- 清单文件：`{self.manifest_path}`\n"
            )
        return self.paths()

    def paths(self) -> dict[str, str]:
        """Return stable paths even before finalization."""

        return {
            "jsonl": str(self.jsonl_path),
            "markdown": str(self.markdown_path),
            "manifest": str(self.manifest_path),
        }

    @classmethod
    def _jsonable(cls, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "<maximum serialization depth reached>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if len(value) <= cls.MAX_STRING_LENGTH:
                return value
            return value[: cls.MAX_STRING_LENGTH] + "...<truncated>"
        if isinstance(value, Path):
            return str(value)
        if is_dataclass(value) and not isinstance(value, type):
            return cls._jsonable(asdict(value), depth + 1)
        if isinstance(value, dict):
            return {
                str(key): cls._jsonable(item, depth + 1)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._jsonable(item, depth + 1) for item in value]
        if hasattr(value, "tolist"):
            return cls._jsonable(value.tolist(), depth + 1)
        return repr(value)

    @staticmethod
    def _markdown_event(event: dict[str, Any]) -> str:
        title = (
            f"## {event['sequence']:03d}. {event['stage']} - "
            f"{event['component']}.{event['action']}"
        )
        inputs = json.dumps(event["inputs"], ensure_ascii=False, indent=2)
        outputs = json.dumps(event["outputs"], ensure_ascii=False, indent=2)
        artifacts = "\n".join(f"- `{path}`" for path in event["artifacts"])
        artifact_section = f"\n### 产物\n\n{artifacts}\n" if artifacts else ""
        return (
            f"{title}\n\n"
            f"- 时间：{event['timestamp']}\n"
            f"- 类型：`{event['component_type']}`\n"
            f"- 状态：`{event['status']}`\n\n"
            f"### 输入/调用参数\n\n```json\n{inputs}\n```\n\n"
            f"### 输出/返回结果\n\n```json\n{outputs}\n```\n"
            f"{artifact_section}\n"
        )


class RunRetentionManager:
    """Delete only old timestamp-named run directories below one verified root."""

    RUN_DIRECTORY_PATTERN = re.compile(r"^\d{8}_\d{6}_\d{6}$")

    @classmethod
    def cleanup(cls, output_root: str | Path, keep_runs: int) -> list[str]:
        """Keep the newest N run directories and return verified deleted paths."""

        if keep_runs <= 0:
            raise ValueError("keep_runs must be positive")
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve()
        candidates = []
        for candidate in root.iterdir():
            if (
                not candidate.is_dir()
                or candidate.is_symlink()
                or not cls.RUN_DIRECTORY_PATTERN.fullmatch(candidate.name)
            ):
                continue
            if not any(
                (candidate / marker).exists()
                for marker in (
                    "detailed_trace.jsonl",
                    "run_manifest.json",
                    "validation_report.json",
                )
            ):
                # The newest run may still be empty; it sorts first and is retained.
                newest_name = max(
                    (
                        path.name
                        for path in root.iterdir()
                        if path.is_dir()
                        and cls.RUN_DIRECTORY_PATTERN.fullmatch(path.name)
                    ),
                    default="",
                )
                if candidate.name != newest_name:
                    continue
            resolved_candidate = candidate.resolve()
            if resolved_candidate.parent != resolved_root:
                continue
            candidates.append(candidate)
        candidates.sort(key=lambda path: path.name, reverse=True)
        deleted = []
        for candidate in candidates[keep_runs:]:
            resolved_candidate = candidate.resolve()
            if resolved_candidate.parent != resolved_root:
                raise RuntimeError(f"Refusing to delete outside run root: {candidate}")
            shutil.rmtree(resolved_candidate)
            deleted.append(str(resolved_candidate))
        return deleted
