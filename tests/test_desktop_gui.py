from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from deployments.desktop import server
from deployments.desktop.shared import agents

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_server_routes_are_registered() -> None:
    server_source = (PROJECT_ROOT / "deployments/desktop/server.py").read_text(encoding="utf-8")

    assert "/api/health" in server.GET_ROUTES
    assert "/api/source-options" in server.GET_ROUTES
    assert "/api/settings" in server.POST_ROUTES
    assert "/api/submit" in server.POST_ROUTES
    assert "/api/export" in server.POST_ROUTES
    assert "/api/roles" in server.GET_ROUTES
    assert "/api/roles" in server.POST_ROUTES
    assert "/api/must-read" in server.GET_ROUTES
    assert "/api/must-read" in server.POST_ROUTES
    assert "/api/read/arxiv" in server.POST_ROUTES
    assert "/api/read/pdf" in server.POST_ROUTES
    assert "/api/provider-test" in server.POST_ROUTES
    assert "/api/daily/status" in server.GET_ROUTES
    assert "/api/daily/start" in server.POST_ROUTES
    assert "/api/wiki/ask/stream" in server.POST_ROUTES
    assert 'self.send_header("Cache-Control", "no-store")' in server_source


def test_desktop_wiki_stream_helpers_emit_sse_frames() -> None:
    frame = server._sse_bytes("chunk", {"text": "引用 [1]"})  # noqa: SLF001 - stream wire contract

    assert frame.decode("utf-8") == 'event: chunk\ndata: {"text": "引用 [1]"}\n\n'
    assert server._stream_chunks("abcdef", size=2) == ["ab", "cd", "ef"]  # noqa: SLF001
    source = (PROJECT_ROOT / "deployments/desktop/server.py").read_text(encoding="utf-8")
    assert "agents.wiki_ask_stream" in source
    assert "_api_wiki_ask({}, body)" not in source


def test_desktop_daily_target_date_controls_backend_fetch_window() -> None:
    today = server.datetime.now().date()

    assert server._daily_days_from_body({"days": 7}) == 7  # noqa: SLF001 - GUI date contract
    assert server._daily_days_from_body({"target_date": today.isoformat(), "days": 9}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today - timedelta(days=2)).isoformat()}) == 3  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year + 1)).isoformat(), "days": 3}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year - 1)).isoformat()}) == 14  # noqa: SLF001
    assert "/api/wiki/graph" in server.GET_ROUTES
    assert "/api/wiki/node" in server.POST_ROUTES
    assert callable(server.run_server)


def test_desktop_settings_exposes_storage_paths() -> None:
    settings = agents.settings()
    assert "paths" in settings
    assert "editable_env" in settings
    assert "pdf_dir" in settings["paths"]
    assert "reading_reports_dir" in settings["paths"]
    assert "wiki_dir" in settings["paths"]


def test_desktop_settings_page_renders_storage_paths_as_inputs() -> None:
    html = (PROJECT_ROOT / "deployments" / "desktop" / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments" / "desktop" / "static" / "desktop.js").read_text(encoding="utf-8")

    assert '<script src="desktop.js"></script>' in html
    assert 'id="saveStorageSettingsBtn" class="primary" type="button">保存设置</button>' in html
    assert 'data-env-key="${escapeHtml(row.envKey)}"' in script
    assert "editable-path-row" in script
    assert '$("saveStorageSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));' in script
    assert "PAPERFLOW_PDF_DIR" in script
    assert "PAPERFLOW_READING_REPORTS_DIR" in script
    assert "PAPERFLOW_WIKI_DIR" in script


def test_desktop_wiki_graph_uses_user_nodes_and_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit: [
            {
                "node_id": "paper:1",
                "node_type": "paper",
                "title": "Graph RAG Paper",
                "body": "A graph RAG paper.",
                "metadata": {},
                "keywords": "graph rag",
                "file_path": "papers/graph-rag.md",
                "score": 0.8,
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "topic:rag",
                "node_type": "topic",
                "title": "RAG",
                "body": "Retrieval augmented generation.",
                "metadata": {},
                "keywords": "retrieval",
                "file_path": "topics/rag.md",
                "score": 0.7,
                "updated_at": "2026-06-01",
            },
        ],
    )

    class FakeRows:
        def fetchall(self):
            return [
                {
                    "src_id": "paper:1",
                    "dst_id": "topic:rag",
                    "relation": "same_topic",
                    "weight": 0.9,
                    "metadata_json": '{"reason": "keyword"}',
                    "created_at": "2026-06-01",
                },
                {
                    "src_id": "user:user_test",
                    "dst_id": "paper:1",
                    "relation": "interested_in",
                    "weight": 1.0,
                    "metadata_json": "{}",
                    "created_at": "2026-06-01",
                },
            ]

    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            return FakeRows()

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test")

    assert graph["source"] == "wiki_db"
    assert {node["node_id"] for node in graph["nodes"]} == {"user:user_test", "paper:1", "topic:rag"}
    assert [edge["relation"] for edge in graph["edges"]] == ["same_topic", "interested_in"]


def test_desktop_wiki_graph_prefers_edge_connected_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(agents.wiki_db, "list_nodes", lambda user_id, limit: [])

    class FakeRows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class FakeConnection:
        def execute(self, sql, *_args, **_kwargs):
            if "FROM wiki_edges" in sql:
                return FakeRows(
                    [
                        {
                            "src_id": "paper:important",
                            "dst_id": "topic:rag",
                            "relation": "cites_method",
                            "weight": 0.95,
                            "metadata_json": "{}",
                            "created_at": "2026-06-01",
                        }
                    ]
                )
            if "FROM wiki_nodes" in sql:
                return FakeRows(
                    [
                        {
                            "node_id": "paper:important",
                            "node_type": "paper",
                            "title": "Important Paper",
                            "body": "A highly connected paper.",
                            "metadata_json": "{}",
                            "keywords": "rag",
                            "file_path": "papers/important.md",
                            "score": 0.9,
                            "updated_at": "2026-06-01",
                        },
                        {
                            "node_id": "topic:rag",
                            "node_type": "topic",
                            "title": "RAG",
                            "body": "Retrieval augmented generation.",
                            "metadata_json": "{}",
                            "keywords": "retrieval",
                            "file_path": "topics/rag.md",
                            "score": 0.8,
                            "updated_at": "2026-06-01",
                        },
                    ]
                )
            return FakeRows([])

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test")

    assert {node["node_id"] for node in graph["nodes"]} == {"paper:important", "topic:rag"}
    assert graph["edges"][0]["relation"] == "cites_method"


def test_desktop_wiki_search_filters_to_configured_wiki_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wiki_root = tmp_path / "wiki"
    kept = wiki_root / "user_test" / "papers" / "kept.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("# kept", encoding="utf-8")
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: wiki_root)
    monkeypatch.setattr(
        agents.wiki_db,
        "search_nodes",
        lambda *_args, **_kwargs: [
            {
                "node_id": "paper:kept",
                "node_type": "paper",
                "title": "Kept",
                "body": "exists in configured wiki dir",
                "metadata": {},
                "keywords": "",
                "file_path": "user_test/papers/kept.md",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "paper:old",
                "node_type": "paper",
                "title": "Old",
                "body": "old mirror path",
                "metadata": {},
                "keywords": "",
                "file_path": "user_test/papers/old.md",
                "updated_at": "2026-06-01",
            },
        ],
    )

    result = agents.wiki_search("user_test", query="paper")

    assert [node["node_id"] for node in result["nodes"]] == ["paper:kept"]


def test_desktop_wiki_node_update_preserves_node_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = {
        "node_id": "topic:rag",
        "node_type": "topic",
        "title": "Old RAG",
        "body": "old body",
        "metadata": {"rank": 1},
        "keywords": "rag",
        "source_type": "topic_clustering",
        "source_ref": "keyword_flush",
        "file_path": "topics/rag.md",
    }
    captured = {}

    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: existing)

    def fake_upsert_node(**kwargs):
        captured.update(kwargs)
        return {**existing, **kwargs}

    monkeypatch.setattr(agents.wiki_db, "upsert_node", fake_upsert_node)

    result = agents.update_wiki_node("user_test", "topic:rag", title="New RAG", body="new body")

    assert result["node"]["title"] == "New RAG"
    assert captured["body"] == "new body"
    assert captured["metadata"] == {"rank": 1}
    assert captured["file_path"] == "topics/rag.md"


