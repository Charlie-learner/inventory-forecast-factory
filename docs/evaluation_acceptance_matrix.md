# 笔试要求评分验收中心

> 本文由 `inventory_agent audit` 根据仓库当前证据生成；Web 端“评分验收”页面使用同一数据源。

## 一句话结论

基础与进阶必需项均有可执行证据，可进入提交前演示。

必需项 **19/19** 已完成，部分完成 **0**，未完成 **0**，完成率 **100.0%**。

## 核心闭环

**需求理解** → **能力抽取** → **方案规划** → **代码复刻** → **统一验证** → **失败修复** → **知识沉淀**

| 阶段 | 协作角色 | 可检查结果 |
|---|---|---|
| 需求理解 | RequirementAgent | 自然语言转结构化任务 |
| 能力抽取 | ExtractionAgent | 来源、函数、依赖与能力规格 |
| 方案规划 | PlannerAgent | 画像匹配与候选算法计划 |
| 代码复刻 | 架构/实现/审查 Agents | 多个独立代码候选 |
| 统一验证 | Validator + Benchmark | 门禁、回测、指标与资源分析 |
| 失败修复 | RepairAgent | 失败分类、多轮修复和再验证 |
| 知识沉淀 | ExperienceAgent + Graph | 验证、失败、策略和版本回写 |

## 核心任务

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 已完成 | LLM 用于能力理解、知识抽取、代码生成或修复 | 系统提供统一 LLM 客户端、可调用外部兼容接口，也保留可复现的规则降级；代码生成和修复由专门 Agent 调用。<br>边界：外部 API 是否验收取决于运行环境；doctor 会发起最小真实请求并安全报告结果，Mock 模式不冒充外部调用。 | `inventory_agent/llm/client.py`<br>`inventory_agent/agents/code_collaboration.py`<br>`inventory_agent/agents/repair.py` |
| 已完成 | 选择并落地一个真实行业场景 | 项目聚焦库存预测与补货决策，包含商品、仓库、需求、缺货成本和积压成本等业务语义。 | `docs/business/inventory_forecasting_scenario.md`<br>`inventory_agent/services/replenishment.py`<br>`examples/business_data/README.md` |
| 已完成 | 构建小规模行业算法能力知识库或知识图谱 | 图谱连接算法、需求画像、指标、来源、验证运行、失败案例、修复策略和能力版本，并可回写运行证据。 | `docs/knowledge_graph_schema.md`<br>`inventory_agent/knowledge/graph.py`<br>`knowledge/base_capability_graph.json`<br>`knowledge/base_capability_graph.graphml` |
| 已完成 | 自然语言能力描述到可运行算法代码的自动或半自动复刻 | 能力规格先结构化，再由多个实现 Agent 生成候选代码，经审查 Agent 修改后逐份执行验证并选优。 | `inventory_agent/codegen/replication.py`<br>`inventory_agent/agents/code_collaboration.py`<br>`examples/advanced_showcase/20260717_120418/protocol_demo/review_manifest.json` |
| 已完成 | 统一验证正确性、指标表现、运行稳定性和接口一致性 | 同一验证门禁检查语法、依赖、接口、运行、稳定性和结果等价性，并用滚动回测比较业务指标。 | `inventory_agent/codegen/validator.py`<br>`inventory_agent/validation/profiles.py`<br>`inventory_agent/services/benchmark.py` |
| 已完成 | 形成能力抽取—复刻—验证—修复—沉淀闭环 | 完整工作流从用户需求出发，检索能力、生成与比较代码、自动修复，最后把验证、失败、修复和版本写回图谱。 | `inventory_agent/workflow/factory.py`<br>`inventory_agent/observability/trace.py`<br>`examples/advanced_showcase/20260717_120418/showcase_summary.md` |
| 已完成 | 提供简单 UI、CLI 或 API 接口 | 普通用户可用自然语言和数据文件启动 Web 工作流；开发者可使用 CLI 或自动生成的 OpenAPI 接口。 | `inventory_agent/web/static/index.html`<br>`inventory_agent/cli.py`<br>`inventory_agent/web/api_docs.py` |

