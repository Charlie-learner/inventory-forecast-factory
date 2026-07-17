"""Build one evidence-backed audit shared by the CLI, Web UI, and docs.

The catalog mirrors the written-test requirements.  Statuses are computed from
repository evidence so the Web page and CLI cannot drift into two conflicting
claims about project completeness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AuditItem:
    """One assessable requirement and the evidence a reviewer can inspect."""

    item_id: str
    category: str
    requirement: str
    plain_language: str
    status: str
    required: bool
    evidence: tuple[str, ...]
    cli_command: str
    web_view: str
    boundary: str = ""


CATEGORY_ORDER = (
    "核心任务",
    "开发要求",
    "基础交付",
    "进阶要求",
    "拓展尝试",
    "实现边界",
)

STATUS_LABELS = {
    "passed": "已完成",
    "partial": "部分完成",
    "missing": "未完成",
    "excluded": "不纳入本次目标",
}


def _all_exist(root: Path, paths: Iterable[str]) -> bool:
    return all((root / path).exists() for path in paths)


def _status(root: Path, evidence: tuple[str, ...], *, partial: bool = False) -> str:
    if _all_exist(root, evidence):
        return "partial" if partial else "passed"
    return "missing"


def _latest_showcase(root: Path) -> Path | None:
    showcase_root = root / "examples" / "advanced_showcase"
    sessions = sorted(
        (
            path
            for path in showcase_root.glob("20*")
            if path.is_dir() and (path / "showcase_summary.md").is_file()
        ),
        reverse=True,
    )
    return sessions[0] if sessions else None


def _latest_research_showcase(root: Path) -> Path | None:
    """Find the newest showcase that contains actual research evidence.

    Offline refreshes intentionally do not fabricate a research result.  Research
    evidence therefore has its own freshness selector instead of being coupled to
    whichever offline showcase happened to run most recently.
    """

    showcase_root = root / "examples" / "advanced_showcase"
    sessions = sorted(
        (
            path
            for path in showcase_root.glob("20*")
            if path.is_dir()
            and (path / "online_knowledge_extraction.json").is_file()
        ),
        reverse=True,
    )
    return sessions[0] if sessions else None


def _latest_repair_run(root: Path) -> Path | None:
    """Find the newest committed repair example without fixing a timestamp in code."""

    repair_root = root / "examples" / "repair_run"
    sessions = sorted(
        (
            path
            for path in repair_root.glob("20*")
            if path.is_dir()
            and (path / "validation_report.md").is_file()
            and (path / "detailed_trace.md").is_file()
        ),
        reverse=True,
    )
    return sessions[0] if sessions else None


def _item(
    root: Path,
    item_id: str,
    category: str,
    requirement: str,
    plain_language: str,
    evidence: tuple[str, ...],
    cli_command: str,
    web_view: str,
    *,
    required: bool = True,
    partial: bool = False,
    boundary: str = "",
) -> AuditItem:
    return AuditItem(
        item_id=item_id,
        category=category,
        requirement=requirement,
        plain_language=plain_language,
        status=_status(root, evidence, partial=partial),
        required=required,
        evidence=evidence,
        cli_command=cli_command,
        web_view=web_view,
        boundary=boundary,
    )


def build_submission_audit(workspace: str | Path = ".") -> dict[str, Any]:
    """Return the current written-test compliance result with inspectable evidence."""

    root = Path(workspace).resolve()
    latest = _latest_showcase(root)
    latest_research = _latest_research_showcase(root)
    latest_repair = _latest_repair_run(root)
    showcase = (
        latest.relative_to(root).as_posix()
        if latest is not None
        else "examples/advanced_showcase/<latest>"
    )
    summary_path = f"{showcase}/showcase_summary.md"
    collaboration_path = (
        f"{showcase}/protocol_demo/review_manifest.json"
    )
    research_showcase = (
        latest_research.relative_to(root).as_posix()
        if latest_research is not None
        else "examples/advanced_showcase/<latest-research>"
    )
    research_path = f"{research_showcase}/online_knowledge_extraction.json"
    repair_run = (
        latest_repair.relative_to(root).as_posix()
        if latest_repair is not None
        else "examples/repair_run/<latest>"
    )

    items = [
        _item(
            root,
            "core_llm",
            "核心任务",
            "LLM 用于能力理解、知识抽取、代码生成或修复",
            "系统提供统一 LLM 客户端、可调用外部兼容接口，也保留可复现的规则降级；代码生成和修复由专门 Agent 调用。",
            (
                "inventory_agent/llm/client.py",
                "inventory_agent/agents/code_collaboration.py",
                "inventory_agent/agents/repair.py",
            ),
            "uv run python -m inventory_agent doctor --live-llm",
            "系统总览 / 完整能力工厂",
            boundary="外部 API 是否可用取决于运行环境；doctor 会发起最小真实请求并安全报告结果，Mock 模式不会冒充外部调用。",
        ),
        _item(
            root,
            "core_scenario",
            "核心任务",
            "选择并落地一个真实行业场景",
            "项目聚焦库存预测与补货决策，包含商品、仓库、需求、缺货成本和积压成本等业务语义。",
            (
                "docs/business/inventory_forecasting_scenario.md",
                "inventory_agent/services/replenishment.py",
                "examples/business_data/README.md",
            ),
            "uv run python -m inventory_agent run --help",
            "完整能力工厂",
        ),
        _item(
            root,
            "core_graph",
            "核心任务",
            "构建小规模行业算法能力知识库或知识图谱",
            "图谱连接算法、需求画像、指标、来源、验证运行、失败案例、修复策略和能力版本，并可回写运行证据。",
            (
                "docs/knowledge_graph_schema.md",
                "inventory_agent/knowledge/graph.py",
                "knowledge/base_capability_graph.json",
                "knowledge/base_capability_graph.graphml",
            ),
            "uv run python -m inventory_agent visualize-graph",
            "知识图谱",
        ),
        _item(
            root,
            "core_replication",
            "核心任务",
            "自然语言能力描述到可运行算法代码的自动或半自动复刻",
            "能力规格先结构化，再由多个实现 Agent 生成候选代码，经审查 Agent 修改后逐份执行验证并选优。",
            (
                "inventory_agent/codegen/replication.py",
                "inventory_agent/agents/code_collaboration.py",
                collaboration_path,
            ),
            "uv run python -m inventory_agent replicate-capability --help",
            "能力抽取与复刻",
        ),
        _item(
            root,
            "core_validation",
            "核心任务",
            "统一验证正确性、指标表现、运行稳定性和接口一致性",
            "同一验证门禁检查语法、依赖、接口、运行、稳定性和结果等价性，并用滚动回测比较业务指标。",
            (
                "inventory_agent/codegen/validator.py",
                "inventory_agent/validation/profiles.py",
                "inventory_agent/services/benchmark.py",
            ),
            "uv run pytest -q",
            "算法回测比较 / 运行证据",
        ),
        _item(
            root,
            "core_closed_loop",
            "核心任务",
            "形成能力抽取—复刻—验证—修复—沉淀闭环",
            "完整工作流从用户需求出发，检索能力、生成与比较代码、自动修复，最后把验证、失败、修复和版本写回图谱。",
            (
                "inventory_agent/workflow/factory.py",
                "inventory_agent/observability/trace.py",
                summary_path,
            ),
            "uv run python scripts/run_advanced_showcase.py --mode offline",
            "完整能力工厂 / 运行证据 / 知识图谱",
        ),
        _item(
            root,
            "core_interfaces",
            "核心任务",
            "提供简单 UI、CLI 或 API 接口",
            "普通用户可用自然语言和数据文件启动 Web 工作流；开发者可使用 CLI 或自动生成的 OpenAPI 接口。",
            (
                "inventory_agent/web/static/index.html",
                "inventory_agent/cli.py",
                "inventory_agent/web/api_docs.py",
            ),
            "uv run python -m inventory_agent web --open-browser",
            "全部页面 / API 文档",
        ),
        _item(
            root,
            "dev_reproducible",
            "开发要求",
            "代码模块化、可读、可复现并采用版本控制",
            "项目按 agents、codegen、validation、knowledge、web 和 services 分层；依赖、环境模板、测试与运行命令齐全。",
            (
                ".git",
                "pyproject.toml",
                ".env.example",
                "docs/project_structure.md",
                "scripts/clean_workspace.py",
                "tests",
            ),
            "uv sync && uv run pytest -q",
            "系统总览 / 项目自检",
        ),
        _item(
            root,
            "dev_fallback",
            "开发要求",
            "外部 LLM 不可用时提供 Mock、规则或 API 替代方案",
            "Mock 模式用于离线复现；API 模式用于真实生成；联网研究失败时只降级研究步骤，不中断核心预测闭环。",
            (
                "inventory_agent/llm/client.py",
                "inventory_agent/agents/research.py",
                "docs/custom_llm.md",
            ),
            "uv run python -m inventory_agent doctor",
            "系统总览 / 插件与配置",
        ),
        _item(
            root,
            "delivery_materials",
            "基础交付",
            "提供行业数据、文档、业务材料和来源说明",
            "仓库包含可直接运行的演示数据、菜鸟字段适配说明、业务场景、补货策略和来源元数据。",
            (
                "examples/data/cainiao_demo.csv",
                "examples/business_data/README.md",
                "examples/business_data/source_metadata.json",
                "docs/data_schema.md",
            ),
            "uv run python -m inventory_agent benchmark --help",
            "完整能力工厂",
        ),
        _item(
            root,
            "delivery_extraction",
            "基础交付",
            "提供知识抽取结果文件",
            "抽取结果以 JSON 保存来源、函数、依赖、调用关系和能力说明，并可同步写入 JSON、GraphML 和 HTML 图谱。",
            (
                "knowledge/extracted_external_capabilities.json",
                "examples/knowledge_graph/complete_capability_graph.graphml",
            ),
            "uv run python -m inventory_agent extract-capability --source inventory_agent/forecasting",
            "能力抽取与复刻 / 知识图谱",
        ),
        _item(
            root,
            "delivery_example",
            "基础交付",
            "提供完整自然语言到代码、验证与报告示例",
            "高级展示保存两次端到端运行、代码候选、修复过程、研究抽取、图谱回写和结果汇总。",
            (
                summary_path,
                f"{repair_run}/validation_report.md",
                f"{repair_run}/detailed_trace.md",
            ),
            "uv run python scripts/run_advanced_showcase.py --mode summarize",
            "运行证据 / 项目自检",
        ),
        _item(
            root,
            "delivery_docs_tests",
            "基础交付",
            "提供 README、依赖、使用说明、测试和验证报告",
            "README 给出快速启动；测试覆盖核心模块；业务报告、技术报告、JSON、Trace 和产物清单可以分别查看。",
            (
                "README.md",
                "pyproject.toml",
                "docs/usage_examples_and_test_cases.md",
                "scripts/validate_project.py",
                "tests",
            ),
            "uv run python scripts/validate_project.py",
            "运行证据 / 项目自检",
        ),
        _item(
            root,
            "advanced_interfaces",
            "进阶要求",
            "同时提供 Web、CLI 和 API",
            "三种入口复用同一业务服务：Web 面向普通用户，CLI 方便复现和调试，API 用于程序集成。",
            (
                "inventory_agent/web/app.py",
                "inventory_agent/web/server.py",
                "inventory_agent/cli.py",
                "inventory_agent/web/api_docs.py",
            ),
            "uv run python -m inventory_agent web",
            "全部页面 / API 文档",
        ),
        _item(
            root,
            "advanced_repair",
            "进阶要求",
            "支持多轮代码修复",
            "失败会被分类、生成指纹并选择修复策略；修复后的代码再次经过同一组门禁，直到通过或达到次数上限。",
            (
                "inventory_agent/agents/repair.py",
                "inventory_agent/validation/failures.py",
                f"{repair_run}/generated_versions",
            ),
            "uv run python scripts/run_acceptance_cases.py",
            "运行证据",
        ),
        _item(
            root,
            "advanced_compare",
            "进阶要求",
            "支持多个候选算法方案自动比较",
            "系统按时间顺序滚动回测多个候选算法，以验证配置规定的主指标选优，同时保留全部比较明细。",
            (
                "inventory_agent/services/benchmark.py",
                "inventory_agent/forecasting/registry.py",
                "docs/inventory_evaluation.md",
            ),
            "uv run python -m inventory_agent benchmark --data examples/data/cainiao_demo.csv --item 3424 --store 1",
            "算法回测比较",
        ),
        _item(
            root,
            "advanced_graph_report",
            "进阶要求",
            "支持知识图谱可视化和自动验证报告",
            "图谱可以搜索、筛选和查看节点详情；每次运行自动生成业务报告、技术报告、JSON 和详细 Trace。",
            (
                "inventory_agent/knowledge/graph.py",
                "knowledge/base_capability_graph.html",
                "inventory_agent/agents/report.py",
            ),
            "uv run python -m inventory_agent visualize-graph",
            "知识图谱 / 运行证据",
        ),
        _item(
            root,
            "advanced_writeback",
            "进阶要求",
            "验证结果可回写知识库或知识图谱",
            "成功验证、失败指纹、修复策略和能力版本均成为图谱节点或关系，后续任务可以检索并复用。",
            (
                "inventory_agent/knowledge/graph.py",
                "inventory_agent/agents/experience.py",
                f"{showcase}/capability_graph.json",
            ),
            "uv run python scripts/run_advanced_showcase.py --mode offline",
            "知识图谱 / 运行证据",
        ),
        _item(
            root,
            "advanced_profiles_plugins",
            "进阶要求",
            "支持不同验证配置和插件式算法模板或评价指标",
            "验证配置将业务目标、主指标、折数和门槛解耦；可信本地插件可以注册新指标和新验证策略。",
            (
                "inventory_agent/validation/profiles.py",
                "inventory_agent/plugins.py",
                "examples/plugins/stockout_priority.py",
            ),
            "uv run python -m inventory_agent plugins --help",
            "插件与配置",
        ),
        _item(
            root,
            "bonus_multi_agent",
            "拓展尝试",
            "多智能体协作，而非单次 Prompt 直接生成代码",
            "架构 Agent 先定义约束，多个实现 Agent 并行产出不同方案，审查 Agent 给出结构化修改意见，验证与修复 Agent 再闭环执行。",
            (
                "inventory_agent/agents/code_collaboration.py",
                collaboration_path,
                "docs/multi_agent_code_collaboration.md",
            ),
            "uv run python scripts/run_advanced_showcase.py --mode protocol",
            "能力抽取与复刻 / 运行证据",
            required=False,
            boundary="协议演示使用确定性 LLM 形状测试替身，用于离线复现协作协议；真实 API 模式使用外部 LLM。",
        ),
        _item(
            root,
            "bonus_repo_extract",
            "拓展尝试",
            "从真实代码仓库抽取函数、依赖和能力描述",
            "抽取器递归分析 Python 仓库，记录函数签名、导入依赖、内部调用、复杂度、源码哈希和来源位置。",
            (
                "inventory_agent/extraction/extractor.py",
                "inventory_agent/agents/extraction.py",
                "docs/capability_extraction.md",
            ),
            "uv run python -m inventory_agent extract-capability --source inventory_agent/forecasting",
            "能力抽取与复刻",
            required=False,
        ),
        _item(
            root,
            "bonus_failure_experience",
            "拓展尝试",
            "自动分析失败案例并形成可复用经验",
            "系统将失败归类并生成稳定指纹，保存根因、修复动作和结果；下一次遇到同类问题时优先检索历史修复经验。",
            (
                "inventory_agent/validation/failures.py",
                "inventory_agent/agents/experience.py",
                f"{showcase}/showcase_summary.json",
            ),
            "uv run python scripts/run_advanced_showcase.py --mode offline",
            "运行证据 / 知识图谱",
            required=False,
        ),
        _item(
            root,
            "bonus_versions",
            "拓展尝试",
            "算法能力版本管理",
            "已验证代码按哈希形成版本，可比较指标和验证证据，并支持发布和回滚生命周期事件。",
            (
                "inventory_agent/services/versioning.py",
                "docs/capability_lifecycle_features.md",
                "tests/test_versioning.py",
            ),
            "uv run python -m inventory_agent versions --help",
            "插件与配置",
            required=False,
        ),
        _item(
            root,
            "bonus_explanation",
            "拓展尝试",
            "用自然语言解释生成方案的设计依据",
            "业务报告先给一句话结论，再说明预测需求、目标库存、补货建议、采用方法、可信度和风险；技术术语收纳到可展开的技术报告。",
            (
                "inventory_agent/agents/report.py",
                "inventory_agent/services/replenishment.py",
                f"{repair_run}/business_report.md",
            ),
            "uv run python -m inventory_agent run --help",
            "完整能力工厂 / 运行证据",
            required=False,
        ),
        _item(
            root,
            "bonus_research_performance",
            "拓展尝试",
            "支持可追溯联网研究、性能优化和资源分析",
            "联网研究仅接收带 DOI 的可追溯资料并形成抽取文件；生成算法同时记录耗时、吞吐、内存和复杂度提示。",
            (
                "inventory_agent/agents/research.py",
                "inventory_agent/services/performance.py",
                research_path,
                "docs/performance_and_runtime.md",
            ),
            "uv run python -m inventory_agent research-industry --query \"intermittent demand inventory forecasting\"",
            "完整能力工厂 / 运行证据",
            required=False,
            boundary="联网结果依赖 Crossref 和当前网络；失败时会明确标为 degraded，不伪造文献。",
        ),
        _item(
            root,
            "bonus_api_deploy",
            "拓展尝试",
            "提供 API 文档和部署运行说明",
            "API 路由目录同时生成 OpenAPI JSON 和浏览器文档，Web 服务可由一条 CLI 命令启动。",
            (
                "inventory_agent/web/api_docs.py",
                "docs/web_interface.md",
                "README.md",
            ),
            "uv run python -m inventory_agent web",
            "插件与配置 / API 文档",
            required=False,
        ),
        AuditItem(
            item_id="boundary_search",
            category="实现边界",
            requirement="Beam Search、MCTS 或通用图搜索",
            plain_language="当前候选方案采用受约束的多实现生成、滚动回测和指标排序，没有把通用搜索算法包装成已完成功能。",
            status="excluded",
            required=False,
            evidence=(),
            cli_command="",
            web_view="项目自检",
            boundary="当前版本没有实现该功能。",
        ),
        AuditItem(
            item_id="boundary_transfer",
            category="实现边界",
            requirement="跨行业能力迁移",
            plain_language="项目专注库存预测行业，不声称已经验证跨行业迁移。",
            status="excluded",
            required=False,
            evidence=(),
            cli_command="",
            web_view="项目自检",
            boundary="当前版本没有实现该功能。",
        ),
        AuditItem(
            item_id="boundary_sandbox",
            category="实现边界",
            requirement="容器级代码沙箱",
            plain_language="当前提供 AST 安全门禁、导入白名单、临时目录、子进程超时和资源分析，但不等同于 OS 或容器级强隔离。",
            status="excluded",
            required=False,
            evidence=(
                "inventory_agent/codegen/validator.py",
                "inventory_agent/codegen/runner.py",
            ),
            cli_command="uv run pytest tests/test_codegen.py -q",
            web_view="运行证据",
            boundary="当前只做到应用层安全检查，没有实现容器级沙箱。",
        ),
    ]

    required_items = [item for item in items if item.required]
    passed = sum(item.status == "passed" for item in required_items)
    partial = sum(item.status == "partial" for item in required_items)
    missing = sum(item.status == "missing" for item in required_items)
    completion = round(100.0 * passed / max(len(required_items), 1), 1)
    categories = []
    for category in CATEGORY_ORDER:
        members = [asdict(item) for item in items if item.category == category]
        if members:
            categories.append({"name": category, "items": members})

    return {
        "schema_version": "1.0",
        "title": "项目功能自检",
        "summary": {
            "required_total": len(required_items),
            "passed": passed,
            "partial": partial,
            "missing": missing,
            "completion_rate": completion,
            "conclusion": (
                "当前列出的核心功能都有可运行代码或示例。"
                if not partial and not missing
                else "仍有功能缺少代码或示例，请查看部分完成和未完成条目。"
            ),
        },
        "closed_loop": [
            {"stage": "需求理解", "agent": "RequirementAgent", "result": "自然语言转结构化任务"},
            {"stage": "能力抽取", "agent": "ExtractionAgent", "result": "来源、函数、依赖与能力规格"},
            {"stage": "方案规划", "agent": "PlannerAgent", "result": "画像匹配与候选算法计划"},
            {"stage": "代码复刻", "agent": "架构/实现/审查 Agents", "result": "多个独立代码候选"},
            {"stage": "统一验证", "agent": "Validator + Benchmark", "result": "门禁、回测、指标与资源分析"},
            {"stage": "失败修复", "agent": "RepairAgent", "result": "失败分类、多轮修复和再验证"},
            {"stage": "知识沉淀", "agent": "ExperienceAgent + Graph", "result": "验证、失败、策略和版本回写"},
        ],
        "scoring_dimensions": [
            {"name": "技术能力", "weight": 40, "focus": "核心闭环、Agent、代码生成、图谱和自动验证"},
            {"name": "代码质量", "weight": 30, "focus": "模块、接口、错误处理、复现、测试和可维护性"},
            {"name": "创新性", "weight": 15, "focus": "多智能体、图谱增强、自修复和失败经验"},
            {"name": "完整性", "weight": 15, "focus": "功能、文档、示例、报告、体验和端到端结果"},
        ],
        "categories": categories,
        "items": [asdict(item) for item in items],
        "latest_showcase": {
            "path": showcase if latest is not None else "",
            "summary": summary_path if (root / summary_path).exists() else "",
            "available": latest is not None,
        },
        "quick_commands": [
            "uv run python -m inventory_agent audit",
            "uv run python -m inventory_agent audit --format markdown --output docs/evaluation_acceptance_matrix.md",
            "uv run python -m inventory_agent web --open-browser",
            "uv run python scripts/validate_project.py",
            "uv run python scripts/run_advanced_showcase.py --mode offline",
        ],
    }


def audit_as_text(audit: dict[str, Any]) -> str:
    """Render a concise, reviewer-friendly terminal report."""

    summary = audit["summary"]
    lines = [
        audit["title"],
        "=" * len(audit["title"]),
        (
            f"核心检查项：{summary['passed']}/{summary['required_total']} 已完成；"
            f"部分完成 {summary['partial']}；未完成 {summary['missing']}；"
            f"完成率 {summary['completion_rate']:.1f}%"
        ),
        summary["conclusion"],
        "",
        "核心闭环："
        + " → ".join(stage["stage"] for stage in audit["closed_loop"]),
    ]
    for category in audit["categories"]:
        lines.extend(["", f"[{category['name']}]"])
        for item in category["items"]:
            label = STATUS_LABELS[item["status"]]
            lines.append(f"- {label}｜{item['requirement']}")
            lines.append(f"  {item['plain_language']}")
            if item["evidence"]:
                lines.append(f"  证据：{', '.join(item['evidence'])}")
            if item["cli_command"]:
                lines.append(f"  验证：{item['cli_command']}")
            if item["boundary"]:
                lines.append(f"  边界：{item['boundary']}")
    return "\n".join(lines) + "\n"


def audit_as_markdown(audit: dict[str, Any]) -> str:
    """Render the same audit as a repository evidence document."""

    summary = audit["summary"]
    lines = [
        f"# {audit['title']}",
        "",
        "> 本文由 `inventory_agent audit` 根据仓库当前文件生成；Web 端“项目自检”页面使用同一数据源。",
        "",
        "## 一句话结论",
        "",
        summary["conclusion"],
        "",
        (
            f"核心检查项 **{summary['passed']}/{summary['required_total']}** 已完成，"
            f"部分完成 **{summary['partial']}**，未完成 **{summary['missing']}**，"
            f"完成率 **{summary['completion_rate']:.1f}%**。"
        ),
        "",
        "## 核心闭环",
        "",
        " → ".join(f"**{stage['stage']}**" for stage in audit["closed_loop"]),
        "",
        "| 阶段 | 协作角色 | 可检查结果 |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {stage['stage']} | {stage['agent']} | {stage['result']} |"
        for stage in audit["closed_loop"]
    )
    for category in audit["categories"]:
        lines.extend(
            [
                "",
                f"## {category['name']}",
                "",
                "| 状态 | 功能 | 可以检查的结果 | 主要文件 |",
                "|---|---|---|---|",
            ]
        )
        for item in category["items"]:
            evidence = "<br>".join(f"`{path}`" for path in item["evidence"]) or "—"
            boundary = f"<br>边界：{item['boundary']}" if item["boundary"] else ""
            lines.append(
                f"| {STATUS_LABELS[item['status']]} | {item['requirement']} | "
                f"{item['plain_language']}{boundary} | {evidence} |"
            )
    lines.extend(
        [
            "",
            "## 建议查看顺序",
            "",
            "1. 在 Web“项目自检”页先看总览和七阶段闭环。",
            "2. 在“完整能力工厂”输入自然语言并上传数据，查看业务报告。",
            "3. 在“运行证据”查看候选代码、修复、技术报告和 Trace。",
            "4. 在“知识图谱”查看验证、失败、修复策略和版本回写。",
            "5. 用 CLI 运行下列命令复核关键结论。",
            "",
        ]
    )
    lines.extend(f"- `{command}`" for command in audit["quick_commands"])
    lines.extend(
        [
            "",
            "## 结果与边界说明",
            "",
            "没有实现的功能会直接标出来。外部 LLM 和联网研究以实际运行结果为准；离线协议测试会明确标注为测试替身。",
            "",
        ]
    )
    return "\n".join(lines)
