"""
Tests for webhook bot-echo filtering and message/task deduplication.
"""

import importlib.util
import json
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
WEBHOOK_PATH = PROJECT_ROOT / "services" / "webhook-server" / "scripts" / "webhook_server.py"

spec = importlib.util.spec_from_file_location("webhook_server_test", WEBHOOK_PATH)
webhook_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webhook_server)


def _build_text_event(message_id: str, text: str) -> dict:
    return {
        "event": {
            "message": {
                "chat_id": "oc_rolea",
                "message_id": message_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }


def test_is_likely_bot_echo_matches_known_prefixes():
    prefix = webhook_server.BOT_MESSAGE_PREFIXES[0]
    assert webhook_server.is_likely_bot_echo(prefix + " sample")
    assert not webhook_server.is_likely_bot_echo("lower GUI Agent weight")


def test_is_likely_bot_echo_matches_reading_report_summary():
    reading_report_summary = (
        "============================================================\n"
        "Reading reports created (2)\n"
        "============================================================\n\n"
        "01. DNA damage drives antigen diversification\n"
        "    doc_token: EbKydK0DqoFHNrxJ2XichnognKf\n\n"
        "02. Female mice grow testes after this single DNA tweak\n"
        "    doc_token: V4Evdnt7joFuPWxAjdCchMnfn5c\n\n"
        "Open the links above to start reading."
    )

    assert webhook_server.is_likely_bot_echo(reading_report_summary)


def test_is_likely_bot_echo_matches_reading_doc_title_echo():
    assert webhook_server.is_likely_bot_echo("[精读] 面向兴趣漂移驱动的序列推荐用户表示学习")


def test_is_likely_bot_echo_matches_pdf_processing_ack():
    assert webhook_server.is_likely_bot_echo("收到 PDF，正在生成精读报告，请稍候...")


def test_recent_outbound_bot_text_is_ignored(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.RECENT_TEXT_MESSAGE_FINGERPRINTS.clear()
    handler = webhook_server.FeishuEventHandler()

    monkeypatch.setattr(
        webhook_server,
        "_is_recent_outbound_bot_message",
        lambda chat_id, text: chat_id == "oc_rolea" and text == "精读任务已执行，但这次没有成功生成文档链接。请稍后重试；如果还不行，我可以继续帮你排查。",
    )

    result = handler._handle_message(
        _build_text_event(
            "om_bot_echo_like",
            "精读任务已执行，但这次没有成功生成文档链接。请稍后重试；如果还不行，我可以继续帮你排查。",
        )
    )

    assert result == {"status": "ignored", "reason": "recent_outbound_bot_message"}


def test_is_likely_bot_echo_matches_duplicate_async_ack():
    duplicate_ack = "当前已有一个冷启动任务在处理中，请稍候查看本群结果。"

    assert webhook_server.is_likely_bot_echo(duplicate_ack)


def test_is_duplicate_message_rejects_retries():
    webhook_server.PROCESSED_MESSAGE_IDS.clear()

    assert webhook_server.is_duplicate_message("om_test_message") is False
    assert webhook_server.is_duplicate_message("om_test_message") is True


def test_pdf_file_message_routes_to_reading_report(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    captured = {}

    monkeypatch.setattr(handler, "_find_existing_pdf_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(handler, "_register_async_task", lambda task_key: captured.setdefault("task_key", task_key) or True)
    monkeypatch.setattr(
        handler,
        "_send_async_ack_async",
        lambda chat_id, open_id, text: captured.update({"ack": (chat_id, open_id, text)}),
    )
    monkeypatch.setattr(
        handler,
        "_route_pdf_reading_report_async",
        lambda task_key, message_id, file_key, file_name, chat_id, open_id: captured.update(
            {
                "route": {
                    "task_key": task_key,
                    "message_id": message_id,
                    "file_key": file_key,
                    "file_name": file_name,
                    "chat_id": chat_id,
                    "open_id": open_id,
                }
            }
        ),
    )

    event = {
        "event": {
            "message": {
                "chat_id": "oc_test",
                "message_id": "om_file_test",
                "msg_type": "file",
                "content": '{"file_key":"file_v3_test","file_name":"sample.pdf"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }

    result = handler._handle_message(event)

    assert result == {
        "status": "accepted",
        "mode": "async",
        "intent": "reading_report",
        "source": "pdf",
        "chat_id": "oc_test",
    }
    assert captured["task_key"] == "pdf:oc_test:ou_test:file_v3_test"
    assert captured["ack"] == ("oc_test", "ou_test", webhook_server.PDF_ASYNC_ACK)
    assert captured["route"] == {
        "task_key": "pdf:oc_test:ou_test:file_v3_test",
        "message_id": "om_file_test",
        "file_key": "file_v3_test",
        "file_name": "sample.pdf",
        "chat_id": "oc_test",
        "open_id": "ou_test",
    }


def test_duplicate_pdf_file_message_is_blocked_by_async_task_lock(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    captured = {"routes": 0}

    monkeypatch.setattr(handler, "_find_existing_pdf_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(handler, "_register_async_task", lambda task_key: False)
    monkeypatch.setattr(
        handler,
        "_route_pdf_reading_report_async",
        lambda *args, **kwargs: captured.__setitem__("routes", captured["routes"] + 1),
    )

    event = {
        "event": {
            "message": {
                "chat_id": "oc_test",
                "message_id": "om_file_test_dup",
                "msg_type": "file",
                "content": '{"file_key":"file_v3_test","file_name":"sample.pdf"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }

    result = handler._handle_message(event)

    assert result == {
        "status": "ignored",
        "reason": "duplicate_pdf_inflight",
        "source": "pdf",
        "chat_id": "oc_test",
    }
    assert captured["routes"] == 0


def test_completed_pdf_file_message_is_silently_ignored(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()

    monkeypatch.setattr(
        handler,
        "_find_existing_pdf_report",
        lambda user_id, source_type, source_key: {
            "doc_url": "https://example.feishu.cn/docx/existing-pdf",
            "doc_token": "existing_pdf_doc",
        },
    )
    monkeypatch.setattr(
        handler,
        "_register_async_task",
        lambda task_key: (_ for _ in ()).throw(AssertionError("should not register duplicate completed PDF task")),
    )

    event = {
        "event": {
            "message": {
                "chat_id": "oc_test",
                "message_id": "om_file_test_done",
                "msg_type": "file",
                "content": '{"file_key":"file_v3_done","file_name":"sample.pdf"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }

    result = handler._handle_message(event)

    assert result == {
        "status": "ignored",
        "reason": "duplicate_pdf_file_message",
        "source": "pdf",
        "chat_id": "oc_test",
    }


def test_non_pdf_file_like_message_is_ignored(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    handler = webhook_server.FeishuEventHandler()
    called = {"reading_report": False}

    def fake_pdf_reading_report(*args, **kwargs):
        called["reading_report"] = True
        return {"status": "success"}

    monkeypatch.setattr(handler, "_handle_pdf_reading_report", fake_pdf_reading_report)

    event = {
        "event": {
            "message": {
                "chat_id": "oc_test",
                "message_id": "om_file_echo_test",
                "msg_type": "file",
                "content": '{"file_key":"file_v3_echo","file_name":"[精读] 测试文档"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }

    result = handler._handle_message(event)

    assert result == {"status": "ignored", "reason": "non_pdf_file_message"}
    assert called["reading_report"] is False


def test_text_message_retry_with_new_message_id_is_deduplicated(monkeypatch, tmp_path):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.RECENT_TEXT_MESSAGE_FINGERPRINTS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    processed = []

    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", tmp_path / "webhook_task_locks")
    monkeypatch.setattr(handler, "_find_role_by_chat_id", lambda chat_id: "rolea")
    monkeypatch.setattr(handler, "_send_async_ack_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        handler,
        "_route_to_coordinator_async",
        lambda task_key, user_id, message, chat_id, sender_open_id=None: processed.append(
            {
                "task_key": task_key,
                "user_id": user_id,
                "message": message,
                "chat_id": chat_id,
                "sender_open_id": sender_open_id,
            }
        ),
    )

    first_result = handler._handle_message(_build_text_event("om_weekly_1", "weekly report"))
    second_result = handler._handle_message(_build_text_event("om_weekly_2", "weekly report"))

    assert first_result["status"] == "accepted"
    assert first_result["mode"] == "async"
    assert second_result == {"status": "ignored", "reason": "duplicate_text_message"}
    assert len(processed) == 1


def test_feedback_messages_run_async_to_avoid_retry_duplicates(monkeypatch, tmp_path):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.RECENT_TEXT_MESSAGE_FINGERPRINTS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    captured = {}

    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", tmp_path / "webhook_task_locks")
    monkeypatch.setattr(handler, "_find_role_by_chat_id", lambda chat_id: "rolea")
    monkeypatch.setattr(handler, "_send_async_ack_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(handler, "_route_to_coordinator_async", lambda *args, **kwargs: captured.update({"called": True}))
    monkeypatch.setattr(handler, "_detect_coordinator_intent", lambda *args, **kwargs: "feedback")

    result = handler._handle_message(_build_text_event("om_feedback_async_1", "1-3"))

    assert result["status"] == "accepted"
    assert result["mode"] == "async"
    assert result["intent"] == "feedback"
    assert captured["called"] is True


def test_daily_push_duplicate_is_blocked_by_inflight_task_lock(monkeypatch, tmp_path):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.RECENT_TEXT_MESSAGE_FINGERPRINTS.clear()
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    captured = {"routes": 0, "acks": 0}

    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", tmp_path / "webhook_task_locks")
    monkeypatch.setattr(webhook_server, "is_duplicate_text_message", lambda *args, **kwargs: False)
    monkeypatch.setattr(handler, "_find_role_by_chat_id", lambda chat_id: "rolea")
    monkeypatch.setattr(handler, "_detect_coordinator_intent", lambda *args, **kwargs: "daily_push")
    monkeypatch.setattr(
        handler,
        "_send_async_ack_async",
        lambda *args, **kwargs: captured.__setitem__("acks", captured["acks"] + 1),
    )
    monkeypatch.setattr(
        handler,
        "_route_to_coordinator_async",
        lambda *args, **kwargs: captured.__setitem__("routes", captured["routes"] + 1),
    )

    first_result = handler._handle_message(_build_text_event("om_push_1", "push"))
    second_result = handler._handle_message(_build_text_event("om_push_2", "push"))

    assert first_result["status"] == "accepted"
    assert first_result.get("duplicate") is not True
    assert second_result["status"] == "accepted"
    assert second_result["duplicate"] is True
    assert captured["routes"] == 1
    assert captured["acks"] == 2


def test_register_async_task_respects_existing_persistent_lock(monkeypatch, tmp_path):
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", tmp_path / "webhook_task_locks")

    task_key = "user_rolea:daily_push"
    lock_dir = webhook_server.ASYNC_TASK_LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = webhook_server._get_async_task_lock_path(task_key)
    lock_path.write_text(
        json.dumps({"task_key": task_key, "created_at": time.time(), "pid": 99999}),
        encoding="utf-8",
    )

    assert handler._register_async_task(task_key) is False


def test_register_async_task_reclaims_stale_persistent_lock(monkeypatch, tmp_path):
    webhook_server.INFLIGHT_COORDINATOR_TASKS.clear()
    handler = webhook_server.FeishuEventHandler()
    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", tmp_path / "webhook_task_locks")
    monkeypatch.setenv("SCITASTE_ASYNC_TASK_LOCK_TTL_SECONDS", "30")

    task_key = "user_rolea:daily_push"
    lock_dir = webhook_server.ASYNC_TASK_LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = webhook_server._get_async_task_lock_path(task_key)
    lock_path.write_text(
        json.dumps({"task_key": task_key, "created_at": time.time() - 120, "pid": 99999}),
        encoding="utf-8",
    )

    try:
        assert handler._register_async_task(task_key) is True
    finally:
        handler._release_async_task(task_key)


def test_clear_async_task_locks_on_startup_removes_existing_lock_files(monkeypatch, tmp_path):
    lock_dir = tmp_path / "webhook_task_locks"
    monkeypatch.setattr(webhook_server, "ASYNC_TASK_LOCK_DIR", lock_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock_a.json").write_text("{}", encoding="utf-8")
    (lock_dir / "lock_b.json").write_text("{}", encoding="utf-8")

    removed = webhook_server.clear_async_task_locks_on_startup()

    assert removed == 2
    assert list(lock_dir.glob("*.json")) == []
