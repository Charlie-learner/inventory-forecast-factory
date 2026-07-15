# 库存预测能力验证报告

- 能力描述：为商品 3424 在仓库 1 预测未来14天需求，比较多个算法并优先降低补多补少成本
- 商品：3424
- 仓库：1
- 预测周期：14 天
- 任务类型：inventory_target
- 主验证指标：inventory_cost
- 需求类型：volatile
- 历史状态：observed
- 选中模型：last_value
- 未来 14 天目标库存：308.00
- 成本 A（补少/缺货）：6.48
- 成本 B（补多/积压）：11.00
- 成本来源：config2.csv
- 成本口径：horizon_total

## 候选模型验证

| 模型 | WAPE | sMAPE | Bias | 平均单折库存成本 |
|---|---:|---:|---:|---:|
| ridge_lag | 1.1913 | 0.7267 | 6.9491 | 1523.93 |
| last_value | 0.6247 | 0.7039 | -6.9048 | 626.40 |
| croston | 0.9580 | 0.6585 | 3.3700 | 1426.80 |

## 生成代码验证

- 生成方式：constrained_template
- 语法、导入、接口、运行、稳定性检查：{'syntax': True, 'imports': True, 'interface': True, 'runtime': True, 'stability': True}
- 受限运行耗时：0.948 秒
- 修复次数：0

## Agent 总结

{"mode": "mock", "summary": "使用可复现规则完成需求理解、模型检索与验证。", "input_excerpt": "{\"run_id\": \"run:5d00f4da4b54\", \"created_at\": \"2026-07-15T14:46:52.074291+00:00\", \"request\": {\"description\": \"为商品 3424 在仓"}

## 使用边界

目标库存 T 是预测周期内非聚划算需求总量。实际下单量仍需结合现货、在途库存、提前期和安全库存。