#!/usr/bin/env python3
"""
飞书 Webhook 服务器 - 接收飞书开放平台的事件订阅

支持的事件类型：
1. 用户消息（机器人收到消息）
2. 按钮点击（交互组件）
3. 菜单选择
4. 表单提交

服务器会：
1. 验证飞书的 URL 验证请求
2. 接收并解析事件
3. 路由到对应的 Agent 处理
"""

import sys
import os
import json
import hashlib
import hmac
import base64
import importlib
import re
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import parse_qs, urlparse
import logging
import threading
import time

# 添加项目根目录到路径（webhook_server.py 在 services/webhook-server/scripts/）
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.normpath(os.path.join(script_dir, "..", "..", ".."))
sys.path.insert(0, project_root)
PROJECT_ROOT_PATH = Path(project_root)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook-server")

logger.info(f"Project root: {project_root}")


BOT_MESSAGE_PREFIXES = (
    "📰 今日论文",
    "📋 你的学术画像",
    "📊 你的学术画像周度报告",
    "📫 精读报告已生成",
    "📚 精读报告已生成",
    "SciTaste 学术画像确认",
    "收到，",
    "收到 PDF，",
    "当前已有一个",
    "当前已有相同任务在处理中",
    "📊 今日反馈已记录",
    "抱歉，",  # 未知意图回复，避免回声触发
    "已增强你对",
    "已下调你对",
    "已将 ",
)

PROCESSED_MESSAGE_IDS: Dict[str, float] = {}
MESSAGE_ID_TTL_SECONDS = 600
RECENT_TEXT_MESSAGE_FINGERPRINTS: Dict[str, float] = {}
TEXT_MESSAGE_FINGERPRINT_TTL_SECONDS = 5
ASYNC_INTENT_ACKS = {
    "cold_start": "收到，正在生成学术画像，完成后会把结果发到本群。",
    "daily_push": "收到，正在抓取并排序今日论文，稍后把结果发到本群。",
    "feedback": "收到，正在处理你的反馈和精读任务，结果会发到本群。",
    "reading_report": "收到，正在生成精读报告，完成后会把链接发到本群。",
    "weekly_report": "收到，正在生成周报，完成后会把结果发到本群。",
}
ASYNC_INTENT_DUPLICATE_ACKS = {
    "cold_start": "当前已有一个冷启动任务在处理中，请稍候查看本群结果。",
    "daily_push": "当前已有一个推送任务在处理中，请稍候查看本群结果。",
    "feedback": "当前已有一个反馈处理任务在运行，请稍候查看本群结果。",
    "reading_report": "当前已有一个精读报告任务在处理中，请稍候查看本群结果。",
    "weekly_report": "当前已有一个周报任务在处理中，请稍候查看本群结果。",
}
PDF_ASYNC_ACK = "收到 PDF，正在生成精读报告，请稍候..."
RECENT_UPLOAD_INTEREST_WINDOW_MINUTES = 30
INFLIGHT_COORDINATOR_TASKS: set[str] = set()
INFLIGHT_COORDINATOR_TASKS_LOCK = threading.Lock()
ASYNC_TASK_LOCK_DIR = PROJECT_ROOT_PATH / "data" / "webhook_task_locks"


def looks_like_recent_upload_interest_reinforcement(text: str) -> bool:
    """Detect short follow-up phrases that likely refer to the latest uploaded PDF."""
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    anchor_tokens = ("这类", "这种", "这一类", "这篇", "这个方向", "这条线")
    intent_tokens = (
        "想多看",
        "想多读",
        "想多关注",
        "想继续看",
        "想继续读",
        "更想看",
        "更感兴趣",
    )
    return any(anchor in normalized for anchor in anchor_tokens) and any(token in normalized for token in intent_tokens)


def get_async_task_lock_ttl_seconds() -> int:
    raw = os.environ.get("SCITASTE_ASYNC_TASK_LOCK_TTL_SECONDS", "1800").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 1800


def _get_async_task_lock_path(task_key: str) -> Path:
    digest = hashlib.sha256(task_key.encode("utf-8")).hexdigest()
    return ASYNC_TASK_LOCK_DIR / f"{digest}.json"


def _read_async_task_lock(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _acquire_async_task_lock(task_key: str) -> bool:
    ASYNC_TASK_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _get_async_task_lock_path(task_key)
    now = time.time()
    ttl_seconds = get_async_task_lock_ttl_seconds()

    for _ in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            payload = _read_async_task_lock(lock_path)
            created_at = float(payload.get("created_at", 0.0) or 0.0)
            if created_at and (now - created_at) <= ttl_seconds:
                return False
            try:
                lock_path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                return False
            continue

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "task_key": task_key,
                        "created_at": now,
                        "pid": os.getpid(),
                    },
                    handle,
                    ensure_ascii=False,
                )
            return True
        except Exception:
            try:
                lock_path.unlink()
            except OSError:
                pass
            return False

    return False


