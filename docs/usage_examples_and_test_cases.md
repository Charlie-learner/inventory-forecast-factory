# 使用示例与测试用例

本文面向三类读者：

- 业务用户：通过 Web 上传数据并用自然语言获得库存预测和补货建议；
- 开发人员：通过 CLI 验证能力抽取、代码复刻、算法比较和自动修复；
- 想了解完整流程的开发者：按照测试用例查看“能力抽取—能力复刻—能力验证与沉淀”闭环。

建议首次演示使用：

```dotenv
LLM_MODE=mock
```

Mock 模式不需要 API Key，结果可复现。需要展示真实 LLM 调用时，再按照
[`custom_llm.md`](custom_llm.md) 切换到 OpenAI 兼容接口。

## 一、Web 端快速演示

启动服务：

```powershell
uv run python -m inventory_agent web --open-browser
```

打开 `http://127.0.0.1:8000`，进入“完整能力工厂”，一次选择：

```text
data/config2.csv
data/item_feature2.csv
data/item_store_feature2.csv
```

页面应显示：

- 成本配置 5,778 行；
- 全国特征 210,549 行；
- 分仓特征 864,772 行；
- 963 个商品；
- 全国汇总和仓库 1-5。

上传完成后，可以点击 Web 页面中的示例卡片自动填入自然语言任务。

## 二、推荐自然语言示例

### 示例 1：单商品、单仓库业务预测

```text
预测商品 1013 在仓库 3 未来 14 天的需求，比较多个算法，
给出目标库存、进货/补货建议，并用业务语言解释选择依据。
```

预期：

- 创建 1 个完整工作流；
- 展示目标库存、日均需求、补货计算方式；
- 比较多个候选算法；
- 生成业务报告、技术验证报告、JSON 和 Trace。

### 示例 2：两个商品的全国汇总预测

```text
预测商品 132 和 1013 在仓库 all 未来 14 天的库存，
分别给出目标库存和补货建议。
```

预期：

- 识别两个商品，不只取第一个；
- 创建 2 个独立子任务；
- `all` 使用全国特征表；
- Web 汇总两个商品的结果，并保留两份独立报告。

### 示例 3：一个商品在所有仓库预测

```text
预测商品 1013 在所有仓库未来 7 天的库存，
比较各仓库需求差异并给出补货建议。
```

预期：

- “所有仓库”展开为仓库 1、2、3、4、5；
- 创建 5 个独立子任务；
- 展示每个仓库的目标库存和日均需求。

注意：“全国”或“仓库 all”表示全国汇总序列；“所有仓库”表示分别计算每个仓库。

### 示例 4：间歇需求商品

```text
预测商品 330 在仓库 5 未来 14 天的库存。
该商品需求较稀疏，请重点比较间歇需求算法，并说明缺货风险。
```

预期：

- 需求画像识别为间歇型；
- 候选方案包含 Croston 和可解释基线；
- 报告提示零需求比例较高，不能只根据最近一天决定长期备货。

### 示例 5：全零历史与数据质量诊断

```text
预测商品 330 在所有仓库未来 7 天的库存，
并解释为什么部分仓库结果可能为 0。
```

预期：

- 仓库 1-4 显示“历史销量全为 0”数据警告；
- 报告说明预测为 0 不等于未来一定没有需求；
- 不把 WAPE=0 或库存损失=0描述成高准确率；
- 建议检查未上架、断货或销量口径缺失。

### 示例 6：以预测精度为主要目标

```text
预测商品 1013 在仓库 4 未来 14 天的每日需求，
重点比较 WAPE 预测误差，并解释误差意味着什么。
```

预期：

- Agent 选择 `demand_forecast` 验证配置；
- 以预测误差指标排序候选方案；
- 业务报告仍使用通俗名称，技术报告保留原始指标。

### 示例 7：仓库内置最小演示数据

点击“使用演示数据”，然后输入：

```text
预测商品 3424 在仓库 1 未来 14 天的需求，
比较多个算法并给出目标库存和补货建议。
```

该示例适合不上传原始大文件时快速演示完整工作流。

### 示例 8：完整库存位置与补货约束

点击 Web 的“使用完整业务示例”，系统会选择 `examples/business_data/demand_history.csv`，并
自动读取同目录的库存快照和补货策略。示例任务：

```text
预测商品 1001 在仓库 1 未来 14 天的需求，比较多个算法，
并结合现货、在途、安全库存、最小订货量、包装倍数和仓容给出建议补货量。
```

预期：

- 使用 `replenishment_policy.csv` 中的缺货/积压成本；
- 显示目标库存、库存位置和生产目标库存；
- 应用安全库存、MOQ、包装倍数和仓容；
- 给出具体建议补货量和供应提前期提示；
- 不自动执行采购或调拨。

