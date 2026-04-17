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
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
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
    assert (
        "https://example.feishu.cn/docx/1" in sent_messages[0]["text"]
        or "target=https%3A%2F%2Fexample.feishu.cn%2Fdocx%2F1" in sent_messages[0]["text"]
    )
    assert (
        "https://example.feishu.cn/docx/2" in sent_messages[0]["text"]
        or "target=https%3A%2F%2Fexample.feishu.cn%2Fdocx%2F2" in sent_messages[0]["text"]
    )


def test_create_reading_report_uses_tracking_links_when_public_url_available(monkeypatch):
    monkeypatch.setattr(reading_agent, "get_profile", lambda user_id: {"core_directions": {"machine-learning": 0.8}})
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(reading_agent, "enrich_paper_for_reading_report", lambda paper: (paper, None, None))
    monkeypatch.setattr(reading_agent, "_load_public_webhook_base_url", lambda: "https://demo.ngrok.app")

    sent_messages = []
    monkeypatch.setattr(
        reading_agent,
        "send_text",
        lambda target_id, text, use_chat_id=False: sent_messages.append(text) or {"ok": True},
    )
    monkeypatch.setattr(
        reading_agent,
        "create_doc",
        lambda title, content, folder_id=None: {"url": "https://example.feishu.cn/docx/1", "obj_token": "doc_1"},
    )

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1],
        papers=[{"id": 1, "title": "Paper One", "authors": ["Alice"], "abstract": "Abstract one"}],
        send_to_feishu=True,
        chat_id="oc_rolea_test",
    )

    assert len(docs) == 1
    assert docs[0]["tracking_url"].startswith("https://demo.ngrok.app/r/doc?")
    assert "https://demo.ngrok.app/r/doc?" in sent_messages[0]


def test_create_reading_report_direct_upload_applies_weak_reading_signal(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {}, "topic_weights": {}, "methodology_preferences": {}},
    )
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (
            {
                **paper,
                "title": "GUI Agent Survey",
                "authors": ["Alice"],
                "abstract": "We study GUI agents for interface automation.",
            },
            {
                "abstract": "We study GUI agents for interface automation.",
                "inferred_topics": ["gui agent"],
                "inferred_directions": [{"name": "GUI Agent", "confidence": 0.66}],
                "sections": {},
                "full_text": "We study GUI agents for interface automation.",
            },
            None,
        ),
    )

    updated_profiles = []

    monkeypatch.setattr(
        reading_agent,
        "update_profile_with_reading_signal",
        lambda profile, **kwargs: {
            **profile,
            "reading_signal_state": {
                "last_signal": {
                    "timestamp": "2026-04-17T13:00:00",
                    "topics": ["gui-agent"],
                    "activated_topics": [],
                    "strength": "weak",
                    "source_type": kwargs.get("source_type", ""),
                    "source_key": kwargs.get("source_key", ""),
                    "explicit_note": "",
                },
                "short_term_topics": {},
            },
        },
    )
    monkeypatch.setattr(reading_agent, "update_profile", lambda user_id, profile: updated_profiles.append((user_id, profile)))
    monkeypatch.setattr(
        reading_agent,
        "create_doc",
        lambda title, content, folder_id=None: {"url": "https://example.feishu.cn/docx/direct-upload", "obj_token": "doc_direct_upload"},
    )

    logged = []
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: logged.append(kwargs))

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[],
        papers=[{"pdf_path": "C:/tmp/uploaded.pdf", "title": "Uploaded PDF"}],
        send_to_feishu=False,
        request_metadata={
            "report_source_type": "feishu_file_key",
            "report_source_key": "file_v3_uploaded_signal",
            "report_source_name": "uploaded.pdf",
        },
    )

    assert len(docs) == 1
    assert updated_profiles
    assert any(log["action_type"] == "reading_signal" for log in logged)
    created_report_log = next(log for log in logged if log["action_type"] == "reading")
    assert created_report_log["metadata"]["reading_signal_topics"] == ["gui-agent"]


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
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
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
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
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


