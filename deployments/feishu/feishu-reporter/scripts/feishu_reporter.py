#!/usr/bin/env python3
"""
Feishu Reporter - 飞书消息发送工具

在 Windows 上，`im +messages-send` 经过 shell 转义后容易出现：
- 中文被替换成 `?`
- 多行文本被截断
- `post` 的 JSON 被错误解析

这里统一改为通过 `lark-cli api POST /open-apis/im/v1/messages`
直接发送原始消息体，避免这些问题。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _resolve_feishu_cli() -> str:
    """Locate the most stable lark-cli entrypoint for the current platform."""
    candidates = [
        os.environ.get("FEISHU_CLI_CMD"),
        os.path.expanduser("~/npm-global/node_modules/@larksuite/cli/bin/lark-cli.exe"),
        shutil.which("lark-cli.exe"),
        shutil.which("lark-cli.cmd"),
        shutil.which("lark-cli"),
        shutil.which("lark"),
        os.path.expanduser("~/npm-global/lark-cli.cmd"),
        os.path.expanduser("~/npm-global/lark-cli"),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    for candidate in candidates:
        if candidate:
            return candidate

    raise FileNotFoundError(
        "Unable to find lark-cli. Set FEISHU_CLI_CMD or install lark-cli first."
    )


FEISHU_CLI_CMD = _resolve_feishu_cli()
CURRENT_USER_ID = os.environ.get("FEISHU_USER_ID", "")
DEFAULT_IM_IDENTITY = os.environ.get("FEISHU_IM_IDENTITY", "bot")
RECENT_OUTBOUND_TEXT_MESSAGES: Dict[str, float] = {}
OUTBOUND_TEXT_TTL_SECONDS = 120.0


def _sanitize_download_filename(file_name: str, fallback_name: str) -> str:
    """Keep downloaded file names Windows-safe and preserve useful extensions."""
    candidate = (file_name or "").strip() or fallback_name
    candidate = os.path.basename(candidate)
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", candidate)
    candidate = candidate.strip(" .") or fallback_name
    if "." not in candidate and "." in fallback_name:
        candidate = f"{candidate}{os.path.splitext(fallback_name)[1]}"
    return candidate


def download_file_from_feishu(
    message_id: str,
    file_key: str,
    file_name: Optional[str] = None,
    save_dir: Optional[str] = None,
) -> str:
    """
    从飞书下载文件

    Args:
        message_id: 消息 ID
        file_key: 文件 key（从消息内容中获取）
        file_name: 原始文件名（用于保留扩展名）
        save_dir: 保存目录（默认临时目录）

    Returns:
        本地文件路径
    """
    if save_dir is None:
        save_dir = tempfile.gettempdir()
    os.makedirs(save_dir, exist_ok=True)

    fallback_name = f"{os.path.basename(file_key)}.bin"
    safe_file_name = _sanitize_download_filename(file_name or "", fallback_name)
    save_path = os.path.join(save_dir, safe_file_name)

    params = {"type": "file"}
    args = [
        FEISHU_CLI_CMD,
        "api",
        "GET",
        f"/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
        "--as",
        DEFAULT_IM_IDENTITY,
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--output",
        safe_file_name,
    ]

    # 设置环境变量禁用 Git Bash 路径转换
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=save_dir,
        env=env,
    )

    if result.returncode == 0 and os.path.exists(save_path):
        return save_path

    _parse_cli_output(result.stdout, result.stderr)
    raise RuntimeError(f"Failed to download file: {file_key}")


def _parse_cli_output(stdout: str, stderr: str) -> Dict[str, Any]:
    """Parse JSON returned by lark-cli and raise on API failures."""
    for raw in (stdout, stderr):
        text = (raw or "").strip()
        if not text:
            continue

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            if payload.get("ok") is False:
                error = payload.get("error", {})
                message = error.get("message") or text
                raise RuntimeError(f"Feishu API error: {message}")
            if "code" in payload and payload.get("code") not in (0, "0", None):
                message = payload.get("msg") or text
                raise RuntimeError(f"Feishu API error: {message}")

        return payload

    combined = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    raise RuntimeError(f"Feishu CLI error: {combined or 'empty response'}")


def _prune_outbound_text_cache(now: Optional[float] = None) -> None:
    current = time.time() if now is None else now
    expired_keys = [
        key for key, created_at in RECENT_OUTBOUND_TEXT_MESSAGES.items()
        if current - created_at > OUTBOUND_TEXT_TTL_SECONDS
    ]
    for key in expired_keys:
        RECENT_OUTBOUND_TEXT_MESSAGES.pop(key, None)


def _remember_outbound_text(receive_type: str, receive_id: str, text: str) -> None:
    normalized = (text or "").strip()
    if not receive_id or not normalized:
        return
    _prune_outbound_text_cache()
    RECENT_OUTBOUND_TEXT_MESSAGES[f"{receive_type}:{receive_id}:{normalized}"] = time.time()


def is_recent_outbound_text(receive_type: str, receive_id: str, text: str) -> bool:
    normalized = (text or "").strip()
    if not receive_id or not normalized:
        return False
    _prune_outbound_text_cache()
    return f"{receive_type}:{receive_id}:{normalized}" in RECENT_OUTBOUND_TEXT_MESSAGES


def _run_cli(
    args: List[str],
    *,
    input_text: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    # MSYS / Git-Bash on Windows rewrites `/open-apis/...` arguments into
    # `C:/Program Files/Git/open-apis/...` before they reach lark-cli, which
    # makes every `api POST /open-apis/...` request return HTTP 404. Disable
    # path conversion so API paths survive intact regardless of the shell that
    # launched the parent Python process.
    effective_env = dict(env if env is not None else os.environ)
    effective_env.setdefault("MSYS_NO_PATHCONV", "1")
    effective_env.setdefault("MSYS2_ARG_CONV_EXCL", "*")

    result = subprocess.run(
        [FEISHU_CLI_CMD, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        input=input_text,
        cwd=cwd,
        env=effective_env,
    )
    return _parse_cli_output(result.stdout, result.stderr)


def _extract_doc_token(payload: Dict[str, Any]) -> Optional[str]:
    """Best-effort extract a doc token from common create-doc response shapes."""
    if not isinstance(payload, dict):
        return None

    direct_candidates = [
        payload.get("obj_token"),
        payload.get("document_id"),
        payload.get("token"),
    ]
    for candidate in direct_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    data = payload.get("data")
    if isinstance(data, dict):
        nested_candidates = [
            data.get("obj_token"),
            data.get("document_id"),
            data.get("token"),
        ]
        document = data.get("document")
        if isinstance(document, dict):
            nested_candidates.extend(
                [
                    document.get("obj_token"),
                    document.get("document_id"),
                    document.get("token"),
                ]
            )

        for candidate in nested_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    return None


def get_drive_meta(doc_token: str, doc_type: str = "docx", with_url: bool = True) -> Dict[str, Any]:
    """Fetch Drive metadata for a document token."""
    body = {
        "request_docs": [{"doc_token": doc_token, "doc_type": doc_type}],
        "with_url": with_url,
    }
    return _run_cli(
        [
            "drive",
            "metas",
            "batch_query",
            "--as",
            DEFAULT_IM_IDENTITY,
            "--data",
            json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        ]
    )


def _send_api_message(
    user_id: str,
    msg_type: str,
    content: Dict[str, Any],
    identity: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a message through the raw IM API so Unicode and structure survive intact."""
    body = {
        "receive_id": user_id,
        "msg_type": msg_type,
        "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
    }
    params = {"receive_id_type": "open_id"}

    return _run_cli(
        [
            "api",
            "POST",
            "/open-apis/im/v1/messages",
            "--as",
            identity or DEFAULT_IM_IDENTITY,
            "--params",
            json.dumps(params, ensure_ascii=False, separators=(",", ":")),
            "--data",
            json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        ]
    )


