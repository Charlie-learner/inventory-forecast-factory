# 笔试要求核验与追踪

本表以《人工智能（大模型）-笔试.pdf》第 2-5 页为核验基准。状态含义：

> 提交前请优先执行 `uv run python -m inventory_agent audit --strict`，并查看
> [`evaluation_acceptance_matrix.md`](evaluation_acceptance_matrix.md)。该矩阵由 CLI 与 Web
> “评分验收”页面共用的证据检查器生成；本文保留更详细的设计边界说明。

- **完成**：仓库中有实现、可运行入口和自动化测试或示例证据。
- **部分完成**：主链路可用，但与题目描述的完整能力仍有明确边界。
- **未实现**：当前仓库没有可执行实现，不以规划或文档代替功能。

## 基础要求

| 要求 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| 完整项目代码库 | 完成 | `inventory_agent/`、`tests/`、`scripts/` | 无 |
| 示例行业数据或模拟材料 | 完成 | `examples/data/cainiao_demo.csv`；`examples/business_data/` 提供 6 商品、3 仓、2880 条需求历史，以及商品主数据、库存快照、补货策略和需求事件；工作流实际使用库存快照和策略表计算约束补货量 | 完整原始菜鸟数据因体积和再分发边界不提交 Git |
| 能力知识图谱 schema 说明 | 完成 | `docs/knowledge_graph_schema.md` | 无 |
| 知识抽取结果文件 | 完成 | `knowledge/extracted_capabilities.json` 来自真实 `forecasting/models.py`；`knowledge/extracted_external_capabilities.json` 来自五份带权威来源、许可、置信度和证据位置的能力文档；结构由 `capability_spec.schema.json` 说明 | 当前解析器支持 JSON、结构化 Markdown/TXT 和 ForecastModel Python AST，不是任意文件格式 |
| Agent 工作流代码或配置 | 完成 | `inventory_agent/workflow/factory.py` 的 LangGraph 流程 | 无 |
| 至少一个描述到代码的完整示例 | 完成 | `examples/extraction_run/` 展示完整业务闭环；`examples/replication_run/` 展示独立复刻；`examples/detailed_run/` 保存完整事件、候选算法代码及逐一验证结果 | Mock 使用受约束模板；API 模式支持多策略独立源码生成与验证选优 |
| 自动验证脚本 | 完成 | `scripts/validate_project.py` | 无 |
| 验证报告样例 | 完成 | `examples/complete_run/validation_report.{json,md}`；`examples/detailed_run/` 含完整事件流；`examples/repair_run/` 展示首次失败、修复和再验证 | 样例由提交证据生成脚本维护 |
| README | 完成 | `README.md` 覆盖题目要求的十个章节 | 无 |
| 环境依赖文件 | 完成 | `pyproject.toml`、`uv.lock`、`requirements.txt` | 无 |
| 使用示例和测试用例 | 完成 | `docs/usage_examples_and_test_cases.md` 提供 Web/CLI 示例和 24 项验收矩阵；离线自动验收覆盖六类需求画像、多智能体代码协作、任务持久化与核心闭环；外部验收脚本实际验证 LLM 和 Crossref | 单次批量完整工作流限制为 20 个商品—仓库组合；外部验收依赖网络 |

## 任务核心流程

