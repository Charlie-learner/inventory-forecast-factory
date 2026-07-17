# 能力抽取、复刻、验证与版本沉淀

本文说明笔试核心闭环的可执行实现。项目中的“复刻”不是复制文件，而是将来源材料规范化为可审计能力规格，再生成满足统一接口且行为一致的独立实现。

## 1. CapabilitySpec

所有来源统一转换为 `CapabilitySpec`：

| 字段 | 含义 |
|---|---|
| `name` / `version` | 能力名称和业务版本 |
| `task_type` | 任务类型 |
| `description` | 算法能力说明 |
| `template_name` | 离线安全生成模板或参考能力名称 |
| `input_contract` / `output_contract` | 输入输出契约 |
| `suitable_for` | 适用需求画像 |
| `metrics` | 验证指标 |
| `dependencies` / `parameters` | 环境依赖和算法参数 |
| `source_type` / `source_ref` | 来源类型和位置 |
| `source_hash` | 原始来源 SHA-256 |
| `extracted_by` | `python_ast`、`deterministic` 或 `llm` |
| `source_title` / `source_url` / `source_license` | 外部资料标题、地址和使用说明 |
| `accessed_at` | 外部资料访问日期 |
| `confidence` / `review_status` | 抽取置信度和审核状态 |
| `evidence_refs` / `extraction_warnings` | 字段证据位置和抽取边界 |

## 2. 支持的来源

- JSON：单个对象、对象数组或带 `capabilities` 的对象。
- Markdown/TXT：标题加 `key: value` 字段；示例见 `examples/capabilities/moving_average.md`。
- Python 文件或本地仓库目录：递归 AST 扫描 `ForecastModel` 子类，忽略虚拟环境、缓存、构建和产物目录，抽取类名、模型名、文档字符串、构造参数默认值、类级适用画像和该类实际引用的导入依赖；结果附带扫描文件数、命中文件数和解析错误。
- API 模式：Markdown/TXT 优先由 LLM 规范化为 JSON；调用失败时回退确定性解析器。

抽取与执行是两个不同状态：尚未接入本地 `ModelRegistry` 的新算法仍会作为 `Algorithm` 和 `SourceArtifact` 沉淀，但不会进入自动回测；完成实现注册或人工审核后才能成为可执行候选。这样既保留半自动扩展入口，也避免把“抽取到描述”误当成“算法已经可运行”。

抽取真实源码：

```bash
python -m inventory_agent extract-capability \
  --source . \
  --output knowledge/extracted_capabilities.json \
  --knowledge knowledge/base_capability_graph.json
```

图谱会增加 `SourceArtifact` 节点和 `Algorithm -EXTRACTED_FROM-> SourceArtifact` 关系。

仓库另提供两组提交版抽取结果：

- `knowledge/extracted_capabilities.json`：从本地真实 Python 源码抽取；
- `knowledge/extracted_external_capabilities.json`：从五份带权威来源的能力文档抽取。

结构约束见 `knowledge/capability_spec.schema.json`。

独立的半自动复刻入口：

```bash
python -m inventory_agent replicate-capability \
  --source examples/capabilities/moving_average.md \
  --output-dir artifacts/replication/generated \
  --manifest artifacts/replication/review_manifest.json
```

该命令输出自包含源码、JSON 审核清单和 Markdown 审核清单。有注册参考能力时，等价性通过后状态为 `auto_validated`；没有参考能力时只完成安全、接口和运行检查，状态为 `review_required`。显式 `--approve` 会记录人工批准，而不会伪造等价性检查结果。

## 3. 规格驱动复刻

工作流在候选回测结束后，从图谱恢复胜出算法的 `CapabilitySpec`：

- Mock 模式：按 `template_name` 渲染自包含、可审计实现。
- API 模式：先让 LLM 根据完整规格生成源码；若提供方失败则回退安全模板。

生成文件包含 `CAPABILITY_NAME`、完整 `CAPABILITY_SPEC`、参数和实际算法逻辑，不依赖 `default_registry()` 转发预测，因此生成产物本身可独立审查。

## 4. 统一验证

生成源码依次通过：

1. Python 语法检查；
2. 导入白名单、文件/网络访问、危险属性调用和双下划线运行时内省检查；
3. `forecast()`、`build_inventory_target()` 接口检查；
4. 非负、有限、预测周期长度和目标库存契约；
5. 全零历史和短预测周期边界输入；
6. 相同输入重复执行的确定性；
7. 去除 API Key 后的超时子进程运行；
8. 生成实现与参考算法的数值等价性。

等价性在隔离子进程中使用周期型、间歇型、趋势型和全零历史四组用例，对比生成实现与注册参考模型，并报告 `equivalence_cases` 和 `equivalence_max_error`。任一用例不一致都会进入修复循环，而不能仅因代码“能运行”就通过。

## 5. 多实现自主代码生成

API 模式不会只接受第一份 LLM 代码。`SafeCodeGenerator` 会根据同一个 `CapabilitySpec` 和当前
业务上下文生成多份独立实现，当前内置策略包括：

- 规格语义忠实；
- 边界输入鲁棒；
- 最小依赖与清晰结构；
- 向量化实现；
- 数值稳定性。

生成提示中明确禁止调用 `inventory_agent` 内部注册表、已有模型实现或生成代码，要求从算法原理
编写自包含模块。每份实现分别保存：

- 实现候选 ID 和生成策略；
- 生成提示摘要哈希；
- 源码哈希和代码路径；
- 安全、接口、运行、稳定性和等价验证结果；
- 运行耗时、是否入选。

存在注册参考能力时，候选必须通过四组行为等价用例；新算法没有参考实现时，可以完成安全和运行
验证，但仍标记为 `review_required`，需要人工确认算法语义后才能注册。这样既增强自动生成能力，
又不会把“代码能运行”误写成“新算法正确”。

## 6. 修复与沉淀

API 模式首轮把当前源码、能力规格和验证错误交给修复 Agent；失败或第二轮时使用安全规格模板。每个最终结果沉淀为：

- `ValidationRun`：业务指标、检查结果、状态和时间；
- `RepairStrategy`：错误类型、修复轮次和策略；
- `CapabilityVersion`：规格版本、生成模式、规格哈希、源码哈希和产物路径；
- `SourceArtifact`：原始材料路径、类型、哈希和抽取方式。

验证失败会先归一化为类别、稳定指纹和可重试属性，并沉淀为 `FailureCase`。成功运行中的 `RepairStrategy` 会通过 `ADDRESSES` 关联失败类型；后续同模型遇到同类失败时，RepairAgent 会检索最近的成功修复经验，API 模式还会把这些经验加入修复上下文。

验证后的源码版本默认处于 `candidate` 状态，可使用以下命令管理：

```bash
python -m inventory_agent versions list --knowledge artifacts/knowledge/capability_graph.json --model moving_average
python -m inventory_agent versions compare --knowledge artifacts/knowledge/capability_graph.json --model moving_average --left HASH1 --right HASH2
python -m inventory_agent versions promote --knowledge artifacts/knowledge/capability_graph.json --model moving_average --version HASH
python -m inventory_agent versions rollback --knowledge artifacts/knowledge/capability_graph.json --model moving_average --version OLD_HASH
```

只有至少一次成功验证的版本可以被激活。发布或回滚会把旧活动版本标记为 `superseded`，并创建 `VersionEvent` 审计节点。

这些关系使评审者能够从验证报告追溯到生成源码、能力规格和原始来源，也使后续运行能够复用历史成功率和平均库存成本。
