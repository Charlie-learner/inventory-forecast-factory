"""Persistent background-job orchestration for the local Web application."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeAlias
from uuid import uuid4


logger = logging.getLogger(__name__)
ProgressCallback: TypeAlias = Callable[[dict[str, Any]], None]
JobRunner: TypeAlias = Callable[[dict[str, Any], ProgressCallback], dict[str, Any]]


class JobNotFoundError(LookupError):
    """Signal that a job identifier is invalid or no longer retained."""


class BackgroundJobManager:
    """Run bounded background work and persist progress across server restarts."""

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        max_history: int = 50,
        max_concurrent: int = 1,
    ) -> None:
        if max_history <= 0 or max_concurrent <= 0:
            raise ValueError("job limits must be positive")
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_history = max_history
        self._lock = threading.Lock()
        self._slot = threading.BoundedSemaphore(max_concurrent)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._load_retained_jobs()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _path(self, job_id: str) -> Path:
        return self.storage_dir / f"{job_id}.json"

    def _write(self, job: dict[str, Any]) -> None:
        path = self._path(str(job["job_id"]))
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_retained_jobs(self) -> None:
        for path in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
        )[-self.max_history :]:
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(job, dict) and re.fullmatch(
                    r"[a-f0-9]{16}", str(job.get("job_id", ""))
                ):
                    if job.get("status") in {"queued", "running"}:
                        job.update(
                            status="failed",
                            stage="interrupted",
                            message="服务重启前任务尚未完成，请重新运行。",
                            finished_at=self._now(),
                        )
                        self._write(job)
                    self._jobs[str(job["job_id"])] = job
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("Skipping unreadable retained job %s: %s", path, exc)
                continue

    def _update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(updates)
            self._write(job)

    def _prune(self) -> None:
        completed = sorted(
            (
                item
                for item in self._jobs.values()
                if item.get("status") in {"completed", "failed"}
            ),
            key=lambda item: str(item.get("finished_at", item.get("created_at", ""))),
        )
        for stale in completed[: max(0, len(completed) - self.max_history)]:
            job_id = str(stale["job_id"])
            self._jobs.pop(job_id, None)
            path = self._path(job_id).resolve()
            if self.storage_dir in path.parents:
                path.unlink(missing_ok=True)

    def start(
        self,
        payload: dict[str, Any],
        runner: JobRunner,
    ) -> dict[str, Any]:
        """Queue one job and return its immediately pollable status."""

        job_id = uuid4().hex[:16]
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "percent": 0,
            "message": "任务已进入本地执行队列。",
            "created_at": self._now(),
        }
        with self._lock:
            self._prune()
            self._jobs[job_id] = job
            self._write(job)
        thread = threading.Thread(
            target=self._execute,
            args=(job_id, dict(payload), runner),
            name=f"inventory-job-{job_id}",
            daemon=True,
        )
        thread.start()
        return dict(job)

    def _execute(
        self,
        job_id: str,
        payload: dict[str, Any],
        runner: JobRunner,
    ) -> None:
        with self._slot:
            self._update(
                job_id,
                status="running",
                stage="starting",
                percent=1,
                message="正在初始化 Agent 工作流。",
                started_at=self._now(),
            )

            def progress(event: dict[str, Any]) -> None:
                self._update(job_id, **event)

            try:
                result = runner(payload, progress)
                self._update(
                    job_id,
                    status="completed",
                    stage="completed",
                    percent=100,
                    message="工作流完成，报告已生成。",
                    result=result,
                    finished_at=self._now(),
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                logger.exception("Background job %s failed", job_id)
                self._update(
                    job_id,
                    status="failed",
                    stage="failed",
                    message=message,
                    error=message,
                    finished_at=self._now(),
                )

    def status(self, job_id: str) -> dict[str, Any]:
        """Return an in-memory or persisted job record."""

        if not re.fullmatch(r"[a-f0-9]{16}", job_id):
            raise JobNotFoundError(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return dict(job)
        path = self._path(job_id)
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JobNotFoundError(job_id) from exc
        if not isinstance(job, dict):
            raise JobNotFoundError(job_id)
        return job
