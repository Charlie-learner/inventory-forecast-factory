# 库存预测能力验证报告

- 能力描述：为商品 1002 在仓库 1 预测未来14天目标库存，比较候选算法并展示失败修复
- 商品：1002
- 仓库：1
- 预测周期：14 天
- 任务类型：inventory_target
- 主验证指标：inventory_cost
- 需求类型：stable
- 历史状态：observed
- 选中模型：seasonal_naive
- 未来 14 天目标库存：184.00
- 成本 A（补少/缺货）：1.00
- 成本 B（补多/积压）：1.00
- 成本来源：unit_default
- 成本口径：horizon_total
- 能力抽取数量：5
- 能力来源扫描文件数：5
- 能力来源：examples\capabilities\seasonal_naive.md

## 候选模型验证

| 模型 | WAPE | sMAPE | Bias | 平均单折库存成本 |
|---|---:|---:|---:|---:|
| moving_average | 0.2081 | 0.2143 | -0.0000 | 0.00 |
| seasonal_naive | 0.0000 | 0.0000 | 0.0000 | 0.00 |
| croston | 0.2068 | 0.2131 | -0.1137 | 1.59 |

## 候选代码方案生成与比较

| 代码方案 | 回测选中 | 生成方式 | 代码验证 | 等价误差 | 文件 |
|---|---|---|---|---:|---|
| moving_average | False | spec_template | True | 0.0 | `examples\repair_run\20260716_165939_831375\candidate_solutions\moving_average\forecast_moving_average.py` |
| seasonal_naive | True | spec_template | True | 0.0 | `examples\repair_run\20260716_165939_831375\candidate_solutions\seasonal_naive\forecast_seasonal_naive.py` |
| croston | False | spec_template | True | 0.0 | `examples\repair_run\20260716_165939_831375\candidate_solutions\croston\forecast_croston.py` |

## 生成代码验证

- 生成方式：spec_template
- 能力规格哈希：4d4f5ff275bb7139
- 生成源码哈希：c8baa3ac039bcf62
- 语法、导入、接口、运行、稳定性检查：{'syntax': True, 'imports': True, 'interface': True, 'runtime': True, 'stability': True, 'equivalence': True}
- 与参考能力最大误差：0.0
- 等价性验证用例数：4
- 受限运行耗时：0.985 秒
- 修复次数：1
- 结构化失败记录数：1
- 复用历史修复经验数：0
- 详细中间过程：examples\repair_run\20260716_165939_831375\detailed_trace.md

## Agent 总结

[mock] 使用可复现规则完成需求理解、模型检索与验证。

## 使用边界

目标库存 T 是预测周期内非聚划算需求总量。实际下单量仍需结合现货、在途库存、提前期和安全库存。