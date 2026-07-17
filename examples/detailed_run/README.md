# 完整离线运行示例

本目录保留一次 `--trace-level full` 的真实离线运行。进入时间戳子目录后，建议按以下顺序查看：

1. `validation_report.md`：先看业务结果、候选模型指标和候选代码验证对比；
2. `detailed_trace.md`：按事件顺序查看各 Agent、工具和 Mock LLM 的输入输出；
3. `run_manifest.json`：检查状态、事件数、起止时间和产物索引；
4. `candidate_solutions/`：比较三个候选算法生成的独立代码；
5. `generated/`：查看最终选中算法的执行代码；
6. `generated_versions/`：查看初始代码和可能的修复版本快照；
7. `detailed_trace.jsonl`：用于程序化分析完整事件流。

本示例使用 Mock LLM、`examples/data/cainiao_demo.csv` 和 `examples/capabilities/moving_average.md`，不需要 API Key。