def test_desktop_wiki_ask_routes_mentions_into_local_cited_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    selected_node = {
        "node_id": "paper:structured-memory",
        "node_type": "paper",
        "title": "Structured Memory Paper",
        "body": "Memory slots improve grounded retrieval.",
        "metadata": {"url": "https://example.com/paper"},
        "keywords": "memory rag",
        "file_path": "reports/structured-memory.md",
        "score": 0.95,
        "updated_at": "2026-06-01",
    }
    captured = {}

    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: selected_node if node_id == selected_node["node_id"] else None)
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda user_id, query, limit=5, node_type=None: [selected_node])

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None):
        captured["question"] = question
        captured["limit"] = limit
        captured["pinned_nodes"] = pinned_nodes or []
        return {
            "text": "结构化记忆方法更强调长期证据槽。[1]",
            "citations": [
                {
                    "index": 1,
                    "node_id": selected_node["node_id"],
                    "title": selected_node["title"],
                    "node_type": selected_node["node_type"],
                    "excerpt": "Memory slots improve grounded retrieval.",
                    "source_type": "reading_report",
                    "source_id": "report-1",
                    "metadata": selected_node["metadata"],
                }
            ],
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask(
        "user_test",
        "对比 @[Structured Memory Paper](paper:structured-memory) 的方法",
        mentions=[{"node_id": "paper:structured-memory", "title": "Structured Memory Paper"}],
    )

    assert payload["mode"] == "wiki"
    assert payload["retrieval_required"] is True
    assert payload["routing_reason"] == "explicit_mention"
    assert captured["pinned_nodes"][0]["node_id"] == "paper:structured-memory"
    assert payload["sources"][0]["title"] == "Structured Memory Paper"
    assert payload["sources"][0]["url"] == "https://example.com/paper"


def test_desktop_wiki_ask_pins_recent_papers_for_trend_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    recent_papers = [
        {
            "id": "paper-1",
            "title": "Agentic Memory for Scientific Reading",
            "abstract": "Agentic memory improves long horizon paper triage and report grounding.",
            "authors": ["A. Researcher", "B. Scientist"],
            "subjects": ["cs.AI", "cs.CL"],
            "category": "high_match",
            "rank": 1,
            "score": 0.94,
            "push_id": "push_20260614",
            "url": "https://example.com/agentic-memory",
        },
        {
            "id": "paper-2",
            "title": "Multimodal Retrieval Agents",
            "summary": "Retrieval agents connect paper figures, text, and user feedback.",
            "authors": "C. Author, D. Author",
            "categories": "cs.IR, cs.MM",
            "category": "explore",
            "rank": 2,
            "score": 0.88,
            "push_id": "push_20260614",
        },
    ]
    captured = {}

    monkeypatch.setattr(agents.db_ops, "get_recent_pushes", lambda user_id, limit=8: recent_papers)
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: {})

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None):
        captured["question"] = question
        captured["pinned_nodes"] = pinned_nodes or []
        return {
            "text": "最近推送集中在 agentic memory 和 multimodal retrieval。[1][2]",
            "citations": [],
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask("user_test", "总结一下我的论文趋势")

    assert payload["mode"] == "wiki"
    assert payload["routing_reason"] == "local_research_context"
    assert [node["title"] for node in captured["pinned_nodes"]] == [
        "Agentic Memory for Scientific Reading",
        "Multimodal Retrieval Agents",
    ]
    first = captured["pinned_nodes"][0]
    second = captured["pinned_nodes"][1]
    assert first["node_type"] == "paper"
    assert first["metadata"]["source"] == "recent_daily_push"
    assert "Agentic memory improves long horizon" in first["body"]
    assert "Category: high_match" in first["body"]
    assert "cs.IR" in second["body"]


def test_desktop_wiki_ask_stream_pins_recent_papers_for_trend_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    recent_paper = {
        "id": "paper-stream-1",
        "title": "Personalized Research Trend Mining",
        "abstract": "User feedback is aggregated into daily research trend summaries.",
        "authors": ["E. Analyst"],
        "subjects": ["cs.DL"],
        "category": "profile_match",
        "rank": 1,
        "score": 0.91,
        "push_id": "push_stream",
    }
    captured = {}

    monkeypatch.setattr(agents.db_ops, "get_recent_pushes", lambda user_id, limit=8: [recent_paper])
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: {})

    def fake_answer_question_stream(user_id, question, *, limit=8, pinned_nodes=None):
        captured["pinned_nodes"] = pinned_nodes or []
        yield {"event": "meta", "data": {"citations": [], "streaming": {"provider": True, "transport": "sse"}}}
        yield {"event": "chunk", "data": {"text": "趋势摘要"}}
        yield {"event": "done", "data": {"text": "趋势摘要", "citations": [], "streaming": {"provider": True, "transport": "sse"}}}

    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", fake_answer_question_stream)

    events = list(agents.wiki_ask_stream("user_test", "最近论文趋势是什么"))

    assert [event["event"] for event in events] == ["meta", "chunk", "done"]
    assert captured["pinned_nodes"][0]["title"] == "Personalized Research Trend Mining"
    assert captured["pinned_nodes"][0]["metadata"]["source"] == "recent_daily_push"
    assert events[-1]["data"]["mode"] == "wiki"


def test_desktop_wiki_ask_pins_filtered_recent_papers_for_rag_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    recent_papers = [
        {
            "id": "rag-paper",
            "title": "RAG Agents for Literature Review",
            "abstract": "Retrieval augmented generation agents summarize recent papers with citations.",
            "authors": ["A. RAG"],
            "subjects": ["cs.IR"],
            "category": "high_match",
            "rank": 1,
            "score": 0.93,
            "push_id": "push_rag",
        },
        {
            "id": "vision-paper",
            "title": "Vision Transformers for Segmentation",
            "abstract": "A segmentation model unrelated to retrieval augmented generation.",
            "authors": ["V. Author"],
            "subjects": ["cs.CV"],
            "category": "explore",
            "rank": 2,
            "score": 0.75,
            "push_id": "push_rag",
        },
    ]
    captured = {}

    monkeypatch.setattr(agents.db_ops, "get_recent_pushes", lambda user_id, limit=32: recent_papers)
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: {})

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None):
        captured["pinned_nodes"] = pinned_nodes or []
        return {"text": "RAG 相关论文集中在带引用的综述代理。[1]", "citations": []}

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask("user_test", "总结最近一周和 RAG 相关的论文")

    assert payload["mode"] == "wiki"
    assert [node["title"] for node in captured["pinned_nodes"]] == ["RAG Agents for Literature Review"]
    assert "Retrieval augmented generation" in captured["pinned_nodes"][0]["body"]


def test_desktop_wiki_ask_requires_mentions_for_ambiguous_two_paper_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.wiki_answer, "answer_question", lambda *_args, **_kwargs: pytest.fail("ambiguous comparisons should not call LLM"))

    payload = agents.wiki_ask("user_test", "对比这两篇论文的方法差异")

    assert payload["mode"] == "wiki"
    assert payload["routing_reason"] == "mention_required"
    assert payload["citations"] == []
    assert "@ 选择两篇具体论文" in payload["text"]


def test_desktop_wiki_ask_stream_requires_mentions_for_ambiguous_two_paper_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", lambda *_args, **_kwargs: pytest.fail("ambiguous comparisons should not stream LLM"))

    events = list(agents.wiki_ask_stream("user_test", "对比这两篇论文的方法差异"))

    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "done"
    assert any(event["event"] == "chunk" for event in events)
    assert events[-1]["data"]["routing_reason"] == "mention_required"
    assert "@ 选择两篇具体论文" in events[-1]["data"]["text"]


def test_desktop_wiki_ask_rolls_section_citations_up_to_paper_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    section_node = {
        "node_id": "section:paper-1#Q1-problem-analysis",
        "node_type": "section",
        "title": "Q1 Problem analysis",
        "body": "The paper frames retrieval grounding as a factuality problem.",
        "metadata": {"parent_paper_id": "paper:paper-1", "section_kind": "Q1-problem-analysis"},
        "keywords": "retrieval grounding",
        "file_path": "reports/paper-1.md",
    }
    paper_node = {
        "node_id": "paper:paper-1",
        "node_type": "paper",
        "title": "Grounded Retrieval for Scientific QA",
        "body": "A paper about grounded retrieval.",
        "metadata": {"url": "https://example.com/grounded"},
        "keywords": "retrieval grounding",
        "file_path": "reports/paper-1.md",
    }

    monkeypatch.setattr(agents.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 0})
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: [section_node])
    monkeypatch.setattr(agents.wiki_db, "get_node", lambda _user_id, node_id: paper_node if node_id == "paper:paper-1" else None)
    monkeypatch.setattr(agents.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})

    class FakeLLM:
        name = "fake"
        model = "fake-model"

        def generate(self, *_args, **_kwargs):
            class Response:
                text = "这篇论文从事实性角度分析检索增强。[1]"
                prompt_tokens = 0
                completion_tokens = 0

            return Response()

    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeLLM())

    payload = agents.wiki_ask("user_test", "总结这篇论文的问题分析")

    assert payload["citations"][0]["title"] == "Grounded Retrieval for Scientific QA"
    assert payload["citations"][0]["node_id"] == "paper:paper-1"
    assert payload["sources"][0]["title"] == "Grounded Retrieval for Scientific QA"
    assert "Q1" not in payload["sources"][0]["title"]


