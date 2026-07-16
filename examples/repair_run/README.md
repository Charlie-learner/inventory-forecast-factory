# 自动修复闭环示例

本目录由 `scripts/generate_submission_examples.py` 生成，刻意在最终代码第一次验证时注入一个
语法类失败，用于展示：

```text
生成代码
  -> 验证失败
  -> 失败归一化与指纹
  -> RepairAgent 安全修复
  -> 再次验证通过
  -> FailureCase / RepairStrategy / CapabilityVersion 写入图谱
```

先查看 `index.json` 找到当前时间戳运行目录，再依次打开：

1. `validation_report.md`：修复次数、失败记录和最终结果；
2. `detailed_trace.md`：验证失败、RepairAgent输入输出和重新验证事件；
3. `generated_versions/`：初始版本和修复版本；
4. `run_manifest.json`：运行状态与产物索引。

该失败只用于演示修复闭环，不表示算法本身存在已知语法缺陷。

