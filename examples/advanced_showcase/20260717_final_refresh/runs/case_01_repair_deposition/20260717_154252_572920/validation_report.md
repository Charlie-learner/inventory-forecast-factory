# 库存预测能力验证报告

- 任务：为商品1002在仓库1预测未来14天目标库存，比较至少三种算法，结合现货、在途、欠单和补货约束给出建议，并保存完整验证证据。
- 商品 / 仓库：1002 / 1
- 预测周期：14 天
- 任务类型：inventory_target
- 需求画像：weekly_seasonal，零需求比例 0.00%
- 选中模型：seasonal_naive
- 目标库存：184.00
- 主验证指标：inventory_cost
- 决胜指标：wape, rmse
- 缺货 / 积压成本：3.50 / 1.50
- 能力来源扫描文件数：5

## 方案设计依据

该任务要求为商品 1002 在仓库 1 预测未来 14 天，并以 inventory_cost 为主要目标。历史序列被识别为 weekly_seasonal，共有 180 个观测，零需求比例为 0.00%。因此先从知识图谱检索与该需求画像匹配的能力，再保留可解释基线，形成 seasonal_naive, croston, last_value 三类候选。最终不由语言模型主观决定，而是使用 inventory_cost 及决胜指标执行无时间泄漏滚动回测；生成代码还必须通过安全、接口、稳定性和参考行为等价验证后才允许沉淀为新版本。

| 候选能力 | 能力说明 | 历史验证证据 |
|---|---|---|
| seasonal_naive | Repeat the latest weekly pattern over the forecast horizon. | 暂无历史验证，作为待比较候选 |
| croston | Estimate non-zero demand size and the interval between demands separately. | 暂无历史验证，作为待比较候选 |
| last_value | Repeat the latest observed demand as a transparent baseline. | 暂无历史验证，作为待比较候选 |

- 选择规则：按 inventory_cost 排序，使用验证配置中的 tie-breakers 决胜；模型名仅用于完全相同时的确定性排序。
- 发布门禁：语法、导入安全、统一接口、受限运行、确定性、边界输入和数值等价。
- 主要风险：周周期较明显，节假日或促销变化可能破坏历史周期。

## 联网行业研究与知识抽取

- 状态：disabled
- 提供方：crossref
- 查询：-
- 分析方式：-
- 抽取文件：-
- 使用原则：外部资料只影响候选优先级和实现上下文，最终结果由本地回测与代码门禁裁决。

| 在线资料 | DOI / URL | 相关度 |
|---|---|---:|
| 未启用或未检索到资料 | - | - |

## 候选模型自动比较

| 模型 | WAPE | sMAPE | Bias | MAE | 库存成本 |
|---|---:|---:|---:|---:|---:|
| seasonal_naive | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00 |
| croston | 0.2068 | 0.2131 | -0.1137 | 2.7184 | 5.57 |
| last_value | 0.2283 | 0.2314 | 1.8571 | 3.0000 | 39.00 |

## 候选代码生成与验证

| 代码方案 | 回测选中 | 生成方式 | 验证通过 | 等价误差 |
|---|---|---|---|---:|
| seasonal_naive | True | spec_template | True | 0.00000000 |
| croston | False | spec_template | True | 0.00000000 |
| last_value | False | spec_template | True | 0.00000000 |

## 同一能力的多实现代码候选

API 模式会根据不同实现策略生成多份独立源码，逐份通过安全、接口、稳定性和参考行为验证，再从合格实现中选择运行耗时更低且代码更精简的版本。Mock 模式为保持完全可复现，只生成一份安全模板实现。

| 实现候选 | 生成策略 | 生成方式 | 自动验证 | 运行耗时 | 结果 |
|---|---|---|---|---:|---|
| primary | specification_fidelity | spec_template | 通过 | 1.0291 | 选中 |

## 多智能体代码协作证据

本次代码不是由单次提示直接决定，而是经过相互独立的设计、实现、审查和验证角色。

- 协作协议：architecture -> parallel implementation -> independent review -> validation
- 参与角色：CodeArchitectureAgent, CodeImplementationAgent, CodeReviewAgent, GeneratedCodeValidator
- 架构设计方式：-
- 实现策略：-
- 独立审查方式：-
- 审查结论：需要验证门禁裁决
- 审查修订代码：否
- 审查发现：未发现问题
- 完整协作记录：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_final_refresh\runs\case_01_repair_deposition\20260717_154252_572920\generated\multi_agent_collaboration.json
- 实现蓝图：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_final_refresh\runs\case_01_repair_deposition\20260717_154252_572920\generated\implementation_blueprint.json

## 失败分析与多轮修复

| 轮次 | 失败根因 | 建议动作 | 修复策略 |
|---:|---|---|---|
| 1 | 生成模块未满足 forecast/build_inventory_target 统一接口契约。 | 按接口签名重新生成 / 补齐返回字段 / 运行契约测试 | 第 1 轮修复（受约束安全模板回退；错误类型=interface；根因=生成模块未满足 forecast/build_inventory_target 统一接口契约。；建议动作=按接口签名重新生成 / 补齐返回字段 / 运行契约测试）：interface: forecast returned ndarray instead of required list[float] [failure_fingerprint=0b494e8f4d0bcb6f] |

- 复用历史修复经验：0 条

## 性能与资源消耗分析

- 微基准迭代次数：20
- 单次预测平均延迟：0.7063 ms
- 吞吐量：1415.77 次/秒
- Python 分配内存峰值：26.04 KB
- 源码规模：40 行 / 2769 字节
- 优化建议：当前基准未触发资源告警；继续保留回归基准，避免无证据的过早优化。
- 说明：该微基准用于候选间相对比较，不能替代生产环境压测。

## 插件与验证配置

| 插件 | 新增指标 | 新增验证配置 |
|---|---|---|
| 内置注册表 | 无外部插件 | 无外部插件 |

## 最终代码与版本证据

- 自动分配语义版本：1.1.0
- 父版本：-
- 生成方式：spec_template
- 能力规格哈希：9d907c2f2b036644
- 生成源码哈希：6c2d6284158f5a5d
- 验证矩阵：{'syntax': True, 'imports': True, 'interface': True, 'runtime': True, 'stability': True, 'equivalence': True}
- 等价性用例数：4
- 受限运行耗时：1.029 秒
- 详细中间过程：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_final_refresh\runs\case_01_repair_deposition\20260717_154252_572920\detailed_trace.md

## Agent 总结

[mock] 使用可复现规则完成需求理解、模型检索与验证。

## 使用边界

目标库存 T 是预测周期内非聚划算需求总量。实际补货量仍需结合现货、在途库存、供应提前期、安全库存和服务水平约束。