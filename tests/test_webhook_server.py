"""
Tests for webhook bot-echo filtering and message retry deduplication.
"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
WEBHOOK_PATH = PROJECT_ROOT / "services" / "webhook-server" / "scripts" / "webhook_server.py"

spec = importlib.util.spec_from_file_location("webhook_server_test", WEBHOOK_PATH)
webhook_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webhook_server)


def test_is_likely_bot_echo_matches_push_and_feedback_messages():
    assert webhook_server.is_likely_bot_echo("📰 今日论文 | 04-11 | 抓取 60 篇 → 筛后 60 篇")
    assert webhook_server.is_likely_bot_echo("收到，6 篇已进入偏好学习流程。\n📊 今日反馈已记录")
    assert not webhook_server.is_likely_bot_echo("降低 GUI Agent 权重")


def test_is_likely_bot_echo_matches_weekly_report_messages():
    weekly_report = (
        "============================================================\n"
        "📊 你的学术画像周度报告 | 2026-04-05 ~ 2026-04-12\n"
        "============================================================\n\n"
        "━━━ 本周阅读统计 ━━━\n"
        "推送论文总数：60\n"
        "你选择精读：6（选择率 10.0%）"
    )
    assert webhook_server.is_likely_bot_echo(weekly_report)


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


def test_is_duplicate_message_rejects_retries():
    webhook_server.PROCESSED_MESSAGE_IDS.clear()

    assert webhook_server.is_duplicate_message("om_test_message") is False
    assert webhook_server.is_duplicate_message("om_test_message") is True


def test_file_message_routes_to_pdf_coldstart(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    handler = webhook_server.FeishuEventHandler()
    captured = {}

    def fake_pdf_coldstart(message_id, file_key, file_name, chat_id, open_id):
        captured["message_id"] = message_id
        captured["file_key"] = file_key
        captured["file_name"] = file_name
        captured["chat_id"] = chat_id
        captured["open_id"] = open_id
        return {"status": "success"}

    monkeypatch.setattr(handler, "_handle_pdf_coldstart", fake_pdf_coldstart)

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

    assert result == {"status": "success"}
    assert captured == {
        "message_id": "om_file_test",
        "file_key": "file_v3_test",
        "file_name": "sample.pdf",
        "chat_id": "oc_test",
        "open_id": "ou_test",
    }


def test_text_message_retry_with_new_message_id_is_deduplicated(monkeypatch):
    webhook_server.PROCESSED_MESSAGE_IDS.clear()
    webhook_server.RECENT_TEXT_MESSAGE_FINGERPRINTS.clear()
    handler = webhook_server.FeishuEventHandler()
    processed = []

    def fake_route(user_id, message, chat_id, sender_open_id=None):
        processed.append(
            {
                "user_id": user_id,
                "message": message,
                "chat_id": chat_id,
                "sender_open_id": sender_open_id,
            }
        )
        return {"success": True}

    monkeypatch.setattr(handler, "_route_to_coordinator", fake_route)
    monkeypatch.setattr(handler, "_find_role_by_chat_id", lambda chat_id: "rolea")

    base_event = {
        "event": {
            "message": {
                "chat_id": "oc_rolea",
                "msg_type": "text",
                "content": '{"text":"周报"}',
            },
            "sender": {
                "sender_id": {"open_id": "ou_test", "user_id": None},
                "sender_type": "user",
            },
        }
    }

    first_event = {
        "event": {
            **base_event["event"],
            "message": {**base_event["event"]["message"], "message_id": "om_weekly_1"},
        }
    }
    second_event = {
        "event": {
            **base_event["event"],
            "message": {**base_event["event"]["message"], "message_id": "om_weekly_2"},
        }
    }

    first_result = handler._handle_message(first_event)
    second_result = handler._handle_message(second_event)

    assert first_result["status"] == "success"
    assert second_result == {"status": "ignored", "reason": "duplicate_text_message"}
    assert len(processed) == 1


def test_is_likely_bot_echo_matches_must_read_list_messages():
    must_read_list = (
        "============================================================\n"
        "📋 必读清单\n"
        "============================================================\n\n"
        "━━━ 👥 作者 (1) ━━━\n"
        "  • tansong\n\n"
        "━━━ 🏛️ 机构 (0) ━━━\n"
        "  （空，待添加）\n\n"
        "━━━ 🔑 关键词 (0) ━━━\n"
        "  （空，待添加）\n\n"
        "============================================================\n"
        "添加方式：\n"
        '  "加个必读作者：Mohammed AlQuraishi"\n'
        '  "添加必读机构：MIT"\n'
        '  "添加必读关键词：GUI Agent"\n\n'
        "移除方式：\n"
        '  "移除必读作者：张三"\n'
        "============================================================"
    )

    assert webhook_server.is_likely_bot_echo(must_read_list)
