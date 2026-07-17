# 项目能力自查与运行依据

这份文件从核心技术、代码质量、功能设计和完整性四个方面整理项目现状。这里不估算分数，只记录对应实现、运行方法和仍然存在的边界。

## 核心技术

| 检查项 | 项目实现 | 建议查看方式 |
|---|---|---|
| 能力抽取-复刻-验证-沉淀闭环 | `InventoryCapabilityWorkflow` 的 LangGraph 节点和条件修复边 | 运行 `uv run python scripts/validate_project.py`，再查看 `examples/advanced_showcase/README.md` |
| LLM Agent、代码生成、知识图谱、算法验证理解 | Extraction/Requirement/Planning/Repair/Experience/Report Agent；API 模式多策略生成独立源码并验证选优；NetworkX 图谱；滚动回测和等价验证 | 检查 `examples/extraction_run/` 和技术报告中的实现候选表 |
| 图谱 schema 合理性 | 来源、算法、指标、画像、验证、失败、修复、版本和版本事件节点 | 打开 `examples/knowledge_graph/complete_capability_graph.html` |
| Agent 工作流清晰有效 | 解析、抽取、画像、规划、回测、生成、验证、修复、报告均为独立节点 | 使用 `--verbose` 运行完整流程 |
| 验证机制可执行、可扩展 | 验证配置注册表、指标插件、AST 安全检查、子进程、四类需求等价验证 | 运行 `pytest tests/test_codegen.py tests/test_validation_profiles.py` |
| 修复、比较或搜索优化 | 五候选滚动回测；最多两轮修复；失败经验跨运行复用 | 运行 `pytest tests/test_workflow.py -k reuses` |

## 代码质量

| 检查项 | 项目实现 |
|---|---|
| 规范与可读性 | 类型标注、模块 docstring、核心函数短注释、Ruff 全量通过 |
| 模块设计 | `agents`、`extraction`、`codegen`、`knowledge`、`validation`、`workflow` 分层 |
| 接口合理 | `CapabilitySpec`、统一 `forecast/build_inventory_target`、注册表和验证配置契约；Web、CLI、JSON API 共用服务层；自动 OpenAPI 文档 |
| 错误处理和日志 | CLI 输入校验、LLM 降级、修复预算、结构化失败指纹、`--verbose` 日志 |
| 易运行和复现 | Mock LLM 默认离线；`scripts/validate_project.py` 可一键自检 |
| 测试 | 单元、CLI、Web/API、图谱、代码生成、修复、工作流和端到端测试；2026-07-17 的完整测试中 136 项通过，覆盖率下限为 80%，当前实测 85.34% |
| 避免硬编码 | 算法、指标、验证配置均可注册；数据成本和任务类型按输入解析 |

## 设计上的尝试

| 检查项 | 项目实现 | 边界 |
|---|---|---|
| Agent 协作 | 业务工作流 Agent 经 LangGraph 协作；代码阶段额外执行 `CodeArchitectureAgent -> 多个 CodeImplementationAgent -> CodeReviewAgent -> GeneratedCodeValidator`，架构、实现和审查在 API 模式下是独立调用 | 当前为单进程编排，角色状态通过结构化产物传递 |
| 图谱增强生成和验证 | 图谱检索候选、恢复规格、按历史成本排序、检索成功修复经验；联网 DOI 资料作为 SourceArtifact 写入图谱 | 未实现向量检索 |
| 搜索、优化、自修复 | 需求画像驱动的 Crossref 检索与证据排序、候选优先级优化、算法回测选优、同一能力多实现源码生成与验证排名、历史经验检索、LLM 最小修复和安全模板回退 | 未实现 Beam Search/MCTS |
| 失败经验复用 | `FailureCase` 稳定指纹、`RepairStrategy ADDRESSES FailureCase`、跨运行检索 | 当前为规则分类，不是根因聚类 |
| 真实行业问题 | 菜鸟全国/分仓数据、A/B 缺货积压成本、非聚划算销量口径；完整业务示例进一步应用现货、在途、欠单、安全库存、MOQ、包装倍数和仓容计算建议补货量 | 供应商产能、预算、采购日历和跨仓调拨执行仍在原型边界外 |

## 项目完整性

| 检查项 | 项目实现 |
|---|---|
| 功能完整 | 完整闭环、CLI、图谱、报告、版本管理和失败经验 |
| 文档质量 | README、schema、数据口径、能力抽取、需求追踪和本文件 |
| 示例完整 | `examples/advanced_showcase/README.md` 指向当前高级用例；`examples/repair_run/README.md` 指向当前修复闭环；另含 `complete_run/`、`extraction_run/`、`replication_run/`、`detailed_run/` 和多表行业数据 |
| 报告清晰 | JSON 机器报告和 Markdown 人类报告 |
| 用户体验 | 自然语言 Web 对话、多文件上传与字段映射、批量商品/仓库任务、业务报告优先、Markdown 渲染、CLI/API、三级追踪和版本生命周期 |
| 端到端结果 | 一键脚本实际抽取 5 个能力、复刻代码、回测、验证、写图谱并管理版本 |

## 尚未覆盖的高阶项

- Beam Search、MCTS 或通用图搜索。
- 远程仓库自动克隆、跨语言调用图和测试语义抽取。
- Docker/容器级文件系统、网络和系统调用隔离。
- 与生产部署系统联动的物理回滚。
- 跨行业场景迁移、生产部署配置自动生成（接口文档已经由路由目录自动生成）。
- 生产并发压测和原生库完整常驻内存分析；当前已提供 CPU 时间、平均延迟、吞吐量和 Python 分配内存峰值。

以上边界同时记录在 `docs/requirements_traceability.md`，避免把可扩展设计描述成已经实现的功能。