def test_desktop_wiki_ask_stream_uses_native_wiki_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    selected_node = {
        "node_id": "paper:structured-memory",
        "node_type": "paper",
        "title": "Structured Memory Paper",
        "body": "Memory slots improve grounded retrieval.",
        "metadata": {"url": "https://example.com/paper"},
        "keywords": "memory rag",
        "file_path": "reports/structured-memory.md",
        "score": 0.95,
        "updated_at": "2026-06-01",
    }
    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: selected_node)
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda user_id, query, limit=5, node_type=None: [selected_node])

    def fake_answer_question_stream(user_id, question, *, limit=8, pinned_nodes=None):
        yield {
            "event": "meta",
            "data": {
                "citations": [
                    {
                        "index": 1,
                        "node_id": selected_node["node_id"],
                        "title": selected_node["title"],
                        "node_type": selected_node["node_type"],
                        "excerpt": "Memory slots improve grounded retrieval.",
                        "metadata": selected_node["metadata"],
                    }
                ],
                "streaming": {"provider": True, "transport": "sse"},
            },
        }
        yield {"event": "chunk", "data": {"text": "结构化"}}
        yield {"event": "chunk", "data": {"text": "记忆"}}
        yield {
            "event": "done",
            "data": {
                "text": "结构化记忆",
                "citations": [
                    {
                        "index": 1,
                        "node_id": selected_node["node_id"],
                        "title": selected_node["title"],
                        "node_type": selected_node["node_type"],
                        "excerpt": "Memory slots improve grounded retrieval.",
                        "metadata": selected_node["metadata"],
                    }
                ],
                "streaming": {"provider": True, "transport": "sse"},
            },
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", fake_answer_question_stream)

    events = list(
        agents.wiki_ask_stream(
            "user_test",
            "对比 @[Structured Memory Paper](paper:structured-memory) 的方法",
            mentions=[{"node_id": "paper:structured-memory", "title": "Structured Memory Paper"}],
        )
    )

    assert [event["event"] for event in events] == ["meta", "chunk", "chunk", "done"]
    assert events[0]["data"]["mode"] == "wiki"
    assert events[0]["data"]["sources"][0]["url"] == "https://example.com/paper"
    assert "".join(event["data"].get("text", "") for event in events if event["event"] == "chunk") == "结构化记忆"
    assert events[-1]["data"]["streaming"]["provider"] is True


def test_desktop_wiki_ask_can_answer_general_question_without_local_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMockLLM:
        name = "mock"
        model = "mock-llm"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeMockLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct questions should not search wiki"))

    payload = agents.wiki_ask("user_test", "什么是 RAG？")

    assert payload["mode"] == "direct"
    assert payload["retrieval_required"] is False
    assert payload["citations"] == []
    assert payload["sources"] == []


def test_desktop_wiki_ask_stream_can_direct_answer_without_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            captured.update(_kwargs)
            yield "RAG"
            yield " 是检索增强生成"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeStreamingLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct stream should not search wiki"))

    events = list(agents.wiki_ask_stream("user_test", "什么是 RAG？"))

    assert [event["event"] for event in events] == ["meta", "chunk", "chunk", "done"]
    assert events[0]["data"]["mode"] == "direct"
    assert events[0]["data"]["retrieval_required"] is False
    assert "".join(event["data"].get("text", "") for event in events if event["event"] == "chunk") == "RAG 是检索增强生成"
    assert events[-1]["data"]["text"] == "RAG 是检索增强生成"
    assert captured["max_tokens"] >= 1400


def test_desktop_wiki_answer_stream_uses_longer_default_completion_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    node = {
        "node_id": "paper:rag",
        "node_type": "paper",
        "title": "RAG Paper",
        "body": "Retrieval augmented generation needs enough answer budget.",
        "metadata": {},
    }

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            captured.update(_kwargs)
            yield "完整回答"

    monkeypatch.delenv("PAPERFLOW_WIKI_ANSWER_MAX_TOKENS", raising=False)
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 1})
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "search_nodes", lambda *_args, **_kwargs: [node])
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeStreamingLLM())

    events = list(agents.wiki_answer.answer_question_stream("user_test", "总结 RAG", limit=4))

    assert events[-1]["data"]["text"] == "完整回答"
    assert captured["max_tokens"] >= 1800


def test_desktop_wiki_answer_stream_recovers_obviously_incomplete_text(monkeypatch: pytest.MonkeyPatch) -> None:
    node = {
        "node_id": "paper:weekly-work",
        "node_type": "paper",
        "title": "Weekly Work",
        "body": "The user accepted paper recommendations and drafted a reading plan this week.",
        "metadata": {},
    }
    captured = {"fallback_called": False}

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            yield "您本周的工作主要集中在论文推荐接收与阅读计划制定：在2026年6月"

        def generate(self, *_args, **_kwargs):
            captured["fallback_called"] = True

            class Response:
                text = "您本周的工作主要集中在论文推荐接收与阅读计划制定：在2026年6月12日和6月14日接收了推荐论文，并围绕阅读计划推进了后续精读。"
                prompt_tokens = 0
                completion_tokens = 0

            return Response()

    monkeypatch.setattr(agents.wiki_answer.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 1})
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "search_nodes", lambda *_args, **_kwargs: [node])
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeStreamingLLM())

    events = list(agents.wiki_answer.answer_question_stream("user_test", "总结一下我这一周的工作", limit=4))

    assert captured["fallback_called"] is True
    assert events[-1]["data"]["text"].endswith("后续精读。")


def test_desktop_source_options_exposes_push_sources() -> None:
    options = agents.source_options()

    assert any(item["id"] == "cs.LG" for item in options["arxiv_categories"])
    assert any(item["id"] == "ICLR" for item in options["conferences"])
    iclr = next(item for item in options["conferences"] if item["id"] == "ICLR")
    assert iclr["source"]
    assert iclr["venue_id"]
    assert "acceptance_timeline" in iclr
    assert "conference_date" in iclr
    assert options["journals"]


def test_desktop_save_settings_updates_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PAPERFLOW_LLM_MODEL=old-model\nOPENAI_API_KEY=sk-existing\n", encoding="utf-8")
    monkeypatch.setattr(agents, "ENV_PATH", env_path)

    result = agents.save_settings(
        {
            "PAPERFLOW_LLM_MODEL": "new-model",
            "OPENAI_API_KEY": "***",
            "PAPERFLOW_WRITE_FEISHU": "true",
            "PAPERFLOW_ENABLE_ARXIV": "false",
            "PAPERFLOW_CUSTOM_RSS_URLS": "https://example.com/rss.xml",
            "PAPERFLOW_CONFERENCE_ACCESS_MODE": "credential",
            "PAPERFLOW_CONFERENCE_COOKIE_FILE": r"C:\paperflow\cookies\neurips.txt",
            "SEMANTIC_SCHOLAR_API_KEY": "s2-test-key",
            "OPENREVIEW_TOKEN": "or-test-token",
            "PAPERFLOW_REPORT_STYLE": "deep",
            "PAPERFLOW_DAILY_LIMIT": "17",
            "PAPERFLOW_RELEVANCE_THRESHOLD": "72",
            "PAPERFLOW_MAX_CONCURRENCY": "4",
            "PAPERFLOW_PDF_DIR": str(tmp_path / "pdf-cache"),
            "PAPERFLOW_READING_REPORTS_DIR": str(tmp_path / "reading-reports"),
            "PAPERFLOW_WIKI_DIR": str(tmp_path / "knowledge-base"),
            "HTTP_PROXY": "http://127.0.0.1:18080",
            "UNSUPPORTED_KEY": "ignored",
        }
    )

    text = env_path.read_text(encoding="utf-8")
    assert "PAPERFLOW_LLM_MODEL=new-model" in text
    assert "OPENAI_API_KEY=sk-existing" in text
    assert "PAPERFLOW_WRITE_FEISHU=true" in text
    assert "PAPERFLOW_ENABLE_ARXIV=false" in text
    assert "PAPERFLOW_CUSTOM_RSS_URLS=https://example.com/rss.xml" in text
    assert f"PAPERFLOW_PDF_DIR={tmp_path / 'pdf-cache'}" in text
    assert f"PAPERFLOW_READING_REPORTS_DIR={tmp_path / 'reading-reports'}" in text
    assert f"PAPERFLOW_WIKI_DIR={tmp_path / 'knowledge-base'}" in text
    assert result["paths"]["pdf_dir"] == str(tmp_path / "pdf-cache")
    assert result["paths"]["reading_reports_dir"] == str(tmp_path / "reading-reports")
    assert result["paths"]["wiki_dir"] == str(tmp_path / "knowledge-base")
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE=credential" in text
    assert r"PAPERFLOW_CONFERENCE_COOKIE_FILE=C:\paperflow\cookies\neurips.txt" in text
    assert "SEMANTIC_SCHOLAR_API_KEY=s2-test-key" in text
    assert "OPENREVIEW_TOKEN=or-test-token" in text
    assert "PAPERFLOW_REPORT_STYLE=deep" in text
    assert "PAPERFLOW_DAILY_LIMIT=17" in text
    assert "PAPERFLOW_RELEVANCE_THRESHOLD=72" in text
    assert "PAPERFLOW_MAX_CONCURRENCY=4" in text
    assert "HTTP_PROXY=http://127.0.0.1:18080" in text
    assert "UNSUPPORTED_KEY" not in text
    assert result["paths"]["write_feishu"] is True
    assert result["report_preferences"]["style"] == "deep"
    assert result["advanced"]["daily_limit"] == 17
    assert result["advanced"]["relevance_threshold"] == 72
    assert result["advanced"]["http_proxy"] == "http://127.0.0.1:18080"
    assert result["source_preferences"]["conference_access_mode"] == "credential"
    assert result["source_preferences"]["auth_status"]["semantic_scholar_api_key"] is True


