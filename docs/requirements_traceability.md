# 笔试要求核验与追踪

本表以《人工智能（大模型）-笔试.pdf》第 2-5 页为核验基准。状态含义：

- **完成**：仓库中有实现、可运行入口和自动化测试或示例证据。
- **部分完成**：主链路可用，但与题目描述的完整能力仍有明确边界。
- **未实现**：当前仓库没有可执行实现，不以规划或文档代替功能。

## 基础要求

| 要求 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| 完整项目代码库 | 完成 | `inventory_agent/`、`tests/`、`scripts/` | 无 |
| 示例行业数据或模拟材料 | 完成 | `examples/data/cainiao_demo.csv`、`docs/data_schema.md` | 完整原始数据因体积不提交 Git |
| 能力知识图谱 schema 说明 | 完成 | `docs/knowledge_graph_schema.md` | 无 |
| 知识抽取结果文件 | 完成 | `knowledge/base_capability_graph.json`、`.graphml` | 当前知识主要由算法注册元数据构建，不是通用文档抽取器 |
| Agent 工作流代码或配置 | 完成 | `inventory_agent/workflow/factory.py` 的 LangGraph 流程 | 无 |
| 至少一个描述到代码的完整示例 | 完成 | `examples/complete_run/`；`python -m inventory_agent run ...` | 示例采用受约束代码模板，不是自由生成源码 |
| 自动验证脚本 | 完成 | `scripts/validate_project.py` | 无 |
| 验证报告样例 | 完成 | `examples/complete_run/validation_report.{json,md}` | 样例需在重要逻辑变化后重新生成 |
| README | 完成 | `README.md` 覆盖题目要求的十个章节 | 无 |
| 环境依赖文件 | 完成 | `pyproject.toml`、`uv.lock`、`requirements.txt` | 无 |
| 使用示例和测试用例 | 完成 | README 命令、`tests/` | 无 |

## 任务核心流程

| 流程 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| 理解自然语言能力描述 | 完成 | `RequirementAgent`；中文/英文和全国/分仓测试 | Mock 模式以规则抽取为主 |
| 从文档、代码或图谱检索知识 | 部分完成 | `CapabilityKnowledgeGraph.retrieve_algorithms` 检索图谱，并结合历史验证排序 | 没有从任意文档或真实代码仓库在线抽取能力 |
| 规划算法实现方案 | 完成 | `PlanningAgent` 输出候选、依据和验证指标 | 不是 Beam Search/MCTS |
| 生成可运行代码 | 完成 | `SafeCodeGenerator` 生成标准能力模块 | 受约束模板生成，未让 LLM 自由生成 |
| 自动测试和指标评估 | 完成 | 滚动回测、A/B 库存成本、WAPE/sMAPE/Bias/RMSE、代码五类检查 | 子进程不是容器级沙箱 |
| 根据错误修复或优化 | 完成 | LangGraph 最多两轮；API 模式首轮按源码和错误进行 LLM 修复，失败后回退安全模板；Mock 模式直接安全回退；均重新验证 | 不做 AST 级最小差异补丁或超参数优化 |
| 验证结果沉淀 | 完成 | 成功与最终失败写回 `ValidationRun`/`RepairStrategy`；历史指标参与后续检索排序 | 还没有跨数据集归一化经验评分 |

## 进阶要求

| 进阶要求 | 状态 | 实现与证据 | 尚存边界 |
|---|---|---|---|
| Web、CLI 或 API | 完成 | CLI：`doctor`、`prepare-sample`、`benchmark`、`run`、`visualize-graph` | 没有 Web/API，但题目要求三选一 |
| 多轮代码修复 | 完成 | `validate -> repair -> validate`，默认最多两轮；API 首轮 LLM 修复、后续安全模板回退，测试覆盖两种策略 | Mock 模式为保证离线确定性，不调用 LLM |
| 多候选算法自动比较 | 完成 | 五个模型插件、滚动回测、配置化指标排序 | 未实现图搜索 |
| 知识图谱可视化 | 完成 | `render_html()` 生成无外部依赖的 SVG HTML；CLI 与工作流自动输出 | 暂无筛选、缩放等复杂交互 |
| 自动生成验证报告 | 完成 | `ReportAgent` 输出 JSON 和 Markdown | 无 |
| 验证结果回写图谱 | 完成 | 成功和最终失败均回写，保存 JSON/GraphML/HTML | 无 |
| 不同任务类型的验证配置 | 完成 | `ValidationProfileRegistry` 内置 `inventory_target` 与 `demand_forecast` | 目前都属于库存预测场景，未跨行业任务 |
| 插件式接入算法模板或指标 | 完成 | `ModelRegistry.register()`、`MetricRegistry.register()` 及各自统一契约；均有注册测试 | 外部插件发现仍需在启动时显式注册，未使用 Python entry points 自动发现 |

## 加分项核验

| 加分项 | 状态 | 说明 |
|---|---|---|
| 图搜索、Beam Search 或 MCTS | 未实现 | 当前为知识检索加确定性排序 |
| 多智能体协作 | 完成 | Requirement、Planning、Repair、Experience、Report 多 Agent 经 LangGraph 协作 |
| 从真实代码仓库抽取能力 | 未实现 | 当前从注册元数据构建基础图谱 |
| 代码安全检查和沙箱执行 | 部分完成 | AST 白名单、危险调用阻断、去密钥超时子进程；不是容器/系统调用/网络隔离沙箱 |
| 自动分析失败并形成经验 | 部分完成 | 错误分类、轮次、LLM/模板策略和最终失败会写入图谱；未做跨运行根因聚类 |
| 算法能力版本管理 | 部分完成 | Git 管理源码和基础图谱，schema 有版本；没有独立能力版本/发布机制 |
| 自然语言解释设计依据 | 完成 | 规划 rationale 与报告 Agent 总结 |
| 跨场景迁移 | 未实现 | 当前仅库存预测 |
| 自动生成接口文档或部署配置 | 未实现 | README 有人工接口说明，但没有自动生成器 |
| 性能优化和资源消耗分析 | 部分完成 | 记录生成代码运行耗时；未分析内存、CPU 或执行优化 |

## 评审时建议运行的证据命令

```bash
python -m inventory_agent --help
python -m inventory_agent visualize-graph --output artifacts/knowledge/capability_graph.html
python scripts/validate_project.py
pytest --cov=inventory_agent --cov-report=term-missing
ruff check inventory_agent tests scripts
```

以上状态只描述当前仓库已被代码和测试证明的能力，不把“可扩展设计”写成“已实现功能”。