| 流程 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| 理解自然语言能力描述 | 完成 | `RequirementAgent`；中文/英文和全国/分仓测试 | Mock 模式以规则抽取为主 |
| 从文档、代码或图谱检索知识 | 完成 | `CapabilityExtractionAgent` 支持 JSON、结构化文档和 Python AST，摄取图谱后结合历史验证检索 | 尚未递归扫描远程仓库或解析 PDF/Word |
| 联网搜索行业资料并抽取知识 | 完成 | 可选 `IndustryResearchAgent` 从 Crossref 检索 DOI 元数据、排序、LLM/规则分析，生成 `online_knowledge_extraction.json` 并写入图谱 | 只分析元数据和可用摘要，不声称读取全文；不执行远程代码 |
| 规划算法实现方案 | 完成 | `PlanningAgent` 输出候选、依据和验证指标；仅让本地已注册能力进入自动回测 | 不是 Beam Search/MCTS；新抽取能力需注册/审核后执行 |
| 生成可运行代码 | 完成 | `CodeArchitectureAgent` 先输出结构化蓝图，多个 `CodeImplementationAgent` 按策略独立生成源码，`CodeReviewAgent` 逐份独立审查和修订，再由验证器选优；保存角色、候选 ID、策略、提示/规格/源码哈希和审查证据 | 未注册新算法缺少参考语义时仍需人工审核；只有已支持模板提供确定性回退 |
| 自动测试和指标评估 | 完成 | 滚动回测、A/B 成本、精度指标、安全/接口/稳定性检查及与参考能力的数值等价性 | 子进程不是容器级沙箱 |
| 根据错误修复或优化 | 完成 | LangGraph 最多两轮；API 模式首轮按源码和错误进行 LLM 修复，失败后回退安全模板；Mock 模式直接安全回退；均重新验证 | 不做 AST 级最小差异补丁或超参数优化 |
| 验证结果沉淀 | 完成 | `SourceArtifact`、`ValidationRun`、`RepairStrategy`、`CapabilityVersion` 串联来源、生成源码和验证证据；历史指标参与排序 | 还没有跨数据集归一化经验评分 |

## 进阶要求

| 进阶要求 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| Web、CLI 或 API | 完成 | 同时提供 CLI、可视化 Web 工作台和本地 JSON API；`/api/docs` 与 `/api/openapi.json` 从路由目录自动生成接口文档 | Web/API 默认用于本机演示，没有用户登录、租户隔离和公网鉴权 |
| 多轮代码修复 | 完成 | `validate -> repair -> validate`，默认最多两轮；API 首轮 LLM 修复、后续安全模板回退，测试覆盖两种策略 | Mock 模式为保证离线确定性，不调用 LLM |
| 多候选算法自动比较 | 完成 | 五个模型插件、规格参数驱动的滚动回测、配置化指标排序 | 未实现图搜索 |
| 知识图谱可视化 | 完成 | 分层交互 HTML 支持搜索、类型筛选、缩放、重置、关系名称、关联高亮和节点属性详情；CLI、Web 与工作流均有入口 | 当前适合原型规模，尚未接入 Neo4j 等大规模图数据库 |
| 自动生成验证报告 | 完成 | `ReportAgent` 输出业务 Markdown、技术 Markdown 和 JSON；Web 默认渲染业务报告并可切换技术报告 | 无 |
| 验证结果回写图谱 | 完成 | 成功和最终失败均回写，且关联被验证的内容寻址 `CapabilityVersion`，保存 JSON/GraphML/HTML | 无 |
| 不同任务类型的验证配置 | 完成 | `ValidationProfileRegistry` 内置 `inventory_target`、`demand_forecast`、`intermittent_demand`，并支持插件新增 | 目前都属于库存预测场景，未跨行业任务 |
| 插件式接入算法模板或指标 | 完成 | `ModelRegistry.register()`、`MetricRegistry.register()` 及各自统一契约；均有注册测试 | 外部插件发现仍需在启动时显式注册，未使用 Python entry points 自动发现 |

## 加分项核验

