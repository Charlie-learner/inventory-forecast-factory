# 插件示例

`stockout_priority.py` 演示如何在不修改核心包的情况下注册：

- 自定义指标 `underforecast_rate`；
- 自定义验证任务 `stockout_priority`；
- 该任务专门优先降低缺货，再使用库存成本和 WAPE 决胜。

插件会执行普通 Python 代码，只应加载经过审核的本地文件：

```bash
python -m inventory_agent plugins \
  --plugin examples/plugins/stockout_priority.py:register

python -m inventory_agent benchmark \
  --data examples/data/cainiao_demo.csv \
  --item 3424 \
  --store 1 \
  --task-type stockout_priority \
  --plugin examples/plugins/stockout_priority.py:register
```
