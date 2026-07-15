# Inventory Capability Factory

基于 AI Agent 的菜鸟多仓需求预测算法能力工厂。系统把自然语言库存预测需求转换为可运行的 Python 能力模块，并自动完成知识检索、候选算法比较、滚动验证、代码检查、失败修复、报告生成和经验沉淀。

本仓库主数据集仅使用[菜鸟-需求预测与分仓规划](https://tianchi.aliyun.com/dataset/167097)。

## 1. 项目背景和目标

普通预测脚本只能执行预先写好的流程。本项目针对笔试要求，完整实现：

```text
能力描述 -> 知识检索 -> 方案规划 -> 代码生成
         -> 自动验证 -> 错误修复 -> 结果沉淀
```

业务目标是预测某个商品在全国或区域仓未来 14 天的非聚划算支付件数，并通过补多/补少成本、WAPE、sMAPE 和 Bias 比较候选方案。预测结果是需求输入，不直接等同于最终补货量。

## 2. 系统架构和模块设计

```mermaid
flowchart LR
    U[自然语言需求] --> R[RequirementAgent]
    R --> P[序列画像]
    P --> K[能力知识图谱检索]
    K --> L[PlanningAgent]
    L --> B[候选模型滚动回测]
    B --> C[CodeGenerationAgent]
    C --> V[静态和隔离运行验证]
    V -->|失败| F[RepairAgent]
    F --> V
    V -->|成功| E[ExperienceAgent]
    E --> G[(JSON / GraphML)]
    E --> O[ReportAgent]
```

主要模块：

- `inventory_agent/data`：菜鸟无表头 CSV schema、ZIP 读取、面板时序构造。
- `inventory_agent/forecasting`：统一预测接口与插件式模型注册。
- `inventory_agent/validation`：无数据泄漏的滚动回测与业务指标。
- `inventory_agent/knowledge`：NetworkX 能力知识图谱和历史经验。
- `inventory_agent/codegen`：受约束代码生成、AST 检查和超时子进程验证。
- `inventory_agent/agents`：需求、规划、修复、经验和报告 Agent。
- `inventory_agent/workflow`：LangGraph 闭环编排。

旧的 `time_series_agent/` 仅作为原型来源保留，新功能全部位于 `inventory_agent/`。

## 3. 能力知识图谱 schema 和示例

知识图谱包含 `Algorithm`、`DemandProfile`、`Metric`、`ValidationRun` 和 `RepairStrategy` 节点，以及 `SUITABLE_FOR`、`EVALUATED_BY`、`VALIDATED`、`REPAIRED_BY` 关系。

详细说明见 [docs/knowledge_graph_schema.md](docs/knowledge_graph_schema.md)。可直接检查：

- `knowledge/base_capability_graph.json`
- `knowledge/base_capability_graph.graphml`

运行后的验证结果写入 `artifacts/knowledge/`，避免修改版本化基础图谱。

## 4. Agent 工作流设计

1. `RequirementAgent` 从中文或英文需求中提取商品、仓库、预测周期和目标。
2. 数据画像计算零需求比例、波动系数和需求类型。
3. `PlanningAgent` 从图谱检索适用算法，形成多个候选方案。
4. 验证器执行滚动时间回测，按库存成本和 WAPE 排序。
5. 代码生成器为胜出模型生成标准 `forecast(history, horizon)` 模块。
6. 验证器检查语法、导入白名单、接口和隔离子进程运行结果。
7. 失败时 `RepairAgent` 在最多两轮内重新生成安全实现。
8. `ExperienceAgent` 把指标和修复经验写回知识图谱。
9. `ReportAgent` 输出 JSON 和 Markdown 报告。

默认使用 Mock LLM，完全离线可复现。切换到 OpenAI 兼容接口后，LLM 参与需求理解和报告总结；模型选择仍由实际回测裁决。

## 5. 环境配置和运行方法

要求 Python 3.10-3.13，推荐使用 `uv`：

```bash
uv sync --extra dev
```

也可以使用 pip：

```bash
python -m venv .venv
pip install -r requirements.txt
```

复制环境模板：

```bash
copy .env.example .env
```

离线模式：

```dotenv
LLM_MODE=mock
```

OpenAI 兼容接口模式：

```dotenv
LLM_MODE=api
MODEL=your-model-name
BASE_URL=https://your-provider.example/v1
API_KEY=your-new-api-key
```

`.env` 已被 Git 忽略。不要把真实密钥写入 README、源码、命令行或提交记录。

环境诊断：

```bash
uv run python -m inventory_agent doctor
```

## 6. 示例数据和测试任务

原始 ZIP 不提交 Git。通过环境变量或参数指定：

```bash
uv run python -m inventory_agent prepare-data \
  --zip-path "C:/Users/you/Downloads/CAINIAO Part II Data_20160509.zip" \
  --items 20 \
  --output data/processed/cainiao_sample.csv
```

真实文件统计：

- 全国特征：210,549 行，963 个有历史商品，31 列。
- 分仓特征：864,772 行，963 个商品，5 个仓，32 列。
- 时间范围：2014-10-10 至 2015-12-27，共 444 天。
- 提交模板：1,000 个商品 × 全国和 5 个仓，包含冷启动商品。

字段定义见 [docs/data_schema.md](docs/data_schema.md)。仓库附带一个从菜鸟数据抽取的 140 天最小演示文件：`examples/data/cainiao_demo.csv`。

## 7. 生成算法代码示例

完整自然语言任务：

```bash
uv run python -m inventory_agent run \
  --description "为商品 3424 在仓库 1 预测未来14天需求，比较多个算法并降低补多补少成本" \
  --data examples/data/cainiao_demo.csv
```

系统会生成类似以下接口：

```python
def forecast(history: list[float], horizon: int) -> list[float]:
    series = pd.Series(history, dtype=float)
    model = default_registry().create(MODEL_NAME)
    return model.predict(series, horizon).tolist()
```

真实生成文件见 `examples/complete_run/generated/forecast_moving_average.py`。

## 8. 验证结果和报告样例

完整样例见：

- `examples/complete_run/validation_report.json`
- `examples/complete_run/validation_report.md`

该样例使用 3 折、每折 14 天的滚动回测，比较 Moving Average、Seasonal Naive 和 Croston；随后对生成代码执行：

- Python 语法检查
- 导入白名单检查
- `forecast(history, horizon)` 接口检查
- 删除 API Key 后的超时子进程运行检查

运行完整项目验收：

```bash
uv run python scripts/validate_project.py
```

或者分别运行：

```bash
uv run pytest --cov=inventory_agent --cov-report=term-missing
uv run ruff check inventory_agent tests scripts
```

## 9. 遇到的挑战和解决方案

- 原始 CSV 无表头：建立严格有序 schema，并在加载时验证 31/32 列。
- 多商品多仓：按 `item_id + store_code` 构造连续日序列，缺失日期按零需求补齐。
- 防止时间泄漏：采用滚动起点回测，每折只使用预测时点之前的数据。
- 间歇需求：注册 Croston，并由零需求比例驱动知识检索。
- 业务目标不同于纯精度：同时报告 WAPE、Bias 和非对称库存成本。
- 生成代码风险：限制导入和危险调用，在去除密钥的子进程中设置超时运行。
- API 不可用：Mock LLM 保证核心流程、测试和展示完全离线可运行。
- 成本字段方向尚未由原始文档确认：当前保留为 `cost_a/cost_b`，避免错误解释补多和补少成本。

## 10. 后续可扩展方向

- 确认成本字段方向后实现真实非对称竞赛损失函数。
- 加入浏览、收藏、加购等外生特征的 pooled Gradient Boosting 模型。
- 针对 37 个无历史商品实现类目和品牌相似商品冷启动迁移。
- 增加全国预测与五仓预测的层级一致性约束。
- 加入安全库存、在途库存和提前期，输出最终补货量。
- 增加 Streamlit 图谱和预测报告可视化。
- 将子进程执行升级为容器级资源和网络隔离沙箱。

## Git 与 GitHub

不需要先创建 GitHub 仓库。本地分支和提交可以独立工作。当前仓库的 `origin` 指向上游 TimeSeriesScientist，因此创建自己的空仓库后建议：

```bash
git remote rename origin upstream
git remote add origin https://github.com/YOUR_NAME/inventory-capability-factory.git
git push -u origin inventory-capability-factory:main
```

不要在 GitHub 页面初始化 README、License 或 `.gitignore`，否则首次推送可能产生无意义冲突。
