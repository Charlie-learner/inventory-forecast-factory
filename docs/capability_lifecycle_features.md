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
更高的历史策略，并将经验提供给 `RepairAgent`。每次运行还会生成独立的
`failure_experience.json`，便于不打开图谱也能核查根因、修复轮次和复用来源。

## 3. 算法能力版本管理

每个生成版本保存：

- 语义能力版本、规格哈希和源码哈希；
- 生成方式、来源和生成文件；
- 父版本、修复次数和验证配置；
- 自动分配的语义补丁版本和性能/资源基准；
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
最终解释进一步区分数据事实、系统推断和业务使用边界，并逐一说明其他候选未被采用的原因。

## 5. 性能优化与资源证据

生成代码在隔离子进程中执行可配置微基准，记录平均预测延迟、CPU 时间、吞吐量、
Python 内存峰值和静态复杂度。只有先通过正确性门禁的候选才能参与资源选优，避免用
“速度更快”掩盖结果错误。详细策略见
[`performance_and_runtime.md`](performance_and_runtime.md)。

## 6. 多智能体代码协作

代码阶段划分为架构设计、候选实现、独立审查、确定性验证和失败修复角色。API 模式下
架构、实现、审查分别发起独立调用，审查 Agent 可以给出完整修订源码，但是否发布仍由
本地安全、接口、运行、稳定性和等价性门禁裁决。每次运行保存实现蓝图、各候选策略、
源码哈希、审查问题、是否修订和验证结果，避免把一次 Prompt 的回答包装成“多智能体”。
完整协议和产物位置见
[`multi_agent_code_collaboration.md`](multi_agent_code_collaboration.md)。

Web 后台任务进度写入 `artifacts/jobs/`，已完成任务在服务重启后仍可读取；正在执行的
任务若遇服务重启会被明确标为失败，避免页面无限等待。
