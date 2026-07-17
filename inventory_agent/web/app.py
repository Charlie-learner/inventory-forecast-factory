"""Application services exposed by the local Web interface."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import threading
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import (
    create_cainiao_loader,
    inspect_csv,
    load_location_frame,
    load_cost_csv,
    load_panel_csv,
    normalize_mapped_panel_csv,
)
from inventory_agent.forecasting.registry import default_registry
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.llm.client import create_llm
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.services.audit import build_submission_audit
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.services.replenishment import load_business_costs
from inventory_agent.data.schema import ZIP_MEMBERS
from inventory_agent.execution import (
    DEFAULT_RUNTIME_LIMITS,
    ProgressCallback,
    RuntimeLimits,
    format_byte_limit,
)
from inventory_agent.validation.metrics import default_metric_registry
from inventory_agent.validation.profiles import default_validation_profiles
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow
from inventory_agent.web.jobs import BackgroundJobManager, JobNotFoundError


logger = logging.getLogger(__name__)


class WebRequestError(ValueError):
    """Represent a user-facing Web request failure."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class WebApplication:
    """Bridge JSON Web requests to the existing capability-factory services."""

    def __init__(
        self,
        workspace: str | Path = ".",
        settings: Settings | None = None,
        output_root: str | Path = "artifacts/runs",
        knowledge_path: str | Path = "artifacts/knowledge/capability_graph.json",
        runtime_limits: RuntimeLimits | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.settings = settings or Settings.from_env()
        self.output_root = self._path(output_root)
        self.knowledge_path = self._path(knowledge_path)
        self.runtime_limits = runtime_limits or DEFAULT_RUNTIME_LIMITS
        self._run_lock = threading.Lock()
        self.jobs = BackgroundJobManager(
            self._path("artifacts/jobs"),
            max_history=self.runtime_limits.max_job_history,
            max_concurrent=self.runtime_limits.max_concurrent_jobs,
        )

    def start_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start a background workflow and return immediately for progress polling."""

        return self.jobs.start(
            payload,
            lambda job_payload, progress: self.run_workflow(
                job_payload, progress_callback=progress
            ),
        )

    def job_status(self, job_id: str) -> dict[str, Any]:
        """Return current progress and the final result when available."""

        try:
            return self.jobs.status(job_id)
        except JobNotFoundError as exc:
            raise WebRequestError("任务不存在、已过期或任务 ID 非法。", 404) from exc

    def _path(self, value: str | Path, *, must_exist: bool = False) -> Path:
        """Resolve one path and keep Web operations inside the project workspace."""

        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise WebRequestError(f"路径必须位于项目目录内：{value}")
        if must_exist and not resolved.exists():
            raise WebRequestError(f"路径不存在：{value}")
        return resolved

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable JSON state %s: %s", path, exc)
            return {}

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return [item.strip() for item in value if item.strip()]
        raise WebRequestError("列表字段必须是字符串数组或按行分隔的文本。")

    def _plugin_specs(self, value: Any) -> list[str]:
        specs = self._string_list(value)
        for spec in specs:
            reference = spec.rpartition(":")[0] or spec
            if reference.lower().endswith(".py"):
                self._path(reference, must_exist=True)
        return specs

    def _upload_session(self, requested: str | None = None) -> tuple[str, Path]:
        session_id = str(requested or uuid4().hex[:16]).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", session_id):
            raise WebRequestError("非法上传会话 ID。")
        session_dir = self._path(Path("artifacts/uploads") / session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_id, session_dir

    @staticmethod
    def _panel_info(frame: Any) -> dict[str, Any]:
        return {
            "rows": len(frame),
            "columns": list(frame.columns),
            "item_count": int(frame["item_id"].nunique()),
            "store_count": int(frame["store_code"].nunique()),
            "item_examples": frame["item_id"].drop_duplicates().head(8).tolist(),
            "store_examples": frame["store_code"]
            .drop_duplicates()
            .head(8)
            .tolist(),
            "date_start": frame["date"].min().date().isoformat(),
            "date_end": frame["date"].max().date().isoformat(),
        }

    def _session_summary(
        self, session_id: str, session_dir: Path, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        files = list(manifest.get("files", {}).values())
        demand_files = [
            item
            for item in files
            if item.get("status") == "ready"
            and item.get("kind")
            in {"panel", "cainiao_national", "cainiao_store"}
        ]
        cost_files = [
            item
            for item in files
            if item.get("status") == "ready"
            and item.get("kind") == "cost_config"
        ]
        zip_files = [
            item
            for item in files
            if item.get("status") == "ready" and item.get("kind") == "zip"
        ]
        cainiao_demand_files = [
            item
            for item in demand_files
            if item.get("kind") in {"cainiao_national", "cainiao_store"}
        ]
        generic_demand_files = [
            item for item in demand_files if item.get("kind") == "panel"
        ]
        runnable_path = ""
        mode = "incomplete"
        if zip_files:
            runnable_path = str(zip_files[-1]["path"])
            mode = "zip_bundle"
        elif cost_files and cainiao_demand_files:
            runnable_path = str(session_dir.relative_to(self.workspace))
            mode = "directory_bundle"
        elif generic_demand_files:
            runnable_path = str(generic_demand_files[-1]["path"])
            mode = "single_panel_unit_cost"
        elif len(cainiao_demand_files) == 1:
            runnable_path = str(cainiao_demand_files[0]["path"])
            mode = "single_panel_unit_cost"
        elif len(cainiao_demand_files) > 1:
            mode = "needs_cost_config"
        item_examples = []
        store_examples = []
        for item in demand_files:
            item_examples.extend(item.get("item_examples", []))
            store_examples.extend(item.get("store_examples", []))
        preview_limit = self.runtime_limits.identifier_preview
        item_examples = list(dict.fromkeys(item_examples))[:preview_limit]
        store_examples = list(dict.fromkeys(map(str, store_examples)))[:preview_limit]
        needs_mapping = [
            item for item in files if item.get("status") == "needs_mapping"
        ]
        if not runnable_path:
            if needs_mapping:
                message = "存在待映射的 CSV，请先选择日期、商品、仓库和需求字段。"
            elif cost_files and not demand_files:
                message = "成本配置已识别，请继续上传全国或分仓需求特征表。"
            elif len(demand_files) > 1 and not cost_files:
                message = "已识别多张需求表，请继续上传 config2.csv 组成完整数据集。"
            else:
                message = "请上传需求时间序列 CSV，或上传包含完整数据的 ZIP。"
        elif mode == "single_panel_unit_cost":
            message = "需求数据可运行；未上传成本配置，将使用单位缺货/积压成本。"
        else:
            message = "完整数据集已就绪，将使用上传的需求表和成本配置。"
        return {
            "session_id": session_id,
            "files": files,
            "ready": bool(runnable_path),
            "runnable_path": runnable_path,
            "mode": mode,
            "message": message,
            "item_examples": item_examples,
            "store_examples": store_examples,
            "item_count": max(
                (int(item.get("item_count", 0)) for item in demand_files),
                default=0,
            ),
            "store_count": max(
                (int(item.get("store_count", 0)) for item in demand_files),
                default=0,
            ),
        }

    def upload_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add one CSV/ZIP to a multi-file upload session."""

        session_id, session_dir = self._upload_session(payload.get("session_id"))
        manifest_path = session_dir / "upload_manifest.json"
        manifest = self._read_json(manifest_path)
        manifest.setdefault("files", {})
        filename = Path(str(payload.get("filename", ""))).name
        if not filename:
            raise WebRequestError("上传文件缺少文件名。")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".zip"}:
            raise WebRequestError("目前支持 CSV 文件或 ZIP 数据压缩包。")
        try:
            content = base64.b64decode(
                str(payload.get("content_base64", "")), validate=True
            )
        except (ValueError, binascii.Error) as exc:
            raise WebRequestError("上传文件内容无法解析。") from exc
        if not content:
            raise WebRequestError("上传文件不能为空。")
        if len(content) > self.runtime_limits.max_upload_file_bytes:
            limit = format_byte_limit(self.runtime_limits.max_upload_file_bytes)
            raise WebRequestError(f"单个上传文件不能超过 {limit}。", 413)
        digest = hashlib.sha256(content).hexdigest()
        safe_stem = re.sub(
            r"[^A-Za-z0-9_-]+", "_", Path(filename).stem
        ).strip("_") or "dataset"
        output = session_dir / f"{safe_stem}_{digest[:12]}{suffix}"
        output.write_bytes(content)
        info: dict[str, Any] = {
            "original_name": filename,
            "path": str(output.relative_to(self.workspace)),
            "size_bytes": len(content),
            "sha256": digest,
            "uploaded_at": datetime.now().isoformat(),
            "kind": suffix.removeprefix("."),
            "status": "ready",
        }
        lower_name = filename.lower()
        if suffix == ".zip":
            try:
                with ZipFile(output) as archive:
                    members = [
                        name
                        for name in archive.namelist()
                        if not name.endswith("/") and "__MACOSX" not in name
                    ]
                    csv_members = [
                        name for name in members if name.lower().endswith(".csv")
                    ]
                    cainiao_members = {
                        kind: next(
                            (
                                name
                                for name in members
                                if name.endswith(expected)
                            ),
                            None,
                        )
                        for kind, expected in ZIP_MEMBERS.items()
                    }
                    if (
                        cainiao_members.get("cost")
                        and (
                            cainiao_members.get("national")
                            or cainiao_members.get("store")
                        )
                    ):
                        info.update(
                            {
                                "kind": "zip",
                                "members": members[: self.runtime_limits.archive_member_preview],
                                "member_count": len(members),
                                "cainiao_members": cainiao_members,
                            }
                        )
                    elif len(csv_members) == 1:
                        member = csv_members[0]
                        extracted = session_dir / Path(member).name
                        extracted.write_bytes(archive.read(member))
                        try:
                            frame = load_panel_csv(extracted)
                            info.update(
                                {
                                    "kind": "panel",
                                    "path": str(extracted.relative_to(self.workspace)),
                                    "archive_path": str(output.relative_to(self.workspace)),
                                    "members": members[: self.runtime_limits.archive_member_preview],
                                    "member_count": len(members),
                                    **self._panel_info(frame),
                                }
                            )
                        except (ValueError, TypeError, UnicodeError) as exc:
                            info.update(
                                {
                                    "status": "needs_mapping",
                                    "kind": "unmapped_csv",
                                    "path": str(extracted.relative_to(self.workspace)),
                                    "archive_path": str(output.relative_to(self.workspace)),
                                    "diagnostic": str(exc),
                                    **inspect_csv(extracted),
                                }
                            )
                    else:
                        info.update(
                            {
                                "status": "needs_mapping",
                                "kind": "multi_csv_archive",
                                "members": members[: self.runtime_limits.archive_member_preview],
                                "member_count": len(members),
                                "diagnostic": (
                                    "压缩包包含多份非菜鸟 CSV。请直接多选这些 CSV 上传，"
                                    "系统会逐个诊断和组合。"
                                ),
                            }
                        )
            except BadZipFile as exc:
                output.unlink(missing_ok=True)
                raise WebRequestError("上传内容不是有效的 ZIP 文件。") from exc
        elif lower_name == "config2.csv" or "config" in lower_name:
            try:
                costs = load_cost_csv(output)
            except (ValueError, TypeError, UnicodeError) as exc:
                raise WebRequestError(f"成本配置格式无法识别：{exc}") from exc
            canonical = session_dir / "config2.csv"
            canonical.write_bytes(content)
            output.unlink(missing_ok=True)
            output = canonical
            info.update(
                {
                    "path": str(output.relative_to(self.workspace)),
                    "kind": "cost_config",
                    "rows": len(costs),
                    "item_count": int(costs["item_id"].nunique()),
                    "store_count": int(costs["store_code"].nunique()),
                    "item_examples": costs["item_id"].drop_duplicates().head(8).tolist(),
                    "store_examples": costs["store_code"].drop_duplicates().head(8).tolist(),
                }
            )
        else:
            try:
                frame = load_panel_csv(output)
                kind = "panel"
                canonical_name = None
                if lower_name == "item_feature2.csv":
                    kind, canonical_name = "cainiao_national", "item_feature2.csv"
                elif lower_name == "item_store_feature2.csv":
                    kind, canonical_name = "cainiao_store", "item_store_feature2.csv"
                if canonical_name:
                    canonical = session_dir / canonical_name
                    canonical.write_bytes(content)
                    output.unlink(missing_ok=True)
                    output = canonical
                info.update(
                    {
                        "path": str(output.relative_to(self.workspace)),
                        "kind": kind,
                        **self._panel_info(frame),
                    }
                )
            except (ValueError, TypeError, UnicodeError) as exc:
                preview = inspect_csv(output)
                info.update(
                    {
                        "status": "needs_mapping",
                        "kind": "unmapped_csv",
                        "diagnostic": str(exc),
                        **preview,
                    }
                )
        manifest["files"][filename] = info
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return {
            "uploaded_file": info,
            "dataset": self._session_summary(session_id, session_dir, manifest),
        }

    def map_dataset_columns(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply an explicit field mapping to an unrecognized uploaded CSV."""

        session_id, session_dir = self._upload_session(payload.get("session_id"))
        manifest_path = session_dir / "upload_manifest.json"
        manifest = self._read_json(manifest_path)
        filename = str(payload.get("filename", ""))
        info = manifest.get("files", {}).get(filename)
        if not info:
            raise WebRequestError("上传会话中找不到待映射文件。")
        source = self._path(str(info.get("path", "")), must_exist=True)
        mapping = {
            key: str(value)
            for key, value in dict(payload.get("mapping", {})).items()
            if str(value)
        }
        output = session_dir / f"{source.stem}_normalized.csv"
        try:
            frame = normalize_mapped_panel_csv(source, output, mapping)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise WebRequestError(f"字段映射后仍无法规范化：{exc}") from exc
        info.update(
            {
                "path": str(output.relative_to(self.workspace)),
                "kind": "panel",
                "status": "ready",
                "mapping": mapping,
                **self._panel_info(frame),
            }
        )
        manifest["files"][filename] = info
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return {
            "mapped_file": info,
            "dataset": self._session_summary(session_id, session_dir, manifest),
        }

    @staticmethod
    def _description_with_dataset_context(
        description: str, data_path: Path
    ) -> str:
        """Infer a unique item/location from an uploaded panel when omitted."""

        if data_path.suffix.lower() != ".csv":
            return description
        frame = load_panel_csv(data_path)
        has_item = bool(
            re.search(r"(?:item|商品|货品|SKU)[_\s:=号#-]*\d+", description, re.I)
        )
        has_store = bool(
            re.search(
                r"(?:store|仓库|分仓|区域)[_\s:=号#-]*"
                r"(?:all|全国|[A-Za-z0-9_-]+)",
                description,
                re.I,
            )
            or "全国" in description
        )
        additions = []
        if not has_item:
            items = frame["item_id"].drop_duplicates().tolist()
            if len(items) != 1:
                raise WebRequestError(
                    "数据包含多个商品，请在自然语言描述中指定商品 ID。"
                )
            additions.append(f"商品 {items[0]}")
        if not has_store:
            stores = frame["store_code"].drop_duplicates().astype(str).tolist()
            if len(stores) != 1:
                raise WebRequestError(
                    "数据包含多个仓库，请在自然语言描述中指定仓库编码。"
                )
            additions.append(
                "全国" if stores[0].lower() == "all" else f"仓库 {stores[0]}"
            )
        return f"{description}；{'，'.join(additions)}" if additions else description

    @staticmethod
    def _unique(values: list[Any]) -> list[Any]:
        """Deduplicate values while preserving their source order."""

        return list(dict.fromkeys(values))

    def _dataset_dimensions(self, data_path: Path) -> tuple[list[int], list[str]]:
        """Return the item and warehouse values available to natural-language tasks."""

        if data_path.is_dir() or data_path.suffix.lower() == ".zip":
            loader = create_cainiao_loader(data_path)
            national = loader.load_national()
            store = loader.load_store()
            items = self._unique(
                [
                    *national["item_id"].drop_duplicates().astype(int).tolist(),
                    *store["item_id"].drop_duplicates().astype(int).tolist(),
                ]
            )
            stores = (
                store["store_code"].drop_duplicates().astype(str).tolist()
            )
            return items, self._unique(stores)
        frame = load_panel_csv(data_path)
        return (
            frame["item_id"].drop_duplicates().astype(int).tolist(),
            frame["store_code"].drop_duplicates().astype(str).tolist(),
        )

    def _request_targets(
        self, description: str, data_path: Path
    ) -> list[tuple[int, str]]:
        """Expand one natural-language request into item/warehouse sub-tasks."""

        available_items, available_stores = self._dataset_dimensions(data_path)
        item_groups = re.findall(
            r"(?:item|商品|货品|SKU)(?:\s*ID)?[_\s:=号-]*"
            r"(\d+(?:(?:\s*(?:、|,|，|和|及|与|/)\s*)"
            r"(?:(?:item|商品|货品|SKU)(?:\s*ID)?[_\s:=号-]*)?\d+)*)",
            description,
            re.IGNORECASE,
        )
        item_ids = [
            int(value)
            for group in item_groups
            for value in re.findall(r"\d+", group)
        ]
        if re.search(r"(?:所有|全部|每个|各个?)商品", description):
            item_ids = available_items
        item_ids = self._unique(item_ids)
        if not item_ids:
            if len(available_items) == 1:
                item_ids = available_items
            else:
                raise WebRequestError(
                    "数据包含多个商品。请在自然语言中写明一个或多个商品 ID，"
                    "例如“商品 132 和商品 1013”；也可以写“所有商品”。"
                )
        missing_items = [
            item_id for item_id in item_ids if item_id not in available_items
        ]
        if missing_items:
            raise WebRequestError(
                f"数据中找不到商品 {missing_items}。可用示例："
                f"{available_items[:10]}"
            )

        all_warehouses = bool(
            re.search(r"(?:所有|全部|每个|各个?)\s*(?:仓库|分仓|门店)", description)
        )
        nationwide = "全国" in description
        if all_warehouses:
            store_codes = [
                value for value in available_stores if value.lower() != "all"
            ] or ["all"]
        elif nationwide:
            store_codes = ["all"]
        else:
            store_codes = re.findall(
                r"(?:store|仓库|分仓|区域)(?:\s*ID)?"
                r"[_\s:=号-]*(all|全国|[A-Za-z0-9_-]+)",
                description,
                re.IGNORECASE,
            )
            store_codes = [
                "all" if value.lower() in {"all", "全国"} else str(value)
                for value in store_codes
            ]
            store_codes = self._unique(store_codes)
        if not store_codes:
            if len(available_stores) == 1:
                store_codes = available_stores
            else:
                raise WebRequestError(
                    "数据包含多个仓库。可以写“仓库 1”“仓库 1 和仓库 2”、"
                    "“所有仓库”，或使用“全国”表示全国汇总序列。"
                )
        invalid_stores = [
            store
            for store in store_codes
            if store.lower() != "all" and store not in available_stores
        ]
        if invalid_stores:
            raise WebRequestError(
                f"数据中找不到仓库 {invalid_stores}。可用仓库："
                f"{available_stores[:10]}"
            )
        targets = [
            (item_id, store_code)
            for item_id in item_ids
            for store_code in store_codes
        ]
        if len(targets) > 20:
            raise WebRequestError(
                f"当前描述会产生 {len(targets)} 个商品—仓库任务，超过单次上限 20。"
                "请缩小商品或仓库范围后分批运行。"
            )
        return targets

    @staticmethod
    def _business_result(result: dict[str, Any], run_id: str) -> dict[str, Any]:
        """Build a concise business-facing result for one workflow run."""

        report = result["report"]
        request = report["request"]
        benchmark = report["benchmark"]
        selected = next(
            candidate
            for candidate in benchmark["candidates"]
            if candidate["model"] == benchmark["selected_model"]
        )
        target = float(benchmark["target_inventory"])
        horizon = int(request["horizon"])
        forecast = [float(value) for value in benchmark.get("forecast", [])]
        return {
            "run_id": run_id,
            "item_id": request["item_id"],
            "store_code": request["store_code"],
            "horizon": horizon,
            "selected_model": benchmark["selected_model"],
            "target_inventory": target,
            "average_daily_demand": target / max(horizon, 1),
            "peak_daily_demand": max(forecast, default=0.0),
            "wape": selected["metrics"].get("wape"),
            "inventory_cost": selected["metrics"].get("inventory_cost"),
            "replenishment": report.get("replenishment", {}),
            "online_research": {
                "status": report.get("online_research", {}).get(
                    "status", "disabled"
                ),
                "provider": report.get("online_research", {}).get("provider"),
                "record_count": len(
                    report.get("online_research", {}).get("records", [])
                ),
                "result_path": report.get("online_research", {}).get(
                    "result_path"
                ),
            },
            "history_status": report.get("profile", {}).get(
                "history_status", "observed"
            ),
            "nonzero_observations": report.get("profile", {}).get(
                "nonzero_observations", 0
            ),
            "replenishment_formula": (
                "max(目标库存 + 安全库存 + 欠单 - 当前可用库存 - 已下单在途库存, 0)"
            ),
            "risks": report.get("plan", {}).get("risks", []),
            "design_explanation": report.get("design_explanation", {}),
            "performance": report.get("performance_analysis", {}).get(
                "measurements", {}
            ),
            "multi_agent_collaboration": report.get(
                "multi_agent_collaboration", {}
            ),
        }

    def overview(self) -> dict[str, Any]:
        """Return dashboard data without exposing API credentials."""

        metrics = default_metric_registry()
        profiles = default_validation_profiles()
        registry = default_registry()
        runs = self.list_runs(limit=8)
        graph_path = self._available_graph_path()
        graph = (
            CapabilityKnowledgeGraph.load(graph_path)
            if graph_path and graph_path.suffix.lower() == ".json"
            else CapabilityKnowledgeGraph.bootstrap(registry)
        )
        node_types: dict[str, int] = {}
        for _, attributes in graph.graph.nodes(data=True):
            node_type = str(attributes.get("type", "Unknown"))
            node_types[node_type] = node_types.get(node_type, 0) + 1
        return {
            "project": {
                "name": "库存算法能力工厂",
                "subtitle": "AI Agent · 能力抽取—复刻—验证—沉淀",
                "llm_mode": self.settings.llm_mode,
                "model": self.settings.model,
                "configuration_issues": self.settings.validate(),
            },
            "counts": {
                "algorithms": len(registry.names()),
                "metrics": len(metrics.names()),
                "validation_profiles": len(profiles.names()),
                "runs": len(self.list_runs(limit=None)),
                "graph_nodes": graph.graph.number_of_nodes(),
                "graph_edges": graph.graph.number_of_edges(),
            },
            "algorithms": [
                asdict(registry.metadata(name)) for name in registry.names()
            ],
            "metrics": metrics.names(),
            "validation_profiles": [
                asdict(profiles.get(name)) for name in profiles.names()
            ],
            "graph_node_types": node_types,
            "recent_runs": runs,
        }

    def audit(self) -> dict[str, Any]:
        """Return the evidence-backed written-test audit used by Web and CLI."""

        return build_submission_audit(self.workspace)

    def list_runs(self, limit: int | None = 20) -> list[dict[str, Any]]:
        """List timestamped workflow runs with concise evidence summaries."""

        if not self.output_root.exists():
            return []
        run_dirs = sorted(
            (
                path
                for path in self.output_root.iterdir()
                if path.is_dir()
                and (
                    (path / "run_manifest.json").exists()
                    or (path / "validation_report.json").exists()
                )
            ),
            key=lambda path: path.name,
            reverse=True,
        )
        if limit is not None:
            run_dirs = run_dirs[:limit]
        results = []
        for run_dir in run_dirs:
            manifest = self._read_json(run_dir / "run_manifest.json")
            report = self._read_json(run_dir / "validation_report.json")
            request = report.get("request", {})
            benchmark = report.get("benchmark", {})
            results.append(
                {
                    "id": run_dir.name,
                    "status": manifest.get("status", "unknown"),
                    "started_at": manifest.get("started_at"),
                    "finished_at": manifest.get("finished_at"),
                    "event_count": manifest.get("event_count", 0),
                    "description": request.get("description", ""),
                    "task_type": request.get("task_type", ""),
                    "item_id": request.get("item_id"),
                    "store_code": request.get("store_code"),
                    "selected_model": benchmark.get("selected_model"),
                    "target_inventory": benchmark.get("target_inventory"),
                    "repairs": len(report.get("repairs", [])),
                    "candidate_count": len(benchmark.get("candidates", [])),
                }
            )
        return results

    def run_detail(self, run_id: str) -> dict[str, Any]:
        """Return report, manifest, and structured trace events for one run."""

        if Path(run_id).name != run_id:
            raise WebRequestError("非法运行 ID。")
        run_dir = self._path(self.output_root / run_id, must_exist=True)
        report = self._read_json(run_dir / "validation_report.json")
        manifest = self._read_json(run_dir / "run_manifest.json")
        events = []
        trace_path = run_dir / "detailed_trace.jsonl"
        if trace_path.exists():
            for line in trace_path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if not report and not manifest:
            raise WebRequestError("运行产物不完整或无法读取。", 404)
        return {
            "id": run_id,
            "manifest": manifest,
            "report": report,
            "events": events,
        }

    def run_workflow(
        self,
        payload: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Execute one or more complete Agent workflows from a Web form."""

        description = str(payload.get("description", "")).strip()
        if not description:
            raise WebRequestError("请输入自然语言任务描述。")
        data_path = self._path(
            str(payload.get("data_path", "examples/data/cainiao_demo.csv")),
            must_exist=True,
        )
        targets = self._request_targets(description, data_path)
        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("capability_sources"))
        ]
        plugins = self._plugin_specs(payload.get("plugins"))
        trace_level = str(payload.get("trace_level", "full"))
        task_type = str(payload.get("task_type", "")).strip() or None
        keep_runs = int(
            payload.get("keep_runs", self.runtime_limits.default_keep_runs)
        )
        online_research = bool(payload.get("online_research", False))
        execution_mode = str(payload.get("execution_mode", "balanced"))
        run_results = []
        with self._run_lock:
            workflow = InventoryCapabilityWorkflow(
                settings=self.settings,
                knowledge_path=self.knowledge_path,
                plugin_specs=plugins,
            )
            for target_index, (item_id, store_code) in enumerate(targets):
                child_description = (
                    f"本次子任务：商品 {item_id}，仓库 {store_code}。"
                    f"用户原始要求：{description}"
                )
                def child_progress(event: dict[str, Any]) -> None:
                    if progress_callback is None:
                        return
                    child_percent = int(event.get("percent", 0))
                    overall = int(
                        (target_index * 100 + child_percent) / len(targets)
                    )
                    progress_callback(
                        {
                            **event,
                            "percent": overall,
                            "workflow_percent": child_percent,
                            "batch_index": target_index + 1,
                            "batch_total": len(targets),
                            "batch_item": {
                                "item_id": item_id,
                                "store_code": store_code,
                            },
                        }
                    )

                result = workflow.run(
                    child_description,
                    data_path,
                    self.output_root,
                    capability_sources=sources,
                    trace_level=trace_level,
                    keep_runs=max(keep_runs, len(targets)),
                    task_type_override=task_type,
                    online_research=online_research,
                    execution_mode=execution_mode,
                    progress_callback=child_progress,
                )
                report_path = Path(result["report_paths"]["json"])
                if not report_path.is_absolute():
                    report_path = self.workspace / report_path
                run_id = report_path.parent.name
                run_results.append(
                    {
                        **self._business_result(result, run_id),
                        "candidate_count": len(
                            result["benchmark"]["candidates"]
                        ),
                        "candidate_code_solutions": len(
                            result.get("candidate_code_solutions", [])
                        ),
                        "repairs": len(result.get("repairs", [])),
                        "code_validation": asdict(result["code_validation"]),
                        "detail": self.run_detail(run_id),
                    }
                )
        primary = run_results[0]
        return {
            "batch": len(run_results) > 1,
            "target_count": len(run_results),
            "results": run_results,
            "total_target_inventory": sum(
                float(item["target_inventory"]) for item in run_results
            ),
            "run_id": primary["run_id"],
            "selected_model": primary["selected_model"],
            "target_inventory": primary["target_inventory"],
            "forecast_total": primary["target_inventory"],
            "candidate_count": primary["candidate_count"],
            "candidate_code_solutions": primary[
                "candidate_code_solutions"
            ],
            "repairs": primary["repairs"],
            "code_validation": primary["code_validation"],
            "detail": primary["detail"],
        }

    def run_artifact(self, run_id: str, artifact: str) -> tuple[bytes, str]:
        """Return one allow-listed report artifact for inline viewing or download."""

        allowed = {
            "report.json": ("validation_report.json", "application/json; charset=utf-8"),
            "report.md": ("validation_report.md", "text/markdown; charset=utf-8"),
            "business.md": ("business_report.md", "text/markdown; charset=utf-8"),
            "trace.md": ("detailed_trace.md", "text/markdown; charset=utf-8"),
            "manifest.json": ("run_manifest.json", "application/json; charset=utf-8"),
            "performance.json": (
                "performance_analysis.json",
                "application/json; charset=utf-8",
            ),
            "experience.json": (
                "failure_experience.json",
                "application/json; charset=utf-8",
            ),
            "collaboration.json": (
                "generated/multi_agent_collaboration.json",
                "application/json; charset=utf-8",
            ),
            "blueprint.json": (
                "generated/implementation_blueprint.json",
                "application/json; charset=utf-8",
            ),
        }
        if artifact not in allowed:
            raise WebRequestError("不支持的运行产物。", 404)
        if Path(run_id).name != run_id:
            raise WebRequestError("非法运行 ID。")
        filename, content_type = allowed[artifact]
        path = self._path(self.output_root / run_id / filename, must_exist=True)
        return path.read_bytes(), content_type

    def benchmark(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run task-configured candidate comparison without the full workflow."""

        source = self._path(
            str(payload.get("data_path", "examples/data/cainiao_demo.csv")),
            must_exist=True,
        )
        item_id = int(payload.get("item_id"))
        store_code = str(payload.get("store_code", "")).strip()
        if not store_code:
            raise WebRequestError("请输入仓库编码。")
        model_names = self._string_list(payload.get("models")) or None
        plugins = self._plugin_specs(payload.get("plugins"))
        metrics = default_metric_registry()
        profiles = default_validation_profiles()
        loaded = load_plugins(plugins, metrics, profiles)
        task_type = str(payload.get("task_type", "inventory_target"))
        is_raw_source = source.is_dir() or source.suffix.lower() == ".zip"
        if is_raw_source:
            frame = load_location_frame(source, store_code)
            costs = resolve_inventory_costs(
                create_cainiao_loader(source).load_costs(),
                item_id,
                store_code,
            )
        else:
            frame = load_panel_csv(source)
            costs = (
                load_business_costs(source, item_id, store_code)
                or UNIT_COSTS
            )
        result = benchmark_series(
            frame,
            item_id=item_id,
            store_code=store_code,
            model_names=model_names,
            horizon=int(payload.get("horizon", 14)),
            folds=(
                int(payload["folds"])
                if payload.get("folds") not in (None, "")
                else None
            ),
            costs=costs,
            allow_missing=is_raw_source,
            validation_profile=profiles.get(task_type),
            metric_registry=metrics,
        )
        result["plugins"] = plugin_manifest(loaded)
        return result

    def extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract capabilities from local documents or code and update knowledge."""

        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("sources"))
        ]
        if not sources:
            raise WebRequestError("请至少提供一个能力来源。")
        output = self._path(
            str(
                payload.get(
                    "output",
                    "artifacts/web/extraction/extracted_capabilities.json",
                )
            )
        )
        agent = CapabilityExtractionAgent(create_llm(self.settings))
        capabilities = agent.extract_sources(sources)
        result_path = agent.write_result(capabilities, output, agent.scan_reports)
        knowledge_paths = None
        if bool(payload.get("update_knowledge", True)):
            knowledge = (
                CapabilityKnowledgeGraph.load(self.knowledge_path)
                if self.knowledge_path.exists()
                else CapabilityKnowledgeGraph.bootstrap()
            )
            knowledge.ingest_capabilities(capabilities)
            knowledge.save(
                self.knowledge_path,
                self.knowledge_path.with_suffix(".graphml"),
                self.knowledge_path.with_suffix(".html"),
            )
            knowledge_paths = {
                "json": str(self.knowledge_path),
                "graphml": str(self.knowledge_path.with_suffix(".graphml")),
                "html": str(self.knowledge_path.with_suffix(".html")),
            }
        return {
            "count": len(capabilities),
            "capabilities": [asdict(capability) for capability in capabilities],
            "scan_reports": agent.scan_reports,
            "result_path": str(result_path),
            "knowledge_graph": knowledge_paths,
        }

    def replicate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Replicate and validate one extracted capability."""

        sources = [
            self._path(source, must_exist=True)
            for source in self._string_list(payload.get("sources"))
        ]
        if not sources:
            raise WebRequestError("请至少提供一个能力来源。")
        agent = CapabilityExtractionAgent(create_llm(self.settings))
        capabilities = agent.extract_sources(sources)
        capability_name = str(payload.get("capability", "")).strip()
        if capability_name:
            matches = [
                capability
                for capability in capabilities
                if capability.name == capability_name
            ]
            if len(matches) != 1:
                raise WebRequestError(
                    f"未找到唯一能力 {capability_name!r}，匹配数量为 {len(matches)}。"
                )
            spec = matches[0]
        elif len(capabilities) == 1:
            spec = capabilities[0]
        else:
            raise WebRequestError("来源包含多个能力，请填写要复刻的能力名称。")
        output_dir = self._path(
            str(payload.get("output_dir", "artifacts/web/replication/generated"))
        )
        manifest = self._path(
            str(
                payload.get(
                    "manifest",
                    "artifacts/web/replication/review_manifest.json",
                )
            )
        )
        candidate_count = int(payload.get("candidate_count", 3))
        if not 1 <= candidate_count <= 5:
            raise WebRequestError("代码实现候选数必须在 1 到 5 之间。")
        result = CapabilityReplicator().replicate(
            spec,
            output_dir,
            manifest,
            llm=create_llm(self.settings),
            reference_model=(
                str(payload.get("reference_model", "")).strip() or None
            ),
            approved=bool(payload.get("approved", False)),
            candidate_count=candidate_count,
        )
        return result

    def versions(self, model: str) -> dict[str, Any]:
        """Return capability versions and lifecycle events for one model."""

        if not model.strip():
            raise WebRequestError("请提供模型名称。")
        if not self.knowledge_path.exists():
            return {"model": model, "versions": [], "events": []}
        knowledge = CapabilityKnowledgeGraph.load(self.knowledge_path)
        return {
            "model": model,
            "versions": knowledge.capability_versions(model),
            "events": knowledge.version_events(model),
        }

    def manage_version(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compare, promote, or roll back validated capability versions."""

        if not self.knowledge_path.exists():
            raise WebRequestError("运行知识图谱尚不存在，请先执行一次完整工作流。")
        model = str(payload.get("model", "")).strip()
        action = str(payload.get("action", "")).strip()
        if not model:
            raise WebRequestError("请提供模型名称。")
        knowledge = CapabilityKnowledgeGraph.load(self.knowledge_path)
        if action == "compare":
            result = knowledge.compare_versions(
                model,
                str(payload.get("left", "")),
                str(payload.get("right", "")),
            )
        elif action == "promote":
            result = {
                "event": knowledge.promote_version(
                    model, str(payload.get("version", ""))
                )
            }
        elif action == "rollback":
            result = {
                "event": knowledge.rollback_version(
                    model, str(payload.get("version", ""))
                )
            }
        else:
            raise WebRequestError("版本操作必须是 compare、promote 或 rollback。")
        knowledge.save(
            self.knowledge_path,
            self.knowledge_path.with_suffix(".graphml"),
            self.knowledge_path.with_suffix(".html"),
        )
        return {
            "action": action,
            "result": result,
            **self.versions(model),
        }

    def _available_graph_path(self) -> Path | None:
        candidates = [
            self.knowledge_path,
            self.workspace / "knowledge/base_capability_graph.json",
        ]
        return next((path for path in candidates if path.exists()), None)

    def graph_html(self) -> bytes:
        """Return the newest available interactive graph visualization."""

        candidates = [
            self.knowledge_path.with_suffix(".html"),
            self.workspace / "knowledge/base_capability_graph.html",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            graph = CapabilityKnowledgeGraph.bootstrap()
            path = self.workspace / "artifacts/web/capability_graph.html"
            graph.render_html(path)
        return path.read_bytes()
