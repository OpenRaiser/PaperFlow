"""
Tests for routing weekly reports back to role chats.
"""

import importlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

master_coordinator = importlib.import_module("agents.master_coordinator.main")
profile_report_agent = importlib.import_module("agents.profile-report-agent.main")


def test_master_coordinator_resolves_role_chat_id_from_role_meta(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "feishu_chat_id": "oc_rolea_test",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    original_role_meta_path = master_coordinator.ROLE_META_PATH
    try:
        master_coordinator.ROLE_META_PATH = str(roles_path)
        monkeypatch.setattr(master_coordinator, "get_profile", lambda user_id: {})

        coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

        assert coordinator.role_name == "rolea"
        assert coordinator.chat_id == "oc_rolea_test"
    finally:
        master_coordinator.ROLE_META_PATH = original_role_meta_path


def test_send_weekly_report_routes_to_role_chat_when_chat_id_missing(monkeypatch):
    monkeypatch.setattr(
        profile_report_agent,
        "load_roles_meta",
        lambda: {
            "roles": {
                "rolea": {
                    "user_id": "user_rolea",
                    "feishu_chat_id": "oc_rolea_test",
                }
            }
        },
    )
    monkeypatch.setattr(profile_report_agent, "get_profile", lambda user_id: {})
    monkeypatch.setattr(
        profile_report_agent,
        "generate_weekly_report",
        lambda user_id, days: {
            "period": "2026-04-05 ~ 2026-04-12",
            "direction_changes": [],
            "stats": {"total": 0, "selected": 0, "selection_rate": 0.0},
            "stats_by_category": {},
            "top_authors": [],
            "top_institutions": [],
            "missed_papers": [],
        },
    )

    captured = {}

    def fake_send_text_to_chat(chat_id, text):
        captured["chat_id"] = chat_id
        captured["text"] = text
        return {"success": True}

    monkeypatch.setattr(profile_report_agent, "send_text_to_chat", fake_send_text_to_chat)

    result = profile_report_agent.send_weekly_report(
        user_id="user_rolea",
        send_to_feishu=True,
    )

    assert "error" not in result
    assert captured["chat_id"] == "oc_rolea_test"
    assert "你的学术画像周度报告" in captured["text"]
