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

当前工作流直接读取 `demand_history.csv`；如果同目录存在 `inventory_snapshot.csv` 和
`replenishment_policy.csv`，会自动使用真实库存位置、订货约束和缺货/积压成本计算建议补货量。
商品主数据与需求事件用于解释生产化还需补充的层级、促销、新品和断货信息。
