import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inventory_agent.codegen.validator import CodeValidationResult, GeneratedCodeValidator
from inventory_agent.config import Settings
from inventory_agent.data.schema import NATIONAL_COLUMNS, STORE_COLUMNS, TARGET_COLUMN
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


ROOT = Path(__file__).resolve().parents[1]


class _AlwaysInvalidValidator:
    def validate(
        self,
        path: Path,
        reference_model: str | None = None,
        reference_parameters: dict | None = None,
    ) -> CodeValidationResult:
        del path, reference_model, reference_parameters
        return CodeValidationResult(False, {}, ("runtime: forced failure",))


class _FailsOnceValidator:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = GeneratedCodeValidator()

    def validate(
        self,
        path: Path,
        reference_model: str | None = None,
        reference_parameters: dict | None = None,
    ) -> CodeValidationResult:
        self.calls += 1
        if self.calls == 1:
            return CodeValidationResult(
                False,
                {
                    "syntax": False,
                    "imports": False,
                    "interface": False,
                    "runtime": False,
                    "stability": False,
                    "equivalence": False,
                },
                ("syntax: forced reusable failure at line 12",),
            )
        return self.delegate.validate(
            path,
            reference_model=reference_model,
            reference_parameters=reference_parameters,
        )


def test_end_to_end_mock_workflow(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=140, freq="D")
    data = pd.DataFrame(
        {
            "date": dates,
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 20),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    progress_events = []
    result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天需求",
        data_path,
        tmp_path / "runs",
        trace_level="full",
        keep_runs=2,
        progress_callback=progress_events.append,
    )
    assert result["code_validation"].valid
    assert Path(result["report_paths"]["json"]).exists()
    assert Path(result["report_paths"]["markdown"]).exists()
    business_report = Path(result["report_paths"]["business_markdown"])
    assert business_report.exists()
    business_text = business_report.read_text(encoding="utf-8")
    assert "库存预测业务建议" in business_text
    assert "建议补货量" in business_text
    assert "当前可用库存" in business_text
    assert (tmp_path / "knowledge.graphml").exists()
    assert (tmp_path / "knowledge.html").exists()
    assert result["report"]["validation_profile"]["name"] == "inventory_target"
    assert result["code_validation"].checks["equivalence"]
    assert result["generated"].generation_mode == "spec_template"
    assert result["generated"].source_hash
    assert result["code_validation"].mean_latency_ms is not None
    assert Path(result["report_paths"]["performance"]).exists()
    assert Path(result["report_paths"]["failure_experience"]).exists()
    assert result["report"]["performance_analysis"]["recommendations"]
    assert result["report"]["design_explanation"]["summary"]
    assert result["report"]["selection_explanation"]["data_facts"]
    assert result["report"]["capability_version"]["capability_version"] == "1.0.0"
    assert len(result["implementation_candidates"]) == 1
    assert result["implementation_candidates"][0]["selected"]
    assert len(result["candidate_code_solutions"]) == 3
    assert result["trace_paths"] is not None
    assert len(result["execution_tasks"]) == 9
    assert all(
        1 <= event["task_index"] <= event["task_total"] == 9
        for event in progress_events
    )
    generation_progress = next(
        event for event in progress_events if event["stage"] == "code_generation"
    )
    assert generation_progress["task_index"] == 7
    assert generation_progress["task_title"] == "生成并审查独立代码实现"
    assert generation_progress["percent"] >= 66
    assert generation_progress["stage_percent"] == 58
    trace_events = [
        json.loads(line)
        for line in Path(result["trace_paths"]["jsonl"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    stages = {event["stage"] for event in trace_events}
    assert {
        "requirement_understanding",
        "candidate_comparison",
        "candidate_code_generation",
        "selected_code_generation",
        "code_validation",
        "experience_deposition",
        "report_generation",
    } <= stages
    assert any(event["component"] == "MockLLMClient" for event in trace_events)
    run_dir = Path(result["trace_paths"]["manifest"]).parent
    assert not list(run_dir.rglob("__pycache__"))
    saved_graph = CapabilityKnowledgeGraph.load(tmp_path / "knowledge.json")
    versions = [
        attributes
        for _, attributes in saved_graph.graph.nodes(data=True)
        if attributes.get("type") == "CapabilityVersion"
    ]
    assert len(versions) == 1
    assert versions[0]["source_hash"] == result["generated"].source_hash


def test_workflow_optional_online_research_is_persisted(tmp_path: Path):
    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=70, freq="D"),
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 10),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)

    class FakeResearchAgent:
        def research(self, description, profile, output, limit=5):
            del description, profile, limit
            payload = {
                "schema_version": "1.0",
                "created_at": "2026-07-17T00:00:00+00:00",
                "status": "success",
                "provider": "crossref",
                "query": "inventory forecasting",
                "records": [
                    {
                        "title": "Seasonal inventory forecasting",
                        "doi": "10.1000/workflow-demo",
                        "url": "https://doi.org/10.1000/workflow-demo",
                        "relevance_score": 1.0,
                    }
                ],
                "analysis": {
                    "recommended_models": ["seasonal_naive"],
                    "findings": ["seasonality evidence"],
                    "risks": [],
                    "analysis_mode": "deterministic",
                },
                "warnings": [],
                "safety_policy": "evidence only",
            }
            Path(output).write_text(json.dumps(payload), encoding="utf-8")
            payload["result_path"] = str(output)
            return payload

    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    workflow.research_agent = FakeResearchAgent()
    result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天库存",
        data_path,
        tmp_path / "runs",
        online_research=True,
    )

    research = result["report"]["online_research"]
    assert research["status"] == "success"
    assert Path(research["result_path"]).exists()
    assert result["plan"].design_basis["online_research"]["record_count"] == 1
    assert any(
        attributes.get("source_type") == "online_research"
        for _, attributes in workflow.knowledge.graph.nodes(data=True)
    )


