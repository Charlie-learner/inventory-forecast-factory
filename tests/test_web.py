import base64
import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd
import pytest

from inventory_agent.config import Settings
from inventory_agent.data.schema import NATIONAL_COLUMNS, STORE_COLUMNS, TARGET_COLUMN
from inventory_agent.execution import RuntimeLimits
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.web.api_docs import openapi_document, post_route_handlers
from inventory_agent.web.app import WebApplication
from inventory_agent.web.server import ASSET_ROOT, create_server


ROOT = Path(__file__).resolve().parents[1]


def _request(url: str, payload: dict | None = None) -> tuple[int, str, str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=10) as response:
        return (
            response.status,
            response.headers.get_content_type(),
            response.read().decode("utf-8"),
        )


def test_web_index_is_self_contained_and_utf8():
    source = (ASSET_ROOT / "index.html").read_text(encoding="utf-8")

    assert "<title>库存算法能力工厂</title>" in source
    assert "和库存预测 Agent 对话" in source
    assert "上传一个或多个文件" in source
    assert 'type="file" accept=".csv,.zip" multiple' in source
    assert "/api/datasets/map" in source
    assert "单商品业务预测" in source
    assert "多商品全国预测" in source
    assert "所有仓库预测" in source
    assert "间歇需求预测" in source
    assert "全零历史诊断" in source
    assert "预测精度任务" in source
    assert 'id="runDescription"' in source
    assert "prompt-example" in source
    assert "/api/docs" in source
    assert "/api/openapi.json" in source
    assert 'data-view="audit"' in source
    assert 'id="view-audit"' in source
    assert "/api/audit" in source
    assert "Planner Agent 执行计划" in source
    assert "任务 ${taskIndex}/${taskTotal}" in source
    assert "批次 ${batchIndex}/${batchTotal}" in source
    assert 'id="useBusinessData"' in source
    assert "库存快照和补货策略" in source
    assert "真实验证报告" in source
    assert "styles.css" not in source
    assert "app.js" not in source