def test_desktop_daily_push_uses_saved_settings_when_gui_omits_filters(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PAPERFLOW_DAILY_LIMIT=17",
                "PAPERFLOW_RELEVANCE_THRESHOLD=60",
                "PAPERFLOW_ENABLE_ARXIV=false",
                "PAPERFLOW_ENABLE_OPENREVIEW=false",
                "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR=true",
                "PAPERFLOW_ENABLE_CUSTOM_RSS=true",
                "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES=cs.LG,cs.CV",
                "PAPERFLOW_DEFAULT_CONFERENCES=ICLR,NeurIPS",
                "PAPERFLOW_DEFAULT_JOURNALS=Nature",
                "PAPERFLOW_CUSTOM_RSS_URLS=https://example.com/feed.xml",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    captured: dict[str, object] = {}

    def fake_daily_push(**kwargs):
        captured.update(kwargs)
        return {"push_id": "push_settings_effect"}

    monkeypatch.setattr(agents.daily_agent, "daily_push", fake_daily_push)
    monkeypatch.setattr(agents.db_ops, "get_push_papers", lambda push_id: None)
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: None)

    agents.run_daily_push("user_settings", days=2)

    assert captured["limit_per_source"] == 17
    assert captured["push_limit"] == 17
    assert captured["arxiv_categories"] == []
    assert captured["conferences"] == []
    assert captured["journals"] == ["Nature"]
    assert captured["enable_semantic_scholar"] is True
    assert captured["enable_custom_rss"] is True
    assert captured["custom_rss_urls"] == ["https://example.com/feed.xml"]


def test_desktop_relevance_threshold_changes_daily_push_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    base = {
        "threshold_high_relevant": 0.40,
        "threshold_maybe_interested": 0.25,
        "threshold_edge_relevant": 0.15,
        "min_relevance_signal": 0.08,
    }

    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "90")
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "12")
    strict = agents.daily_agent.apply_relevance_threshold_override(base)
    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "30")
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "8")
    relaxed = agents.daily_agent.apply_relevance_threshold_override(base)

    assert strict["threshold_edge_relevant"] > base["threshold_edge_relevant"]
    assert relaxed["threshold_edge_relevant"] < base["threshold_edge_relevant"]
    assert strict["paperflow_relevance_threshold"] == 90
    assert strict["push_target_count"] == 12
    assert strict["push_max_count"] == 12
    assert relaxed["push_target_count"] == 8


def test_daily_push_custom_rss_fetcher_builds_paper_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    rss = b"""<?xml version="1.0"?>
    <rss><channel><item>
      <title>RSS Paper</title>
      <link>https://example.com/paper</link>
      <description>RSS abstract</description>
      <pubDate>Mon, 01 Jun 2026 00:00:00 GMT</pubDate>
    </item></channel></rss>
    """

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return rss

    monkeypatch.setattr(agents.daily_agent.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    papers = agents.daily_agent.fetch_custom_rss_papers(["https://example.com/rss.xml"], 5)

    assert papers[0]["title"] == "RSS Paper"
    assert papers[0]["source"] == "custom_rss"
    assert papers[0]["paper_url"] == "https://example.com/paper"


def test_daily_push_semantic_scholar_fetcher_uses_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        b'{"data":[{"title":"Semantic Paper","abstract":"Graph result",'
        b'"authors":[{"name":"Ada"}],"publicationDate":"2026-06-01",'
        b'"url":"https://semanticscholar.org/paper/1","venue":"ACL",'
        b'"externalIds":{"ArXiv":"2606.00001","DOI":"10.0000/test"}}]}'
    )
    captured_headers = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    def fake_urlopen(request, timeout=20):
        captured_headers.update(dict(request.header_items()))
        return FakeResponse()

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-live-test")
    monkeypatch.setattr(agents.daily_agent.urllib.request, "urlopen", fake_urlopen)

    papers = agents.daily_agent.fetch_semantic_scholar_papers(["retrieval"], days=30, limit_per_source=5)

    assert captured_headers["X-api-key"] == "s2-live-test"
    assert papers[0]["title"] == "Semantic Paper"
    assert papers[0]["source"] == "semantic_scholar"
    assert papers[0]["arxiv_id"] == "2606.00001"


def test_latest_push_metadata_lifts_generation_settings_from_paper_rows() -> None:
    metadata = agents.db_ops._derive_push_metadata_from_papers(  # noqa: SLF001 - persisted GUI metadata contract
        [
            {
                "metadata": {
                    "paper_count": 17,
                    "total_fetched": 50,
                    "daily_limit": 17,
                    "push_target_count": 17,
                    "push_max_count": 17,
                    "limit_per_source": 17,
                    "fetch_days": 1,
                    "relevance_threshold": 72,
                    "arxiv_categories": ["cs.LG"],
                    "conferences": [],
                    "journals": ["Nature"],
                    "enable_semantic_scholar": True,
                    "enable_custom_rss": True,
                    "custom_rss_urls": ["https://example.com/feed.xml"],
                }
            }
        ]
    )

    assert metadata["paper_count"] == 17
    assert metadata["total_fetched"] == 50
    assert metadata["daily_limit"] == 17
    assert metadata["push_target_count"] == 17
    assert metadata["push_max_count"] == 17
    assert metadata["limit_per_source"] == 17
    assert metadata["relevance_threshold"] == 72
    assert metadata["custom_rss_urls"] == ["https://example.com/feed.xml"]


def test_desktop_source_settings_explain_conference_auth() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'name="conferenceAccessMode"' in html
    assert 'value="credential"' in html
    assert 'data-env-key="SEMANTIC_SCHOLAR_API_KEY"' in html
    assert 'data-env-key="OPENREVIEW_TOKEN"' in html
    assert 'data-env-key="PAPERFLOW_CONFERENCE_COOKIE_FILE"' in html
    assert 'id="settingConferenceList"' in html
    assert "settingConferenceSelect" not in html
    assert "settings-model" in html
    assert "settings-source" in html
    assert "settings-storage" in html
    assert "模型与密钥" in html
    assert "论文来源" in html
    assert "需要登录的会议源不要混在普通下拉框里" in html
    assert "updateSourceAuthStatus(sourcePrefs, env)" in script
    assert "renderConferenceSettings(sourcePrefs)" in script
    assert "selectedSettingConferences().join(\",\")" in script
    assert "conferenceAccessInfo(item)" in script
    assert "syncConferenceAccessUi(input.value)" in script
    assert "settingEnableCustomRss" in script
    assert 'input.disabled = normalized !== "credential"' in script
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE" in script
    assert "state.settings = data || {}" in script
    assert "syncDailySourceControls(sourcePrefs)" in script
    assert "limit_per_source: configuredDailyLimit()" in script
    assert "PAPERFLOW_LLM_MODEL" in script
    assert ".source-auth-panel" in css
    assert ".conference-source-list" in css
    assert ".conference-source-item.active" in css
    assert ".settings-source .source-auth-panel" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(320px, 360px)" in css
    assert '[data-mode="credential"]' in css
    assert "label:has(input:checked)" in css


