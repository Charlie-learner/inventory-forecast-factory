# 库存业务数据契约

## 1. 表关系

```text
item_master.item_id
    ├── demand_history.item_id
    ├── inventory_snapshot.item_id
    └── replenishment_policy.item_id

warehouse_id
    ├── demand_history.store_code
    ├── inventory_snapshot.store_code
    └── replenishment_policy.store_code
```

所有业务日期使用 ISO `YYYY-MM-DD`，数量字段必须为有限非负数。需求历史主键为
`date + item_id + store_code`，库存快照和补货策略主键为 `item_id + store_code`。

## 2. 数据表

### demand_history.csv

| 字段 | 含义 |
|---|---|
| `date` | 业务日期 |
| `item_id` | 商品标识 |
| `store_code` | 仓库标识 |
| `qty_alipay_njhs` | 非聚划算需求量，兼容当前预测工作流 |
| `unit_price` | 销售价格 |
| `promotion_flag` | 促销标记 |
| `holiday_flag` | 节假日标记 |
| `stockout_flag` | 可能造成销量截断的缺货标记 |

### item_master.csv

记录商品类别、品牌、供应商、上市日期和模拟需求类型，用于层级分析与冷启动。

### inventory_snapshot.csv

记录现货、在途、欠单、提前期、安全库存、最小订货量、包装倍数和仓容。

### replenishment_policy.csv

记录缺货成本、单位持有成本、服务水平、复核周期和补货方式。

### demand_events.csv

记录促销、节假日、价格变化和新品上市等需求驱动事件。

## 3. 数据质量检查

- 主键不能重复；
- 外键必须能在商品主数据中找到；
- 数量、价格、成本、提前期必须非负；
- 服务水平必须位于 0 到 1；
- 促销和节假日标记必须为 0/1；
- 每个非冷启动序列至少包含 90 天历史；
- 缺货标记不能被直接解释为真实需求为零。

## 4. 数据来源

`examples/business_data/` 是确定性生成的合成业务数据，可自由随项目提交；它只借鉴供应链
数据实体和库存政策概念，不包含第三方原始记录。菜鸟真实数据仍按原始条款保存在本地，不随
Git仓库分发。

