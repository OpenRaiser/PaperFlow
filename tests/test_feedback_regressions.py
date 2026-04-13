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