| 加分项 | 状态 | 说明 |
|---|---|---|
| 图搜索、Beam Search 或 MCTS | 未实现 | 当前为知识检索加确定性排序 |
| 多智能体协作 | 完成 | 除业务 LangGraph Agent 外，代码阶段采用架构—多实现—独立审查—验证协议；API 模式对应三类独立 LLM 调用，Mock 模式使用可复现角色实现；证据写入 `implementation_blueprint.json`、`multi_agent_collaboration.json`、Trace、技术报告和 Web | 采用共享进程内编排，不是分布式 Agent 平台 |
| 从真实代码仓库抽取能力 | 完成 | 可递归扫描任意本地代码仓库，忽略缓存/产物目录，从 Python AST 抽取函数、类、参数、直接/传递依赖、内部调用、复杂度和来源哈希 | 不负责克隆远程仓库；跨语言调用图和测试语义仍未覆盖 |
| 代码安全检查和沙箱执行 | 部分完成 | AST 导入白名单、文件/网络/内省等危险调用阻断、去密钥超时子进程 | 不是容器级文件系统、系统调用和网络隔离沙箱 |
| 自动分析失败并形成经验 | 完成 | 失败被归一为稳定指纹和 `FailureCase`；成功修复与失败类型关联，后续运行会检索同模型、同类别的成功策略并提供给 RepairAgent | 当前是规则分类与精确类别检索，未做向量化根因聚类 |
| 算法能力版本管理 | 完成 | `CapabilitySpec.version`、规格/源码 SHA-256、自动语义补丁版本、父版本血缘、性能证据、`CapabilityVersion` 生命周期及 `versions list/compare/promote/rollback` CLI；操作写入 `VersionEvent` | 原型不负责生产环境文件切换 |
| 自然语言解释设计依据 | 完成 | 规划 rationale、候选未选原因以及“数据事实—系统推断—业务边界”结构；API 模式使用紧凑证据生成面向非技术用户的说明，失败时确定性降级 | 无 |
| 跨场景迁移 | 未实现 | 当前仅库存预测 |
| 自动生成接口文档或部署配置 | 完成 | `/api/docs` 和 `/api/openapi.json` 从服务端 `API_ROUTES` 自动生成，POST 分发也复用同一路由目录 | 未自动生成 Docker/Kubernetes 等生产部署配置 |
| 性能优化和资源消耗分析 | 完成 | 隔离微基准记录平均延迟、CPU 时间、吞吐量、Python 内存峰值和源码复杂度；正确候选按资源证据选优，输出独立 `performance_analysis.json`；Web 支持异步进度和 fast/balanced/thorough 配置 | 微基准不替代生产并发压测，原生库内存可能不完全计入 `tracemalloc` |

## 评审时建议运行的证据命令

```bash
python -m inventory_agent --help
python -m inventory_agent extract-capability --source . --output knowledge/extracted_capabilities.json
python -m inventory_agent replicate-capability --source examples/capabilities/moving_average.md --manifest artifacts/replication/review_manifest.json
python -m inventory_agent versions list --knowledge artifacts/knowledge/capability_graph.json --model moving_average
python -m inventory_agent run --description "为商品 3424 在仓库 1 预测未来14天目标库存" --data examples/data/cainiao_demo.csv --capability-source examples/capabilities/moving_average.md
python -m inventory_agent visualize-graph --output artifacts/knowledge/capability_graph.html
curl http://127.0.0.1:8000/api/openapi.json
python scripts/validate_project.py
pytest --cov=inventory_agent --cov-report=term-missing
ruff check inventory_agent tests scripts
```

以上状态只描述当前仓库已被代码和测试证明的能力，不把“可扩展设计”写成“已实现功能”。
# 最新进阶要求核查

八项进阶要求的逐项运行证据、改进内容和边界已整理到
[`docs/advanced_requirements_audit.md`](advanced_requirements_audit.md)。
本轮新增了第三类内置验证配置、自然语言间歇需求识别、CLI 任务配置覆盖、
可信本地指标插件加载、插件检查命令，以及报告中的插件与多轮修复证据。

项目现已同时提供可运行的 Web 可视化工作台，启动和页面功能说明见
[`docs/web_interface.md`](web_interface.md)。Web 页面覆盖完整工作流、能力抽取与
复刻、候选算法回测、运行证据、知识图谱和插件配置，并直接调用现有后端实现。

真实仓库函数与依赖抽取、失败根因经验、能力版本生命周期和自然语言设计依据的实现
说明见 [`docs/capability_lifecycle_features.md`](capability_lifecycle_features.md)。
