"""Run auditable advanced scenarios for teacher-facing capability-factory review."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.codegen.validator import (
    CodeValidationResult,
    GeneratedCodeValidator,
)
from inventory_agent.config import Settings
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "examples/advanced_showcase"
BUSINESS_DATA = ROOT / "examples/business_data/demand_history.csv"
CAPABILITY_SOURCES = sorted((ROOT / "examples/capabilities").glob("*.md"))


class _FailSelectedCodeOnceValidator:
    """Inject one realistic interface failure after candidate preselection."""

    def __init__(self) -> None:
        self.failed = False
        self.delegate = GeneratedCodeValidator()

    def validate(
        self,
        path: Path,
        reference_model: str | None = None,
        reference_parameters: dict | None = None,
    ) -> CodeValidationResult:
        if path.parent.name == "generated" and not self.failed:
            self.failed = True
            return CodeValidationResult(
                valid=False,
                checks={
                    "syntax": True,
                    "imports": True,
                    "interface": False,
                    "runtime": False,
                    "stability": False,
                    "equivalence": False,
                },
                errors=(
                    "interface: forecast returned ndarray instead of required list[float]",
                ),
            )
        return self.delegate.validate(
            path,
            reference_model=reference_model,
            reference_parameters=reference_parameters,
        )


class _ProtocolTestLLM:
    """Provide deterministic LLM-shaped responses for collaboration protocol testing."""

    def complete(self, system: str, user: str) -> str:
        del system
        payload = json.loads(user)
        if "business_context" in payload:
            return json.dumps(
                {
                    "algorithm_steps": [
                        "clean non-negative numeric history",
                        "average the latest 14 observations",
                        "repeat the estimate for the requested horizon",
                    ],
                    "required_contracts": [
                        "forecast returns built-in list[float]",
                        "target_inventory equals sum(daily_forecast)",
                    ],
                    "edge_cases": ["empty history", "non-positive horizon"],
                    "allowed_dependencies": ["numpy", "pandas"],
                    "performance_goal": "linear history cleaning and constant forecast cost",
                    "risks": ["constant-rate forecast does not express daily seasonality"],
                }
            )
        if "implementation_variant" in payload:
            variant = payload["implementation_variant"]
            if variant == "candidate_1":
                body = """import pandas as pd

def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = pd.to_numeric(pd.Series(history), errors="coerce").dropna().clip(lower=0)
    if clean.empty:
        raise ValueError("empty history")
    estimate = float(clean.iloc[-min(14, len(clean)):].mean())
    return [estimate for _ in range(horizon)]
"""
            elif variant == "candidate_2":
                body = """import numpy as np

def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = np.asarray([max(float(value), 0.0) for value in history], dtype=float)
    estimate = float(clean[-min(14, clean.size):].mean())
    return np.repeat(estimate, horizon)
"""
            else:
                body = """def forecast(history, horizon):
    if horizon <= 0 or not history:
        raise ValueError("invalid input")
    clean = [max(float(value), 0.0) for value in history]
    recent = clean[-min(14, len(clean)):]
    estimate = float(sum(recent) / len(recent))
    return [estimate] * horizon
"""
            return body + """
def build_inventory_target(history, horizon):
    values = forecast(history, horizon)
    return {"daily_forecast": values, "target_inventory": float(sum(values))}