def test_desktop_settings_controls_use_compact_typography() -> None:
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert ".setting-card {\n  display: grid;\n  gap: 11px;\n  padding: 15px;" in css
    assert ".setting-card button,\n.setting-card input,\n.setting-card select,\n.setting-card textarea {\n  font-size: 13px;" in css
    assert ".setting-card input,\n.setting-card select,\n.setting-card textarea {\n  min-height: 34px;\n  padding: 7px 9px;" in css
    assert ".setting-card button {\n  min-height: 34px;\n  padding: 7px 10px;" in css
    assert ".setting-card-head h2 {\n  margin: 0;\n  font-size: 15px;" in css
    assert ".settings-source .source-edit-row {\n  grid-column: 2;\n  grid-row: 5;\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) 74px;" in css
    assert ".settings-source .source-edit-row button {\n  white-space: normal;\n  line-height: 1.2;" in css
    assert ".settings-storage .button-row button,\n.settings-advanced > button,\n.profile-card #saveProfileBtn {\n  min-height: 34px;\n  font-size: 13px;" in css


def test_desktop_reports_view_uses_compact_reading_typography() -> None:
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert ".report-list-pane .pane-head h2 {\n  font-size: 14px;" in css
    assert ".report-list-pane .pane-head select,\n.report-list-pane .pane-head button,\n.report-filter-row input,\n.filter-actions button {\n  min-height: 32px;\n  padding: 6px 8px;\n  font-size: 12.5px;" in css
    assert ".report-list-pane .pane-head button,\n.filter-actions button,\n.report-reader .reader-head .button-row button {\n  white-space: nowrap;" in css
    assert ".report-row {\n  width: 100%;\n  display: block;\n  text-align: left;\n  border-color: #e0e9f6;\n  background: #fff;\n  padding: 8px 9px;\n  font-size: 12px;" in css
    assert ".reader-head h2 {\n  margin: 0 0 4px;\n  font-size: 18px;" in css
    assert ".markdown-body {\n  padding: 14px 0 4px;\n  color: #25354f;\n  line-height: 1.68;\n  font-size: 13.5px;" in css
    assert ".markdown-body h1 {\n  font-size: 19px;" in css


def test_desktop_direct_read_generation_shows_status_feedback() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="directArxivStatus"' in html
    assert 'id="directPdfStatus"' in html
    assert 'class="direct-read-status"' in html
    assert "function setDirectReadStatus" in script
    assert "function setDirectReadBusy" in script
    assert "正在生成${sourceLabel}精读报告" in script
    assert "后端正在拉取论文信息、调用模型并写入本地报告库" in script
    assert "报告已生成" in script
    assert "报告生成失败" in script
    assert "请先填写 arXiv ID" in script
    assert "请先填写 PDF 路径" in script
    assert "showFeedbackToast(warning ? \"warning\" : \"success\", \"精读报告已生成\", reportTitle)" in script
    assert "await openReport(doc.report_id)" in script
    assert ".direct-read-status {" in css
    assert ".direct-read-status.success" in css
    assert ".direct-read-status.warning" in css
    assert ".direct-read-status.error" in css
    assert ".primary.loading" in css


def test_desktop_user_picker_hydrates_settings_profile_form() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="profileSyncStatus"' in html
    assert 'id="profileInfoGrid"' in html
    assert 'id="profileTagGrid"' not in html
    assert ".profile-tag-grid" not in css
    assert ".setting-card-head small" in css
    assert ".profile-info-grid" in css
    assert ".profile-info-item.wide" in css
    assert "function renderProfileForm(data = {})" in script
    assert "function renderProfileInfoGrid(profile, raw, userInfo, details)" in script
    assert "function profileAffiliation(raw, userInfo)" in script
    assert "async function loadCurrentProfile()" in script
    assert "/api/profile?user_id=${encodeURIComponent(userId)}" in script
    assert "renderProfileForm(data);" in script
    assert "await loadCurrentProfile();" in script
    assert "$(\"profileUserId\").value = userId;" in script
    assert 'profileInfoItem("个人机构", profileAffiliation(raw, userInfo), "wide")' in script
    assert 'profileEditItem("关注方向", "profileDirectionsInput"' in script
    assert 'profileEditItem("关注关键词", "profileKeywordsInput"' in script
    assert 'profileEditItem("关注作者", "profileAuthorsInput"' in script
    assert 'profileEditItem("关注机构", "profileInstitutionsInput"' in script
    assert 'profileEditItem("关注主题", "profileTopicsInput"' in script
    assert 'profileAffiliationInput' not in script
    assert "用分号或换行分隔；可写 方向:0.8" in script
    assert "用分号或换行分隔；可写 主题:0.8" in script
    assert 'profileInfoItem("机构", listText(mustRead.institutions, 8), "wide")' not in script
    assert 'core_directions_text: $("profileDirectionsInput")?.value || ""' in script
    assert 'topic_weights_text: $("profileTopicsInput")?.value || ""' in script
    assert 'must_read_keywords: splitListValue($("profileKeywordsInput")?.value || "")' in script
    assert ".profile-info-item.editable" in css
    assert ".profile-info-item.editable small" in css
    assert "$(\"naturalLanguage\").value = profileEditableDescription(raw, userInfo);" in script
    assert 'renderSettingTags("profileTagGrid"' not in script
    assert 'userInfo.has_profile ? "画像已加载" : "尚未生成画像，可在此补充"' in script
    assert "showSettingsMessage(`已加载 ${userId} 的画像信息。`);" in script


def test_desktop_save_profile_applies_manual_editable_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "user_id": "user_test",
        "version": "0.1",
        "core_directions": {"old": 0.2},
        "topic_weights": {"old topic": 0.1},
        "must_read": {"authors": ["Old"], "institutions": [], "keywords": []},
    }
    saved = {}

    monkeypatch.setattr(agents.coldstart_agent, "cold_start", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(agents.db_ops, "get_profile", lambda user_id: saved.get(user_id) or profile)

    def fake_update_profile(user_id, updated):
        saved[user_id] = updated
        return True

    monkeypatch.setattr(agents.db_ops, "update_profile", fake_update_profile)

    result = agents.create_or_update_profile(
        user_id="user_test",
        affiliation="OpenAI",
        core_directions_text="GUI Agent:0.8; Scientific Discovery=0.6",
        topic_weights_text="paper recommendation:0.7",
        must_read_keywords=["agent", "rag"],
        must_read_authors=["Alice"],
        must_read_institutions=["Stanford"],
    )

    updated = saved["user_test"]
    assert updated["affiliation"] == "OpenAI"
    assert updated["core_directions"] == {"GUI Agent": 0.8, "Scientific Discovery": 0.6}
    assert updated["topic_weights"] == {"paper recommendation": 0.7}
    assert updated["must_read"] == {
        "authors": ["Alice"],
        "institutions": ["Stanford"],
        "keywords": ["agent", "rag"],
    }
    assert result["profile"]["top_directions"][0] == ("GUI Agent", 0.8)


def test_desktop_health_is_json_ready() -> None:
    health = agents.health()
    assert health["ok"] is True
    assert "database" in health


def test_desktop_paper_card_backfills_arxiv_links() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "Arxiv Paper", "arxiv_id": "2606.02556v1", "source": "arxiv"},
        1,
    )

    assert card["url"] == "https://arxiv.org/abs/2606.02556v1"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.02556v1"
    assert card["arxiv_id"] == "2606.02556v1"
    assert card["source"] == "arxiv"


def test_desktop_paper_card_extracts_arxiv_id_from_url() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "Arxiv URL Paper", "url": "https://arxiv.org/abs/2606.03963v1"},
        1,
    )

    assert card["url"] == "https://arxiv.org/abs/2606.03963v1"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.03963v1"
    assert card["arxiv_id"] == "2606.03963v1"


def test_desktop_paper_card_backfills_doi_link_from_metadata() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "DOI Paper", "metadata": {"doi": "10.1038/example"}},
        1,
    )

    assert card["url"] == "https://doi.org/10.1038/example"
    assert card["pdf_url"] == ""
    assert card["doi"] == "10.1038/example"


def test_desktop_paper_card_prefers_explicit_url_over_fallbacks() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {
            "title": "Publisher Paper",
            "url": "https://publisher.example/paper",
            "arxiv_id": "2606.02556v1",
            "metadata": {"doi": "10.1038/example"},
        },
        1,
    )

    assert card["url"] == "https://publisher.example/paper"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.02556v1"


