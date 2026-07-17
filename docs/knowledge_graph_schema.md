# 库存算法能力知识图谱 Schema

本文描述当前代码实际使用的知识图谱契约。实现位于
`inventory_agent/knowledge/graph.py`，当前 `SCHEMA_VERSION = "1.5"`。图谱同时输出：

- JSON node-link：工作流读写和自动测试使用；
- GraphML：供 Gephi 等图分析工具导入；
- 独立 HTML/SVG：无需外部 JavaScript，可直接在浏览器交互查看。

## 1. 设计目标

图谱不是静态算法清单，而是“来源—能力—验证—失败—修复—版本”证据链。它需要回答：

1. 算法能力来自哪个文档、代码文件或带 DOI 的研究来源；
2. 算法适合什么需求画像，使用什么业务/精度指标；
3. 哪份生成源码实际通过了哪次验证；
4. 失败的归一化原因是什么，哪种修复策略曾成功；
5. 当前激活的是哪个能力版本，是否发生过发布或回滚。

## 2. 节点类型

| 类型 | 作用 | 主要属性 |
|---|---|---|
| `Algorithm` | 可检索、可复刻的预测能力 | `name`、`task_type`、`description`、`template_name`、`parameters`、`dependencies`、输入/输出契约、`source_hash`、`version`、`review_status` |
| `SourceArtifact` | Markdown、JSON、Python 或联网研究来源 | `source_type`、`source_ref`、`source_hash`、`source_url`、`source_license`、`accessed_at`、`provider`、`doi`、`relevance_score` |
| `DemandProfile` | 算法适用的数据画像 | `name`，如 `stable`、`trend`、`intermittent`、`weekly_seasonal` |
| `Metric` | 统一验证目标 | `name`；`inventory_cost` 额外保存公式、评价单位和 A/B 成本语义 |
| `ValidationRun` | 一次真实验证运行 | `item_id`、`store_code`、`status`、`metrics`、`validation_checks`、`timestamp` |
| `FailureCase` | 可跨运行复用的归一化失败 | `category`、`fingerprint`、`normalized_error`、`root_cause`、`recommended_actions`、`occurrence_count` |
| `RepairStrategy` | 针对失败案例的修复经验 | `description`、`strategy_fingerprint`、`attempt_count`、`success_count`、`last_used` |
| `CapabilityVersion` | 一份内容寻址的生成实现 | `source_hash`、`generated_path`、`generation_mode`、`lifecycle_status`、验证次数、最近指标与检查结果 |
| `VersionEvent` | 发布或回滚的审计事件 | `action`、`model`、`previous_active`、`selected_version`、`timestamp` |

## 3. 关系类型

| 关系 | 起点 → 终点 | 含义 |
|---|---|---|
| `SUITABLE_FOR` | `Algorithm` → `DemandProfile` | 算法适用的数据条件 |
| `EVALUATED_BY` | `Algorithm` → `Metric` | 算法应接受的统一评价口径 |
| `EXTRACTED_FROM` | `Algorithm` → `SourceArtifact` | 能力的可审计抽取来源 |
| `SUPPORTED_BY_RESEARCH` | `Algorithm` → `SourceArtifact` | 联网资料影响候选优先级，但不代表本地性能已经通过 |
| `VALIDATED` | `ValidationRun` → `Algorithm` | 本次运行验证了哪个算法 |
| `VERSION_OF` | `CapabilityVersion` → `Algorithm` | 生成源码属于哪个算法能力 |
| `VALIDATED_VERSION` | `ValidationRun` → `CapabilityVersion` | 本次运行实际检查的精确源码版本 |
| `OBSERVED_FAILURE` | `ValidationRun` → `FailureCase` | 本次运行观察到的归一化失败 |
| `FAILURE_OF` | `FailureCase` → `Algorithm` | 失败影响哪个算法能力 |
| `REPAIRED_BY` | `ValidationRun` → `RepairStrategy` | 本次运行采用的修复策略 |
| `ADDRESSES` | `RepairStrategy` → `FailureCase` | 修复策略针对的失败案例 |
| `ACTIVATED_VERSION` | `VersionEvent` → `CapabilityVersion` | 发布或回滚后被激活的版本 |

## 4. 关键约束

- 节点 ID 使用类型前缀，例如 `algorithm:croston`、`metric:inventory_cost`；生成版本和失败案例使用内容哈希或稳定指纹，避免仅靠显示名称关联。
- `SourceArtifact.source_hash` 保存来源内容摘要；同一路径的新内容摄取后会替换旧来源节点，防止图谱保留错误版本。
- `ValidationRun.metrics` 与 `validation_checks` 在 GraphML 中以 JSON 字符串保存，保证跨格式可序列化。
- 未经过统一门禁的 `CapabilityVersion` 不能发布；发布/回滚只接受已验证版本，并生成 `VersionEvent`。
- 联网研究节点的 `review_status` 为 `evidence_only`。研究资料只增强检索和解释，不能绕过本地回测与代码验证。
- `inventory_cost` 的语义固定为 `A=understock（补少/缺货）`、`B=overstock（补多/积压）`，评价单位为预测周期总量。

## 5. Schema 版本演进

| 版本 | 主要变化 |
|---|---|
| `1.5` | 加入有界联网研究证据和 `SUPPORTED_BY_RESEARCH` |
| `1.4` | 加入来源许可、置信度、审查状态、证据引用与抽取诊断 |
| `1.3` | 加入可复用失败案例及可审计版本生命周期事件 |
| `1.2` | 加入来源追踪和内容寻址的生成能力版本 |
| `1.1` | 加入历史验证增强检索与独立 HTML 输出 |

## 6. 当前示例

以下统计由 2026-07-17 的确定性用例重新生成：

| 图谱 | 内容 | 节点 / 关系 | 入口 |
|---|---|---:|---|
| 基础图谱 | 五个注册算法、需求画像和指标 | 18 / 35 | [`knowledge/base_capability_graph.html`](../knowledge/base_capability_graph.html) |
| 完整精选图谱 | 增加来源、验证、失败、修复、版本及发布事件 | 28 / 48 | [`examples/knowledge_graph/complete_capability_graph.html`](../examples/knowledge_graph/complete_capability_graph.html) |
| 最新高级用例图谱 | 两次修复闭环与一次经验复用 | 29 / 52 | [`examples/advanced_showcase/README.md`](../examples/advanced_showcase/README.md) |

机器可读的外部能力抽取结果位于
[`knowledge/extracted_external_capabilities.json`](../knowledge/extracted_external_capabilities.json)。基础图谱是确定性
bootstrap 产物；普通运行产生的临时图谱写入 `artifacts/knowledge/`，不会污染版本化基础图谱。

## 7. 生成与查看

生成基础图谱的浏览器视图：

```bash
uv run python -m inventory_agent visualize-graph \
  --knowledge knowledge/base_capability_graph.json \
  --output artifacts/knowledge/capability_graph.html
```

重新生成外部能力抽取、自动修复示例和完整精选图谱：

```bash
uv run python scripts/generate_submission_examples.py
```

HTML 使用确定性分层布局，支持节点搜索、类型筛选、缩放/拖动、关系名称开关、关联边高亮和节点属性详情。图例只显示当前图中实际存在的节点类型。