def test_create_reading_report_regenerates_existing_doc_when_metadata_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {"agent": 0.8}, "methodology_preferences": {}},
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reading_agent,
        "get_existing_reading_reports_for_papers",
        lambda user_id, paper_ids: {
            88: {
                "doc_title": "[精读] Old Report",
                "doc_url": "https://example.feishu.cn/docx/old",
                "doc_token": "doc_old",
                "timestamp": "2026-04-14 00:00:00",
                "metadata": {"report_version": reading_agent.READING_REPORT_OUTPUT_VERSION},
            }
        },
    )
    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (
            {
                **paper,
                "title": "Recovered Paper",
                "authors": ["Alice"],
                "abstract": "Recovered abstract from source page.",
            },
            None,
            None,
        ),
    )

    created = {}

    def fake_create_doc(title, content, folder_id=None):
        created["title"] = title
        created["content"] = content
        return {"url": "https://example.feishu.cn/docx/new", "obj_token": "doc_new"}

    monkeypatch.setattr(reading_agent, "create_doc", fake_create_doc)

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1],
        papers=[
            {
                "id": 88,
                "title": "Recovered Paper",
                "authors": [],
                "abstract": "",
                "url": "https://www.nature.com/articles/s41586-026-00001-1",
            }
        ],
        send_to_feishu=False,
    )

    assert len(docs) == 1
    assert docs[0].get("reused") is not True
    assert docs[0]["url"] == "https://example.feishu.cn/docx/new"
    assert "Recovered abstract from source page." in created["content"]


def test_create_reading_report_regenerates_old_version_report_even_when_metadata_complete(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {"agent": 0.8}, "methodology_preferences": {}},
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "get_recent_created_report_by_source", lambda *args, **kwargs: None)
    monkeypatch.setattr(reading_agent, "_synthesize_report_with_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reading_agent,
        "get_existing_reading_reports_for_papers",
        lambda user_id, paper_ids: {
            91: {
                "doc_title": "[精读] Old Version",
                "doc_url": "https://example.feishu.cn/docx/old-version",
                "doc_token": "doc_old_version",
                "timestamp": "2026-04-14 00:00:00",
                "metadata": {"report_version": "2026-04-01-v0"},
            }
        },
    )
    monkeypatch.setattr(
        reading_agent,
        "enrich_paper_for_reading_report",
        lambda paper: (paper, None, None),
    )

    created = {}

    def fake_create_doc(title, content, folder_id=None):
        created["title"] = title
        return {"url": "https://example.feishu.cn/docx/regenerated", "obj_token": "doc_regenerated"}

    monkeypatch.setattr(reading_agent, "create_doc", fake_create_doc)

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1],
        papers=[
            {
                "id": 91,
                "title": "Complete Paper",
                "authors": ["Alice"],
                "abstract": "A complete abstract that would normally satisfy reuse conditions.",
            }
        ],
        send_to_feishu=False,
    )

    assert len(docs) == 1
    assert docs[0].get("reused") is not True
    assert docs[0]["url"] == "https://example.feishu.cn/docx/regenerated"


def test_enrich_paper_for_reading_report_replaces_feed_style_abstract(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "off")

    class FakeJournalFetcher:
        @staticmethod
        def _fetch_article_detail(url):
            return {
                "title": "Recovered Nature Paper",
                "authors": ["Alice", "Bob"],
                "abstract": "Recovered abstract from the article detail page with concrete method and results information.",
                "pdf_url": "https://www.nature.com/articles/example.pdf",
            }

    monkeypatch.setattr(reading_agent, "_load_journal_fetcher", lambda: FakeJournalFetcher())
    monkeypatch.setattr(
        reading_agent,
        "_download_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pdf download should be skipped")),
    )

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "title": "Recovered Nature Paper",
            "authors": ["Alice"],
            "abstract": (
                '<p>Nature, Published online: 14 April 2026; '
                '<a href="https://www.nature.com/articles/s41586-026-00001-1">doi:10.1038/s41586-026-00001-1</a>'
                "</p>The RSS teaser is not the real abstract."
            ),
            "url": "https://www.nature.com/articles/s41586-026-00001-1",
            "venue": "Nature",
        }
    )

    assert parsed_pdf is None
    assert pdf_error is None
    assert enriched["abstract"] == (
        "Recovered abstract from the article detail page with concrete method and results information."
    )
    assert enriched["pdf_url"] == "https://www.nature.com/articles/example.pdf"


def test_generate_reading_report_strips_html_from_abstract_preview():
    paper = {
        "title": "Nature Paper",
        "authors": ["Alice"],
        "abstract": (
            '<p>Nature, Published online: 14 April 2026; '
            '<a href="https://www.nature.com/articles/s41586-026-00001-1">doi:10.1038/s41586-026-00001-1</a>'
            "</p><p>This is the actual abstract preview content.</p>"
        ),
        "venue": "Nature",
    }
    profile = {"core_directions": {}, "methodology_preferences": {}}

    report = reading_agent.generate_reading_report(
        paper,
        profile,
        report_payload={"abstract": paper["abstract"]},
    )

    assert "<p>" not in report
    assert "Published online:" not in report
    assert "This is the actual abstract preview content." in report


