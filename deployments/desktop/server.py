"""Stdlib local web server for the PaperFlow desktop GUI."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deployments.desktop.shared import agents  # noqa: E402


ApiHandler = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _sse_bytes(event: str, payload: Dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _stream_chunks(text: str, size: int = 18) -> list[str]:
    content = str(text or "")
    if not content:
        return [""]
    return [content[index : index + size] for index in range(0, len(content), size)]


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


def _query(path: str) -> Tuple[str, Dict[str, Any]]:
    parsed = urllib.parse.urlparse(path)
    query = {
        key: values[-1] if values else ""
        for key, values in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()
    }
    return parsed.path, query


def _required_user(params: Dict[str, Any]) -> str:
    user_id = str(params.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return user_id


def _daily_days_from_body(body: Dict[str, Any]) -> int:
    raw_days = int(body.get("days") or 1)
    target_date = str(body.get("target_date") or "").strip()
    if not target_date:
        return max(1, min(14, raw_days))
    try:
        selected = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return max(1, min(14, raw_days))
    today = datetime.now().date()
    if selected > today:
        return 1
    return max(1, min(14, (today - selected).days + 1))


def _optional_positive_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return max(1, int(value))


def _api_health(_query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.health()


def _api_settings(_query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.settings()


def _api_save_settings(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.save_settings(dict(body.get("values") or {}))


def _api_source_options(_query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.source_options()


def _api_provider_test(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.test_provider(str(body.get("kind") or ""))


def _api_users(_query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.list_users()


def _api_roles(_query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.list_roles()


def _api_profile(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.get_profile(_required_user(query_params))


def _api_latest_push(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.load_latest_push(_required_user(query_params))


def _api_daily_status(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.get_daily_push_task(
        task_id=str(query_params.get("task_id") or "").strip(),
        user_id=str(query_params.get("user_id") or "").strip(),
    )


def _api_wiki_stats(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.wiki_stats(_required_user(query_params))


def _api_wiki_search(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.wiki_search(
        _required_user(query_params),
        query=str(query_params.get("q") or ""),
        node_type=str(query_params.get("type") or "").strip() or None,
        limit=int(query_params.get("limit") or 12),
    )


def _api_wiki_graph(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.wiki_graph(
        _required_user(query_params),
        query=str(query_params.get("q") or ""),
        limit=int(query_params.get("limit") or 24),
    )


def _api_activity(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.recent_activity(
        _required_user(query_params),
        days=int(query_params.get("days") or 14),
        limit=int(query_params.get("limit") or 80),
    )


def _api_reports(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.list_reports(
        user_id=str(query_params.get("user_id") or "").strip(),
        query=str(query_params.get("q") or ""),
        days=int(query_params.get("days") or 30),
        limit=int(query_params.get("limit") or 80),
        exact_date=str(query_params.get("date") or "").strip(),
    )


def _api_report_content(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.get_report_content(str(query_params.get("report_id") or "").strip())


def _api_must_read(query_params: Dict[str, Any], _body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.list_must_read(_required_user(query_params))


def _api_create_profile(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.create_or_update_profile(
        user_id=str(body.get("user_id") or "").strip(),
        natural_language=str(body.get("natural_language") or ""),
        scholar_url=str(body.get("scholar_url") or ""),
        homepage_url=str(body.get("homepage_url") or ""),
        pdf_paths=list(body.get("pdf_paths") or []),
        reset_existing=bool(body.get("reset_existing")),
    )


def _api_update_roles(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    action = str(body.get("action") or "").strip().lower()
    if action == "create":
        return agents.create_role(
            role_name=str(body.get("role_name") or "").strip(),
            description=str(body.get("description") or "").strip(),
            feishu_chat_id=str(body.get("feishu_chat_id") or "").strip(),
        )
    if action == "switch":
        return agents.switch_role(str(body.get("role_name") or "").strip())
    if action == "delete":
        return agents.delete_role(str(body.get("role_name") or "").strip())
    raise ValueError("action must be create, switch, or delete")


def _api_daily(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return agents.run_daily_push(
        user_id=user_id,
        days=_daily_days_from_body(body),
        limit_per_source=_optional_positive_int(body.get("limit_per_source")),
        arxiv_categories=body.get("arxiv_categories"),
        conferences=body.get("conferences"),
        journals=body.get("journals"),
    )


def _api_daily_start(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return agents.start_daily_push_task(
        user_id=user_id,
        days=_daily_days_from_body(body),
        limit_per_source=_optional_positive_int(body.get("limit_per_source")),
        arxiv_categories=body.get("arxiv_categories"),
        conferences=body.get("conferences"),
        journals=body.get("journals"),
    )


def _api_feedback(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    push_id = str(body.get("push_id") or "").strip()
    if not user_id or not push_id:
        raise ValueError("user_id and push_id are required")
    return agents.submit_gui_feedback(
        user_id=user_id,
        push_id=push_id,
        selected_numbers=body.get("selected_numbers") or [],
        skipped_numbers=body.get("skipped_numbers") or [],
        later_numbers=body.get("later_numbers") or [],
    )


def _api_read(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    push_id = str(body.get("push_id") or "").strip()
    if not user_id or not push_id:
        raise ValueError("user_id and push_id are required")
    return agents.create_reading_reports(
        user_id=user_id,
        push_id=push_id,
        paper_numbers=body.get("paper_numbers") or body.get("selected_numbers") or [],
        write_feishu=body.get("write_feishu"),
    )


def _api_read_arxiv(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return agents.read_arxiv(
        user_id=user_id,
        arxiv_id=str(body.get("arxiv_id") or "").strip(),
        write_feishu=body.get("write_feishu"),
    )


def _api_read_pdf(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return agents.read_local_pdf(
        user_id=user_id,
        pdf_path=str(body.get("pdf_path") or "").strip(),
        title=str(body.get("title") or "").strip(),
        write_feishu=body.get("write_feishu"),
    )


def _api_submit(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(body.get("user_id") or "").strip()
    push_id = str(body.get("push_id") or "").strip()
    if not user_id or not push_id:
        raise ValueError("user_id and push_id are required")
    return agents.submit_and_read(
        user_id=user_id,
        push_id=push_id,
        selected_numbers=body.get("selected_numbers") or [],
        skipped_numbers=body.get("skipped_numbers") or [],
        later_numbers=body.get("later_numbers") or [],
        generate_reports=bool(body.get("generate_reports", True)),
        write_feishu=body.get("write_feishu"),
    )


def _api_wiki_ask(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.wiki_ask(
        user_id=str(body.get("user_id") or "").strip(),
        question=str(body.get("question") or "").strip(),
        scope=str(body.get("scope") or "all").strip(),
        limit=int(body.get("limit") or 8),
        mentions=body.get("mentions") or [],
    )


def _api_wiki_node(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.update_wiki_node(
        user_id=str(body.get("user_id") or "").strip(),
        node_id=str(body.get("node_id") or "").strip(),
        title=str(body.get("title") or "").strip(),
        body=str(body.get("body") or ""),
    )


def _api_export(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.export_data(
        user_id=str(body.get("user_id") or "").strip(),
        export_format=str(body.get("format") or "markdown").strip(),
    )


def _api_must_read_update(_query_params: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    return agents.update_must_read(
        user_id=str(body.get("user_id") or "").strip(),
        item_type=str(body.get("item_type") or "").strip(),
        value=str(body.get("value") or "").strip(),
        action=str(body.get("action") or "").strip(),
    )


GET_ROUTES: Dict[str, ApiHandler] = {
    "/api/health": _api_health,
    "/api/settings": _api_settings,
    "/api/source-options": _api_source_options,
    "/api/users": _api_users,
    "/api/roles": _api_roles,
    "/api/profile": _api_profile,
    "/api/latest-push": _api_latest_push,
    "/api/daily/status": _api_daily_status,
    "/api/wiki/stats": _api_wiki_stats,
    "/api/wiki/search": _api_wiki_search,
    "/api/wiki/graph": _api_wiki_graph,
    "/api/activity": _api_activity,
    "/api/reports": _api_reports,
    "/api/reports/content": _api_report_content,
    "/api/must-read": _api_must_read,
}

POST_ROUTES: Dict[str, ApiHandler] = {
    "/api/provider-test": _api_provider_test,
    "/api/settings": _api_save_settings,
    "/api/profile": _api_create_profile,
    "/api/roles": _api_update_roles,
    "/api/daily": _api_daily,
    "/api/daily/start": _api_daily_start,
    "/api/feedback": _api_feedback,
    "/api/read": _api_read,
    "/api/read/arxiv": _api_read_arxiv,
    "/api/read/pdf": _api_read_pdf,
    "/api/submit": _api_submit,
    "/api/wiki/ask": _api_wiki_ask,
    "/api/wiki/ask/stream": _api_wiki_ask,
    "/api/wiki/node": _api_wiki_node,
    "/api/export": _api_export,
    "/api/must-read": _api_must_read_update,
}


class PaperFlowGuiHandler(BaseHTTPRequestHandler):
    server_version = "PaperFlowGUI/0.1"

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"ok": False, "error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime = f"{mime}; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_api(self, routes: Dict[str, ApiHandler], body: Dict[str, Any] | None = None) -> None:
        path, query_params = _query(self.path)
        route = routes.get(path)
        if route is None:
            self._send_json({"ok": False, "error": f"Unknown API route: {path}"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            payload = route(query_params, body or {})
            self._send_json({"ok": True, **payload})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _send_sse_event(self, event: str, payload: Dict[str, Any]) -> None:
        self.wfile.write(_sse_bytes(event, payload))
        self.wfile.flush()

    def _handle_wiki_ask_stream(self, body: Dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self._send_sse_event("status", {"text": "正在检索本地 Wiki 与引用来源"})
            for event in agents.wiki_ask_stream(
                user_id=str(body.get("user_id") or "").strip(),
                question=str(body.get("question") or "").strip(),
                scope=str(body.get("scope") or "all").strip(),
                limit=int(body.get("limit") or 8),
                mentions=body.get("mentions") or [],
            ):
                self._send_sse_event(str(event.get("event") or "message"), {"ok": True, **(event.get("data") or {})})
        except Exception as exc:
            self._send_sse_event("error", {"ok": False, "error": str(exc)})

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        path, _query_params = _query(self.path)
        if path.startswith("/api/"):
            self._handle_api(GET_ROUTES)
            return
        if path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return
        if path == "/favicon.ico":
            self._send_file(STATIC_DIR / "favicon.svg")
            return
        requested = (STATIC_DIR / path.lstrip("/")).resolve()
        try:
            requested.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_json({"ok": False, "error": "Invalid path"}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_file(requested)

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        try:
            body = _read_json(self)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        path, _query_params = _query(self.path)
        if path == "/api/wiki/ask/stream":
            self._handle_wiki_ask_stream(body)
            return
        self._handle_api(POST_ROUTES, body)

    def log_message(self, fmt: str, *args: Any) -> None:
        path, _query_params = _query(self.path)
        if path == "/api/daily/status":
            return
        sys.stdout.write("[gui] " + fmt % args + "\n")


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, int(port)), PaperFlowGuiHandler)
    url = f"http://{host}:{port}"
    print(f"PaperFlow GUI running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PaperFlow GUI...")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PaperFlow local web GUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args(argv)
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
