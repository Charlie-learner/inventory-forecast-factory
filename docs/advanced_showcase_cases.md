# 高级进阶功能演示用例

本测试包用于向评审者集中展示联网知识搜索、LLM 多智能体代码生成、候选算法比较、
自动验证、错误修复、经验复用、能力版本和知识图谱沉淀。运行入口：

```powershell
# 完全离线、可重复：自动修复 + 跨运行经验复用
uv run python scripts/run_advanced_showcase.py --mode offline

# 协议级多智能体代码生成：3 份独立实现、审查修订和等价验证
uv run python scripts/run_advanced_showcase.py --mode protocol --session <上一步输出的会话名>

# 使用 .env 中的真实外部 LLM，并调用 Crossref
uv run python scripts/run_advanced_showcase.py --mode live --session <上一步输出的会话名>

# 外部 LLM 不可用时，可独立执行公开资料联网检索后刷新汇总
$env:LLM_MODE='mock'
uv run python -m inventory_agent research-industry --query `
  "intermittent demand forecasting inventory control Croston TSB safety stock" `
  --profile intermittent --limit 5 `
  --output examples/advanced_showcase/<session>/online_knowledge_extraction.json
uv run python scripts/run_advanced_showcase.py --mode summarize --session <session>

# 一次运行全部用例
uv run python scripts/run_advanced_showcase.py --mode all
```

脚本不会输出 API Key。每次新执行默认创建独立时间戳目录，避免覆盖历史证据；使用
`--session` 可以向同一份知识图谱追加真实联网用例。

## 用例一：候选比较、故障修复与知识沉淀

业务请求：商品 1002、仓库 1、未来 14 天库存目标。该商品具有明显周周期，且目录中
同时提供现货、在途、欠单、安全库存、MOQ、包装倍数和仓容。

验证内容：

1. RequirementAgent 理解自然语言任务并生成需求画像；
2. PlanningAgent 从图谱检索不少于三个可执行算法；
3. 滚动回测比较库存成本、WAPE、RMSE 等指标；
4. 代码团队生成架构蓝图、自包含实现并独立审查；
5. 测试脚本在最终代码验证阶段注入一次真实接口错误；
6. FailureAnalyzer 生成稳定失败指纹和根因；
7. RepairAgent 修复代码并重新执行全部门禁；
8. ExperienceAgent 写入 FailureCase、RepairStrategy、ValidationRun 和 CapabilityVersion。

通过标准：恰好出现至少一次失败和修复，最终验证通过，图谱出现对应失败、修复和版本节点。

## 用例二：跨运行复用失败经验

使用相同知识图谱再次运行商品 1002，并注入同类别接口错误。

通过标准：`repair_experience_used` 非空；Trace 能看到历史策略检索；最终生成新的验证记录，
相同失败类型不需要从零判断修复方向。

## 用例三：多智能体代码生成协议与审查修订

该用例使用确定性的 LLM 协议测试双，不访问外部服务，但会经过与 API 模式完全相同的
`complete(system, user)` 接口和架构—实现—审查链路。三个实现 Agent 分别生成 Pandas、
NumPy 和纯 Python 版本，其中 NumPy 版本故意返回 `ndarray`；CodeReviewAgent 将其修订为
`list[float]`，然后所有候选接受安全、接口、稳定性、等价性和性能验证。

通过标准：生成 3 个不同源码哈希，至少 1 份出现审查修订，最终选中候选通过参考行为等价验证。

这个用例验证多智能体协议和代码门禁，不冒充真实外部模型调用。真实模型参与情况只由下一用例证明。

## 用例四：真实联网研究与 LLM 多智能体代码生成

业务请求：高间歇需求商品 1003、仓库 2、未来 21 天库存目标。

验证内容：

1. IndustryResearchAgent 实际调用 Crossref 检索间歇需求和库存控制资料；
2. 生成 `online_knowledge_extraction.json` 并将来源写成 SourceArtifact；
3. CodeArchitectureAgent 独立生成实现蓝图；
4. 多个 CodeImplementationAgent 按不同策略生成独立源码；
5. CodeReviewAgent 分别审查并在必要时修订源码；
6. GeneratedCodeValidator 执行安全、接口、边界、稳定性、等价性和资源门禁；
7. 系统在正确候选中按延迟、内存和代码规模选优；
8. 报告解释算法依据、联网证据、库存成本和补货约束；
9. 通过验证的版本和研究来源写回知识图谱。

通过标准：研究状态为 `success`，至少获得一条来源；代码协作记录包含架构、实现和审查角色；
至少一个自主生成候选通过最终门禁；验证报告、Trace、源码、性能报告和图谱文件均存在。

## 证据结构

```text
examples/advanced_showcase/<session>/
├── showcase_summary.json       # 三个用例的机器可读汇总
├── showcase_summary.md         # 教师快速查看入口
├── capability_graph.json       # 跨用例共享知识图谱
├── capability_graph.graphml
├── capability_graph.html
└── runs/
    ├── case_01_repair_deposition/<run_id>/
    ├── case_02_experience_reuse/<run_id>/
    └── case_04_live_research_multi_agent/<run_id>/
```

每个运行目录都包含业务报告、技术报告、JSON、详细 Trace、候选算法源码、实现蓝图、
多智能体协作记录、性能分析、失败经验和运行清单。
