# 库存预测能力验证报告

- 任务：为高间歇需求商品1003在仓库2预测未来21天目标库存。请联网检索间歇需求预测与库存控制资料，比较 Croston、移动平均和最近值等方案；由多智能体自动生成并审查多个独立代码实现，执行安全、等价性、性能和库存成本评估，最后结合库存快照给出补货建议和设计依据。
- 商品 / 仓库：1003 / 2
- 预测周期：21 天
- 任务类型：intermittent_demand
- 需求画像：intermittent，零需求比例 80.00%
- 选中模型：croston
- 目标库存：124.42
- 主验证指标：mae
- 决胜指标：inventory_cost, wape
- 缺货 / 积压成本：3.50 / 3.00
- 能力来源扫描文件数：5

## 方案设计依据

该任务要求为商品 1003 在仓库 2 预测未来 21 天，并以 mae 为主要目标。历史序列被识别为 intermittent，共有 180 个观测，零需求比例为 80.00%。因此先从知识图谱检索与该需求画像匹配的能力，再保留可解释基线，形成 croston, moving_average, seasonal_naive 三类候选。最终不由语言模型主观决定，而是使用 mae 及决胜指标执行无时间泄漏滚动回测；生成代码还必须通过安全、接口、稳定性和参考行为等价验证后才允许沉淀为新版本。联网研究从 crossref 检索到 5 条可追溯资料，其建议只用于调整候选优先级，不替代本地回测。

| 候选能力 | 能力说明 | 历史验证证据 |
|---|---|---|
| croston | Estimate non-zero demand size and the interval between demands separately. | 暂无历史验证，作为待比较候选 |
| moving_average | Forecast stable demand with the mean of the most recent observations. | 暂无历史验证，作为待比较候选 |
| seasonal_naive | Repeat the latest weekly pattern over the forecast horizon. | 已有 2 次历史验证，成功率 100%，历史平均库存成本 0.00 |

- 选择规则：按 mae 排序，使用验证配置中的 tie-breakers 决胜；模型名仅用于完全相同时的确定性排序。
- 发布门禁：语法、导入安全、统一接口、受限运行、确定性、边界输入和数值等价。
- 主要风险：零需求比例较高，普通均值模型可能持续高估需求。

## 联网行业研究与知识抽取

- 状态：success
- 提供方：crossref
- 查询：intermittent demand Croston spare parts algorithm validation
- 分析方式：llm_evidence_analysis
- 抽取文件：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_120418\runs\case_04_live_research_multi_agent\20260717_121335_461921\online_knowledge_extraction.json
- 使用原则：外部资料只影响候选优先级和实现上下文，最终结果由本地回测与代码门禁裁决。

| 在线资料 | DOI / URL | 相关度 |
|---|---|---:|
| Intermittent demand forecasting for spare parts: A Critical review | 10.1016/j.omega.2021.102513 | 0.780 |
| Intermittent demand forecasting for aircraft inventories: a study of Brazilian’s Boeing 737NG aircraft´s spare parts management | 10.14295/transportes.v27i2.1600 | 0.714 |
| Forecasting Intermittent Demand for Spare Parts | 10.5120/13154-0805 | 0.661 |
| A Data Mining Approach for Intermittent Demand Forecasting of Aircraft Spare Parts － Focusing on the E-737(AEW&C: Airborne Early Warning & Control) Spare Parts － | 10.30529/amsok.2018.16.4.008 | 0.606 |
| Cost-Aligned Deep Learning for Intermittent Spare-Parts Demand and Inventory | 10.2139/ssrn.5554492 | 0.286 |

## 候选模型自动比较

| 模型 | WAPE | sMAPE | Bias | MAE | 库存成本 |
|---|---:|---:|---:|---:|---:|
| croston | 1.6908 | 1.8659 | 0.6367 | 9.3375 | 40.11 |
| moving_average | 1.6967 | 1.8649 | 0.6905 | 9.3707 | 43.50 |
| seasonal_naive | 2.1506 | 0.8095 | 0.7976 | 11.8452 | 149.38 |

## 候选代码生成与验证

| 代码方案 | 回测选中 | 生成方式 | 验证通过 | 等价误差 |
|---|---|---|---|---:|
| croston | True | spec_template | True | 0.00000000 |
| moving_average | False | spec_template | True | 0.00000000 |
| seasonal_naive | False | spec_template | True | 0.00000000 |

## 同一能力的多实现代码候选

API 模式会根据不同实现策略生成多份独立源码，逐份通过安全、接口、稳定性和参考行为验证，再从合格实现中选择运行耗时更低且代码更精简的版本。Mock 模式为保持完全可复现，只生成一份安全模板实现。

| 实现候选 | 生成策略 | 生成方式 | 自动验证 | 运行耗时 | 结果 |
|---|---|---|---|---:|---|
| candidate_1 | specification_fidelity: 优先忠实实现能力规格中的数学语义、参数和边界条件，保持实现直接且可审计。 | spec_template_fallback | 通过 | 1.0229 | 选中 |

