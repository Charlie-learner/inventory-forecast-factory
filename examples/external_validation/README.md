# 外部服务联网实测记录

本目录保存 2026-07-17 的脱敏实测摘要。结果包括：

- OpenAI 兼容接口返回预期健康检查标记，未输出 API Key；
- Crossref 返回 5 条 DOI 资料；
- LLM 从标题和摘要中建议 Croston 与移动平均作为间歇需求候选；
- 完整工作流将研究证据用于候选规划，最终通过本地回测选择 Croston；
- 三份代码实现中，两份自主生成实现因返回类型违反接口契约被拒绝，一份安全候选通过；
- 最终代码通过安全、接口、稳定性和四个参考行为等价用例；
- 目标库存约 109.59 件，结合库存位置和订货约束后建议补货 66 件。

该结果体现了“外部建议可以失败，但本地验证门禁不能失效”。完整实时产物默认位于
`artifacts/live_e2e_runs/`，不会进入 Git。重新检查：

```powershell
uv run python -m inventory_agent doctor --live-llm
uv run python scripts/validate_external_services.py
```

算法、资料和接口响应具有时效性，需要确认时应以重新运行结果为准。