def _release_async_task_lock(task_key: str) -> None:
    try:
        _get_async_task_lock_path(task_key).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def clear_async_task_locks_on_startup() -> int:
    """Clear persistent async task locks from previous runs before serving requests."""
    try:
        if not ASYNC_TASK_LOCK_DIR.exists():
            return 0
    except OSError:
        return 0

    removed = 0
    for lock_path in ASYNC_TASK_LOCK_DIR.glob("*.json"):
        try:
            lock_path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def is_likely_bot_echo(text: str) -> bool:
    """Filter bot-authored push/profile/feedback messages that Feishu echoes back."""
    normalized = (text or "").strip()
    if not normalized:
        return False

    if any(normalized.startswith(prefix) for prefix in BOT_MESSAGE_PREFIXES):
        return True

    if "选择方式（任选）" in normalized and "快捷命令" in normalized:
        return True

    if "今日反馈已记录" in normalized and "画像已更新" in normalized:
        return True

    if "你的学术画像" in normalized and "你可以直接说：" in normalized:
        return True

    if "你的学术画像周度报告" in normalized and "推送论文总数" in normalized:
        return True

    if normalized.startswith("已增强你对") and ("同步更新方向：" in normalized or "你的学术画像" in normalized):
        return True

    if normalized.startswith("已下调你对") and ("同步更新方向：" in normalized or "你的学术画像" in normalized):
        return True

    if normalized.startswith("已将 ") and ("权重从" in normalized or "你的学术画像" in normalized):
        return True

    if "Reading reports created (" in normalized and "Open the links above to start reading." in normalized:
        return True

    if "Reading reports created (" in normalized and "doc_token:" in normalized:
        return True

    if normalized.startswith("精读报告已生成："):
        return True

    if normalized.startswith("收到 PDF，") and "正在生成精读报告" in normalized:
        return True

    if "精读任务已执行，但这次没有成功生成文档链接" in normalized:
        return True

    if normalized.startswith("[精读]"):
        return True

    if "[精读]" in normalized and "本群成员" in normalized and "可阅读" in normalized:
        return True

    if "必读清单" in normalized and "添加方式：" in normalized and "移除方式：" in normalized:
        return True

    if "学术画像已更新" in normalized and "最后更新" in normalized and "你可以随时回复调整" in normalized:
        return True

    return False


def _is_recent_outbound_bot_message(chat_id: str, text: str) -> bool:
    normalized = (text or "").strip()
    if not chat_id or not normalized:
        return False

    try:
        feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
    except Exception:
        return False

    checker = getattr(feishu_reporter, "is_recent_outbound_text", None)
    if not callable(checker):
        return False

    try:
        return bool(checker("chat_id", chat_id, normalized))
    except Exception:
        return False


def is_duplicate_message(message_id: str) -> bool:
    """Deduplicate retried Feishu messages within a short TTL window."""
    if not message_id:
        return False

    now = time.time()
    expired_ids = [
        cached_id for cached_id, cached_at in PROCESSED_MESSAGE_IDS.items()
        if now - cached_at > MESSAGE_ID_TTL_SECONDS
    ]
    for cached_id in expired_ids:
        PROCESSED_MESSAGE_IDS.pop(cached_id, None)

    if message_id in PROCESSED_MESSAGE_IDS:
        return True

    PROCESSED_MESSAGE_IDS[message_id] = now
    return False


def is_duplicate_text_message(chat_id: str, open_id: str, text: str) -> bool:
    """Deduplicate retried text messages even when Feishu assigns a new message_id."""
    normalized = (text or "").strip()
    if not normalized:
        return False

    fingerprint_source = f"{chat_id}|{open_id}|{normalized}"
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    now = time.time()

    expired_fingerprints = [
        cached_key for cached_key, cached_at in RECENT_TEXT_MESSAGE_FINGERPRINTS.items()
        if now - cached_at > TEXT_MESSAGE_FINGERPRINT_TTL_SECONDS
    ]
    for cached_key in expired_fingerprints:
        RECENT_TEXT_MESSAGE_FINGERPRINTS.pop(cached_key, None)

    if fingerprint in RECENT_TEXT_MESSAGE_FINGERPRINTS:
        return True

    RECENT_TEXT_MESSAGE_FINGERPRINTS[fingerprint] = now
    return False


def looks_like_pdf_attachment(msg_type: str, content: Dict[str, Any]) -> bool:
    """Only route genuine user-uploaded PDF files into the PDF reading flow."""
    file_name = str(content.get("file_name") or content.get("name") or content.get("title") or "").strip()
    file_type = str(content.get("file_type") or content.get("type") or "").strip().lower()
    file_url = str(content.get("file_url") or "").strip().lower()

    if file_name.lower().endswith(".pdf"):
        return True
    if file_type == "pdf":
        return True
    if ".pdf" in file_url:
        return True

    # Be conservative: if Feishu is sending a generic file card/share without a
    # clear PDF suffix, do not recurse into the reading-report pipeline.
    return False