def test_retrieve_report_evidence_ranks_expected_pdf_chunks(monkeypatch):
    class FakeEmbeddingService:
        descriptor = "fake:test:4"

        def embed_batch(self, texts):
            vectors = []
            for text in texts:
                lowered = text.lower()
                background_score = float(sum(lowered.count(token) for token in ("background", "motivation", "challenge", "dataset shift")))
                method_score = float(sum(lowered.count(token) for token in ("method", "approach", "two-stage planner", "evidence retriever", "gating network")))
                results_score = float(sum(lowered.count(token) for token in ("results", "improves", "12%", "beats the baseline", "benchmark", "evaluation")))
                limitation_score = float(sum(lowered.count(token) for token in ("limitation", "limitations", "small number of domains", "future work")))
                vectors.append(
                    [
                        background_score,
                        method_score,
                        results_score,
                        limitation_score,
                    ]
                )
            return vectors

        @staticmethod
        def cosine_similarity(vector1, vector2):
            dot_product = sum(a * b for a, b in zip(vector1, vector2))
            norm1 = sum(a * a for a in vector1) ** 0.5
            norm2 = sum(b * b for b in vector2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    class FakeEmbeddingModule:
        @staticmethod
        def get_embedding_service():
            return FakeEmbeddingService()

    monkeypatch.setattr(reading_agent, "_load_embedding_module", lambda: FakeEmbeddingModule())

    paper = {
        "title": "Scientific Planner",
        "abstract": "We study literature triage under dataset shift.",
    }
    profile = {
        "core_directions": {"agent": 0.8, "retrieval": 0.7},
        "methodology_preferences": {},
    }
    parsed_pdf = {
        "abstract": "We study literature triage under dataset shift.",
        "sections": {
            "introduction": "The main challenge is dataset shift across scientific domains and reviewer preferences.",
            "method": "We propose a two-stage planner with an evidence retriever and a gating network.",
            "results": "Across three benchmark settings, the method improves ranking quality by 12% and beats the baseline.",
            "discussion": "One limitation is that the evaluation covers a small number of domains.",
        },
        "full_text": (
            "The main challenge is dataset shift across scientific domains and reviewer preferences. "
            "We propose a two-stage planner with an evidence retriever and a gating network. "
            "Across three benchmark settings, the method improves ranking quality by 12% and beats the baseline. "
            "One limitation is that the evaluation covers a small number of domains."
        ),
    }

    evidence = reading_agent._retrieve_report_evidence(paper, profile, parsed_pdf)

    assert evidence["descriptor"] == "fake:test:4"
    assert evidence["chunk_count"] >= 4
    assert "dataset shift" in evidence["matches"]["background"][0]["text"].lower()
    assert "two-stage planner" in evidence["matches"]["method"][0]["text"].lower()
    assert "12%" in evidence["matches"]["results"][0]["text"]
    assert "small number of domains" in evidence["matches"]["limitations"][0]["text"].lower()


def test_build_heuristic_report_payload_uses_retrieved_evidence(monkeypatch):
    class FakeEmbeddingService:
        descriptor = "fake:test:4"

        def embed_batch(self, texts):
            vectors = []
            for text in texts:
                lowered = text.lower()
                background_score = float(sum(lowered.count(token) for token in ("background", "motivation", "challenge", "dataset shift")))
                method_score = float(sum(lowered.count(token) for token in ("method", "approach", "two-stage planner", "evidence retriever", "gating network")))
                results_score = float(sum(lowered.count(token) for token in ("results", "improves", "12%", "beats the baseline", "benchmark", "evaluation")))
                limitation_score = float(sum(lowered.count(token) for token in ("limitation", "limitations", "small number of domains", "future work")))
                vectors.append(
                    [
                        background_score,
                        method_score,
                        results_score,
                        limitation_score,
                    ]
                )
            return vectors

        @staticmethod
        def cosine_similarity(vector1, vector2):
            dot_product = sum(a * b for a, b in zip(vector1, vector2))
            norm1 = sum(a * a for a in vector1) ** 0.5
            norm2 = sum(b * b for b in vector2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    class FakeEmbeddingModule:
        @staticmethod
        def get_embedding_service():
            return FakeEmbeddingService()

    monkeypatch.setattr(reading_agent, "_load_embedding_module", lambda: FakeEmbeddingModule())

    paper = {
        "title": "Scientific Planner",
        "abstract": "We study literature triage under dataset shift.",
        "score": 0.81,
    }
    profile = {
        "core_directions": {"agent": 0.8, "retrieval": 0.7},
        "methodology_preferences": {"preference_systematic_work_over_incremental": True},
    }
    parsed_pdf = {
        "abstract": "We study literature triage under dataset shift.",
        "sections": {
            "introduction": "The main challenge is dataset shift across scientific domains and reviewer preferences.",
            "method": "We propose a two-stage planner with an evidence retriever and a gating network.",
            "results": "Across three benchmark settings, the method improves ranking quality by 12% and beats the baseline.",
            "discussion": "One limitation is that the evaluation covers a small number of domains.",
        },
        "full_text": (
            "The main challenge is dataset shift across scientific domains and reviewer preferences. "
            "We propose a two-stage planner with an evidence retriever and a gating network. "
            "Across three benchmark settings, the method improves ranking quality by 12% and beats the baseline. "
            "One limitation is that the evaluation covers a small number of domains."
        ),
    }

    payload = reading_agent.build_heuristic_report_payload(
        paper,
        profile,
        parsed_pdf=parsed_pdf,
        pdf_error=None,
    )

    assert payload["analysis_source"] == "pdf"
    assert "two-stage planner" in payload["core_method"].lower()
    assert "12%" in payload["key_results"]
    assert "small number of domains" in " ".join(payload["limitations"]).lower()
    assert "切块语义检索证据" in payload["analysis_note"]
    assert payload["retrieved_evidence"]["descriptor"] == "fake:test:4"
    assert payload["retrieved_evidence"]["matches"]["method"]
    assert payload["field_evidence_map"]["core_method"]
    assert payload["report_evidence_anchors"]["results"]


def test_retrieve_report_evidence_uses_profile_embedding_as_primary_signal(monkeypatch):
    class FakeEmbeddingService:
        descriptor = "fake:test:profile"

        def embed_batch(self, texts):
            vectors = []
            for text in texts:
                lowered = text.lower()
                vectors.append(
                    [
                        float("agent" in lowered or "retrieval" in lowered),
                        float("planner" in lowered or "workflow" in lowered),
                        float("protein" in lowered or "molecule" in lowered),
                        float("benchmark" in lowered or "result" in lowered),
                    ]
                )
            return vectors

        @staticmethod
        def cosine_similarity(vector1, vector2):
            dot_product = sum(a * b for a, b in zip(vector1, vector2))
            norm1 = sum(a * a for a in vector1) ** 0.5
            norm2 = sum(b * b for b in vector2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    class FakeEmbeddingModule:
        @staticmethod
        def get_embedding_service():
            return FakeEmbeddingService()

    monkeypatch.setattr(reading_agent, "_load_embedding_module", lambda: FakeEmbeddingModule())
    monkeypatch.setattr(reading_agent, "READING_REPORT_PROFILE_RETRIEVAL_WEIGHT", 0.5)
    monkeypatch.setattr(reading_agent, "READING_REPORT_EVIDENCE_CACHE_ENABLED", False)

    paper = {"title": "Mixed Paper", "abstract": "This paper includes multiple chunks."}
    profile = {"core_directions": {"agent": 0.8, "retrieval": 0.7}, "methodology_preferences": {}}
    parsed_pdf = {
        "abstract": "This paper includes multiple chunks.",
        "sections": {
            "method": "We propose an agent retrieval workflow planner for long-horizon literature tasks.",
            "results": "Benchmark results show the planner improves retrieval quality.",
            "discussion": "A protein analysis appendix is unrelated to the user profile.",
        },
        "full_text": (
            "We propose an agent retrieval workflow planner for long-horizon literature tasks. "
            "Benchmark results show the planner improves retrieval quality. "
            "A protein analysis appendix is unrelated to the user profile."
        ),
    }

    evidence = reading_agent._retrieve_report_evidence(paper, profile, parsed_pdf)

    assert evidence["profile_retrieval_weight"] == 0.5
    assert "agent retrieval workflow planner" in evidence["matches"]["relevance"][0]["text"].lower()


def test_generate_reading_report_includes_pdf_evidence_anchor_section():
    paper = {
        "title": "Scientific Planner",
        "authors": ["Alice"],
        "abstract": "We propose a planner for scientific agents.",
        "score": 0.81,
    }
    profile = {"core_directions": {"agent": 0.8}, "methodology_preferences": {}}
    payload = {
        "abstract": "We propose a planner for scientific agents.",
        "one_sentence_summary": "This paper proposes a two-stage planner.",
        "research_background": "The main challenge is dataset shift.",
        "core_method": "We propose a two-stage planner with an evidence retriever.",
        "key_results": "The method improves ranking quality by 12%.",
        "main_contributions": ["提出两阶段流程", "增强证据过滤"],
        "limitations": ["跨领域验证还不够充分"],
        "relevance_points": ["与智能体方向高度相关"],
        "reading_focus": ["先看 Method，再看 Results"],
        "estimated_reading_minutes": 8,
        "analysis_source": "pdf",
        "analysis_note": "已结合 PDF 切块语义检索证据生成。",
        "recommendation_label": "推荐阅读",
        "field_evidence_map": {
            "core_method": ["Method | score=0.912 | We propose a two-stage planner with an evidence retriever."],
            "key_results": ["Results | score=0.884 | The method improves ranking quality by 12%."],
        },
        "report_evidence_anchors": {
            "method": ["Method | score=0.912 | We propose a two-stage planner with an evidence retriever."],
            "results": ["Results | score=0.884 | The method improves ranking quality by 12%."],
        },
    }

    report = reading_agent.generate_reading_report(paper, profile, report_payload=payload)

    assert "## PDF 证据定位" in report
    assert "Method | score=0.912" in report
    assert "Results | score=0.884" in report
    assert "方法证据锚点" in report
    assert "结果证据锚点" in report


def test_retrieve_report_evidence_uses_persistent_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("READING_REPORT_EVIDENCE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(reading_agent, "READING_REPORT_EVIDENCE_CACHE_ENABLED", True)

    call_counter = {"count": 0}

    class FakeEmbeddingService:
        descriptor = "fake:test:4"

        def embed_batch(self, texts):
            call_counter["count"] += 1
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        @staticmethod
        def cosine_similarity(vector1, vector2):
            return 1.0

    class FakeEmbeddingModule:
        @staticmethod
        def get_embedding_service():
            return FakeEmbeddingService()

    monkeypatch.setattr(reading_agent, "_load_embedding_module", lambda: FakeEmbeddingModule())

    paper = {"title": "Cached Paper", "abstract": "Abstract"}
    profile = {"core_directions": {"agent": 0.8}, "methodology_preferences": {}}
    parsed_pdf = {
        "abstract": "Abstract",
        "sections": {"method": "We propose a cached planner.", "results": "It works well."},
        "full_text": "Abstract We propose a cached planner. It works well.",
    }

    first = reading_agent._retrieve_report_evidence(paper, profile, parsed_pdf)
    second = reading_agent._retrieve_report_evidence(paper, profile, parsed_pdf)

    assert call_counter["count"] == 1
    assert first == second
    assert list(tmp_path.glob("*.json"))


def test_create_reading_report_reuses_existing_docs_for_selected_papers(monkeypatch):
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
        "get_recent_created_report_by_source",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        reading_agent,
        "get_existing_reading_reports_for_papers",
        lambda user_id, paper_ids: {
            1: {
                "paper_id": 1,
                "timestamp": "2026-04-14 16:00:00",
                "paper_title": "Paper One",
                "doc_title": "[精读] Paper One",
                "doc_url": "https://example.feishu.cn/docx/existing-1",
                "doc_token": "doc_existing_1",
                "metadata": {"report_version": reading_agent.READING_REPORT_OUTPUT_VERSION},
            }
        },
    )

    create_doc_calls = []

    def fake_create_doc(title, content, folder_id=None):
        create_doc_calls.append(title)
        return {
            "url": "https://example.feishu.cn/docx/new-2",
            "obj_token": "doc_new_2",
        }

    monkeypatch.setattr(reading_agent, "create_doc", fake_create_doc)

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[1, 2],
        papers=[
            {"id": 1, "title": "Paper One", "authors": ["Alice"], "abstract": "Abstract one"},
            {"id": 2, "title": "Paper Two", "authors": ["Bob"], "abstract": "Abstract two"},
        ],
        send_to_feishu=False,
    )

    assert len(docs) == 2
    assert docs[0]["url"] == "https://example.feishu.cn/docx/existing-1"
    assert docs[0]["reused"] is True
    assert docs[1]["url"] == "https://example.feishu.cn/docx/new-2"
    assert create_doc_calls == ["[精读] Paper Two"]


def test_create_reading_report_reuses_existing_pdf_doc_without_regeneration(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "get_profile",
        lambda user_id: {"core_directions": {"agent": 0.8}, "methodology_preferences": {}},
    )
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: None)
    monkeypatch.setattr(reading_agent, "get_existing_reading_reports_for_papers", lambda user_id, paper_ids: {})
    monkeypatch.setattr(
        reading_agent,
        "get_recent_created_report_by_source",
        lambda user_id, source_type, source_key, days=30: {
            "paper_id": None,
            "timestamp": "2026-04-14 16:10:00",
            "paper_title": "面向兴趣漂移驱动的序列推荐用户表示学习",
            "doc_title": "[精读] 面向兴趣漂移驱动的序列推荐用户表示学习",
            "doc_url": "https://example.feishu.cn/docx/existing-pdf",
            "doc_token": "doc_existing_pdf",
            "metadata": {
                "report_source_type": source_type,
                "report_source_key": source_key,
                "report_version": reading_agent.READING_REPORT_OUTPUT_VERSION,
            },
        },
    )

    monkeypatch.setattr(
        reading_agent,
        "create_doc",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not create a new doc for reused PDF")),
    )

    docs = reading_agent.create_reading_report(
        user_id="user_rolea",
        paper_ids=[],
        papers=[{"pdf_path": "C:/tmp/example.pdf", "title": "面向兴趣漂移驱动的序列推荐用户表示学习"}],
        send_to_feishu=False,
        request_metadata={
            "report_source_type": "feishu_file_key",
            "report_source_key": "file_v3_existing",
        },
    )

    assert len(docs) == 1
    assert docs[0]["url"] == "https://example.feishu.cn/docx/existing-pdf"
    assert docs[0]["reused"] is True


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

    def fake_download(pdf_url, title, referer=None):
        captured["pdf_url"] = pdf_url
        captured["title"] = title
        captured["referer"] = referer
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
    assert captured["referer"] is None
    assert pdf_error is None
    assert parsed_pdf is not None
    assert enriched["abstract"] == "PDF abstract from parsed full text."
    assert enriched["authors"] == ["Carol"]


def test_enrich_paper_backfills_missing_metadata_from_source_page(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "off")

    class FakeJournalFetcher:
        @staticmethod
        def _fetch_article_detail(url):
            return {
                "title": "Recovered Nature Paper",
                "abstract": "Recovered abstract from the journal source page.",
                "authors": ["Dana", "Eli"],
                "pdf_url": "https://www.nature.com/articles/example.pdf",
            }

    monkeypatch.setattr(reading_agent, "_load_journal_fetcher", lambda: FakeJournalFetcher)

    def fail_download(*args, **kwargs):
        raise AssertionError("pdf download should be skipped after source-page metadata backfill")

    monkeypatch.setattr(reading_agent, "_download_pdf", fail_download)

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "id": 70,
            "title": "Recovered Nature Paper",
            "authors": [],
            "abstract": "",
            "url": "https://www.nature.com/articles/s41586-026-00001-1",
            "journal": "nature",
        }
    )

    assert parsed_pdf is None
    assert pdf_error is None
    assert enriched["abstract"] == "Recovered abstract from the journal source page."
    assert enriched["authors"] == ["Dana", "Eli"]
    assert enriched["pdf_url"] == "https://www.nature.com/articles/example.pdf"