def test_web_server_exposes_dashboard_api_and_graph(tmp_path: Path):
    application = WebApplication(
        workspace=ROOT,
        settings=Settings(llm_mode="mock"),
        output_root=tmp_path.relative_to(ROOT) if ROOT in tmp_path.parents else "artifacts/runs",
        knowledge_path="knowledge/base_capability_graph.json",
    )
    server = create_server(application, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, content_type, index = _request(base_url + "/")
        assert status == 200
        assert content_type == "text/html"
        assert "库存算法能力工厂" in index

        status, content_type, body = _request(base_url + "/api/overview")
        overview = json.loads(body)
        assert status == 200
        assert content_type == "application/json"
        assert overview["counts"]["algorithms"] == 5
        assert overview["counts"]["validation_profiles"] >= 3

        status, content_type, body = _request(base_url + "/api/audit")
        audit = json.loads(body)
        assert status == 200
        assert content_type == "application/json"
        assert audit["summary"]["missing"] == 0
        assert audit["closed_loop"][0]["stage"] == "需求理解"

        status, content_type, graph = _request(base_url + "/graph")
        assert status == 200
        assert content_type == "text/html"
        assert "库存算法能力知识图谱" in graph

        status, content_type, api_docs = _request(base_url + "/api/docs")
        assert status == 200
        assert content_type == "text/html"
        assert "库存算法能力工厂 API" in api_docs

        status, content_type, body = _request(
            base_url + "/api/openapi.json"
        )
        schema = json.loads(body)
        assert status == 200
        assert content_type == "application/json"
        assert schema["openapi"] == "3.0.3"
        assert "/api/run" in schema["paths"]
        assert "/api/audit" in schema["paths"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_api_documentation_and_post_dispatch_share_the_same_catalog():
    schema = openapi_document()
    post_paths = {
        path
        for path, operations in schema["paths"].items()
        if "post" in operations
    }

    assert post_paths == set(post_route_handlers())
    assert post_route_handlers()["/api/run"] == "run_workflow"
    assert post_route_handlers()["/api/replicate"] == "replicate"


def test_web_server_logs_internal_errors_without_exposing_details(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
    )

    def fail_overview():
        raise RuntimeError("private-path-and-provider-detail")

    application.overview = fail_overview  # type: ignore[method-assign]
    server = create_server(application, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as captured:
            _request(
                f"http://127.0.0.1:{server.server_address[1]}/api/overview"
            )
        payload = json.loads(captured.value.read().decode("utf-8"))
        assert captured.value.code == 500
        assert payload["error_type"] == "RuntimeError"
        assert "private-path" not in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_upload_limit_is_injected_instead_of_hard_coded(tmp_path: Path):
    limits = RuntimeLimits(
        max_http_body_bytes=32,
        max_upload_file_bytes=8,
    )
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        runtime_limits=limits,
    )

    with pytest.raises(ValueError, match="不能超过 8 B"):
        application.upload_dataset(
            {
                "filename": "data.csv",
                "content_base64": base64.b64encode(b"123456789").decode("ascii"),
            }
        )


def test_web_benchmark_api_uses_real_backtest():
    application = WebApplication(
        workspace=ROOT,
        settings=Settings(llm_mode="mock"),
        output_root="artifacts/runs",
        knowledge_path="knowledge/base_capability_graph.json",
    )

    result = application.benchmark(
        {
            "data_path": "examples/data/cainiao_demo.csv",
            "item_id": 3424,
            "store_code": "1",
            "models": ["last_value", "moving_average"],
            "horizon": 14,
            "task_type": "inventory_target",
        }
    )

    assert len(result["candidates"]) == 2
    assert result["selected_model"] in {"last_value", "moving_average"}
    assert result["validation_profile"]["primary_metric"] == "inventory_cost"


def test_web_version_management_exposes_lifecycle_and_metrics(tmp_path: Path):
    knowledge_path = tmp_path / "knowledge.json"
    graph = CapabilityKnowledgeGraph.bootstrap()
    graph.record_validation(
        1,
        "1",
        "moving_average",
        {"inventory_cost": 1.0},
        validation_checks={"syntax": True},
        capability_version={
            "capability_version": "1.0.0",
            "generation_mode": "spec_template",
            "spec_hash": "1" * 64,
            "source_hash": "a" * 64,
            "source_ref": "source.md",
            "generated_path": "generated.py",
        },
    )
    graph.save(knowledge_path)
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        knowledge_path="knowledge.json",
        output_root="runs",
    )

    before = application.versions("moving_average")
    assert before["versions"][0]["validation_status"] == "success"

    after = application.manage_version(
        {
            "action": "promote",
            "model": "moving_average",
            "version": "a" * 12,
        }
    )

    assert after["versions"][0]["lifecycle_status"] == "active"
    assert after["events"][0]["action"] == "promote"


def test_web_upload_accepts_alias_csv_and_returns_dataset_profile(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )
    content = (
        "ds,sku_id,warehouse_id,sales\n"
        "2026-01-01,1001,WH-A,3\n"
        "2026-01-02,1001,WH-A,5\n"
    ).encode()

    result = application.upload_dataset(
        {
            "filename": "my-demand.csv",
            "content_base64": base64.b64encode(content).decode(),
        }
    )

    uploaded = result["uploaded_file"]
    dataset = result["dataset"]
    assert uploaded["rows"] == 2
    assert dataset["ready"] is True
    assert dataset["item_count"] == 1
    assert dataset["store_count"] == 1
    assert dataset["item_examples"] == [1001]
    assert (tmp_path / uploaded["path"]).exists()


def _cainiao_row(columns: list[str], *, item_id: int, store_code: int | None = None):
    values = list(range(len(columns)))
    values[0] = 20151227
    values[1] = item_id
    if store_code is not None:
        values[2] = store_code
    values[columns.index(TARGET_COLUMN)] = 7
    return values


def _upload(
    application: WebApplication,
    filename: str,
    content: bytes,
    session_id: str = "testsession01",
) -> dict:
    return application.upload_dataset(
        {
            "session_id": session_id,
            "filename": filename,
            "content_base64": base64.b64encode(content).decode(),
        }
    )


def test_web_combines_cainiao_multi_file_upload_and_shows_examples(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )
    national = pd.DataFrame(
        [_cainiao_row(NATIONAL_COLUMNS, item_id=3424)]
    ).to_csv(index=False, header=False).encode()
    store = pd.DataFrame(
        [_cainiao_row(STORE_COLUMNS, item_id=3424, store_code=1)]
    ).to_csv(index=False, header=False).encode()
    costs = b"3424,all,10.44_20.88\n3424,1,10.44_20.88\n"

    cost_result = _upload(application, "config2.csv", costs)
    assert cost_result["uploaded_file"]["kind"] == "cost_config"
    assert cost_result["dataset"]["ready"] is False

    _upload(application, "item_feature2.csv", national)
    result = _upload(application, "item_store_feature2.csv", store)

    dataset = result["dataset"]
    assert dataset["ready"] is True
    assert dataset["mode"] == "directory_bundle"
    assert dataset["item_examples"] == [3424]
    assert set(dataset["store_examples"]) == {"all", "1"}
    assert (tmp_path / dataset["runnable_path"] / "config2.csv").exists()


def test_web_unrecognized_csv_can_be_mapped_without_reupload(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )
    content = (
        "period,material,site,units\n"
        "2026-01-01,1001,WH-A,3\n"
        "2026-01-02,1001,WH-A,5\n"
    ).encode()

    uploaded = _upload(application, "erp-export.csv", content)
    assert uploaded["uploaded_file"]["status"] == "needs_mapping"
    assert uploaded["dataset"]["ready"] is False

    mapped = application.map_dataset_columns(
        {
            "session_id": "testsession01",
            "filename": "erp-export.csv",
            "mapping": {
                "date": "period",
                "item_id": "material",
                "store_code": "site",
                TARGET_COLUMN: "units",
            },
        }
    )

    assert mapped["dataset"]["ready"] is True
    assert mapped["dataset"]["item_examples"] == [1001]
    assert (tmp_path / mapped["mapped_file"]["path"]).exists()


def test_web_accepts_zip_with_one_generic_csv(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )
    archive_path = tmp_path / "generic.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "exports/demand.csv",
            "date,item_id,store_code,demand\n2026-01-01,1001,WH-A,3\n",
        )

    result = _upload(application, "generic.zip", archive_path.read_bytes())

    assert result["uploaded_file"]["kind"] == "panel"
    assert result["dataset"]["ready"] is True
    assert result["dataset"]["item_examples"] == [1001]