### 示例 9：联网行业研究增强

在 Web 高级设置勾选“联网检索 DOI 行业资料”，输入：

```text
为商品 1003 在仓库 1 预测未来14天间歇需求，
联网检索相关行业资料，比较算法并给出补货建议。
```

预期：

- Crossref 返回带 DOI/URL 的资料元数据；
- 生成 `online_knowledge_extraction.json`；
- 技术报告显示检索词、资料来源、相关度和分析风险；
- 研究建议影响候选优先级，但最终算法仍由本地滚动回测决定；
- 来源写入知识图谱并与受支持的算法建立关系；
- 网络失败时显示降级状态，核心工作流仍可完成。

## 三、CLI 核心能力演示

### 1. 环境诊断

```powershell
uv run python -m inventory_agent doctor
```

预期：显示 Python、依赖、LLM 模式和配置状态，但不打印 API Key。

API 模式下实际检查外部调用：

```powershell
uv run python -m inventory_agent doctor --live-llm
```

### 2. 完整自然语言工作流

```powershell
uv run python -m inventory_agent run `
  --description "为商品 1013 在仓库 3 预测未来14天目标库存，并给出补货建议" `
  --data data `
  --trace-level full `
  --execution-mode thorough `
  --keep-runs 10
```

预期产物：

```text
artifacts/runs/<时间戳>/
├── business_report.md
├── validation_report.md
├── validation_report.json
├── detailed_trace.md
├── detailed_trace.jsonl
├── run_manifest.json
├── performance_analysis.json
├── failure_experience.json
├── candidate_solutions/
├── generated/
└── generated_versions/
```

### 3. 从真实本地代码仓库抽取能力

```powershell
uv run python -m inventory_agent extract-capability `
  --source . `
  --output knowledge/extracted_capabilities.json `
  --knowledge knowledge/base_capability_graph.json
```

预期：

- 递归扫描 Python 文件；
- 抽取函数入口、参数、依赖、内部调用和来源哈希；
- 输出结构化 JSON；
- 更新 JSON、GraphML 和 HTML 知识图谱。

### 4. 独立复刻算法能力

```powershell
uv run python -m inventory_agent replicate-capability `
  --source examples/capabilities/moving_average.md `
  --output-dir artifacts/replication/generated `
  --manifest artifacts/replication/review_manifest.json `
  --candidates 3
```

预期：

- API 模式按不同策略生成最多 3 份独立可运行代码；
- Mock 模式生成一份确定性安全模板；
- 检查语法、导入安全、接口、运行、稳定性和数值等价性；
- 自动从验证通过的实现中选择最终版本；
- 生成 JSON/Markdown 审核清单。

### 5. 查看知识图谱

```powershell
uv run python -m inventory_agent visualize-graph `
  --knowledge artifacts/knowledge/capability_graph.json `
  --output artifacts/knowledge/capability_graph.html
```

预期：生成可搜索、筛选和点击节点的独立 HTML 图谱。

## 四、功能测试清单