def test_generate_reading_report_uses_source_link_when_abstract_missing():
    paper = {
        "title": "No Abstract Paper",
        "authors": ["Alice"],
        "abstract": "",
        "paper_url": "https://example.com/paper",
    }
    profile = {
        "core_directions": {"agent": 0.8},
        "methodology_preferences": {},
    }

    report = reading_agent.generate_reading_report(paper, profile, report_payload={"abstract": ""})

    assert "源站暂未返回可用摘要" in report
    assert "https://example.com/paper" in report


def test_download_pdf_uses_http_get_with_pdf_accept_and_referer(monkeypatch):
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/pdf"}
        content = b"%PDF-1.4\nfake"

    def fake_http_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(reading_agent, "_http_get", fake_http_get)

    pdf_path = reading_agent._download_pdf(
        "https://example.com/paper.pdf",
        "Example Paper",
        referer="https://example.com/article",
    )

    assert captured["url"] == "https://example.com/paper.pdf"
    assert captured["accept_pdf"] is True
    assert captured["referer"] == "https://example.com/article"
    Path(pdf_path).unlink(missing_ok=True)


def test_pick_download_referer_prefers_same_host():
    paper = {
        "url": "https://www.nature.com/articles/s41586-026-00001-1",
        "metadata": {
            "paper_url": "https://doi.org/10.1038/example",
        },
    }

    referer = reading_agent._pick_download_referer(
        paper,
        "https://www.nature.com/articles/s41586-026-00001-1.pdf",
    )

    assert referer == "https://www.nature.com/articles/s41586-026-00001-1"


