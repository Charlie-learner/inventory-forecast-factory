# 目标库存与补货策略

## 1. 概念区分

```text
forecast_demand = 预测周期需求
project_target_inventory = forecast_demand
production_target_inventory = project_target_inventory + safety_stock
inventory_position = on_hand + on_order - backorder
recommended_order_qty = max(production_target_inventory - inventory_position, 0)
```

能力工厂的 `target_inventory` 等于预测周期需求总量，不直接把安全库存混入预测值。当需求文件旁
存在 `inventory_snapshot.csv` 时，决策层会进一步计算 `inventory_position`、生产目标库存和
建议补货量；结果只作为建议，不自动执行采购或调拨。

## 2. 约束后的建议补货量

当前原型自动应用以下规则：

1. 小于最小订货量 `min_order_qty` 时提升到最小订货量；
2. 按包装倍数 `pack_size` 向上取整；
3. 不得超过仓库剩余容量；
4. 输出供应提前期和仓容限制提示。

仍需由外部业务系统或人工处理：

- 供应商可供量和预算；
- 采购日历、运输时效分布；
- 促销、新品、断货和异常事件复核；
- 跨仓调拨成本与执行审批。

## 3. 成本口径

菜鸟示例场景使用：

```text
C = A * max(D - T, 0) + B * max(T - D, 0)
```

- `A`：库存不足时的单位缺货成本；
- `B`：库存过多时的单位积压成本；
- `D`：未来预测周期实际需求总量；
- `T`：同一周期目标库存。

当 `A > B` 时，业务更厌恶缺货，目标库存应偏向较高分位；当 `B > A` 时，应更重视积压风险。
项目已经使用 `A/(A+B)` 记录临界分位，但尚未把它扩展为完整的概率预测库存优化器。

## 4. 生产化边界

当前项目不包含供应商产能、采购日历、运输时效分布、跨仓调拨成本、保质期和多级库存网络。
这些约束应在预测能力之后由补货优化或供应计划模块处理。
