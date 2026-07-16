# 代码能力抽取、失败经验、版本管理与方案解释

本文说明项目对四项核心能力的实现边界和可运行入口。

## 1. 从真实代码仓库抽取能力

`CapabilityExtractor` 会递归扫描本地 Python 仓库，并忽略虚拟环境、缓存、测试、
构建目录和生成代码目录。当前能够抽取：

- `ForecastModel` 子类及其算法名称、构造参数和适用需求画像；
- 带文档字符串的公开函数；
- 函数签名、默认参数和返回类型说明；
- 函数直接和传递使用的第三方依赖；
- 同一模块中的内部函数调用关系；
- 代码行数、分支数、循环数和调用数等静态审查指标；
- 源文件、起止行号和 SHA-256 来源证据。

普通仓库函数会标记为 `review_required`，不会因为被抽取就自动进入预测回测。只有已
注册且满足统一预测接口的算法才会进入自动执行闭环。

```powershell
uv run python -m inventory_agent extract-capability `
  --source . `
  --output artifacts/extraction/repository_capabilities.json
```

Web 端可在“能力抽取与复刻”页面查看函数入口、外部依赖和内部调用。

## 2. 自动分析失败并形成经验

`FailureAnalyzer` 将失败归一化为稳定指纹，并输出：

- 失败类别和严重度；
- 可能发生的工作流阶段；
- 与具体路径、行号无关的规范化错误；
- 根因说明；
- 建议修复动作；
- 是否允许自动重试。

失败和修复策略分别沉淀为 `FailureCase` 与 `RepairStrategy` 节点。相同修复策略会
累计尝试次数、成功次数和成功率。后续出现同模型、同失败类别时，系统优先检索成功率
更高的历史策略，并将经验提供给 `RepairAgent`。

## 3. 算法能力版本管理

每个生成版本保存：

- 语义能力版本、规格哈希和源码哈希；
- 生成方式、来源和生成文件；
- 父版本、修复次数和验证配置；
- 最近验证指标、验证矩阵、验证次数和验证状态；
- `candidate / active / superseded / rejected` 生命周期。

CLI 支持：

```powershell
python -m inventory_agent versions list --model moving_average
python -m inventory_agent versions compare --model moving_average --left HASH1 --right HASH2
python -m inventory_agent versions promote --model moving_average --version HASH
python -m inventory_agent versions rollback --model moving_average --version HASH
```

版本比较会同时给出元数据差异、指标差值、验证矩阵和父版本血缘。Web 端“插件与
验证配置”页面提供版本列表、发布和回滚操作。

## 4. 自然语言解释设计依据

`PlanningAgent` 不再只输出候选名称，而会生成结构化 `design_basis` 和自然语言说明，
内容包括：

- 商品、仓库、周期和业务目标；
- 需求类型、样本长度、零需求比例和波动系数；
- 每个候选能力的说明、需求匹配情况和历史验证证据；
- 主指标、决胜指标和确定性排序规则；
- 代码发布门禁；
- 样本不足、间歇需求、波动和分布漂移风险。

这些依据会同时写入详细 trace、JSON/Markdown 验证报告，并在 Web 运行详情中展示。