## 多智能体代码协作证据

本次代码不是由单次提示直接决定，而是经过相互独立的设计、实现、审查和验证角色。

- 协作协议：architecture -> parallel implementation -> independent review -> validation
- 参与角色：CodeArchitectureAgent, CodeImplementationAgent, CodeReviewAgent, GeneratedCodeValidator
- 架构设计方式：deterministic
- 实现策略：specification_fidelity: 优先忠实实现能力规格中的数学语义、参数和边界条件，保持实现直接且可审计。
- 独立审查方式：deterministic
- 审查结论：通过
- 审查修订代码：否
- 审查发现：未发现问题
- 完整协作记录：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_120418\runs\case_04_live_research_multi_agent\20260717_121335_461921\generated\multi_agent_collaboration.json
- 实现蓝图：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_120418\runs\case_04_live_research_multi_agent\20260717_121335_461921\generated\implementation_blueprint.json

## 失败分析与多轮修复

| 轮次 | 失败根因 | 建议动作 | 修复策略 |
|---:|---|---|---|
| 0 | 首次验证通过 | - | 无需修复 |

- 复用历史修复经验：0 条

## 性能与资源消耗分析

- 微基准迭代次数：20
- 单次预测平均延迟：0.8815 ms
- 吞吐量：1134.43 次/秒
- Python 分配内存峰值：28.08 KB
- 源码规模：53 行 / 3270 字节
- 优化建议：当前基准未触发资源告警；继续保留回归基准，避免无证据的过早优化。
- 说明：该微基准用于候选间相对比较，不能替代生产环境压测。

## 插件与验证配置

| 插件 | 新增指标 | 新增验证配置 |
|---|---|---|
| 内置注册表 | 无外部插件 | 无外部插件 |

## 最终代码与版本证据

- 自动分配语义版本：1.1.0
- 父版本：-
- 生成方式：spec_template_fallback
- 能力规格哈希：d356dc7116b42628
- 生成源码哈希：1c96601ed98f337a
- 验证矩阵：{'syntax': True, 'imports': True, 'interface': True, 'runtime': True, 'stability': True, 'equivalence': True}
- 等价性用例数：4
- 受限运行耗时：1.023 秒
- 详细中间过程：F:\AgentProjects\TimeSeriesScientist\examples\advanced_showcase\20260717_120418\runs\case_04_live_research_multi_agent\20260717_121335_461921\detailed_trace.md

## Agent 总结

[api] 【数据事实】商品1003、仓库2共有180期历史记录，其中36期有需求，零需求占80%，需求波动系数为2.01，属于高波动的间歇需求；趋势强度接近0，未显示明显趋势。系统以未来21天MAE为主指标进行无时间泄漏滚动回测。Croston的MAE为9.3375，略优于移动平均的9.3707，明显优于季节性最近值法的11.8452；对应库存成本分别为40.1150、43.5000和149.3750。因此选中Croston。移动平均未选是因为MAE高0.0333且库存成本更高；季节性最近值法未选是因为MAE高2.5078、RMSE和库存成本也明显较高。Crossref检索到5条可追溯资料，资料仅用于提高Croston和移动平均的候选优先级，最终选择仍以本地回测为准。
【系统推断】Croston分别估计非零需求量和需求间隔，更贴合大量零需求的序列特征。虽然其综合结果最佳，但与移动平均的MAE差距仅0.0333，优势很小，模型选择存在一定不确定性。高零需求和高波动意味着未来21天实际需求可能与目标值偏差较大；促销、历史断货、供应变化等信息未提供，不能据此调整预测。季节性最近值法虽有既往验证记录，但在本次相同数据与周期的回测中表现较差，故未采用。
【性能与实现】性能测试20次，平均单次延迟约0.88毫秒，CPU时间15.63毫秒，峰值内存约28.08KB，吞吐约1134次/秒，计算资源消耗较低。方案规定代码需经过语法、导入安全、统一接口、受限运行、确定性、边界输入和数值等价检查；已提供信息仅显示修复次数为0，未提供各项审查的独立结果，因此不能进一步断言所有审查均已通过。
【目标库存与业务建议】系统给出的未来21天目标库存为124.42个单位，这是库存目标而非直接补货量。建议先按包装规格和企业取整规则确定可执行目标，再用“建议补货量=max(0，目标库存－当前库存位置)”计算；库存位置通常应结合可用库存、在途订单及已承诺未发数量。当前请求未提供库存快照、在途量、欠单、包装规格和供应提前期，因此无法给出有证据支持的具体补货数量。执行前应人工核对这些数据；若业务要求整数且无其他规则，可将124.42作为约124至125单位的规划参考，而不应直接视为必须采购125单位。

## 使用边界

目标库存 T 是预测周期内非聚划算需求总量。实际补货量仍需结合现货、在途库存、供应提前期、安全库存和服务水平约束。