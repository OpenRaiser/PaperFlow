"""
Tests for routing weekly reports back to role chats.
"""

import importlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

master_coordinator = importlib.import_module("agents.master-coordinator.main")
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
    assert "学术画像周度报告" in captured["text"]


def test_send_weekly_report_includes_drift_section(monkeypatch):
    monkeypatch.setattr(profile_report_agent, "get_profile", lambda user_id: {})
    monkeypatch.setattr(
        profile_report_agent,
        "generate_weekly_report",
        lambda user_id, days: {
            "period": "2026-04-05 ~ 2026-04-12",
            "direction_changes": [],
            "stats": {"total": 5, "selected": 2, "selection_rate": 0.4},
            "stats_by_category": {},
            "top_authors": [],
            "top_institutions": [],
            "missed_papers": [],
            "drift_summary": {
                "status": "shifting",
                "status_label": "迁移中",
                "max_score": 0.58,
                "detected_at": "2026-04-12T09:30:00",
                "top_shift_topics": ["multimodal-reasoning", "protein-language-model"],
                "explanation": "近期在多模态推理上的选择显著偏离历史窗口，因此系统提高了短期兴趣权重。",
            },
        },
    )

    captured = {}

    def fake_send_text_to_chat(chat_id, text):
        captured["chat_id"] = chat_id
        captured["text"] = text
        return {"success": True}

    monkeypatch.setattr(profile_report_agent, "send_text_to_chat", fake_send_text_to_chat)

    profile_report_agent.send_weekly_report(
        user_id="user_rolea",
        feishu_chat_id="oc_rolea_test",
        send_to_feishu=True,
    )

    assert "兴趣迁移状态" in captured["text"]
    assert "迁移中" in captured["text"]
    assert "本周最高漂移分数" in captured["text"]


def test_detect_missed_papers_uses_external_impact_signal(monkeypatch):
    monkeypatch.setattr(
        profile_report_agent,
        "_fetch_openalex_impact_signal",
        lambda paper: {"cited_by_count": 42, "venue": "Nature", "is_open_access": True},
    )

    missed = profile_report_agent._detect_missed_papers(
        logs=[{"action_type": "selected", "paper_id": 1}],
        recent_pushes=[
            {"id": 1, "title": "Selected Paper", "category": "high_relevant", "score": 0.8},
            {"id": 2, "title": "Missed Important Paper", "category": "high_relevant", "score": 0.76, "doi": "10.1000/test"},
        ],
    )

    assert missed[0]["title"] == "Missed Important Paper"
    assert missed[0]["cited_by_count"] == 42


def test_build_external_impact_summary_detects_cited_by_must_read(monkeypatch):
    monkeypatch.setattr(
        profile_report_agent,
        "_cached_openalex_impact_signal",
        lambda paper, cache: {
            "cited_by_count": 18,
            "venue": "Nature",
            "cited_by_api_url": "https://api.openalex.org/works?filter=cites:W1",
        },
    )
    monkeypatch.setattr(
        profile_report_agent,
        "_fetch_citing_author_matches",
        lambda impact_signal, must_read_authors: [
            {
                "title": "Follow-up Work",
                "matched_authors": ["Cheng Tan"],
                "cited_by_count": 5,
            }
        ],
    )

    summary = profile_report_agent._build_external_impact_summary(
        profile={"must_read": {"authors": ["Cheng Tan"], "institutions": [], "keywords": []}},
        logs=[{"action_type": "selected", "paper_id": 1}],
        recent_pushes=[{"id": 1, "title": "Selected Paper", "category": "high_relevant", "score": 0.8}],
    )

    assert summary["cited_by_must_read"][0]["title"] == "Selected Paper"
    assert any("必读作者" in item for item in summary["explanations"])


def test_format_report_card_includes_accuracy_and_trend_explanations():
    card = profile_report_agent.format_report_card(
        {
            "period": "2026-04-10 ~ 2026-04-17",
            "direction_changes": [],
            "stats": {"total": 10, "selected": 4, "selection_rate": 0.4},
            "stats_by_category": {
                "high_relevant": {"selection_rate": 0.6},
                "maybe_interested": {"selection_rate": 0.3},
                "edge_relevant": {"selection_rate": 0.1},
            },
            "accuracy_explanations": ["高相关分组的选择率高于中低相关分组，说明当前排序主链路整体有效。"],
            "missed_papers": [{"title": "Missed Important Paper", "cited_by_count": 18}],
            "external_impact": {
                "selected_impacts": [{"title": "Selected Impact Paper", "cited_by_count": 22}],
                "cited_by_must_read": [{"title": "Linked Paper", "matches": [{"matched_authors": ["Cheng Tan"]}]}],
                "explanations": ["《Linked Paper》已被你的必读作者 Cheng Tan 的后续工作引用。"],
            },
            "trend_explanations": ["系统检测到近期偏好与长期画像明显拉开，因此推荐排序已更偏向短期兴趣。"],
            "top_authors": [],
            "top_institutions": [],
            "drift_summary": {"status_label": "迁移中", "max_score": 0.5, "explanation": "test"},
        }
    )

    assert "排序主链路整体有效" in card
    assert "OpenAlex cited_by=18" in card
    assert "外部影响信号" in card
    assert "必读作者引用" in card
    assert "趋势解释" in card


def test_format_report_card_includes_doc_engagement_stats():
    card = profile_report_agent.format_report_card(
        {
            "period": "2026-04-10 ~ 2026-04-17",
            "direction_changes": [],
            "stats": {"total": 10, "selected": 4, "selection_rate": 0.4},
            "stats_by_category": {},
            "top_authors": [],
            "top_institutions": [],
            "missed_papers": [],
            "doc_engagement": {
                "total_doc_opens": 6,
                "unique_doc_opens": 4,
                "avg_dwell_proxy_seconds": 95.0,
                "dwell_proxy_count": 3,
            },
        }
    )

    assert "精读文档打开：6 次" in card
    assert "精读阅读停留代理：平均 95 秒" in card