def test_all_zero_history_is_reported_as_data_warning(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    data_path = tmp_path / "zero-panel.csv"
    pd.DataFrame(
        {
            "date": dates,
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": 0,
        }
    ).to_csv(data_path, index=False)
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )

    result = workflow.run(
        "为商品 42 在仓库 1 预测未来7天需求",
        data_path,
        tmp_path / "runs",
        trace_level="basic",
    )

    assert result["profile"]["history_status"] == "all_zero_history"
    business_text = Path(
        result["report_paths"]["business_markdown"]
    ).read_text(encoding="utf-8")
    assert "历史目标销量全部为 0" in business_text
    assert "不是高准确率证明" in business_text


def test_workflow_uses_companion_inventory_tables_for_real_order_advice(
    tmp_path: Path,
):
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )

    result = workflow.run(
        "为商品 1001 在仓库 1 预测未来14天需求并给出补货量",
        ROOT / "examples/business_data/demand_history.csv",
        tmp_path / "runs",
        trace_level="basic",
    )

    assert result["benchmark"]["costs"]["source"] == "replenishment_policy.csv"
    advice = result["report"]["replenishment"]
    assert advice["available"] is True
    assert advice["recommended_order_qty"] > 0
    business_text = Path(
        result["report_paths"]["business_markdown"]
    ).read_text(encoding="utf-8")
    assert "应用最小订货量、包装倍数和仓容后" in business_text


def test_workflow_extracts_source_before_replication(tmp_path: Path):
    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=140, freq="D"),
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 20),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    source = tmp_path / "moving_average.md"
    source.write_text(
        """# Extracted moving average
- name: moving_average
- description: Extracted from a business capability document.
- template_name: moving_average
- suitable_for: stable, weekly_seasonal
- metrics: inventory_cost, wape
- parameters: {"window": 14}
- version: 1.2.0
""",
        encoding="utf-8",
    )
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天目标库存",
        data_path,
        tmp_path / "runs",
        capability_sources=[source],
    )
    assert result["report"]["capability_extraction"]["count"] == 1
    extraction_path = result["report"]["capability_extraction"]["result_path"]
    assert Path(extraction_path).exists()
    saved_graph = CapabilityKnowledgeGraph.load(tmp_path / "knowledge.json")
    source_nodes = [
        attributes
        for _, attributes in saved_graph.graph.nodes(data=True)
        if attributes.get("type") == "SourceArtifact"
    ]
    assert len(source_nodes) == 1


