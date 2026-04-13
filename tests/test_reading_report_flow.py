"""
Tests for reading-report document link delivery.
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

reading_agent = importlib.import_module("agents.reading-agent.main")


def test_create_reading_report_sends_doc_links(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {"machine-learning": 0.8}},
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (paper, None, None),
    )

    sent_messages = []

    def fake_send_text(target_id, text, use_chat_id=False):
        sent_messages.append(
            {"target_id": target_id, "text": text, "use_chat_id": use_chat_id}
        )
        return {"ok": True}

    create_doc_calls = []

    def fake_create_doc(title, content, folder_id=None):
        create_doc_calls.append({"title": title, "content": content, "folder_id": folder_id})
        return {
            "url": f"https://example.feishu.cn/docx/{len(create_doc_calls)}",
            "obj_token": f"doc_{len(create_doc_calls)}",
        }

    monkeypatch.setattr(reading_agent, "send_text", fake_send_text)
    monkeypatch.setattr(reading_agent, "create_doc", fake_create_doc)

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1, 2],
        papers=[
            {
                "id": 1,
                "arxiv_id": "2401.00001",
                "title": "Paper One",
                "authors": ["Alice"],
                "abstract": "Abstract one",
            },
            {
                "id": 2,
                "arxiv_id": "2401.00002",
                "title": "Paper Two",
                "authors": ["Bob"],
                "abstract": "Abstract two",
            },
        ],
        send_to_feishu=True,
        chat_id="oc_rolea_test",
    )

    assert len(docs) == 2
    assert docs[0]["url"] == "https://example.feishu.cn/docx/1"
    assert docs[1]["doc_token"] == "doc_2"
    assert sent_messages[0]["target_id"] == "oc_rolea_test"
    assert sent_messages[0]["use_chat_id"] is True
    assert "https://example.feishu.cn/docx/1" in sent_messages[0]["text"]
    assert "https://example.feishu.cn/docx/2" in sent_messages[0]["text"]


def test_generate_reading_report_contains_real_sections_without_placeholders():
    paper = {
        "title": "Adaptive Scientific Agents",
        "authors": ["Alice", "Bob"],
        "abstract": (
            "We propose an adaptive scientific agent framework for literature triage. "
            "The method improves retrieval quality and reduces manual screening effort."
        ),
        "venue": "arXiv",
        "publish_date": "2026-04-13",
        "score": 0.82,
    }
    profile = {
        "core_directions": {"agent": 0.8, "retrieval": 0.7},
        "methodology_preferences": {"preference_systematic_work_over_incremental": True},
    }

    payload = reading_agent.build_heuristic_report_payload(paper, profile)
    report = reading_agent.generate_reading_report(paper, profile, report_payload=payload)

    assert "<!--" not in report
    assert "## 主要贡献" in report
    assert "## 与你的研究画像关联" in report
    assert "adaptive scientific agent framework" in report.lower()
    assert "推荐级别" in report


def test_create_reading_report_uses_pdf_enrichment_for_doc_content(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {
            "core_directions": {"agent": 0.8},
            "methodology_preferences": {"preference_data_driven_over_theory": True},
        },
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)

    parsed_pdf = {
        "abstract": "We propose a planner for scientific agents.",
        "sections": {
            "introduction": "This paper studies how scientific agents prioritize papers under limited attention budgets.",
            "method": "We propose a two-stage planner that first filters evidence and then ranks candidate papers.",
            "results": "Results show the planner improves ranking quality and reduces wasted reading time.",
            "conclusion": "A remaining limitation is evaluation breadth across different research domains.",
        },
        "full_text": (
            "This paper studies how scientific agents prioritize papers under limited attention budgets. "
            "We propose a two-stage planner that first filters evidence and then ranks candidate papers. "
            "Results show the planner improves ranking quality and reduces wasted reading time."
        ),
    }

    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (
            {
                **paper,
                "title": "Scientific Planner",
                "authors": ["Alice"],
                "abstract": "We propose a planner for scientific agents.",
            },
            parsed_pdf,
            None,
        ),
    )

    captured = {}

    def fake_create_doc(title, content, folder_id=None):
        captured["title"] = title
        captured["content"] = content
        return {"url": "https://example.feishu.cn/docx/enriched", "obj_token": "doc_enriched"}

    monkeypatch.setattr(reading_agent, "create_doc", fake_create_doc)

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1],
        papers=[{"id": 1, "title": "Paper 1"}],
        send_to_feishu=False,
    )

    assert len(docs) == 1
    assert docs[0]["report_payload"]["analysis_source"] == "pdf"
    assert "two-stage planner" in captured["content"].lower()
    assert "ranking quality" in captured["content"].lower()
    assert "<!--" not in captured["content"]