| 编号 | 测试目标 | 操作 | 预期结果 |
|---|---|---|---|
| TC-01 | 环境可运行 | 执行 `doctor` | 不泄露密钥；依赖与配置状态明确 |
| TC-02 | 自动化测试 | `uv run pytest -q` | 全部测试通过 |
| TC-03 | 项目级自检 | `uv run python scripts/validate_project.py` | pytest、Ruff 和端到端工作流全部通过 |
| TC-04 | 单目标闭环 | 运行示例 1 | 产生候选比较、代码、验证、报告和图谱写回 |
| TC-05 | 多商品理解 | 运行示例 2 | 创建 2 个子任务，不遗漏第二个商品 |
| TC-06 | 所有仓库展开 | 运行示例 3 | 创建仓库 1-5 共 5 个子任务 |
| TC-07 | 数据异常解释 | 运行示例 5 | 全零历史显示警告，不误报为高准确率 |
| TC-08 | 多候选比较 | 查看技术报告 | 至少比较 3 个候选，并按验证配置选优 |
| TC-09 | 自动代码生成 | 查看 `candidate_solutions/` 和 `generated/` | 每个候选有独立代码，最终代码可运行 |
| TC-10 | 多轮修复 | 查看 `examples/repair_run/` | 能看到失败、根因、修复版本和重新验证通过 |
| TC-11 | 能力抽取 | 执行代码仓库抽取命令 | JSON 中包含入口、依赖、来源和哈希 |
| TC-12 | 能力复刻 | 执行独立复刻命令 | 生成代码和审核清单，验证矩阵完整 |
| TC-13 | 报告生成 | 查看 Web 报告 | 业务报告可直接阅读，技术报告可展开，Markdown 已渲染 |
| TC-14 | 知识沉淀 | 完成一次运行后刷新图谱 | 出现 ValidationRun、CapabilityVersion 等验证证据 |
| TC-15 | 版本管理 | Web“插件与配置”或 CLI `versions` | 能查看候选版本、发布/回滚事件和版本血缘 |
| TC-16 | 插件扩展 | 加载 `examples/plugins/stockout_priority.py:register` | 新指标/验证配置进入注册表且不修改核心流程 |
| TC-17 | 真实补货约束 | 运行示例 8 | 使用库存快照和策略表，输出约束后的具体建议补货量 |
| TC-18 | 多场景自动测试 | `uv run python scripts/run_acceptance_cases.py` | 六类业务样本、批量语义、复刻、修复、图谱和 API 检查全部通过 |
| TC-19 | 外部 LLM 实际调用 | `doctor --live-llm` | 返回预期标记、延迟和脱敏状态，不输出密钥 |
| TC-20 | 联网研究与搜索优化 | 运行示例 9 | 生成 DOI 知识抽取文件，证据进入规划、报告和图谱，断网可降级 |
| TC-21 | 后台进度与执行模式 | Web 分别选择 fast/balanced/thorough | 请求立即返回任务 ID，页面逐阶段更新，三种模式使用集中配置 |
| TC-22 | 性能与资源分析 | 查看 `performance_analysis.json` | 包含平均延迟、CPU、吞吐量、内存峰值、源码复杂度和优化建议 |
| TC-23 | 多智能体代码协作 | API 模式运行 1 个实现候选，或执行 `pytest tests/test_codegen.py -k multi_agent` | 依次出现架构、实现、审查三类独立调用；审查可修订错误返回类型；最终源码通过验证；协作 JSON 与蓝图均存在 |
| TC-24 | Web 任务状态持久化 | 完成 Web 任务后重启服务，再查询原任务 ID | 已完成状态和报告路径仍可读取；重启时未完成任务被明确标为失败而非无限等待 |

## 五、自动化测试分层

运行全部测试：

```powershell
uv run pytest -q
```

运行重点模块：

```powershell
uv run pytest tests/test_agents.py -q
uv run pytest tests/test_extraction.py tests/test_replication.py -q
uv run pytest tests/test_forecasting.py tests/test_validation_profiles.py -q
uv run pytest tests/test_repair.py tests/test_failures.py -q
uv run pytest tests/test_knowledge_graph.py -q
uv run pytest tests/test_web.py tests/test_workflow.py -q
uv run pytest tests/test_performance.py tests/test_versioning.py -q
uv run pytest tests/test_codegen.py -k multi_agent -q
```

测试覆盖关系：

| 测试文件 | 主要覆盖能力 |
|---|---|
| `test_agents.py` | 自然语言理解、需求画像和方案规划 |
| `test_extraction.py` | 文档、Python 和本地代码仓库能力抽取 |
| `test_replication.py` | 能力复刻、审核状态与数值等价 |
| `test_forecasting.py` | 预测算法、回测和库存成本 |
| `test_validation_profiles.py` | 不同任务类型的验证配置 |
| `test_repair.py` / `test_failures.py` | 失败分析、多轮修复和经验复用 |
| `test_knowledge_graph.py` | 图谱 schema、验证写回和版本事件 |
| `test_web.py` | 文件上传、字段映射、批量自然语言任务和 Web API |
| `test_workflow.py` | 完整 Agent 闭环、报告、Trace 和知识沉淀 |
| `test_acceptance_cases.py` | 六类需求样本、约束补货和跨组件运行结果 |
| `test_research.py` | Crossref 解析、证据排序、候选优化、图谱写入和断网降级 |

## 六、建议的查看顺序

1. 打开 Web“系统总览”，说明能力、指标、图谱和历史运行；
2. 上传三份菜鸟数据，展示自动识别和商品/仓库示例；
3. 运行示例 1，展示业务报告和补货建议；
4. 运行示例 2 或示例 3，展示自然语言批量任务；
5. 展开技术报告，展示候选算法比较和代码验证；
6. 打开“运行证据”，查看 Agent/工具调用时间线；
7. 打开 `examples/repair_run/`，展示验证失败后的自动修复；
8. 打开“知识图谱”，展示验证结果、失败案例、修复策略和能力版本；
9. 执行 `scripts/validate_project.py`，完成一次可复现的项目自检。

这个顺序可以比较完整地看到项目的主流程、工程结构、扩展功能和运行结果。
