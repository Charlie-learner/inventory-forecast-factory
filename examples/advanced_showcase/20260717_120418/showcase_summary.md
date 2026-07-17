# 高级能力场景验收结果

## 一句话结论

本会话完成 **3 个端到端任务**、比较算法、生成并验证代码，执行 **2 次自动修复**、复用 **5 条历史经验**，并把验证、失败、修复策略、版本和外部资料写回同一知识图谱。

## 老师建议先看什么

1. 先看下表，确认每个高级能力都有实际用例和数量结果。
2. 打开每个用例的业务报告，看非技术用户能否理解预测与补货结论。
3. 打开协作记录，核对架构、实现、审查、验证不是一次 Prompt 完成。
4. 打开详细 Trace，核对工具调用、候选比较、错误、修复和写回顺序。
5. 打开本会话图谱，核对 ValidationRun、FailureCase、RepairStrategy 和 CapabilityVersion 节点。

## 关键结果总览

- 会话：`20260717_120418`
- 图谱：38 个节点 / 73 条关系
- 联网行业资料：success / 5 条带来源记录
- 多智能体协议演示：3 个独立代码候选 / 审查 Agent 实际修订 1 份 / 选中 candidate_3 
- 外部 LLM 真实性说明：已真实发起外部 LLM 请求，但返回 APITimeoutError: Request timed out.，随后按设计降级为确定性方案。

> 协议演示使用确定性的 LLM 形状测试替身，以便离线复现多智能体协作；它不冒充外部模型调用。外部 API 的实际结果单独按上面的真实性说明记录。

| 用例 | 状态 | 联网研究 | 算法候选 | 代码候选 | 修复 | 经验复用 | 选中算法 |
|---|---|---|---:|---:|---:|---:|---|
| case_01_repair_deposition | passed | disabled | 3 | 1 | 1 | 2 | seasonal_naive |
| case_02_experience_reuse | passed | disabled | 3 | 1 | 1 | 3 | seasonal_naive |
| case_04_live_research_multi_agent | passed | success | 3 | 1 | 0 | 0 | croston |

## 每个用例做了什么

### case_01_repair_deposition

**任务目的：** 周季节商品的候选算法比较、代码验证、接口故障注入、自动修复，并把失败指纹、修复策略和能力版本写回知识图谱。

**系统做了什么：** 比较 3 个候选算法；检测到代码接口不符合统一契约，自动分类、生成失败指纹、修复并重新验证。本次从图谱检索并复用了 2 条成功修复经验。

**结果怎么理解：** 最终采用 `seasonal_naive`，未来周期目标库存为 **184.0**。这里的采用结果来自历史滚动回测和业务成本指标，不是语言模型主观指定。

- 候选比较：seasonal_naive（库存损失 0，误差比例 0.00%）；croston（库存损失 5.573，误差比例 20.68%）；last_value（库存损失 39，误差比例 22.83%）
- 代码实现候选：1 份
- 自动修复：1 次
- 历史经验复用：2 条
- 运行目录：`examples/advanced_showcase/20260717_120418/runs/case_01_repair_deposition/20260717_122847_488830`
- 技术报告：`examples/advanced_showcase/20260717_120418/runs/case_01_repair_deposition/20260717_122847_488830/validation_report.md`
- 协作记录：`examples/advanced_showcase/20260717_120418/runs/case_01_repair_deposition/20260717_122847_488830/generated/multi_agent_collaboration.json`
- 详细 Trace：`examples/advanced_showcase/20260717_120418/runs/case_01_repair_deposition/20260717_122847_488830/detailed_trace.md`

### case_02_experience_reuse

**任务目的：** 再次触发同类接口失败，验证 RepairAgent 能从共享知识图谱检索上一用例的成功修复经验，并在修复后生成新的版本化验证记录。

**系统做了什么：** 比较 3 个候选算法；检测到代码接口不符合统一契约，自动分类、生成失败指纹、修复并重新验证。本次从图谱检索并复用了 3 条成功修复经验。

