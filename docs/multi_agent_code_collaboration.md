# 多智能体代码生成协作协议

项目的代码生成不是把需求交给一次 Prompt 后直接采用结果，而是使用有明确职责边界、独立调用和验证裁决的协作协议：

```text
CapabilitySpec + 业务上下文
        ↓
CodeArchitectureAgent（只设计蓝图，不生成代码）
        ↓
CodeImplementationAgent（按不同策略独立生成 1～5 份源码）
        ↓
CodeReviewAgent（逐份独立审查，必要时返回完整修订源码）
        ↓
GeneratedCodeValidator（安全、接口、运行、稳定性、等价性、资源门禁）
        ↓
正确候选按延迟、内存和代码规模确定性选优
        ↓
RepairAgent（验证失败时进入最多两轮“修复—再验证”）
```

## 角色职责

| 角色 | 输入 | 输出 | 不允许做的事 |
|---|---|---|---|
| CodeArchitectureAgent | 能力规格、需求画像、验证指标、研究证据 | 算法步骤、接口约束、边界条件、允许依赖、性能目标和风险 | 不输出 Python 代码，不决定验证是否通过 |
| CodeImplementationAgent | 蓝图、能力规格、某一种实现策略 | 一份自包含 Python 模块 | 不调用项目内现成模型，不访问文件、网络、进程或环境变量 |
| CodeReviewAgent | 蓝图、源码、静态发现 | 审查结论、问题列表、可选完整修订源码 | 不绕过安全规则，不替代验证器裁决 |
| GeneratedCodeValidator | 审查后的源码、参考语义 | 可执行验证矩阵和资源证据 | 不因 LLM 声称“通过”而放行 |
| RepairAgent | 实际验证错误、历史失败经验、当前源码 | 有边界的修订版本 | 不无限重试；达到预算后停止 |

Mock 模式使用确定性架构蓝图、模板实现和静态审查，以便离线复现；API 模式的架构、实现和审查是三类独立 LLM 调用。即使审查 Agent 表示通过，源码仍必须通过本地验证器。

## 可审计证据

每次完整运行会在 `artifacts/runs/<run_id>/generated/` 产生：

- `implementation_blueprint.json`：架构 Agent 的结构化设计；
- `forecast_<model>_candidate_<n>.py`：各实现 Agent 候选；
- `multi_agent_collaboration.json`：角色、策略、源码哈希、审查发现和修订记录；
- 验证报告中的“多智能体代码协作证据”章节；
- `detailed_trace.jsonl/.md` 中的 `multi_agent_code_collaboration` 事件。

Web 端完整工作流结束后，可直接点击“多智能体协作”和“实现蓝图”查看原始 JSON。后台任务状态还会写入 `artifacts/jobs/`，服务重启后仍能读取已完成任务的结果。

## 失败边界

- 架构或审查服务返回非法 JSON 时，记录降级原因并采用确定性蓝图或静态审查，不丢失可复现性；
- 审查修订后的源码重新计算 SHA-256，不沿用修订前证据；
- 多候选必须先通过正确性门禁，性能更快但结果错误的实现不会入选；
- 无候选通过时进入既有 RepairAgent 循环，而不是把审查意见当作成功证据；
- Beam Search/MCTS、跨行业迁移和容器级沙箱不在本次实现范围。