def test_build_pdf_url_candidates_from_source_url_handles_major_publishers():
    nature_candidates = reading_agent._build_pdf_url_candidates_from_source_url(
        "https://www.nature.com/articles/s41586-026-00001-1"
    )
    science_candidates = reading_agent._build_pdf_url_candidates_from_source_url(
        "https://www.science.org/doi/abs/10.1126/science.aed0645?af=R"
    )
    springer_candidates = reading_agent._build_pdf_url_candidates_from_source_url(
        "https://link.springer.com/article/10.1007/s11263-026-02826-y"
    )

    assert "https://www.nature.com/articles/s41586-026-00001-1_reference.pdf" in nature_candidates
    assert "https://www.nature.com/articles/s41586-026-00001-1.pdf" in nature_candidates
    assert "https://www.science.org/doi/pdf/10.1126/science.aed0645?download=true" in science_candidates
    assert "https://link.springer.com/content/pdf/10.1007/s11263-026-02826-y.pdf" in springer_candidates


def test_extract_pdf_url_falls_back_to_heuristic_candidate_when_source_page_resolution_fails(monkeypatch):
    monkeypatch.setattr(
        reading_agent,
        "_resolve_pdf_url_from_source_page",
        lambda source_url: (_ for _ in ()).throw(RuntimeError("403 forbidden")),
    )

    pdf_url = reading_agent._extract_pdf_url(
        {
            "title": "Science Paper",
            "url": "https://www.science.org/doi/abs/10.1126/science.aed0645?af=R",
        }
    )

    assert pdf_url == "https://www.science.org/doi/pdf/10.1126/science.aed0645?download=true"


