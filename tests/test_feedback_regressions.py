"""
Regression tests for push/feedback mapping issues seen in roleA flows.
"""

import copy
import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
feedback_agent = importlib.import_module("agents.feedback-agent.main")


def _use_test_db(test_db_path):
    db_ops.DB_PATH = test_db_path
    feedback_agent.db_ops.DB_PATH = test_db_path


def test_save_paper_without_identifiers_keeps_distinct_rows(test_db_path):
    _use_test_db(test_db_path)

    paper_a_id = db_ops.save_paper(
        arxiv_id="",
        doi="",
        title="RoleA Journal Paper A",
        authors=["Alice"],
        abstract="A",
    )
    paper_b_id = db_ops.save_paper(
        arxiv_id="",
        doi="",
        title="RoleA Journal Paper B",
        authors=["Bob"],
        abstract="B",
    )

    assert paper_a_id != paper_b_id


def test_get_push_papers_filters_feedback_logs_and_sorts_by_rank(test_db_path):
    _use_test_db(test_db_path)

    paper_a_id = db_ops.save_paper("", "", "Paper A", ["Alice", "Bob"], "A")
    paper_b_id = db_ops.save_paper("", "", "Paper B", ["Carol"], "B")

    db_ops.log_behavior(
        user_id="user_rolea",
        push_id="push_rolea_001",
        paper_id=paper_a_id,
        action="pushed",
        action_type="push",
        category="high_relevant",
        metadata={"rank": 2, "category": "high_relevant"},
    )
    db_ops.log_behavior(
        user_id="user_rolea",
        push_id="push_rolea_001",
        paper_id=paper_b_id,
        action="pushed",
        action_type="push",
        category="must_read",
        metadata={"rank": 1, "category": "must_read"},
    )
    db_ops.log_behavior(
        user_id="user_rolea",
        push_id="push_rolea_001",
        paper_id=paper_a_id,
        action="selected",
        action_type="selected",
        category="high_relevant",
        metadata={"paper_number": 2},
    )

    push_info = db_ops.get_push_papers("push_rolea_001")
    latest_push = db_ops.get_latest_push("user_rolea")

    assert push_info["push_id"] == "push_rolea_001"
    assert len(push_info["papers"]) == 2
    assert [paper["title"] for paper in push_info["papers"]] == ["Paper B", "Paper A"]
    assert push_info["papers"][1]["authors"] == ["Alice", "Bob"]

    assert latest_push["push_id"] == "push_rolea_001"
    assert [paper["rank"] for paper in latest_push["papers"]] == [1, 2]


def test_parse_user_reply_uses_real_push_length_instead_of_hardcoded_50():
    papers = [{"id": idx + 1, "category": "edge_relevant"} for idx in range(60)]
    selected = feedback_agent.parse_user_reply("51-60", papers)
    assert selected == set(range(51, 61))


def test_process_feedback_accepts_none_and_normalizes_author_lists(test_db_path, sample_profile):
    _use_test_db(test_db_path)

    profile = copy.deepcopy(sample_profile)
    profile["user_id"] = "user_rolea"
    profile["author_heat"] = {}
    db_ops.create_profile("user_rolea", profile)

    papers = [
        {
            "id": 1,
            "title": "RoleA Paper",
            "authors": '["Alice","Bob"]',
            "category": "maybe_interested",
        }
    ]

    none_result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_none",
        reply="none",
        papers=papers,
        send_to_feishu=False,
    )
    select_result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_select",
        reply="1",
        papers=papers,
        send_to_feishu=False,
    )
    updated_profile = db_ops.get_profile("user_rolea")

    assert none_result["status"] == "success"
    assert none_result["selected_count"] == 0
    assert none_result["skipped_count"] == 1

    assert select_result["status"] == "success"
    assert updated_profile["author_heat"]["Alice"] > 0
    assert updated_profile["author_heat"]["Bob"] > 0
    assert "A" not in updated_profile["author_heat"]


def test_selection_summary_uses_pdf_style_ranges():
    papers = [
        {"id": idx + 1, "title": f"Paper {idx + 1}", "category": "high_relevant"}
        for idx in range(5)
    ]

    summary = feedback_agent.format_selection_summary({1, 2, 4}, 5, papers)

    assert "01-02" in summary
    assert "04" in summary
    assert "05" in summary


def test_build_learning_signals_includes_contrastive_pair_explanation():
    papers = [
        {
            "id": 1,
            "title": "Emergence in Biological Models",
            "category": "maybe_interested",
            "topics": ["bio-molecular", "emergence"],
        },
        {
            "id": 2,
            "title": "AutoML for Science",
            "category": "high_relevant",
            "topics": ["optimization", "science-discovery"],
        },
    ]

    signals = feedback_agent.build_learning_signals({1}, {2}, papers)

    assert any("你选了 01" in signal and "跳过了 02" in signal for signal in signals)


