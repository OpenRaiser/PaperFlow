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


def test_extract_doc_url_ignores_non_url_placeholders():
    doc_info = {
        "url": "[精读] Placeholder title",
        "obj_token": "doc_token_123",
    }

    assert reading_agent.extract_doc_url(doc_info) is None


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
    assert "## 创新点" in report
    assert "## 与我的研究的关系" in report
    assert "## 代码与资源" in report
    assert "## 推荐指数" in report
    assert "adaptive scientific agent framework" in report.lower()
    assert "推荐级别" in report


def test_generate_reading_report_keeps_full_template_and_links_on_fallback():
    paper = {
        "title": "Fallback Report",
        "authors": ["Alice"],
        "abstract": "We propose a lightweight fallback pipeline for literature triage.",
        "venue": "Nature",
        "publish_date": "2026-04-14",
        "arxiv_id": "2604.12345",
        "doi": "10.1000/example",
        "paper_url": "https://example.com/paper",
    }
    profile = {
        "core_directions": {"agent": 0.9},
        "methodology_preferences": {},
    }

    heuristic_payload = reading_agent.build_heuristic_report_payload(
        paper,
        profile,
        parsed_pdf=None,
        pdf_error="403 Client Error: Forbidden",
    )
    report_payload = reading_agent._merge_report_payload(
        heuristic_payload,
        {"analysis_note": "生成式精读补充本次未返回，当前内容仍按精读模板基于已拿到的摘要、元数据和可用 PDF 片段生成。"},
    )
    report = reading_agent.generate_reading_report(paper, profile, report_payload=report_payload)

    assert "## 核心方法" in report
    assert "## 主要结果" in report
    assert "## 创新点" in report
    assert "## 代码与资源" in report
    assert "## 推荐指数" in report
    assert "https://arxiv.org/abs/2604.12345" in report
    assert "https://doi.org/10.1000/example" in report
    assert "https://example.com/paper" in report
    assert "源站拒绝了 PDF 访问" in report
    assert "生成式精读补充本次未返回" in report


def test_create_reading_report_resolves_position_refs_when_db_ids_differ(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {"agent": 0.8}, "methodology_preferences": {}},
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (paper, None, None),
    )
    monkeypatch.setattr(
        reading_agent,
        "create_doc",
        lambda title, content, folder_id=None: {"url": "https://example.feishu.cn/docx/position", "obj_token": "doc_pos"},
    )

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1, 3],
        papers=[
            {"id": 81, "title": "Paper 81", "authors": ["A"], "abstract": "A"},
            {"id": 83, "title": "Paper 83", "authors": ["B"], "abstract": "B"},
            {"id": 82, "title": "Paper 82", "authors": ["C"], "abstract": "C"},
        ],
        send_to_feishu=False,
    )

    assert [doc["paper"]["id"] for doc in docs] == [81, 82]


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
    assert "## 代码与资源" in captured["content"]
    assert "## 推荐指数" in captured["content"]
    assert "<!--" not in captured["content"]


def test_enrich_paper_skips_arxiv_pdf_after_detail_fetch_failure_when_metadata_is_sufficient(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "smart")

    class BrokenFetcher:
        @staticmethod
        def get_paper_detail(arxiv_id, timeout=None):
            raise RuntimeError("ssl eof")

    monkeypatch.setattr(reading_agent, "_load_arxiv_fetcher", lambda: BrokenFetcher)

    def fail_download(*args, **kwargs):
        raise AssertionError("pdf download should be skipped for already-complete metadata")

    monkeypatch.setattr(reading_agent, "_download_pdf", fail_download)

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "id": 68,
            "arxiv_id": "2604.09497v1",
            "title": "BERT-as-a-Judge",
            "authors": ["Alice", "Bob"],
            "abstract": "We propose a robust alternative to lexical evaluation methods.",
        }
    )

    assert parsed_pdf is None
    assert pdf_error is None
    assert enriched["abstract"] == "We propose a robust alternative to lexical evaluation methods."
    assert enriched["authors"] == ["Alice", "Bob"]


def test_enrich_paper_still_uses_pdf_when_metadata_is_incomplete(monkeypatch, tmp_path):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "smart")

    class EmptyFetcher:
        @staticmethod
        def get_paper_detail(arxiv_id, timeout=None):
            return None

    monkeypatch.setattr(reading_agent, "_load_arxiv_fetcher", lambda: EmptyFetcher)

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured = {}

    def fake_download(pdf_url, title):
        captured["pdf_url"] = pdf_url
        captured["title"] = title
        return str(pdf_path)

    monkeypatch.setattr(reading_agent, "_download_pdf", fake_download)
    monkeypatch.setattr(
        reading_agent,
        "_parse_pdf_for_report",
        lambda path: {
            "abstract": "PDF abstract from parsed full text.",
            "authors": ["Carol"],
            "sections": {"method": "We propose a lightweight evaluator."},
            "full_text": "PDF abstract from parsed full text. We propose a lightweight evaluator.",
        },
    )

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "id": 69,
            "arxiv_id": "2604.09497v1",
            "title": "Paper 69",
            "authors": [],
            "abstract": "",
        }
    )

    assert captured["pdf_url"] == "https://arxiv.org/pdf/2604.09497v1.pdf"
    assert captured["title"] == "Paper 69"
    assert pdf_error is None
    assert parsed_pdf is not None
    assert enriched["abstract"] == "PDF abstract from parsed full text."
    assert enriched["authors"] == ["Carol"]


def test_reading_report_pdf_mode_defaults_to_always(monkeypatch):
    monkeypatch.delenv("READING_REPORT_PDF_MODE", raising=False)

    assert reading_agent._get_pdf_enrichment_mode() == "always"