class FeishuEventHandler:
    """飞书事件处理器"""

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        self.verification_token = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")

    def _resolve_user_id_for_chat(self, chat_id: str, open_id: str) -> str:
        """Resolve the stable user_id used by the coordinator / reading flows."""
        role_name = self._find_role_by_chat_id(chat_id)
        if role_name:
            return f"user_{role_name}"
        return open_id

    def _find_existing_pdf_report(self, user_id: str, source_type: str, source_key: str) -> Optional[Dict[str, Any]]:
        """Check whether the same uploaded PDF has already produced a report."""
        if not user_id or not source_type or not source_key:
            return None

        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            finder = getattr(db_ops, "get_recent_created_report_by_source", None)
            if not callable(finder):
                return None
            return finder(user_id, source_type, source_key)
        except Exception as exc:
            logger.warning(f"Failed to look up existing PDF report: {exc}")
            return None

    def _find_recent_pdf_interest_signal(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return the latest direct-upload reading signal for a user."""
        if not user_id:
            return None

        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            finder = getattr(db_ops, "get_recent_reading_signal", None)
            if not callable(finder):
                return None
            return finder(
                user_id,
                minutes=RECENT_UPLOAD_INTEREST_WINDOW_MINUTES,
                source_prefix="",
            )
        except Exception as exc:
            logger.warning(f"Failed to fetch recent PDF interest signal: {exc}")
            return None

    def _log_doc_open(self, user_id: str, *, doc_url: str, doc_token: str = "", title: str = "") -> None:
        if not user_id or not doc_url:
            return
        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            logger_fn = getattr(db_ops, "log_behavior", None)
            if not callable(logger_fn):
                return
            logger_fn(
                user_id=user_id,
                push_id="reading_report",
                paper_id=None,
                action="opened_report",
                action_type="doc_open",
                category="reading_report",
                metadata={
                    "doc_url": doc_url,
                    "doc_token": doc_token,
                    "paper_title": title,
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to log doc open: {exc}")

    def _log_pending_doc_dwell_proxy(self, user_id: str) -> None:
        if not user_id:
            return
        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            finder = getattr(db_ops, "get_pending_doc_open_for_dwell", None)
            logger_fn = getattr(db_ops, "log_behavior", None)
            if not callable(finder) or not callable(logger_fn):
                return
            pending = finder(user_id, within_minutes=240)
            if not pending:
                return
            opened_at = datetime.fromisoformat(str(pending.get("timestamp")).replace("Z", "+00:00"))
            now = datetime.now(opened_at.tzinfo) if opened_at.tzinfo else datetime.now()
            dwell_seconds = max(0.0, min(7200.0, (now - opened_at).total_seconds()))
            if dwell_seconds < 5:
                return
            metadata = pending.get("metadata", {}) or {}
            logger_fn(
                user_id=user_id,
                push_id="reading_report",
                paper_id=pending.get("paper_id"),
                action="doc_dwell_proxy",
                action_type="doc_engagement",
                category="reading_report",
                metadata={
                    "doc_url": metadata.get("doc_url", ""),
                    "doc_token": metadata.get("doc_token", ""),
                    "paper_title": metadata.get("paper_title", ""),
                    "dwell_seconds": round(dwell_seconds, 2),
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to log doc dwell proxy: {exc}")

    def _handle_recent_upload_interest_reinforcement(
        self,
        user_id: str,
        chat_id: str,
        open_id: str,
        text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Treat phrases like “这类我最近想多看” as a strong signal for the latest uploaded PDF topics.
        """
        if not looks_like_recent_upload_interest_reinforcement(text):
            return None

        recent_signal = self._find_recent_pdf_interest_signal(user_id)
        if not recent_signal:
            return None

        topics = recent_signal.get("topics") or []
        if not topics:
            return None

        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
            direction_lexicon = importlib.import_module("config.direction_lexicon")

            get_profile = getattr(db_ops, "get_profile")
            update_profile = getattr(db_ops, "update_profile")
            log_behavior = getattr(db_ops, "log_behavior")
            ensure_profile_schema = getattr(profile_updater, "ensure_profile_schema")
            update_profile_with_reading_signal = getattr(profile_updater, "update_profile_with_reading_signal")

            signal_time = datetime.now()
            profile = ensure_profile_schema(get_profile(user_id), now=signal_time)
            updated_profile = update_profile_with_reading_signal(
                profile,
                signal_topics=list(topics),
                signal_strength="strong",
                explicit_text=text,
                current_time=signal_time,
                source_type=recent_signal.get("source_type") or "",
                source_key=recent_signal.get("source_key") or "",
            )
            update_profile(user_id, updated_profile)

            last_signal = (
                (updated_profile.get("reading_signal_state", {}) or {}).get("last_signal", {}) or {}
            )
            activated_topics = last_signal.get("activated_topics", []) or []

            log_behavior(
                user_id=user_id,
                push_id="reading_signal",
                paper_id=recent_signal.get("paper_id"),
                action="profile_updated",
                action_type="reading_signal",
                category="strong",
                metadata={
                    "signal_strength": "strong",
                    "signal_topics": list(last_signal.get("topics", []) or topics),
                    "activated_topics": list(activated_topics),
                    "source_type": last_signal.get("source_type") or recent_signal.get("source_type") or "",
                    "source_key": last_signal.get("source_key") or recent_signal.get("source_key") or "",
                    "trigger": "recent_upload_followup_text",
                    "explicit_note": text,
                },
            )

            label_formatter = getattr(direction_lexicon, "format_direction_label", None)
            if callable(label_formatter):
                topic_labels = [label_formatter(topic, prefer_chinese=True) for topic in (last_signal.get("topics") or topics)[:3]]
                activated_labels = [label_formatter(topic, prefer_chinese=True) for topic in activated_topics[:3]]
            else:
                topic_labels = [str(topic) for topic in (last_signal.get("topics") or topics)[:3]]
                activated_labels = [str(topic) for topic in activated_topics[:3]]

            summary = f"收到，已把最近这篇直传论文对应的方向按强正信号记入画像：{'、'.join(topic_labels)}。"
            if activated_labels:
                summary += f"\n已进入短期兴趣关注：{'、'.join(activated_labels)}。"
            else:
                summary += "\n这次会先按强正信号处理，但不会立刻触发整体兴趣漂移。"

            self._send_async_ack(chat_id, open_id, summary)
            return {
                "status": "success",
                "intent": "reading_signal_reinforce",
                "user_id": user_id,
                "chat_id": chat_id,
                "topics": list(last_signal.get("topics", []) or topics),
                "activated_topics": list(activated_topics),
            }
        except Exception as exc:
            logger.error(f"Failed to reinforce recent upload interest signal: {exc}", exc_info=True)
            self._send_async_ack(
                chat_id,
                open_id,
                "我识别到你是在增强最近直传论文的兴趣信号，但这次更新失败了，请稍后再试。",
            )
            return {
                "status": "error",
                "intent": "reading_signal_reinforce",
                "user_id": user_id,
                "chat_id": chat_id,
                "message": str(exc),
            }

    def verify_url(self, token: str, challenge: str) -> str:
        """
        验证飞书 URL

        飞书开放平台会发送验证请求来确认 URL 有效性
        需要返回 challenge 参数

        Args:
            token: 验证 token
            challenge: 挑战字符串

        Returns:
            challenge 字符串
        """
        if token != self.verification_token:
            logger.error(f"Verification token mismatch")
            return ""

        logger.info("URL verification successful")
        return challenge

    def verify_signature(self, body: bytes, signature: str, timestamp: str) -> bool:
        """
        验证请求签名

        Args:
            body: 请求体
            signature: 签名
            timestamp: 时间戳

        Returns:
            是否验证通过
        """
        # 构建待签名字符串：timestamp + body
        sign_str = timestamp + body.decode('utf-8')

        # 使用 app_secret 进行 HMAC-SHA256 签名
        signature_computed = hmac.new(
            self.app_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).digest()

        # Base64 编码
        signature_b64 = base64.b64encode(signature_computed).decode('utf-8')

        return hmac.compare_digest(signature_b64, signature)

    def handle_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理飞书事件

        Args:
            event: 事件数据

        Returns:
            响应数据
        """
        header = event.get("header", {})
        event_type = header.get("event_type", "")

        logger.info(f"Received event type: {event_type}")

        # 根据事件类型路由
        if event_type == "im.message.receive_v1":
            return self._handle_message(event)
        elif event_type == "im.message.react_v1":
            return self._handle_reaction(event)
        elif event_type == "menu.button":
            return self._handle_menu_button(event)
        else:
            logger.info(f"Unhandled event type: {event_type}")
            return {"status": "ignored"}

    def _handle_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理用户消息

        Args:
            event: 消息事件

        Returns:
            处理结果
        """
        message = event.get("event", {}).get("message", {})
        sender = event.get("event", {}).get("sender", {})

        chat_id = message.get("chat_id", "")
        message_id = message.get("message_id", "")
        msg_type = message.get("msg_type", "")
        content_raw = message.get("content", "{}")

        # 解析消息内容
        try:
            content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        except json.JSONDecodeError:
            content = {"text": content_raw}

        text = content.get("text", "")
        file_url = content.get("file_url", "")
        file_key = content.get("file_key", "")
        file_name = content.get("file_name", "")
        user_id = sender.get("sender_id", {}).get("user_id", "")
        open_id = sender.get("sender_id", {}).get("open_id", "")
        sender_type = sender.get("sender_type", "")

        # 过滤 Bot 自己发送的消息（避免循环）
        if sender_type == "app_bot":
            logger.info(f"Ignoring message from bot (sender_type=app_bot)")
            return {"status": "ignored", "reason": "bot_self_message"}

        if is_duplicate_message(message_id):
            logger.info(f"Ignoring duplicate message retry: {message_id}")
            return {"status": "ignored", "reason": "duplicate_message"}

        if msg_type == "text" and is_duplicate_text_message(chat_id, open_id, text):
            logger.info(f"Ignoring duplicate text payload in chat {chat_id}: {text[:50]}...")
            return {"status": "ignored", "reason": "duplicate_text_message"}

        if msg_type == "text" and _is_recent_outbound_bot_message(chat_id, text):
            logger.info("Ignoring recent outbound bot text echoed back by Feishu")
            return {"status": "ignored", "reason": "recent_outbound_bot_message"}

        # 检查消息是否是 Bot 回声消息（send-as-user 时 sender_type 不可靠）
        if is_likely_bot_echo(text):
            logger.info("Ignoring likely bot echo based on message content")
            return {"status": "ignored", "reason": "likely_bot_message"}

        # 检测文件消息：只有明确的 PDF 才进入精读报告流程
        if file_key or file_url:
            if looks_like_pdf_attachment(msg_type, content):
                logger.info(
                    "PDF file message detected: msg_type=%s, file_key=%s, file_name=%s, file_url=%s",
                    msg_type,
                    file_key,
                    file_name,
                    file_url,
                )
                source_type = "feishu_file_key" if file_key else "feishu_file_url"
                source_key = file_key or file_url
                resolved_user_id = self._resolve_user_id_for_chat(chat_id, open_id)
                existing_report = self._find_existing_pdf_report(resolved_user_id, source_type, source_key)
                if existing_report:
                    logger.info(
                        "Ignoring already-processed PDF upload event: user_id=%s, %s=%s",
                        resolved_user_id,
                        source_type,
                        source_key,
                    )
                    return {
                        "status": "ignored",
                        "reason": "duplicate_pdf_file_message",
                        "source": "pdf",
                        "chat_id": chat_id,
                    }

                file_identity = file_key or file_url or message_id
                task_key = f"pdf:{chat_id}:{open_id}:{file_identity}"
                if not self._register_async_task(task_key):
                    logger.info(f"Ignoring duplicate in-flight async PDF task for {task_key}")
                    return {
                        "status": "ignored",
                        "reason": "duplicate_pdf_inflight",
                        "source": "pdf",
                        "chat_id": chat_id,
                    }

                self._send_async_ack_async(chat_id, open_id, PDF_ASYNC_ACK)
                self._route_pdf_reading_report_async(task_key, message_id, file_key, file_name, chat_id, open_id)
                return {
                    "status": "accepted",
                    "mode": "async",
                    "intent": "reading_report",
                    "source": "pdf",
                    "chat_id": chat_id,
                }

            logger.info(
                "Ignoring non-PDF file-like message: msg_type=%s, file_key=%s, file_name=%s, file_url=%s",
                msg_type,
                file_key,
                file_name,
                file_url,
            )
            return {"status": "ignored", "reason": "non_pdf_file_message"}

        logger.info(f"Message {message_id} from {open_id} in chat {chat_id}: {text[:50]}...")

        # 根据 chat_id 查找对应的角色
        role_name = self._find_role_by_chat_id(chat_id)
        if role_name:
            logger.info(f"Found role: {role_name} for chat_id: {chat_id}")
            user_id = f"user_{role_name}"  # 使用角色对应的 user_id
        else:
            # 如果没有找到匹配的角色，使用 open_id 作为 user_id
            user_id = open_id
            logger.info(f"No role found for chat_id: {chat_id}, using open_id as user_id: {open_id}")

        logger.info(f"Final user_id for coordinator: {user_id}")
        self._log_pending_doc_dwell_proxy(user_id)

        recent_upload_reinforcement = self._handle_recent_upload_interest_reinforcement(
            user_id,
            chat_id,
            open_id,
            text,
        )
        if recent_upload_reinforcement is not None:
            return recent_upload_reinforcement

        # 路由到 master-coordinator 处理
        # 注意：飞书 p2p 聊天中 user_id 为 null，使用 open_id 作为用户 ID
        coordinator_user_id = user_id or open_id or "unknown_user"
        logger.info(f"Calling coordinator with user_id={coordinator_user_id}, chat_id={chat_id}")

        intent = self._detect_coordinator_intent(coordinator_user_id, text, chat_id, open_id)
        if intent in ASYNC_INTENT_ACKS:
            task_key = f"{coordinator_user_id}:{intent}"
            if not self._register_async_task(task_key):
                logger.info(f"Skipping duplicate async coordinator task for {task_key}")
                self._send_async_ack_async(
                    chat_id,
                    open_id,
                    ASYNC_INTENT_DUPLICATE_ACKS.get(intent, "当前已有相同任务在处理中，请稍候。"),
                )
                return {
                    "status": "accepted",
                    "mode": "async",
                    "intent": intent,
                    "duplicate": True,
                    "user_id": coordinator_user_id,
                    "chat_id": chat_id,
                }

            logger.info(f"Dispatching async coordinator task for intent={intent}")
            self._send_async_ack_async(chat_id, open_id, ASYNC_INTENT_ACKS[intent])
            self._route_to_coordinator_async(task_key, coordinator_user_id, text, chat_id, open_id)
            return {
                "status": "accepted",
                "mode": "async",
                "intent": intent,
                "user_id": coordinator_user_id,
                "chat_id": chat_id,
            }

        response = self._route_to_coordinator(coordinator_user_id, text, chat_id, open_id)

        return {
            "status": "success",
            "user_id": coordinator_user_id,
            "chat_id": chat_id,
            "response": response
        }

    def _find_role_by_chat_id(self, chat_id: str) -> Optional[str]:
        """
        根据 chat_id 查找对应的角色

        Args:
            chat_id: 聊天 ID

        Returns:
            角色名称（如 rolea, roleb 等），如果没有找到则返回 None
        """
        import json
        try:
            # 项目根目录是 scitaste，data/roles.json 相对于项目根目录
            project_root = os.path.normpath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", ".."  # services/webhook-server/scripts -> scitaste
            ))
            roles_path = os.path.join(project_root, "data", "roles.json")
            logger.info(f"Looking for roles.json at: {roles_path}")
            with open(roles_path, 'r', encoding='utf-8') as f:
                roles_data = json.load(f)
            logger.info(f"Loaded roles: {list(roles_data.get('roles', {}).keys())}")

            for role_name, role_data in roles_data.get("roles", {}).items():
                role_chat_id = role_data.get("feishu_chat_id")
                logger.info(f"Checking role {role_name}: feishu_chat_id={role_chat_id} vs incoming={chat_id}")
                if role_chat_id == chat_id:
                    logger.info(f"Match found: {role_name}")
                    return role_name
            logger.info(f"No match found for chat_id: {chat_id}")
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error finding role: {e}")
        return None

    def _handle_reaction(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理消息表情回复

        Args:
            event: 表情事件

        Returns:
            处理结果
        """
        reaction_event = event.get("event", {})
        message_id = reaction_event.get("message_id", "")
        reaction_type = reaction_event.get("reaction_type", "")
        chat_id = (
            reaction_event.get("chat_id")
            or ((reaction_event.get("message") or {}).get("chat_id"))
            or ""
        )
        sender = reaction_event.get("operator", {}) or reaction_event.get("sender", {}) or {}
        open_id = (
            ((sender.get("operator_id") or {}).get("open_id"))
            or ((sender.get("sender_id") or {}).get("open_id"))
            or ""
        )
        user_id = self._resolve_user_id_for_chat(chat_id, open_id)

        logger.info(f"Reaction {reaction_type} on message {message_id}")
        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            logger_fn = getattr(db_ops, "log_behavior", None)
            if callable(logger_fn) and user_id:
                logger_fn(
                    user_id=user_id,
                    push_id="reaction",
                    paper_id=None,
                    action="message_reaction",
                    action_type="reaction",
                    category=str(reaction_type or ""),
                    metadata={
                        "message_id": message_id,
                        "chat_id": chat_id,
                    },
                )
        except Exception as exc:
            logger.warning(f"Failed to persist reaction log: {exc}")

        normalized_reaction = str(reaction_type or "").lower()
        positive_tokens = {"+1", "thumbsup", "thumbs_up", "like", "ok"}
        negative_tokens = {"-1", "thumbsdown", "thumbs_down", "dislike"}
        if normalized_reaction in positive_tokens and user_id:
            self._route_to_coordinator(user_id, "这篇报告写得好", chat_id, open_id)
        elif normalized_reaction in negative_tokens and user_id:
            self._route_to_coordinator(user_id, "这篇报告没抓住重点", chat_id, open_id)

        return {"status": "success", "reaction": reaction_type}

    def _handle_menu_button(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理菜单按钮点击

        Args:
            event: 按钮事件

        Returns:
            处理结果
        """
        button_event = event.get("event", {})
        action = button_event.get("action", {})
        value = action.get("value", "{}")

        try:
            value_data = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            value_data = {}

        logger.info(f"Menu button clicked: {value_data}")
        chat_id = button_event.get("chat_id", "")
        open_id = (
            ((button_event.get("operator") or {}).get("operator_id") or {}).get("open_id")
            or ""
        )
        user_id = self._resolve_user_id_for_chat(chat_id, open_id)

        command_text = (
            value_data.get("command")
            or value_data.get("text")
            or value_data.get("message")
            or ""
        )
        if command_text and user_id:
            result = self._route_to_coordinator(user_id, str(command_text), chat_id, open_id)
            return {"status": "success", "action": value_data, "response": result}

        try:
            db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
            logger_fn = getattr(db_ops, "log_behavior", None)
            if callable(logger_fn) and user_id:
                logger_fn(
                    user_id=user_id,
                    push_id="menu_button",
                    paper_id=None,
                    action="menu_button",
                    action_type="ui_action",
                    category=str(value_data.get("action") or value_data.get("type") or "button"),
                    metadata=value_data,
                )
        except Exception as exc:
            logger.warning(f"Failed to persist menu button log: {exc}")

        return {"status": "success", "action": value_data}

    def _handle_pdf_reading_report(
        self,
        message_id: str,
        file_key: str,
        file_name: str,
        chat_id: str,
        open_id: str,
    ) -> Dict[str, Any]:
        """
        处理 PDF 文件消息，生成精读报告

        Args:
            message_id: 消息 ID
            file_key: 文件 key（用于下载）
            file_name: 文件名
            chat_id: 聊天 ID
            open_id: 用户 open_id

        Returns:
            处理结果
        """
        try:
            # 导入 feishu-reporter 下载文件和发送消息
            feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
            download_file = feishu_reporter.download_file_from_feishu
            send_text = feishu_reporter.send_text

            # 导入 reading-agent 生成精读报告
            reading_agent = importlib.import_module("agents.reading-agent.main")
            create_reading_report = reading_agent.create_reading_report

            # 根据 chat_id 查找角色
            role_name = self._find_role_by_chat_id(chat_id)
            if role_name:
                user_id = f"user_{role_name}"
                logger.info(f"Found role: {role_name} for chat_id: {chat_id}, user_id: {user_id}")
            else:
                user_id = open_id
                logger.info(f"No role found, using open_id as user_id: {user_id}")

            # 下载 PDF 文件
            logger.info(
                f"Downloading PDF from Feishu: message_id={message_id}, "
                f"file_key={file_key}, file_name={file_name}"
            )
            pdf_path = download_file(message_id, file_key, file_name=file_name)
            logger.info(f"PDF downloaded to: {pdf_path}")

            # 执行精读报告生成
            logger.info(f"Executing reading report with PDF: {pdf_path}")
            source_type = "feishu_file_key" if file_key else "feishu_message_id"
            source_key = file_key or message_id
            created_docs = create_reading_report(
                user_id=user_id,
                paper_ids=[],  # 空列表，使用 PDF 文件
                papers=[{"pdf_path": pdf_path, "title": os.path.splitext(file_name)[0]}],
                send_to_feishu=True,
                feishu_user_id=open_id,
                chat_id=chat_id,
                request_metadata={
                    "report_source_type": source_type,
                    "report_source_key": source_key,
                    "report_source_name": file_name,
                    "report_source_message_id": message_id,
                },
            )

            return {
                "status": "success",
                "message": f"PDF reading report generated for user {user_id}",
                "pdf_path": pdf_path,
                "created_docs": created_docs
            }
        except Exception as e:
            logger.error(f"Error handling PDF reading report: {e}", exc_info=True)
            # 发送错误通知
            try:
                feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
                send_text = feishu_reporter.send_text
                send_text(
                    chat_id,
                    f"精读报告生成失败：{str(e)}",
                    use_chat_id=True
                )
            except Exception:
                pass
            return {"status": "error", "message": str(e)}

    def _route_to_coordinator(self, user_id: str, message: str, chat_id: str, sender_open_id: str = None) -> Dict[str, Any]:
        """
        路由消息到 master-coordinator

        Args:
            user_id: 用户 ID
            message: 消息内容
            chat_id: 聊天 ID（用于回复到原聊天）
            sender_open_id: 发送者的 open_id（备选）

        Returns:
            响应结果
        """
        try:
            from agents.master_coordinator.main import MasterCoordinator

            # 优先使用 chat_id 回复到原聊天，如果没有则使用发送者的 open_id
            reply_to = chat_id or sender_open_id or os.environ.get("FEISHU_USER_ID", "")
            logger.info(f"Creating coordinator: user={user_id}, chat={chat_id}, reply_to={reply_to[:20] if reply_to else 'None'}...")

            coordinator = MasterCoordinator(
                user_id=user_id,
                feishu_user_id=sender_open_id,
                chat_id=chat_id
            )

            logger.info(f"Processing message: {message[:50]}...")
            result = coordinator.process(message)
            logger.info(f"Coordinator result: {result}")

            return result
        except Exception as e:
            logger.error(f"Error routing to coordinator: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _detect_coordinator_intent(
        self,
        user_id: str,
        message: str,
        chat_id: str,
        sender_open_id: Optional[str] = None,
    ) -> str:
        """Best-effort detect coordinator intent before deciding whether to run async."""
        try:
            from agents.master_coordinator.main import MasterCoordinator

            coordinator = MasterCoordinator(
                user_id=user_id,
                feishu_user_id=sender_open_id,
                chat_id=chat_id,
            )
            detected = coordinator.detect_intent(message)
            return str(detected.get("intent", "")).strip()
        except Exception as exc:
            logger.warning(f"Failed to pre-detect intent, falling back to sync processing: {exc}")
            return ""

    def _route_to_coordinator_async(
        self,
        task_key: str,
        user_id: str,
        message: str,
        chat_id: str,
        sender_open_id: Optional[str] = None,
    ) -> None:
        """Run coordinator work in a background thread so webhook responses can return immediately."""

        def target() -> None:
            try:
                result = self._route_to_coordinator(user_id, message, chat_id, sender_open_id)
                logger.info(f"Async coordinator task finished: {result}")
            finally:
                self._release_async_task(task_key)

        thread = threading.Thread(
            target=target,
            name=f"scitaste-{user_id}-{int(time.time())}",
            daemon=True,
        )
        thread.start()

    def _route_pdf_reading_report_async(
        self,
        task_key: str,
        message_id: str,
        file_key: str,
        file_name: str,
        chat_id: str,
        open_id: str,
    ) -> None:
        """Run PDF reading report generation in the background."""

        def target() -> None:
            try:
                result = self._handle_pdf_reading_report(message_id, file_key, file_name, chat_id, open_id)
                logger.info(f"Async PDF reading-report task finished: {result}")
            finally:
                self._release_async_task(task_key)

        thread = threading.Thread(
            target=target,
            name=f"scitaste-pdf-{int(time.time())}",
            daemon=True,
        )
        thread.start()

    def _send_async_ack(self, chat_id: str, open_id: str, text: str) -> None:
        """Send a short acknowledgement before a long-running task starts."""
        try:
            feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
            if chat_id:
                feishu_reporter.send_text(chat_id, text, use_chat_id=True)
            elif open_id:
                feishu_reporter.send_text(open_id, text)
        except Exception as exc:
            logger.warning(f"Failed to send async acknowledgement: {exc}")

    def _send_async_ack_async(self, chat_id: str, open_id: str, text: str) -> None:
        """Send the acknowledgement before background work starts.

        The actual coordinator task still runs asynchronously, but the short
        acknowledgement is sent inline so users see "processing..." before the
        final result rather than after it.
        """
        self._send_async_ack(chat_id, open_id, text)

    def _register_async_task(self, task_key: str) -> bool:
        """Register an async task if the same user+intent is not already running."""
        with INFLIGHT_COORDINATOR_TASKS_LOCK:
            if task_key in INFLIGHT_COORDINATOR_TASKS:
                return False
            if not _acquire_async_task_lock(task_key):
                return False
            INFLIGHT_COORDINATOR_TASKS.add(task_key)
            return True

    def _release_async_task(self, task_key: str) -> None:
        """Release a finished async task registration."""
        with INFLIGHT_COORDINATOR_TASKS_LOCK:
            INFLIGHT_COORDINATOR_TASKS.discard(task_key)
        _release_async_task_lock(task_key)


class ReusableHTTPServer(HTTPServer):
    """Allow quick restarts on the same port during local development."""

    allow_reuse_address = True


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def __init__(self, *args, **kwargs):
        self.event_handler = FeishuEventHandler()
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """处理 GET 请求（URL 验证）"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        logger.info(f"GET request: {self.path}")

        # 飞书 URL 验证
        if "token" in params and "challenge" in params:
            token = params["token"][0]
            challenge = params["challenge"][0]

            response = self.event_handler.verify_url(token, challenge)

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(response.encode('utf-8'))
            return

        # 健康检查
        if parsed.path == "/r/doc":
            target = params.get("target", [""])[0].strip()
            user_id = params.get("user_id", [""])[0].strip()
            doc_token = params.get("doc_token", [""])[0].strip()
            title = params.get("title", [""])[0].strip()
            if not target.startswith(("http://", "https://")):
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write("Invalid target URL".encode("utf-8"))
                return
            self.event_handler._log_doc_open(user_id, doc_url=target, doc_token=doc_token, title=title)
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return

        if parsed.path == "/health":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            payload = {"status": "healthy"}
            try:
                scheduler_module = importlib.import_module("services.webhook-server.scripts.scheduler")
                status_snapshot = getattr(scheduler_module, "get_scheduler_status_snapshot", None)
                if callable(status_snapshot):
                    payload["scheduler"] = status_snapshot()
            except Exception:
                logger.debug("Unable to include scheduler status in health payload", exc_info=True)
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        """处理 POST 请求（事件订阅）"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        logger.info(f"POST request: {self.path}, Content-Length: {content_length}")

        # 解析事件
        try:
            event = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
            return

        # 处理 url_verification 事件（飞书验证 URL 用）
        event_type = event.get("type", "")
        if event_type == "url_verification":
            token = event.get("token", "")
            challenge = event.get("challenge", "")

            logger.info(f"Received url_verification: token={token[:10]}..., challenge={challenge[:10]}...")

            # 验证 token 并返回 challenge（JSON 格式）
            if token == self.event_handler.verification_token:
                logger.info("URL verification token matched")
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"challenge": challenge}).encode('utf-8'))
                return
            else:
                logger.error(f"Token mismatch: expected={self.event_handler.verification_token[:10]}..., got={token[:10]}...")
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Token mismatch"}).encode('utf-8'))
                return

        # 获取签名信息（其他事件需要验证签名）
        signature = self.headers.get('X-Feishu-Signature', '')
        timestamp = self.headers.get('X-Feishu-Timestamp', '')

        # 验证签名
        if signature and timestamp:
            if not self.event_handler.verify_signature(body, signature, timestamp):
                logger.error("Signature verification failed")
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid signature"}).encode('utf-8'))
                return

        # 处理其他事件
        result = self.event_handler.handle_event(event)

        # 返回响应
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        try:
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError) as exc:
            logger.warning(f"Client closed connection before webhook response completed: {exc}")

    def log_message(self, format, *args):
        """自定义日志格式"""
        logger.info("%s - %s" % (self.address_string(), format % args))