## 开发要求

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 已完成 | 代码模块化、可读、可复现并采用版本控制 | 项目按 agents、codegen、validation、knowledge、web 和 services 分层；依赖、环境模板、测试与运行命令齐全。 | `.git`<br>`pyproject.toml`<br>`.env.example`<br>`docs/project_structure.md`<br>`scripts/clean_workspace.py`<br>`tests` |
| 已完成 | 外部 LLM 不可用时提供 Mock、规则或 API 替代方案 | Mock 模式用于离线复现；API 模式用于真实生成；联网研究失败时只降级研究步骤，不中断核心预测闭环。 | `inventory_agent/llm/client.py`<br>`inventory_agent/agents/research.py`<br>`docs/custom_llm.md` |

## 基础交付

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 已完成 | 提供行业数据、文档、业务材料和来源说明 | 仓库包含可直接运行的演示数据、菜鸟字段适配说明、业务场景、补货策略和来源元数据。 | `examples/data/cainiao_demo.csv`<br>`examples/business_data/README.md`<br>`examples/business_data/source_metadata.json`<br>`docs/data_schema.md` |
| 已完成 | 提供知识抽取结果文件 | 抽取结果以 JSON 保存来源、函数、依赖、调用关系和能力说明，并可同步写入 JSON、GraphML 和 HTML 图谱。 | `knowledge/extracted_external_capabilities.json`<br>`examples/advanced_showcase/20260717_120418/online_knowledge_extraction.json`<br>`examples/knowledge_graph/complete_capability_graph.graphml` |
| 已完成 | 提供完整自然语言到代码、验证与报告示例 | 高级展示保存两次端到端运行、代码候选、修复过程、研究抽取、回写图谱和面向评审者的汇总。 | `examples/advanced_showcase/20260717_120418/showcase_summary.md`<br>`examples/repair_run/20260717_102359_522951/validation_report.md`<br>`examples/repair_run/20260717_102359_522951/detailed_trace.md` |
| 已完成 | 提供 README、依赖、使用说明、测试和验证报告 | README 给出快速启动；测试覆盖核心模块；业务报告、技术报告、JSON、Trace 和产物清单可以分别查看。 | `README.md`<br>`pyproject.toml`<br>`docs/usage_examples_and_test_cases.md`<br>`scripts/validate_project.py`<br>`tests` |

## 进阶要求

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 已完成 | 同时提供 Web、CLI 和 API | 三种入口复用同一业务服务：Web 面向普通用户，CLI 面向复现和验收，API 面向程序集成。 | `inventory_agent/web/app.py`<br>`inventory_agent/web/server.py`<br>`inventory_agent/cli.py`<br>`inventory_agent/web/api_docs.py` |
| 已完成 | 支持多轮代码修复 | 失败会被分类、生成指纹并选择修复策略；修复后的代码再次经过同一组门禁，直到通过或达到次数上限。 | `inventory_agent/agents/repair.py`<br>`inventory_agent/validation/failures.py`<br>`examples/repair_run/20260717_102359_522951/generated_versions` |
| 已完成 | 支持多个候选算法方案自动比较 | 系统按时间顺序滚动回测多个候选算法，以验证配置规定的主指标选优，同时保留全部比较明细。 | `inventory_agent/services/benchmark.py`<br>`inventory_agent/forecasting/registry.py`<br>`docs/inventory_evaluation.md` |
| 已完成 | 支持知识图谱可视化和自动验证报告 | 图谱可以搜索、筛选和查看节点详情；每次运行自动生成业务报告、技术报告、JSON 和详细 Trace。 | `inventory_agent/knowledge/graph.py`<br>`knowledge/base_capability_graph.html`<br>`inventory_agent/agents/report.py` |
| 已完成 | 验证结果可回写知识库或知识图谱 | 成功验证、失败指纹、修复策略和能力版本均成为图谱节点或关系，后续任务可以检索并复用。 | `inventory_agent/knowledge/graph.py`<br>`inventory_agent/agents/experience.py`<br>`examples/advanced_showcase/20260717_120418/capability_graph.json` |
| 已完成 | 支持不同验证配置和插件式算法模板或评价指标 | 验证配置将业务目标、主指标、折数和门槛解耦；可信本地插件可以注册新指标和新验证策略。 | `inventory_agent/validation/profiles.py`<br>`inventory_agent/plugins.py`<br>`examples/plugins/stockout_priority.py` |

