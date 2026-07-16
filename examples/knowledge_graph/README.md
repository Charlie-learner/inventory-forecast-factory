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

建议直接打开 `complete_capability_graph.html`。页面支持搜索、按节点类型筛选、缩放拖动、
显示关系名称、点击节点查看完整属性，并会高亮与所选节点相连的边。也可以使用 Gephi 打开
GraphML；JSON用于代码加载和审计。所有文件均可通过以下命令重新生成：

```bash
python scripts/generate_submission_examples.py
```