def test_end_to_end_raw_directory_nationwide_uses_competition_costs(tmp_path: Path):
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    national_rows = []
    store_rows = []
    for index, date in enumerate(dates):
        national = [0] * len(NATIONAL_COLUMNS)
        national[NATIONAL_COLUMNS.index("date")] = int(date.strftime("%Y%m%d"))
        national[NATIONAL_COLUMNS.index("item_id")] = 42
        national[NATIONAL_COLUMNS.index(TARGET_COLUMN)] = index % 7 + 1
        national_rows.append(national)

        store = [0] * len(STORE_COLUMNS)
        store[STORE_COLUMNS.index("date")] = int(date.strftime("%Y%m%d"))
        store[STORE_COLUMNS.index("item_id")] = 42
        store[STORE_COLUMNS.index("store_code")] = 1
        store[STORE_COLUMNS.index(TARGET_COLUMN)] = index % 7 + 1
        store_rows.append(store)

    pd.DataFrame(national_rows).to_csv(
        tmp_path / "item_feature2.csv", index=False, header=False
    )
    pd.DataFrame(store_rows).to_csv(
        tmp_path / "item_store_feature2.csv", index=False, header=False
    )
    pd.DataFrame([[42, "all", "3_7"], [42, "1", "2_5"]]).to_csv(
        tmp_path / "config2.csv", index=False, header=False
    )

    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=tmp_path / "knowledge.json",
    )
    result = workflow.run(
        "为商品 42 预测全国未来14天目标库存",
        tmp_path,
        tmp_path / "runs",
    )
    assert result["benchmark"]["store_code"] == "all"
    assert result["benchmark"]["evaluation_unit"] == "horizon_total"
    assert result["benchmark"]["costs"]["understock_cost"] == 3.0
    assert result["benchmark"]["costs"]["overstock_cost"] == 7.0
    assert result["benchmark"]["target_inventory"] >= 0

    warehouse_result = workflow.run(
        "为商品 42 在仓库 1 预测未来14天目标库存",
        tmp_path,
        tmp_path / "runs",
    )
    assert warehouse_result["benchmark"]["store_code"] == "1"
    assert warehouse_result["benchmark"]["costs"]["understock_cost"] == 2.0
    assert warehouse_result["benchmark"]["costs"]["overstock_cost"] == 5.0


def test_failed_workflow_records_two_repairs_and_failure_experience(tmp_path: Path):
    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=70, freq="D"),
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 10),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    knowledge_path = tmp_path / "knowledge.json"
    workflow = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=knowledge_path,
    )
    workflow.validator = _AlwaysInvalidValidator()

    with pytest.raises(RuntimeError, match="failed after repair budget"):
        workflow.run(
            "为商品 42 在仓库 1 预测未来14天目标库存",
            data_path,
            tmp_path / "runs",
        )

    failed_run = next((tmp_path / "runs").iterdir())
    failed_manifest = json.loads(
        (failed_run / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert failed_manifest["status"] == "failed"
    failed_events = [
        json.loads(line)
        for line in (failed_run / "detailed_trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert sum(event["stage"] == "code_validation" for event in failed_events) == 3

    saved = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"),
        knowledge_path=knowledge_path,
    ).knowledge
    failures = [
        attributes
        for _, attributes in saved.graph.nodes(data=True)
        if attributes.get("type") == "ValidationRun"
    ]
    repairs = [
        attributes["description"]
        for _, attributes in saved.graph.nodes(data=True)
        if attributes.get("type") == "RepairStrategy"
    ]
    assert failures[0]["status"] == "failure"
    assert "第 1 轮修复" in repairs[0]
    assert "第 2 轮修复" in repairs[0]


def test_later_run_reuses_successful_repair_experience(tmp_path: Path):
    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=70, freq="D"),
            "item_id": 42,
            "store_code": 1,
            "qty_alipay_njhs": np.tile([1, 2, 3, 4, 5, 6, 7], 10),
        }
    )
    data_path = tmp_path / "panel.csv"
    data.to_csv(data_path, index=False)
    knowledge_path = tmp_path / "knowledge.json"

    first = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"), knowledge_path=knowledge_path
    )
    first.validator = _FailsOnceValidator()
    first_result = first.run(
        "为商品 42 在仓库 1 预测未来14天目标库存",
        data_path,
        tmp_path / "runs",
    )
    assert first_result["failure_history"][0]["category"] == "syntax"

    second = InventoryCapabilityWorkflow(
        settings=Settings(llm_mode="mock"), knowledge_path=knowledge_path
    )
    second.validator = _FailsOnceValidator()
    second_result = second.run(
        "为商品 42 在仓库 1 预测未来14天目标库存",
        data_path,
        tmp_path / "runs",
    )

    assert len(second_result["repair_experience_used"]) == 1
    assert second_result["repair_experience_used"][0]["category"] == "syntax"
    assert "reused_successful_repairs=1" in second_result["repairs"][0]
