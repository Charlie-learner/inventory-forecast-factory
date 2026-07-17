# 系统架构、模块设计与 Agent 工作流图

三张图采用黑白手绘、圆角框、节点箭头和虚线关系风格，SVG 可直接用浏览器打开，也可插入 Markdown、Word 或答辩 PPT。文字与连接关系来自当前项目代码，而不是通用 Agent 模板。

## 1. 系统架构图

![库存算法能力工厂系统架构](diagrams/system_architecture.svg)

该图从外到内展示用户入口、能力工厂核心、库存预测行业适配层、外部 LLM/研究能力以及最终代码、报告和图谱输出。

## 2. 模块设计图

![库存算法能力工厂模块设计](diagrams/module_design.svg)

模块依赖自上而下：Web/CLI 负责接口适配，`workflow` 负责流程编排，Agent 和应用服务负责业务协作，领域模块负责数据、算法、验证与图谱。跨模块通过 `CapabilitySpec`、预测接口、验证配置、运行策略和失败证据契约交互。

## 3. Agent 完整工作流图

![LangGraph Agent 完整工作流](diagrams/agent_workflow.svg)

## 是否使用 LangGraph？

**是。** 项目在 `inventory_agent/workflow/factory.py` 的 `InventoryCapabilityWorkflow._build_graph()` 中使用：

```python
workflow = StateGraph(dict)
```

实际主链为：

```text
START
  → parse
  → extract
  → profile
  → research
  → plan
  → benchmark
  → generate
  → validate
```

`validate` 使用 `add_conditional_edges()` 分流：

- 验证通过：进入 `report`，生成业务报告、技术报告、Trace，并回写知识图谱后结束；
- 可以修复：进入 `repair`，随后重新回到 `validate`；
- 修复预算耗尽：进入 `failed`，保存失败分析和沉淀证据。

其中 `generate` 节点不是单次 Prompt 调用，而是一层具有角色分工、共享制品和反馈回环的代码多智能体协议：

```text
CodeArchitectureAgent
  → 多个 CodeImplementationAgent
  → CodeReviewAgent
  → GeneratedCodeValidator
  → 正确候选的性能/资源比较与选优
```

各角色通过结构化制品协作：架构 Agent 产生实现规格，多个实现 Agent 使用不同策略并行生成候选，各候选再接受独立并行审查和验证，最后按照正确性、业务指标、性能与资源证据汇聚排名；审查或验证失败会触发定向再生成。外层 `RepairAgent` 再结合失败根因和历史经验执行跨轮修复，最终由 `ExperienceAgent` 与 `ReportAgent` 完成经验、版本、报告和知识图谱沉淀。该并行过程由 `ThreadPoolExecutor` 和运行档位中的 worker 数量进行有界控制，并不是图示层面的伪并行。

图中的双向箭头表示状态交互边界：LangGraph 将当前共享状态交给节点，节点调用 Tool/Store 后获得 `ToolResult`，再由节点把结果整理为 state patch 返回给 LangGraph；Tool 不会绕过 Agent 直接修改全局状态。类似地，`generate` 节点把任务规格交给代码协作团队，并接收候选代码、审查结论与验证证据组成的 generated state。

因此该项目不是“单个 Prompt 顺序调用几个函数”，而是 **LangGraph 业务状态图 + 代码阶段多智能体协作 + 验证失败条件回环** 的组合编排。
