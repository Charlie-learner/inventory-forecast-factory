"""Generate API documentation from the same route catalog used by the Web server."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from inventory_agent.execution import DEFAULT_RUNTIME_LIMITS


@dataclass(frozen=True)
class ApiRoute:
    """Describe one public local API operation."""

    method: str
    path: str
    summary: str
    description: str
    handler: str = ""
    request_example: dict[str, Any] | None = None


API_ROUTES = (
    ApiRoute("GET", "/health", "服务健康检查", "检查本地 Web 服务是否在线。"),
    ApiRoute("GET", "/api/overview", "系统总览", "返回算法、指标、验证配置、图谱和运行统计。"),
    ApiRoute(
        "GET",
        "/api/audit",
        "项目功能自检",
        "逐项返回完成状态、功能说明、相关文件、CLI 检查命令和实现边界。",
    ),
    ApiRoute("GET", "/api/runs", "运行列表", "返回最近的完整工作流运行记录。"),
    ApiRoute(
        "GET",
        "/api/jobs/{job_id}",
        "异步任务进度",
        "返回工作流当前阶段、完成百分比；结束后同时返回完整结果。",
    ),
    ApiRoute(
        "GET",
        "/api/runs/{run_id}",
        "运行详情",
        "返回验证报告、运行清单和结构化 Agent 事件。",
    ),
    ApiRoute(
        "GET",
        "/api/runs/{run_id}/{artifact}",
        "运行产物",
        "读取业务报告、技术报告、JSON、Trace 或产物清单。",
    ),
    ApiRoute(
        "GET",
        "/api/versions?model={model}",
        "能力版本",
        "查询一个算法能力的版本、验证证据和生命周期事件。",
    ),
    ApiRoute(
        "POST",
        "/api/run-async",
        "异步执行完整 Agent 工作流",
        "立即返回任务 ID，适合 Web 轮询进度，避免长连接等待。",
        "start_workflow",
        {
            "description": "预测商品 1013 在仓库 3 未来14天库存并解释依据",
            "data_path": "examples/business_data/demand_history.csv",
            "execution_mode": "balanced",
        },
    ),
    ApiRoute(
        "POST",
        "/api/run",
        "执行完整 Agent 工作流",
        "从自然语言和上传数据执行需求理解、检索、比较、代码生成、验证、修复、报告与沉淀。",
        "run_workflow",
        {
            "description": "预测商品 1013 在仓库 3 未来14天库存并给出补货建议",
            "data_path": "data",
            "trace_level": "full",
            "keep_runs": DEFAULT_RUNTIME_LIMITS.default_keep_runs,
            "online_research": True,
            "execution_mode": "thorough",
        },
    ),
    ApiRoute(
        "POST",
        "/api/upload",
        "上传一份业务文件",
        "把 CSV 或 ZIP 加入同一个上传会话并返回数据诊断。",
        "upload_dataset",
        {
            "session_id": "demo_session_01",
            "filename": "demand.csv",
            "content_base64": "<base64>",
        },
    ),
    ApiRoute(
        "POST",
        "/api/datasets/map",
        "映射自定义数据字段",
        "把非标准 CSV 的日期、商品、仓库和需求列映射到统一契约。",
        "map_dataset_columns",
        {
            "session_id": "demo_session_01",
            "filename": "erp.csv",
            "mapping": {
                "date": "period",
                "item_id": "material",
                "store_code": "site",
                "qty_alipay_njhs": "units",
            },
        },
    ),
    ApiRoute(
        "POST",
        "/api/benchmark",
        "候选算法回测",
        "对一个商品和位置执行多个候选算法的滚动回测与指标比较。",
        "benchmark",
        {
            "data_path": "examples/data/cainiao_demo.csv",
            "item_id": 3424,
            "store_code": "1",
            "horizon": 14,
            "models": ["last_value", "moving_average", "croston"],
        },
    ),
    ApiRoute(
        "POST",
        "/api/extract",
        "抽取算法能力",
        "从本地文档、Python 文件或代码仓库抽取结构化能力并可写入知识图谱。",
        "extract",
        {
            "sources": ["inventory_agent/forecasting/models.py"],
            "update_knowledge": True,
        },
    ),
    ApiRoute(
        "POST",
        "/api/replicate",
        "复刻并验证能力",
        "生成一个或多个独立代码实现，逐份验证并自动选择合格实现。",
        "replicate",
        {
            "sources": ["examples/capabilities/moving_average.md"],
            "reference_model": "moving_average",
            "candidate_count": 3,
        },
    ),
    ApiRoute(
        "POST",
        "/api/versions",
        "管理能力版本",
        "比较、发布或回滚经过验证的算法能力版本。",
        "manage_version",
        {
            "action": "promote",
            "model": "moving_average",
            "version": "<source-hash-prefix>",
        },
    ),
)


def post_route_handlers() -> dict[str, str]:
    """Return exact POST route to WebApplication method mappings."""

    return {
        route.path: route.handler
        for route in API_ROUTES
        if route.method == "POST" and route.handler
    }


def openapi_document() -> dict[str, Any]:
    """Build a compact OpenAPI-compatible document from the route catalog."""

    paths: dict[str, Any] = {}
    for route in API_ROUTES:
        normalized_path = route.path.split("?", 1)[0]
        operation: dict[str, Any] = {
            "operationId": route.handler or (
                route.method.lower()
                + "_"
                + re.sub(r"[^a-zA-Z0-9]+", "_", normalized_path).strip("_")
            ),
            "summary": route.summary,
            "description": route.description,
            "responses": {
                "200": {"description": "成功"},
                "400": {"description": "输入或业务校验失败"},
                "500": {"description": "内部执行失败"},
            },
        }
        parameters = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
            for name in re.findall(r"{([^}]+)}", normalized_path)
        ]
        if "?" in route.path:
            query = route.path.split("?", 1)[1]
            for name, placeholder in re.findall(
                r"([^=&]+)=\{([^}]+)\}", query
            ):
                parameters.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": f"对应 {placeholder}",
                    }
                )
        if parameters:
            operation["parameters"] = parameters
        if route.method == "POST":
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"type": "object"},
                        "example": route.request_example or {},
                    }
                },
            }
        paths.setdefault(normalized_path, {})[route.method.lower()] = operation
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "库存算法能力工厂本地 API",
            "version": "1.0.0",
            "description": (
                "Web、CLI 和 API 共用同一套能力工厂服务。"
                "接口默认仅绑定本机，未提供公网鉴权。"
            ),
        },
        "servers": [{"url": "http://127.0.0.1:8000"}],
        "paths": paths,
    }


def render_api_docs_html() -> str:
    """Render a readable, dependency-free API reference page."""

    cards = []
    for route in API_ROUTES:
        example = ""
        if route.request_example is not None:
            import json

            example = (
                "<pre>"
                + html.escape(
                    json.dumps(
                        route.request_example,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                + "</pre>"
            )
        cards.append(
            "<article>"
            f"<div><span class='{route.method.lower()}'>{route.method}</span>"
            f"<code>{html.escape(route.path)}</code></div>"
            f"<h2>{html.escape(route.summary)}</h2>"
            f"<p>{html.escape(route.description)}</p>{example}"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>库存算法能力工厂 API 文档</title>
<style>
body{{margin:0;background:#f4f7fb;color:#17243a;font:14px/1.6 system-ui,"Microsoft YaHei";}}
main{{max-width:1050px;margin:auto;padding:36px 22px 70px;}}
header{{padding:26px;border-radius:18px;color:white;background:linear-gradient(120deg,#102650,#3267e8);}}
header h1{{margin:0 0 8px;}}header p{{margin:0;color:#dce8ff;}}
.links{{display:flex;gap:10px;margin:18px 0;}}
a{{color:#245edb;text-decoration:none;font-weight:700;}}
article{{margin:13px 0;padding:20px;border:1px solid #e0e7f1;border-radius:14px;background:white;}}
article h2{{margin:10px 0 4px;font-size:18px;}}article p{{margin:0;color:#5d6a7e;}}
span{{display:inline-block;margin-right:10px;padding:3px 8px;border-radius:7px;color:white;font-weight:800;}}
.get{{background:#16845c;}}.post{{background:#356ae6;}}
code{{font-size:14px;}}pre{{overflow:auto;padding:14px;border-radius:10px;color:#dce8ff;background:#101a2e;}}
</style>
</head>
<body><main>
<header><h1>库存算法能力工厂 API</h1>
<p>由服务端路由目录自动生成，主要用于本地集成和接口联调。</p></header>
<div class="links"><a href="/api/openapi.json">查看 OpenAPI JSON</a><a href="/">返回 Web 工作台</a></div>
{''.join(cards)}
</main></body></html>"""
