# 详细运行过程、候选代码比较与结果保留

完整追踪用于调试、查看 Agent 中间过程和复现实验。CLI 的 `run` 命令默认使用 `full` 级别：

```bash
python -m inventory_agent run \
  --description "为商品 3424 在仓库 1 预测未来14天目标库存" \
  --data examples/data/cainiao_demo.csv \
  --capability-source examples/capabilities/moving_average.md \
  --output-root artifacts/runs \
  --trace-level full \
  --keep-runs 10
```

## 追踪级别

| 级别 | 行为 |
|---|---|
| `off` | 不写详细事件文件，也不额外生成候选代码方案 |
| `basic` | 记录实际工作流中的 Agent、工具、LLM、验证、修复和沉淀事件 |
| `full` | 在 `basic` 基础上，为每个规划候选生成独立代码，执行同一验证器并形成代码方案比较 |

## 单次运行目录

```text
YYYYMMDD_HHMMSS_microseconds/
├── detailed_trace.jsonl        每行一个结构化事件，适合程序解析
├── detailed_trace.md           教师可顺序阅读的完整中间过程
├── run_manifest.json           状态、事件数、时间和全部产物索引
├── extracted_capabilities.json 能力抽取结果
├── candidate_solutions/        每个候选算法的独立生成代码
├── generated/                  最终选中并执行的代码
├── generated_versions/         初始代码及每轮修复后的不可变快照
├── validation_report.json      完整机器报告
└── validation_report.md        汇总报告和候选代码比较表
```

事件记录包含：

- 顺序号、UTC 时间、阶段、组件、组件类型和状态；
- Agent 输入与结构化输出；
- 数据加载、图谱检索、回测、代码生成、验证和持久化等工具调用参数与结果；
- LLM system/user prompt、响应或异常；
- 候选算法指标、候选代码路径、代码哈希和验证结果；
- 每次验证失败、失败指纹、历史经验检索、修复原因和修复后代码快照；
- 最终报告、知识图谱和其他文件路径。

事件会在步骤结束后立即追加到 JSONL 和 Markdown，因此即使工作流最终失败，已经发生的验证和修复过程仍会保留，`run_manifest.json` 的状态会是 `failed`。

## 候选代码方案比较

`full` 模式不会只展示最终算法。它会对规划阶段的每个候选：

1. 从知识图谱恢复 `CapabilitySpec`；
2. 生成自包含代码到 `candidate_solutions/<model>/`；
3. 执行安全、接口、稳定性和四类需求数值等价验证；
4. 将代码验证结果与该模型的滚动回测指标合并；
5. 在验证报告中输出候选代码比较表。

候选方案生成只用于审计和比较，最终执行代码仍按回测选择结果单独生成，避免改变原有选型逻辑。

## 自动清理旧运行

`--keep-runs N` 表示一个输出根目录最多保留最新 N 个任务。清理逻辑具有以下限制：

- 只检查 `--output-root` 的直接子目录；
- 只删除名称严格匹配 `YYYYMMDD_HHMMSS_microseconds` 的目录；
- 不处理符号链接；
- 删除前验证解析后的父目录仍是指定输出根目录；
- 不删除手工命名目录、数据文件、知识图谱或其他项目文件；
- `N` 必须大于 0。

需要长期保留的运行可以复制到 `examples/` 或改成非时间戳目录名。仓库附带的完整示例位于 `examples/detailed_run/`。

若需要在提交前统一清除本地上传副本、运行产物、测试缓存和覆盖率文件，可先运行
`uv run python scripts/clean_workspace.py` 预览，再运行
`uv run python scripts/clean_workspace.py --apply` 执行。该脚本不会删除 `data/`、
`examples/`、虚拟环境或 Git 元数据。

## 信息安全边界

追踪文件会记录模型提示词、响应、用户需求和文件路径，但不会主动记录 API Key。真实业务使用时仍应避免把客户隐私、商业机密或凭据写入自然语言描述和模型提示词；提交前应人工检查追踪文件。