## 加分能力

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 已完成 | 多智能体协作，而非单次 Prompt 直接生成代码 | 架构 Agent 先定义约束，多个实现 Agent 并行产出不同方案，审查 Agent 给出结构化修改意见，验证与修复 Agent 再闭环执行。<br>边界：协议演示使用确定性 LLM 形状测试替身，用于离线复现协作协议；真实 API 模式使用外部 LLM。 | `inventory_agent/agents/code_collaboration.py`<br>`examples/advanced_showcase/20260717_120418/protocol_demo/review_manifest.json`<br>`docs/multi_agent_code_collaboration.md` |
| 已完成 | 从真实代码仓库抽取函数、依赖和能力描述 | 抽取器递归分析 Python 仓库，记录函数签名、导入依赖、内部调用、复杂度、源码哈希和来源位置。 | `inventory_agent/extraction/extractor.py`<br>`inventory_agent/agents/extraction.py`<br>`docs/capability_extraction.md` |
| 已完成 | 自动分析失败案例并形成可复用经验 | 系统将失败归类并生成稳定指纹，保存根因、修复动作和结果；下一次遇到同类问题时优先检索历史修复经验。 | `inventory_agent/validation/failures.py`<br>`inventory_agent/agents/experience.py`<br>`examples/advanced_showcase/20260717_120418/showcase_summary.json` |
| 已完成 | 算法能力版本管理 | 已验证代码按哈希形成版本，可比较指标和验证证据，并支持发布和回滚生命周期事件。 | `inventory_agent/services/versioning.py`<br>`docs/capability_lifecycle_features.md`<br>`tests/test_versioning.py` |
| 已完成 | 用自然语言解释生成方案的设计依据 | 业务报告先给一句话结论，再说明预测需求、目标库存、补货建议、采用方法、可信度和风险；技术术语收纳到可展开的技术报告。 | `inventory_agent/agents/report.py`<br>`inventory_agent/services/replenishment.py`<br>`examples/repair_run/20260717_102359_522951/business_report.md` |
| 已完成 | 支持可追溯联网研究、性能优化和资源分析 | 联网研究仅接收带 DOI 的可追溯资料并形成抽取文件；生成算法同时记录耗时、吞吐、内存和复杂度提示。<br>边界：联网结果依赖 Crossref 和当前网络；失败时会明确标为 degraded，不伪造文献。 | `inventory_agent/agents/research.py`<br>`inventory_agent/services/performance.py`<br>`examples/advanced_showcase/20260717_120418/online_knowledge_extraction.json`<br>`docs/performance_and_runtime.md` |
| 已完成 | 提供 API 文档和部署运行说明 | API 路由目录同时生成 OpenAPI JSON 和浏览器文档，Web 服务可由一条 CLI 命令启动。 | `inventory_agent/web/api_docs.py`<br>`docs/web_interface.md`<br>`README.md` |

## 本次边界

| 状态 | 要求 | 评审者能看到什么 | 主要证据 |
|---|---|---|---|
| 不纳入本次目标 | Beam Search、MCTS 或通用图搜索 | 当前候选方案采用受约束的多实现生成、滚动回测和指标排序，没有把通用搜索算法包装成已完成功能。<br>边界：按本次任务约定不纳入实现范围。 | — |
| 不纳入本次目标 | 跨行业能力迁移 | 项目专注库存预测行业，不声称已经验证跨行业迁移。<br>边界：按本次任务约定不纳入实现范围。 | — |
| 不纳入本次目标 | 容器级代码沙箱 | 当前提供 AST 安全门禁、导入白名单、临时目录、子进程超时和资源分析，但不等同于 OS 或容器级强隔离。<br>边界：按本次任务约定不实现容器沙箱，并在界面中如实说明现有安全边界。 | `inventory_agent/codegen/validator.py`<br>`inventory_agent/codegen/runner.py` |

## 建议演示顺序

1. 在 Web“评分验收”页先看总览和七阶段闭环。
2. 在“完整能力工厂”提交自然语言与数据，查看业务报告。
3. 在“运行证据”查看候选代码、修复、技术报告和 Trace。
4. 在“知识图谱”查看验证、失败、修复策略和版本回写。
5. 用 CLI 运行下列命令复核关键结论。

- `uv run python -m inventory_agent audit`
- `uv run python -m inventory_agent audit --format markdown --output docs/evaluation_acceptance_matrix.md`
- `uv run python -m inventory_agent web --open-browser`
- `uv run python scripts/validate_project.py`
- `uv run python scripts/run_advanced_showcase.py --mode offline`

## 评分边界说明

状态为“不纳入本次目标”的能力不会被包装成已完成。外部 LLM 和联网研究的真实性以运行时验收结果为准；离线协议测试会明确标注为测试替身。
