# 联网行业研究、搜索优化与自修复策略

## 目标与边界

联网研究是完整工作流中的可选增强节点，不是预测结果的外部替代品。它负责：

1. 根据需求画像构造库存预测研究查询；
2. 从 Crossref REST API 检索 DOI/URL 可追溯的学术元数据；
3. 对标题和可用摘要进行相关性排序与结构化分析；
4. 生成 `online_knowledge_extraction.json`；
5. 将来源作为 `SourceArtifact` 写入知识图谱；
6. 调整已注册候选的规划优先级，并为代码生成和修复提供约束。

Crossref 官方说明其 REST API 可公开检索成员提交的学术元数据且无需注册：
<https://www.crossref.org/documentation/retrieve-metadata/rest-api/>。

系统不会下载或执行网上代码，也不会把标题或摘要自动转换成未经审核的新算法。

## 工作流位置

```text
自然语言解析
  → 本地能力抽取
  → 数据画像
  → 联网行业研究（可选）
  → 图谱检索与候选优化
  → 滚动回测
  → 多实现代码生成
  → 安全与等价验证
  → 失败分析/经验检索/修复
  → 报告与图谱沉淀
```

不开启联网研究时，节点会记录 `disabled` 并立即继续，不影响离线可复现验收。网络、
Crossref 或 LLM 暂不可用时，节点记录 `degraded` 和错误类型，核心工作流安全降级。

## 搜索与证据排序

搜索策略不是把自然语言原样发送到任意搜索引擎，而是进行有边界的领域查询：

- 间歇需求：`intermittent demand Croston spare parts algorithm validation`；
- 周季节需求：`seasonal demand forecasting inventory algorithm validation`；
- 趋势需求：`demand forecasting trend regression inventory algorithm validation`；
- 波动需求：`volatile demand forecasting safety stock algorithm validation`；
- 稳定需求：`inventory demand forecasting stock control algorithm validation`。

每次最多返回 1-10 条记录，默认 5 条。相关性分数综合：

- 查询词与标题/摘要的覆盖率；
- 引用次数的对数缩放奖励；
- DOI 的确定性去重与排序。

输出保留标题、DOI、URL、作者、年份、来源期刊、许可地址、引用数、匹配词和相关性。
摘要只保存有界摘录，并明确“元数据和摘要不能替代全文复核”。

## 候选优化策略

LLM 只能在五个已注册模型中返回建议：`last_value`、`moving_average`、
`seasonal_naive`、`croston`、`ridge_lag`。研究建议用于调整候选顺序，但不能直接决定
最终模型。最终选择仍依次经过：

1. 需求画像匹配；
2. 图谱历史成功率和库存成本证据；
3. 无时间泄漏滚动回测；
4. 任务验证配置中的主指标与决胜指标。

因此，即使网上资料推荐 Croston，本地数据上若移动平均成本或误差更低，系统仍可选择
移动平均。此设计避免了“文献看起来权威，所以跳过本地验证”的错误。

## 代码生成与自修复策略

### 多实现搜索

API 模式默认从以下方向生成三个独立实现，最多可扩展为五个：

- 规格忠实；
- 边界条件鲁棒；
- 最小依赖；
- 向量化；
- 数值稳定。

候选不是按 LLM 自评选优，而是逐份经过语法、导入、接口、受限运行、确定性、边界输入
和参考行为等价验证。合格候选按运行耗时、源码规模和哈希进行确定性排序。

### 三层修复

1. **内部经验搜索**：按模型和失败类别检索知识图谱中的成功 `RepairStrategy`；
2. **LLM 最小修复**：输入当前源码、结构化根因、建议动作、历史经验和研究约束；
3. **安全模板回退**：外部接口失败或修复仍不合格时，回到经过参考行为验证的模板。

任何修复都必须重新执行完整代码门禁。最多两轮，安全类失败不会被自动执行。

接口契约被明确限定为：

- `forecast(history, horizon) -> list[float]`；
- `build_inventory_target(...) -> {daily_forecast: list, target_inventory: float}`。

运行器会把 `ndarray`、`Series`、标量或缺失字段报告为明确接口错误，便于形成可复用经验。

## 使用方法

先真实验证外部 LLM：

```powershell
uv run python -m inventory_agent doctor --live-llm
```

单独生成联网知识抽取文件：

```powershell
uv run python -m inventory_agent research-industry `
  --query "intermittent demand inventory forecasting" `
  --profile intermittent `
  --output artifacts/research/online_knowledge_extraction.json
```

执行包含联网研究的完整工作流：

```powershell
uv run python -m inventory_agent run `
  --description "为商品 1003 在仓库 1 预测未来14天间歇需求，联网检索资料并给出补货建议" `
  --data examples/business_data/demand_history.csv `
  --online-research `
  --trace-level full
```

一次验证 LLM 和 Crossref：

```powershell
uv run python scripts/validate_external_services.py
```

该脚本需要网络，故不加入默认离线 CI。结果写入 `artifacts/external_validation/`，且不会
保存 API Key。

Web 端可在“完整能力工厂 → 高级设置”勾选“联网检索 DOI 行业资料”。运行完成后，
技术报告会渲染资料标题、DOI、相关度、分析方式和知识抽取文件路径。