def test_build_pdf_download_candidates_adds_site_specific_fallbacks():
    paper = {
        "title": "Nature Paper",
        "url": "https://www.nature.com/articles/s41586-026-00001-1",
    }

    candidates = reading_agent._build_pdf_download_candidates(
        paper,
        "https://example.com/fallback.pdf",
    )

    assert candidates[0] == "https://example.com/fallback.pdf"
    assert "https://www.nature.com/articles/s41586-026-00001-1_reference.pdf" in candidates
    assert "https://www.nature.com/articles/s41586-026-00001-1.pdf" in candidates


def test_reading_report_pdf_mode_defaults_to_always(monkeypatch):
    monkeypatch.delenv("READING_REPORT_PDF_MODE", raising=False)

    assert reading_agent._get_pdf_enrichment_mode() == "always"


def test_should_attempt_pdf_enrichment_parses_research_journal_pdf_in_smart_mode(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "smart")

    should_parse, reason = reading_agent._should_attempt_pdf_enrichment(
        {
            "title": "Recovered Nature Communications Paper",
            "authors": ["Alice", "Bob"],
            "abstract": "We propose a robust benchmark and show strong gains across settings.",
            "venue": "Nature Communications",
            "url": "https://www.nature.com/articles/s41467-026-71877-z",
        },
        "https://www.nature.com/articles/s41467-026-71877-z.pdf",
    )

    assert should_parse is True
    assert reason == "journal_pdf_evidence"


