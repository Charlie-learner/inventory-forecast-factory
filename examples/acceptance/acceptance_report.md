# 多场景自动验收报告

- 模式：确定性 Mock，不依赖外部 API；
- 需求画像与库存案例：6 个；
- 跨组件案例：4 个；
- 总结：全部通过。

## 六类库存需求与补货结果

| 商品 | 预设需求类型 | 检测画像 | 选中算法 | 目标库存 | 建议补货 | 库存成本 |
|---:|---|---|---|---:|---:|---:|
| 1001 | stable | stable | ridge_lag | 190.33 | 144.00 | 9.19 |
| 1002 | weekly_seasonal | weekly_seasonal | seasonal_naive | 184.00 | 138.00 | 0.00 |
| 1003 | intermittent | intermittent | ridge_lag | 115.01 | 72.00 | 0.27 |
| 1004 | trend | trend | ridge_lag | 496.80 | 450.00 | 1.26 |
| 1005 | volatile | volatile | ridge_lag | 237.16 | 192.00 | 15.10 |
| 1006 | cold_start | intermittent | last_value | 280.00 | 234.00 | 192.00 |

## 自然语言批量范围

- 多商品：`[[1001, '1'], [1003, '1']]`
- 所有仓库：`[[1003, '1'], [1003, '2'], [1003, '3']]`

## 核心闭环验收

| 验收项 | 结果 | 证据摘要 |
|---|---|---|
| repair_loop | 通过 | `{"status": "success_after_repair", "repair_count": 1, "passed": true}` |
| knowledge_lifecycle | 通过 | `{"required_types": ["CapabilityVersion", "FailureCase", "RepairStrategy", "ValidationRun", "VersionEvent"], "passed": true}` |
| api_documentation | 通过 | `{"openapi": "3.0.3", "post_routes": ["/api/benchmark", "/api/datasets/map", "/api/extract", "/api/replicate", "/api/run", "/api/run-async", "/api/upload", "/api/versions"], "passed": true}` |
| capability_replication | 通过 | `{"valid": true, "equivalence_cases": 4, "review_status": "auto_validated", "implementation_candidates": 1, "passed": true}` |

## 使用说明

重新运行：`uv run python scripts/run_acceptance_cases.py`。
该报告用于提交评审证据，不替代完整的 pytest、覆盖率和端到端验收。