def test_desktop_must_read_payload_normalizes_missing_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.db_ops,
        "get_profile",
        lambda user_id: {"must_read": {"authors": ["Alice"], "keywords": ["agent"]}},
    )

    payload = agents.list_must_read("user_test")

    assert payload["must_read"]["authors"] == ["Alice"]
    assert payload["must_read"]["institutions"] == []
    assert payload["must_read"]["keywords"] == ["agent"]


def test_desktop_provider_test_uses_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "mock")
    monkeypatch.setenv("PAPERFLOW_LLM_MODEL", "mock-llm")

    result = agents.test_provider("llm")

    assert result["ok"] is True
    assert result["kind"] == "llm"
    assert result["provider"] == "mock"


def test_desktop_submit_and_read_forwards_feishu_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    monkeypatch.setattr(
        agents,
        "submit_gui_feedback",
        lambda **kwargs: {
            "selected_numbers": [1],
            "skipped_numbers": [],
            "profile": {},
        },
    )

    def fake_create_reading_reports(**kwargs):
        captured.update(kwargs)
        return {"created_docs": [], "count": 0}

    monkeypatch.setattr(agents, "create_reading_reports", fake_create_reading_reports)

    agents.submit_and_read(
        user_id="user_test",
        push_id="push_test",
        selected_numbers=[1],
        skipped_numbers=[],
        write_feishu=True,
    )

    assert captured["write_feishu"] is True