def test_should_attempt_pdf_enrichment_skips_nature_news_page_in_smart_mode(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "smart")

    should_parse, reason = reading_agent._should_attempt_pdf_enrichment(
        {
            "title": "Daily briefing: A treatment to reverse cellular ageing is about to be tested in people",
            "authors": ["Alice"],
            "abstract": "A short complete abstract-like summary from the source page.",
            "venue": "Nature",
            "url": "https://www.nature.com/articles/d41586-026-01225-0",
        },
        "https://www.nature.com/articles/d41586-026-01225-0.pdf",
    )

    assert should_parse is False
    assert reason == "metadata_already_sufficient"


def test_should_attempt_pdf_enrichment_parses_openreview_pdf_in_smart_mode(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "smart")

    should_parse, reason = reading_agent._should_attempt_pdf_enrichment(
        {
            "title": "OpenReview Paper",
            "authors": ["Alice", "Bob"],
            "abstract": "We propose a multimodal reasoning benchmark with strong gains across settings.",
            "venue": "ICLR",
            "openreview_url": "https://openreview.net/forum?id=abc123",
        },
        "https://openreview.net/pdf?id=abc123",
    )

    assert should_parse is True
    assert reason == "conference_pdf_evidence"


def test_build_heuristic_report_payload_uses_source_page_fulltext(monkeypatch):
    class FakeEmbeddingService:
        descriptor = "fake:test:4"

        def embed_batch(self, texts):
            vectors = []
            for text in texts:
                lowered = text.lower()
                vectors.append(
                    [
                        float(sum(lowered.count(token) for token in ("challenge", "motivation", "background"))),
                        float(sum(lowered.count(token) for token in ("method", "approach", "extractor", "pipeline"))),
                        float(sum(lowered.count(token) for token in ("results", "improves", "richer", "benchmark"))),
                        float(sum(lowered.count(token) for token in ("limitation", "limitations", "fallback"))),
                    ]
                )
            return vectors

        @staticmethod
        def cosine_similarity(vector1, vector2):
            dot_product = sum(a * b for a, b in zip(vector1, vector2))
            norm1 = sum(a * a for a in vector1) ** 0.5
            norm2 = sum(b * b for b in vector2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    class FakeEmbeddingModule:
        @staticmethod
        def get_embedding_service():
            return FakeEmbeddingService()

    monkeypatch.setattr(reading_agent, "_load_embedding_module", lambda: FakeEmbeddingModule())

    paper = {
        "title": "Source Page Scientific Reader",
        "abstract": "We study source-page fallback for reading reports.",
        "openreview_url": "https://openreview.net/forum?id=source-page-demo",
    }
    profile = {"core_directions": {"agent": 0.8}, "methodology_preferences": {}}
    parsed_source_page = {
        "source_kind": "source_page",
        "abstract": "We study source-page fallback for reading reports.",
        "sections": {
            "introduction": "The core challenge is that many papers expose useful body text even when the PDF cannot be fetched reliably.",
            "method": "We propose a source-page section extractor and reuse the same evidence retrieval pipeline as PDF-based reports.",
            "results": "Results show the fallback report keeps method and result details richer than an abstract-only summary on a benchmark set.",
            "discussion": "One limitation is that publisher HTML structure can vary across venues.",
        },
        "full_text": (
            "The core challenge is that many papers expose useful body text even when the PDF cannot be fetched reliably. "
            "We propose a source-page section extractor and reuse the same evidence retrieval pipeline as PDF-based reports. "
            "Results show the fallback report keeps method and result details richer than an abstract-only summary on a benchmark set. "
            "One limitation is that publisher HTML structure can vary across venues."
        ),
    }

    payload = reading_agent.build_heuristic_report_payload(
        paper,
        profile,
        parsed_pdf=parsed_source_page,
        pdf_error="403 Client Error: Forbidden",
    )
    report = reading_agent.generate_reading_report(paper, profile, report_payload=payload)

    assert payload["analysis_source"] == "source_page"
    assert "source-page section extractor" in payload["core_method"].lower()
    assert "源站正文" in payload["analysis_note"]
    assert "## 全文证据定位" in report
    assert "源站正文 + 元数据" in report


def test_enrich_paper_falls_back_to_source_page_when_pdf_download_fails(monkeypatch):
    monkeypatch.setenv("READING_REPORT_PDF_MODE", "always")

    class FakeJournalFetcher:
        @staticmethod
        def _fetch_article_detail(url):
            return {
                "title": "Fallback OpenReview Paper",
                "abstract": "Recovered abstract from the source page.",
                "authors": ["Alice", "Bob"],
                "pdf_url": "https://openreview.net/pdf?id=fallback-demo",
                "metadata": {
                    "source_page": {
                        "source_kind": "source_page",
                        "source_url": url,
                        "abstract": "Recovered abstract from the source page.",
                        "sections": {
                            "method": "We propose a source-page fallback pipeline for structured reading reports.",
                            "results": "The fallback keeps links, sections, and evidence anchors even when the PDF fails.",
                        },
                        "full_text": (
                            "Recovered abstract from the source page. "
                            "We propose a source-page fallback pipeline for structured reading reports. "
                            "The fallback keeps links, sections, and evidence anchors even when the PDF fails."
                        ),
                    }
                },
            }

    monkeypatch.setattr(reading_agent, "_load_journal_fetcher", lambda: FakeJournalFetcher())
    monkeypatch.setattr(
        reading_agent,
        "_download_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("403 forbidden")),
    )

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "title": "Fallback OpenReview Paper",
            "authors": [],
            "abstract": "",
            "venue": "ICLR",
            "openreview_url": "https://openreview.net/forum?id=fallback-demo",
        }
    )

    assert enriched["abstract"] == "Recovered abstract from the source page."
    assert parsed_pdf is not None
    assert parsed_pdf["source_kind"] == "source_page"


