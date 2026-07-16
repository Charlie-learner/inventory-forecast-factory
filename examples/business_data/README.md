# 多商品多仓库存业务示例

本目录是可随Git仓库分发的确定性合成数据，不包含天池原始记录。它用于展示比单商品演示文件
更完整的库存业务数据关系，并覆盖稳定、周期、间歇、趋势、波动和冷启动需求。

运行生成器：

```bash
python scripts/generate_business_demo.py
```

文件：

- `demand_history.csv`：6个商品 × 3个仓库 × 最多180天；
- `item_master.csv`：商品层级、供应商、上市时间和需求类型；
- `inventory_snapshot.csv`：现货、在途、欠单、提前期和订货约束；
- `replenishment_policy.csv`：缺货成本、持有成本和服务水平；
- `demand_events.csv`：促销、节假日、价格和新品事件；
- `source_metadata.json`：来源、许可和生成方法。

当前预测工作流可以直接读取 `demand_history.csv`，因为它保留了
`date/item_id/store_code/qty_alipay_njhs` 四个兼容字段。其他表用于说明生产化库存决策还需
哪些业务输入。