def test_desktop_reading_reports_forward_saved_report_style(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PAPERFLOW_REPORT_STYLE=brief\n", encoding="utf-8")
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {"papers": [{"id": 1, "title": "Styled Paper"}]},
    )
    captured: dict[str, object] = {}

    def fake_create_reading_report(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(agents.reading_agent, "create_reading_report", fake_create_reading_report)

    agents.create_reading_reports(
        user_id="user_style",
        push_id="push_style",
        paper_numbers=[1],
        write_feishu=False,
    )

    assert captured["request_metadata"]["report_style"] == "brief"


def test_desktop_direct_arxiv_read_generates_backend_report(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "direct-arxiv.md"
    report_path.write_text("# Direct arXiv Report\n", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        agents.db_ops,
        "get_paper_by_arxiv_id",
        lambda arxiv_id: {
            "id": 7,
            "arxiv_id": arxiv_id,
            "title": "Direct arXiv Paper",
            "authors": ["Alice"],
            "abstract": "A direct read paper.",
            "source": "arxiv",
        },
    )
    monkeypatch.setattr(agents, "_backfill_docs_to_wiki", lambda user_id, docs: 1)

    def fake_create_reading_report(**kwargs):
        captured.update(kwargs)
        return [
            {
                "title": "Direct arXiv Report",
                "report_path": str(report_path),
                "paper": kwargs["papers"][0],
            }
        ]

    monkeypatch.setattr(agents.reading_agent, "create_reading_report", fake_create_reading_report)

    result = agents.read_arxiv("user_direct", "https://arxiv.org/abs/2606.03963", write_feishu=False)

    assert result["count"] == 1
    assert result["wiki_backfilled"] == 1
    assert result["created_docs"][0]["title"] == "Direct arXiv Report"
    assert result["created_docs"][0]["report_id"]
    assert captured["user_id"] == "user_direct"
    assert captured["request_metadata"]["report_source_type"] == "desktop_arxiv"
    assert captured["request_metadata"]["report_source_key"] == "2606.03963"


def test_reading_report_template_changes_with_saved_style() -> None:
    report = agents.reading_agent.generate_reading_report(
        {"title": "Styled Paper", "abstract": "A structured abstract."},
        {"core_directions": {}},
        report_payload={
            "report_style": "deep",
            "one_sentence_summary": "A concise summary.",
            "abstract": "A structured abstract.",
            "recommendation_label": "maybe_interested",
        },
    )

    assert "Deep-Dive Checklist" in report


def test_desktop_backfills_reused_reading_report_to_wiki(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "reading-report.md"
    report_path.write_text(
        "---\n"
        'title: "Reused Report"\n'
        'arxiv_id: "2606.12087v1"\n'
        "---\n"
        "# Reused Report\n\nImportant report body.",
        encoding="utf-8",
    )
    captured = {}

    def fake_ingest(**kwargs):
        captured.update(kwargs)
        return {"paper_node": "paper:2606.12087v1", "section_count": 0}

    monkeypatch.setattr(agents.reading_agent, "ingest_reading_report_to_wiki", fake_ingest)

    docs = [{"paper": {"title": "Fallback title"}, "report_path": str(report_path), "reused": True}]
    count = agents._backfill_docs_to_wiki("user_test", docs)  # noqa: SLF001 - GUI backfill contract

    assert count == 1
    assert captured["user_id"] == "user_test"
    assert captured["paper"]["arxiv_id"] == "2606.12087v1"
    assert "Important report body." in captured["report_content"]
    assert docs[0]["wiki_ingest"]["paper_node"] == "paper:2606.12087v1"


def test_desktop_paper_card_actions_are_mutually_exclusive_before_submit() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'data-action="read"' in script
    assert '"加载中"' in script
    assert '"精读报告"' in script
    assert '"已选精读"' in script
    assert "readSinglePaper" in script
    assert "setPaperDisposition(number, \"read\")" in script
    assert "setPaperDisposition(number, \"skip\")" in script
    assert "setPaperDisposition(number, \"later\")" in script
    assert "同一篇论文只能选择精读、不感兴趣、稍后看中的一种" in script
    assert "待提交：" in script
    assert "card.dataset.disposition = disposition" in script
    assert "delete card.dataset.disposition" in script
    assert '"已不感兴趣"' in script
    assert '"已加入稍后看"' in script
    assert "selected_numbers: selectedNumbers" in script
    assert "请先选择精读论文" in script
    assert "selected_numbers: [number]" not in script
    assert 'button.dataset.action === "select"' not in script
    assert '.paper-card[data-disposition="skip"]' in css
    assert '.paper-card[data-disposition="later"]' in css
    assert '.paper-actions button[data-action="read"].active' in css
    assert '.paper-actions button[data-action="skip"].active' in css
    assert '.paper-actions button[data-action="later"].active' in css


def test_desktop_skip_and_later_feedback_submit_to_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_events: list[tuple[int, str, str]] = []

    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "papers": [
                {"id": "p1", "title": "Read Paper", "category": "agent"},
                {"id": "p2", "title": "Skip Paper", "category": "agent"},
                {"id": "p3", "title": "Later Paper", "category": "memory"},
            ]
        },
    )
    monkeypatch.setattr(agents.feedback_agent, "get_existing_selected_numbers", lambda user_id, push_id, papers: set())
    monkeypatch.setattr(agents.db_ops, "get_profile", lambda user_id: {"core_directions": {}})
    monkeypatch.setattr(agents.db_ops, "get_recent_selected_papers", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.feedback_agent, "estimate_feedback_strength_multiplier", lambda push_id, current_timestamp: (1.0, 0.0))
    monkeypatch.setattr(agents.feedback_agent, "update_profile_based_on_selection", lambda **kwargs: {"core_directions": {"agent": 1}})
    monkeypatch.setattr(agents.feedback_agent, "ingest_profile_drift_to_wiki", lambda **kwargs: None)

    def fake_log_feedback_event(**kwargs):
        captured_events.append((kwargs["paper_number"], kwargs["action"], kwargs["action_type"]))
        return len(captured_events)

    monkeypatch.setattr(agents, "_log_feedback_event", fake_log_feedback_event)

    result = agents.submit_gui_feedback(
        user_id="user_test",
        push_id="push_test",
        selected_numbers=[1],
        skipped_numbers=[2],
        later_numbers=[3],
    )

    assert result["selected_numbers"] == [1]
    assert result["skipped_numbers"] == [2]
    assert result["later_numbers"] == [3]
    assert (1, "selected", "gui_selected") in captured_events
    assert (2, "skipped", "gui_skipped") in captured_events
    assert (3, "later", "gui_later") in captured_events


def test_desktop_wiki_frontend_derives_architecture_from_backend_graph() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert "buildWikiMap" in script
    assert "conceptEntriesFromGraph" in script
    assert "candidateLabelsForNode" in script
    assert "architecture:core" in script
    assert "知识库架构" in script
    assert "原始节点" in script
    assert "related_papers" in script
    assert "setWikiMapFocus(\"architecture:core\")" in script
    assert "wikiMapCatalog" not in script
    assert "concept:structured-memory" not in script
    assert "concept:agent" not in script
    assert "&limit=48" in script
    assert "const query = rawQuery ||" not in script
    assert 'DEMO_MODE ? demoWikiNodes : []' in script
    assert 'class="wiki-entry-body"' in html
    assert "Wiki 架构图" in html
    assert "grid-template-columns: minmax(760px, 1fr) 292px" in css
    assert "repeating-linear-gradient(115deg" in css
    assert ".wiki-evidence-pane" in css
    assert "position: sticky" in css
    assert "left: calc(100% + 9px)" in css
    assert 'setWikiEntry("结构化记忆", "跨论文沉淀的 memory slot' not in script


def test_desktop_wiki_frontend_recovers_when_graph_is_empty() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert "wiki_search_fallback" in script
    assert "!state.wikiNodes.length && Number(stats.nodes || 0) > 0" in script
    assert "/api/wiki/search?user_id=" in script


def test_desktop_feedback_submit_shows_user_confirmation() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="feedbackToast"' in html
    assert 'id="paperFeedbackResult"' in html
    assert ".feedback-toast.success" in css
    assert ".paper-feedback-result.success" in css
    assert ".paper-feedback-result.pending" in css
    assert "showSubmitResult(data, generateReports)" in script
    assert "showPaperFeedback(result.type, result.title, result.detail)" in script
    assert "setSubmitButtonsBusy(true, generateReports)" in script
    assert "正在提交反馈" in script
    assert "反馈已提交" in script
    assert "已写入本地反馈" in script
    assert "反馈提交失败" in script
    assert "await loadWiki()" in script


def test_desktop_buttons_have_unified_visual_feedback() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert "buttonFeedbackTimers: new WeakMap()" in script
    assert "lastActionButton: null" in script
    assert "function flashButtonFeedback" in script
    assert "function setActionButtonBusy" in script
    assert "function bindButtonFeedback" in script
    assert "document.addEventListener(\"click\"" in script
    assert "state.lastActionButton = button" in script
    assert "setActionButtonBusy(actionButton, true)" in script
    assert "flashButtonFeedback(actionButton, \"success\")" in script
    assert "flashButtonFeedback(actionButton, \"error\")" in script
    assert "bindButtonFeedback();" in script
    assert "已全选论文来源" in script
    assert "已清空论文来源" in script
    assert "已复制报告路径" in script
    assert "已打开链接" in script
    assert "已移除" in script
    assert "button.feedback-click::after" in css
    assert "button.feedback-success::after" in css
    assert "button.feedback-error::after" in css
    assert "button.is-busy" in css
    assert "@keyframes button-feedback-flash" in css
    assert "@keyframes button-busy-spin" in css


def test_desktop_paper_date_and_metrics_sync_with_backend() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert '<strong id="candidateStat">-</strong>' in html
    assert '<strong id="filteredStat">-</strong>' in html
    assert "当前批次候选" in html
    assert "推荐数" in html
    assert "今日候选" not in html
    assert 'id="cacheSizeStat"' in html
    assert "2.8GB" not in html
    assert "cache_display" in script
    assert "storage_stats" in script
    assert 'new Date("2026-06-10")' not in script
    assert "function todayDateValue()" in script
    assert "function syncDateControls()" in script
    assert '$("paperDate").value = todayDateValue()' in script
    assert "selectedDateFetchDays()" in script
    assert "runButton.disabled = false" in script
    assert 'target_date: $("paperDate").value' in script
    assert "每日上限 ${metadata.daily_limit}" in script
    assert "旧缓存参数不一致时会自动刷新" in script
    assert 'id="saveAdvancedSettingsBtn" class="primary" type="button">保存设置</button>' in html
    assert 'runAction(saveSettings, "保存设置")' in script
    assert "/api/daily/status?task_id=" in script
    assert "/api/daily/status?user_id=" in script
    assert "pollDailyTask(taskId, data.push, userId, pollToken)" in script
    assert "检查当天缓存" in script
    assert "已加载当天缓存" in script
    assert "本次没有重新爬取" in script
    assert 'if (data.cached || data.task?.status === "completed")' in script
    assert "fromCache: Boolean(data.cached || data.task.cached)" in script
    assert "while (pollToken === state.dailyPollToken)" in script
    assert "for (let attempt = 0; attempt < 80" not in script
    assert "function setDailyTaskState(" in script
    assert "async function resumeDailyTask()" in script
    assert 'if (name === "papers") {' in script
    assert "await resumeDailyTask()" in script
    assert "state.dailyPollToken += 1" in script
    assert "metadata.total_fetched ?? metadata.fetched_count ?? papers.length ?? 0" in script
    assert "metadata.paper_count ?? metadata.filtered_count ?? metadata.ranked_count ?? papers.length ?? 0" in script
    assert "function pushMetaText(" in script
    assert "最近缓存批次" in script
    assert "单源上限" in script
    assert 'task.status === "completed"' in script
    assert "renderPush(task.push || task.preview_push" not in script
    assert "后台仍在拉取和排序论文" in script
    assert ".paper-list.empty.syncing" in css
    assert "|| 247" not in script


def test_desktop_settings_exposes_backend_storage_stats(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_dir = tmp_path / "pdf"
    reports_dir = tmp_path / "reports"
    wiki_dir = tmp_path / "wiki"
    for path in (pdf_dir, reports_dir, wiki_dir):
        path.mkdir()
    (pdf_dir / "a.pdf").write_bytes(b"a" * 1024)
    (reports_dir / "b.md").write_bytes(b"b" * 1024)
    (wiki_dir / "c.md").write_bytes(b"c" * 1024)

    monkeypatch.setenv("PAPERFLOW_PDF_DIR", str(pdf_dir))
    monkeypatch.setenv("PAPERFLOW_READING_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("PAPERFLOW_WIKI_DIR", str(wiki_dir))

    payload = agents.settings()

    assert payload["storage_stats"]["cache_bytes"] == 3072
    assert payload["storage_stats"]["cache_display"] == "3.0KB"


def test_desktop_chat_sources_do_not_fallback_to_demo_in_real_mode() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert "Efficient Test-Time Scaling</span>" not in html
    assert "Multi-Modal RAG</span>" not in html
    assert "Wiki: 结构化记忆</span>" not in html
    assert "function renderChatSources(sources = DEMO_MODE ? demoSources : [])" in script
    assert "data.sources || demoSources" not in script
    assert "暂无参考文献" in script
    assert 'mention_required: "需要选择论文"' in script
    assert 'data.routing_reason !== "mention_required" ? "" : routingLabel(data.routing_reason)' in script
    assert 'replace(/\\*\\*([^*\\n]+?)\\*\\*/g, "<strong>$1</strong>")' in script


def test_desktop_wiki_chat_supports_clickable_citations_streaming_and_mentions() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="mentionSuggestions"' in html
    assert 'id="chatMentionChips"' in html
    assert "/api/wiki/ask/stream" in script
    assert "streamWikiAsk(payload, answerTarget, message)" in script
    assert "renderAnswerWithCitations" in script
    assert "let doneReceived = false" in script
    assert "doneReceived = true" in script
    assert "if (!doneReceived)" in script
    assert "流式连接中断，正在切换到完整回答" in script
    assert "流式回答中断，已自动切换到完整回答" in script
    assert "流式输出中断" in script
    assert "已自动切换到完整回答" in script
    assert "class=\"citation-ref\"" in script
    assert "data-citation-index" in script
    assert "focusCitationSource" in script
    assert "renderCitationRow" not in script
    assert "本地 Wiki 引用" not in script
    assert "参考文献 ·" in script
    assert "renderMentionSuggestions" in script
    assert "insertMention" in script
    assert "`@[${title}](${nodeId})`" in script
    assert "mentions: activeMentionsForQuestion(question)" in script
    assert "retrieval_required" in script
    assert ".citation-ref" in css
    assert ".mention-suggestions" in css
    assert ".answer-meta .wiki" in css
    assert ".answer-text strong" in css


def test_desktop_daily_push_preserves_empty_push_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_daily_push(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "push_id": "push_empty_001",
            "paper_count": 0,
            "total_fetched": 15,
            "reason": "all_candidates_filtered",
        }

    monkeypatch.setattr(
        agents.daily_agent,
        "daily_push",
        fake_daily_push,
    )
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "push_id": push_id,
            "push_time": "2026-06-01 12:27:12",
            "papers": [],
            "metadata": {"paper_count": 0},
        },
    )
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: None)

    payload = agents.run_daily_push(
        "test_user",
        days=1,
        arxiv_categories=["cs.LG", "cs.CV"],
        conferences=["ICLR"],
        journals=[],
    )

    assert payload["push"]["push_id"] == "push_empty_001"
    assert payload["push"]["papers"] == []
    assert payload["push"]["metadata"]["paper_count"] == 0
    assert payload["push"]["metadata"]["total_fetched"] == 15
    assert payload["push"]["metadata"]["reason"] == "all_candidates_filtered"
    assert captured["arxiv_categories"] == ["cs.LG", "cs.CV"]
    assert captured["conferences"] == ["ICLR"]
    assert captured["journals"] == []