def test_enrich_paper_prefers_longer_pdf_abstract_over_short_metadata(monkeypatch):
    pdf_path = Path("C:/tmp/example-full-abstract.pdf")

    monkeypatch.setattr(reading_agent.os.path, "exists", lambda path: str(path) == str(pdf_path))
    monkeypatch.setattr(
        reading_agent,
        "_parse_pdf_for_report",
        lambda path: {
            "abstract": (
                "This paper presents a complete PDF abstract with concrete motivation, method design, "
                "training setup, and experimental findings that are substantially longer than the teaser."
            ),
            "authors": ["Alice", "Bob"],
            "sections": {},
            "full_text": "Full PDF text.",
        },
    )

    enriched, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(
        {
            "title": "PDF Preferred Abstract",
            "pdf_path": str(pdf_path),
            "abstract": "Short teaser abstract.",
            "authors": ["Alice"],
        }
    )

    assert pdf_error is None
    assert parsed_pdf is not None
    assert enriched["abstract"].startswith("This paper presents a complete PDF abstract")


def test_build_heuristic_report_payload_keeps_full_pdf_abstract():
    full_abstract = (
        "This paper presents a complete PDF abstract with concrete motivation, method design, "
        "training setup, evaluation protocol, and detailed empirical findings. "
        "It is intentionally longer than the reading-report abstract character cap and should still "
        "be preserved in full once the PDF extractor has already recovered it."
    )

    payload = reading_agent.build_heuristic_report_payload(
        {
            "title": "Full PDF Abstract Paper",
            "abstract": "Short metadata teaser.",
        },
        {"core_directions": {"agent": 0.8}, "methodology_preferences": {}},
        parsed_pdf={
            "source_kind": "pdf",
            "abstract": full_abstract,
            "sections": {},
            "full_text": full_abstract,
        },
    )

    assert payload["abstract"] == full_abstract
