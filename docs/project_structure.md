# 项目目录与模块边界

本文说明哪些内容属于源码、提交证据、本地数据或可删除产物，避免把运行结果和业务数据混入核心代码。

## 顶层目录

| 目录 | 职责 | 是否提交 Git |
|---|---|---|
| `inventory_agent/` | 可安装的核心 Python 包 | 是 |
| `tests/` | 单元、接口、Web、工作流和端到端测试 | 是 |
| `scripts/` | 数据生成、展示用例、外部验收、项目验收和安全清理脚本 | 是 |
| `docs/` | 架构、接口、业务口径、评分追踪和使用文档 | 是 |
| `knowledge/` | 版本化的基础能力图谱与知识抽取结果 | 是 |
| `examples/` | 小型可复现数据和精选运行证据 | 是 |
| `data/` | 用户本地原始数据与处理中间数据 | 只提交 `.gitkeep` |
| `artifacts/` | Web 上传、任务状态和本地运行产物 | 否，可随时重新生成 |
| `tmp/`、缓存、覆盖率文件 | 测试或工具临时文件 | 否，可随时删除 |

`examples/` 与 `artifacts/` 的区别是：前者是经过筛选、用于评分复核的稳定证据；后者是用户每次运行产生的本地状态，不应提交。

## 核心包分层

```text
inventory_agent/
├── agents/          单一职责 Agent：需求、抽取、规划、研究、生成协作、修复、报告
├── codegen/         独立源码生成、复刻、受限执行与统一代码验证
├── data/            菜鸟及通用 CSV/ZIP 识别、标准化、成本和序列面板
├── extraction/      Python AST、Markdown、JSON 等来源的能力抽取
├── forecasting/     预测算法统一接口和注册表
├── knowledge/       能力知识图谱 schema、检索、沉淀和可视化
├── llm/             Mock 与 OpenAI 兼容客户端的最小统一接口
├── observability/   详细 Trace、运行清单和历史保留策略
├── research/        可替换的联网研究提供者
├── services/        回测、补货、性能、版本和评分审计等应用服务
├── validation/      指标、滚动回测、失败分类和验证配置
├── web/             HTTP 适配层、后台任务、OpenAPI 和静态前端
├── workflow/        LangGraph 业务编排；不重复实现底层算法和服务
├── config.py        密钥安全的环境配置
├── domain.py        跨模块领域数据契约
└── execution.py     执行档位和可注入运行限制
```

依赖方向遵循“接口层 → 工作流/服务 → 领域与基础能力”。Web 和 CLI 只负责输入输出适配；算法选择、验证、补货和图谱写回由共享服务完成，避免两套业务逻辑。

## 运行产物清理

先预览：

```powershell
uv run python scripts/clean_workspace.py
```

确认后清理：

```powershell
uv run python scripts/clean_workspace.py --apply
```

脚本只清理已知的缓存、`artifacts/`、`tmp/`、覆盖率文件、构建元数据和源码目录中的 `__pycache__`。它明确保护 `.git/`、`.venv/`、`.uv-cache/`、`data/` 和 `examples/`，并验证所有删除目标都位于项目根目录内。

## 维护原则

- 新算法通过注册表与统一预测契约接入，不在工作流中增加模型名称分支。
- 新指标和验证任务通过插件或注册表接入，不修改 Web/CLI 分发逻辑。
- 可调运行限制使用 `RuntimeLimits` 注入；性能开销使用 `ExecutionProfile` 配置。
- 预期的用户错误使用明确异常和中文提示；意外异常记录服务端堆栈，对客户端返回脱敏消息。
- 外部 LLM 和联网研究失败必须记录降级原因，不能静默吞掉，也不能阻断可复现的核心流程。
