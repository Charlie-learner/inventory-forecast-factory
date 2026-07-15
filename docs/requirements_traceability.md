# 笔试要求追踪表

| 笔试要求 | 实现位置 | 验证方式 |
|---|---|---|
| LLM 完成能力理解、知识抽取或代码修改 | `inventory_agent/llm`、`agents/requirement.py`、`agents/report.py` | Mock 和 OpenAI 兼容两种模式 |
| 具体行业场景 | 库存预测；菜鸟数据作为场景样例 | `examples/data/cainiao_demo.csv` |
| 小型能力知识库/知识图谱 | `inventory_agent/knowledge` | JSON 和 GraphML 双格式 |
| 自然语言描述到可运行算法 | `RequirementAgent` -> `PlanningAgent` -> `SafeCodeGenerator` | `inventory-agent run` |
| 统一验证机制 | `inventory_agent/validation`、`codegen/validator.py` | 滚动回测和四项代码检查 |
| CLI 用户入口 | `inventory_agent/cli.py` | `python -m inventory_agent --help` |
| 需求理解 | `agents/requirement.py` | `tests/test_agents.py` |
| 文档/知识图谱检索 | `knowledge/graph.py::retrieve_algorithms` | 需求类型驱动检索测试 |
| 规划算法实现 | `agents/planner.py` | 输出多个候选和选择依据 |
| 生成可运行代码 | `codegen/generator.py` | `examples/complete_run/generated` |
| 自动执行测试和指标评估 | `RollingBacktester`、`scripts/validate_project.py` | 一条命令执行完整验收 |
| 根据错误修复（基础） | `agents/repair.py`、LangGraph 条件回路 | 重新生成安全模板，尚非 LLM 定位修改 |
| 验证结果沉淀 | `agents/experience.py` | 运行后生成 ValidationRun 节点 |
| Git 版本控制 | `inventory-capability-factory` 分支 | 分阶段语义化提交 |
| 完整项目文档 | `README.md`、`docs/` | 覆盖题目要求的十个 README 章节 |
| 模块化和接口清晰 | `data/forecasting/validation/agents/workflow` | Ruff 和 pytest |
| 本地可复现 | `pyproject.toml`、`uv.lock`、`requirements.txt` | Mock 模式无需外部 API |
| 自动验证报告 | `agents/report.py` | JSON 与 Markdown 示例 |
| 真实非对称库存成本 | `data/costs.py`、`validation/metrics.py` | A=补少、B=补多，按 14 天总量计算 |
| 全国与分仓统一入口 | `data/loader.py`、`data/panel.py` | `all` 使用全国表，1-5 使用分仓表 |
| 多轮代码修复（基础） | LangGraph `validate -> repair -> validate` | 最大两轮预算，同模板重生成 |
| 多候选算法自动比较 | 五模型注册表与滚动回测 | 库存场景真实数据示例比较三个候选 |
| 图谱可交换/可查看 | `knowledge/*.json`、`knowledge/*.graphml` | NetworkX/Gephi 可打开 |
| 插件式算法接入 | `ModelRegistry.register` | 统一 `ForecastModel` 接口 |
| 代码安全检查 | AST 白名单和去密钥超时子进程 | `tests/test_codegen.py` |
| Mock LLM | `MockLLMClient` | 默认配置和端到端测试 |

## 尚未完成的加分项

- 没有实现 Beam Search 或 MCTS。
- 没有容器级安全沙箱，目前是 AST 限制加超时子进程。
- 没有 Web 界面，选择 CLI 作为题目允许的用户入口。
- 没有跨任务迁移，当前聚焦库存需求预测这一条闭环。
- 库存场景尚未实现跨商品冷启动；竞赛批量提交不属于本能力工厂原型的核心交付。
