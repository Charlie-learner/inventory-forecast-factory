# 笔试评分标准对照与演示证据

本文件按笔试 PDF 第 6-7 页的四类评分标准组织，不自行估算分数，只给出可运行证据和仍存边界。

## 技术能力（40%）

| 评分关注点 | 项目证据 | 建议演示 |
|---|---|---|
| 能力抽取-复刻-验证-沉淀闭环 | `InventoryCapabilityWorkflow` 的 LangGraph 节点和条件修复边 | 运行 `python scripts/validate_project.py` |
| LLM Agent、代码生成、知识图谱、算法验证理解 | Extraction/Requirement/Planning/Repair/Experience/Report Agent；规格驱动生成；NetworkX 图谱；滚动回测和等价验证 | 检查 `examples/extraction_run/` |
| 图谱 schema 合理性 | 来源、算法、指标、画像、验证、失败、修复、版本和版本事件节点 | 打开 `knowledge/base_capability_graph.html` |
| Agent 工作流清晰有效 | 解析、抽取、画像、规划、回测、生成、验证、修复、报告均为独立节点 | 使用 `--verbose` 运行完整流程 |
| 验证机制可执行、可扩展 | 验证配置注册表、指标插件、AST 安全检查、子进程、四类需求等价验证 | 运行 `pytest tests/test_codegen.py tests/test_validation_profiles.py` |
| 修复、比较或搜索优化 | 五候选滚动回测；最多两轮修复；失败经验跨运行复用 | 运行 `pytest tests/test_workflow.py -k reuses` |

## 代码质量（30%）

| 评分关注点 | 项目证据 |
|---|---|
| 规范与可读性 | 类型标注、模块 docstring、核心函数短注释、Ruff 全量通过 |
| 模块设计 | `agents`、`extraction`、`codegen`、`knowledge`、`validation`、`workflow` 分层 |
| 接口合理 | `CapabilitySpec`、统一 `forecast/build_inventory_target`、注册表和验证配置契约 |
| 错误处理和日志 | CLI 输入校验、LLM 降级、修复预算、结构化失败指纹、`--verbose` 日志 |
| 易运行和复现 | Mock LLM 默认离线；`scripts/validate_project.py` 一键验收 |
| 测试 | 单元、CLI、图谱、工作流和端到端测试；覆盖率命令写入 README |
| 避免硬编码 | 算法、指标、验证配置均可注册；数据成本和任务类型按输入解析 |

## 创新性（15%）

| 评分关注点 | 项目证据 | 边界 |
|---|---|---|
| Agent 协作 | 六类 Agent 经 LangGraph 协作 | 当前为单进程编排 |
| 图谱增强生成和验证 | 图谱检索候选、恢复规格、按历史成本排序、检索成功修复经验 | 未实现向量检索 |
| 搜索、优化、自修复 | 候选回测选优、条件修复循环、安全模板回退 | 未实现 Beam Search/MCTS |
| 失败经验复用 | `FailureCase` 稳定指纹、`RepairStrategy ADDRESSES FailureCase`、跨运行检索 | 当前为规则分类，不是根因聚类 |
| 真实行业问题 | 菜鸟全国/分仓数据、A/B 缺货积压成本、非聚划算销量口径 | 订单量仍未结合现货和在途库存 |

## 完整性（15%）

| 评分关注点 | 项目证据 |
|---|---|
| 功能完整 | 完整闭环、CLI、图谱、报告、版本管理和失败经验 |
| 文档质量 | README、schema、数据口径、能力抽取、需求追踪和本文件 |
| 示例完整 | `examples/complete_run/`、`examples/extraction_run/`、`examples/replication_run/`、带完整事件流和候选代码的 `examples/detailed_run/` |
| 报告清晰 | JSON 机器报告和 Markdown 人类报告 |
| 用户体验 | 八类 CLI 命令、完整/基础/关闭三级追踪、安全的旧任务保留策略、明确错误、审核状态和版本生命周期 |
| 端到端结果 | 一键脚本实际抽取 5 个能力、复刻代码、回测、验证、写图谱并管理版本 |

## 尚未覆盖的高阶项

- Beam Search、MCTS 或通用图搜索。
- 远程仓库拉取、跨文件调用图和测试语义抽取。
- Docker/容器级文件系统、网络和系统调用隔离。
- 自动语义版本递增，以及与生产部署系统联动的物理回滚。
- 跨行业场景迁移、自动接口文档和部署配置生成。
- CPU、峰值内存等系统级资源分析。

以上边界同时记录在 `docs/requirements_traceability.md`，避免把可扩展设计描述成已经实现的功能。
