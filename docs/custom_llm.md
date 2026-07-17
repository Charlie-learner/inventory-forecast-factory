# 使用自定义 OpenAI 兼容 LLM

项目通过 OpenAI Python 客户端调用 `chat.completions.create`。只要服务商实现兼容的
`POST /chat/completions` 接口，即可通过环境变量接入。

## 安全要求

- API Key 只写入本机 `.env`；
- 不要写入 `.env.example`、源代码、命令行参数、截图、聊天或 Git 提交；
- 如果密钥曾公开展示，应立即撤销并重新生成；
- `.env` 已被 `.gitignore` 忽略。

## 配置

在项目根目录复制环境模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
LLM_MODE=api
MODEL=your-provider-model
BASE_URL=https://your-provider.example/v1
API_KEY=replace-with-a-new-secret
LLM_TIMEOUT_SECONDS=30
```

检查项目是否读取到配置：

```powershell
uv run python -m inventory_agent doctor
```

输出中的 `api_key_configured` 应为 `true`。诊断命令不会打印密钥。

上述命令只检查配置。要实际发起一次最小请求并记录延迟，请运行：

```powershell
uv run python -m inventory_agent doctor --live-llm
```

成功时 `live_llm.status` 为 `passed`，且 `response_excerpt` 包含
`INVENTORY_LLM_OK`。该命令不会打印 API Key。

然后重启 Web：

```powershell
uv run python -m inventory_agent web --open-browser
```

## 代码生成候选数与调用成本

API 模式的完整工作流默认会针对最终能力生成 3 个不同实现策略的源码候选，并逐份验证后选优。
Web“能力抽取与复刻”页面和 CLI `replicate-capability --candidates 1-5` 可以调整候选数。

候选数越多，通常会增加 LLM 请求次数、运行时间和接口费用。调试接口连通性时建议先设为 1；
正式展示自动生成与选优能力时建议使用 3。Mock 模式忽略候选数并只生成一份确定性模板。

页面右上角应从 `MOCK` 变成 `API`，并显示配置的模型名称。

同时验证模型与 Crossref 联网研究：

```powershell
uv run python scripts/validate_external_services.py
```

联网行业研究和搜索增强策略见
[`online_research_and_optimization.md`](online_research_and_optimization.md)。

## 使用边界

服务商模型名称必须真实存在，并且接口需要兼容 OpenAI Chat Completions。若服务商只
支持 Responses API、特殊鉴权头或自定义请求格式，则需要单独编写 LLM 适配器。