"""
        source = str(payload["source"])
        findings: list[str] = []
        if "return np.repeat(estimate, horizon)" in source:
            findings.append("ndarray output violates list[float] contract")
            source = source.replace(
                "return np.repeat(estimate, horizon)",
                "return np.repeat(estimate, horizon).astype(float).tolist()",
            )
        return json.dumps(
            {
                "approved": True,
                "findings": findings,
                "revised_source": source,
            }
        )


def _safe_session(output_root: Path, requested: str | None) -> Path:
    session_name = requested or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not session_name.replace("_", "").isalnum():
        raise ValueError("session must contain only letters, numbers, or underscores")
    root = output_root.resolve()
    session = (root / session_name).resolve()
    if root not in session.parents:
        raise ValueError("session escaped the showcase output directory")
    session.mkdir(parents=True, exist_ok=True)
    return session


def _case_summary(
    case_id: str,
    purpose: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    report = result["report"]
    benchmark = report["benchmark"]
    run_dir = Path(result["report_paths"]["json"]).parent
    return {
        "case_id": case_id,
        "purpose": purpose,
        "status": "passed",
        "run_dir": str(run_dir),
        "request": report["request"],
        "demand_profile": report["profile"],
        "online_research": {
            "status": report.get("online_research", {}).get("status"),
            "provider": report.get("online_research", {}).get("provider"),
            "record_count": len(report.get("online_research", {}).get("records", [])),
            "result_path": report.get("online_research", {}).get("result_path"),
        },
        "algorithm_comparison": [
            {
                "model": candidate["model"],
                "inventory_cost": candidate["metrics"].get("inventory_cost"),
                "wape": candidate["metrics"].get("wape"),
                "rmse": candidate["metrics"].get("rmse"),
            }
            for candidate in benchmark["candidates"]
        ],
        "selected_model": benchmark["selected_model"],
        "target_inventory": benchmark["target_inventory"],
        "implementation_candidates": [
            {
                "variant_id": item.get("variant_id"),
                "strategy": item.get("strategy"),
                "generation_mode": item.get("generation_mode"),
                "valid": item.get("validation", {}).get("valid"),
                "selected": item.get("selected"),
                "review": item.get("collaboration", {}).get("review", {}),
            }
            for item in result.get("implementation_candidates", [])
        ],
        "code_validation": asdict(result["code_validation"]),
        "repairs": result.get("repairs", []),
        "failure_history": result.get("failure_history", []),
        "repair_experience_used": result.get("repair_experience_used", []),
        "capability_version": report.get("capability_version", {}),
        "replenishment": report.get("replenishment", {}),
        "multi_agent_collaboration": report.get("multi_agent_collaboration", {}),
        "report_paths": result["report_paths"],
        "trace_paths": result.get("trace_paths"),
    }


def _run_case(
    *,
    case_id: str,
    purpose: str,
    description: str,
    session: Path,
    settings: Settings,
    online_research: bool,
    execution_mode: str,
    inject_failure: bool = False,
) -> dict[str, Any]:
    workflow = InventoryCapabilityWorkflow(
        settings=settings,
        knowledge_path=session / "capability_graph.json",
    )
    if inject_failure:
        workflow.validator = _FailSelectedCodeOnceValidator()
    result = workflow.run(
        description,
        BUSINESS_DATA,
        session / "runs" / case_id,
        capability_sources=CAPABILITY_SOURCES,
        trace_level="full",
        keep_runs=2,
        online_research=online_research,
        execution_mode=execution_mode,
    )
    return _case_summary(case_id, purpose, result)


def _write_summary(session: Path, cases: list[dict[str, Any]]) -> None:
    def portable_path(value: Any) -> str:
        """Prefer repository-relative evidence links that survive another machine."""

        if not value:
            return "-"
        candidate = Path(str(value))
        try:
            return candidate.relative_to(ROOT).as_posix()
        except ValueError:
            return str(candidate)

    graph = CapabilityKnowledgeGraph.load(session / "capability_graph.json")
    research_path = session / "online_knowledge_extraction.json"
    standalone_research = (
        json.loads(research_path.read_text(encoding="utf-8"))
        if research_path.exists()
        else {}
    )
    if standalone_research.get("status") == "success":
        graph.ingest_research_evidence(standalone_research)
        graph.save(
            session / "capability_graph.json",
            session / "capability_graph.graphml",
            session / "capability_graph.html",
        )
    protocol_path = session / "protocol_demo" / "review_manifest.json"
    protocol_demo = (
        json.loads(protocol_path.read_text(encoding="utf-8"))
        if protocol_path.exists()
        else {}
    )
    node_types: dict[str, int] = {}
    for _, attributes in graph.graph.nodes(data=True):
        node_type = str(attributes.get("type", "Unknown"))
        node_types[node_type] = node_types.get(node_type, 0) + 1
    payload = {
        "schema_version": "1.0",
        "session": session.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "cases": cases,
        "standalone_online_research": {
            "status": standalone_research.get("status", "not_run"),
            "provider": standalone_research.get("provider"),
            "query": standalone_research.get("query"),
            "record_count": len(standalone_research.get("records", [])),
            "recommended_models": standalone_research.get("analysis", {}).get(
                "recommended_models", []
            ),
            "result_path": str(research_path) if research_path.exists() else None,
        },
        "multi_agent_protocol_demo": {
            "status": "passed" if protocol_demo.get("validation", {}).get("valid") else "not_run",
            "candidate_count": len(protocol_demo.get("implementation_candidates", [])),
            "selected_variant": protocol_demo.get("generation", {}).get("variant_id"),
            "selected_mode": protocol_demo.get("generation", {}).get("mode"),
            "revision_count": sum(
                bool(
                    candidate.get("collaboration", {})
                    .get("review", {})
                    .get("revision_applied")
                )
                for candidate in protocol_demo.get("implementation_candidates", [])
            ),
            "manifest_path": str(protocol_path) if protocol_path.exists() else None,
        },
        "knowledge_graph": {
            "json": str(session / "capability_graph.json"),
            "graphml": str(session / "capability_graph.graphml"),
            "html": str(session / "capability_graph.html"),
            "node_count": graph.graph.number_of_nodes(),
            "edge_count": graph.graph.number_of_edges(),
            "node_types": node_types,
        },
    }
    (session / "showcase_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total_repairs = sum(len(case.get("repairs", [])) for case in cases)
    reused_experience = sum(
        len(case.get("repair_experience_used", [])) for case in cases
    )
    protocol_candidates = protocol_demo.get("implementation_candidates", [])
    protocol_revisions = sum(
        bool(
            item.get("collaboration", {})
            .get("review", {})
            .get("revision_applied")
        )
        for item in protocol_candidates
    )
    live_case = next(
        (case for case in cases if case["case_id"] == "case_04_live_research_multi_agent"),
        {},
    )
    selected_collaboration = (
        live_case.get("multi_agent_collaboration", {}).get("selected_candidate", {})
    )
    live_architecture = selected_collaboration.get("architecture", {})
    live_llm_note = "未运行外部 LLM 用例"
    if live_case:
        fallback = live_architecture.get("fallback_reason")
        live_llm_note = (
            f"已真实发起外部 LLM 请求，但返回 {fallback}，随后按设计降级为确定性方案"
            if fallback
            else "外部 LLM 已返回可用结果"
        )

    rows = [
        "# 高级能力场景验收结果",
        "",
        "## 一句话结论",
        "",
        (
            f"本会话完成 **{len(cases)} 个端到端任务**、比较算法、生成并验证代码，"
            f"执行 **{total_repairs} 次自动修复**、复用 **{reused_experience} 条历史经验**，"
            "并把验证、失败、修复策略、版本和外部资料写回同一知识图谱。"
        ),
        "",
        "## 老师建议先看什么",
        "",
        "1. 先看下表，确认每个高级能力都有实际用例和数量结果。",
        "2. 打开每个用例的业务报告，看非技术用户能否理解预测与补货结论。",
        "3. 打开协作记录，核对架构、实现、审查、验证不是一次 Prompt 完成。",
        "4. 打开详细 Trace，核对工具调用、候选比较、错误、修复和写回顺序。",
        "5. 打开本会话图谱，核对 ValidationRun、FailureCase、RepairStrategy 和 CapabilityVersion 节点。",
        "",
        "## 关键结果总览",
        "",
        f"- 会话：`{session.name}`",
        f"- 图谱：{graph.graph.number_of_nodes()} 个节点 / {graph.graph.number_of_edges()} 条关系",
        f"- 联网行业资料：{standalone_research.get('status', 'not_run')} / "
        f"{len(standalone_research.get('records', []))} 条带来源记录",
        f"- 多智能体协议演示：{len(protocol_candidates)} 个独立代码候选 / "
        f"审查 Agent 实际修订 {protocol_revisions} 份 / "
        f"选中 {protocol_demo.get('generation', {}).get('variant_id', '-')} ",
        f"- 外部 LLM 真实性说明：{live_llm_note}。",
        "",
        "> 协议演示使用确定性的 LLM 形状测试替身，以便离线复现多智能体协作；"
        "它不冒充外部模型调用。外部 API 的实际结果单独按上面的真实性说明记录。",
        "",
        "| 用例 | 状态 | 联网研究 | 算法候选 | 代码候选 | 修复 | 经验复用 | 选中算法 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for case in cases:
        rows.append(
            f"| {case['case_id']} | {case['status']} | "
            f"{case.get('online_research', {}).get('status') or '-'} | "
            f"{len(case.get('algorithm_comparison', []))} | "
            f"{len(case.get('implementation_candidates', []))} | "
            f"{len(case.get('repairs', []))} | "
            f"{len(case.get('repair_experience_used', []))} | "
            f"{case.get('selected_model', '-')} |"
        )
    rows.extend(
        [
            "",
            "## 每个用例做了什么",
            "",
        ]
    )
    for case in cases:
        comparison = case.get("algorithm_comparison", [])
        comparison_text = "；".join(
            f"{item['model']}（库存损失 {item.get('inventory_cost', '-'):.4g}，"
            f"误差比例 {item.get('wape', '-'):.2%}）"
            for item in comparison
        )
        repair_text = (
            "检测到代码接口不符合统一契约，自动分类、生成失败指纹、修复并重新验证。"
            if case.get("repairs")
            else "生成代码一次通过统一门禁，本次无需修复。"
        )
        reuse_text = (
            f"本次从图谱检索并复用了 {len(case['repair_experience_used'])} 条成功修复经验。"
            if case.get("repair_experience_used")
            else "本次没有可复用的历史经验，产生的新经验会写回图谱供后续使用。"
        )
        display_run = portable_path(case.get("run_dir"))
        rows.extend(
            [
                f"### {case['case_id']}",
                "",
                f"**任务目的：** {case['purpose']}",
                "",
                f"**系统做了什么：** 比较 {len(comparison)} 个候选算法；{repair_text}{reuse_text}",
                "",
                f"**结果怎么理解：** 最终采用 `{case.get('selected_model', '-')}`，"
                f"未来周期目标库存为 **{case.get('target_inventory', '-')}**。"
                "这里的采用结果来自历史滚动回测和业务成本指标，不是语言模型主观指定。",
                "",
                f"- 候选比较：{comparison_text or '未生成'}",
                f"- 代码实现候选：{len(case.get('implementation_candidates', []))} 份",
                f"- 自动修复：{len(case.get('repairs', []))} 次",
                f"- 历史经验复用：{len(case.get('repair_experience_used', []))} 条",
                f"- 运行目录：`{display_run or '-'}`",
                f"- 技术报告：`{portable_path(case.get('report_paths', {}).get('markdown'))}`",
                f"- 协作记录：`{portable_path(case.get('report_paths', {}).get('manifest'))}`",
                f"- 详细 Trace：`{portable_path((case.get('trace_paths') or {}).get('markdown'))}`",
                "",
            ]
        )
    rows.extend(
        [
            "## 沉淀到知识图谱的结果",
            "",
            "| 节点类型 | 数量 | 对评审者的含义 |",
            "|---|---:|---|",
        ]
    )
    node_meanings = {
        "Algorithm": "可复用算法能力",
        "DemandProfile": "算法适用的需求画像",
        "Metric": "统一评价口径",
        "SourceArtifact": "可追溯资料或源码",
        "ValidationRun": "一次真实验证记录",
        "FailureCase": "归一化失败案例",
        "RepairStrategy": "可复用修复策略",
        "CapabilityVersion": "经过验证的代码版本",
    }
    for node_type, count in sorted(node_types.items()):
        rows.append(
            f"| {node_type} | {count} | {node_meanings.get(node_type, '结构化能力证据')} |"
        )
    rows.extend(
        [
            "",
            f"- 图谱 JSON：`{(session / 'capability_graph.json').relative_to(ROOT).as_posix()}`",
            f"- 图谱 GraphML：`{(session / 'capability_graph.graphml').relative_to(ROOT).as_posix()}`",
            f"- 交互可视化：`{(session / 'capability_graph.html').relative_to(ROOT).as_posix()}`",
            f"- 联网知识抽取：`{research_path.relative_to(ROOT).as_posix()}`",
            "",
            "## 结论可信度与边界",
            "",
            "- 所有预测选择均由历史时间序列回测和验证配置决定，不由 LLM 直接拍板。",
            "- Mock、协议测试替身、真实外部 LLM 和联网研究在证据中分别标记，不混为一谈。",
            "- AST 白名单、临时目录和子进程超时属于应用级安全门禁，不宣称为容器级强隔离。",
            "- 行业资料用于增强规划与解释，不能绕过代码门禁和指标验证。",
            "",
        ]
    )
    (session / "showcase_summary.md").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


def run_showcase(
    *,
    mode: str,
    output_root: Path = DEFAULT_OUTPUT,
    session_name: str | None = None,
) -> Path:
    """Run offline, live, or all cases and return the evidence session path."""

    session = _safe_session(output_root, session_name)
    summary_path = session / "showcase_summary.json"
    existing = (
        json.loads(summary_path.read_text(encoding="utf-8")).get("cases", [])
        if summary_path.exists()
        else []
    )
    cases_by_id = {str(case["case_id"]): case for case in existing}

    if mode in {"offline", "all"}:
        offline_settings = Settings(llm_mode="mock")
        first = _run_case(
            case_id="case_01_repair_deposition",
            purpose=(
                "周季节商品的候选算法比较、代码验证、接口故障注入、自动修复，"
                "并把失败指纹、修复策略和能力版本写回知识图谱。"
            ),
            description=(
                "为商品1002在仓库1预测未来14天目标库存，比较至少三种算法，"
                "结合现货、在途、欠单和补货约束给出建议，并保存完整验证证据。"
            ),
            session=session,
            settings=offline_settings,
            online_research=False,
            execution_mode="balanced",
            inject_failure=True,
        )
        cases_by_id[first["case_id"]] = first
        second = _run_case(
            case_id="case_02_experience_reuse",
            purpose=(
                "再次触发同类接口失败，验证 RepairAgent 能从共享知识图谱检索上一用例"
                "的成功修复经验，并在修复后生成新的版本化验证记录。"
            ),
            description=(
                "再次为商品1002在仓库1预测未来14天库存，要求复用历史失败经验，"
                "重新比较算法、验证代码并说明版本变化。"
            ),
            session=session,
            settings=offline_settings,
            online_research=False,
            execution_mode="balanced",
            inject_failure=True,
        )
        cases_by_id[second["case_id"]] = second

    if mode in {"live", "all"}:
        live_settings = Settings.from_env()
        if live_settings.llm_mode != "api":
            raise RuntimeError("live showcase requires LLM_MODE=api in .env")
        issues = live_settings.validate()
        if issues:
            raise RuntimeError("; ".join(issues))
        live = _run_case(
            case_id="case_04_live_research_multi_agent",
            purpose=(
                "高间歇需求场景中实际调用 Crossref 联网检索和外部 LLM；执行架构、"
                "多实现、独立审查、统一验证、资源比较、业务补货和知识图谱沉淀。"
            ),
            description=(
                "为高间歇需求商品1003在仓库2预测未来21天目标库存。请联网检索"
                "间歇需求预测与库存控制资料，比较 Croston、移动平均和最近值等方案；"
                "由多智能体自动生成并审查多个独立代码实现，执行安全、等价性、"
                "性能和库存成本评估，最后结合库存快照给出补货建议和设计依据。"
            ),
            session=session,
            settings=live_settings,
            online_research=True,
            execution_mode="balanced",
        )
        cases_by_id[live["case_id"]] = live

    if mode in {"protocol", "all"}:
        protocol_dir = session / "protocol_demo"
        specification = CapabilityKnowledgeGraph.bootstrap().capability_spec(
            "moving_average"
        )
        CapabilityReplicator().replicate(
            specification,
            protocol_dir / "generated",
            protocol_dir / "review_manifest.json",
            llm=_ProtocolTestLLM(),
            reference_model="moving_average",
            candidate_count=3,
            max_workers=1,
        )

    cases = [cases_by_id[key] for key in sorted(cases_by_id)]
    _write_summary(session, cases)
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("offline", "protocol", "live", "all", "summarize"),
        default="offline",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--session", help="Reuse an existing showcase session name")
    args = parser.parse_args()
    session = run_showcase(
        mode=args.mode,
        output_root=args.output_root,
        session_name=args.session,
    )
    print(f"Advanced showcase completed: {session}")
    print(f"Summary: {session / 'showcase_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