def run_server(port: int = 8080, start_scheduler: bool = True):
    """
    启动 webhook 服务器

    Args:
        port: 端口号，默认 8080
    """
    server_address = ('', port)

    try:
        httpd = ReusableHTTPServer(server_address, WebhookHandler)
    except OSError as exc:
        logger.error(f"Failed to bind webhook server on port {port}: {exc}", exc_info=True)
        raise

    cleared_lock_count = clear_async_task_locks_on_startup()
    if cleared_lock_count:
        logger.info(f"Cleared {cleared_lock_count} stale async task lock(s) on startup")

    scheduler_module = None
    if start_scheduler:
        try:
            scheduler_module = importlib.import_module("services.webhook-server.scripts.scheduler")
            scheduler_thread = scheduler_module.start_scheduler_thread()
            if scheduler_thread:
                logger.info(f"Scheduler started: {scheduler_module.describe_schedule()}")
        except Exception as exc:
            logger.error(f"Failed to start scheduler: {exc}", exc_info=True)

    logger.info(f"Starting Feishu webhook server on port {port}...")
    logger.info(f"Event endpoint: http://localhost:{port}/")
    logger.info(f"Health check: http://localhost:{port}/health")
    logger.info("Press Ctrl+C to stop")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        httpd.shutdown()
    finally:
        if scheduler_module is not None:
            try:
                scheduler_module.stop_scheduler_thread()
            except Exception:
                pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Feishu Webhook Server")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--verify-only", action="store_true", help="Verify environment variables")

    args = parser.parse_args()

    # 验证环境变量
    if args.verify_only:
        required_vars = [
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_VERIFICATION_TOKEN"
        ]

        missing = [var for var in required_vars if not os.environ.get(var)]

        if missing:
            print(f"Missing environment variables: {', '.join(missing)}")
            print("\nPlease set these in your .env file:")
            print("  FEISHU_APP_ID=your_app_id")
            print("  FEISHU_APP_SECRET=your_app_secret")
            print("  FEISHU_VERIFICATION_TOKEN=your_verification_token")
            sys.exit(1)
        else:
            print("All required environment variables are set")
            sys.exit(0)

    # 启动服务器
    run_server(args.port)
