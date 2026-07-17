"""Threaded standard-library HTTP server for the local Web dashboard."""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from inventory_agent.config import Settings
from inventory_agent.execution import format_byte_limit
from inventory_agent.web.api_docs import (
    openapi_document,
    post_route_handlers,
    render_api_docs_html,
)
from inventory_agent.web.app import WebApplication, WebRequestError


ASSET_ROOT = Path(__file__).resolve().parent / "static"
logger = logging.getLogger(__name__)


def build_handler(application: WebApplication) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to one application instance."""

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "InventoryCapabilityFactory/1.0"

        def log_message(self, format: str, *args: object) -> None:
            """Use a compact local-server log format."""

            logger.info("%s - %s", self.address_string(), format % args)

        def _send(
            self,
            body: bytes,
            content_type: str,
            status: int = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: object, status: int = HTTPStatus.OK) -> None:
            self._send(
                json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _payload(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = application.runtime_limits.max_http_body_bytes
                if length > limit:
                    raise WebRequestError(
                        f"请求内容超过 {format_byte_limit(limit)}。", 413
                    )
                body = self.rfile.read(length)
                value = json.loads(body.decode("utf-8")) if body else {}
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WebRequestError(f"请求 JSON 无法解析：{exc}") from exc
            if not isinstance(value, dict):
                raise WebRequestError("请求主体必须是 JSON 对象。")
            return value

        def _handle_error(self, exc: Exception) -> None:
            if isinstance(exc, WebRequestError):
                logger.warning("Rejected Web request: %s", exc)
                self._json({"error": str(exc)}, exc.status)
            else:
                logger.exception("Unhandled Web request error")
                self._json(
                    {
                        "error": "服务器内部错误，请查看服务端日志。",
                        "error_type": type(exc).__name__,
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            try:
                if path in {"/", "/index.html"}:
                    self._send(
                        (ASSET_ROOT / "index.html").read_bytes(),
                        "text/html; charset=utf-8",
                    )
                elif path.startswith("/static/"):
                    asset_path = (
                        ASSET_ROOT / path.removeprefix("/static/")
                    ).resolve()
                    if ASSET_ROOT.resolve() not in asset_path.parents:
                        raise WebRequestError(
                            "非法静态资源路径。", HTTPStatus.NOT_FOUND
                        )
                    if not asset_path.is_file():
                        raise WebRequestError(
                            "静态资源不存在。", HTTPStatus.NOT_FOUND
                        )
                    content_type = mimetypes.guess_type(asset_path.name)[0]
                    self._send(
                        asset_path.read_bytes(),
                        f"{content_type or 'application/octet-stream'}; charset=utf-8",
                    )
                elif path == "/api/overview":
                    self._json(application.overview())
                elif path == "/api/audit":
                    self._json(application.audit())
                elif path == "/api/openapi.json":
                    self._json(openapi_document())
                elif path == "/api/docs":
                    self._send(
                        render_api_docs_html().encode("utf-8"),
                        "text/html; charset=utf-8",
                    )
                elif path == "/api/runs":
                    self._json({"runs": application.list_runs()})
                elif path.startswith("/api/jobs/"):
                    self._json(application.job_status(path.rsplit("/", 1)[-1]))
                elif path.startswith("/api/runs/") and path.count("/") >= 4:
                    _, _, _, run_id, artifact = path.split("/", 4)
                    body, content_type = application.run_artifact(
                        run_id, artifact
                    )
                    self._send(body, content_type)
                elif path.startswith("/api/runs/"):
                    self._json(application.run_detail(path.rsplit("/", 1)[-1]))
                elif path == "/api/versions":
                    query = parse_qs(parsed.query)
                    self._json(
                        application.versions(
                            str(query.get("model", [""])[0])
                        )
                    )
                elif path == "/graph":
                    self._send(
                        application.graph_html(),
                        "text/html; charset=utf-8",
                    )
                elif path == "/health":
                    self._json({"status": "ok"})
                else:
                    self._json({"error": "页面不存在。"}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._handle_error(exc)

        def do_POST(self) -> None:
            path = unquote(urlparse(self.path).path)
            try:
                payload = self._payload()
                handler_name = post_route_handlers().get(path)
                if handler_name:
                    self._json(getattr(application, handler_name)(payload))
                else:
                    self._json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._handle_error(exc)

    return DashboardHandler


def create_server(
    application: WebApplication,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> ThreadingHTTPServer:
    """Create the server separately so tests can bind an ephemeral port."""

    return ThreadingHTTPServer((host, port), build_handler(application))


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
    output_root: str | Path = "artifacts/runs",
    knowledge_path: str | Path = "artifacts/knowledge/capability_graph.json",
    settings: Settings | None = None,
) -> None:
    """Run the local dashboard until interrupted."""

    application = WebApplication(
        settings=settings,
        output_root=output_root,
        knowledge_path=knowledge_path,
    )
    server = create_server(application, host, port)
    url = f"http://{host}:{server.server_address[1]}"
    print(f"库存算法能力工厂 Web 界面：{url}")
    print("按 Ctrl+C 停止服务。")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 Web 服务……")
    finally:
        server.server_close()
