# 能力复刻审核清单

- 能力：moving_average:1.1.0
- 生成方式：spec_template
- 生成文件：examples\replication_run\generated\forecast_moving_average.py
- 规格哈希：6d5a7644b3e06bafc07be2f1871e6a76ae1c8c171b209028a12fe0be0a82edd1
- 源码哈希：6f4ed1926562e5a7967d716a45e5916da094808468fd2fb4b4cede9e2b76885c
- 实现候选：1
- 选中候选：primary
- 生成策略：specification_fidelity
- 参考能力：moving_average
- 自动验证：通过
- 检查项：{'syntax': True, 'imports': True, 'interface': True, 'runtime': True, 'stability': True, 'equivalence': True}
- 等价用例数：4
- 最大等价误差：0.0
- 平均预测延迟：0.7731799996690825 ms
- Python 内存峰值：25.8095703125 KB
- 审核状态：auto_validated
- 可注册：True
- 判定依据：Behavior matches registered reference capability moving_average.

## 多智能体协作

- 协作协议：architecture -> parallel implementation -> independent review -> validation
- 参与角色：CodeArchitectureAgent, CodeImplementationAgent, CodeReviewAgent, GeneratedCodeValidator
- 实现蓝图：examples\replication_run\generated\implementation_blueprint.json
- 完整协作记录：examples\replication_run\generated\multi_agent_collaboration.json

## 验证错误


## 实现候选比较

| 候选 | 策略 | 验证 | 平均延迟(ms) | 内存峰值(KB) | 选中 |
|---|---|---|---:|---:|---|
| primary | specification_fidelity | 通过 | 0.7731799996690825 | 25.8095703125 | True |