def test_process_feedback_triggers_reading_report_generation_for_selected_papers(
    test_db_path,
    sample_profile,
    monkeypatch,
):
    _use_test_db(test_db_path)

    profile = copy.deepcopy(sample_profile)
    profile["user_id"] = "user_rolea"
    db_ops.create_profile("user_rolea", profile)

    captured = {}

    def fake_send_text(target_id, text, use_chat_id=False):
        captured.setdefault("messages", []).append(
            {"target_id": target_id, "text": text, "use_chat_id": use_chat_id}
        )
        return {"ok": True}

    def fake_create_reports(**kwargs):
        captured["report_kwargs"] = kwargs
        return [{"title": "[reading] RoleA Paper", "url": "https://example.feishu.cn/docx/report-1"}]

    monkeypatch.setattr(feedback_agent, "send_text", fake_send_text)
    monkeypatch.setattr(
        feedback_agent,
        "create_reading_reports_for_selection",
        fake_create_reports,
    )

    result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_select",
        reply="1",
        papers=[
            {
                "id": 1,
                "title": "RoleA Paper",
                "authors": ["Alice"],
                "category": "high_relevant",
            }
        ],
        chat_id="oc_rolea_test",
        send_to_feishu=True,
    )

    assert result["status"] == "success"
    assert result["reading_reports_created"] == 1
    assert result["reading_report_urls"] == ["https://example.feishu.cn/docx/report-1"]
    assert captured["report_kwargs"]["user_id"] == "user_rolea"
    assert captured["report_kwargs"]["selected"] == {1}
    assert captured["report_kwargs"]["target_id"] == "oc_rolea_test"
    assert captured["report_kwargs"]["use_chat_id"] is True


def test_create_reading_reports_for_selection_passes_actual_paper_ids():
    captured = {}

    class FakeReadingAgent:
        @staticmethod
        def create_reading_report(**kwargs):
            captured.update(kwargs)
            return []

    original_import = feedback_agent.importlib.import_module

    def fake_import(name):
        if name == "agents.reading-agent.main":
            return FakeReadingAgent()
        return original_import(name)

    feedback_agent.importlib.import_module = fake_import
    try:
        feedback_agent.create_reading_reports_for_selection(
            user_id="user_rolea",
            selected={1, 3},
            papers=[
                {"id": 81, "title": "Paper 81"},
                {"id": 83, "title": "Paper 83"},
                {"id": 82, "title": "Paper 82"},
            ],
            target_id="oc_test_chat",
            use_chat_id=True,
            send_to_feishu=True,
        )
    finally:
        feedback_agent.importlib.import_module = original_import

    assert captured["paper_ids"] == [81, 82]


def test_process_feedback_skips_reading_report_generation_when_feishu_send_disabled(
    test_db_path,
    sample_profile,
    monkeypatch,
):
    _use_test_db(test_db_path)

    profile = copy.deepcopy(sample_profile)
    profile["user_id"] = "user_rolea"
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(
        feedback_agent,
        "create_reading_reports_for_selection",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_select",
        reply="1",
        papers=[
            {
                "id": 1,
                "title": "RoleA Paper",
                "authors": ["Alice"],
                "category": "high_relevant",
            }
        ],
        send_to_feishu=False,
    )

    assert result["status"] == "success"
    assert result["reading_reports_created"] == 0


def test_process_feedback_logs_drift_snapshot_for_legacy_profile(test_db_path, sample_profile):
    _use_test_db(test_db_path)

    legacy_profile = copy.deepcopy(sample_profile)
    legacy_profile["user_id"] = "user_rolea"
    legacy_profile.pop("drift_state", None)
    db_ops.create_profile("user_rolea", legacy_profile)

    result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_drift",
        reply="1",
        papers=[
            {
                "id": 1,
                "title": "RoleA Paper",
                "authors": ["Alice"],
                "keywords": ["gui-agent"],
                "embedding": [1.0, 0.0, 0.0],
                "category": "high_relevant",
            },
            {
                "id": 2,
                "title": "Skipped Paper",
                "authors": ["Bob"],
                "keywords": ["bio-molecular"],
                "embedding": [0.0, 1.0, 0.0],
                "category": "maybe_interested",
            },
        ],
        send_to_feishu=False,
    )
    updated_profile = db_ops.get_profile("user_rolea")
    logs = db_ops.get_behavior_logs("user_rolea", "2000-01-01", "2100-01-01")
    drift_logs = [log for log in logs if log["action"] == "profile_updated" and log["action_type"] == "drift_update"]

    assert result["status"] == "success"
    assert "drift_state" in updated_profile
    assert updated_profile["drift_state"]["status"] in {"stable", "shifting", "recovered"}
    assert len(drift_logs) == 1


def test_process_feedback_all_lock_skips_profile_learning(
    test_db_path,
    sample_profile,
    monkeypatch,
):
    _use_test_db(test_db_path)

    profile = copy.deepcopy(sample_profile)
    profile["user_id"] = "user_rolea"
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(
        feedback_agent,
        "update_profile_based_on_selection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("all lock should skip profile learning")),
    )

    result = feedback_agent.process_feedback(
        user_id="user_rolea",
        push_id="push_all_lock",
        reply="all lock",
        papers=[
            {"id": 1, "title": "Must Read A", "authors": ["Alice"], "category": "must_read"},
            {"id": 2, "title": "Other B", "authors": ["Bob"], "category": "high_relevant"},
        ],
        send_to_feishu=False,
    )

    assert result["status"] == "success"
    assert result["selected_count"] == 1
    assert result["skipped_count"] == 1


def test_estimate_feedback_strength_multiplier_uses_push_latency(monkeypatch):
    now = feedback_agent.datetime(2026, 4, 18, 10, 0, 0)

    monkeypatch.setattr(
        feedback_agent,
        "get_push_papers",
        lambda push_id: {"push_time": "2026-04-18 09:50:00"},
    )

    multiplier, latency_seconds = feedback_agent.estimate_feedback_strength_multiplier("push_1", now)

    assert multiplier > 1.0
    assert latency_seconds == 600.0