**结果怎么理解：** 最终采用 `seasonal_naive`，未来周期目标库存为 **184.0**。这里的采用结果来自历史滚动回测和业务成本指标，不是语言模型主观指定。

- 候选比较：seasonal_naive（库存损失 0，误差比例 0.00%）；croston（库存损失 5.573，误差比例 20.68%）；last_value（库存损失 39，误差比例 22.83%）
- 代码实现候选：1 份
- 自动修复：1 次
- 历史经验复用：3 条
- 运行目录：`examples/advanced_showcase/20260717_120418/runs/case_02_experience_reuse/20260717_122852_377525`
- 技术报告：`examples/advanced_showcase/20260717_120418/runs/case_02_experience_reuse/20260717_122852_377525/validation_report.md`
- 协作记录：`examples/advanced_showcase/20260717_120418/runs/case_02_experience_reuse/20260717_122852_377525/generated/multi_agent_collaboration.json`
- 详细 Trace：`examples/advanced_showcase/20260717_120418/runs/case_02_experience_reuse/20260717_122852_377525/detailed_trace.md`

### case_04_live_research_multi_agent

**任务目的：** 高间歇需求场景中实际调用 Crossref 联网检索和外部 LLM；执行架构、多实现、独立审查、统一验证、资源比较、业务补货和知识图谱沉淀。

**系统做了什么：** 比较 3 个候选算法；生成代码一次通过统一门禁，本次无需修复。本次没有可复用的历史经验，产生的新经验会写回图谱供后续使用。

**结果怎么理解：** 最终采用 `croston`，未来周期目标库存为 **124.41663889376699**。这里的采用结果来自历史滚动回测和业务成本指标，不是语言模型主观指定。

- 候选比较：croston（库存损失 40.11，误差比例 169.08%）；moving_average（库存损失 43.5，误差比例 169.67%）；seasonal_naive（库存损失 149.4，误差比例 215.06%）
- 代码实现候选：1 份
- 自动修复：0 次
- 历史经验复用：0 条
- 运行目录：`examples/advanced_showcase/20260717_120418/runs/case_04_live_research_multi_agent/20260717_121335_461921`
- 技术报告：`examples/advanced_showcase/20260717_120418/runs/case_04_live_research_multi_agent/20260717_121335_461921/validation_report.md`
- 协作记录：`examples/advanced_showcase/20260717_120418/runs/case_04_live_research_multi_agent/20260717_121335_461921/generated/multi_agent_collaboration.json`
- 详细 Trace：`examples/advanced_showcase/20260717_120418/runs/case_04_live_research_multi_agent/20260717_121335_461921/detailed_trace.md`

## 沉淀到知识图谱的结果

| 节点类型 | 数量 | 对评审者的含义 |
|---|---:|---|
| Algorithm | 5 | 可复用算法能力 |
| CapabilityVersion | 2 | 经过验证的代码版本 |
| DemandProfile | 8 | 算法适用的需求画像 |
| FailureCase | 1 | 归一化失败案例 |
| Metric | 5 | 统一评价口径 |
| RepairStrategy | 2 | 可复用修复策略 |
| SourceArtifact | 10 | 可追溯资料或源码 |
| ValidationRun | 5 | 一次真实验证记录 |

- 图谱 JSON：`examples/advanced_showcase/20260717_120418/capability_graph.json`
- 图谱 GraphML：`examples/advanced_showcase/20260717_120418/capability_graph.graphml`
- 交互可视化：`examples/advanced_showcase/20260717_120418/capability_graph.html`
- 联网知识抽取：`examples/advanced_showcase/20260717_120418/online_knowledge_extraction.json`

## 结论可信度与边界

- 所有预测选择均由历史时间序列回测和验证配置决定，不由 LLM 直接拍板。
- Mock、协议测试替身、真实外部 LLM 和联网研究在证据中分别标记，不混为一谈。
- AST 白名单、临时目录和子进程超时属于应用级安全门禁，不宣称为容器级强隔离。
- 行业资料用于增强规划与解释，不能绕过代码门禁和指标验证。

