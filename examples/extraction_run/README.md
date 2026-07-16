# 外部能力抽取到业务验证示例

本目录展示外部 `moving_average.md` 被抽取、摄取知识图谱并进入候选规划后的完整业务运行。

需要区分两个结论：

- “抽取成功”表示系统成功得到带来源的 `CapabilitySpec`；
- “最终选中”必须由当前商品、仓库、验证窗口和库存成本决定，不保证来源算法一定获胜。

进入时间戳目录后查看 `extracted_capabilities.json`、`detailed_trace.md`、
`candidate_solutions/` 和 `validation_report.md`。如果只想验证指定能力是否能被独立复刻，
请查看 `examples/replication_run/`。