def _markdown_to_text(markdown: str) -> str:
    """
    Keep Markdown-looking text as plain text.

    The raw IM API does not accept `markdown` as a message type. For this project,
    plain text with preserved newlines is more reliable than `im +messages-send --markdown`
    on Windows.
    """
    return markdown


def send_text(user_id: str, text: str, use_chat_id: bool = False) -> Dict[str, Any]:
    """
    发送纯文本消息

    Args:
        user_id: 用户 open_id 或 chat_id
        text: 消息内容
        use_chat_id: 如果 True，user_id 被视为 chat_id；否则视为 open_id
    """
    if use_chat_id:
        return send_to_chat(user_id, "text", {"text": text})
    result = _send_api_message(user_id, "text", {"text": text})
    _remember_outbound_text("open_id", user_id, text)
    return result


def send_markdown(user_id: str, markdown: str) -> Dict[str, Any]:
    """发送 Markdown 风格内容，内部按多行纯文本发送。"""
    return send_text(user_id, _markdown_to_text(markdown))


def send_post(user_id: str, title: str, content: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """发送 post 富文本消息。"""
    payload = {
        "zh_cn": {
            "title": title,
            "content": content,
        }
    }
    return _send_api_message(user_id, "post", payload)


def send_daily_push(user_id: str, push_card: str) -> Dict[str, Any]:
    """发送每日推送，保留全文换行和编号。"""
    return send_text(user_id, push_card)


def send_to_chat(chat_id: str, msg_type: str, content: Dict[str, Any], identity: Optional[str] = None) -> Dict[str, Any]:
    """
    发送消息到飞书群聊

    Args:
        chat_id: 群聊 ID
        msg_type: 消息类型 (text, post, markdown)
        content: 消息内容
        identity: 发送身份（可选，用于多角色）

    Returns:
        API 响应
    """
    body = {
        "receive_id": chat_id,
        "msg_type": msg_type,
        "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
    }
    params = {"receive_id_type": "chat_id"}

    result = _run_cli([
        "api",
        "POST",
        "/open-apis/im/v1/messages",
        "--as",
        identity or DEFAULT_IM_IDENTITY,
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--data",
        json.dumps(body, ensure_ascii=False, separators=(",", ":")),
    ])
    if msg_type == "text":
        _remember_outbound_text("chat_id", chat_id, content.get("text", ""))
    return result


def send_text_to_chat(chat_id: str, text: str, identity: Optional[str] = None) -> Dict[str, Any]:
    """发送文本消息到群聊"""
    return send_to_chat(chat_id, "text", {"text": text}, identity)


def send_post_to_chat(chat_id: str, title: str, content: List[List[Dict[str, Any]]], identity: Optional[str] = None) -> Dict[str, Any]:
    """发送 post 消息到群聊"""
    payload = {
        "zh_cn": {
            "title": title,
            "content": content,
        }
    }
    return send_to_chat(chat_id, "post", payload, identity)


def create_doc(title: str, content: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
    """
    创建飞书文档

    Args:
        title: 文档标题
        content: 文档内容（Markdown 格式）
        folder_id: 文件夹 ID（可选，默认存到根目录）

    Returns:
        文档信息 {"obj_token": "...", "url": "..."}
    """
    try:
        args = [
            "docs",
            "+create",
            "--as",
            DEFAULT_IM_IDENTITY,
            "--title",
            title,
            "--markdown",
            "-",
        ]
        if folder_id:
            args.extend(["--folder-token", folder_id])

        result = _run_cli(args, input_text=content or "")

        data = result.get("data", {}) if isinstance(result, dict) else {}
        if isinstance(data, dict):
            if data.get("doc_id"):
                result.setdefault("obj_token", data["doc_id"])
            if data.get("doc_url"):
                result["url"] = data["doc_url"]

        doc_token = _extract_doc_token(result)
        if doc_token:
            result.setdefault("obj_token", doc_token)

        return result
    except Exception:
        body = {
            "title": title,
            "content": content,
            "folder_token": folder_id,
        }

        result = _run_cli([
            "api",
            "POST",
            "/open-apis/docx/v1/documents",
            "--as",
            DEFAULT_IM_IDENTITY,
            "--data",
            json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        ])

        doc_token = _extract_doc_token(result)
        if doc_token:
            result.setdefault("obj_token", doc_token)
        return result


def get_user_info(user_id: Optional[str] = None) -> Dict[str, Any]:
    """获取用户信息。暂未实现，保留接口以兼容调用方。"""
    raise NotImplementedError("get_user_info not yet implemented")


if __name__ == "__main__":
    print("Testing Feishu API...")

    try:
        result = send_text(CURRENT_USER_ID, "Test from Feishu Reporter API")
        print("Send text result:", json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print("Send text error:", exc)

    try:
        result = send_post(
            CURRENT_USER_ID,
            "Test Post",
            [
                [{"tag": "text", "text": "Line 1"}],
                [{"tag": "text", "text": "Line 2"}],
                [{"tag": "text", "text": "Line 3"}],
            ],
        )
        print("Send post result:", json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print("Send post error:", exc)
