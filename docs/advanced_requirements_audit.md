# 扩展功能实现情况

这个文件记录几个扩展功能目前做到什么程度。判断时不只看是否存在相关类，还会检查：

1. 是否有可调用入口；
2. 是否进入真实工作流；
3. 是否有测试或运行产物；
4. 是否在报告、追踪或知识图谱中留下可检查的结果。

## 核查结论

| 功能 | 当前情况 | 主要实现 | 可查看内容 |
|---|---|---|---|
| Web、CLI 或 API 接口 | 已实现 | 同时提供 CLI、可视化 Web 工作台和本地 JSON API；接口参考与 OpenAPI JSON 由路由目录自动生成 | `uv run python -m inventory_agent --help`、`/api/docs` |
| 支持多轮代码修复 | 完成 | LangGraph 的 `validate -> repair -> validate` 条件循环，默认最多两轮；记录失败指纹、修复策略和历史经验复用 | `examples/repair_run/`、`tests/test_workflow.py` |
| 多个候选算法方案自动比较 | 已实现 | 从知识图谱检索多个可执行能力，执行无时间泄漏的滚动回测，按任务验证配置排序；完整追踪还会逐个生成并验证候选代码 | `examples/detailed_run/candidate_solutions/` |
| 知识图谱可视化 | 已实现 | 独立 HTML 分层视图，支持搜索、类型筛选、缩放、拖动、关系名称、关联高亮和节点详情 | `knowledge/base_capability_graph.html` |
| 自动生成验证报告 | 已实现 | 自动输出业务 Markdown、技术 Markdown 和 JSON；包含候选比较、多实现代码生成、验证、修复、插件、配置和使用边界；Web 直接渲染 | 每次运行目录的 `business_report.md`、`validation_report.json/.md` |
| 验证结果回写知识库或知识图谱 | 已实现 | 成功与最终失败均写入图谱；关联验证运行、失败案例、修复策略、源码版本和版本事件 | `examples/knowledge_graph/complete_capability_graph.html` |
| 不同任务类型的验证配置 | 已实现 | 内置库存成本、预测精度、间歇性需求三类配置；支持 CLI 显式覆盖和插件新增配置 | `uv run python -m inventory_agent plugins` |
| 插件式接入算法模板或评估指标 | 完成 | 模型与指标均有注册表；新增可信本地插件加载器，可通过 CLI 注入自定义指标和验证配置 | `examples/plugins/stockout_priority.py` |

## 本轮重点补强

### 1. 不同任务验证配置

内置配置现包括：

- `inventory_target`：主指标为非对称缺货/积压库存成本；
- `demand_forecast`：主指标为 WAPE；
- `intermittent_demand`：主指标为 MAE，增加回测起点和最短历史要求，适合大量零需求；
- 外部插件可继续注册新任务配置。

自然语言中出现“间歇、稀疏、大量零、零需求、备件、Croston”等表达时，会自动选择
`intermittent_demand`。也可以使用 `run --task-type` 显式覆盖，避免运行结果完全依赖语义推断。

### 2. 可审计插件接入

插件格式为 `module:callable` 或 `path.py:callable`。注册函数接收受限的
`PluginContext`，目前公开两个稳定扩展点：

- `register_metric()`；
- `register_validation_profile()`。

插件不会自动从网络发现或下载。插件执行普通 Python 代码，因此只应加载经过审核的本地文件。
每次加载会记录插件来源、新增指标和新增验证配置，并写入运行追踪及验证报告。

检查示例插件：

```bash
uv run python -m inventory_agent plugins \
  --plugin examples/plugins/stockout_priority.py:register
```

使用插件执行回测：

```bash
uv run python -m inventory_agent benchmark \
  --data examples/data/cainiao_demo.csv \
  --item 3424 \
  --store 1 \
  --task-type stockout_priority \
  --plugin examples/plugins/stockout_priority.py:register \
  --output artifacts/plugin_benchmark.json
```

使用插件执行完整 Agent 工作流：

```bash
uv run python -m inventory_agent run \
  --description "为商品 3424 在仓库 1 预测未来14天目标库存" \
  --data examples/data/cainiao_demo.csv \
  --task-type stockout_priority \
  --plugin examples/plugins/stockout_priority.py:register \
  --trace-level full
```

## 仍需诚实说明的边界

- Web、CLI 和本地 JSON API 均已提供，但 Web/API 没有登录、租户隔离和公网鉴权，不应直接暴露公网。
- 修复循环是有上限的工程闭环，不是无限自主修改；Mock 模式优先保证离线可复现。
- 算法候选是知识图谱检索加滚动回测，不是 Beam Search、MCTS 或通用图搜索。
- 外部插件采用显式可信加载，不会自动安装第三方包，也没有使用 Python entry points 自动发现。
- 生成代码使用受限子进程和 AST 安全规则，但不是容器级沙箱。