def test_desktop_daily_push_preserves_fallback_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.daily_agent,
        "daily_push",
        lambda **kwargs: {
            "success": True,
            "push_id": "push_fallback_001",
            "paper_count": 1,
            "total_fetched": 7,
            "fallback_used": True,
            "fallback_days": 7,
            "fallback_total_fetched": 30,
            "fallback_filtered_already_handled": 2,
            "fallback_kept_candidates": 28,
            "fallback_relaxed": True,
            "fallback_source_scope": "arxiv",
        },
    )
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "push_id": push_id,
            "push_time": "2026-06-02 12:00:00",
            "papers": [{"title": "Fallback Paper"}],
            "metadata": {},
        },
    )

    payload = agents.run_daily_push("test_user", days=1)

    assert payload["push"]["metadata"]["fallback_used"] is True
    assert payload["push"]["metadata"]["fallback_days"] == 7
    assert payload["push"]["metadata"]["fallback_relaxed"] is True


def test_desktop_daily_push_task_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents,
        "run_daily_push",
        lambda *args, **kwargs: {
            "result": {"push_id": "push_task_complete"},
            "push": {"push_id": "push_task_complete", "papers": [], "metadata": {}},
        },
    )

    started = agents.start_daily_push_task("user_task_complete", days=1)
    task_id = started["task"]["task_id"]

    task = None
    for _ in range(50):
        task = agents.get_daily_push_task(task_id=task_id)["task"]
        if task and task["status"] == "completed":
            break
        time.sleep(0.02)

    assert task is not None
    assert task["status"] == "completed"
    assert task["push"]["push_id"] == "push_task_complete"


def test_desktop_daily_push_task_reuses_cached_target_date(monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = PROJECT_ROOT / ".missing-test-env"
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "30")
    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "60")
    monkeypatch.setenv("PAPERFLOW_ENABLE_ARXIV", "true")
    monkeypatch.setenv("PAPERFLOW_ENABLE_OPENREVIEW", "true")
    monkeypatch.setenv("PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR", "false")
    monkeypatch.setenv("PAPERFLOW_ENABLE_CUSTOM_RSS", "false")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_ARXIV_CATEGORIES", "cs.CL,cs.AI,cs.IR,cs.LG")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_CONFERENCES", "ICLR,NeurIPS,ACL,SIGIR")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_JOURNALS", "")
    monkeypatch.setenv("PAPERFLOW_CUSTOM_RSS_URLS", "https://arxiv.org/rss/cs.CL")
    cached_push = {
        "push_id": "push_cached_today",
        "push_time": "2026-06-14 08:00:00",
        "papers": [{"id": 1, "title": "Cached Paper"}],
        "metadata": {
            "paper_count": 1,
            "total_fetched": 8,
            "daily_limit": 30,
            "limit_per_source": 30,
            "fetch_days": 1,
            "relevance_threshold": 60,
            "arxiv_categories": ["cs.CL", "cs.AI", "cs.IR", "cs.LG"],
            "conferences": ["ICLR", "NeurIPS", "ACL", "SIGIR"],
            "journals": [],
            "enable_semantic_scholar": False,
            "enable_custom_rss": False,
            "custom_rss_urls": [],
        },
    }

    monkeypatch.setattr(agents.db_ops, "get_push_for_date", lambda user_id, target_date: cached_push)
    monkeypatch.setattr(
        agents,
        "run_daily_push",
        lambda *args, **kwargs: pytest.fail("cached daily push should not recrawl"),
    )

    started = agents.start_daily_push_task(
        "user_task_cached",
        days=1,
        target_date="2026-06-14",
    )

    assert started["cached"] is True
    assert started["task"]["status"] == "completed"
    assert started["task"]["cached"] is True
    assert started["task"]["push"]["push_id"] == "push_cached_today"
    assert started["task"]["push"]["metadata"]["cached_for_date"] == "2026-06-14"


def test_desktop_daily_push_task_ignores_cached_target_date_when_settings_change(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PAPERFLOW_DAILY_LIMIT=12",
                "PAPERFLOW_RELEVANCE_THRESHOLD=80",
                "PAPERFLOW_ENABLE_ARXIV=true",
                "PAPERFLOW_ENABLE_OPENREVIEW=false",
                "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR=false",
                "PAPERFLOW_ENABLE_CUSTOM_RSS=false",
                "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES=cs.CL",
                "PAPERFLOW_DEFAULT_CONFERENCES=",
                "PAPERFLOW_DEFAULT_JOURNALS=",
                "PAPERFLOW_CUSTOM_RSS_URLS=",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    cached_push = {
        "push_id": "push_old_settings",
        "push_time": "2026-06-14 08:00:00",
        "papers": [{"id": 1, "title": "Old Cached Paper"}],
        "metadata": {
            "paper_count": 1,
            "total_fetched": 8,
            "daily_limit": 30,
            "limit_per_source": 30,
            "fetch_days": 1,
            "relevance_threshold": 60,
            "arxiv_categories": ["cs.CL"],
            "conferences": [],
            "journals": [],
            "enable_semantic_scholar": False,
            "enable_custom_rss": False,
            "custom_rss_urls": [],
        },
    }
    started_event = threading.Event()
    release_event = threading.Event()
    captured: dict[str, object] = {}

    monkeypatch.setattr(agents.db_ops, "get_push_for_date", lambda user_id, target_date: cached_push)

    def fake_run_daily_push(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_new_settings"},
            "push": {"push_id": "push_new_settings", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    started = agents.start_daily_push_task(
        "user_task_cache_mismatch",
        days=1,
        target_date="2026-06-14",
    )

    try:
        assert started.get("cached") is not True
        assert started["task"]["status"] == "queued"
        assert started_event.wait(timeout=2)
        assert captured["limit_per_source"] == 12
    finally:
        release_event.set()


def test_desktop_daily_push_task_reuses_running_user_task(monkeypatch: pytest.MonkeyPatch) -> None:
    started_event = threading.Event()
    release_event = threading.Event()

    def fake_run_daily_push(*args, **kwargs):
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_task_running"},
            "push": {"push_id": "push_task_running", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    first = agents.start_daily_push_task("user_task_running", days=1)
    assert started_event.wait(timeout=2)
    second = agents.start_daily_push_task("user_task_running", days=1)
    release_event.set()

    assert second["already_running"] is True
    assert second["task"]["task_id"] == first["task"]["task_id"]


def test_desktop_daily_push_task_forwards_gui_filters_and_recovers_by_user(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    started_event = threading.Event()
    release_event = threading.Event()

    def fake_run_daily_push(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_task_filters"},
            "push": {"push_id": "push_task_filters", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    started = agents.start_daily_push_task(
        "user_task_filters",
        days=3,
        limit_per_source=77,
        arxiv_categories=["cs.LG", "cs.CV"],
        conferences=["ICLR"],
        journals=["Nature"],
    )

    try:
        assert started_event.wait(timeout=2)
        by_user = agents.get_daily_push_task(user_id="user_task_filters")["task"]

        assert by_user["task_id"] == started["task"]["task_id"]
        assert by_user["days"] == 3
        assert by_user["limit_per_source"] == 77
        assert by_user["arxiv_categories"] == ["cs.LG", "cs.CV"]
        assert by_user["conferences"] == ["ICLR"]
        assert by_user["journals"] == ["Nature"]
        assert captured["user_id"] == "user_task_filters"
        assert captured["days"] == 3
        assert captured["limit_per_source"] == 77
        assert captured["arxiv_categories"] == ["cs.LG", "cs.CV"]
        assert captured["conferences"] == ["ICLR"]
        assert captured["journals"] == ["Nature"]
        assert callable(captured["progress_callback"])
    finally:
        release_event.set()

    task = None
    for _ in range(50):
        task = agents.get_daily_push_task(task_id=started["task"]["task_id"])["task"]
        if task and task["status"] == "completed":
            break
        time.sleep(0.02)
    assert task is not None
    assert task["status"] == "completed"


def test_desktop_reports_payload_warns_on_feishu_failure() -> None:
    payload = agents._reports_payload(  # noqa: SLF001 - GUI warning contract
        [
            {
                "title": "Report",
                "report_path": "report.md",
                "feishu_error": "missing feishu config",
            }
        ],
        write_feishu_requested=True,
    )

    assert payload["write_feishu_requested"] is True
    assert "飞书文档发送失败" in payload["feishu_warning"]
    assert payload["created_docs"][0]["feishu_error"] == "missing feishu config"
