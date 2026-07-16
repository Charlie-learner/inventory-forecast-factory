# 完整能力知识图谱示例

本目录保存可随Git仓库交付的完整运行图谱，而不是只包含静态算法的基础图谱。

它至少包含：

- 外部能力文档及 `SourceArtifact`；
- `Algorithm`、`DemandProfile` 和 `Metric`；
- 一次带失败历史的 `ValidationRun`；
- 归一化 `FailureCase`；
- 成功 `RepairStrategy`；
- 生成代码 `CapabilityVersion`；
- 发布动作 `VersionEvent`。

建议直接打开 `complete_capability_graph.html`，或使用 Gephi 打开 GraphML。JSON用于代码加载
和审计，所有文件均可通过以下命令重新生成：

```bash
python scripts/generate_submission_examples.py
```

