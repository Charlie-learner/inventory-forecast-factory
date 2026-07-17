# 示例与评分证据索引

本目录只保存小型、稳定、可复核的提交证据。日常 Web 上传和新运行结果位于 `artifacts/`，不会提交 Git。

| 目录 | 用途 | 建议查看内容 |
|---|---|---|
| `data/` | 最小菜鸟格式演示数据 | `cainiao_demo.csv` |
| `business_data/` | 含库存快照、在途、欠单、MOQ 和仓容的完整业务样例 | `README.md`、五张业务表 |
| `capabilities/` | 五种预测算法的可抽取能力文档 | Markdown 能力规格与来源 |
| `replication_run/` | 独立能力复刻和多智能体审查证据 | 生成源码、审查清单、性能比较 |
| `repair_run/` | 首次失败、根因分析、自动修复和重新验证 | `index.json` 指向当前精选运行 |
| `advanced_showcase/` | 联网研究、多智能体代码、经验复用、性能和图谱写回的综合展示 | `showcase_summary.md` |
| `acceptance/` | 多场景自动验收汇总 | Markdown 与 JSON 报告 |
| `external_validation/` | 已脱敏的外部 LLM/Crossref 验收摘要 | 不包含 API Key |
| `knowledge_graph/` | 包含验证、失败、修复和版本节点的完整图谱 | HTML、JSON、GraphML |
| `complete_run/` | 真实菜鸟格式的简明业务结果 | 业务与技术报告 |
| `detailed_run/` | 逐 Agent/工具事件和候选代码的完整 Trace | `detailed_trace.md` |
| `extraction_run/` | 带来源能力抽取参与的完整运行 | 抽取结果、Trace 和报告 |
| `plugins/` | 指标与验证配置插件示例 | `stockout_priority.py` |
| `performance_validation/` | 性能字段和资源边界说明 | `README.md` |

其中 `advanced_showcase/` 是综合演示入口；其余目录用于单独复核某项能力。生成新提交证据时应先运行自动验收，确认后再替换对应精选示例，不要直接把整个 `artifacts/` 复制进来。