def test_web_can_serve_real_report_artifacts(tmp_path: Path):
    run_dir = tmp_path / "runs" / "20260717_120000_000001"
    run_dir.mkdir(parents=True)
    (run_dir / "validation_report.md").write_text("# 真实报告", encoding="utf-8")
    (run_dir / "validation_report.json").write_text("{}", encoding="utf-8")
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )

    content, content_type = application.run_artifact(
        run_dir.name, "report.md"
    )

    assert content.decode("utf-8") == "# 真实报告"
    assert content_type.startswith("text/markdown")


def test_web_infers_unique_item_and_store_from_uploaded_csv(tmp_path: Path):
    source = tmp_path / "single-series.csv"
    source.write_text(
        "date,item_id,store_code,demand\n"
        "2026-01-01,1001,WH-A,3\n"
        "2026-01-02,1001,WH-A,5\n",
        encoding="utf-8",
    )

    description = WebApplication._description_with_dataset_context(
        "预测未来14天需求并给出目标库存",
        source,
    )

    assert "商品 1001" in description
    assert "仓库 WH-A" in description


def test_web_expands_multiple_items_and_all_warehouses(tmp_path: Path):
    source = tmp_path / "panel.csv"
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=8).tolist() * 4,
            "item_id": [132] * 16 + [1013] * 16,
            "store_code": (["1"] * 8 + ["2"] * 8) * 2,
            "demand": list(range(1, 9)) * 4,
        }
    ).to_csv(source, index=False)
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )

    assert application._request_targets(
        "预测商品132和商品1013在仓库all未来14天库存",
        source,
    ) == [(132, "all"), (1013, "all")]
    assert application._request_targets(
        "预测商品132和1013在仓库all未来14天库存",
        source,
    ) == [(132, "all"), (1013, "all")]
    assert application._request_targets(
        "预测商品132在所有仓库未来7天库存",
        source,
    ) == [(132, "1"), (132, "2")]


def test_web_runs_one_complete_subworkflow_per_requested_item(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=140, freq="D")
    source = tmp_path / "panel.csv"
    pd.concat(
        [
            pd.DataFrame(
                {
                    "date": dates,
                    "item_id": item_id,
                    "store_code": "all",
                    "demand": [1, 2, 3, 4, 5, 6, 7] * 20,
                }
            )
            for item_id in (132, 1013)
        ],
        ignore_index=True,
    ).to_csv(source, index=False)
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )

    progress_events = []
    result = application.run_workflow(
        {
            "description": (
                "预测商品132和商品1013在仓库all未来14天需求，"
                "并给出进货和补货建议"
            ),
            "data_path": str(source.relative_to(tmp_path)),
            "trace_level": "basic",
            "keep_runs": 5,
        },
        progress_callback=progress_events.append,
    )

    assert result["batch"] is True
    assert result["target_count"] == 2
    assert [item["item_id"] for item in result["results"]] == [132, 1013]
    assert {event["batch_index"] for event in progress_events} == {1, 2}
    assert all(event["batch_total"] == 2 for event in progress_events)
    assert all(not event["message"].startswith("任务 ") for event in progress_events)
    assert all(1 <= event["task_index"] <= event["task_total"] for event in progress_events)
    for item in result["results"]:
        assert item["replenishment_formula"]
        assert (
            tmp_path
            / "runs"
            / item["run_id"]
            / "business_report.md"
        ).exists()


def test_web_async_job_reports_progress_and_result(tmp_path: Path):
    application = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )

    def fake_run(payload, progress_callback=None):
        assert payload["description"] == "demo"
        progress_callback(
            {
                "stage": "code_validation",
                "percent": 82,
                "message": "正在验证",
                "task_index": 8,
                "task_total": 9,
                "task_title": "验证与必要时修复",
            }
        )
        return {"status": "ok"}

    application.run_workflow = fake_run
    created = application.start_workflow({"description": "demo"})
    deadline = time.time() + 2
    status = application.job_status(created["job_id"])
    while status["status"] not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.01)
        status = application.job_status(created["job_id"])

    assert status["status"] == "completed"
    assert status["percent"] == 100
    assert status["task_index"] == 8
    assert status["task_total"] == 9
    assert status["result"] == {"status": "ok"}

    restarted = WebApplication(
        workspace=tmp_path,
        settings=Settings(llm_mode="mock"),
        output_root="runs",
        knowledge_path="knowledge.json",
    )
    persisted = restarted.job_status(created["job_id"])
    assert persisted["status"] == "completed"
    assert persisted["result"] == {"status": "ok"}
